from __future__ import annotations

"""ROCKSOUL execution control plane over the existing g4f Client."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Sequence

from .client import Client
from .rocksoul_control import ProviderControlStore
from .rocksoul_db import RocksoulDB
from .rocksoul_execution_store import ExecutionTraceStore
from .rocksoul_intelligence import CapabilityRequirement, ExplainableRouter
from .rocksoul_policy import ExecutionPolicy, RetryAction, RetryBudget

@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    model: str
    messages: Any
    requirements: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    max_attempts: int = 3
    max_same_provider_attempts: int = 1
    max_total_time: float = 90.0
    timeout: float = 30.0
    retry_base: float = 0.25
    retry_max: float = 30.0
    retry_jitter: float = 0.0
    stream: bool = False
    kwargs: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    attempt_no: int
    provider: str
    model: str
    started_at: float
    finished_at: float
    latency_ms: float
    status: str
    error_class: str | None = None
    error: str | None = None
    response_valid: bool | None = None

@dataclass(frozen=True, slots=True)
class ExecutionResult:
    request_id: str
    ok: bool
    model: str
    provider: str | None
    response: Any = None
    attempts: tuple[ExecutionAttempt, ...] = ()
    outcome: str = "failed"
    error_class: str | None = None
    error: str | None = None

class ExecutionEngine:
    """Execute through ranked ROCKSOUL candidates without duplicating providers."""
    def __init__(self, db: RocksoulDB | None = None, client: Client | None = None) -> None:
        self.db = db or RocksoulDB()
        self.control = ProviderControlStore(self.db)
        self.trace = ExecutionTraceStore(self.db)
        self.client = client or Client()

    def _call(self, request: ExecutionRequest, provider: str) -> Any:
        return self.client.chat.completions.create(
            messages=request.messages,
            model=request.model,
            provider=provider,
            stream=request.stream,
            **request.kwargs,
        )

    def _call_with_timeout(self, request: ExecutionRequest, provider: str, timeout: float | None = None) -> Any:
        """Execute one provider call under the effective per-attempt deadline.

        ``timeout`` may be smaller than ``request.timeout`` when the remaining
        whole-request budget is smaller. This prevents an individual provider
        attempt from overrunning ``max_total_time`` merely because it started
        while a small amount of total budget remained.
        """
        call_timeout = request.timeout if timeout is None else timeout
        if call_timeout <= 0:
            return self._call(request, provider)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rocksoul-exec")
        future = executor.submit(self._call, request, provider)
        try:
            return future.result(timeout=call_timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError(f"provider {provider} timed out after {call_timeout}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _response_valid(response: Any) -> bool:
        if response is None:
            return False
        if isinstance(response, str):
            return bool(response.strip())
        return True

    def _select(self, request: ExecutionRequest) -> dict[str, Any] | None:
        requirements = [CapabilityRequirement(name) for name in request.requirements]
        return ExplainableRouter(self.db).select(request.model, requirements, request.providers or None)

    def _candidates(self, request: ExecutionRequest) -> list[Any]:
        selected_explanation = ExplainableRouter(self.db).explain(
            request.model,
            [CapabilityRequirement(name) for name in request.requirements],
            request.providers or None,
        )
        from .rocksoul_db import RouteCandidate
        return [RouteCandidate(item["provider"], item["score"], item["model_verified"], item["health_score"], item["avg_latency_ms"]) for item in selected_explanation if item["accepted"]]

    def _record_route(self, request: ExecutionRequest, candidates: Sequence[Any], selected: str | None) -> None:
        reasons = ["model_verified", "health_score", "latency_score"]
        reasons.extend(f"capability:{name}" for name in request.requirements)
        if request.providers:
            reasons.append("provider_allowlist")
        self.db.record_route(request.model, candidates, selected, reasons)

    def _stream_wrap(self, request: ExecutionRequest, provider: str, response: Any, attempt_no: int, started_at: float):
        try:
            iterator = iter(response)
        except TypeError:
            return response

        def generator():
            emitted = 0
            try:
                for chunk in iterator:
                    emitted += 1
                    yield chunk
            except Exception as exc:
                finished = time.time()
                latency_ms = max(0.0, (finished - started_at) * 1000.0)
                status = "stream_failed_after_partial" if emitted else "stream_failed_before_output"
                error_class = ExecutionPolicy.classify(exc).value
                self.trace.record_execution_attempt(
                    request.request_id, attempt_no, provider, request.model,
                    started_at, finished, latency_ms, status, error_class, str(exc), False,
                )
                self.trace.record_execution_evidence(
                    provider, request.model, False, latency_ms,
                    error_class=error_class, error=str(exc),
                )
                self.trace.record_execution_run(
                    request.request_id, request.model, started_at, finished,
                    status, provider, attempt_no, error_class,
                )
                raise
        return generator()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started_total = time.monotonic()
        started_wall = time.time()
        attempts: list[ExecutionAttempt] = []
        provider_attempts: dict[str, int] = {}
        budget = RetryBudget(
            max_attempts=max(1, request.max_attempts),
            max_total_time=max(0.0, request.max_total_time),
            max_same_provider_attempts=max(1, request.max_same_provider_attempts),
        )
        self.trace.record_execution_run(request.request_id, request.model, started_wall, None, "running", None, 0, None)

        candidates = self._candidates(request)
        self._record_route(request, candidates, candidates[0].provider if candidates else None)
        if not candidates:
            self.trace.record_execution_run(request.request_id, request.model, started_wall, time.time(), "exhausted", None, 0, "no_candidate")
            return ExecutionResult(request.request_id, False, request.model, None, attempts=(), outcome="exhausted", error_class="no_candidate", error="No eligible provider candidates")

        index = 0
        current_provider: str | None = None
        while len(attempts) < budget.max_attempts:
            elapsed = time.monotonic() - started_total
            if elapsed >= budget.max_total_time:
                break
            if current_provider is not None:
                provider = current_provider
            else:
                while index < len(candidates) and provider_attempts.get(candidates[index].provider, 0) >= budget.max_same_provider_attempts:
                    index += 1
                if index >= len(candidates):
                    break
                provider = candidates[index].provider
                index += 1
            provider_attempts[provider] = provider_attempts.get(provider, 0) + 1
            if not budget.allows(len(attempts), time.monotonic() - started_total, provider_attempts[provider] - 1):
                break
            remaining_total = budget.max_total_time - (time.monotonic() - started_total)
            if remaining_total <= 0:
                break
            effective_timeout = remaining_total if request.timeout <= 0 else min(request.timeout, remaining_total)
            started = time.time()
            monotonic_started = time.monotonic()
            attempt_no = len(attempts) + 1
            try:
                response = self._call_with_timeout(request, provider, effective_timeout)
                finished = time.time()
                latency_ms = (time.monotonic() - monotonic_started) * 1000.0
                if not self._response_valid(response):
                    raise ValueError("empty or invalid provider response")
                exposed_response = self._stream_wrap(request, provider, response, attempt_no, started) if request.stream else response
                attempt = ExecutionAttempt(attempt_no, provider, request.model, started, finished, latency_ms, "success", response_valid=True)
                attempts.append(attempt)
                self.trace.record_execution_attempt(request.request_id, attempt_no, provider, request.model, started, finished, latency_ms, "success", None, None, True)
                self.trace.record_execution_evidence(provider, request.model, True, latency_ms)
                self.trace.record_execution_run(request.request_id, request.model, started_wall, time.time(), "success", provider, len(attempts), None)
                return ExecutionResult(request.request_id, True, request.model, provider, response=exposed_response, attempts=tuple(attempts), outcome="success")
            except Exception as exc:
                finished = time.time()
                latency_ms = (time.monotonic() - monotonic_started) * 1000.0
                decision = ExecutionPolicy.decide(exc)
                error_class = decision.error_class.value
                attempt = ExecutionAttempt(attempt_no, provider, request.model, started, finished, latency_ms, "failed", error_class, str(exc), False)
                attempts.append(attempt)
                self.trace.record_execution_attempt(request.request_id, attempt_no, provider, request.model, started, finished, latency_ms, "failed", error_class, str(exc), False)
                self.trace.record_execution_evidence(provider, request.model, False, latency_ms, error_class=error_class, error=str(exc))
                if decision.action is RetryAction.TERMINAL:
                    self.trace.record_execution_run(request.request_id, request.model, started_wall, time.time(), "failed", provider, len(attempts), error_class)
                    return ExecutionResult(request.request_id, False, request.model, provider, attempts=tuple(attempts), outcome="failed", error_class=error_class, error=str(exc))
                if decision.action is RetryAction.COOLDOWN_NEXT_PROVIDER:
                    self.control.cooldown(provider, min(decision.cooldown_seconds, request.retry_max), reason=error_class)
                if len(attempts) >= budget.max_attempts or time.monotonic() - started_total >= budget.max_total_time:
                    break
                delay = ExecutionPolicy.backoff_seconds(decision, len(attempts) - 1, base=request.retry_base, maximum=request.retry_max, jitter=request.retry_jitter)
                if delay > 0:
                    remaining = budget.max_total_time - (time.monotonic() - started_total)
                    if remaining <= 0:
                        break
                    time.sleep(min(delay, remaining))
                if decision.action is RetryAction.RECOMPUTE_CANDIDATES:
                    candidates = self._candidates(request)
                    self._record_route(request, candidates, candidates[0].provider if candidates else None)
                    index = 0
                    current_provider = None
                elif decision.action is RetryAction.BOUNDED_RETRY and provider_attempts[provider] < budget.max_same_provider_attempts:
                    current_provider = provider
                else:
                    current_provider = None

        last = attempts[-1] if attempts else None
        outcome = "budget_exhausted" if last is None or time.monotonic() - started_total >= budget.max_total_time else "exhausted"
        error_class = "budget_exhausted" if outcome == "budget_exhausted" else (last.error_class if last else "exhausted")
        error = "Execution total-time budget exhausted before a provider attempt" if last is None and outcome == "budget_exhausted" else (last.error if last else "No provider succeeded")
        self.trace.record_execution_run(request.request_id, request.model, started_wall, time.time(), outcome, last.provider if last else None, len(attempts), error_class)
        return ExecutionResult(request.request_id, False, request.model, last.provider if last else None, attempts=tuple(attempts), outcome=outcome, error_class=error_class, error=error)

    def route_explain(self, model: str, requirements: Sequence[str] = ()) -> list[dict[str, Any]]:
        return ExplainableRouter(self.db).explain(model, [CapabilityRequirement(name) for name in requirements])

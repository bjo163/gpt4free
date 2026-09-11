from __future__ import annotations

"""ROCKSOUL execution control plane over the existing g4f Client."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Sequence

from .client import Client
from .rocksoul_db import DBRouter, RocksoulDB
from .rocksoul_execution_store import ExecutionTraceStore
from .rocksoul_policy import ExecutionPolicy, RetryAction, RetryBudget


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    model: str
    messages: Any
    requirements: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    max_attempts: int = 3
    timeout: float = 30.0
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
    """Execute through ranked ROCKSOUL candidates without duplicating g4f providers."""

    def __init__(self, db: RocksoulDB | None = None, client: Client | None = None) -> None:
        self.db = db or RocksoulDB()
        self.router = DBRouter(self.db)
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

    def _call_with_timeout(self, request: ExecutionRequest, provider: str) -> Any:
        if request.timeout <= 0:
            return self._call(request, provider)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rocksoul-exec")
        future = executor.submit(self._call, request, provider)
        try:
            return future.result(timeout=request.timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError(f"provider {provider} timed out after {request.timeout}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _response_valid(response: Any) -> bool:
        if response is None:
            return False
        if isinstance(response, str):
            return bool(response.strip())
        return True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started_total = time.monotonic()
        attempts: list[ExecutionAttempt] = []
        tried: set[str] = set()
        budget = RetryBudget(max_attempts=max(1, request.max_attempts))
        self.trace.record_execution_run(
            request.request_id, request.model, time.time(), None,
            "running", None, 0, None,
        )
        candidates = self.db.route_candidates(
            request.model,
            providers=request.providers or None,
            capabilities=request.requirements or None,
        )
        if not candidates:
            self.trace.record_execution_run(
                request.request_id, request.model, time.time(), time.time(),
                "exhausted", None, 0, "no_candidate",
            )
            return ExecutionResult(
                request.request_id, False, request.model, None,
                attempts=(), outcome="exhausted",
                error_class="no_candidate", error="No eligible provider candidates",
            )

        index = 0
        while index < len(candidates) and len(attempts) < budget.max_attempts:
            candidate = candidates[index]
            index += 1
            if candidate.provider in tried:
                continue
            if not budget.allows(len(attempts), time.monotonic() - started_total, 0):
                break
            tried.add(candidate.provider)
            started = time.time()
            monotonic_started = time.monotonic()
            try:
                response = self._call_with_timeout(request, candidate.provider)
                finished = time.time()
                latency_ms = (time.monotonic() - monotonic_started) * 1000.0
                valid = self._response_valid(response)
                if not valid:
                    raise ValueError("empty or invalid provider response")
                attempt = ExecutionAttempt(
                    len(attempts) + 1, candidate.provider, request.model, started, finished,
                    latency_ms, "success", response_valid=True,
                )
                attempts.append(attempt)
                self.trace.record_execution_attempt(
                    request.request_id, attempt.attempt_no, candidate.provider, request.model,
                    started, finished, latency_ms, "success", None, None, True,
                )
                self.trace.record_execution_evidence(candidate.provider, request.model, True, latency_ms)
                self.trace.record_execution_run(
                    request.request_id, request.model, started_total, time.time(),
                    "success", candidate.provider, len(attempts), None,
                )
                return ExecutionResult(
                    request.request_id, True, request.model, candidate.provider,
                    response=response, attempts=tuple(attempts), outcome="success",
                )
            except Exception as exc:
                finished = time.time()
                latency_ms = (time.monotonic() - monotonic_started) * 1000.0
                decision = ExecutionPolicy.decide(exc)
                error_class = decision.error_class.value
                attempt = ExecutionAttempt(
                    len(attempts) + 1, candidate.provider, request.model, started, finished,
                    latency_ms, "failed", error_class, str(exc), False,
                )
                attempts.append(attempt)
                self.trace.record_execution_attempt(
                    request.request_id, attempt.attempt_no, candidate.provider, request.model,
                    started, finished, latency_ms, "failed", error_class, str(exc), False,
                )
                self.trace.record_execution_evidence(
                    candidate.provider, request.model, False, latency_ms,
                    error_class=error_class, error=str(exc),
                )
                if decision.action is RetryAction.TERMINAL:
                    self.trace.record_execution_run(
                        request.request_id, request.model, started_total, time.time(),
                        "failed", candidate.provider, len(attempts), error_class,
                    )
                    return ExecutionResult(
                        request.request_id, False, request.model, candidate.provider,
                        attempts=tuple(attempts), outcome="failed",
                        error_class=error_class, error=str(exc),
                    )
                if decision.action is RetryAction.RECOMPUTE_CANDIDATES:
                    candidates = self.db.route_candidates(
                        request.model,
                        providers=request.providers or None,
                        capabilities=request.requirements or None,
                    )
                    index = 0
        last = attempts[-1] if attempts else None
        self.trace.record_execution_run(
            request.request_id, request.model, started_total, time.time(),
            "exhausted", last.provider if last else None, len(attempts),
            last.error_class if last else None,
        )
        return ExecutionResult(
            request.request_id, False, request.model,
            last.provider if last else None,
            attempts=tuple(attempts), outcome="exhausted",
            error_class=last.error_class if last else "exhausted",
            error=last.error if last else "No provider succeeded",
        )

    def route_explain(self, model: str, requirements: Sequence[str] = ()) -> list[dict[str, Any]]:
        candidates = self.db.route_candidates(model, capabilities=requirements)
        return [
            {
                "provider": candidate.provider,
                "score": candidate.score,
                "model_verified": candidate.model_verified,
                "health_score": candidate.health_score,
                "avg_latency_ms": candidate.avg_latency_ms,
            }
            for candidate in candidates
        ]

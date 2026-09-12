from __future__ import annotations

"""Live provider probing for ROCKSOUL.

Live probes are always explicit. They execute real g4f provider requests,
validate the normalized result, and persist evidence into the SQLite store.
"""

import concurrent.futures
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .rocksoul_db import RocksoulDB


@dataclass(frozen=True, slots=True)
class ProbeResult:
    provider: str
    model: str
    probe_type: str
    ok: bool
    latency_ms: float | None
    response_valid: bool | None
    error_class: str | None = None
    error: str | None = None
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "probe_type": self.probe_type,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "response_valid": self.response_valid,
            "error_class": self.error_class,
            "error": self.error,
            "status_code": self.status_code,
        }


class ResponseValidator:
    @staticmethod
    def chat(value: Any, stream: bool = False) -> bool:
        if value is None:
            return False
        if stream:
            return isinstance(value, Sequence) and len(value) > 0
        content = getattr(value, "content", None)
        if content is not None and str(content).strip():
            return True
        tool_calls = getattr(value, "tool_calls", None)
        return bool(tool_calls)


class LiveProbe:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB()

    @staticmethod
    def _provider(name: str) -> Any:
        from .client.service import convert_to_provider

        return convert_to_provider(name)

    @staticmethod
    def _error_details(exc: BaseException) -> tuple[str, int | None]:
        from .rocksoul_platform import classify_error

        return classify_error(exc), getattr(exc, "status_code", None)

    def probe(
        self,
        provider: str,
        model: str,
        probe_type: str = "smoke",
        timeout: float = 30.0,
        client_factory: Callable[[Any], Any] | None = None,
    ) -> ProbeResult:
        if probe_type not in {"smoke", "stream"}:
            raise ValueError(f"Unsupported probe type: {probe_type}")
        started = time.perf_counter()
        stream = probe_type == "stream"
        ok = False
        valid = False
        error_class: str | None = None
        error: str | None = None
        status_code: int | None = None
        try:
            if client_factory is not None:
                provider_handler = provider
                client = client_factory(provider_handler)
            else:
                provider_handler = self._provider(provider)
                client = self._default_client(provider_handler)
            request_timeout = max(1.0, float(timeout))
            result = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly: ROCKSOUL_PROBE_OK"}],
                provider=provider_handler,
                stream=stream,
                timeout=request_timeout,
            )
            if stream:
                chunks = list(result)
                valid = ResponseValidator.chat(chunks, stream=True)
                ok = valid
            else:
                valid = ResponseValidator.chat(result)
                ok = valid
        except Exception as exc:
            error_class, status_code = self._error_details(exc)
            error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000.0
        probe = ProbeResult(provider, model, probe_type, ok, latency_ms, valid, error_class, error, status_code)
        self.db.record_probe(
            provider=provider,
            probe_type=probe_type,
            ok=ok,
            latency_ms=latency_ms,
            model=model,
            status_code=status_code,
            error_class=error_class,
            error=error,
            response_valid=valid,
        )
        self.db.bind_model(provider, model, verified=ok)
        if ok:
            self.db.set_capability(provider, "streaming" if stream else "text", True, True, True, model=model)
        return probe

    @staticmethod
    def _default_client(provider: Any) -> Any:
        from .client import Client

        return Client(provider=provider)

    def probe_many(
        self,
        providers: Sequence[str],
        model: str,
        concurrency: int = 4,
        probe_type: str = "smoke",
        timeout: float = 30.0,
    ) -> list[ProbeResult]:
        workers = max(1, min(int(concurrency), len(providers) or 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.probe, name, model, probe_type, timeout)
                for name in providers
            ]
            results: list[ProbeResult] = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(
                        ProbeResult(
                            provider="<worker>",
                            model=model,
                            probe_type=probe_type,
                            ok=False,
                            latency_ms=None,
                            response_valid=False,
                            error_class=type(exc).__name__,
                            error=str(exc),
                        )
                    )
        return sorted(results, key=lambda item: item.provider.lower())


def default_probe_model() -> str:
    return "gpt-4o-mini"


def result_summary(results: Iterable[ProbeResult]) -> dict[str, Any]:
    items = list(results)
    return {
        "tests": len(items),
        "passed": sum(item.ok for item in items),
        "failed": sum(not item.ok for item in items),
        "success_rate": (sum(item.ok for item in items) / len(items)) if items else 0.0,
        "results": [item.to_dict() for item in items],
    }

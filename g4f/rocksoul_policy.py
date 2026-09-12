from __future__ import annotations

"""Deterministic policy for ROCKSOUL execution retry/fallback decisions."""

import random
from dataclasses import dataclass
from enum import Enum

class ErrorClass(str, Enum):
    TIMEOUT = "timeout"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    MODEL_NOT_FOUND = "model_not_found"
    UNSUPPORTED = "unsupported"
    CONTENT_BLOCKED = "content_blocked"
    UNKNOWN = "unknown"

class RetryAction(str, Enum):
    NEXT_PROVIDER = "next_provider"
    COOLDOWN_NEXT_PROVIDER = "cooldown_next_provider"
    RECOMPUTE_CANDIDATES = "recompute_candidates"
    TERMINAL = "terminal"
    BOUNDED_RETRY = "bounded_retry"

@dataclass(frozen=True, slots=True)
class PolicyDecision:
    error_class: ErrorClass
    action: RetryAction
    retryable: bool
    cooldown_seconds: float = 0.0

class ExecutionPolicy:
    """Classify provider failures and calculate bounded retry delays."""
    @staticmethod
    def classify(error: BaseException) -> ErrorClass:
        name = type(error).__name__.lower(); message = str(error).lower(); text = f"{name} {message}"
        if "timeout" in text or "timed out" in text: return ErrorClass.TIMEOUT
        if any(token in text for token in ("rate limit", "ratelimit", "too many requests", "429")): return ErrorClass.RATE_LIMIT
        if any(token in text for token in ("authentication", "unauthorized", "forbidden", "invalid api key", "401", "403")): return ErrorClass.AUTH
        if any(token in text for token in ("model not found", "unknown model", "no such model")): return ErrorClass.MODEL_NOT_FOUND
        if any(token in text for token in ("unsupported", "not supported", "streamnotsupported")): return ErrorClass.UNSUPPORTED
        if any(token in text for token in ("content blocked", "content policy", "safety filter", "moderation")): return ErrorClass.CONTENT_BLOCKED
        if any(token in text for token in ("connection", "connect", "network", "dns", "socket", "httpx", "aiohttp")): return ErrorClass.NETWORK
        return ErrorClass.UNKNOWN

    @classmethod
    def decide(cls, error: BaseException) -> PolicyDecision:
        error_class = cls.classify(error)
        if error_class is ErrorClass.TIMEOUT: return PolicyDecision(error_class, RetryAction.NEXT_PROVIDER, True)
        if error_class is ErrorClass.NETWORK: return PolicyDecision(error_class, RetryAction.NEXT_PROVIDER, True)
        if error_class is ErrorClass.RATE_LIMIT: return PolicyDecision(error_class, RetryAction.COOLDOWN_NEXT_PROVIDER, True, 30.0)
        if error_class is ErrorClass.AUTH: return PolicyDecision(error_class, RetryAction.NEXT_PROVIDER, True)
        if error_class is ErrorClass.MODEL_NOT_FOUND: return PolicyDecision(error_class, RetryAction.RECOMPUTE_CANDIDATES, True)
        if error_class is ErrorClass.UNSUPPORTED: return PolicyDecision(error_class, RetryAction.RECOMPUTE_CANDIDATES, True)
        if error_class is ErrorClass.CONTENT_BLOCKED: return PolicyDecision(error_class, RetryAction.TERMINAL, False)
        return PolicyDecision(error_class, RetryAction.BOUNDED_RETRY, True)

    @staticmethod
    def backoff_seconds(decision: PolicyDecision, retry_index: int, *, base: float = 0.25, maximum: float = 8.0, jitter: float = 0.0, rng: random.Random | None = None) -> float:
        """Return only the delay required before another attempt.

        A rate-limit cooldown is a provider state transition, not a reason to
        block execution when the policy already selected the next provider.
        """
        if not decision.retryable or decision.action in (RetryAction.TERMINAL, RetryAction.RECOMPUTE_CANDIDATES, RetryAction.COOLDOWN_NEXT_PROVIDER): return 0.0
        index = max(0, retry_index)
        delay = 0.0 if decision.error_class is ErrorClass.TIMEOUT else max(0.0, base) * (2 ** min(index, 5))
        delay = min(maximum, delay) if maximum >= 0 else delay
        if jitter > 0 and delay > 0:
            source = rng or random; delay = min(maximum, delay + source.uniform(0.0, jitter))
        return max(0.0, delay)

@dataclass(frozen=True, slots=True)
class RetryBudget:
    max_attempts: int = 3
    max_total_time: float = 90.0
    max_same_provider_attempts: int = 1
    def allows(self, attempts: int, elapsed: float, provider_attempts: int) -> bool:
        return attempts < max(1, self.max_attempts) and elapsed < max(0.0, self.max_total_time) and provider_attempts < max(1, self.max_same_provider_attempts)

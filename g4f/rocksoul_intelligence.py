from __future__ import annotations

"""ROCKSOUL capability verification, explainable routing and recovery controls."""

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .rocksoul_control import ProviderControlStore
from .rocksoul_db import RocksoulDB, RouteCandidate
from .rocksoul_probe import LiveProbe

CAPABILITIES = ("streaming", "tools", "structured_output", "vision", "image")

@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    name: str
    required: bool = True

@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    provider: str
    model: str
    capability: str
    ok: bool
    detail: str
    latency_ms: float | None
    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "capability": self.capability, "ok": self.ok, "detail": self.detail, "latency_ms": self.latency_ms}

class CapabilityVerifier:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB(); self.live = LiveProbe(self.db)
    @staticmethod
    def _provider(name: str) -> Any:
        from .client.service import convert_to_provider
        return convert_to_provider(name)
    @staticmethod
    def _client(provider: Any) -> Any:
        from .client import Client
        return Client(provider=provider)
    @staticmethod
    def _tool() -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": "rocksoul_probe", "description": "Return the requested probe token.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}}]
    def _declared(self, provider: Any, capability: str) -> bool | None:
        mapping = {"streaming": "supports_stream", "vision": "supports_vision", "tools": "supports_native_tools", "structured_output": "supports_structured_output", "image": "supports_image_generation"}
        value = getattr(provider, mapping[capability], None)
        return None if value is None else bool(value)
    def verify(self, provider: str, model: str, capability: str, timeout: float = 30.0) -> CapabilityEvidence:
        if capability not in CAPABILITIES: raise ValueError(f"Unsupported capability: {capability}")
        started = time.perf_counter(); ok = False; detail = ""; declared: bool | None = None; handler: Any | None = None
        try:
            handler = self._provider(provider); declared = self._declared(handler, capability)
            if capability == "streaming":
                result = self.live.probe(provider, model, "stream", timeout); ok, detail = result.ok, "stream produced at least one chunk" if result.ok else (result.error or "stream validation failed")
            else:
                client = self._client(handler); kwargs: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly: ROCKSOUL_CAPABILITY_OK"}], "provider": handler, "stream": False, "timeout": max(1.0, float(timeout))}
                if capability == "tools": kwargs["tools"] = self._tool()
                elif capability == "structured_output": kwargs["response_format"] = {"type": "json_object"}; kwargs["messages"] = [{"role": "user", "content": '{"probe":"ROCKSOUL_CAPABILITY_OK"}'}]
                elif capability == "vision": kwargs["messages"] = [{"role": "user", "content": [{"type": "text", "text": "Describe this image in one word."}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="}}]}]
                elif capability == "image": image = client.images.generate(model=model, prompt="A tiny abstract ROCKSOUL capability probe image", provider=handler); ok, detail = bool(image), "image generation returned a response" if image else "empty image response"
                if capability != "image":
                    result = client.chat.completions.create(**kwargs)
                    if capability == "tools": ok = bool(getattr(result, "tool_calls", None)); detail = "tool call returned" if ok else "no tool call returned"
                    elif capability == "structured_output":
                        try:
                            parsed = json.loads(str(getattr(result, "content", ""))); ok = isinstance(parsed, dict) and parsed.get("probe") == "ROCKSOUL_CAPABILITY_OK"; detail = "valid JSON object returned" if ok else "JSON object did not match probe"
                        except (TypeError, ValueError): detail = "response was not valid JSON"
                    else:
                        content = getattr(result, "content", None); ok = bool(content and str(content).strip()); detail = "non-empty response returned" if ok else "empty response"
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"; declared = self._declared(handler, capability) if handler is not None else None
        latency = (time.perf_counter() - started) * 1000.0; self.db.set_capability(provider, capability, declared, ok, ok, model=model)
        return CapabilityEvidence(provider, model, capability, ok, detail, latency)
    def verify_many(self, provider: str, model: str, capabilities: Iterable[str], timeout: float = 30.0) -> list[CapabilityEvidence]:
        return [self.verify(provider, model, capability, timeout) for capability in capabilities]

class ExplainableRouter:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB(); self.control = ProviderControlStore(self.db)
    def _capability_state(self, provider: str, model: str, name: str) -> tuple[bool, str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT c.declared,c.detected,c.verified FROM capabilities c JOIN providers p ON p.id=c.provider_id LEFT JOIN models m ON m.id=c.model_id WHERE p.name=? AND c.name=? AND (m.name=? OR c.model_id IS NULL) ORDER BY c.verified DESC,c.detected DESC,c.declared DESC LIMIT 1", (provider, name, model)).fetchone()
        if row is None: return False, "UNKNOWN"
        if int(row["verified"] or 0): return True, "VERIFIED"
        if int(row["detected"] or 0): return False, "DETECTED"
        if int(row["declared"] or 0): return False, "DECLARED"
        return False, "UNKNOWN"
    def explain(self, model: str, requirements: Sequence[CapabilityRequirement] = (), providers: Sequence[str] | None = None, verified_only: bool = False) -> list[dict[str, Any]]:
        output=[]
        for candidate in self.db.route_candidates(model, providers, verified_only, capabilities=None):
            control = self.control.get(candidate.provider); states={}; reasons=[]; accepted=not control.blocked
            if control.blocked: reasons.append(f"provider state {control.state.lower()}")
            for req in requirements:
                good,state=self._capability_state(candidate.provider,model,req.name); states[req.name]=state
                if req.required and not good: accepted=False; reasons.append(f"missing verified capability: {req.name} ({state.lower()})")
            reasons.append("model verified" if candidate.model_verified else "model not yet verified"); reasons.append(f"health score {candidate.health_score:.2f}")
            if candidate.avg_latency_ms is not None: reasons.append(f"average latency {candidate.avg_latency_ms:.1f}ms")
            output.append({"provider":candidate.provider,"accepted":accepted,"score":round(candidate.score,2),"model_verified":candidate.model_verified,"health_score":round(candidate.health_score,2),"avg_latency_ms":candidate.avg_latency_ms,"capabilities":states,"control_state":control.state,"control_reason":control.reason,"reasons":reasons})
        return output
    def select(self, model: str, requirements: Sequence[CapabilityRequirement] = (), providers: Sequence[str] | None = None, verified_only: bool = False) -> dict[str, Any] | None:
        explained=self.explain(model,requirements,providers,verified_only); accepted=[x for x in explained if x["accepted"]]; selected=max(accepted,key=lambda x:x["score"]) if accepted else None
        self.db.record_route(model,[RouteCandidate(x["provider"],x["score"],x["model_verified"],x["health_score"],x["avg_latency_ms"]) for x in explained],selected["provider"] if selected else None,selected["reasons"] if selected else ["no candidate satisfied requirements"])
        return selected

class RecoveryManager:
    def __init__(self, db: RocksoulDB | None = None) -> None:
        self.db = db or RocksoulDB(); self.control = ProviderControlStore(self.db)
    def quarantined(self) -> list[str]: return [item.provider for item in self.control.list() if item.state == "QUARANTINED"]
    def recover(self, providers: Sequence[str] | None = None, model: str = "gpt-4o-mini", timeout: float = 30.0) -> list[dict[str, Any]]:
        targets=list(providers) if providers else self.quarantined(); probe=LiveProbe(self.db); results=[]
        for provider in targets:
            current=self.control.get(provider)
            if current.state not in ("QUARANTINED", "DEGRADED", "PROBING"):
                results.append({"provider":provider,"probe_ok":False,"latency_ms":None,"health_score":round(self.db.health(provider).score,2),"re_admitted":False,"status":current.state,"reason":"provider is not recoverable in current state"}); continue
            self.control.begin_recovery(provider); result=probe.probe(provider,model,"smoke",timeout); health=self.db.health(provider)
            if result.ok: self.control.re_admit(provider)
            else: self.control.quarantine(provider, result.error or "recovery_probe_failed")
            state=self.control.get(provider); results.append({"provider":provider,"probe_ok":result.ok,"latency_ms":result.latency_ms,"health_score":round(health.score,2),"re_admitted":result.ok,"status":state.state})
        return results

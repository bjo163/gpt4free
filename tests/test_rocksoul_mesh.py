from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from g4f.rocksoul_db import RocksoulDB
from g4f.rocksoul_mesh import MeshAuthContext, MeshAuthError, MeshPolicy, MeshSecurityError, MeshStore, make_mesh_auth


class RocksoulMeshTests(unittest.TestCase):
    def make_store(self, *, threshold: int = 3, max_inflight: int = 1) -> tuple[MeshStore, str]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        secret = "node-secret"
        return MeshStore(
            RocksoulDB(Path(temp.name) / "rocksoul.db"),
            secret=secret,
            policy=MeshPolicy(
                heartbeat_ttl=60.0,
                lease_ttl=30.0,
                auth_clock_skew=60.0,
                nonce_ttl=600.0,
                failure_threshold=threshold,
                max_inflight_per_node=max_inflight,
                allow_insecure_local=True,
            ),
        ), secret

    def activate(self, store: MeshStore, secret: str, node_id: str, *, now: float, endpoint: str,
                 capabilities: tuple[str, ...], latency_ms: float = 20.0, weight: float = 1.0):
        register_payload = {"endpoint": endpoint, "capabilities": tuple(sorted(capabilities)), "weight": weight}
        store.register_node(
            node_id,
            endpoint,
            capabilities,
            weight=weight,
            auth=make_mesh_auth(secret, "register", node_id, register_payload, timestamp=now, nonce=f"{node_id}-reg"),
            now=now,
        )
        heartbeat_payload = {"health": 100.0, "latency_ms": latency_ms}
        return store.heartbeat(
            node_id,
            health=100.0,
            latency_ms=latency_ms,
            auth=make_mesh_auth(secret, "heartbeat", node_id, heartbeat_payload,
                                timestamp=now + 1, nonce=f"{node_id}-hb"),
            now=now + 1,
        )

    def test_authenticated_registration_rejects_invalid_signature_and_replay(self):
        store, secret = self.make_store()
        payload = {"endpoint": "http://127.0.0.1:9000", "capabilities": ("streaming",), "weight": 1.0}
        auth = make_mesh_auth(secret, "register", "node-a", payload, timestamp=1000.0, nonce="n1")
        with self.assertRaises(MeshAuthError):
            store.register_node("node-a", payload["endpoint"], payload["capabilities"], weight=1.0,
                                auth=MeshAuthContext(auth.timestamp, auth.nonce, "0" * 64), now=1000.0)
        self.assertEqual(
            store.register_node("node-a", payload["endpoint"], payload["capabilities"], weight=1.0,
                                auth=auth, now=1000.0).state,
            "REGISTERED",
        )
        with self.assertRaises(MeshAuthError):
            store.register_node("node-a", payload["endpoint"], payload["capabilities"], weight=1.0,
                                auth=auth, now=1000.0)

    def test_per_node_keys_isolate_node_identity(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = MeshStore(
            RocksoulDB(Path(temp.name) / "rocksoul.db"),
            secret={"node-a": "secret-a", "node-b": "secret-b"},
            policy=MeshPolicy(allow_insecure_local=True),
        )
        payload = {"endpoint": "http://127.0.0.1:9002", "capabilities": ("streaming",), "weight": 1.0}
        forged = make_mesh_auth("secret-a", "register", "node-b", payload, timestamp=1000.0, nonce="forged")
        with self.assertRaises(MeshAuthError):
            store.register_node("node-b", payload["endpoint"], payload["capabilities"], weight=1.0,
                                auth=forged, now=1000.0)

    def test_endpoint_security_requires_https_unless_local_policy_is_explicit(self):
        store, _ = self.make_store()
        strict = MeshStore(store.db, policy=MeshPolicy(allow_insecure_local=False))
        with self.assertRaises(MeshSecurityError):
            strict.register_operator_node("node-a", "http://127.0.0.1:9000", now=1000.0)

    def test_heartbeat_activates_and_stale_node_becomes_offline(self):
        store, secret = self.make_store()
        node = self.activate(store, secret, "node-a", now=1000.0, endpoint="http://127.0.0.1:9000",
                             capabilities=("streaming",))
        self.assertEqual(node.state, "ACTIVE")
        self.assertEqual(store.refresh_stale(now=1062.0), ["node-a"])
        self.assertEqual(store.get("node-a").state, "OFFLINE")

    def test_selection_respects_capabilities_score_capacity_and_idempotency(self):
        store, secret = self.make_store(max_inflight=1)
        self.activate(store, secret, "node-fast", now=1000.0, endpoint="http://127.0.0.1:9001",
                      capabilities=("streaming", "vision"), latency_ms=10.0)
        self.activate(store, secret, "node-slow", now=1000.0, endpoint="http://127.0.0.1:9002",
                      capabilities=("streaming",), latency_ms=200.0)
        first = store.acquire_lease("req-1", ("streaming",), now=1002.0)
        second = store.acquire_lease("req-2", ("streaming",), now=1002.0)
        self.assertEqual(first.node_id, "node-fast")
        self.assertEqual(second.node_id, "node-slow")
        self.assertIsNone(store.acquire_lease("req-3", ("streaming",), now=1002.0))
        self.assertEqual(store.acquire_lease("req-1", ("streaming",), now=1002.0).lease_id, first.lease_id)
        self.assertIsNone(store.select(("vision",), now=1002.0))

    def test_failure_isolation_quarantines_only_failing_node(self):
        store, secret = self.make_store(threshold=2, max_inflight=1)
        self.activate(store, secret, "node-a", now=1000.0, endpoint="http://127.0.0.1:9001",
                      capabilities=("streaming",), latency_ms=10.0, weight=2.0)
        self.activate(store, secret, "node-b", now=1000.0, endpoint="http://127.0.0.1:9002",
                      capabilities=("streaming",), latency_ms=20.0)
        first = store.acquire_lease("req-a1", ("streaming",), now=1002.0)
        store.release_lease(first.lease_id, success=False, error="boom-1", now=1003.0)
        store.set_state("node-a", "ACTIVE", "operator_retry", now=1004.0)
        second = store.acquire_lease("req-a2", ("streaming",), now=1005.0)
        self.assertEqual(second.node_id, "node-a")
        store.release_lease(second.lease_id, success=False, error="boom-2", now=1006.0)
        self.assertEqual(store.get("node-a").state, "QUARANTINED")
        self.assertEqual(store.get("node-b").state, "ACTIVE")
        self.assertEqual(store.select(("streaming",), now=1007.0).node_id, "node-b")

    def test_draining_and_expired_leases_are_isolated_and_auditable(self):
        store, secret = self.make_store(max_inflight=1)
        self.activate(store, secret, "node-a", now=1000.0, endpoint="http://127.0.0.1:9001",
                      capabilities=("streaming",))
        lease = store.acquire_lease("req-1", ("streaming",), ttl=5.0, now=1002.0)
        self.assertEqual(store.get("node-a").inflight, 1)
        self.assertEqual(store.expire_leases(now=1008.0), [lease.lease_id])
        self.assertEqual(store.get("node-a").inflight, 0)
        store.set_state("node-a", "DRAINING", "maintenance", now=1009.0)
        self.assertIsNone(store.select(("streaming",), now=1010.0))
        names = {event["event"] for event in store.events("node-a")}
        self.assertTrue({"node_registered", "heartbeat", "lease_acquired", "lease_expired", "state_changed"}.issubset(names))

    def test_status_exposes_lifecycle_and_auth_contract(self):
        store, secret = self.make_store()
        self.activate(store, secret, "node-a", now=1000.0, endpoint="http://127.0.0.1:9001",
                      capabilities=("streaming",))
        status = store.status(now=1002.0)
        self.assertEqual(status["nodes"], 1)
        self.assertEqual(status["states"]["ACTIVE"], 1)
        self.assertEqual(status["authentication"], "hmac-sha256+node-key+timestamp+nonce")


if __name__ == "__main__":
    unittest.main()

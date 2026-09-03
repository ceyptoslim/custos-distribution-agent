"""Hash-chained audit log — tamper-evident, mirroring CUSTOS-CORE's design."""
import hashlib
import json
import os

GENESIS = "0" * 64


class AuditChain:
    def __init__(self, path="audit_log.jsonl"):
        self.path = path
        self._prev = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if not os.path.exists(self.path):
            return GENESIS
        last = GENESIS
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["digest"]
        return last

    def record(self, event: dict) -> str:
        digest = hashlib.sha256(
            (self._prev + json.dumps(event, sort_keys=True, separators=(",", ":"))).encode()
        ).hexdigest()
        entry = dict(event, prev=self._prev, digest=digest)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        self._prev = digest
        return digest

    def verify(self) -> bool:
        """Recompute the whole chain; False if any entry was altered or removed."""
        prev = GENESIS
        if not os.path.exists(self.path):
            return True
        with open(self.path) as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                expected = hashlib.sha256(
                    (prev + json.dumps({k: v for k, v in entry.items() if k not in ("prev", "digest")}, sort_keys=True, separators=(",", ":"))).encode()
                ).hexdigest()
                if entry["prev"] != prev or entry["digest"] != expected:
                    return False
                prev = entry["digest"]
        return True

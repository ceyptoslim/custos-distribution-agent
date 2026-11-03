"""Governance invariants: fail-closed gate, tamper-evident audit, blocked executor."""
import json

from custos_distribution_agent.audit import AuditChain
from custos_distribution_agent.executor import YouTubeExecutor
from custos_distribution_agent.gate import CUSTOSGate
from custos_distribution_agent.models import ActionKind, YouTubeAction
from custos_distribution_agent.pipeline import run_action


class DeadGate(CUSTOSGate):
    """Simulates CUSTOS being unreachable — must fail closed."""

    def evaluate(self, action):
        return False


class AllowGate(CUSTOSGate):
    def evaluate(self, action):
        return True


def test_gate_fails_closed_when_custos_unreachable():
    gate = CUSTOSGate(base_url="http://localhost:1", timeout=0.1)
    assert gate.evaluate(YouTubeAction(ActionKind.UPLOAD, video_id="abc")) is False


def test_executor_blocks_without_credentials():
    result = YouTubeExecutor().execute(YouTubeAction(ActionKind.REPLY_COMMENT))
    assert result["status"] == "blocked"


def test_pipeline_denies_and_audits_when_gate_closed(tmp_path):
    chain = AuditChain(tmp_path / "a.jsonl")
    outcome = run_action(
        YouTubeAction(ActionKind.UPLOAD, video_id="abc"),
        gate=DeadGate(), chain=chain, approve=lambda a: True,
    )
    assert outcome["status"] == "denied"
    assert chain.verify() is True


def test_pipeline_blocked_at_executor_records_full_trail(tmp_path):
    chain = AuditChain(tmp_path / "a.jsonl")
    outcome = run_action(
        YouTubeAction(ActionKind.ADD_TO_PLAYLIST, video_id="abc", payload={"playlist": "trending"}),
        gate=AllowGate(), chain=chain, approve=lambda a: True,
    )
    assert outcome["status"] == "blocked"  # ALLOW + approved, but executor refuses without creds
    events = [json.loads(line)["event"] for line in open(tmp_path / "a.jsonl")]
    assert events == ["drafted", "allowed", "approved", "blocked"]
    assert chain.verify() is True


def test_audit_chain_detects_tampering(tmp_path):
    path = tmp_path / "a.jsonl"
    chain = AuditChain(path)
    chain.record({"event": "drafted"})
    chain.record({"event": "allowed"})
    assert chain.verify() is True
    lines = open(path).read().splitlines()
    entry = json.loads(lines[0])
    entry["event"] = "executed"  # tamper
    lines[0] = json.dumps(entry, sort_keys=True)
    open(path, "w").write("\n".join(lines) + "\n")
    assert AuditChain(path).verify() is False


def test_pipeline_never_executes_when_human_rejects(tmp_path):
    chain = AuditChain(tmp_path / "a.jsonl")
    outcome = run_action(
        YouTubeAction(ActionKind.UPLOAD),
        gate=AllowGate(), chain=chain, approve=lambda a: False,
    )
    assert outcome["status"] == "rejected"
    events = [json.loads(line)["event"] for line in open(tmp_path / "a.jsonl")]
    assert "blocked" not in events and "approved" not in events

"""The gate keeps the decision: trace join, version header, fail-closed paths."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from custos_distribution_agent.audit import AuditChain
from custos_distribution_agent.gate import CUSTOSGate
from custos_distribution_agent.models import ActionKind, YouTubeAction
from custos_distribution_agent.pipeline import run_action

ALLOW_BODY = {
    "allowed": True,
    "action": "upload",
    "triggered_rule": None,
    "reason": "No policy violations detected",
    "client_id": "distribution-agent",
    "tenant_id": "probe_tenant",
    "audit_record_hash": "a" * 64,
    "trace_id": "trace-42",
}


@pytest.fixture
def stub():
    """A local stand-in for /v1/evaluate that records what it received."""
    state = {"body": ALLOW_BODY, "status": 200, "seen": {}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib naming
            length = int(self.headers.get("Content-Length", 0))
            state["seen"] = {
                "path": self.path,
                "version": self.headers.get("X-CUSTOS-Version"),
                "auth": self.headers.get("Authorization"),
                "payload": json.loads(self.rfile.read(length) or b"{}"),
            }
            raw = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()


def test_decide_carries_trace_and_record_hash(stub):
    url, _ = stub
    decision = CUSTOSGate(base_url=url, token="t").decide(
        YouTubeAction(ActionKind.UPLOAD, video_id="abc")
    )
    assert decision.allowed is True
    assert decision.trace_id == "trace-42"
    assert decision.audit_record_hash == "a" * 64


def test_version_header_is_configurable_not_hardcoded(stub, monkeypatch):
    url, state = stub
    CUSTOSGate(base_url=url, api_version="9.9.9").decide(YouTubeAction(ActionKind.UPLOAD))
    assert state["seen"]["version"] == "9.9.9"

    monkeypatch.setenv("CUSTOS_API_VERSION", "2.0.0")
    CUSTOSGate(base_url=url).decide(YouTubeAction(ActionKind.UPLOAD))
    assert state["seen"]["version"] == "2.0.0"


def test_denied_response_is_not_treated_as_outage(stub):
    url, state = stub
    state["body"] = {"allowed": False, "reason": "tool not allowlisted",
                     "triggered_rule": "action_gate_tool_not_allowlisted"}
    decision = CUSTOSGate(base_url=url).decide(YouTubeAction(ActionKind.UPLOAD))
    assert decision.allowed is False
    assert decision.triggered_rule == "action_gate_tool_not_allowlisted"


def test_http_error_fails_closed_with_reason(stub):
    url, state = stub
    state["status"] = 500
    decision = CUSTOSGate(base_url=url).decide(YouTubeAction(ActionKind.UPLOAD))
    assert decision.allowed is False
    assert decision.reason == "custos_http_error"


def test_allow_response_missing_allowed_key_fails_closed(stub):
    url, state = stub
    state["body"] = {"trace_id": "trace-1"}
    assert CUSTOSGate(base_url=url).decide(YouTubeAction(ActionKind.UPLOAD)).allowed is False


def test_pipeline_logs_the_gate_trace_for_allowed_and_denied(tmp_path, stub):
    url, state = stub
    chain = AuditChain(tmp_path / "a.jsonl")
    gate = CUSTOSGate(base_url=url)

    ok = run_action(YouTubeAction(ActionKind.UPLOAD, video_id="abc"), gate=gate,
                    chain=chain, approve=lambda a: True,
                    executor=_StubExec())
    assert ok["trace_id"] == "trace-42"

    state["body"] = {"allowed": False, "reason": "denied_by_policy", "trace_id": "trace-43"}
    denied = run_action(YouTubeAction(ActionKind.UPLOAD), gate=gate,
                        chain=chain, approve=lambda a: True)
    assert denied["status"] == "denied"

    lines = [json.loads(line) for line in open(tmp_path / "a.jsonl")]
    allowed_lines = [line for line in lines if line["event"] == "allowed"]
    denied_lines = [line for line in lines if line["event"] == "denied"]
    assert allowed_lines[0]["trace_id"] == "trace-42"
    assert allowed_lines[0]["audit_record_hash"] == "a" * 64
    assert denied_lines[0]["trace_id"] == "trace-43"
    assert chain.verify() is True


def test_stale_decision_is_not_attributed_to_a_later_call(stub):
    """A gate that answered once must not hand that evidence to the next action."""
    url, state = stub
    gate = CUSTOSGate(base_url=url)
    gate.evaluate(YouTubeAction(ActionKind.UPLOAD))
    assert gate.last_decision is not None

    state["status"] = 500
    gate.evaluate(YouTubeAction(ActionKind.UPLOAD))
    assert gate.last_decision.allowed is False
    assert gate.last_decision.trace_id is None


class _StubExec:
    def execute(self, action):
        return {"status": "executed", "action_id": action.action_id}

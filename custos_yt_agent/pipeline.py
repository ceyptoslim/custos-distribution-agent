"""Governed pipeline: draft -> CUSTOS gate (fail-closed) -> approval -> execute -> audit."""
from .approver import human_approval
from .audit import AuditChain
from .executor import YouTubeExecutor
from .gate import CUSTOSGate


def run_action(action, gate=None, chain=None, executor=None, approve=None) -> dict:
    """Run one action through the full governed pipeline. Returns the outcome."""
    gate = gate or CUSTOSGate()
    chain = chain or AuditChain()
    executor = executor or YouTubeExecutor()
    approve = approve or human_approval

    chain.record({"event": "drafted", "action_id": action.action_id, "kind": action.kind.value})

    if not gate.evaluate(action):
        chain.record({"event": "denied", "action_id": action.action_id, "by": "custos_gate"})
        return {"status": "denied", "action_id": action.action_id}

    chain.record({"event": "allowed", "action_id": action.action_id, "by": "custos_gate"})

    if not approve(action):
        chain.record({"event": "rejected", "action_id": action.action_id, "by": "human"})
        return {"status": "rejected", "action_id": action.action_id}

    chain.record({"event": "approved", "action_id": action.action_id, "by": "human"})
    result = executor.execute(action)
    chain.record({"event": result["status"], "action_id": action.action_id})
    return result

"""Governed pipeline: draft -> CUSTOS gate (fail-closed) -> approval -> execute -> audit.

Two ledgers, one join. CUSTOS holds the decision record; this agent holds its own
local log. The ``trace_id`` returned with the decision is written next to every
local line that follows, so a reader can follow one action from the gate's
tamper-evident store into this agent's history without trusting either one alone.

Scope note, stated where the claim is made: the gate decides, and this process
performs the effect. That is a governed agent, not an enforced one. Enforcement
in the strong sense needs the call itself to be forwarded by the gate (the
``/v1/execute`` assembly), so that no execution path exists which skips it.
"""
from .approver import human_approval
from .audit import AuditChain
from .executor import YouTubeExecutor
from .gate import CUSTOSGate


def _line(event, action, **fields):
    record = {"event": event, "action_id": action.action_id, "kind": action.kind.value}
    record.update({k: v for k, v in fields.items() if v is not None})
    return record


def run_action(action, gate=None, chain=None, executor=None, approve=None) -> dict:
    """Run one action through the full governed pipeline. Returns the outcome."""
    gate = gate or CUSTOSGate()
    chain = chain or AuditChain()
    executor = executor or YouTubeExecutor()
    approve = approve or human_approval

    chain.record(_line("drafted", action))

    allowed = bool(gate.evaluate(action))
    decision = getattr(gate, "last_decision", None)
    trace_id = getattr(decision, "trace_id", None)
    record_hash = getattr(decision, "audit_record_hash", None)

    if not allowed:
        chain.record(
            _line(
                "denied",
                action,
                by="custos_gate",
                trace_id=trace_id,
                audit_record_hash=record_hash,
                reason=getattr(decision, "reason", None),
                triggered_rule=getattr(decision, "triggered_rule", None),
            )
        )
        return {"status": "denied", "action_id": action.action_id, "trace_id": trace_id}

    chain.record(
        _line(
            "allowed",
            action,
            by="custos_gate",
            trace_id=trace_id,
            audit_record_hash=record_hash,
            triggered_rule=getattr(decision, "triggered_rule", None),
        )
    )

    if not approve(action):
        chain.record(_line("rejected", action, by="human", trace_id=trace_id))
        return {"status": "rejected", "action_id": action.action_id, "trace_id": trace_id}

    chain.record(_line("approved", action, by="human", trace_id=trace_id))
    result = executor.execute(action)
    chain.record(_line(result["status"], action, trace_id=trace_id, audit_record_hash=record_hash))
    result.setdefault("trace_id", trace_id)
    return result

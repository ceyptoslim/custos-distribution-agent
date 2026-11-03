"""CUSTOS policy gate — FAIL-CLOSED, and the response is kept.

No CUSTOS decision means no execution. Any transport error, timeout, malformed
response, or explicit DENY evaluates to False. There is no permissive fallback.

The gate returns more than a yes/no: CUSTOS records the decision in its own
hash-chained store and returns the ``trace_id`` and ``audit_record_hash`` of
that record. Both are carried through to this agent's local log so the two
ledgers can be joined afterwards. Without that join, the local log is a claim
about what happened; with it, each line points at a record the operator cannot
rewrite.
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .models import YouTubeAction

#: Version this client speaks. Sent as ``X-CUSTOS-Version`` so a server-side log
#: shows which client contract produced the request. Override with
#: ``CUSTOS_API_VERSION`` when pinning to a specific CUSTOS-CORE release.
DEFAULT_API_VERSION = "1.4.0"


@dataclass(frozen=True)
class GateDecision:
    """One decision, including the evidence pointers CUSTOS returns."""

    allowed: bool
    reason: str = ""
    triggered_rule: Optional[str] = None
    trace_id: Optional[str] = None
    audit_record_hash: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def deny(cls, reason: str, **detail: Any) -> "GateDecision":
        return cls(allowed=False, reason=reason, detail=detail)


class CUSTOSGate:
    def __init__(self, base_url=None, token=None, timeout=5.0, api_version=None):
        self.base_url = (base_url or os.environ.get("CUSTOS_URL", "http://localhost:8000")).rstrip("/")
        self.token = token or os.environ.get("CUSTOS_JWT", "")
        self.timeout = timeout
        self.api_version = (
            api_version or os.environ.get("CUSTOS_API_VERSION") or DEFAULT_API_VERSION
        )

    # -- request building -------------------------------------------------
    def _payload(self, action: YouTubeAction) -> bytes:
        return json.dumps({
            "client_id": os.environ.get("CUSTOS_CLIENT_ID", "youtube-agent"),
            "action": action.kind.value,
            "resource": f"youtube:video:{action.video_id}" if action.video_id else "youtube:channel",
            "metadata": action.payload,
        }).encode()

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-CUSTOS-Version": self.api_version,
        }

    # -- decisions --------------------------------------------------------
    def decide(self, action: YouTubeAction) -> GateDecision:
        """Ask CUSTOS. Returns the full decision, or a fail-closed denial."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/v1/evaluate",
                data=self._payload(action),
                headers=self._headers(),
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as exc:  # 4xx/5xx is a denial, not an outage
            return GateDecision.deny("custos_http_error", status=exc.code)
        except Exception as exc:  # unreachable, timeout, malformed JSON
            return GateDecision.deny("custos_unavailable", error=type(exc).__name__)

        if not isinstance(body, dict):
            return GateDecision.deny("malformed_response")
        if body.get("allowed") is not True:
            # A denial is a decision with evidence, not an absence of one: the
            # gate writes a record for it too, so keep its pointers.
            return GateDecision(
                allowed=False,
                reason=str(body.get("reason") or "denied_by_policy"),
                triggered_rule=body.get("triggered_rule"),
                trace_id=body.get("trace_id"),
                audit_record_hash=body.get("audit_record_hash"),
                detail={"tenant_id": body.get("tenant_id")},
            )
        return GateDecision(
            allowed=True,
            reason=str(body.get("reason", "")),
            triggered_rule=body.get("triggered_rule"),
            trace_id=body.get("trace_id"),
            audit_record_hash=body.get("audit_record_hash"),
            detail={"tenant_id": body.get("tenant_id")},
        )

    def evaluate(self, action: YouTubeAction) -> bool:
        """Yes/no contract, unchanged for subclasses that override it.

        The decision that produced the answer is left on ``last_decision`` so a
        caller can pick up the evidence pointers without re-asking. It is reset
        first, so a stale decision can never be attributed to a later action.
        """
        self.last_decision: Optional[GateDecision] = None
        decision = self.decide(action)
        self.last_decision = decision
        return decision.allowed

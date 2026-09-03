"""CUSTOS policy gate — FAIL-CLOSED.

No CUSTOS decision means no execution. Any transport error, timeout, malformed
response, or explicit DENY evaluates to False. There is no permissive fallback.
"""
import json
import os
import urllib.request

from .models import YouTubeAction


class CUSTOSGate:
    def __init__(self, base_url=None, token=None, timeout=5.0):
        self.base_url = (base_url or os.environ.get("CUSTOS_URL", "http://localhost:8000")).rstrip("/")
        self.token = token or os.environ.get("CUSTOS_JWT", "")
        self.timeout = timeout

    def evaluate(self, action: YouTubeAction) -> bool:
        """Return True only on an explicit ALLOW from CUSTOS. Fail-closed."""
        body = json.dumps({
            "client_id": os.environ.get("CUSTOS_CLIENT_ID", "youtube-agent"),
            "action": action.kind.value,
            "resource": f"youtube:video:{action.video_id}" if action.video_id else "youtube:channel",
            "metadata": action.payload,
        }).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-CUSTOS-Version": "1.3.1",
        }
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/evaluate", data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp).get("allowed") is True
        except Exception:
            return False  # FAIL-CLOSED: unreachable, timeout, 4xx/5xx, malformed — all DENY

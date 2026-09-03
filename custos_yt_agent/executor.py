"""YouTube Data API executor — BLOCKED until owner OAuth credentials exist.

Intentionally refuses to act without credentials. All API calls land here and
nowhere else, so nothing reaches the channel without: CUSTOS ALLOW + human
approval + valid credentials.
"""


class YouTubeExecutor:
    def __init__(self, credentials=None):
        self.credentials = credentials  # google.oauth2 credentials after owner authorization

    @property
    def enabled(self) -> bool:
        return self.credentials is not None

    def execute(self, action) -> dict:
        if not self.enabled:
            return {
                "status": "blocked",
                "reason": "no YouTube OAuth credentials connected — execution refused",
                "action_id": action.action_id,
            }
        raise NotImplementedError(
            f"execution for {action.kind.value} is implemented after OAuth connection"
        )

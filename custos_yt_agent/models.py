"""Action models for the governed YouTube agent."""
from dataclasses import dataclass, field
from enum import Enum
from time import time
from uuid import uuid4


class ActionKind(str, Enum):
    UPDATE_METADATA = "update_metadata"
    REPLY_COMMENT = "reply_comment"
    MODERATE_COMMENT = "moderate_comment"
    ADD_TO_PLAYLIST = "add_to_playlist"
    UPLOAD = "upload"


@dataclass
class YouTubeAction:
    """A single proposed channel action, gated before execution."""

    kind: ActionKind
    video_id: str = ""
    payload: dict = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: float = field(default_factory=time)

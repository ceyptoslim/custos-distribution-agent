"""Platform adapter registry (see registry.py for the contract)."""

from .registry import (  # noqa: F401
    AdapterRegistry,
    ActionSpec,
    DeclarationError,
    EFFECT_CLASSES,
    PlatformDeclaration,
    REVERSIBILITY,
    STATUSES,
)

__all__ = [
    "AdapterRegistry",
    "ActionSpec",
    "DeclarationError",
    "EFFECT_CLASSES",
    "PlatformDeclaration",
    "REVERSIBILITY",
    "STATUSES",
]

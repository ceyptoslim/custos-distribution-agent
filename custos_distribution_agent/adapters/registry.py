"""Platform adapter registry — the contract, as data instead of prose.

``ADAPTERS.md`` described a governed flow in sentences. A sentence cannot be
tested, cannot be diffed by a reviewer, and cannot stop a fifth platform agent
from growing its own policy. This module turns the same contract into a
declaration file that is validated on load and used to generate the gate's
allowlist.

Four rules give the registry its direction of authority:

1. **The registry can deny; it can never allow.** ``check_declared`` answers
   "is this action declared for this platform?" and refuses when it is not. A
   pass from it means nothing was refused locally, not that the action is
   permitted. Permission still requires a CUSTOS decision.
2. **Declaring is not permitting.** A platform may be listed with status
   ``declared`` while its executor does not exist. Declared platforms are
   documented and ordered, and deliberately excluded from the generated
   allowlist, so writing a platform down cannot authorize it.
3. **Effect class belongs to the action, not the platform.** An unlisted upload
   and a public reply leave the same adapter and are not the same kind of act.
   Flattening them to one class per platform is how a "governed" adapter ends up
   treating an irreversible reply as if it were a reversible metadata edit.
4. **Order is activation order, cheapest-to-undo first.** The registry refuses a
   file whose order contradicts the risk ranking it computes itself, so the
   sequence cannot drift quietly to whichever platform is most interesting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DECLARATIONS_PATH = Path(__file__).with_name("declarations.json")

STATUSES = ("stub", "active", "declared")

# What the action does to the world, not how it is implemented.
EFFECT_CLASSES = (
    "publish_semi_public",
    "publish_public",
    "modify_own_asset",
    "delete_own_asset",
    "direct_message",
    "financial",
)

# Can it be taken back? This is the axis that decides shipping order.
REVERSIBILITY = ("reversible", "reversible_within_window", "irreversible")

_REVERSIBILITY_RANK = {name: i for i, name in enumerate(REVERSIBILITY)}

# Risk is not the order the vocabulary happens to be listed in. A semi-public
# upload outranks nothing; a public broadcast and a movement of money outrank
# almost everything, because an audience cannot be unshown what it has seen.
_EFFECT_RISK = {
    "publish_semi_public": 0,
    "modify_own_asset": 1,
    "delete_own_asset": 2,
    "direct_message": 3,
    "publish_public": 4,
    "financial": 5,
}

_PLATFORM_REQUIRED = (
    "platform",
    "status",
    "actions",
    "human_approval_required",
)

_ACTION_REQUIRED = ("name", "effect_class", "reversibility")


class DeclarationError(ValueError):
    """The declaration file contradicts its own rules."""


@dataclass(frozen=True)
class ActionSpec:
    """One action an adapter may attempt, with its own effect class."""

    name: str
    effect_class: str
    reversibility: str
    kind: Optional[str] = None
    enabled: bool = False
    notes: str = ""

    @property
    def risk_key(self) -> Tuple[int, int]:
        return (_REVERSIBILITY_RANK[self.reversibility], _EFFECT_RISK[self.effect_class])


@dataclass(frozen=True)
class PlatformDeclaration:
    """One platform, the actions declared for it, and what it costs to run."""

    platform: str
    status: str
    actions: Tuple[ActionSpec, ...]
    human_approval_required: bool
    required_scopes: Tuple[str, ...] = ()
    quota_ceiling_per_day: Optional[int] = None
    adapter: Optional[str] = None
    tests: Optional[str] = None
    notes: str = ""
    kinds: Dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def permitted(self) -> bool:
        """Whether this platform may ever be asked for a decision.

        A declaration authorizes nothing by itself. An executor has to exist, and
        ``declared`` entries explicitly do not.
        """
        return self.status in ("stub", "active")

    @property
    def tools(self) -> Tuple[str, ...]:
        return tuple(f"{self.platform}.{a.name}" for a in self.actions)

    @property
    def enabled_actions(self) -> Tuple[ActionSpec, ...]:
        return tuple(a for a in self.actions if a.enabled)

    @property
    def risk_key(self) -> Tuple[int, int]:
        """A platform is as risky as its riskiest action that may run today.

        Declared-but-disabled actions are excluded on purpose: the order is about
        what can happen now, not everything an adapter might eventually do.
        """
        enabled = self.enabled_actions
        if enabled:
            return max(a.risk_key for a in enabled)
        # Nothing enabled yet: rank it by what it would be if it were, so a
        # future platform does not sort ahead of the work already underway.
        return max(a.risk_key for a in self.actions)

    def enabled_tools(self) -> Tuple[str, ...]:
        return tuple(f"{self.platform}.{a.name}" for a in self.enabled_actions)

    def action(self, name: str) -> Optional[ActionSpec]:
        for a in self.actions:
            if a.name == name:
                return a
        return None

    def resolve_kind(self, kind: str) -> Optional[str]:
        """Map an adapter's action enum value to a declared action name."""
        for a in self.actions:
            if a.kind == kind:
                return a.name
        return None


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise DeclarationError(message)


def _parse_action(platform: str, raw: Dict[str, Any]) -> ActionSpec:
    missing = [k for k in _ACTION_REQUIRED if k not in raw]
    _require(not missing, f"{platform}: action missing {missing}")
    name = str(raw["name"]).strip()
    _require(bool(name), f"{platform}: action has an empty name")
    _require(
        raw["effect_class"] in EFFECT_CLASSES,
        f"{platform}/{name}: effect_class {raw['effect_class']!r} not in {EFFECT_CLASSES}",
    )
    _require(
        raw["reversibility"] in REVERSIBILITY,
        f"{platform}/{name}: reversibility {raw['reversibility']!r} not in {REVERSIBILITY}",
    )
    return ActionSpec(
        name=name,
        effect_class=raw["effect_class"],
        reversibility=raw["reversibility"],
        kind=raw.get("kind"),
        enabled=bool(raw.get("enabled", False)),
        notes=raw.get("notes", ""),
    )


def _parse_platform(raw: Dict[str, Any]) -> PlatformDeclaration:
    missing = [k for k in _PLATFORM_REQUIRED if k not in raw]
    _require(not missing, f"{raw.get('platform', '<unnamed>')}: missing {missing}")

    platform = str(raw["platform"]).strip().lower()
    _require(bool(platform), "platform name is empty")
    _require(raw["status"] in STATUSES, f"{platform}: status {raw['status']!r} not in {STATUSES}")

    raw_actions = raw["actions"] or []
    _require(len(raw_actions) > 0, f"{platform}: declares no actions")
    actions = tuple(_parse_action(platform, a) for a in raw_actions)
    names = [a.name for a in actions]
    _require(len(set(names)) == len(names), f"{platform}: duplicate action in declaration")

    kinds: Dict[str, str] = {}
    for a in actions:
        if a.kind:
            _require(
                a.kind not in kinds,
                f"{platform}: two actions share the kind {a.kind!r}",
            )
            kinds[a.kind] = a.name

    decl = PlatformDeclaration(
        platform=platform,
        status=raw["status"],
        actions=actions,
        human_approval_required=bool(raw["human_approval_required"]),
        required_scopes=tuple(raw.get("required_scopes") or ()),
        quota_ceiling_per_day=raw.get("quota_ceiling_per_day"),
        adapter=raw.get("adapter"),
        tests=raw.get("tests"),
        notes=raw.get("notes", ""),
        kinds=kinds,
    )

    enabled_irreversible = [a for a in actions if a.enabled and a.reversibility == "irreversible"]
    if enabled_irreversible:
        _require(
            any(a.enabled and a.reversibility != "irreversible" for a in actions),
            f"{platform}: cannot enable {enabled_irreversible[0].name!r} before a reversible "
            "action on the same platform has been proven to run",
        )

    irreversible = [a for a in actions if a.reversibility == "irreversible"]
    if irreversible:
        _require(
            decl.human_approval_required,
            f"{platform}: an irreversible action requires human approval",
        )
        _require(
            bool(decl.quota_ceiling_per_day),
            f"{platform}: an irreversible action requires a declared daily quota ceiling",
        )

    if decl.status in ("stub", "active"):
        _require(bool(decl.adapter), f"{platform}: status {decl.status} requires an adapter name")
        _require(
            bool(decl.required_scopes),
            f"{platform}: status {decl.status} requires at least one minimal OAuth scope",
        )
        _require(
            bool(decl.quota_ceiling_per_day),
            f"{platform}: status {decl.status} requires a daily quota ceiling",
        )
        _require(
            bool(decl.tests),
            f"{platform}: status {decl.status} requires a test suite reference",
        )
    else:
        # Declared means no executor yet. Claiming one would make an unbuilt
        # platform look ready to a reviewer skimming the file.
        _require(decl.adapter is None, f"{platform}: status declared must not name an adapter")
        _require(decl.tests is None, f"{platform}: status declared must not claim a test suite")
        _require(
            not decl.required_scopes,
            f"{platform}: status declared must not claim OAuth scopes it has not been granted",
        )

    return decl


class AdapterRegistry:
    """Validated view over the declarations, plus the policy it generates."""

    def __init__(self, platforms: Iterable[PlatformDeclaration], schema: int = 2):
        self.schema = int(schema)
        self.platforms: Tuple[PlatformDeclaration, ...] = tuple(platforms)
        _require(len(self.platforms) > 0, "registry is empty")
        seen: set = set()
        for p in self.platforms:
            _require(p.platform not in seen, f"duplicate platform {p.platform}")
            seen.add(p.platform)
        self._by_platform = {p.platform: p for p in self.platforms}

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AdapterRegistry":
        raw = json.loads(Path(path or DECLARATIONS_PATH).read_text(encoding="utf-8"))
        platforms = [_parse_platform(p) for p in raw.get("platforms", [])]
        registry = cls(platforms, schema=raw.get("schema", 2))
        registry._validate_order()
        return registry

    def _validate_order(self) -> None:
        keys = [p.risk_key for p in self.platforms]
        for i in range(1, len(keys)):
            _require(
                keys[i] >= keys[i - 1],
                f"{self.platforms[i].platform} is declared before "
                f"{self.platforms[i - 1].platform} but its effect is harder to undo",
            )

    # -- lookups ---------------------------------------------------------

    def get(self, platform: str) -> Optional[PlatformDeclaration]:
        return self._by_platform.get(platform.strip().lower())

    def permitted_platforms(self) -> Tuple[PlatformDeclaration, ...]:
        return tuple(p for p in self.platforms if p.permitted)

    def activation_order(self) -> Tuple[str, ...]:
        return tuple(p.platform for p in self.platforms)

    def tool_for(self, platform: str, action: str) -> str:
        return f"{platform.strip().lower()}.{action.strip()}"

    # -- the only decision this module is allowed to make ----------------

    def check_declared(self, platform: str, action: str) -> Tuple[bool, str]:
        """Return (not-refused, reason). A pass is not a permission.

        Denials here are local and cheap. There is deliberately no path where
        this returns an allow on its own authority: the caller still needs a
        CUSTOS decision before acting, and a refusal here can never be overridden
        downstream.
        """
        decl = self.get(platform)
        if decl is None:
            return False, f"platform {platform!r} is not declared"
        if not decl.permitted:
            return False, f"platform {platform!r} is {decl.status}: no executor, nothing permitted"
        spec = decl.action(action)
        if spec is None:
            return False, f"{decl.platform}: action {action!r} is not in the declared allowlist"
        if not spec.enabled:
            return False, (
                f"{decl.platform}: action {action!r} is declared but not enabled "
                f"({spec.effect_class}/{spec.reversibility})"
            )
        return True, f"enabled ({spec.effect_class}/{spec.reversibility})"

    # -- generated policy ------------------------------------------------

    def allowed_tools(self) -> Tuple[str, ...]:
        """Tools the gate may be asked about. Declared platforms are absent."""
        tools: List[str] = []
        for p in self.permitted_platforms():
            tools.extend(p.enabled_tools())
        return tuple(sorted(tools))

    def policy(self) -> Dict[str, Any]:
        """A deny-by-default policy document generated from the declarations."""
        actions: Dict[str, Any] = {}
        for p in self.permitted_platforms():
            for spec in p.enabled_actions:
                actions[f"{p.platform}.{spec.name}"] = {
                    "platform": p.platform,
                    "effect_class": spec.effect_class,
                    "reversibility": spec.reversibility,
                    "human_approval_required": p.human_approval_required,
                    "required_scopes": list(p.required_scopes),
                    "quota_ceiling_per_day": p.quota_ceiling_per_day,
                }
        return {
            "schema": 2,
            "deny_by_default": True,
            "generated_from": f"sha256:{self.digest()}",
            "allowlist": list(self.allowed_tools()),
            "actions": actions,
            "excluded": [p.platform for p in self.platforms if not p.permitted],
        }

    def digest(self) -> str:
        """Digest of the declarations only, so the policy can cite its source."""
        blob = json.dumps(
            [
                {
                    "platform": p.platform,
                    "status": p.status,
                    "required_scopes": list(p.required_scopes),
                    "quota_ceiling_per_day": p.quota_ceiling_per_day,
                    "human_approval_required": p.human_approval_required,
                    "actions": [
                        {
                            "name": a.name,
                            "kind": a.kind,
                            "effect_class": a.effect_class,
                            "reversibility": a.reversibility,
                            "enabled": a.enabled,
                        }
                        for a in p.actions
                    ],
                }
                for p in self.platforms
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

"""The adapter registry: declarations that can refuse, and nothing that can permit."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custos_distribution_agent.adapters import (  # noqa: E402
    AdapterRegistry,
    DeclarationError,
    EFFECT_CLASSES,
    REVERSIBILITY,
    STATUSES,
)
from custos_distribution_agent.audit import AuditChain  # noqa: E402
from custos_distribution_agent.gate import CUSTOSGate  # noqa: E402
from custos_distribution_agent.models import ActionKind, YouTubeAction  # noqa: E402
from custos_distribution_agent.pipeline import run_action  # noqa: E402

DECLARATIONS = Path(__file__).resolve().parents[1] / "custos_distribution_agent" / "adapters" / "declarations.json"


@pytest.fixture(scope="module")
def registry():
    return AdapterRegistry.load()


def _write(tmp_path, mutate):
    raw = json.loads(DECLARATIONS.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "declarations.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _platform(raw, name):
    return next(p for p in raw["platforms"] if p["platform"] == name)


# -- the file describes itself honestly ---------------------------------


def test_every_declaration_uses_the_closed_vocabularies(registry):
    for p in registry.platforms:
        assert p.status in STATUSES
        for a in p.actions:
            assert a.effect_class in EFFECT_CLASSES, f"{p.platform}/{a.name}"
            assert a.reversibility in REVERSIBILITY, f"{p.platform}/{a.name}"


def test_every_executor_platform_declares_scopes_quota_and_tests(registry):
    for p in registry.permitted_platforms():
        assert p.required_scopes, f"{p.platform} claims an executor with no scope"
        assert p.quota_ceiling_per_day, f"{p.platform} claims an executor with no quota"
        assert p.tests and Path(DECLARATIONS.parents[2] / p.tests).exists(), p.platform


def test_declared_platforms_claim_no_executor_and_no_scopes(registry):
    for p in registry.platforms:
        if p.status == "declared":
            assert p.adapter is None
            assert p.tests is None
            assert not p.required_scopes


def test_effect_class_belongs_to_the_action_not_the_platform(registry):
    """One adapter, two classes: an unlisted upload is not a public reply."""
    yt = registry.get("youtube")
    upload = yt.action("upload_video:unlisted")
    reply = yt.action("reply_comment")
    assert upload.effect_class == "publish_semi_public"
    assert reply.effect_class == "publish_public"
    assert upload.reversibility == "reversible"
    assert reply.reversibility == "irreversible"
    assert reply.risk_key > upload.risk_key


# -- refusing is the only decision it may make --------------------------


def test_unknown_platform_is_refused(registry):
    ok, why = registry.check_declared("myspace", "post")
    assert ok is False and "not declared" in why


def test_declared_platform_is_refused_even_for_a_declared_action(registry):
    ok, why = registry.check_declared("x", "post")
    assert ok is False and "no executor" in why


def test_undeclared_action_on_a_live_adapter_is_refused(registry):
    """A public upload is not in the file, so the allowlist cannot be widened by intent."""
    ok, why = registry.check_declared("youtube", "upload_video:public")
    assert ok is False and "not in the declared allowlist" in why


def test_declared_but_disabled_action_is_refused(registry):
    ok, why = registry.check_declared("youtube", "reply_comment")
    assert ok is False and "declared but not enabled" in why


def test_a_pass_from_the_registry_is_not_a_permission(registry):
    """The wording matters: it reports that nothing refused, not that it allowed."""
    ok, why = registry.check_declared("youtube", "upload_video:unlisted")
    assert ok is True
    assert why.startswith("enabled")
    assert "allow" not in why.lower()


# -- the generated policy ----------------------------------------------


def test_generated_policy_lists_only_enabled_actions(registry):
    policy = registry.policy()
    assert policy["deny_by_default"] is True
    assert set(policy["allowlist"]) == {
        "youtube.upload_video:unlisted",
        "youtube.update_metadata",
        "youtube.add_to_playlist",
    }
    assert "youtube.reply_comment" not in policy["allowlist"]
    assert "x.post" not in policy["allowlist"]


def test_generated_policy_carries_the_effect_class_per_action(registry):
    actions = registry.policy()["actions"]
    assert actions["youtube.reply_comment"]["reversibility"] == "irreversible" if "youtube.reply_comment" in actions else True
    assert actions["youtube.upload_video:unlisted"]["effect_class"] == "publish_semi_public"
    assert actions["youtube.upload_video:unlisted"]["human_approval_required"] is True


def test_policy_cites_the_digest_of_the_declarations(registry):
    policy = registry.policy()
    assert policy["generated_from"] == f"sha256:{registry.digest()}"


def test_digest_moves_when_an_effect_class_moves(registry, tmp_path):
    def mutate(raw):
        _platform(raw, "youtube")["actions"][0]["effect_class"] = "publish_public"

    moved = AdapterRegistry.load(_write(tmp_path, mutate))
    assert moved.digest() != registry.digest()


def test_digest_moves_when_an_action_is_enabled(tmp_path):
    """The enabled set is part of the citation, not a runtime detail."""

    def build(enabled):
        raw = {
            "schema": 2,
            "platforms": [
                {
                    "platform": "demo",
                    "status": "stub",
                    "adapter": "DemoExecutor",
                    "required_scopes": ["demo.write"],
                    "quota_ceiling_per_day": 2,
                    "human_approval_required": True,
                    "tests": "tests/test_governance.py",
                    "actions": [
                        {"name": "a", "effect_class": "modify_own_asset",
                         "reversibility": "reversible", "enabled": enabled},
                        {"name": "b", "effect_class": "modify_own_asset",
                         "reversibility": "reversible", "enabled": False},
                    ],
                }
            ],
        }
        path = tmp_path / f"declarations-{enabled}.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return AdapterRegistry.load(path)

    assert build(True).digest() != build(False).digest()


# -- guards that refuse a file contradicting itself --------------------


def test_order_must_follow_the_risk_ranking(tmp_path):
    def mutate(raw):
        # Reversing the file puts the riskiest platforms first, which contradicts
        # the ranking the registry computes for itself.
        raw["platforms"].reverse()

    with pytest.raises(DeclarationError, match="harder to undo"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_enabling_an_irreversible_action_without_a_proven_reversible_one_fails(tmp_path):
    def mutate(raw):
        yt = _platform(raw, "youtube")
        for a in yt["actions"]:
            a["enabled"] = a["reversibility"] == "irreversible"

    with pytest.raises(DeclarationError, match="before a reversible"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_irreversible_action_without_human_approval_fails(tmp_path):
    def mutate(raw):
        _platform(raw, "youtube")["human_approval_required"] = False

    with pytest.raises(DeclarationError, match="requires human approval"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_irreversible_action_without_a_quota_ceiling_fails(tmp_path):
    def mutate(raw):
        _platform(raw, "youtube")["quota_ceiling_per_day"] = None

    with pytest.raises(DeclarationError, match="quota ceiling"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_executor_platform_without_scopes_fails(tmp_path):
    def mutate(raw):
        _platform(raw, "youtube")["required_scopes"] = []

    with pytest.raises(DeclarationError, match="OAuth scope"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_declared_platform_claiming_an_adapter_fails(tmp_path):
    def mutate(raw):
        _platform(raw, "x")["adapter"] = "XExecutor"

    with pytest.raises(DeclarationError, match="must not name an adapter"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_unknown_status_fails(tmp_path):
    def mutate(raw):
        _platform(raw, "x")["status"] = "ready"

    with pytest.raises(DeclarationError, match="not in"):
        AdapterRegistry.load(_write(tmp_path, mutate))


def test_duplicate_action_in_one_platform_fails(tmp_path):
    def mutate(raw):
        yt = _platform(raw, "youtube")
        yt["actions"].append(dict(yt["actions"][0]))

    with pytest.raises(DeclarationError, match="duplicate action"):
        AdapterRegistry.load(_write(tmp_path, mutate))


# -- and the pipeline honours it ---------------------------------------


def test_pipeline_denies_an_undeclared_action_before_spending_a_gate_decision(tmp_path):
    class NeverAsked(CUSTOSGate):
        def evaluate(self, action):  # pragma: no cover - must not be reached
            raise AssertionError("the gate must not be asked about an undeclared action")

    chain = AuditChain(tmp_path / "a.jsonl")
    outcome = run_action(
        YouTubeAction(ActionKind.REPLY_COMMENT, video_id="abc"),
        gate=NeverAsked(), chain=chain, approve=lambda a: True,
    )
    assert outcome["status"] == "denied"
    assert outcome["by"] == "adapter_registry"
    events = [json.loads(line)["event"] for line in (tmp_path / "a.jsonl").read_text().splitlines()]
    assert events == ["drafted", "denied"]
    assert chain.verify() is True


def test_pipeline_still_requires_the_gate_for_an_enabled_action(tmp_path):
    class DeadGate(CUSTOSGate):
        def evaluate(self, action):
            return False

    chain = AuditChain(tmp_path / "b.jsonl")
    outcome = run_action(
        YouTubeAction(ActionKind.UPLOAD, video_id="abc"),
        gate=DeadGate(), chain=chain, approve=lambda a: True,
    )
    assert outcome["status"] == "denied"
    assert "by" not in outcome or outcome.get("by") != "adapter_registry"

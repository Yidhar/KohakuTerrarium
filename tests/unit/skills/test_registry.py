"""Unit tests for active-skill state on :class:`SkillRegistry`.

The active skill is what the allowed-tools gate keys off. Contract:

- ``set_active`` only accepts a registered name; unknown names are
  rejected so a stale invocation cannot pin a phantom skill.
- "last invoked wins": a later ``set_active`` replaces the previous one.
- a disabled skill is never "active" (disabling lifts its restriction).
- the active name round-trips through the scratchpad so a mid-task resume
  keeps the restriction in force.
"""

from kohakuterrarium.core.scratchpad import Scratchpad
from kohakuterrarium.skills.registry import (
    SCRATCHPAD_ACTIVE_KEY,
    Skill,
    SkillRegistry,
)


def _skill(name, *, allowed=None, enabled=True):
    return Skill(
        name=name,
        description=f"{name} desc",
        body=f"{name} body",
        allowed_tools=list(allowed or []),
        enabled=enabled,
    )


class TestActiveSkill:
    def test_none_active_initially(self):
        reg = SkillRegistry()
        reg.add(_skill("a"))
        assert reg.active_skill is None

    def test_set_active_unknown_rejected(self):
        reg = SkillRegistry()
        reg.add(_skill("a"))
        assert reg.set_active("ghost") is False
        assert reg.active_skill is None

    def test_set_active_known_resolves(self):
        reg = SkillRegistry()
        reg.add(_skill("a", allowed=["bash"]))
        assert reg.set_active("a") is True
        assert reg.active_skill is not None
        assert reg.active_skill.name == "a"

    def test_last_invoked_wins(self):
        reg = SkillRegistry()
        reg.add(_skill("a", allowed=["bash"]))
        reg.add(_skill("b"))
        reg.set_active("a")
        reg.set_active("b")
        assert reg.active_skill.name == "b"

    def test_disabled_skill_is_not_active(self):
        reg = SkillRegistry()
        reg.add(_skill("a", allowed=["bash"]))
        reg.set_active("a")
        reg.disable("a")
        # Disabling the active skill must lift it (and therefore its
        # tool restriction).
        assert reg.active_skill is None

    def test_clear_active(self):
        reg = SkillRegistry()
        reg.add(_skill("a"))
        reg.set_active("a")
        reg.clear_active()
        assert reg.active_skill is None


class TestActivePersistence:
    def test_active_round_trips_through_scratchpad(self):
        pad = Scratchpad()
        reg = SkillRegistry(scratchpad=pad)
        reg.add(_skill("writer", allowed=["bash"]))
        reg.set_active("writer")
        assert pad.get(SCRATCHPAD_ACTIVE_KEY) == "writer"

        # Simulate resume: a fresh registry bound to the same scratchpad,
        # then the skill is rediscovered and added.
        reg2 = SkillRegistry(scratchpad=pad)
        reg2.add(_skill("writer", allowed=["bash"]))
        assert reg2.active_skill is not None
        assert reg2.active_skill.name == "writer"

    def test_clear_persists_empty(self):
        pad = Scratchpad()
        reg = SkillRegistry(scratchpad=pad)
        reg.add(_skill("writer"))
        reg.set_active("writer")
        reg.clear_active()
        assert pad.get(SCRATCHPAD_ACTIVE_KEY) == ""


class TestBundleDirField:
    def test_default_bundle_dir_is_none(self):
        # Flat-form skills carry no private bundle dir.
        assert _skill("a").bundle_dir is None

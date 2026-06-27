"""Unit tests for :class:`SkillCommand` rendering + activation.

Invoking a skill must (1) render the body, (2) append the bundled-resource
manifest for folder-form skills, (3) advertise any allowed-tools
restriction, and (4) mark the skill active so the gate can enforce it.
"""

import asyncio

from kohakuterrarium.skills.command import SkillCommand
from kohakuterrarium.skills.registry import Skill, SkillRegistry


def _bundle_skill(tmp_path, *, allowed=None):
    sk = tmp_path / "writer"
    (sk / "template").mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: writer\n---\nbody")
    (sk / "template" / "science_fiction.md").write_text("scifi")
    return Skill(
        name="writer",
        description="write things",
        body="Body. See template/science_fiction.md",
        allowed_tools=list(allowed or []),
        bundle_dir=sk,
    )


def _run(reg, args):
    return asyncio.run(SkillCommand(reg).execute(args, None))


class TestSkillCommandRendering:
    def test_renders_body(self, tmp_path):
        reg = SkillRegistry()
        reg.add(_bundle_skill(tmp_path))
        out = _run(reg, "writer")
        assert "Body." in out.content

    def test_renders_resource_manifest(self, tmp_path):
        reg = SkillRegistry()
        reg.add(_bundle_skill(tmp_path))
        out = _run(reg, "writer")
        assert "Skill resources" in out.content
        assert "template/science_fiction.md" in out.content

    def test_renders_restriction_when_allowed_tools(self, tmp_path):
        reg = SkillRegistry()
        reg.add(_bundle_skill(tmp_path, allowed=["bash", "write"]))
        out = _run(reg, "writer")
        assert "Tool restriction" in out.content
        assert "bash, write" in out.content

    def test_no_restriction_block_without_allowed_tools(self, tmp_path):
        reg = SkillRegistry()
        reg.add(_bundle_skill(tmp_path))
        out = _run(reg, "writer")
        assert "Tool restriction" not in out.content

    def test_invocation_sets_active(self, tmp_path):
        reg = SkillRegistry()
        reg.add(_bundle_skill(tmp_path, allowed=["bash"]))
        assert reg.active_skill is None
        _run(reg, "writer")
        assert reg.active_skill is not None
        assert reg.active_skill.name == "writer"

    def test_disabled_skill_not_activated(self, tmp_path):
        reg = SkillRegistry()
        skill = _bundle_skill(tmp_path, allowed=["bash"])
        skill.enabled = False
        reg.add(skill)
        out = _run(reg, "writer")
        # Disabled skills are refused, and must not become active.
        assert out.error is not None
        assert reg.active_skill is None

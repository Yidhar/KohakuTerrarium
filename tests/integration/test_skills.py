"""Integration test for the procedural ``skills/`` folder.

Drives the full progressive-disclosure + allowed-tools workflow across the
real collaborators a consumer wires together: an on-disk ``SKILL.md`` bundle
is discovered into a real :class:`SkillRegistry`, invoked through the real
:class:`SkillCommand` (which renders the bundled-resource manifest and marks
the skill active), and the real :class:`SkillToolGatePlugin` then enforces
the skill's ``allowed-tools`` whitelist on subsequent tool calls — until a
different skill is invoked, which lifts the restriction. Activation also
survives a resume because it is scratchpad-backed.

No LLM seam is needed: this exercises the deterministic skill/gate policy
wiring, not a reasoning loop.
"""

import asyncio

import pytest

from kohakuterrarium.builtins.plugins.skillgate.plugin import SkillToolGatePlugin
from kohakuterrarium.core.scratchpad import Scratchpad
from kohakuterrarium.modules.plugin.base import PluginBlockError, PluginContext
from kohakuterrarium.skills.command import SkillCommand
from kohakuterrarium.skills.discovery import discover_skills
from kohakuterrarium.skills.registry import SkillRegistry


class _Agent:
    """Minimal host the gate reaches ``.skills`` through (real registry)."""

    def __init__(self, skills):
        self.skills = skills


class TestSkillsWorkflow:
    def test_progressive_disclosure_and_gate_end_to_end(self, tmp_path):
        # 1. Author a folder-form skill bundle: a restriction + a resource.
        proj = tmp_path / "proj"
        writer = proj / ".kt" / "skills" / "writer"
        (writer / "template").mkdir(parents=True)
        (writer / "SKILL.md").write_text(
            "---\nname: writer\ndescription: long-form writer\n"
            "allowed-tools: bash, write\n---\n"
            "Use template/science_fiction.md for the sci-fi voice.\n"
        )
        (writer / "template" / "science_fiction.md").write_text("scifi voice")

        # A second, unrestricted skill to prove switching lifts the gate.
        chat = proj / ".kt" / "skills" / "chat"
        chat.mkdir(parents=True)
        (chat / "SKILL.md").write_text(
            "---\nname: chat\ndescription: free chat\n---\nJust chat.\n"
        )

        # 2. Discover into a real registry (the consumer's wiring). A clean
        #    home dir keeps the scan to this project's bundles.
        home = tmp_path / "home"
        home.mkdir()
        pad = Scratchpad()
        registry = SkillRegistry(scratchpad=pad)
        for skill in discover_skills(cwd=proj, home=home):
            registry.add(skill)
        assert {"writer", "chat"} <= set(registry.names())

        # 3. Invoke the restricted skill through the real command.
        out = asyncio.run(SkillCommand(registry).execute("writer", None))
        assert "Use template/science_fiction.md" in out.content  # body rendered
        assert str(writer.resolve()) in out.content  # resource directory
        assert "template/science_fiction.md" in out.content  # manifest entry
        assert "Tool restriction" in out.content  # whitelist advertised
        assert registry.active_skill is not None
        assert registry.active_skill.name == "writer"  # activated

        # 4. The real gate enforces the whitelist on the next tool call.
        gate = SkillToolGatePlugin()
        asyncio.run(gate.on_load(PluginContext(_host_agent=_Agent(registry))))
        assert asyncio.run(gate.pre_tool_execute({}, tool_name="bash")) is None
        assert asyncio.run(gate.pre_tool_execute({}, tool_name="read")) is None
        with pytest.raises(PluginBlockError):
            asyncio.run(gate.pre_tool_execute({}, tool_name="grep"))

        # 5. Switching to an unrestricted skill lifts the restriction...
        asyncio.run(SkillCommand(registry).execute("chat", None))
        assert asyncio.run(gate.pre_tool_execute({}, tool_name="grep")) is None

        # ...and the active skill survives a resume (scratchpad-backed).
        resumed = SkillRegistry(scratchpad=pad)
        for skill in discover_skills(cwd=proj, home=home):
            resumed.add(skill)
        assert resumed.active_skill is not None
        assert resumed.active_skill.name == "chat"

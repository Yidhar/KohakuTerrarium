"""Legacy text-format controller command for procedural skills.

Native-capable models should use the built-in ``skill`` tool. This
command remains for bracket/XML/custom text tool formats and shares the
same registry lookup/rendering behavior.

Note: ``disable-model-invocation: true`` hides a skill from the
auto-invoke index (aggregator.py) but explicit skill invocation is still
allowed (spec 4.4).
"""

from typing import Any

from kohakuterrarium.commands.base import BaseCommand, CommandResult
from kohakuterrarium.skill_docs import render_skill_resources
from kohakuterrarium.skills.registry import (
    IMPLICIT_SKILL_ALLOWED_TOOLS,
    Skill,
    SkillRegistry,
)


class SkillCommand(BaseCommand):
    """Return a procedural skill's body."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def command_name(self) -> str:
        return "skill"

    @property
    def description(self) -> str:
        return "Invoke a procedural skill by name (returns the skill body)"

    async def _execute(self, args: str, context: Any) -> CommandResult:
        text = (args or "").strip()
        if not text:
            return CommandResult(
                error=(
                    "No skill name provided. Use skill(name=..., arguments=...). "
                    "List skills with /skill list."
                )
            )
        parts = text.split(None, 1)
        name = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""

        skill = self._registry.get(name)
        if skill is None:
            available = ", ".join(self._registry.names()) or "(none)"
            return CommandResult(
                error=(
                    f"Unknown skill: {name!r}. Available: {available}. "
                    "Run info(name=<skill_name>) for details."
                )
            )
        if not skill.enabled:
            return CommandResult(
                error=(
                    f"Skill {name!r} is disabled. Enable it with "
                    f"/skill enable {name} (user) or leave it off."
                )
            )

        body = skill.body or ""
        preamble = f"## Skill: {skill.name}\n\n{skill.description or ''}".rstrip()
        parts_out = [preamble]
        if rest:
            parts_out.append(f"\nArguments: {rest}")
        parts_out.append("\n" + body if body else "")

        # Progressive disclosure: surface bundled sibling files so the model
        # can resolve relative references (e.g. ``template/foo.md``) with the
        # ``read`` tool. Empty for flat-form skills with no private folder.
        resources = render_skill_resources(skill.bundle_dir)
        if resources:
            parts_out.append("\n" + resources)

        restriction = _render_tool_restriction(skill)
        if restriction:
            parts_out.append("\n" + restriction)

        content = "\n".join(p for p in parts_out if p)

        # Mark this skill active so the allowed-tools gate plugin (when
        # enabled) can enforce its whitelist on subsequent tool calls.
        self._registry.set_active(skill.name)

        return CommandResult(content=content)


def _render_tool_restriction(skill: Skill) -> str:
    """Advertise a skill's ``allowed-tools`` whitelist to the model.

    Returns ``""`` when the skill declares no whitelist. The advertised
    implicit-allow set is sourced from the same constant the gate plugin
    enforces, so the prose can never drift from the actual policy.
    """
    if not skill.allowed_tools:
        return ""
    allowed = ", ".join(skill.allowed_tools)
    implicit = ", ".join(IMPLICIT_SKILL_ALLOWED_TOOLS)
    return (
        "## Tool restriction (active while you follow this skill)\n"
        f"You may only call these tools: {allowed} "
        f"(plus the always-available {implicit}). Other tool calls are "
        "blocked until you invoke a different skill."
    )

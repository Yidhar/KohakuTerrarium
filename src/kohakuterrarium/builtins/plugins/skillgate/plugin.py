"""Allowed-tools gate — enforce an active skill's tool whitelist.

A procedural skill may declare an ``allowed-tools`` whitelist in its
``SKILL.md`` frontmatter. On its own that whitelist is inert: the loader
parses it but nothing stops the model from calling other tools. This
plugin closes that gap. While a skill with a non-empty ``allowed-tools``
list is *active* (i.e. the model invoked it via the ``skill`` tool), any
tool call whose name is outside the whitelist is blocked in
``pre_tool_execute`` — the deterministic guardrail counterpart to the
advisory note the skill renderer prints.

A small implicit-allow set (``read`` / ``skill`` / ``info`` /
``stop_task`` by default) is always permitted so a restricted skill can
never deadlock progressive disclosure, skill switching, or turn
completion. The set is shared with the renderer
(``IMPLICIT_SKILL_ALLOWED_TOOLS``) so what the model is told and what is
enforced never drift.

The gate is a no-op whenever no skill is active or the active skill
declares no whitelist, so it is safe to leave enabled for every agent.
``bootstrap.agent_init`` auto-enables it when at least one discovered
skill declares ``allowed-tools``.
"""

from typing import Any

from kohakuterrarium.modules.plugin.base import (
    BasePlugin,
    PluginBlockError,
    PluginContext,
)
from kohakuterrarium.skills.registry import IMPLICIT_SKILL_ALLOWED_TOOLS


class SkillToolGatePlugin(BasePlugin):
    """Block tool calls outside the active skill's allowed-tools whitelist."""

    name = "skill_tool_gate"
    description = (
        "Enforce a procedural skill's allowed-tools whitelist: while a skill "
        "that declares allowed-tools is active, block tool calls outside it "
        "(plus an always-allowed read/skill/info/stop_task set)."
    )
    # Run before permgate (100) but after argument-rewriting plugins (~50):
    # a disallowed tool should be vetoed outright, not surfaced for approval.
    priority = 90

    @classmethod
    def option_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "implicit_allow": {
                "type": "list",
                "item_type": "string",
                "default": list(IMPLICIT_SKILL_ALLOWED_TOOLS),
                "doc": (
                    "Tools permitted even when not in the active skill's "
                    "allowed-tools list, so progressive disclosure (read), "
                    "skill switching (skill/info), and turn completion "
                    "(stop_task) never deadlock under a restriction."
                ),
            },
        }

    def __init__(
        self,
        implicit_allow: list[str] | None = None,
        **_extra: Any,
    ) -> None:
        super().__init__()
        self.options = {
            "implicit_allow": (
                list(implicit_allow)
                if implicit_allow is not None
                else list(IMPLICIT_SKILL_ALLOWED_TOOLS)
            ),
        }
        self.refresh_options()
        self._context: PluginContext | None = None

    # ── Options ──

    def refresh_options(self) -> None:
        """Re-derive the implicit-allow set from :attr:`options`."""
        self._implicit_allow: set[str] = set(self.options.get("implicit_allow") or [])

    # ── Lifecycle ──

    async def on_load(self, context: PluginContext) -> None:
        self._context = context

    # ── Gating ──

    def _active_restriction(self) -> tuple[str, set[str]] | None:
        """Return ``(skill_name, allowed_tools)`` when a restriction is in
        force, else ``None``.

        ``None`` covers every no-op path: plugin not yet bound, no agent,
        no skill registry, no active skill, or an active skill that
        declares no ``allowed-tools`` whitelist.
        """
        ctx = self._context
        if ctx is None:
            return None
        agent = ctx.host_agent
        if agent is None:
            return None
        registry = getattr(agent, "skills", None)
        if registry is None:
            return None
        active = getattr(registry, "active_skill", None)
        if active is None or not active.allowed_tools:
            return None
        return active.name, set(active.allowed_tools)

    async def pre_tool_execute(self, args: dict, **kwargs: Any) -> dict | None:
        """Block the call when the active skill's whitelist excludes it."""
        tool_name = kwargs.get("tool_name", "")
        if not tool_name:
            return None
        restriction = self._active_restriction()
        if restriction is None:
            return None
        skill_name, allowed = restriction
        if tool_name in allowed or tool_name in self._implicit_allow:
            return None
        permitted = ", ".join(sorted(allowed | self._implicit_allow))
        raise PluginBlockError(
            f"Tool '{tool_name}' is blocked while skill '{skill_name}' is "
            f"active (allowed-tools restriction). Permitted tools: {permitted}. "
            "Invoke a different skill to change or lift the restriction."
        )

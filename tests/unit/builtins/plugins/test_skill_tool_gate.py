"""Unit tests for :class:`SkillToolGatePlugin`.

The gate turns a skill's ``allowed-tools`` whitelist into a deterministic
veto. Contract (negative cases matter most here):

- no active skill, or an active skill without ``allowed-tools`` → no-op.
- a tool in the whitelist, or in the implicit-allow set → permitted.
- any other tool while a restricted skill is active → ``PluginBlockError``.
"""

import asyncio

import pytest

from kohakuterrarium.builtins.plugins.skillgate.plugin import SkillToolGatePlugin
from kohakuterrarium.modules.plugin.base import PluginBlockError, PluginContext
from kohakuterrarium.skills.registry import Skill, SkillRegistry


class _FakeAgent:
    def __init__(self, registry):
        self.skills = registry


def _gate(registry):
    plugin = SkillToolGatePlugin()
    ctx = PluginContext(_host_agent=_FakeAgent(registry))
    asyncio.run(plugin.on_load(ctx))
    return plugin


def _call(plugin, tool_name):
    return asyncio.run(plugin.pre_tool_execute({}, tool_name=tool_name))


def _registry(*skills):
    reg = SkillRegistry()
    for s in skills:
        reg.add(s)
    return reg


def _skill(name, allowed=None):
    return Skill(
        name=name,
        description=f"{name} desc",
        body="body",
        allowed_tools=list(allowed or []),
    )


class TestSkillToolGate:
    def test_no_active_skill_is_noop(self):
        reg = _registry(_skill("writer", ["bash"]))
        plugin = _gate(reg)
        # Nothing active yet.
        assert _call(plugin, "grep") is None

    def test_active_without_allowed_tools_is_noop(self):
        reg = _registry(_skill("chat"))
        reg.set_active("chat")
        plugin = _gate(reg)
        assert _call(plugin, "grep") is None

    def test_whitelisted_tool_permitted(self):
        reg = _registry(_skill("writer", ["bash", "write"]))
        reg.set_active("writer")
        plugin = _gate(reg)
        assert _call(plugin, "bash") is None

    def test_implicit_allow_tool_permitted(self):
        reg = _registry(_skill("writer", ["bash"]))
        reg.set_active("writer")
        plugin = _gate(reg)
        # ``read`` is implicitly allowed so progressive disclosure survives.
        assert _call(plugin, "read") is None

    def test_disallowed_tool_blocked(self):
        reg = _registry(_skill("writer", ["bash"]))
        reg.set_active("writer")
        plugin = _gate(reg)
        with pytest.raises(PluginBlockError) as exc:
            _call(plugin, "grep")
        msg = str(exc.value)
        assert "grep" in msg and "writer" in msg

    def test_missing_tool_name_is_noop(self):
        reg = _registry(_skill("writer", ["bash"]))
        reg.set_active("writer")
        plugin = _gate(reg)
        assert _call(plugin, "") is None

    def test_unbound_plugin_is_noop(self):
        # Never loaded (no context) — must not raise.
        plugin = SkillToolGatePlugin()
        assert _call(plugin, "grep") is None

    def test_custom_implicit_allow_option(self):
        reg = _registry(_skill("writer", ["bash"]))
        reg.set_active("writer")
        plugin = SkillToolGatePlugin(implicit_allow=["grep"])
        ctx = PluginContext(_host_agent=_FakeAgent(reg))
        asyncio.run(plugin.on_load(ctx))
        # ``grep`` now whitelisted via implicit_allow; ``glob`` still blocked.
        assert _call(plugin, "grep") is None
        with pytest.raises(PluginBlockError):
            _call(plugin, "glob")

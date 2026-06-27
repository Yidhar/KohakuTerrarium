"""Allowed-tools gate plugin for active procedural skills.

Turns a skill's ``allowed-tools`` frontmatter from advisory text into a
deterministic guardrail. See ``plugin.py`` for details.
"""

from kohakuterrarium.builtins.plugins.skillgate.plugin import SkillToolGatePlugin

__all__ = ["SkillToolGatePlugin"]

"""Headless one-shot mode (switchyard-headless fork).

Drives the real ``_run_headless`` pipeline with a deterministic
``ScriptedLLM`` (no network): build an Agent with ``io="headless"``,
run exactly one turn via ``run_stream``, and serialize each typed event
as JSONL. Asserts the stream framing (turn_start … turn_end) and the
exit-code contract.
"""

import asyncio
import contextlib
import io
import json

from kohakuterrarium.bootstrap import agent_init
from kohakuterrarium.bootstrap import llm as bootstrap_llm
from kohakuterrarium.core import config as kt_config
from kohakuterrarium.core.config_types import AgentConfig, InputConfig, OutputConfig
from kohakuterrarium.testing.llm import ScriptedLLM


def _leaf_cfg(tmp_path) -> AgentConfig:
    """A minimal, no-subagent creature config (offline)."""
    return AgentConfig(
        name="leaf",
        llm_profile="openai/test",
        model="gpt-4",
        provider="openai",
        api_key_env="",
        system_prompt="You are a test agent.",
        include_tools_in_prompt=True,
        include_hints_in_prompt=False,
        tool_format="bracket",
        agent_path=tmp_path,
        input=InputConfig(type="none"),
        output=OutputConfig(type="stdout"),
        tools=[],
        subagents=[],
    )


def _patch_offline(monkeypatch, tmp_path, script):
    def _fake_create(config, llm=None):
        return ScriptedLLM(script)

    monkeypatch.setattr(bootstrap_llm, "create_llm_provider", _fake_create)
    monkeypatch.setattr(agent_init, "create_llm_provider", _fake_create)
    monkeypatch.setattr(
        kt_config, "load_agent_config", lambda *a, **k: _leaf_cfg(tmp_path)
    )


def _run(tmp_path, *, as_json, prompt="ping", no_subagents=True):
    from kohakuterrarium.cli.run import _run_headless

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = asyncio.run(
            _run_headless(
                str(tmp_path),
                prompt=prompt,
                llm=None,
                cwd=str(tmp_path),
                session=None,
                no_subagents=no_subagents,
                sandbox=None,
                as_json=as_json,
            )
        )
    return rc, buf.getvalue()


def test_headless_jsonl_stream(tmp_path, monkeypatch):
    _patch_offline(monkeypatch, tmp_path, ["Hello from headless."])
    rc, out = _run(tmp_path, as_json=True)

    lines = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    assert rc == 0
    # Every line is a valid JSON object with a ``type``.
    assert all("type" in obj for obj in lines)
    # Framing: starts with turn_start, ends with an ok turn_end.
    assert lines[0]["type"] == "turn_start"
    assert lines[0]["agent"] == "leaf"
    assert lines[-1]["type"] == "turn_end"
    assert lines[-1]["status"] == "ok"
    # Assistant text is delivered via ``text`` events.
    text = "".join(o.get("content", "") for o in lines if o["type"] == "text")
    assert "Hello from headless." in text
    # turn_end carries the concatenated text too.
    assert "Hello from headless." in lines[-1]["text"]


def test_headless_plain_text(tmp_path, monkeypatch):
    _patch_offline(monkeypatch, tmp_path, ["plain answer"])
    rc, out = _run(tmp_path, as_json=False)
    assert rc == 0
    # Plain mode: no JSON envelope, just the assistant text.
    assert "plain answer" in out
    assert '"type"' not in out

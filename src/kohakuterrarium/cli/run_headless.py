"""Headless one-shot mode (switchyard-headless fork).

A first-class non-interactive surface: build a standalone Agent with
``io="headless"`` (NoneInput + NoneOutput so nothing pollutes stdout),
drive exactly ONE turn via ``Agent.run_stream``, serialize each typed
event (text / activity / turn_end) as JSONL, and exit with a status
code. This is the path external drivers (Switchyard, CI, scripts) use
to consume KohakuTerrarium as a subprocess.

Split out of ``cli/run.py`` so the interactive run path stays under the
file-size budget and the heavy ``core.agent`` import chain here loads
only when ``--headless`` is dispatched (see ``cli/__init__._dispatch_run``,
which imports this module lazily).
"""

import asyncio
import json
import sys
from pathlib import Path

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.config import load_agent_config
from kohakuterrarium.core.turn import Activity, TextChunk, TurnEnded
from kohakuterrarium.packages.resolve import resolve_any_path
from kohakuterrarium.session.store import SessionStore
from kohakuterrarium.utils.logging import (
    configure_utf8_stdio,
    enable_stderr_logging,
    get_logger,
    set_level,
)

logger = get_logger(__name__)

_SANDBOX_PRESETS = ("PURE", "READ_ONLY", "WORKSPACE", "NETWORK", "SHELL")


def _read_headless_prompt(prompt: str | None, input_file: str | None) -> str:
    """Resolve the headless prompt from --prompt, --input-file, or stdin."""
    if prompt is not None:
        return prompt
    if input_file:
        if input_file == "-":
            return sys.stdin.read()
        return Path(input_file).read_text(encoding="utf-8")
    # No explicit prompt — consume piped stdin if present (skip a TTY so
    # we don't block waiting for a human in an automated context).
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data
    return ""


def _sandbox_spec(sandbox: str | None) -> dict | None:
    """Map a ``--sandbox`` preset to a plugin config spec (or None)."""
    if not sandbox or sandbox.lower() in ("off", "none"):
        return None
    profile = sandbox.upper()
    if profile not in _SANDBOX_PRESETS:
        print(
            f"Warning: unknown --sandbox preset {sandbox!r}; running without sandbox",
            file=sys.stderr,
        )
        return None
    return {"name": "sandbox", "options": {"enabled": True, "profile": profile}}


def _emit_jsonl(obj: dict) -> None:
    """Write one JSON object as a line on stdout and flush immediately."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def run_headless_cli(
    agent_path: str,
    *,
    prompt: str | None = None,
    input_file: str | None = None,
    llm: str | None = None,
    cwd: str | None = None,
    session: str | None = None,
    no_subagents: bool = False,
    sandbox: str | None = None,
    as_json: bool = False,
    log_level: str = "INFO",
) -> int:
    """Run a single headless turn and stream its result.

    With ``as_json`` every turn event (text deltas, tool/sub-agent
    activity, the final result) is emitted as one JSON object per line
    on stdout — the machine-readable surface external drivers consume.
    Without it, only the streamed assistant text is printed.

    Returns 0 when the turn ends ``ok``, non-zero otherwise (2 for a
    missing prompt / bad path).
    """
    configure_utf8_stdio(log=True)
    set_level(log_level)
    # Logs must never corrupt the JSONL stream on stdout — force stderr.
    enable_stderr_logging(log_level)

    prompt_text = _read_headless_prompt(prompt, input_file)
    if not prompt_text.strip():
        print(
            "Error: headless run requires a prompt (--prompt/-p, "
            "--input-file, or piped stdin).",
            file=sys.stderr,
        )
        return 2

    try:
        path = resolve_any_path(agent_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"Error: path not found: {agent_path}", file=sys.stderr)
        return 1

    try:
        return asyncio.run(
            _run_headless(
                str(path),
                prompt=prompt_text,
                llm=llm,
                cwd=cwd,
                session=session,
                no_subagents=no_subagents,
                sandbox=sandbox,
                as_json=as_json,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if as_json:
            _emit_jsonl({"type": "error", "content": str(exc)})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        logger.warning("kt run --headless failed", error=str(exc), exc_info=True)
        return 1


async def _run_headless(
    agent_path: str,
    *,
    prompt: str,
    llm: str | None,
    cwd: str | None,
    session: str | None,
    no_subagents: bool,
    sandbox: str | None,
    as_json: bool,
) -> int:
    cfg = load_agent_config(agent_path)
    # Leaf enforcement: a delegated/headless run must not spawn sub-agents.
    if no_subagents:
        cfg.subagents = []
    spec = _sandbox_spec(sandbox)
    if spec is not None:
        cfg.plugins = list(getattr(cfg, "plugins", []) or []) + [spec]

    agent = await Agent.build(cfg, llm=llm, pwd=cwd, io="headless", strict=False)

    store: SessionStore | None = None
    if session:
        store = SessionStore(Path(session), writer_lock=True)
        agent.attach_session_store(store)

    model = getattr(getattr(agent, "llm", None), "model", "") or cfg.model or ""
    if as_json:
        _emit_jsonl(
            {
                "type": "turn_start",
                "agent": cfg.name,
                "model": model,
                "cwd": cwd or str(Path.cwd()),
            }
        )

    result = None
    try:
        async with agent:
            async for ev in agent.run_stream(prompt):
                if isinstance(ev, TextChunk):
                    if as_json:
                        _emit_jsonl({"type": "text", "content": ev.text})
                    else:
                        sys.stdout.write(ev.text)
                        sys.stdout.flush()
                elif isinstance(ev, Activity):
                    if as_json:
                        _emit_jsonl(
                            {
                                "type": "activity",
                                "activity_type": ev.kind,
                                "detail": ev.detail,
                                "metadata": ev.metadata or {},
                            }
                        )
                elif isinstance(ev, TurnEnded):
                    result = ev.result
                    if as_json:
                        _emit_jsonl(
                            {
                                "type": "turn_end",
                                "status": result.status,
                                "text": result.text,
                                "error": result.error,
                                "usage": result.usage,
                                "duration_s": result.duration_s,
                            }
                        )
    finally:
        if store is not None:
            store.close()

    if (
        not as_json
        and result is not None
        and result.text
        and not result.text.endswith("\n")
    ):
        sys.stdout.write("\n")
        sys.stdout.flush()

    return 0 if (result is not None and result.ok) else 1

# Non-Blocking Auto-Compact Plan

Automatic context compaction that runs in the background while the agent keeps working.

## Design Principles

1. Agent never blocks waiting for compaction
2. No messages lost during compaction
3. Compacted context replaces raw context atomically
4. Session history (persistent store) keeps everything forever
5. UI (TUI/frontend) optionally hides pre-compact messages

## The Two-Zone Model

```
Context Window:
  [System Prompt]
  [Compact Zone: messages 1..K]     <- will be summarized
  [Live Zone: messages K+1..N]      <- untouched, keeps growing
  [Current LLM generation]

During compaction:
  - Compact Zone is snapshot'd (deep copy) and sent to summarizer
  - Live Zone keeps receiving new messages normally
  - Agent runs on FULL context (both zones) during compaction
  - When summary is ready, Compact Zone is replaced with summary
  - Live Zone becomes the new "recent" context
```

## Trigger Conditions

Auto-compact fires when context approaches the limit:

```python
# In controller, after each LLM call:
context_usage = current_tokens / max_context_tokens
if context_usage >= compact_threshold:  # default 0.80
    trigger_compact()
```

Configurable:
```yaml
controller:
  max_context_chars: 100000
  compact_threshold: 0.80      # trigger at 80% usage
  compact_target: 0.40         # aim for 40% after compact
```

## Compaction Pipeline (Gentle to Aggressive)

Inspired by Microsoft Semantic Kernel's composable strategy approach.

### Stage 1: Tool Result Collapse (no LLM, instant)

Replace old tool results deep in history with compact summaries:

```
Before: [bash] ls -la src/
        total 48
        drwxr-xr-x  6 user group  192 Mar 20 10:00 .
        drwxr-xr-x  3 user group   96 Mar 20 09:55 ..
        -rw-r--r--  1 user group 1234 Mar 20 10:00 main.py
        -rw-r--r--  1 user group  567 Mar 20 09:58 config.py
        ... (40 more lines)

After:  [bash] ls -la src/ -> 42 entries (main.py, config.py, ...)
```

Rules:
- Only collapse tool results older than N turns
- Keep the tool name + args + exit code
- Summarize output to first line + count
- No LLM needed, pure string processing

JetBrains research shows this alone achieves 52% cost reduction while improving solve rates by 2.6% (less noise = better decisions).

### Stage 2: LLM Summarization (background, async)

If stage 1 doesn't free enough space, run full summarization.

**The Snapshot-Background-Splice Flow:**

```python
async def _run_compact(self):
    # 1. Mark boundary
    boundary_idx = len(self.conversation.messages) - self.keep_recent

    # 2. Snapshot compact zone
    compact_messages = self.conversation.messages[:boundary_idx]

    # 3. Launch background task
    task = asyncio.create_task(self._summarize(compact_messages))

    # 4. Agent continues normally (full context still available)
    # ... new messages arrive, tools run, triggers fire ...

    # 5. When summary is ready, atomic splice
    summary = await task
    self.conversation.messages = [
        self.conversation.messages[0],  # system prompt
        {"role": "assistant", "content": summary},  # compact summary
        *self.conversation.messages[boundary_idx:],  # live zone (untouched)
    ]
```

**Handling messages during compaction:**

New messages that arrive during compaction go into the live zone (after `boundary_idx`). They are NEVER touched by the compaction. When the splice happens, the live zone is preserved in full.

**In-flight tool calls:**

If a tool was dispatched before the boundary but returns after compaction completes, its result goes into the live zone (it's a new message). The compact summary already captured the tool dispatch; the result is new information.

### Stage 3: Emergency Truncation (last resort)

If the LLM call for summarization itself fails (context too long for the summarizer), fall back to simple truncation:
- Keep system prompt + last N messages
- Log a warning
- This is the "circuit breaker" that prevents deadlock

## Summary Format

### Structured Summary (Factory's Anchored Approach)

Don't generate freeform prose. Use structured sections:

```markdown
## Session Summary (messages 1-45)

### Current Goal
Fix the authentication middleware bug in src/auth/middleware.py

### Key Decisions
- Chose to fix token validation rather than refactor (message #12)
- Decided to add unit tests before modifying code (message #18)

### Progress
- [DONE] Read and understood the auth module structure
- [DONE] Identified the bug: token expiry check uses wrong timezone
- [IN PROGRESS] Writing the fix
- [PENDING] Run test suite after fix

### Files Modified
- src/auth/middleware.py (line 42: timezone fix)
- tests/test_auth.py (new test added)

### Key Facts
- Bug affects token validation for users in non-UTC timezones
- 47 existing tests, all currently passing
- The fix is a one-line change but needs test coverage

### Keywords
auth, middleware, token, timezone, validation, UTC, expiry

### Key Sentences
- "The issue is on line 42 where datetime.now() should be datetime.utcnow()"
- "All 47 tests pass after the fix"
- "The user wants full test coverage before merging"

### Search Hint
For specific tool outputs, file contents, or error messages from this
period, use search_memory to query the session history.
```

### Why This Format

1. **Structured sections** prevent information drift (Factory scored 3.70/5 vs 3.44 Anthropic, 3.35 OpenAI)
2. **Keywords list** supports FTS5 search without re-reading the summary
3. **Key sentences** preserve exact quotes that abstractive summaries might paraphrase
4. **Search hint** teaches the agent to use memory tools for details
5. **Message numbers** provide temporal anchoring

## Summarization Prompt

```
You are summarizing a conversation between an AI agent and a user (or between agents in a team).

Create a structured summary with these sections:

### Current Goal
What is the agent currently trying to achieve?

### Key Decisions
What important choices were made, and why? Include message numbers.

### Progress
List completed, in-progress, and pending tasks.

### Files Modified
List files that were read, written, or edited.

### Key Facts
Important details that the agent needs to remember.

### Keywords
Comma-separated list of important terms for keyword search.

### Key Sentences
Exact quotes from the conversation that should be preserved.

### Search Hint
Note what types of information can be found by searching the full history.

Rules:
- Preserve decision rationale ("X because Y", not just "decided X")
- Keep exact file paths, line numbers, error codes verbatim
- Note the message number range this summary covers
- Use relative temporal markers ("early in session", "after fixing X")
- Do NOT include raw tool output (it's searchable in history)
- Focus on what the agent needs to continue working, not a narrative
```

## Incremental Compaction (Anchored Approach)

Don't re-summarize everything each time. Only summarize newly-evicted spans:

```
Round 1: Messages 1-45 compacted to Summary_A
Round 2: Messages 46-90 compacted to Summary_B
         Merge Summary_A + Summary_B into Summary_AB

Context after Round 2:
  [System Prompt]
  [Summary_AB]              <- merged summary
  [Messages 91-current]     <- raw recent messages
```

The merge step uses an LLM call that takes both summaries and produces a unified one. This is cheaper than re-reading all original messages.

## Session Store Integration

### What Gets Stored

The compact summary is saved as a special event in the session store:

```python
store.append_event(agent_name, "compact_summary", {
    "summary": structured_summary_text,
    "covers_messages": [1, 45],
    "keywords": ["auth", "middleware", ...],
    "timestamp": time.time(),
})
```

### Resume Behavior

On resume:
1. Load the most recent `compact_summary` event
2. Load raw messages AFTER the summary's `covers_messages` range
3. Inject: system prompt + summary + raw recent messages
4. Agent continues with compact context (not the full history)

The full history is still in the session store for search. Only the context window uses the compact version.

### UI Behavior

**TUI**: Show everything (both compacted and new messages). The summary appears as a system message: "Context compacted (messages 1-45)". User can scroll back to see historical widgets.

**Frontend**: Same default. Optional toggle: "Show only post-compact messages" hides the history accordion.

## Configuration

```yaml
controller:
  max_context_chars: 100000
  compact_threshold: 0.80       # trigger at 80% usage
  compact_target: 0.40          # aim for 40% after compact
  compact_keep_recent: 10       # keep last 10 turns in raw form
  compact_strategy: pipeline    # "pipeline" (stages 1-3), "summarize" (skip stage 1), "truncate" (stage 3 only)
  compact_model: null           # LLM for summarization (null = use agent's own model)
```

## Research Sources

- **Factory.ai**: Anchored iterative summarization scores highest (3.70/5). Structured sections critical.
- **JetBrains**: Tool result masking outperforms full summarization for SWE tasks (52% cost reduction).
- **Microsoft Semantic Kernel**: Pipeline of gentle-to-aggressive strategies.
- **Claude API**: `pause_after_compaction` pattern for injecting context after compact.
- **OpenAI**: Server-side compaction with opaque compression (99.3% ratio).
- **MemGPT/Letta**: Agent self-manages memory tiers. Sleep-time compute for async refinement.
- **ACON paper**: Failure-driven guideline optimization improves compaction quality 26-54%.
- **BM25 for agent self-search**: Keyword search works well because agent queries and content share vocabulary.

## Implementation Phases

### Phase 1: Tool result collapse (no LLM)
- Collapse old tool results to compact summaries
- Trigger on context threshold
- No background task needed (instant)

### Phase 2: Background summarization
- Snapshot + background task + atomic splice
- Structured summary format
- Incremental (anchored) approach

### Phase 3: Session store integration
- Save compact summaries as events
- Resume loads compact summary + recent messages
- UI shows compaction boundary

### Phase 4: Search integration
- Compact summary includes search hint
- Agent uses search_memory for details
- Keywords from summary support FTS5 search

# Configuration Reference

Complete reference for agent configuration (`config.yaml`).

## Agent Configuration

KohakuTerrarium supports YAML, JSON, and TOML configuration formats. YAML is recommended.

### Environment Variable Interpolation

Use `${VAR:default}` syntax for environment variables:

```yaml
controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"  # Uses env var or default
  api_key_env: OPENROUTER_API_KEY                             # Reads from this env var
```

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent identifier |
| `version` | string | No | Version string |
| `session_key` | string | No | Session key for shared state (default: agent name). Agents with the same key share channels, scratchpad, and TUI state |
| `controller` | object | Yes | LLM configuration |
| `system_prompt_file` | string | No | Path to system prompt markdown |
| `input` | object | No | Input module configuration |
| `output` | object | No | Output module configuration |
| `tools` | list | No | Tool configurations |
| `subagents` | list | No | Sub-agent configurations |
| `triggers` | list | No | Trigger configurations |
| `memory` | object | No | Memory system configuration |
| `startup_trigger` | object | No | Event fired on agent start |

### Controller Configuration

```yaml
# Codex OAuth (uses ChatGPT subscription)
controller:
  model: gpt-5.4
  auth_mode: codex-oauth
  tool_format: native

# OpenRouter / OpenAI-compatible
controller:
  model: "google/gemini-3-flash-preview"
  temperature: 0.7
  max_tokens: 4096
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  max_messages: 100
  max_context_chars: 100000
  ephemeral: false
  include_tools_in_prompt: true
  include_hints_in_prompt: true
  skill_mode: "dynamic"
  tool_format: bracket       # "bracket", "xml", "native", or custom dict
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | Required | Model identifier |
| `auth_mode` | string | None | Authentication mode: `codex-oauth` for ChatGPT subscription |
| `temperature` | float | 0.7 | Sampling temperature |
| `max_tokens` | int | 4096 | Max tokens to generate |
| `api_key_env` | string | Required* | Env var containing API key (*not needed with codex-oauth) |
| `base_url` | string | OpenAI URL | API endpoint |
| `max_messages` | int | 0 (unlimited) | Max conversation messages |
| `max_context_chars` | int | 0 (unlimited) | Max context characters |
| `ephemeral` | bool | false | Clear conversation after each turn |
| `include_tools_in_prompt` | bool | true | Include tool list |
| `include_hints_in_prompt` | bool | true | Include framework hints |
| `skill_mode` | string | "dynamic" | "dynamic" (use info command) or "static" (all docs in prompt) |
| `tool_format` | string or dict | "bracket" | Tool call format. See [Tool Formats](../concepts/tool-formats.md) |

### Input Configuration

```yaml
# CLI input (builtin)
input:
  type: cli
  prompt: "> "

# TUI input (builtin)
input:
  type: tui
  prompt: "You: "
  session_key: my_agent     # Optional: override session key

# None input (trigger-only agents)
input:
  type: none

# Custom input
input:
  type: custom
  module: ./custom/my_input.py
  class: MyInputModule
  my_option: value          # Additional fields passed to constructor
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "cli", "tui", "none", or "custom" |
| `module` | string | For custom | Path to module |
| `class` | string | For custom | Class name |
| `prompt` | string | For CLI/TUI | Input prompt string |
| `session_key` | string | For TUI | Override session key for TUI session |

### Output Configuration

```yaml
# Basic output
output:
  type: stdout
  controller_direct: true

# TUI output
output:
  type: tui
  controller_direct: true
  session_key: my_agent

# With named outputs
output:
  type: stdout
  named_outputs:
    discord:
      type: custom
      module: ./custom/discord_output.py
      class: DiscordOutput
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "stdout", "tui", or "custom" |
| `controller_direct` | bool | No | Controller output to default |
| `named_outputs` | object | No | Named output targets |

### Tools Configuration

```yaml
tools:
  # Builtin tools
  - name: bash
    type: builtin
  - name: read
    type: builtin

  # Custom tools
  - name: my_tool
    type: custom
    module: ./custom/my_tool.py
    class: MyTool
    timeout: 30
```

**Available built-in tools (26 total):**

**General tools (18):**

| Name | Description | Name | Description |
|------|-------------|------|-------------|
| `bash` | Execute shell commands | `think` | Extended reasoning step |
| `python` | Execute Python code | `scratchpad` | Session key-value memory |
| `read` | Read file contents | `send_message` | Send to named channel |
| `write` | Create/overwrite files | `wait_channel` | Wait for channel message |
| `edit` | Search-replace in files | `http` | Make HTTP requests |
| `glob` | Find files by pattern | `ask_user` | Prompt user for input |
| `grep` | Regex search in files | `json_read` | Query JSON files |
| `tree` | Directory structure | `json_write` | Modify JSON files |
| `info` | Load tool/sub-agent docs | `list_triggers` | Show active triggers |

**Terrarium management tools (8):** Used by the `root` creature for managing terrariums.

| Name | Description |
|------|-------------|
| `terrarium_create` | Create and start a terrarium |
| `terrarium_status` | Get terrarium status |
| `terrarium_stop` | Stop a running terrarium |
| `terrarium_send` | Send a message to a terrarium channel |
| `terrarium_observe` | Observe terrarium channel traffic |
| `terrarium_history` | Get channel message history |
| `creature_start` | Start a creature in a terrarium |
| `creature_stop` | Stop a creature in a terrarium |

### Sub-Agents Configuration

```yaml
subagents:
  # Builtin
  - name: explore
    type: builtin

  # Custom
  - name: output
    type: custom
    description: Generate responses
    prompt_file: prompts/output.md
    tools: []
    can_modify: false
    max_turns: 5
    timeout: 60
    interactive: false
    output_to: controller
```

**Available built-in sub-agents:**

| Name | Description | Tools |
|------|-------------|-------|
| `explore` | Search and analyze codebase | glob, grep, read |
| `plan` | Create implementation plans | glob, grep, read |
| `worker` | Implement changes | read, write, edit, bash, glob, grep |
| `critic` | Review and critique | read, glob, grep |
| `summarize` | Condense content | (none) |
| `research` | Web + file research | http, read, glob, grep |
| `coordinator` | Multi-agent via channels | send_message, wait_channel |
| `memory_read` | Retrieve from memory | read, glob |
| `memory_write` | Store to memory | write, read |
| `response` | Generate user responses | (none) |

**Sub-agent fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Required | Sub-agent identifier |
| `type` | string | Required | "builtin" or "custom" |
| `description` | string | "" | One-line description |
| `tools` | list | [] | Allowed tool names |
| `system_prompt` | string | "" | Inline system prompt |
| `prompt_file` | string | None | Path to prompt file |
| `can_modify` | bool | false | Allow write/edit tools |
| `stateless` | bool | true | No persistent state |
| `interactive` | bool | false | Long-lived with context updates |
| `context_mode` | string | "interrupt_restart" | How to handle updates |
| `output_to` | string | "controller" | "controller" or "external" |
| `output_module` | string | None | Output module name |
| `return_as_context` | bool | false | Return output to parent |
| `max_turns` | int | 10 | Max conversation turns |
| `timeout` | float | 300.0 | Max execution time |
| `model` | string | None | Override LLM model |
| `temperature` | float | None | Override temperature |
| `memory_path` | string | None | Memory folder path |

**Context update modes:** `interrupt_restart` (stop, start new), `queue_append` (queue, process after), `flush_replace` (flush, replace immediately).

### Triggers Configuration

```yaml
triggers:
  - type: custom
    module: ./custom/idle_trigger.py
    class: IdleTrigger
    prompt: "The chat has been quiet."
    min_idle_seconds: 300
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | "custom" (builtins coming) |
| `module` | string | Yes | Path to module |
| `class` | string | Yes | Class name |
| `prompt` | string | No | Default prompt for events |

### Memory Configuration

```yaml
memory:
  path: ./memory
  init_files:
    - character.md       # Read-only
    - rules.md
  writable_files:
    - context.md         # Agent can modify
    - facts.md
```

### Startup Trigger

```yaml
startup_trigger:
  prompt: "Agent starting. Initialize your state."
```

### Agent Folder Structure

```
examples/agent-apps/my_agent/
+-- config.yaml              # Main configuration
+-- prompts/
|   +-- system.md            # System prompt
|   +-- output.md            # Output sub-agent prompt
|   +-- tools/               # Tool documentation overrides
|       +-- bash.md
+-- memory/
|   +-- character.md
|   +-- context.md
+-- custom/
    +-- my_input.py
    +-- my_tool.py
    +-- my_trigger.py
```

---

For terrarium configuration, see [Terrariums](terrariums.md).

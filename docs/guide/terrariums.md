# Terrariums

This guide covers how to configure and run multi-agent terrariums. For the conceptual model (creature vs terrarium vs root agent, vertical vs horizontal composition), see [Concepts: Terrariums](../concepts/terrariums.md).

## What a Terrarium Does

A terrarium is a pure wiring layer. It loads standalone agent configs as creatures, creates channels between them, injects channel triggers, and manages lifecycle. The terrarium itself has no LLM and makes no decisions.

Creatures inside a terrarium communicate through channels. Each creature is an opaque, self-contained agent that does not know it is inside a terrarium.

## Configuration Format

### File Location

The runtime looks for `terrarium.yaml` or `terrarium.yml` in the given path:

```python
from kohakuterrarium.terrarium import load_terrarium_config

config = load_terrarium_config("examples/terrariums/novel_terrarium/")
config = load_terrarium_config("examples/terrariums/novel_terrarium/terrarium.yaml")
```

### Full YAML Format

```yaml
terrarium:
  name: <string>                    # Terrarium name (default: "terrarium")

  creatures:
    - name: <string>                # Required. Unique creature name.
      config: <path>                # Required. Path to agent config folder (relative to this file).
      channels:
        listen: [<channel_names>]   # Channels this creature receives messages from.
        can_send: [<channel_names>] # Channels this creature is allowed to send to.
      output_log: <bool>            # Capture LLM output to a ring buffer (default: false).
      output_log_size: <int>        # Ring buffer size when output_log is true (default: 100).

  channels:
    <channel_name>:
      type: queue | broadcast       # Channel type (default: queue).
      description: <string>         # Human-readable description, shown in system prompts.

  interface:
    type: cli | web | mcp | none    # Interface type for human interaction.
    observe: [<channel_names>]      # Channels the interface can read.
    inject_to: [<channel_names>]    # Channels the interface can write to.
```

### Creatures Section

Creature config supports two approaches:
- **`config`**: Path to agent config folder (relative to terrarium YAML)
- **`base_config`**: Reference to a creature template (e.g., `creatures/swe`) with inline overrides

When using `base_config`, the creature inherits tools, sub-agents, and system prompts from the referenced creature, and the terrarium YAML can specify overrides inline (model, temperature, etc.).

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | | Unique name for this creature instance |
| `config` | path | Yes* | | Path to agent config folder, relative to terrarium YAML |
| `base_config` | string | Yes* | | Creature template to inherit from (alternative to `config`) |
| `channels.listen` | list[string] | No | `[]` | Channel names to receive messages from |
| `channels.can_send` | list[string] | No | `[]` | Channel names allowed for sending |
| `output_log` | bool | No | `false` | Enable output log capture |
| `output_log_size` | int | No | `100` | Number of log entries to retain |

**Config path resolution:** Creature config paths resolve relative to the directory containing the terrarium YAML file.

**Reusing agent configs:** Multiple creatures can reference the same agent config with different names, creating separate instances from the same template.

### Channels Section

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `queue` | `queue` (point-to-point) or `broadcast` (all subscribers) |
| `description` | string | No | `""` | Shown in creature system prompts for channel awareness |

For channel semantics and implementation details, see [Concepts: Channels](../concepts/channels.md).

### Interface Section

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | No | `none` | Interface type: `cli`, `web`, `mcp`, `none` |
| `observe` | list[string] | No | `[]` | Channels the interface can read |
| `inject_to` | list[string] | No | `[]` | Channels the interface can write to |

### Environment Variables

Creature agent configs support environment variable interpolation:

```yaml
controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  api_key_env: OPENROUTER_API_KEY
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | API key for your LLM provider |
| `OPENROUTER_MODEL` | No | Model override (creature configs have defaults) |

Set these in a `.env` file at the project root, loaded by `python-dotenv`.

## Running a Terrarium

```bash
# Run with a root agent (user talks to root, root orchestrates the team)
kt terrarium run terrariums/swe_team/

# Run with session recording
kt terrarium run terrariums/swe_team/ --session

# Run with channel observation (specific channels)
kt terrarium run examples/terrariums/novel_terrarium/ --observe ideas outline
```

The `--observe` flag prints messages from the specified channels to the terminal as they flow, useful for debugging inter-creature communication.

## Complete Example

```yaml
terrarium:
  name: novel_writer

  creatures:
    - name: brainstorm
      config: ./creatures/brainstorm/
      channels:
        listen: [feedback]
        can_send: [ideas, team_chat]

    - name: planner
      config: ./creatures/planner/
      channels:
        listen: [ideas]
        can_send: [outline, team_chat]

    - name: writer
      config: ./creatures/writer/
      channels:
        listen: [outline]
        can_send: [draft, feedback, team_chat]

  channels:
    ideas:      { type: queue, description: "Raw ideas from brainstorm to planner" }
    outline:    { type: queue, description: "Chapter outlines from planner to writer" }
    draft:      { type: queue, description: "Written chapters for review" }
    feedback:   { type: queue, description: "Feedback from writer back to brainstorm" }
    team_chat:  { type: broadcast, description: "Team-wide status updates" }

  interface:
    type: cli
    observe: [ideas, outline, draft, feedback, team_chat]
    inject_to: [feedback]
```

This terrarium creates a three-creature pipeline: brainstorm generates ideas, planner creates outlines, writer produces chapters. Feedback flows back to brainstorm, and `team_chat` is a broadcast channel visible to all creatures.

## Key Points

- **Input override**: The terrarium runtime overrides each creature's input to `NoneInput` regardless of what their config specifies. Creatures receive work through channel triggers, not direct user input.
- **Channel tools**: Creatures that participate in channels need `send_message` and/or `wait_channel` tools in their own `config.yaml`.
- **Startup triggers**: The runtime fires each creature's `startup_trigger` after all creatures are started, so channels are available from the beginning.
- **Communication pattern**: Creatures send messages via the `send_message` tool and receive them through channel triggers that fire `TriggerEvent`s into the creature's controller queue.

## Further Reading

- [Concepts: Terrariums](../concepts/terrariums.md) for the architecture and design rationale
- [Concepts: Channels](../concepts/channels.md) for channel types, semantics, and the observer pattern
- [Configuration Reference](configuration.md) for agent config fields (used by each creature)
- [Sessions](sessions.md) for terrarium session persistence and resume

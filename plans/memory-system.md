# Memory System Plan

Searchable agent memory using FTS5 + vector search over session history, with temporal awareness.

## Architecture Overview

```
Agent Context Window
  = Compacted summary (structured, key points)
  + Recent raw messages (last N turns)
  + Search results (on demand, via memory tools)

Session Store (.kohakutr)
  = Full event log (every message, tool call, result)
  + FTS5 index (keyword search, BM25 scoring)
  + Vector index (semantic search, sqlite-vec)
  + Extracted facts/entities (LLM-extracted, structured)
```

The agent gets a compact summary in context, recent messages in full, and can search the full history via tools when it needs specific details.

## Embedding Model Options

### Tier 1: Zero-dependency (default, bundle with package)

**Model2Vec potion-base-8M**
- Size: ~8 MB model file
- Dimensions: 256
- Dependencies: numpy only (no PyTorch, no ONNX)
- Speed: microsecond-level inference (static embeddings, just mean pooling)
- Quality: lower than transformer models but beats GloVe/BPEmb
- 500x faster than sentence-transformers on CPU

Best as default because: zero setup cost, tiny bundle, combined with FTS5 it's "good enough" for memory retrieval. The FTS5 keyword search handles exact matches (function names, error codes), vectors handle conceptual similarity.

### Tier 2: Local quality (optional dep)

**bge-small-en-v1.5 + ONNX int8**
- Size: ~33 MB (ONNX quantized)
- Dimensions: 384
- Dependencies: onnxruntime (~50 MB)
- Speed: 10-15 ms per query on CPU
- Quality: 84.7% top-5 retrieval accuracy (MTEB)

Best when: user wants better semantic search and can tolerate the onnxruntime dependency. Install via `pip install kohakuterrarium[embeddings]`.

### Tier 3: Local premium (optional)

**nomic-embed-text-v1.5 + ONNX**
- Size: ~200 MB
- Dimensions: 768 (Matryoshka: reducible to 256)
- Context: 8192 tokens (handles long code chunks)
- Quality: 86.2% top-5 (best fully open model)

Best when: code-heavy use case needs long context embeddings.

### Tier 4: API (optional)

| Provider | Model | Price/MTok | Dimensions | Context | Best for |
|----------|-------|------------|------------|---------|----------|
| OpenAI | text-embedding-3-small | $0.02 | 1,536 | 8K | General (best value) |
| Voyage AI | voyage-code-3 | $0.18 | 1,024 | 32K | Code (13.8% better than OpenAI) |
| Mistral | mistral-embed | $0.01 | 1,024 | 8K | Cheapest |
| Google | gemini-embedding-001 | Free tier | 3,072 | 8K | Free |

Configure in agent config:
```yaml
memory:
  embedding: api
  embedding_model: text-embedding-3-small
  embedding_api_key_env: OPENAI_API_KEY
```

## Storage: sqlite-vec + FTS5 (already available)

KohakuVault already provides both:
- **VectorKVault**: sqlite-vec with cosine metric, f32/int8/bit types
- **TextVault**: FTS5 with BM25 scoring

Performance (sqlite-vec brute-force KNN):
- 384-dim, 100K vectors: ~15 ms query time
- 384-dim, 10K vectors: ~2 ms query time
- Agent memory typically <10K entries, so queries are sub-5ms

### Hybrid Search (FTS5 + Vector with Reciprocal Rank Fusion)

```python
def hybrid_search(query: str, query_embedding: list[float], k: int = 10):
    # BM25 keyword results
    fts_results = text_vault.search(query, k=20)

    # Semantic vector results
    vec_results = vector_vault.search(query_embedding, k=20)

    # Reciprocal Rank Fusion
    scores = {}
    for rank, (doc_id, _) in enumerate(fts_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (60 + rank)
    for rank, (doc_id, _, _) in enumerate(vec_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (60 + rank)

    return sorted(scores.items(), key=lambda x: -x[1])[:k]
```

Hybrid improves recall 15-30% over either method alone, especially for code where you need both exact identifier matching AND conceptual similarity.

## Message Numbering / Temporal Context

### Design

Every event in the session store already has a `ts` (timestamp) field. Add a sequential `seq` (message number) that's human-readable and monotonically increasing:

```python
# In SessionStore
def append_event(self, agent, event_type, data):
    seq = self._next_event_seq(agent)
    data["seq"] = seq
    data["ts"] = time.time()
    # ... store as before
```

### Temporal Markers in Summaries

When compacting, include temporal context:
- "Messages 1-45 (session start to first task completion)"
- "Messages 46-120 (auth bug investigation and fix)"
- Use relative markers: "early in session", "after the first fix", "most recently"

### Agent Temporal Awareness

The memory search tool should return results with temporal info:
```
[Memory search: "auth bug"]
Result 1 (message #23, 45 minutes ago): Found the auth bug on line 42...
Result 2 (message #67, 12 minutes ago): Fixed and tested, all 47 tests pass...
```

This lets the agent understand recency without consuming context tokens.

## Memory Tools (Builtins)

### search_memory

Search session history using keyword or semantic query.

```json
{
  "query": "auth bug fix",
  "mode": "hybrid",     // "keyword", "semantic", or "hybrid"
  "limit": 5,
  "agent": "root"       // optional, search specific agent's history
}
```

Returns results with message number, timestamp, content preview.

### memory_summary

Get the current compacted summary (without searching).

### memory_facts

List extracted key facts/entities from the session. Useful for quick context refresh.

## Existing Framework Comparison

| System | Memory Model | Key Insight |
|--------|-------------|-------------|
| **Mem0** | Extract-then-update pipeline | LLM extracts candidate memories, evaluates against existing (ADD/UPDATE/DELETE) |
| **MemGPT/Letta** | OS-inspired tiered memory | Agent self-manages memory via tool calls (core/recall/archival) |
| **Claude Code** | Static files + auto-memory | Relies on long context window. CLAUDE.md for persistent instructions. |
| **Cursor** | Semantic code indexing | Chunks files, embeds, searches. Never puts full codebase in context. |

### Our Approach

Closest to Letta's model, adapted for our existing infrastructure:
- **Working memory**: Current conversation (controller manages)
- **Session memory**: FTS5 + vector indexed in the .kohakutr file
- **Compacted summaries**: Structured summaries with keyword lists (stored in state table)
- **Search tools**: Agent can search session history when unsure

Key difference from Letta: we DON'T require the agent to manage its own memory via tool calls. The system handles compaction automatically. The agent only uses `search_memory` when it needs specific details not in the current context.

## Implementation Plan

### Phase 1: Memory search tools
- Add `search_memory` builtin tool (FTS5 search over session events)
- Add message numbering (`seq` field) to all events
- `search_memory` returns results with seq + relative time

### Phase 2: Vector search
- Add embedding infrastructure (Model2Vec as default, configurable)
- Index text events as vectors in VectorKVault table
- Add `mode: "semantic"` and `mode: "hybrid"` to search_memory

### Phase 3: Extracted facts
- After each processing cycle, extract key facts via lightweight LLM call
- Store as structured entries (entity, relation, value, source_seq)
- `memory_facts` tool lists current facts

### Phase 4: Temporal awareness
- Compaction summaries include temporal markers
- Search results show "N messages ago" / "X minutes ago"
- Agent prompt hint: "use search_memory to retrieve specific details"

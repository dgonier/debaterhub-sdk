# debaterhub-sdk

Python SDK for IPDA debates via LiveKit. Supports **human-vs-AI** and **AI-vs-AI** modes.

- 📖 **[How-To Guide](docs/how-to.md)** — task-oriented recipes ("How do I…")
- 📖 **[Integration Modes](docs/modes.md)** — Token-Only, Server-Managed, AI-vs-AI
- 📖 **[Events Reference](docs/events.md)** — all 15 event types with handler snippets
- 📖 **[Architecture](docs/architecture.md)** — module layout, data flow, IPDA format

## Install

```bash
# From GitHub
pip install git+https://github.com/dgonier/debaterhub-sdk.git

# From PyPI (when published)
pip install debaterhub-sdk

# Editable (local development)
git clone https://github.com/dgonier/debaterhub-sdk.git
cd debaterhub-sdk
pip install -e ".[dev]"
```

## Quick Start

### Mode 1: Token-Only (frontend connects to LiveKit directly)

```python
from debaterhub import DebateClient, DebateConfig

client = DebateClient("wss://lk.example.com", "api-key", "api-secret")
details = await client.create_session(DebateConfig(topic="AI benefits society"))
# → details.server_url, details.room_name, details.participant_token
# Pass these to your frontend LiveKit SDK
await client.close()
```

### Mode 2: Server-Managed — Human vs AI

```python
from debaterhub import DebateClient, DebateConfig, DebateEventHandler

class MyHandler(DebateEventHandler):
    async def on_debate_ready(self, event):
        print(f"Debate ready: {event.topic}, side: {event.human_side}")

    async def on_turn_signal(self, event):
        print(f"Turn: {event.speech_type} ({event.speaker})")

    async def on_speech_text(self, event):
        print(f"[{event.speech_type}] {event.text[:80]}...")

    async def on_judge_result(self, event):
        print(f"Winner: {event.winner} ({event.margin})")

client = DebateClient("wss://lk.example.com", "api-key", "api-secret")
config = DebateConfig(topic="AI benefits society", human_side="aff")
session = await client.create_managed_session(config, MyHandler())

# Send actions
await session.submit_speech("AC", "My constructive argument text...")
await session.submit_cx_question("Can you clarify your second point?")
await session.request_coaching("1AR")
await session.request_evidence("economic impact of AI")

# Check state
print(session.tracker.current_speech)   # "NC"
print(session.tracker.is_human_turn)    # False
print(session.tracker.phase)            # "active"

await session.disconnect()
await client.close()
```

### Mode 3: AI vs AI (autonomous debates)

Both sides are LLM-generated — you're an observer. See [docs/modes.md](docs/modes.md#ai-vs-ai-autonomous-debates) for a full example.

```python
from debaterhub import DebateClient, DebateConfig, DebateEventHandler

class Observer(DebateEventHandler):
    async def on_speech_text(self, event):
        print(f"[{event.speech_type}] {event.word_count} words")
    async def on_judge_result(self, event):
        print(f"Winner: {event.winner}")

client = DebateClient("wss://lk.example.com", "key", "secret")
config = DebateConfig(
    topic="UBI should replace welfare",
    debate_mode="ai_ai",          # ← the key difference
    coaching_enabled=False,
    evidence_enabled=False,
)
session = await client.create_managed_session(config, Observer())

# No submit_* calls — the agent drives both sides
import asyncio
while not session.tracker.is_complete:
    await asyncio.sleep(5)

await session.disconnect()
await client.close()
```

## Debate Formats

The SDK supports three debate formats via `DebateConfig.format`:

| Format | Id | Speeches | Use case |
|--------|----|----------|----------|
| IPDA | `"ipda"` (default) | 7 | General-purpose, balanced time |
| Lincoln-Douglas | `"ld"` | 7 | Philosophical/value debate |
| Public Forum | `"pf"` | 11 | Lay-judge, topical, evidence-driven |

```python
from debaterhub import DebateClient, DebateConfig

# Lincoln-Douglas
config = DebateConfig(
    topic="Resolved: Governments have an obligation to mitigate climate change over economic growth.",
    format="ld",
    human_side="aff",
)

# Public Forum (with coin flip)
config = DebateConfig(
    topic="Resolved: Social media does more harm than good.",
    format="pf",
    human_side="neg",
    pf_first_speaker="aff",   # coin-flip result
)
```

See [docs/formats.md](docs/formats.md) for speech orders, timings, and format-specific tips.

> **Beta notice:** LD and PF use the same model weights as IPDA (no format-specific fine-tune yet). Quality is acceptable for practice debates but may lag native IPDA quality.

## Configuration

### `DebateClientConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `livekit_url` | `str` | *required* | `wss://` URL of the LiveKit server |
| `livekit_api_key` | `str` | *required* | LiveKit API key |
| `livekit_api_secret` | `str` | *required* | LiveKit API secret |
| `agent_name` | `str` | `"human-debate"` | Name of the deployed LiveKit agent |
| `warmup_url` | `str \| None` | `None` | Optional Modal warmup endpoint URL |

```python
from debaterhub import DebateClient, DebateClientConfig

config = DebateClientConfig(
    livekit_url="wss://lk.example.com",
    livekit_api_key="...",
    livekit_api_secret="...",
)
client = DebateClient.from_config(config)
```

### `DebateConfig`

Per-debate settings passed to the agent via dispatch metadata.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `topic` | `str` | *required* | Debate resolution |
| `debate_mode` | `str` | `"ai_human"` | `"ai_human"` (one side human) or `"ai_ai"` (both sides AI) |
| `human_side` | `str` | `"aff"` | `"aff"` or `"neg"` — ignored in `ai_ai` mode |
| `format` | `str` | `"ipda"` | One of `"ipda"`, `"ld"`, `"pf"` |
| `pf_first_speaker` | `str \| None` | `None` | PF only: `"aff"` or `"neg"` (coin-flip result) |
| `coaching_enabled` | `bool` | `True` | Enable coaching hints |
| `evidence_enabled` | `bool` | `True` | Enable evidence search |
| `enable_prep` | `bool` | `True` | Enable prep time |
| `enable_flow_study` | `bool` | `True` | Enable flow tracking |
| `enable_scoring` | `bool` | `True` | Enable speech scoring |
| `ai_case_mode` | `str \| None` | `None` | `"generate"` or `"reuse"` |
| `ai_reuse_case_id` | `str \| None` | `None` | Case ID to reuse |
| `ai_reuse_mode` | `str \| None` | `None` | `"blind"` or `"select"` |
| `human_speech_text` | `str \| None` | `None` | Pre-supplied human speech text |
| `prep_config` | `dict \| None` | `None` | Override prep pipeline breadth (keys: `values_per_side`, `beliefs_per_value`, `research_per_belief`, `arguments_per_leaf`, `max_depth`). See [Shrinking Prep Time](#shrinking-prep-time). |

## Events

All events extend `DebateEvent` with a `type` field and `raw` dict containing the full payload.

| Event Class | `type` string | Key Fields |
|-------------|---------------|------------|
| `DebateInitializingEvent` | `debate_initializing` | `topic`, `human_side`, `message`, `estimated_seconds` |
| `DebateReadyEvent` | `debate_ready` | `topic`, `human_side`, `speech_order`, `speech_time_limits`, `evidence_cards`, `belief_tree_summary` |
| `TurnSignalEvent` | `turn_signal` | `speech_type`, `speaker`, `is_cx`, `time_limit`, `speech_index`, `total_speeches`, `status` |
| `SpeechTextEvent` | `speech_text` | `speech_type`, `text`, `word_count` |
| `SpeechProgressEvent` | `speech_progress` | `speech_type`, `stage`, `message` |
| `FlowUpdateEvent` | `flow_update` | `speech_type`, `flow` |
| `CoachingHintEvent` | `coaching_hint` | `for_speech`, `hints` |
| `SpeechScoredEvent` | `speech_scored` | `speech_type`, `score`, `feedback`, `dimensions` |
| `CXQuestionEvent` | `cx_question_server` | `question`, `turn_number`, `strategy` |
| `CXAnswerEvent` | `cx_answer_server` | `answer`, `question_ref` |
| `EvidenceResultEvent` | `evidence_result` | `query`, `cards`, `total_results` |
| `JudgingStartedEvent` | `judging_started` | `message`, `estimated_seconds` |
| `JudgeResultEvent` | `judge_result` | `winner`, `aff_score`, `neg_score`, `margin`, `decision`, `voting_issues`, `per_speech_feedback` |
| `ErrorEvent` | `error` | `message`, `code`, `recoverable` |
| `BeliefTreeEvent` | `belief_tree` | `tree` |

### Event Handler

Subclass `DebateEventHandler` and override any method:

```python
class DebateEventHandler:
    async def on_debate_initializing(self, event) -> None: ...
    async def on_debate_ready(self, event) -> None: ...
    async def on_turn_signal(self, event) -> None: ...
    async def on_speech_text(self, event) -> None: ...
    async def on_speech_progress(self, event) -> None: ...
    async def on_flow_update(self, event) -> None: ...
    async def on_coaching_hint(self, event) -> None: ...
    async def on_speech_scored(self, event) -> None: ...
    async def on_cx_question(self, event) -> None: ...
    async def on_cx_answer(self, event) -> None: ...
    async def on_evidence_result(self, event) -> None: ...
    async def on_judging_started(self, event) -> None: ...
    async def on_judge_result(self, event) -> None: ...
    async def on_error(self, event) -> None: ...
    async def on_belief_tree(self, event) -> None: ...
    async def on_unknown(self, event) -> None: ...
    async def on_disconnect(self, reason: str = "") -> None: ...
```

## State Tracking

`DebateTurnTracker` provides read-only properties updated automatically from `TurnSignalEvent`:

| Property | Type | Description |
|----------|------|-------------|
| `current_speech` | `str \| None` | Current speech type (e.g. `"AC"`, `"NC-CX"`) |
| `current_speaker` | `str \| None` | `"human"` or `"ai"` |
| `speech_index` | `int` | 0-based index in speech order |
| `phase` | `str` | `"waiting"`, `"active"`, `"prep_time"`, or `"complete"` |
| `is_human_turn` | `bool` | Whether the human is currently active |
| `is_cx` | `bool` | Whether current speech is a CX period |
| `is_complete` | `bool` | Whether the debate has finished |
| `transcripts` | `dict[str, str]` | Speech type → transcript text |
| `completed_speeches` | `list[str]` | Speeches completed so far (in order) |

## Constants

```python
from debaterhub import IPDA_SPEECH_ORDER, SPEECH_TIME_LIMITS

IPDA_SPEECH_ORDER  # ["AC", "AC-CX", "NC", "NC-CX", "1AR", "NR", "2AR"]

SPEECH_TIME_LIMITS  # {"AC": 300, "AC-CX": 180, "NC": 360, "NC-CX": 180,
                    #  "1AR": 300, "NR": 300, "2AR": 180}
```

| Constant | Type | Description |
|----------|------|-------------|
| `IPDA_SPEECH_ORDER` | `list[str]` | 7-speech IPDA order |
| `SPEECH_TIME_LIMITS` | `dict[str, int]` | Seconds per speech |
| `AFF_SPEECHES` | `set[str]` | `{"AC", "1AR", "2AR"}` |
| `NEG_SPEECHES` | `set[str]` | `{"NC", "NR"}` |
| `AFF_ACTIVE` | `set[str]` | Speeches where AFF is active (speaking + CX questioning) |
| `NEG_ACTIVE` | `set[str]` | Speeches where NEG is active |
| `IS_CX_SPEECH` | `dict[str, bool]` | Whether each speech is a CX period |
| `SPEECH_SIDE` | `dict[str, str]` | Speech type → `"aff"` or `"neg"` |

## ManagedDebateSession Actions

Methods available on the session returned by `create_managed_session()`:

| Method | Description |
|--------|-------------|
| `submit_speech(speech_type, transcript, duration_seconds, word_count)` | Submit a completed human speech |
| `submit_cx_question(question, turn_number)` | Send a CX question |
| `submit_cx_answer(answer, question_ref)` | Send a CX answer |
| `end_cx(speech_type)` | Signal end of CX period |
| `skip_cx(speech_type)` | Skip a CX period entirely |
| `end_prep_time()` | Signal end of prep time |
| `request_coaching(for_speech)` | Request coaching hints |
| `request_evidence(query, limit)` | Search for evidence |
| `connect()` | Connect to the LiveKit room |
| `disconnect()` | Disconnect from the room |

## Verbose Logging (Diagnostics)

Opt-in structured logs for diagnosing a stuck or slow session.

```bash
# Shorthand — enables DEBUG level on the `debaterhub` logger
export DEBATERHUB_VERBOSE=1

# Or pick a specific level
export DEBATERHUB_LOG_LEVEL=INFO
```

When either env var is set, the SDK attaches a stream handler to the
`debaterhub` logger and prints **two layers** of trace:

- **`[EVENT]`** — one scannable line per inbound server event. Shows
  elapsed time since connect + event type + a short summary. Lets you
  read a session top-to-bottom and see exactly where prep stalled.

  ```
  15:09:29 [EVENT] [+   4.7s] debate_initializing — Kicking off remote belief prep…
  15:09:34 [EVENT] [+   9.2s] debate_initializing — [values] Generating values for: …
  15:09:35 [EVENT] [+  10.6s] debate_initializing — [values] Got 1 AFF / 1 NEG values
  15:11:42 [EVENT] [+ 134.4s] debate_initializing — [research] Got 4/5 NEG evidence …
  15:15:20 [EVENT] [+ 348.4s] debate_initializing — [clash] Detecting clashes: 1×1 args
  15:16:34 [EVENT] [+ 421.5s] debate_initializing — [persist] Persisting tree to Neo4j + Weaviate
  15:18:14 [EVENT] [+ 587.0s] debate_ready — Resolved: social media platforms should require …
  ```

- **`[LOG]`** — deeper framework chatter at DEBUG (raw frame dumps,
  parse errors, handler exceptions, connection lifecycle). Grep it out
  when you need the full picture: `grep LOG session.log`.

Default is silent — hosts with their own logging config are unaffected.

## Stall Detection

`create_managed_session()` accepts an `on_stall` callback that fires
when no server event has arrived for `stall_after_seconds` (default
120s). The SDK does **not** disconnect — your callback decides what
to do.

```python
async def on_stall(elapsed, silence, last_phase):
    print(f"STALL at {last_phase!r}: {silence:.0f}s silent, "
          f"session is {elapsed:.0f}s old")
    # ...notify user, log for debugging, trigger retry, etc.

session = await client.create_managed_session(
    config=config,
    handler=handler,
    on_stall=on_stall,
    stall_after_seconds=120,
)
```

Diagnostic properties available on the session:

| Property | Description |
|----------|-------------|
| `last_phase_message` | Most recent human-readable progress message (e.g. `"[beliefs] Generating NEG beliefs"`) |
| `seconds_since_last_event` | Silence duration — `inf` before connect |
| `seconds_since_connect` | Wall-clock time since the session connected |
| `event_count` | Total inbound server events observed |

## Shrinking Prep Time

Default prep runs the full research + argument breadth (~10-15min for
a cold topic). For smoke tests or time-sensitive flows, pass a
`prep_config` to shrink the tree:

```python
config = DebateConfig(
    topic="Resolved: AI does more good than harm",
    human_side="aff",
    prep_config={
        "values_per_side": 1,       # 1 value per side (default: 2)
        "beliefs_per_value": 1,     # 1 belief per value (default: 2)
        "research_per_belief": 1,   # 1 research hit per belief (default: 1)
        "arguments_per_leaf": 1,    # 1 argument per leaf (default: 1)
        "max_depth": 1,             # tree depth (default: 1)
    },
)
```

Minimal config completes in ~5-7 minutes and produces a usable (if
shallow) tree. Omit `prep_config` for production depth.

## Error Handling

```
DebatehubError (base)
├── ConfigValidationError    # Invalid config values
├── ConnectionError          # Failed to connect to LiveKit
├── DispatchError            # Failed to dispatch agent to room
├── WarmupError              # Agent warmup request failed
├── SessionNotConnectedError # Action on disconnected session
└── ProtocolError            # Malformed wire message
```

```python
from debaterhub import DebatehubError, ConnectionError, DispatchError

try:
    session = await client.create_managed_session(config, handler)
except ConnectionError:
    print("Could not connect to LiveKit")
except DispatchError:
    print("Agent dispatch failed")
except DebatehubError as e:
    print(f"SDK error: {e}")
```

## Documentation

- [How-To Guide](docs/how-to.md) — task-oriented "How do I…?" recipes
- [Integration Modes](docs/modes.md) — Mode 1, Mode 2, and AI-vs-AI with full examples
- [Events Reference](docs/events.md) — all 15 event types with handler snippets and lifecycle
- [Architecture](docs/architecture.md) — module layout, data flow, wire protocol, IPDA format
- [Reference FastAPI App](https://github.com/dgonier/debate-fastapi-reference) — working backend that uses this SDK

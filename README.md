# debaterhub-sdk

Python SDK for human-vs-AI IPDA debates via LiveKit.

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

### Mode 2: Server-Managed (backend receives events)

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
| `human_side` | `str` | `"aff"` | `"aff"` or `"neg"` |
| `format` | `str` | `"ipda"` | Debate format |
| `coaching_enabled` | `bool` | `True` | Enable coaching hints |
| `evidence_enabled` | `bool` | `True` | Enable evidence search |
| `enable_prep` | `bool` | `True` | Enable prep time |
| `enable_flow_study` | `bool` | `True` | Enable flow tracking |
| `enable_scoring` | `bool` | `True` | Enable speech scoring |
| `ai_case_mode` | `str \| None` | `None` | `"generate"` or `"reuse"` |
| `ai_reuse_case_id` | `str \| None` | `None` | Case ID to reuse |
| `ai_reuse_mode` | `str \| None` | `None` | `"blind"` or `"select"` |
| `human_speech_text` | `str \| None` | `None` | Pre-supplied human speech text |

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

- [Architecture](docs/architecture.md) — module layout, data flow, wire protocol, IPDA format
- [Integration Modes](docs/modes.md) — detailed Mode 1 and Mode 2 guides with full examples
- [Events Reference](docs/events.md) — all 15 event types with field descriptions and lifecycle
- [Reference FastAPI App](https://github.com/dgonier/debate-fastapi-reference) — working backend that uses this SDK

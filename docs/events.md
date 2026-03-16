# Events Reference

All events inherit from `DebateEvent` and are dispatched to `DebateEventHandler` callback methods.

## Event Lifecycle

A typical debate produces events in this order:

```
debate_initializing  →  Agent is setting up (belief tree, prep)
belief_tree          →  Belief tree structure ready
debate_ready         →  Debate is ready to begin
                         ┌──────────────────────────────┐
                         │  Per-speech cycle (×7):       │
turn_signal          →   │  Signals which speech is next │
speech_progress      →   │  AI generation stages         │
speech_text          →   │  Completed speech text        │
flow_update          →   │  Updated argument flow        │
coaching_hint        →   │  Hints for human (if enabled) │
speech_scored        →   │  Inline score (if enabled)    │
                         │                               │
                         │  CX periods:                  │
cx_question_server   →   │  AI asks/answers questions    │
cx_answer_server     →   │  AI asks/answers questions    │
                         │                               │
                         │  On demand:                   │
evidence_result      →   │  Evidence search results      │
                         └──────────────────────────────┘
judging_started      →  Final judging underway
judge_result         →  Winner, scores, feedback
error                →  (at any time if something goes wrong)
```

## Event Details

### `DebateInitializingEvent`

Sent when the debate agent starts setting up.

| Field | Type | Description |
|-------|------|-------------|
| `topic` | `str` | The debate resolution |
| `human_side` | `str` | `"aff"` or `"neg"` |
| `message` | `str` | Human-readable status message |
| `estimated_seconds` | `float` | Estimated setup time |

### `DebateReadyEvent`

Sent when prep is complete and the debate is about to begin.

| Field | Type | Description |
|-------|------|-------------|
| `topic` | `str` | The debate resolution |
| `human_side` | `str` | `"aff"` or `"neg"` |
| `speech_order` | `list[str]` | Ordered list of speech types |
| `speech_time_limits` | `dict[str, int]` | Speech type → seconds |
| `evidence_cards` | `list[dict]` | Pre-loaded evidence cards |
| `belief_tree_summary` | `str` | Summary of the belief tree |

### `TurnSignalEvent`

Signals the start of a new speech period.

| Field | Type | Description |
|-------|------|-------------|
| `speech_type` | `str` | e.g. `"AC"`, `"NC-CX"`, `"1AR"` |
| `speaker` | `str` | `"human"` or `"ai"` |
| `is_cx` | `bool` | Whether this is a CX period |
| `time_limit` | `int` | Seconds allowed |
| `speech_index` | `int` | 0-based position in speech order |
| `total_speeches` | `int` | Total speeches (7 for IPDA) |
| `status` | `str` | `"active"`, `"prep_time"`, `"complete"` |

### `SpeechTextEvent`

A completed speech (AI-generated or echoed back after human submission).

| Field | Type | Description |
|-------|------|-------------|
| `speech_type` | `str` | Which speech this is |
| `text` | `str` | Full speech transcript |
| `word_count` | `int` | Word count |

### `SpeechProgressEvent`

Intermediate progress updates during AI speech generation.

| Field | Type | Description |
|-------|------|-------------|
| `speech_type` | `str` | Which speech is being generated |
| `stage` | `str` | Pipeline stage (e.g. `"skeleton"`, `"evidence_select"`, `"generate"`) |
| `message` | `str` | Human-readable progress message |

### `FlowUpdateEvent`

Updated argument flow after a speech.

| Field | Type | Description |
|-------|------|-------------|
| `speech_type` | `str` | Speech that triggered the update |
| `flow` | `dict` | Flow structure (argument tracking) |

### `CoachingHintEvent`

Strategic coaching hints for the human debater.

| Field | Type | Description |
|-------|------|-------------|
| `for_speech` | `str` | Which upcoming speech these hints are for |
| `hints` | `list[dict]` | List of hint objects with strategy advice |

### `SpeechScoredEvent`

Inline scoring result for a completed speech.

| Field | Type | Description |
|-------|------|-------------|
| `speech_type` | `str` | Which speech was scored |
| `score` | `float` | Overall score (0.0–1.0) |
| `feedback` | `str` | Written feedback |
| `dimensions` | `list[dict]` | Per-dimension scores |

### `CXQuestionEvent`

A cross-examination question from the AI.

| Field | Type | Description |
|-------|------|-------------|
| `question` | `str` | The question text |
| `turn_number` | `int` | CX exchange number |
| `strategy` | `str` | Strategic objective of the question |

### `CXAnswerEvent`

A cross-examination answer from the AI.

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `str` | The answer text |
| `question_ref` | `str \| None` | Reference to the question being answered |

### `EvidenceResultEvent`

Results from an evidence search request.

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | The search query |
| `cards` | `list[dict]` | Evidence card objects |
| `total_results` | `int` | Total results found |

### `JudgingStartedEvent`

Signals that final judging has begun.

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | Status message |
| `estimated_seconds` | `float` | Estimated judging time |

### `JudgeResultEvent`

Final debate judgment.

| Field | Type | Description |
|-------|------|-------------|
| `winner` | `str` | `"aff"` or `"neg"` |
| `aff_score` | `float` | Affirmative total score |
| `neg_score` | `float` | Negative total score |
| `margin` | `str` | `"decisive"`, `"clear"`, `"close"`, `"split"` |
| `decision` | `str` | Written decision explanation |
| `voting_issues` | `list[str]` | Key voting issues identified |
| `per_speech_feedback` | `list[dict]` | Feedback per speech |

### `ErrorEvent`

An error occurred in the debate pipeline.

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | Error message |
| `code` | `str` | Error code (e.g. `"GENERATION_FAILED"`) |
| `recoverable` | `bool` | Whether the debate can continue |

### `BeliefTreeEvent`

The belief tree structure used for debate preparation.

| Field | Type | Description |
|-------|------|-------------|
| `tree` | `dict` | Full belief tree structure |


# TODO:
- figure out how to start debate if debate_prep is completed via the packages
- 
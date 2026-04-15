# Events Reference

All events inherit from `DebateEvent` and are dispatched to `DebateEventHandler` callback methods. Subclass the handler, override the `on_*` methods you care about, and pass an instance to `create_managed_session()`.

```python
from debaterhub import DebateEventHandler

class MyHandler(DebateEventHandler):
    async def on_debate_ready(self, event):
        print("ready:", event.topic)

    async def on_speech_text(self, event):
        print(f"[{event.speech_type}] {event.word_count} words")

    async def on_judge_result(self, event):
        print(f"winner: {event.winner}")
```

Any event you don't override is silently dropped — or routed to `on_unknown()` if you want a catch-all.

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

The tree has this shape:
```python
{
    "topic": "...",
    "beliefs": [
        {
            "id": "b1",
            "side": "aff",
            "label": "Contention 1: Poverty Reduction",
            "claim": "UBI reduces poverty",
            "arguments": [
                {
                    "id": "a1",
                    "claim": "...",
                    "warrant": "...",
                    "impact": "...",
                    "evidence": [
                        {"tag": "...", "fulltext": "...", "source": "...", "cite": "..."}
                    ],
                },
            ],
        },
    ],
}
```

## Handler snippets

Common patterns for handling each event type. Copy-paste into your `DebateEventHandler` subclass.

```python
class MyHandler(DebateEventHandler):
    async def on_debate_initializing(self, event):
        # Show a loading spinner with the topic
        self.ui.show_loading(event.topic, event.estimated_seconds)

    async def on_debate_ready(self, event):
        # Render the speech order timeline
        self.ui.render_timeline(event.speech_order, event.speech_time_limits)

    async def on_turn_signal(self, event):
        # Core UI update — who's up next
        if event.status == "active":
            self.ui.highlight_speech(event.speech_type, event.speaker)
        elif event.status == "prep_time":
            self.ui.show_prep_timer(event.time_limit)
        elif event.status == "complete":
            self.ui.mark_speech_done(event.speech_type)

    async def on_speech_progress(self, event):
        # Show generation stages so users know the agent is working
        self.ui.set_progress_label(f"{event.speech_type}: {event.stage}")

    async def on_speech_text(self, event):
        # Full speech arrived — render it
        self.ui.append_transcript(event.speech_type, event.text)
        self.store.save_speech(event.speech_type, event.text)

    async def on_coaching_hint(self, event):
        for hint in event.hints:
            self.ui.show_hint(hint)

    async def on_cx_question(self, event):
        # If the AI is asking, prompt the user for an answer.
        # If the human is asking, display what they just sent.
        self.ui.append_cx_question(event.question, event.strategy)

    async def on_cx_answer(self, event):
        self.ui.append_cx_answer(event.answer)

    async def on_speech_scored(self, event):
        self.ui.show_score(event.speech_type, event.score, event.feedback)
        for dim in event.dimensions:
            self.ui.show_dimension(dim["name"], dim["score"])

    async def on_flow_update(self, event):
        self.ui.update_flow_chart(event.flow)

    async def on_evidence_result(self, event):
        self.ui.show_evidence_drawer(event.query, event.cards)

    async def on_judging_started(self, event):
        self.ui.show_judging_overlay(event.estimated_seconds)

    async def on_judge_result(self, event):
        self.ui.show_winner(event.winner, event.margin)
        self.ui.show_scores(event.aff_score, event.neg_score)
        self.ui.show_decision(event.decision)
        for issue in event.voting_issues:
            self.ui.show_voting_issue(issue)

    async def on_error(self, event):
        if event.recoverable:
            self.ui.show_warning(event.message)
        else:
            self.ui.show_fatal_error(event.message)
            # The debate is over — stop waiting for more events.

    async def on_belief_tree(self, event):
        self.ui.render_argument_map(event.tree)

    async def on_unknown(self, event):
        # Catch-all for forward compatibility — log unknown events
        logger.warning("unknown event: %s", event.raw)

    async def on_disconnect(self, reason=""):
        self.ui.show_disconnected(reason)
```

## Starting a debate with pre-built prep

If you built a belief tree out-of-band (e.g. via the FastAPI sidecar's `POST /debates/topics` endpoint, or any other prep pipeline), you can skip the SDK's inline prep by passing the already-computed tree via dispatch metadata. The SDK itself does not currently cache belief trees across sessions — the reference FastAPI sidecar does this by keeping a `TopicStore` and linking each debate to a `topic_id`.

In the SDK directly, every `create_managed_session()` call triggers the agent's own prep phase. To reuse prep across multiple debates, build the topic caching layer in your backend (see `debate-fastapi-package-test/app/store.py` for a reference implementation) and pre-warm topics before your users start debating.

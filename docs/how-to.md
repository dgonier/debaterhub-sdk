# How Do I…?

Task-oriented recipes for the most common things you'll want to do with `debaterhub-sdk`. Each recipe is self-contained and copy-pasteable.

If you're new to the SDK, read [README](../README.md) → [modes.md](modes.md) → [events.md](events.md) first, then use this doc as a lookup.

## Contents

- [Install and set up](#install-and-set-up)
- [Run my first debate (30 lines)](#run-my-first-debate-30-lines)
- [Run an AI-vs-AI debate](#run-an-ai-vs-ai-debate)
- [Handle events in my backend](#handle-events-in-my-backend)
- [Submit a human speech](#submit-a-human-speech)
- [Handle cross-examination](#handle-cross-examination)
- [Check whose turn it is](#check-whose-turn-it-is)
- [Get the belief tree](#get-the-belief-tree)
- [Get final scores and judge feedback](#get-final-scores-and-judge-feedback)
- [Request coaching hints on demand](#request-coaching-hints-on-demand)
- [Search for evidence mid-debate](#search-for-evidence-mid-debate)
- [Run debates without coaching or evidence](#run-debates-without-coaching-or-evidence)
- [Handle disconnects and reconnects](#handle-disconnects-and-reconnects)
- [Warm up the agent before a debate](#warm-up-the-agent-before-a-debate)
- [Run many debates in parallel](#run-many-debates-in-parallel)
- [Log every event for debugging](#log-every-event-for-debugging)
- [Handle errors](#handle-errors)
- [Test without a real LiveKit server](#test-without-a-real-livekit-server)
- [Use from FastAPI / Flask / Django](#use-from-fastapi--flask--django)

---

## Install and set up

```bash
pip install git+https://github.com/dgonier/debaterhub-sdk.git
```

You need LiveKit credentials and a deployed debate agent (`human-debate-agent` on Modal by default).

```python
from debaterhub import DebateClient

client = DebateClient(
    livekit_url="wss://your-livekit.cloud",
    livekit_api_key="YOUR_KEY",
    livekit_api_secret="YOUR_SECRET",
    agent_name="human-debate-agent",         # default
    warmup_url="https://...modal.run",       # optional but recommended
)
```

## Run my first debate (30 lines)

The minimum viable integration — human debating as AFF, printing events as they arrive.

```python
import asyncio
from debaterhub import DebateClient, DebateConfig, DebateEventHandler

class PrintHandler(DebateEventHandler):
    async def on_debate_ready(self, event):
        print(f"Ready: {event.topic}")
    async def on_turn_signal(self, event):
        print(f"→ {event.speech_type} ({event.speaker}) — {event.status}")
    async def on_speech_text(self, event):
        print(f"  {event.speech_type}: {event.text[:100]}...")
    async def on_judge_result(self, event):
        print(f"Winner: {event.winner} ({event.margin})")

async def main():
    client = DebateClient("wss://...", "key", "secret", warmup_url="https://...modal.run")
    config = DebateConfig(topic="AI will benefit society", human_side="aff")
    session = await client.create_managed_session(config, PrintHandler())

    # When it's your turn, submit:
    await session.submit_speech("AC", "I argue that AI will benefit society because...")

    # Block until the debate finishes
    while not session.tracker.is_complete:
        await asyncio.sleep(5)

    await session.disconnect()
    await client.close()

asyncio.run(main())
```

## Run an AI-vs-AI debate

Both sides generated, no human input. See [modes.md](modes.md#ai-vs-ai-autonomous-debates) for the full version.

```python
config = DebateConfig(
    topic="UBI should replace welfare",
    debate_mode="ai_ai",
    coaching_enabled=False,
    evidence_enabled=False,
)
session = await client.create_managed_session(config, MyObserver())

# Don't call submit_speech / submit_cx_* — the agent drives both sides.
while not session.tracker.is_complete:
    await asyncio.sleep(5)
```

## Handle events in my backend

Subclass `DebateEventHandler` and override any of the `on_*` methods. Unoverridden methods are no-ops. See [events.md](events.md#handler-snippets) for the full list of events and sample handlers.

```python
class MyHandler(DebateEventHandler):
    def __init__(self, db, ui):
        self.db = db
        self.ui = ui

    async def on_speech_text(self, event):
        await self.db.insert_speech(event.speech_type, event.text)
        await self.ui.broadcast(event.raw)   # event.raw is the full dict

    async def on_error(self, event):
        if not event.recoverable:
            await self.db.mark_failed(event.code, event.message)
```

## Submit a human speech

When `on_turn_signal` fires with `speaker="human"` and `status="active"`, submit the speech:

```python
await session.submit_speech(
    speech_type="AC",
    transcript="My constructive argument text...",
    duration_seconds=240.0,
    word_count=480,   # optional — will be computed from transcript if omitted
)
```

The tracker automatically records the speech. Next `turn_signal` will advance.

## Handle cross-examination

CX periods alternate questions and answers. Your role depends on `human_side` and which CX period it is:

| Period | AFF role | NEG role |
|---|---|---|
| `AC-CX` | answers | asks |
| `NC-CX` | asks | answers |

```python
class MyHandler(DebateEventHandler):
    async def on_turn_signal(self, event):
        if event.is_cx and event.speaker == "human":
            self.ui.enable_cx_input()

    async def on_cx_question(self, event):
        # Called when the AI asks a question
        self.ui.display_ai_question(event.question)

    async def on_cx_answer(self, event):
        # Called when the AI answers the human's question
        self.ui.display_ai_answer(event.answer)

# When the human sends a CX question:
await session.submit_cx_question("Can you clarify your second warrant?", turn_number=1)

# When the human answers an AI question:
await session.submit_cx_answer("Yes, my warrant is based on...")

# When the CX period is done:
await session.end_cx("AC-CX")

# To skip a CX entirely:
await session.skip_cx("NC-CX")
```

## Check whose turn it is

The `DebateTurnTracker` is updated automatically from `turn_signal` events:

```python
t = session.tracker

t.current_speech      # "AC", "AC-CX", "NC", etc. or None
t.current_speaker     # "human" or "ai"
t.speech_index        # 0-6
t.phase               # "waiting" | "active" | "prep_time" | "complete"
t.is_human_turn       # True if the human should act
t.is_cx               # True if we're in a CX period
t.is_complete         # True after judge_result
t.transcripts         # {"AC": "...", "NC": "..."}
t.completed_speeches  # ["AC", "AC-CX", "NC", ...]
```

Gate your UI on these instead of trying to track state yourself:

```python
if session.tracker.is_human_turn and not session.tracker.is_cx:
    # Show the "record your speech" button
    ...
```

## Get the belief tree

The belief tree arrives once during setup via the `BeliefTreeEvent`. Cache it in your handler:

```python
class MyHandler(DebateEventHandler):
    def __init__(self):
        self.belief_tree = None

    async def on_belief_tree(self, event):
        self.belief_tree = event.tree
        # Render an argument map in your UI
        for belief in event.tree["beliefs"]:
            print(belief["side"], belief["label"])
```

Filter by side:
```python
aff_beliefs = [b for b in handler.belief_tree["beliefs"] if b["side"] == "aff"]
```

## Get final scores and judge feedback

The `judge_result` event is the last event. It has everything:

```python
class MyHandler(DebateEventHandler):
    async def on_judge_result(self, event):
        print(f"Winner: {event.winner}")            # "aff" or "neg"
        print(f"AFF: {event.aff_score}")            # float
        print(f"NEG: {event.neg_score}")            # float
        print(f"Margin: {event.margin}")            # "decisive" | "clear" | "close" | "split"
        print(f"Decision: {event.decision}")        # written explanation
        for issue in event.voting_issues:
            print(f"  • {issue}")
        for fb in event.per_speech_feedback:
            print(f"  {fb['speech_type']}: {fb['feedback']}")
```

## Request coaching hints on demand

Coaching hints arrive automatically before each human speech if `coaching_enabled=True`. You can also request hints for any upcoming speech:

```python
# Request hints for the 1AR while you're still in AC-CX
await session.request_coaching("1AR")

class MyHandler(DebateEventHandler):
    async def on_coaching_hint(self, event):
        print(f"Hints for {event.for_speech}:")
        for hint in event.hints:
            print(f"  • {hint}")
```

## Search for evidence mid-debate

```python
await session.request_evidence("economic impact of universal basic income", limit=5)

class MyHandler(DebateEventHandler):
    async def on_evidence_result(self, event):
        print(f"{event.total_results} cards for '{event.query}'")
        for card in event.cards:
            print(f"  [{card['tag']}] {card['source']}")
            print(f"    {card['fulltext'][:200]}")
```

## Run debates without coaching or evidence

```python
config = DebateConfig(
    topic="...",
    human_side="aff",
    coaching_enabled=False,
    evidence_enabled=False,
    enable_prep=False,          # skip prep time before 1AR
    enable_flow_study=False,    # skip flow tracking
    enable_scoring=False,       # skip inline speech scoring
)
```

Useful for faster test runs, benchmarking, or when you want to implement those features yourself.

## Handle disconnects and reconnects

The SDK emits `on_disconnect` when the session drops. Currently there's **no built-in reconnect** — you need to recreate the session. The debate continues server-side, but you'll miss events that happened while you were offline.

Recovery pattern: keep a log of event timestamps, and on reconnect fetch the missing ones out-of-band (e.g. via your own event store, or the FastAPI sidecar's `GET /debates/{id}/events?since=...` endpoint).

```python
class MyHandler(DebateEventHandler):
    async def on_disconnect(self, reason=""):
        logger.error(f"Disconnected: {reason}")
        # Trigger your reconnect logic here
```

## Warm up the agent before a debate

The Modal-hosted agent scales to zero. Cold starts take ~60–90 seconds, during which `create_managed_session()` will wait. To keep latency low, warm the agent first:

```python
client = DebateClient(
    "wss://...", "key", "secret",
    warmup_url="https://debaterhub--livekit-human-debate-agent-warmup.modal.run",
)

# Explicit warmup (returns the agent's status string)
status = await client.warmup_agent()
print(status)  # "ready" or None on failure

# Or let create_managed_session warm automatically (default: warmup=True)
session = await client.create_managed_session(config, handler, warmup=True)
```

For bursty workloads, call `warmup_agent()` on your server startup.

## Run many debates in parallel

Each `ManagedDebateSession` is independent. Fire them off concurrently:

```python
async def run_one(topic: str):
    config = DebateConfig(topic=topic, debate_mode="ai_ai")
    session = await client.create_managed_session(config, MyHandler())
    while not session.tracker.is_complete:
        await asyncio.sleep(5)
    await session.disconnect()
    return session.tracker.transcripts

topics = ["UBI...", "AI safety...", "Social media liability..."]
results = await asyncio.gather(*[run_one(t) for t in topics])
```

Reuse a single `DebateClient` for all sessions — don't create one per debate. Only call `client.close()` at shutdown.

## Log every event for debugging

```python
class LoggingHandler(DebateEventHandler):
    async def on_unknown(self, event):
        # Catches anything not matched by on_<type> methods
        logger.info("unknown: %s", event.raw)

    # Fallback: override the entire dispatch by intercepting every event
    # via a decorator pattern:
```

Or wrap your handler:

```python
from debaterhub import DebateEventHandler

class TeeHandler(DebateEventHandler):
    """Logs every event AND forwards to a wrapped handler."""
    def __init__(self, inner):
        self.inner = inner

    def __getattribute__(self, name):
        if name.startswith("on_"):
            async def wrapped(event, *a, **kw):
                logger.info(f"{name}: {getattr(event, 'raw', event)}")
                return await getattr(object.__getattribute__(self, "inner"), name)(event, *a, **kw)
            return wrapped
        return object.__getattribute__(self, name)

session = await client.create_managed_session(config, TeeHandler(MyHandler()))
```

## Handle errors

```python
from debaterhub import (
    DebatehubError,
    ConfigValidationError,
    ConnectionError,
    DispatchError,
    WarmupError,
    SessionNotConnectedError,
)

try:
    session = await client.create_managed_session(config, handler)
except ConfigValidationError as e:
    print(f"Bad config: {e}")
except ConnectionError as e:
    print(f"Can't reach LiveKit: {e}")
except DispatchError as e:
    print(f"Agent didn't accept the job: {e}")
except DebatehubError as e:
    print(f"Other SDK error: {e}")
```

`ErrorEvent` is different — it's for **in-debate** errors (generation failed, timeout, etc). Check `event.recoverable`:

```python
async def on_error(self, event):
    if event.recoverable:
        logger.warning(f"recoverable: {event.message}")
    else:
        logger.error(f"fatal: {event.code} — {event.message}")
        # The debate won't continue. Disconnect and clean up.
```

## Test without a real LiveKit server

For unit tests, instantiate the event classes directly and pass them to your handler:

```python
import pytest
from debaterhub import DebateReadyEvent, JudgeResultEvent

@pytest.mark.asyncio
async def test_my_handler():
    handler = MyHandler()

    await handler.on_debate_ready(DebateReadyEvent(
        topic="test topic",
        human_side="aff",
        speech_order=["AC", "AC-CX", "NC", "NC-CX", "1AR", "NR", "2AR"],
        speech_time_limits={"AC": 300},
        evidence_cards=[],
        belief_tree_summary="",
        raw={},
    ))
    assert handler.ready_called
```

For integration tests against a real agent, see `debaterhub-sdk/tests/` and the reference FastAPI sidecar's `tests/test_e2e.py`.

## Use from FastAPI / Flask / Django

The SDK is `asyncio`-native — it plugs directly into FastAPI. For Flask/Django, run the session inside an asyncio task or use a separate worker process.

For FastAPI, the reference implementation is [`debate-fastapi-package-test`](https://github.com/dgonier/debate-fastapi-reference) — it wires `ManagedDebateSession` to a WebSocket bridge so your frontend can drive the debate through JSON messages.

Key integration points:
- Hold `DebateClient` as a singleton on `app.state`.
- Create one `ManagedDebateSession` per debate and store it in a dict keyed by `debate_id`.
- Your `DebateEventHandler` forwards events to the WebSocket.
- Route client actions (`submit_speech`, etc.) through REST or WebSocket messages into `session.submit_*()` calls.

See `app/routes/debates.py` and `app/handler.py` in the reference repo for the full pattern.

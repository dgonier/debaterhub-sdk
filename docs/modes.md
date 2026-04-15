# Integration Modes

The SDK supports two **integration modes** (how your app talks to the debate) and two **debate modes** (who plays which role).

| Integration Mode | What it returns | Who holds the connection |
|---|---|---|
| **Token-Only** | LiveKit token + room name | Your frontend connects directly to LiveKit |
| **Server-Managed** | `ManagedDebateSession` with event handler | Your backend holds the connection |

| Debate Mode | `debate_mode` | Who speaks |
|---|---|---|
| **Human vs AI** (default) | `"ai_human"` | One side is a human, one is the LLM agent |
| **AI vs AI** | `"ai_ai"` | Both sides are LLM-generated; observer-only |

You can combine them freely: Server-Managed + AI-vs-AI is the common "autonomous debate observer" setup. Token-Only + AI-vs-AI is valid if you want a frontend to watch the debate directly.

## Mode 1: Token-Only

Use when your **frontend** will connect to LiveKit directly.

```python
from debaterhub import DebateClient, DebateConfig

client = DebateClient(
    livekit_url="wss://lk.example.com",
    livekit_api_key="...",
    livekit_api_secret="...",
)

# Create session — returns connection details
details = await client.create_session(
    DebateConfig(topic="Universal basic income benefits society"),
    participant_name="Alice",
    warmup=True,
)

# Send these to your frontend
response = {
    "server_url": details.server_url,       # wss://lk.example.com
    "room_name": details.room_name,         # debate-a1b2c3d4e5f6
    "participant_token": details.participant_token,  # JWT token
}

# Frontend connects with LiveKit JS/React SDK:
# const room = new Room();
# await room.connect(serverUrl, token);
# room.on('dataReceived', (data) => { ... });

await client.close()
```

### When to use Mode 1

- Web apps with a LiveKit frontend SDK (React, Vue, vanilla JS)
- Mobile apps using LiveKit iOS/Android SDKs
- When you want the client to handle audio/video alongside data
- Simplest integration path

### What your frontend needs to handle

- Connect to LiveKit with the returned token
- Listen for data channel messages (JSON on topic `"debate"`)
- Parse events and update UI
- Send actions back via data channel

## Mode 2: Server-Managed

Use when your **backend** needs to process events and control the debate.

```python
from debaterhub import DebateClient, DebateConfig, DebateEventHandler

class MyHandler(DebateEventHandler):
    async def on_debate_initializing(self, event):
        print(f"Setting up: {event.message}")

    async def on_debate_ready(self, event):
        print(f"Ready! Topic: {event.topic}")

    async def on_turn_signal(self, event):
        print(f"Turn: {event.speech_type} — {event.speaker}")
        if event.speaker == "human":
            print("  → Waiting for human speech submission")

    async def on_speech_text(self, event):
        print(f"[{event.speech_type}] {event.text[:100]}...")

    async def on_coaching_hint(self, event):
        for hint in event.hints:
            print(f"  Coach: {hint}")

    async def on_speech_scored(self, event):
        print(f"  Score: {event.score:.2f} — {event.feedback[:80]}")

    async def on_judge_result(self, event):
        print(f"Winner: {event.winner} ({event.margin})")
        print(f"  AFF: {event.aff_score:.2f}  NEG: {event.neg_score:.2f}")

    async def on_error(self, event):
        print(f"ERROR [{event.code}]: {event.message}")

    async def on_disconnect(self, reason=""):
        print(f"Disconnected: {reason}")


client = DebateClient("wss://lk.example.com", "key", "secret")
config = DebateConfig(topic="AI benefits society", human_side="aff")
handler = MyHandler()

session = await client.create_managed_session(config, handler)

# The session is now connected and receiving events.
# Use the tracker to check state:
print(session.tracker.current_speech)   # Current speech type
print(session.tracker.is_human_turn)    # True if human should act
print(session.tracker.phase)            # "waiting", "active", "prep_time", "complete"

# Submit human actions:
await session.submit_speech("AC", "I argue that AI will benefit society because...")
await session.submit_cx_question("How do you define 'benefit'?")
await session.submit_cx_answer("By benefit, I mean measurable improvements in...")
await session.end_cx("AC-CX")
await session.end_prep_time()
await session.request_coaching("1AR")
await session.request_evidence("AI economic impact studies")
await session.skip_cx("NC-CX")  # Skip a CX period entirely

# Disconnect when done
await session.disconnect()
await client.close()
```

### When to use Mode 2

- Backend-driven apps (FastAPI, Django, Flask)
- Bot-to-bot testing / automated debate runs
- When you need to log, store, or process events server-side
- When the frontend is a thin client (HTML/WebSocket only)
- CI/CD test harnesses

### State tracking

The `session.tracker` (`DebateTurnTracker`) is automatically updated from `turn_signal` events:

```python
tracker = session.tracker

tracker.current_speech    # "AC", "NC-CX", None, etc.
tracker.current_speaker   # "human" or "ai"
tracker.speech_index      # 0-6
tracker.phase             # "waiting", "active", "prep_time", "complete"
tracker.is_human_turn     # True when human should submit
tracker.is_cx             # True during CX periods
tracker.is_complete       # True after all speeches
tracker.transcripts       # {"AC": "...", "NC": "..."} — recorded speeches
tracker.completed_speeches  # ["AC", "AC-CX", "NC"] — in order
```

### Combining Mode 1 + Mode 2

For some architectures you may want both: use Mode 1 to get a token for the frontend (audio/video), while also running a Mode 2 session on the backend for logging. This requires two participants in the same room — the human and the SDK manager. The SDK handles this automatically with a separate `sdk-manager-*` identity.

## AI-vs-AI: autonomous debates

Set `debate_mode="ai_ai"` on the `DebateConfig` and the agent generates both sides. You submit no speeches, answer no CX questions — you're an observer.

This works with either Mode 1 or Mode 2. Mode 2 is most common because you want the backend to log speeches as they stream.

```python
from debaterhub import DebateClient, DebateConfig, DebateEventHandler

class AIObserver(DebateEventHandler):
    """No submit_* calls — just watch."""

    async def on_debate_ready(self, event):
        print(f"Ready: {event.topic}")

    async def on_speech_text(self, event):
        print(f"[{event.speech_type}] ({event.word_count} words)")
        print(event.text[:200], "...")

    async def on_cx_question(self, event):
        print(f"  CX Q: {event.question}")

    async def on_cx_answer(self, event):
        print(f"  CX A: {event.answer}")

    async def on_judge_result(self, event):
        print(f"\nWinner: {event.winner}")
        print(f"  aff={event.aff_score} neg={event.neg_score}")

client = DebateClient("wss://lk.example.com", "key", "secret")
config = DebateConfig(
    topic="The United States should adopt universal basic income",
    debate_mode="ai_ai",
    # human_side is ignored in ai_ai mode; coaching/evidence usually disabled
    coaching_enabled=False,
    evidence_enabled=False,
)
session = await client.create_managed_session(config, AIObserver())

# Wait for the debate to finish. A full IPDA debate runs ~20–25 minutes.
# Block on the tracker or wait for on_judge_result to fire.
import asyncio
while not session.tracker.is_complete:
    await asyncio.sleep(5)

await session.disconnect()
await client.close()
```

### When to use AI-vs-AI

- Automated evaluation: run N debates on the same topic with different config to compare outputs.
- Training data generation: produce transcripts at scale for downstream SFT/RL.
- Spectator UIs: let users watch the model debate itself on arbitrary topics.
- Regression testing: catch generation quality drift by re-running canonical topics.

### What to omit

- **Don't** call `submit_speech`, `submit_cx_question`, `submit_cx_answer`, `end_cx`, or `end_prep_time` — the agent drives both sides.
- **Don't** rely on `is_human_turn` — it's always `False` in AI-vs-AI mode.
- You *can* still call `request_evidence` if `evidence_enabled=True` — but it's rarely useful since neither side is human.

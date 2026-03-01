# Integration Modes

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

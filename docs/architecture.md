# SDK Architecture

## Overview

The debaterhub SDK provides two integration modes for running human-vs-AI IPDA debates over a LiveKit data channel.

```
┌─────────────────────────────────────────────────────────┐
│                     DebateClient                        │
│                                                         │
│  ┌─────────────────────┐   ┌─────────────────────────┐  │
│  │  Mode 1: Token-Only │   │ Mode 2: Server-Managed  │  │
│  │  create_session()   │   │ create_managed_session() │  │
│  │                     │   │                          │  │
│  │  Returns:           │   │  Returns:                │  │
│  │  ConnectionDetails  │   │  ManagedDebateSession    │  │
│  │  (token, url, room) │   │  (tracker, handler, ws)  │  │
│  └─────────┬───────────┘   └──────────┬───────────────┘  │
│            │                          │                  │
│       Frontend                  DataOnlyParticipant     │
│       connects                  joins room,             │
│       to LiveKit                parses events,           │
│       directly                  dispatches to handler    │
└─────────────────────────────────────────────────────────┘
```

## Module Layout

```
src/debaterhub/
├── __init__.py          # Public API re-exports
├── _version.py          # Package version
├── client.py            # DebateClient (entry point)
├── config.py            # DebateClientConfig, DebateConfig, ConnectionDetails
├── constants.py         # IPDA speech order, time limits, side mappings
├── events.py            # 15 typed event classes + DebateEventHandler
├── exceptions.py        # Exception hierarchy
├── protocol.py          # Wire message parsing, key normalization
├── session.py           # ManagedDebateSession (Mode 2)
├── state.py             # DebateTurnTracker
├── warmup.py            # Optional Modal container warmup
├── _livekit.py          # Internal LiveKit helpers (room, token, dispatch)
└── _data_channel.py     # DataOnlyParticipant (internal)
```

## Mode 1: Token-Only

The simplest integration. Your backend calls `create_session()` which:

1. Optionally warms up the Modal container
2. Creates a LiveKit room
3. Dispatches the debate agent with config metadata
4. Generates a participant JWT token

Returns a `ConnectionDetails` object. Your frontend uses these to connect to LiveKit directly using the LiveKit client SDK (JavaScript/React/Swift/etc).

**Best for:** Web apps where the frontend handles the LiveKit connection and renders events from the data channel.

## Mode 2: Server-Managed

Your backend calls `create_managed_session()` which does everything Mode 1 does, plus:

1. Creates a `DataOnlyParticipant` (no audio/video, data channel only)
2. Connects to the LiveKit room on the server side
3. Parses incoming data-channel messages into typed events
4. Updates the `DebateTurnTracker` state machine
5. Dispatches events to your `DebateEventHandler` subclass

Returns a `ManagedDebateSession` with methods to send actions back to the agent.

**Best for:** Backend-driven apps, bots, testing harnesses, or when you need server-side event processing.

## Data Flow

```
LiveKit Agent (debate orchestrator)
    │
    │  Data Channel (JSON)
    ▼
DataOnlyParticipant._on_data_received()
    │
    │  parse_server_message()  →  normalize keys, speech types
    │  event_from_dict()       →  typed event object
    │
    ▼
ManagedDebateSession._on_data_received()
    │
    ├──→ DebateTurnTracker.update_from_turn_signal()  (for turn_signal events)
    │
    └──→ DebateEventHandler.on_<event_type>()         (dispatched to your handler)
```

## Wire Protocol

Messages are JSON objects on the LiveKit data channel (topic: `"debate"`).

- Server→Client: always has a `type` field (e.g. `"turn_signal"`, `"speech_text"`)
- Client→Server: uses `type` for actions (e.g. `"speech_end"`, `"cx_question"`)
- Keys may arrive as camelCase or snake_case; the SDK normalizes to both
- Speech types are normalized to uppercase hyphenated form: `"AC-CX"`, `"1AR"`, etc.

## IPDA Format

The International Public Debate Association (IPDA) format has 7 speech periods:

| # | Speech | Side | Time | Type |
|---|--------|------|------|------|
| 1 | AC (Affirmative Constructive) | AFF | 5 min | Constructive |
| 2 | AC-CX (Cross-Examination) | NEG asks | 3 min | CX |
| 3 | NC (Negative Constructive) | NEG | 6 min | Constructive |
| 4 | NC-CX (Cross-Examination) | AFF asks | 3 min | CX |
| 5 | 1AR (First Affirmative Rebuttal) | AFF | 5 min | Rebuttal |
| 6 | NR (Negative Rebuttal) | NEG | 5 min | Rebuttal |
| 7 | 2AR (Second Affirmative Rebuttal) | AFF | 3 min | Rebuttal |

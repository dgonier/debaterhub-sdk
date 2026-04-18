"""Integration tests for Lincoln-Douglas format through the SDK.

These tests simulate a full LD debate via the SDK's public API using a fake
LiveKit data channel (see ``conftest.py::fake_participant``). No real
LiveKit server or LLM is required.
"""

from __future__ import annotations

import json
from typing import List

import pytest

from debaterhub import (
    DebateConfig,
    DebateEventHandler,
    ManagedDebateSession,
    get_format_spec,
)
from debaterhub._data_channel import DataOnlyParticipant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _RecordingHandler(DebateEventHandler):
    """Records every event the handler sees, in order."""

    def __init__(self) -> None:
        self.events: List[tuple[str, object]] = []

    async def on_debate_ready(self, event):
        self.events.append(("ready", event))

    async def on_debate_initializing(self, event):
        self.events.append(("initializing", event))

    async def on_turn_signal(self, event):
        self.events.append(("turn", event))

    async def on_speech_text(self, event):
        self.events.append(("speech_text", event))

    async def on_judge_result(self, event):
        self.events.append(("judge", event))

    async def on_unknown(self, event):
        self.events.append(("unknown", event))


# ---------------------------------------------------------------------------
# Config / tracker unit checks
# ---------------------------------------------------------------------------

def test_ld_config_dispatch_metadata():
    cfg = DebateConfig(topic="Resolved: LD test", format="ld", human_side="aff")
    meta = cfg.to_dispatch_metadata()
    assert meta["format"] == "ld"
    assert meta["topic"] == "Resolved: LD test"
    assert meta["human_side"] == "aff"
    assert meta["humanSide"] == "aff"


def test_ld_tracker_respects_ld_timings():
    spec = get_format_spec("ld")
    # LD time limits for key speeches
    assert spec.speech_time_limits["AC"] == 360
    assert spec.speech_time_limits["NC"] == 420
    assert spec.speech_time_limits["1AR"] == 240
    assert spec.speech_time_limits["NR"] == 360
    assert spec.speech_time_limits["2AR"] == 180


def test_ld_aff_active_set():
    spec = get_format_spec("ld")
    # AFF is active in AC, 1AR, 2AR, and NC-CX (AFF asks)
    assert spec.aff_active == {"AC", "1AR", "2AR", "NC-CX"}
    assert spec.neg_active == {"NC", "NR", "AC-CX"}


# ---------------------------------------------------------------------------
# Full turn-by-turn simulation
# ---------------------------------------------------------------------------

LD_SPEECH_SEQUENCE = [
    ("AC", "human"),      # AFF human
    ("AC-CX", "ai"),      # NEG (AI) asks
    ("NC", "ai"),         # NEG AI speaks
    ("NC-CX", "human"),   # AFF (human) asks
    ("1AR", "human"),
    ("NR", "ai"),
    ("2AR", "human"),
]


async def _run_ld_turn_simulation(fake_participant, human_side="aff"):
    handler = _RecordingHandler()

    # Build a session directly (skip DebateClient to avoid LiveKit api init).
    participant = DataOnlyParticipant(
        livekit_url="wss://fake",
        token="fake-token",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side=human_side,
        debate_mode="ai_human",
        format="ld",
    )
    await session.connect()

    # Emit debate_ready
    spec = get_format_spec("ld")
    ready = {
        "type": "debate_ready",
        "format": "ld",
        "topic": "Resolved: Test",
        "human_side": human_side,
        "speech_order": spec.speech_ids,
        "speech_time_limits": spec.speech_time_limits,
    }
    await fake_participant.inject(json.dumps(ready).encode())

    # Emit turn signals for each speech
    for i, (speech_id, speaker) in enumerate(LD_SPEECH_SEQUENCE):
        turn = {
            "type": "turn_signal",
            "speech_type": speech_id,
            "speaker": speaker,
            "is_cx": spec.get_speech(speech_id).is_cx,
            "time_limit": spec.speech_time_limits[speech_id],
            "speech_index": i,
            "total_speeches": 7,
            "status": "active",
        }
        await fake_participant.inject(json.dumps(turn).encode())

        # After each signal, check tracker state
        assert session.tracker.current_speech == speech_id
        assert session.tracker.speech_index == i

        expected_human_turn = (speaker == "human")
        assert session.tracker.is_human_turn == expected_human_turn, (
            f"Speech {speech_id}: expected is_human_turn={expected_human_turn}, "
            f"got {session.tracker.is_human_turn} (human_side={human_side})"
        )

    # Mark complete
    await fake_participant.inject(json.dumps({
        "type": "turn_signal",
        "speech_type": "2AR",
        "speaker": "human",
        "status": "complete",
        "speech_index": 6,
    }).encode())
    assert session.tracker.is_complete

    return session, handler


async def test_ld_turn_simulation_aff_human(fake_participant):
    session, handler = await _run_ld_turn_simulation(
        fake_participant, human_side="aff"
    )
    # Should have received 1 ready + 7 turn signals + 1 completion turn signal
    event_types = [t for t, _ in handler.events]
    assert event_types.count("ready") == 1
    assert event_types.count("turn") >= 7


async def test_ld_turn_simulation_neg_human(fake_participant):
    # Swap speakers for neg-human variant
    neg_sequence = [
        ("AC", "ai"),
        ("AC-CX", "human"),  # NEG human asks
        ("NC", "human"),
        ("NC-CX", "ai"),     # AFF (AI) asks
        ("1AR", "ai"),
        ("NR", "human"),
        ("2AR", "ai"),
    ]

    handler = _RecordingHandler()
    participant = DataOnlyParticipant(
        livekit_url="wss://fake",
        token="fake",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side="neg",
        debate_mode="ai_human",
        format="ld",
    )
    await session.connect()

    spec = get_format_spec("ld")
    for i, (speech_id, speaker) in enumerate(neg_sequence):
        turn = {
            "type": "turn_signal",
            "speech_type": speech_id,
            "speaker": speaker,
            "is_cx": spec.get_speech(speech_id).is_cx,
            "time_limit": spec.speech_time_limits[speech_id],
            "speech_index": i,
            "total_speeches": 7,
            "status": "active",
        }
        await fake_participant.inject(json.dumps(turn).encode())
        assert session.tracker.is_human_turn == (speaker == "human"), (
            f"Speech {speech_id}: expected {(speaker == 'human')}, "
            f"got {session.tracker.is_human_turn}"
        )


# ---------------------------------------------------------------------------
# Human speech submission smoke test
# ---------------------------------------------------------------------------

async def test_ld_submit_speech_records_transcript(fake_participant):
    handler = _RecordingHandler()
    participant = DataOnlyParticipant(
        livekit_url="wss://fake",
        token="fake",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side="aff",
        debate_mode="ai_human",
        format="ld",
    )
    await session.connect()

    # Set tracker to AC (human's turn)
    await fake_participant.inject(json.dumps({
        "type": "turn_signal",
        "speech_type": "AC",
        "speaker": "human",
        "speech_index": 0,
        "total_speeches": 7,
        "status": "active",
    }).encode())

    ac_transcript = "My value is justice, my criterion is maximizing freedom. " * 50
    await session.submit_speech("AC", ac_transcript, duration_seconds=360.0)

    # Outgoing message captured
    assert len(fake_participant.sent) == 1
    sent = fake_participant.sent[0]
    assert sent["type"] == "speech_end"
    assert sent["speechType"] == "AC"
    assert sent["transcript"] == ac_transcript

    # Tracker recorded the transcript
    assert session.tracker.transcripts["AC"] == ac_transcript
    assert "AC" in session.tracker.completed_speeches

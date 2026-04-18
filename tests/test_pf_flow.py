"""Integration tests for Public Forum format through the SDK."""

import json
from typing import List

import pytest

from debaterhub import (
    DebateConfig,
    DebateEventHandler,
    DebateTurnTracker,
    ManagedDebateSession,
    TurnSignalEvent,
    get_format_spec,
)
from debaterhub._data_channel import DataOnlyParticipant


class _Recorder(DebateEventHandler):
    def __init__(self):
        self.events: List[tuple[str, object]] = []

    async def on_debate_ready(self, event):  self.events.append(("ready", event))
    async def on_turn_signal(self, event):   self.events.append(("turn", event))
    async def on_speech_text(self, event):   self.events.append(("speech_text", event))
    async def on_unknown(self, event):       self.events.append(("unknown", event))


# ---------------------------------------------------------------------------
# Config / spec checks
# ---------------------------------------------------------------------------

def test_pf_config_dispatch_metadata():
    cfg = DebateConfig(
        topic="Resolved: Social media does more harm than good",
        format="pf",
        human_side="aff",
        pf_first_speaker="aff",
    )
    meta = cfg.to_dispatch_metadata()
    assert meta["format"] == "pf"
    assert meta["pf_first_speaker"] == "aff"
    assert meta["pfFirstSpeaker"] == "aff"


def test_pf_config_default_pf_first_speaker():
    cfg = DebateConfig(topic="x", format="pf", human_side="aff")
    meta = cfg.to_dispatch_metadata()
    # If not set, key should be absent (not emit None)
    assert "pf_first_speaker" not in meta


def test_pf_spec_structure():
    spec = get_format_spec("pf")
    assert len(spec.speech_order) == 11
    assert spec.first_speaker_configurable is True
    assert spec.prep_time_sec == 180


def test_pf_speech_order_exact():
    spec = get_format_spec("pf")
    assert spec.speech_ids == [
        "PF-AC", "PF-NC", "PF-CF1",
        "PF-AR", "PF-NR", "PF-CF2",
        "PF-ASUM", "PF-NSUM", "PF-GCF",
        "PF-AFF-FF", "PF-NEG-FF",
    ]


def test_pf_crossfires_are_both():
    spec = get_format_spec("pf")
    for cf_id in ("PF-CF1", "PF-CF2", "PF-GCF"):
        s = spec.get_speech(cf_id)
        assert s.side == "both"
        assert s.is_cx is True


def test_pf_aff_active_includes_crossfires():
    spec = get_format_spec("pf")
    # AFF is active in: own speeches + all crossfires
    expected_aff = {
        "PF-AC", "PF-AR", "PF-ASUM", "PF-AFF-FF",   # AFF speeches
        "PF-CF1", "PF-CF2", "PF-GCF",               # crossfires (both active)
    }
    assert spec.aff_active == expected_aff


def test_pf_neg_active_includes_crossfires():
    spec = get_format_spec("pf")
    expected_neg = {
        "PF-NC", "PF-NR", "PF-NSUM", "PF-NEG-FF",
        "PF-CF1", "PF-CF2", "PF-GCF",
    }
    assert spec.neg_active == expected_neg


def test_pf_timings():
    spec = get_format_spec("pf")
    # Constructives + rebuttals = 4 min, summaries = 3 min, final focus = 2 min
    assert spec.speech_time_limits["PF-AC"] == 240
    assert spec.speech_time_limits["PF-AR"] == 240
    assert spec.speech_time_limits["PF-ASUM"] == 180
    assert spec.speech_time_limits["PF-AFF-FF"] == 120
    assert spec.speech_time_limits["PF-CF1"] == 180


# ---------------------------------------------------------------------------
# Tracker-level turn ownership
# ---------------------------------------------------------------------------

def test_pf_tracker_crossfire_both_sides_active():
    t = DebateTurnTracker(human_side="aff", format="pf")
    t.update_from_turn_signal(speech_type="PF-CF1", speaker="human")
    assert t.is_human_turn is True
    assert t.is_cx is True

    t2 = DebateTurnTracker(human_side="neg", format="pf")
    t2.update_from_turn_signal(speech_type="PF-CF1", speaker="ai")
    # NEG human: crossfire is still "human turn" because both are active
    assert t2.is_human_turn is True


def test_pf_tracker_aff_human_ownership():
    """AFF human: AFF speeches are human turns, NEG speeches are AI."""
    t = DebateTurnTracker(human_side="aff", format="pf")

    # Speeches where AFF should be human-turn=True
    for speech_id in ("PF-AC", "PF-AR", "PF-ASUM", "PF-AFF-FF"):
        t.update_from_turn_signal(speech_type=speech_id, speaker="human")
        assert t.is_human_turn is True, f"AFF human on {speech_id}"

    # NEG speeches should be human-turn=False
    for speech_id in ("PF-NC", "PF-NR", "PF-NSUM", "PF-NEG-FF"):
        t.update_from_turn_signal(speech_type=speech_id, speaker="ai")
        assert t.is_human_turn is False, f"AFF human should be AI-turn on {speech_id}"


def test_pf_tracker_neg_human_ownership():
    t = DebateTurnTracker(human_side="neg", format="pf")
    for speech_id in ("PF-NC", "PF-NR", "PF-NSUM", "PF-NEG-FF"):
        t.update_from_turn_signal(speech_type=speech_id, speaker="human")
        assert t.is_human_turn is True

    for speech_id in ("PF-AC", "PF-AR", "PF-ASUM", "PF-AFF-FF"):
        t.update_from_turn_signal(speech_type=speech_id, speaker="ai")
        assert t.is_human_turn is False


# ---------------------------------------------------------------------------
# Full 11-speech simulation
# ---------------------------------------------------------------------------

PF_SEQUENCE_AFF_HUMAN = [
    ("PF-AC", "human"),
    ("PF-NC", "ai"),
    ("PF-CF1", "human"),   # crossfire: human drives
    ("PF-AR", "human"),
    ("PF-NR", "ai"),
    ("PF-CF2", "human"),
    ("PF-ASUM", "human"),
    ("PF-NSUM", "ai"),
    ("PF-GCF", "human"),
    ("PF-AFF-FF", "human"),
    ("PF-NEG-FF", "ai"),
]


@pytest.mark.asyncio
async def test_pf_full_11_speech_flow_aff_human(fake_participant):
    handler = _Recorder()
    participant = DataOnlyParticipant(
        livekit_url="wss://fake", token="fake",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant,
        handler=handler,
        human_side="aff",
        debate_mode="ai_human",
        format="pf",
    )
    await session.connect()

    spec = get_format_spec("pf")

    # debate_ready
    await fake_participant.inject(json.dumps({
        "type": "debate_ready",
        "format": "pf",
        "topic": "Resolved: PF test",
        "human_side": "aff",
        "speech_order": spec.speech_ids,
        "speech_time_limits": spec.speech_time_limits,
    }).encode())

    # Emit all 11 speeches
    for i, (speech_id, speaker) in enumerate(PF_SEQUENCE_AFF_HUMAN):
        await fake_participant.inject(json.dumps({
            "type": "turn_signal",
            "speech_type": speech_id,
            "speaker": speaker,
            "is_cx": spec.get_speech(speech_id).is_cx,
            "time_limit": spec.speech_time_limits[speech_id],
            "speech_index": i,
            "total_speeches": 11,
            "status": "active",
        }).encode())
        assert session.tracker.current_speech == speech_id
        assert session.tracker.speech_index == i

    # Verify tracker visited 11 distinct speeches
    turn_events = [e for t, e in handler.events if t == "turn"]
    assert len(turn_events) == 11

    # Mark complete
    await fake_participant.inject(json.dumps({
        "type": "turn_signal",
        "speech_type": "PF-NEG-FF", "speaker": "ai",
        "status": "complete", "speech_index": 10,
    }).encode())
    assert session.tracker.is_complete


@pytest.mark.asyncio
async def test_pf_submit_speech_uses_pf_speech_id(fake_participant):
    handler = _Recorder()
    participant = DataOnlyParticipant(
        livekit_url="wss://fake", token="fake",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant, handler=handler,
        human_side="aff", debate_mode="ai_human", format="pf",
    )
    await session.connect()

    await fake_participant.inject(json.dumps({
        "type": "turn_signal",
        "speech_type": "PF-AC", "speaker": "human",
        "speech_index": 0, "total_speeches": 11, "status": "active",
    }).encode())

    pf_ac_text = "Our two contentions demonstrate that the resolution is true." * 20
    await session.submit_speech("PF-AC", pf_ac_text, duration_seconds=240.0)

    assert len(fake_participant.sent) == 1
    sent = fake_participant.sent[0]
    assert sent["type"] == "speech_end"
    assert sent["speechType"] == "PF-AC"

    assert session.tracker.transcripts["PF-AC"] == pf_ac_text


@pytest.mark.asyncio
async def test_pf_crossfire_submit_cx_question(fake_participant):
    """In crossfire, human can submit questions regardless of 'side' ownership."""
    handler = _Recorder()
    participant = DataOnlyParticipant(
        livekit_url="wss://fake", token="fake",
        on_data=lambda raw, topic: None,
    )
    session = ManagedDebateSession(
        participant=participant, handler=handler,
        human_side="neg", debate_mode="ai_human", format="pf",
    )
    await session.connect()

    # Set tracker to PF-CF1 (crossfire)
    await fake_participant.inject(json.dumps({
        "type": "turn_signal",
        "speech_type": "PF-CF1", "speaker": "human",
        "is_cx": True,
        "speech_index": 2, "total_speeches": 11, "status": "active",
    }).encode())
    assert session.tracker.is_human_turn is True  # crossfire = both active

    await session.submit_cx_question("How do you defend your first contention?")
    assert len(fake_participant.sent) == 1
    assert fake_participant.sent[0]["type"] == "cx_question"

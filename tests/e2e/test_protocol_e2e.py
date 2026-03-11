"""E2E: Protocol round-trip tests.

Validates that messages survive the full encode → channel → parse → event
pipeline with correct key normalization and speech type canonicalization.

Marker: fast (no LLM calls)
"""

from __future__ import annotations

import asyncio
import json

import pytest

from debaterhub.constants import IPDA_SPEECH_ORDER, SPEECH_TIME_LIMITS
from debaterhub.events import (
    CXQuestionEvent,
    DebateReadyEvent,
    ErrorEvent,
    SpeechTextEvent,
    TurnSignalEvent,
    event_from_dict,
)
from debaterhub.protocol import parse_server_message

from .conftest import RecordingHandler, SimulatedDataChannel, MockParticipant

pytestmark = [pytest.mark.e2e, pytest.mark.fast]


class TestCamelSnakeRoundTrip:
    """Agent sends camelCase, SDK normalizes to snake_case, events expose typed fields."""

    @pytest.mark.asyncio
    async def test_turn_signal_round_trip(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        # Agent sends camelCase
        await channel.send_to_session({
            "type": "turn_signal",
            "speechType": "AC",
            "speaker": "human",
            "isCx": False,
            "timeLimit": 300,
            "speechIndex": 0,
            "totalSpeeches": 7,
            "status": "active",
        })
        await asyncio.sleep(0.05)

        events = handler.events_by_type.get("turn_signal", [])
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, TurnSignalEvent)
        assert e.speech_type == "AC"
        assert e.speaker == "human"
        assert e.time_limit == 300
        assert e.is_cx is False

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_speech_text_round_trip(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        await channel.send_to_session({
            "type": "speech_text",
            "speechType": "NC",
            "text": "The negative case argues...",
            "wordCount": 5,
        })
        await asyncio.sleep(0.05)

        events = handler.events_by_type.get("speech_text", [])
        assert len(events) == 1
        assert events[0].speech_type == "NC"
        assert events[0].text == "The negative case argues..."
        assert events[0].word_count == 5

        await session.disconnect()


class TestSpeechTypeNormalization:
    """Agent may send AC_CX or ac-cx — SDK normalizes to AC-CX."""

    @pytest.mark.asyncio
    async def test_underscore_normalized(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        await channel.send_to_session({
            "type": "turn_signal",
            "speechType": "AC_CX",  # underscore variant
            "speaker": "ai",
            "isCx": True,
            "timeLimit": 180,
            "speechIndex": 1,
            "totalSpeeches": 7,
            "status": "active",
        })
        await asyncio.sleep(0.05)

        events = handler.events_by_type.get("turn_signal", [])
        assert events[0].speech_type == "AC-CX"  # normalized

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_lowercase_normalized(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        await channel.send_to_session({
            "type": "turn_signal",
            "speechType": "nc_cx",
            "speaker": "human",
            "status": "active",
        })
        await asyncio.sleep(0.05)

        events = handler.events_by_type.get("turn_signal", [])
        assert events[0].speech_type == "NC-CX"

        await session.disconnect()


class TestErrorEventParsing:
    """Error events parse correctly and surface all fields."""

    @pytest.mark.asyncio
    async def test_recoverable_error(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        await channel.send_to_session({
            "type": "error",
            "message": "Speech generation timed out",
            "code": "GENERATION_TIMEOUT",
            "recoverable": True,
        })
        await asyncio.sleep(0.05)

        errors = handler.events_by_type.get("error", [])
        assert len(errors) == 1
        assert errors[0].message == "Speech generation timed out"
        assert errors[0].code == "GENERATION_TIMEOUT"
        assert errors[0].recoverable is True

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_fatal_error(self, channel, handler):
        from debaterhub.session import ManagedDebateSession

        participant = MockParticipant(channel)
        session = ManagedDebateSession(participant=participant, handler=handler, human_side="aff")
        await session.connect()

        await channel.send_to_session({
            "type": "error",
            "message": "Agent crashed",
            "code": "AGENT_FATAL",
            "recoverable": False,
        })
        await asyncio.sleep(0.05)

        errors = handler.events_by_type.get("error", [])
        assert errors[0].recoverable is False

        await session.disconnect()


class TestClientToServerProtocol:
    """Validate the shape of messages the SDK sends to the agent."""

    @pytest.mark.asyncio
    async def test_speech_end_message_shape(self, aff_session):
        session, agent, handler = aff_session
        asyncio.create_task(agent.start_debate())

        turn = await handler.wait_human_turn(timeout=5)
        await session.submit_speech("AC", "My speech text", duration_seconds=120.5, word_count=3)

        sent = [m for m in session._participant._channel.session_sent if m["type"] == "speech_end"]
        assert len(sent) == 1
        msg = sent[0]
        assert msg["speechType"] == "AC"
        assert msg["transcript"] == "My speech text"
        assert msg["durationSeconds"] == 120.5
        assert msg["wordCount"] == 3

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_cx_question_message_shape(self, aff_session):
        session, agent, handler = aff_session
        asyncio.create_task(agent.start_debate())
        await handler.wait_ready(timeout=5)

        # Force connected state for sending
        await session.submit_cx_question("Does your evidence account for inflation?", turn_number=2)

        sent = [m for m in session._participant._channel.session_sent if m["type"] == "cx_question"]
        assert len(sent) == 1
        assert sent[0]["question"] == "Does your evidence account for inflation?"
        assert sent[0]["turnNumber"] == 2

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_evidence_request_message_shape(self, aff_session):
        session, agent, handler = aff_session
        asyncio.create_task(agent.start_debate())
        await handler.wait_ready(timeout=5)

        await session.request_evidence("poverty reduction data", limit=10)

        sent = [m for m in session._participant._channel.session_sent if m["type"] == "evidence_request"]
        assert len(sent) == 1
        assert sent[0]["query"] == "poverty reduction data"
        assert sent[0]["limit"] == 10

        await session.disconnect()

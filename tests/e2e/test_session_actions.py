"""E2E: Session action tests — submit_speech, CX, coaching, evidence, prep.

Tests the client→server protocol for all ManagedDebateSession methods
and validates the agent responses.

Marker: fast (no LLM calls)
"""

from __future__ import annotations

import asyncio

import pytest

from debaterhub.constants import IS_CX_SPEECH
from debaterhub.events import (
    CXAnswerEvent,
    CXQuestionEvent,
    CoachingHintEvent,
    EvidenceResultEvent,
    SpeechTextEvent,
)
from debaterhub.exceptions import SessionNotConnectedError
from debaterhub.session import ManagedDebateSession

from .conftest import MOCK_SPEECHES, MockParticipant, RecordingHandler, SimulatedAgent, auto_play_remaining

pytestmark = [pytest.mark.e2e, pytest.mark.fast]


class TestSubmitSpeech:
    """Test speech submission and transcript recording."""

    @pytest.mark.asyncio
    async def test_speech_recorded_in_tracker(self, aff_session):
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        turn = await handler.wait_human_turn(timeout=5)
        assert turn.speech_type == "AC"

        text = "This is the affirmative constructive speech about UBI."
        await session.submit_speech("AC", text, duration_seconds=120.0)

        assert session.tracker.transcripts["AC"] == text
        assert "AC" in session.tracker.completed_speeches

        await auto_play_remaining(session, handler)
        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()

    @pytest.mark.asyncio
    async def test_word_count_auto_calculated(self, aff_session):
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        await handler.wait_human_turn(timeout=5)

        text = "one two three four five six seven"
        await session.submit_speech("AC", text, duration_seconds=10.0)

        # Check the message sent to agent has correct word count
        sent = [m for m in session._participant._channel.session_sent if m.get("type") == "speech_end"]
        assert len(sent) == 1
        assert sent[0]["wordCount"] == 7

        await auto_play_remaining(session, handler)
        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()

    @pytest.mark.asyncio
    async def test_explicit_word_count_used(self, aff_session):
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        await handler.wait_human_turn(timeout=5)
        await session.submit_speech("AC", "test speech", duration_seconds=5.0, word_count=999)

        sent = [m for m in session._participant._channel.session_sent if m.get("type") == "speech_end"]
        assert sent[0]["wordCount"] == 999

        await auto_play_remaining(session, handler)
        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()


class TestCXInteraction:
    """Test cross-examination question/answer flow."""

    @pytest.mark.asyncio
    async def test_submit_cx_question_gets_answer(self, aff_session):
        """Human AFF asks questions during NC-CX → AI answers."""
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        # Play through until NC-CX (human's CX turn)
        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break

            st = turn.speech_type
            if st == "NC-CX":
                # Submit a CX question
                await session.submit_cx_question("How do you respond to the poverty data?", turn_number=0)
                await asyncio.sleep(0.1)

                # Should get an answer back
                answers = handler.events_by_type.get("cx_answer_server", [])
                assert len(answers) >= 1
                assert len(answers[0].answer) > 0

                await session.end_cx(st)
                # Continue playing remaining turns
                await auto_play_remaining(session, handler)
                break
            elif IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()

    @pytest.mark.asyncio
    async def test_skip_cx(self, aff_session):
        """Skipping CX should advance the debate."""
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.skip_cx(st)
            else:
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task

        # Debate should still complete fully
        assert session.tracker.is_complete

        await session.disconnect()


class TestCoaching:
    """Test coaching request/response."""

    @pytest.mark.asyncio
    async def test_request_coaching(self, aff_session):
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        turn = await handler.wait_human_turn(timeout=5)
        st = turn.speech_type

        # Request coaching before speaking
        await session.request_coaching(st)
        await asyncio.sleep(0.1)

        coaching = handler.events_by_type.get("coaching_hint", [])
        assert len(coaching) >= 1
        assert len(coaching[-1].hints) > 0

        # Now submit speech and finish
        await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)

        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()


class TestEvidenceRequest:
    """Test evidence search request/response."""

    @pytest.mark.asyncio
    async def test_request_evidence(self, aff_session):
        session, agent, handler = aff_session
        debate_task = asyncio.create_task(agent.start_debate())

        turn = await handler.wait_human_turn(timeout=5)

        await session.request_evidence("UBI economic impact studies", limit=3)
        await asyncio.sleep(0.1)

        evidence = handler.events_by_type.get("evidence_result", [])
        assert len(evidence) >= 1
        assert evidence[0].query == "UBI economic impact studies"
        assert len(evidence[0].cards) > 0

        # Finish debate
        await session.submit_speech(turn.speech_type, "Speech text", duration_seconds=60.0)
        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task
        await session.disconnect()


class TestSessionErrors:
    """Test error handling for session actions."""

    @pytest.mark.asyncio
    async def test_submit_before_connect_raises(self, channel, handler, aff_config):
        participant = MockParticipant(channel)
        session = ManagedDebateSession(
            participant=participant,
            handler=handler,
            human_side="aff",
        )
        # Not connected yet
        with pytest.raises(SessionNotConnectedError):
            await session.submit_speech("AC", "test", duration_seconds=10.0)

    @pytest.mark.asyncio
    async def test_submit_after_disconnect_raises(self, aff_session):
        session, agent, handler = aff_session
        await session.disconnect()
        with pytest.raises(SessionNotConnectedError):
            await session.submit_speech("AC", "test", duration_seconds=10.0)

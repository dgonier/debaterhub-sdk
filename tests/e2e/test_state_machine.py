"""E2E: State machine integrity through a full debate.

Validates that DebateTurnTracker transitions correctly through all
phases and that the speech order is strictly followed.

Marker: fast (no LLM calls)
"""

from __future__ import annotations

import asyncio

import pytest

from debaterhub.constants import AFF_ACTIVE, IPDA_SPEECH_ORDER, IS_CX_SPEECH, SPEECH_SIDE
from debaterhub.state import DebateTurnTracker

from .conftest import RecordingHandler

pytestmark = [pytest.mark.e2e, pytest.mark.fast]


class TestTrackerThroughFullDebate:
    """Run a full debate and assert tracker state at each step."""

    @pytest.mark.asyncio
    async def test_tracker_phases(self, aff_session):
        session, agent, handler = aff_session

        # Before start
        assert session.tracker.phase == "waiting"
        assert session.tracker.current_speech is None

        debate_task = asyncio.create_task(agent.start_debate())

        # Play through
        seen_speeches = []
        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break

            st = turn.speech_type
            seen_speeches.append(st)

            # Tracker should reflect current turn
            assert session.tracker.current_speech == st
            assert session.tracker.is_human_turn is True
            assert session.tracker.phase == "active"

            if IS_CX_SPEECH.get(st, False):
                assert session.tracker.is_cx is True
                await session.end_cx(st)
            else:
                assert session.tracker.is_cx is False
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task

        # After completion
        assert session.tracker.is_complete is True
        assert session.tracker.phase == "complete"

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_speech_index_increments(self, aff_session):
        session, agent, handler = aff_session

        debate_task = asyncio.create_task(agent.start_debate())

        indices_seen = []
        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            indices_seen.append(session.tracker.speech_index)
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"Speech {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task

        # Indices should be monotonically increasing
        for i in range(1, len(indices_seen)):
            assert indices_seen[i] > indices_seen[i - 1], (
                f"Speech index did not increase: {indices_seen}"
            )

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_transcripts_only_for_human_speeches(self, aff_session):
        """Tracker only records speeches submitted via submit_speech."""
        session, agent, handler = aff_session

        debate_task = asyncio.create_task(agent.start_debate())

        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"Human {st} transcript", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task

        # Only human non-CX speeches should be in transcripts
        for speech_type, text in session.tracker.transcripts.items():
            assert speech_type in AFF_ACTIVE, f"Unexpected transcript for {speech_type}"
            assert not IS_CX_SPEECH.get(speech_type, False), f"CX transcript shouldn't be recorded: {speech_type}"
            assert text.startswith("Human ")

        await session.disconnect()


class TestGetSideForSpeech:
    """Validate the side lookup matches SPEECH_SIDE constant."""

    def test_all_speeches_have_correct_side(self):
        tracker = DebateTurnTracker()
        for speech_type in IPDA_SPEECH_ORDER:
            result = tracker.get_side_for_speech(speech_type)
            expected = SPEECH_SIDE[speech_type]
            assert result == expected, f"{speech_type}: expected {expected}, got {result}"

    def test_unknown_speech_returns_unknown(self):
        tracker = DebateTurnTracker()
        assert tracker.get_side_for_speech("INVALID") == "unknown"

"""E2E: Full IPDA debate flow — human AFF vs AI NEG.

Validates the complete debate lifecycle: initialization → 7 speeches →
judging → completion, with correct event ordering, speech content,
timing metadata, and state machine transitions.

Marker: fast (no LLM calls)
"""

from __future__ import annotations

import asyncio

import pytest

from debaterhub.constants import (
    AFF_ACTIVE,
    IPDA_SPEECH_ORDER,
    IS_CX_SPEECH,
    SPEECH_SIDE,
    SPEECH_TIME_LIMITS,
)
from debaterhub.events import (
    CoachingHintEvent,
    DebateInitializingEvent,
    DebateReadyEvent,
    FlowUpdateEvent,
    JudgeResultEvent,
    JudgingStartedEvent,
    SpeechProgressEvent,
    SpeechScoredEvent,
    SpeechTextEvent,
    TurnSignalEvent,
)

from .conftest import MOCK_SPEECHES, RecordingHandler, SimulatedAgent

pytestmark = [pytest.mark.e2e, pytest.mark.fast]


class TestFullDebateAffHuman:
    """Human plays AFF, AI plays NEG. Full 7-speech IPDA."""

    @pytest.mark.asyncio
    async def test_debate_lifecycle(self, aff_session):
        session, agent, handler = aff_session

        # Start debate in background
        debate_task = asyncio.create_task(agent.start_debate())

        # Wait for ready
        await handler.wait_ready(timeout=5)
        ready_events = handler.events_by_type.get("debate_ready", [])
        assert len(ready_events) == 1
        ready = ready_events[0]
        assert ready.speech_order == IPDA_SPEECH_ORDER
        assert ready.human_side == "aff"

        # Play through the debate — submit human speeches when it's our turn
        human_speeches_submitted = []
        for _ in range(10):  # safety bound
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break

            speech_type = turn.speech_type
            is_cx = IS_CX_SPEECH.get(speech_type, False)

            if is_cx:
                # Human is asking CX questions
                await session.submit_cx_question("What evidence supports your claim?", turn_number=0)
                await asyncio.sleep(0.05)
                await session.end_cx(speech_type)
            else:
                # Human gives a speech
                text = MOCK_SPEECHES.get(speech_type, f"Human {speech_type} speech content here.")
                await session.submit_speech(
                    speech_type=speech_type,
                    transcript=text,
                    duration_seconds=len(text.split()) / 2.5,  # ~150 wpm
                    word_count=len(text.split()),
                )
                human_speeches_submitted.append(speech_type)

            await asyncio.sleep(0.1)

        # Wait for completion
        await handler.wait_complete(timeout=10)
        await debate_task

        # ---- ASSERTIONS ----

        # 1. All speech types appeared in turn signals
        turn_types = [e.speech_type for e in handler.events_by_type.get("turn_signal", [])]
        for st in IPDA_SPEECH_ORDER:
            assert st in turn_types, f"Missing turn signal for {st}"

        # 2. Judge result received
        judge_events = handler.events_by_type.get("judge_result", [])
        assert len(judge_events) == 1
        judge = judge_events[0]
        assert judge.winner in ("aff", "neg")
        assert judge.aff_score > 0
        assert judge.neg_score > 0
        assert len(judge.voting_issues) > 0

        # 3. AI speeches have text
        speech_texts = handler.events_by_type.get("speech_text", [])
        ai_speech_types = {e.speech_type for e in speech_texts}
        # AI is neg: NC, NR are AI speeches
        assert "NC" in ai_speech_types
        assert "NR" in ai_speech_types

        # 4. Speech text has reasonable word counts
        for st_event in speech_texts:
            assert st_event.word_count > 20, f"{st_event.speech_type} too short: {st_event.word_count} words"
            assert st_event.word_count < 2000, f"{st_event.speech_type} too long: {st_event.word_count} words"

        # 5. State tracker is complete
        assert session.tracker.is_complete

        # 6. Human speeches were recorded in tracker
        for st in human_speeches_submitted:
            assert st in session.tracker.transcripts

        await session.disconnect()

    @pytest.mark.asyncio
    async def test_event_ordering(self, aff_session):
        """Events must arrive in protocol order."""
        session, agent, handler = aff_session

        debate_task = asyncio.create_task(agent.start_debate())

        # Auto-play human turns
        async def auto_play():
            for _ in range(10):
                try:
                    turn = await handler.wait_human_turn(timeout=3)
                except asyncio.TimeoutError:
                    break
                st = turn.speech_type
                if IS_CX_SPEECH.get(st, False):
                    await session.end_cx(st)
                else:
                    await session.submit_speech(st, f"Speech for {st}", duration_seconds=60.0)
                await asyncio.sleep(0.05)

        await asyncio.gather(debate_task, auto_play())
        await handler.wait_complete(timeout=10)

        # Verify ordering: initializing < ready < first turn_signal < ... < judge < complete
        types_in_order = [e.type for e in handler.events]
        init_idx = types_in_order.index("debate_initializing")
        ready_idx = types_in_order.index("debate_ready")
        first_turn_idx = types_in_order.index("turn_signal")
        judge_idx = len(types_in_order) - 1 - types_in_order[::-1].index("judge_result")

        assert init_idx < ready_idx, "initializing must come before ready"
        assert ready_idx < first_turn_idx, "ready must come before first turn"
        assert first_turn_idx < judge_idx, "turns must come before judge result"

        await session.disconnect()


class TestFullDebateNegHuman:
    """Human plays NEG, AI plays AFF."""

    @pytest.mark.asyncio
    async def test_ai_speaks_first_as_aff(self, neg_session):
        session, agent, handler = neg_session

        debate_task = asyncio.create_task(agent.start_debate())
        await handler.wait_ready(timeout=5)

        # First turn signal should be for AC with speaker=ai (since AI is aff)
        await asyncio.sleep(0.2)
        turn_signals = handler.events_by_type.get("turn_signal", [])
        assert len(turn_signals) >= 1
        first_turn = turn_signals[0]
        assert first_turn.speech_type == "AC"
        assert first_turn.speaker == "ai"

        # Auto-play human turns
        for _ in range(10):
            try:
                turn = await handler.wait_human_turn(timeout=3)
            except asyncio.TimeoutError:
                break
            st = turn.speech_type
            if IS_CX_SPEECH.get(st, False):
                await session.end_cx(st)
            else:
                await session.submit_speech(st, f"NEG speech for {st}", duration_seconds=60.0)
            await asyncio.sleep(0.05)

        await handler.wait_complete(timeout=10)
        await debate_task

        # AI should have generated AC, 1AR, 2AR texts
        speech_texts = handler.events_by_type.get("speech_text", [])
        ai_types = {e.speech_type for e in speech_texts}
        assert "AC" in ai_types
        assert "1AR" in ai_types
        assert "2AR" in ai_types

        await session.disconnect()


class TestSpeechTimeLimits:
    """Verify time limits in turn signals match IPDA constants."""

    @pytest.mark.asyncio
    async def test_time_limits_match_constants(self, aff_session):
        session, agent, handler = aff_session

        debate_task = asyncio.create_task(agent.start_debate())

        async def auto_play():
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

        await asyncio.gather(debate_task, auto_play())
        await handler.wait_complete(timeout=10)

        for turn_event in handler.events_by_type.get("turn_signal", []):
            if turn_event.status == "complete":
                continue
            expected = SPEECH_TIME_LIMITS.get(turn_event.speech_type)
            if expected is not None:
                assert turn_event.time_limit == expected, (
                    f"{turn_event.speech_type}: expected {expected}s, got {turn_event.time_limit}s"
                )

        await session.disconnect()


class TestSpeechSideAssignment:
    """Verify speaker assignments respect side configuration."""

    @pytest.mark.asyncio
    async def test_correct_speaker_per_speech(self, aff_session):
        session, agent, handler = aff_session

        debate_task = asyncio.create_task(agent.start_debate())

        async def auto_play():
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

        await asyncio.gather(debate_task, auto_play())
        await handler.wait_complete(timeout=10)

        # Human is AFF: AFF_ACTIVE speeches → human, rest → ai
        for turn_event in handler.events_by_type.get("turn_signal", []):
            if turn_event.status == "complete":
                continue
            st = turn_event.speech_type
            expected_speaker = "human" if st in AFF_ACTIVE else "ai"
            assert turn_event.speaker == expected_speaker, (
                f"{st}: expected speaker={expected_speaker}, got {turn_event.speaker}"
            )

        await session.disconnect()

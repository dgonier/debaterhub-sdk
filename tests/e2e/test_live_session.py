"""E2E: Live integration tests — require real LiveKit + agent running.

These tests create actual LiveKit rooms and interact with the deployed
debate agent. They validate real API responses, speech generation
latency, and content quality.

Marker: slow (requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET env vars)

Run with: pytest tests/e2e/test_live_session.py -m slow --timeout=300
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from debaterhub.client import DebateClient
from debaterhub.config import DebateConfig
from debaterhub.constants import IPDA_SPEECH_ORDER, IS_CX_SPEECH, SPEECH_TIME_LIMITS
from debaterhub.events import (
    BeliefTreeEvent,
    DebateEventHandler,
    DebateReadyEvent,
    FlowUpdateEvent,
    JudgeResultEvent,
    SpeechScoredEvent,
    SpeechTextEvent,
    TurnSignalEvent,
)
from debaterhub.models import BeliefTree, FlowState, JudgeDecision

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

# Skip entire module if env vars missing
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")

if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    pytestmark.append(pytest.mark.skip(reason="LIVEKIT_* env vars not set"))


class LiveRecordingHandler(DebateEventHandler):
    """Handler for live tests — collects events and exposes async waiters."""

    def __init__(self):
        self.events = []
        self.speeches = {}
        self.judge_result = None
        self.belief_tree_event = None
        self.flow_updates = []
        self.scored_speeches = []
        self._ready = asyncio.Event()
        self._complete = asyncio.Event()
        self._tree_received = asyncio.Event()
        self._human_turns = asyncio.Queue()
        self._errors = []
        self.start_time = time.monotonic()

    def _elapsed(self):
        return round(time.monotonic() - self.start_time, 1)

    async def on_debate_initializing(self, event):
        self.events.append(event)

    async def on_debate_ready(self, event):
        self.events.append(event)
        self._ready.set()

    async def on_turn_signal(self, event):
        self.events.append(event)
        if event.speaker == "human" and event.status == "active":
            await self._human_turns.put(event)
        if event.status == "complete":
            self._complete.set()

    async def on_speech_text(self, event):
        self.events.append(event)
        self.speeches[event.speech_type] = event

    async def on_speech_progress(self, event):
        self.events.append(event)

    async def on_belief_tree(self, event):
        self.events.append(event)
        self.belief_tree_event = event
        self._tree_received.set()

    async def on_flow_update(self, event):
        self.events.append(event)
        self.flow_updates.append(event)

    async def on_coaching_hint(self, event):
        self.events.append(event)

    async def on_speech_scored(self, event):
        self.events.append(event)
        self.scored_speeches.append(event)

    async def on_cx_question(self, event):
        self.events.append(event)

    async def on_cx_answer(self, event):
        self.events.append(event)

    async def on_evidence_result(self, event):
        self.events.append(event)

    async def on_judging_started(self, event):
        self.events.append(event)

    async def on_judge_result(self, event):
        self.events.append(event)
        self.judge_result = event

    async def on_error(self, event):
        self.events.append(event)
        self._errors.append(event)

    async def on_disconnect(self, reason=""):
        pass


# Canned human speeches for deterministic tests
HUMAN_SPEECHES = {
    "AC": (
        "Universal basic income is a net positive for society. "
        "First, it eliminates extreme poverty by guaranteeing a minimum income floor. "
        "The GiveDirectly trials in Kenya showed a 42 percent reduction in days without food. "
        "Second, UBI stimulates local economies through increased consumer spending. "
        "The Roosevelt Institute projects 12 percent GDP growth over eight years. "
        "Third, UBI enables entrepreneurship by reducing the risk of starting a business. "
        "Therefore we affirm the resolution."
    ),
    "1AR": (
        "Extending the affirmative case. The negative's fiscal concerns are overblown. "
        "Consolidating existing welfare programs recovers 700 billion dollars. A modest "
        "value-added tax generates additional revenue. The Finland pilot showed no labor "
        "supply reduction. UBI complements, rather than replaces, targeted programs. "
        "The affirmative case stands on poverty elimination and economic stimulus."
    ),
    "2AR": (
        "In final rebuttal, the negative concedes that UBI eliminates poverty. Their "
        "objections about cost are differences of degree, not direction. No alternative "
        "policy achieves universal coverage. Affirm the resolution."
    ),
}


@pytest.fixture
def client():
    return DebateClient(
        livekit_url=LIVEKIT_URL,
        livekit_api_key=LIVEKIT_API_KEY,
        livekit_api_secret=LIVEKIT_API_SECRET,
    )


class TestLiveMode1:
    """Mode 1: Token-only session creation."""

    @pytest.mark.asyncio
    async def test_create_session_returns_valid_token(self, client):
        config = DebateConfig(
            topic="Resolved: Universal basic income would benefit society.",
            human_side="aff",
        )
        details = await client.create_session(config, warmup=False)

        assert details.server_url == LIVEKIT_URL
        assert details.room_name.startswith("debate-")
        assert len(details.participant_token) > 50  # JWT is long
        # JWT has 3 parts
        assert details.participant_token.count(".") == 2

        await client.close()


class TestLiveMode2:
    """Mode 2: Full managed debate session with real agent.

    This is the real deal — creates a room, dispatches the agent,
    plays human speeches, and validates the full round-trip.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(1200)  # 20 min: belief prep can take 10-15 min
    async def test_full_live_debate(self, client):
        config = DebateConfig(
            topic="Resolved: Universal basic income would benefit society.",
            human_side="aff",
            coaching_enabled=True,
            evidence_enabled=True,
            enable_scoring=True,
        )
        handler = LiveRecordingHandler()

        session = await client.create_managed_session(config, handler, warmup=False)

        try:
            # Wait for belief tree (sent during prep, before debate_ready)
            # Belief prep can take 10-15 minutes with LLM + Tavily research
            await asyncio.wait_for(handler._tree_received.wait(), timeout=900)

            # Validate belief tree structure
            assert handler.belief_tree_event is not None
            tree = handler.belief_tree_event.belief_tree
            assert isinstance(tree, BeliefTree)
            assert len(tree.beliefs) >= 2, f"Expected >=2 beliefs, got {len(tree.beliefs)}"
            assert len(tree.aff_beliefs) >= 1, "No AFF beliefs in tree"
            assert len(tree.neg_beliefs) >= 1, "No NEG beliefs in tree"
            assert len(tree.all_arguments) >= 2, "Not enough arguments"
            assert len(tree.all_evidence) >= 1, "No evidence in tree"

            # Validate evidence cards have content
            for ev in tree.all_evidence:
                assert ev.tag != "", "Evidence missing tag"
                assert ev.fulltext != "" or ev.source != "", "Evidence missing content"

            # Wait for debate ready (should come shortly after tree)
            await asyncio.wait_for(handler._ready.wait(), timeout=120)
            ready_events = [e for e in handler.events if isinstance(e, DebateReadyEvent)]
            assert len(ready_events) == 1
            assert ready_events[0].topic == config.topic

            # Play through human turns
            for _ in range(10):
                try:
                    turn = await asyncio.wait_for(handler._human_turns.get(), timeout=180)
                except asyncio.TimeoutError:
                    break

                st = turn.speech_type
                if IS_CX_SPEECH.get(st, False):
                    if st == "NC-CX":
                        # Human asks questions
                        await session.submit_cx_question("How do you fund your proposal?")
                        await asyncio.sleep(2)
                    await session.end_cx(st)
                else:
                    text = HUMAN_SPEECHES.get(st, f"Human speech for {st}.")
                    wc = len(text.split())
                    await session.submit_speech(
                        st, text,
                        duration_seconds=wc / 2.5,
                        word_count=wc,
                    )

            # Wait for completion
            await asyncio.wait_for(handler._complete.wait(), timeout=180)

            # ---- ASSERTIONS ----

            # No fatal errors
            fatal = [e for e in handler._errors if not e.recoverable]
            assert len(fatal) == 0, f"Fatal errors: {[e.message for e in fatal]}"

            # AI generated speeches with real content
            for st, speech_event in handler.speeches.items():
                assert speech_event.word_count > 50, (
                    f"{st}: AI speech too short ({speech_event.word_count} words)"
                )
                assert speech_event.word_count < 3000, (
                    f"{st}: AI speech too long ({speech_event.word_count} words)"
                )
                text_lower = speech_event.text.lower()
                assert any(kw in text_lower for kw in [
                    "ubi", "income", "poverty", "economy", "universal",
                    "basic", "argument", "evidence", "contention",
                ]), f"{st}: AI speech doesn't contain debate-relevant content"

            # Flow updates should accumulate across speeches
            assert len(handler.flow_updates) >= 1, "No flow updates received"
            last_flow = handler.flow_updates[-1].flow_state
            assert isinstance(last_flow, FlowState)

            # Speech scoring
            assert len(handler.scored_speeches) >= 1, "No scored speeches"
            for scored in handler.scored_speeches:
                assert scored.score > 0, f"{scored.speech_type}: score is 0"
                dims = scored.scoring_dimensions
                assert len(dims) >= 1, f"{scored.speech_type}: no dimensions"

            # Judge result with typed access
            assert handler.judge_result is not None
            decision = handler.judge_result.decision_detail
            assert isinstance(decision, JudgeDecision)
            assert decision.winner in ("aff", "neg")
            assert decision.aff_score > 0
            assert decision.neg_score > 0
            assert len(decision.decision) > 20
            assert len(decision.per_speech_feedback) >= 1

        finally:
            await session.disconnect()
            await client.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(1200)  # 20 min: includes belief prep time
    async def test_speech_generation_latency(self, client):
        """AI speeches should generate within reasonable time after prep."""
        config = DebateConfig(
            topic="Resolved: Space exploration is worth the cost.",
            human_side="neg",
            coaching_enabled=False,
            evidence_enabled=False,
            enable_scoring=False,
        )
        handler = LiveRecordingHandler()
        session = await client.create_managed_session(config, handler, warmup=False)

        try:
            # Wait for prep + ready (up to 15 min for belief prep)
            await asyncio.wait_for(handler._ready.wait(), timeout=900)

            # AI is AFF, so it speaks first (AC). Measure time to first speech text
            speech_start = time.monotonic()
            first_speech = None

            for _ in range(10):
                try:
                    turn = await asyncio.wait_for(handler._human_turns.get(), timeout=120)
                except asyncio.TimeoutError:
                    break

                # First human turn means AI already spoke AC
                if first_speech is None:
                    speech_events = [e for e in handler.events if isinstance(e, SpeechTextEvent)]
                    if speech_events:
                        first_speech = speech_events[0]
                        latency = time.monotonic() - speech_start
                        # AC should generate within 2 minutes (generous for cold start)
                        assert latency < 120, f"AC took {latency:.1f}s to generate"

                st = turn.speech_type
                if IS_CX_SPEECH.get(st, False):
                    await session.end_cx(st)
                else:
                    await session.submit_speech(st, f"Speech for {st}.", duration_seconds=30.0)

            await asyncio.wait_for(handler._complete.wait(), timeout=120)

        finally:
            await session.disconnect()
            await client.close()

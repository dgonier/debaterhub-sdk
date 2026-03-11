"""E2E: Tests for typed Pydantic models on events.

Validates that BeliefTree, FlowState, SpeechScore, JudgeDecision,
CoachingHint, and EvidenceCard models parse correctly from event data.

Marker: fast (simulated agent)
"""

from __future__ import annotations

import asyncio

import pytest

from debaterhub.events import (
    BeliefTreeEvent,
    CoachingHintEvent,
    FlowUpdateEvent,
    JudgeResultEvent,
    SpeechScoredEvent,
)
from debaterhub.models import (
    BeliefTree,
    CoachingHint,
    FlowState,
    JudgeDecision,
    ScoringDimension,
)

from .conftest import auto_play_remaining

pytestmark = [pytest.mark.e2e, pytest.mark.fast]


class TestBeliefTreeModel:
    """Validate typed access to the belief tree."""

    @pytest.mark.asyncio
    async def test_belief_tree_parsed_from_event(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await handler.wait_ready()

        tree_events = handler.events_by_type.get("belief_tree", [])
        assert len(tree_events) == 1

        event: BeliefTreeEvent = tree_events[0]
        tree = event.belief_tree

        assert isinstance(tree, BeliefTree)
        assert tree.topic != ""
        assert len(tree.beliefs) >= 2
        assert tree.generated_at != ""
        assert tree.prep_time_seconds > 0

        await auto_play_remaining(session, handler)
        await handler.wait_complete()

    @pytest.mark.asyncio
    async def test_belief_tree_has_both_sides(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await handler.wait_ready()

        tree = handler.events_by_type["belief_tree"][0].belief_tree

        assert len(tree.aff_beliefs) >= 1
        assert len(tree.neg_beliefs) >= 1

        await auto_play_remaining(session, handler)
        await handler.wait_complete()

    @pytest.mark.asyncio
    async def test_arguments_have_evidence(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await handler.wait_ready()

        tree = handler.events_by_type["belief_tree"][0].belief_tree

        all_args = tree.all_arguments
        assert len(all_args) >= 2

        all_evidence = tree.all_evidence
        assert len(all_evidence) >= 2

        # Check evidence fields
        for ev in all_evidence:
            assert ev.tag != ""
            assert ev.fulltext != ""
            assert ev.source != ""

        await auto_play_remaining(session, handler)
        await handler.wait_complete()

    @pytest.mark.asyncio
    async def test_evidence_card_fields(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await handler.wait_ready()

        tree = handler.events_by_type["belief_tree"][0].belief_tree
        ev = tree.all_evidence[0]

        assert ev.cite != ""
        assert ev.fullcite != ""
        assert len(ev.selected_texts) >= 1
        assert ev.source_url != ""

        await auto_play_remaining(session, handler)
        await handler.wait_complete()

    @pytest.mark.asyncio
    async def test_argument_structure(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await handler.wait_ready()

        tree = handler.events_by_type["belief_tree"][0].belief_tree
        arg = tree.all_arguments[0]

        assert arg.id != ""
        assert arg.claim != ""
        assert arg.warrant != ""
        assert arg.impact != ""
        assert arg.label != ""

        await auto_play_remaining(session, handler)
        await handler.wait_complete()


class TestFlowStateModel:
    """Validate typed access to flow updates."""

    @pytest.mark.asyncio
    async def test_flow_state_parsed(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()

        # Play through until we get flow updates
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        flow_events = handler.events_by_type.get("flow_update", [])
        assert len(flow_events) >= 1

        event: FlowUpdateEvent = flow_events[0]
        flow = event.flow_state

        assert isinstance(flow, FlowState)
        assert len(flow.arguments) >= 1

    @pytest.mark.asyncio
    async def test_flow_arguments_typed(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        flow = handler.events_by_type["flow_update"][0].flow_state
        arg = flow.arguments[0]

        assert arg.id != ""
        assert arg.label != ""
        assert arg.side in ("aff", "neg")
        assert arg.status in ("standing", "attacked", "dropped", "extended", "turned")
        assert arg.speech_introduced != ""

    @pytest.mark.asyncio
    async def test_flow_voting_issues(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        flow = handler.events_by_type["flow_update"][0].flow_state

        assert len(flow.voting_issues) >= 1
        vi = flow.voting_issues[0]
        assert vi.label != ""
        assert vi.description != ""

    @pytest.mark.asyncio
    async def test_flow_clash_points(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        flow = handler.events_by_type["flow_update"][0].flow_state

        assert len(flow.clash_points) >= 1
        cp = flow.clash_points[0]
        assert cp.label != ""
        assert cp.status != ""

    @pytest.mark.asyncio
    async def test_flow_filter_properties(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        flow = handler.events_by_type["flow_update"][0].flow_state

        standing = flow.standing_arguments
        assert len(standing) >= 1
        assert all(a.status == "standing" for a in standing)

        aff_args = flow.aff_arguments
        assert all(a.side == "aff" for a in aff_args)


class TestSpeechScoreModel:
    """Validate typed access to speech scores."""

    @pytest.mark.asyncio
    async def test_scoring_dimensions_parsed(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        scored_events = handler.events_by_type.get("speech_scored", [])
        assert len(scored_events) >= 1

        event: SpeechScoredEvent = scored_events[0]
        dims = event.scoring_dimensions

        assert len(dims) == 4
        for d in dims:
            assert isinstance(d, ScoringDimension)
            assert d.name != ""
            assert 0.0 <= d.score <= 1.0
            assert d.max_score > 0
            assert d.reasoning != ""

    @pytest.mark.asyncio
    async def test_speech_score_model(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        event: SpeechScoredEvent = handler.events_by_type["speech_scored"][0]
        score = event.speech_score

        assert score.speech_type != ""
        assert score.score > 0
        assert score.feedback != ""
        assert len(score.dimensions) == 4
        assert "argument_quality" in score.dimension_map

    @pytest.mark.asyncio
    async def test_normalized_score(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        dim = handler.events_by_type["speech_scored"][0].scoring_dimensions[0]
        assert 0.0 <= dim.normalized_score <= 1.0


class TestJudgeDecisionModel:
    """Validate typed access to judge decisions."""

    @pytest.mark.asyncio
    async def test_judge_decision_parsed(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        judge_events = handler.events_by_type.get("judge_result", [])
        assert len(judge_events) == 1

        event: JudgeResultEvent = judge_events[0]
        decision = event.decision_detail

        assert isinstance(decision, JudgeDecision)
        assert decision.winner in ("aff", "neg")
        assert decision.aff_score > 0
        assert decision.neg_score > 0
        assert decision.decision != ""
        assert len(decision.voting_issues) >= 1

    @pytest.mark.asyncio
    async def test_per_speech_feedback(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        decision = handler.events_by_type["judge_result"][0].decision_detail

        assert len(decision.per_speech_feedback) >= 2

        ac_fb = decision.feedback_for("AC")
        assert ac_fb is not None
        assert ac_fb.score > 0
        assert ac_fb.feedback != ""
        assert len(ac_fb.strengths) >= 1
        assert len(ac_fb.weaknesses) >= 1

    @pytest.mark.asyncio
    async def test_feedback_for_shortcut(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        event: JudgeResultEvent = handler.events_by_type["judge_result"][0]

        # Shortcut on the event itself
        nc_fb = event.feedback_for("NC")
        assert nc_fb is not None
        assert nc_fb.speech_type == "NC"

        # Non-existent speech returns None
        assert event.feedback_for("XYZ") is None

    @pytest.mark.asyncio
    async def test_spread_property(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        decision = handler.events_by_type["judge_result"][0].decision_detail
        assert decision.spread == abs(decision.aff_score - decision.neg_score)


class TestCoachingHintModel:
    """Validate typed access to coaching hints."""

    @pytest.mark.asyncio
    async def test_coaching_hints_parsed(self, aff_session):
        session, agent, handler = aff_session
        await agent.start_debate()
        await auto_play_remaining(session, handler)
        await handler.wait_complete()

        hint_events = handler.events_by_type.get("coaching_hint", [])
        assert len(hint_events) >= 1

        event: CoachingHintEvent = hint_events[0]
        hints = event.coaching_hints

        assert len(hints) >= 1
        for h in hints:
            assert isinstance(h, CoachingHint)
            assert h.text != ""

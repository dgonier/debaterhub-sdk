"""Typed event models for server → client messages.

Each event wraps the normalised dict from :func:`protocol.parse_server_message`
and exposes typed fields for the most commonly used values. The full raw payload
is always available via :attr:`raw`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .protocol import register_event


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class DebateEvent(BaseModel):
    """Base class for all debate events."""

    model_config = ConfigDict(extra="allow")

    type: str
    raw: Dict[str, Any] = Field(default_factory=dict, exclude=True)


# ---------------------------------------------------------------------------
# Typed event subclasses
# ---------------------------------------------------------------------------

class DebateInitializingEvent(DebateEvent):
    type: str = "debate_initializing"
    topic: str = ""
    human_side: str = ""
    message: str = ""
    estimated_seconds: float = 30.0


class DebateReadyEvent(DebateEvent):
    type: str = "debate_ready"
    topic: str = ""
    human_side: str = ""
    speech_order: List[str] = Field(default_factory=list)
    speech_time_limits: Dict[str, int] = Field(default_factory=dict)
    evidence_cards: List[Dict[str, Any]] = Field(default_factory=list)
    belief_tree_summary: str = ""


class TurnSignalEvent(DebateEvent):
    type: str = "turn_signal"
    speech_type: str = ""
    speaker: str = ""
    is_cx: bool = False
    time_limit: int = 0
    speech_index: int = 0
    total_speeches: int = 7
    status: str = "active"


class SpeechTextEvent(DebateEvent):
    type: str = "speech_text"
    speech_type: str = ""
    text: str = ""
    word_count: int = 0


class SpeechProgressEvent(DebateEvent):
    """Intermediate progress during AI speech generation."""
    type: str = "speech_progress"
    speech_type: str = ""
    stage: str = ""
    message: str = ""


class FlowUpdateEvent(DebateEvent):
    type: str = "flow_update"
    speech_type: str = ""
    flow: Dict[str, Any] = Field(default_factory=dict)


class CoachingHintEvent(DebateEvent):
    type: str = "coaching_hint"
    for_speech: str = ""
    hints: List[Dict[str, Any]] = Field(default_factory=list)


class SpeechScoredEvent(DebateEvent):
    type: str = "speech_scored"
    speech_type: str = ""
    score: float = 0.0
    feedback: str = ""
    dimensions: List[Dict[str, Any]] = Field(default_factory=list)


class CXQuestionEvent(DebateEvent):
    type: str = "cx_question_server"
    question: str = ""
    turn_number: int = 0
    strategy: str = ""


class CXAnswerEvent(DebateEvent):
    type: str = "cx_answer_server"
    answer: str = ""
    question_ref: Optional[str] = None


class EvidenceResultEvent(DebateEvent):
    type: str = "evidence_result"
    query: str = ""
    cards: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0


class JudgingStartedEvent(DebateEvent):
    type: str = "judging_started"
    message: str = ""
    estimated_seconds: float = 30.0


class JudgeResultEvent(DebateEvent):
    type: str = "judge_result"
    winner: str = ""
    aff_score: float = 0.0
    neg_score: float = 0.0
    margin: str = "close"
    decision: str = ""
    voting_issues: List[str] = Field(default_factory=list)
    per_speech_feedback: List[Dict[str, Any]] = Field(default_factory=list)


class ErrorEvent(DebateEvent):
    type: str = "error"
    message: str = ""
    code: str = "UNKNOWN"
    recoverable: bool = True


class BeliefTreeEvent(DebateEvent):
    type: str = "belief_tree"
    tree: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ALL_EVENTS: list[type[DebateEvent]] = [
    DebateInitializingEvent,
    DebateReadyEvent,
    TurnSignalEvent,
    SpeechTextEvent,
    SpeechProgressEvent,
    FlowUpdateEvent,
    CoachingHintEvent,
    SpeechScoredEvent,
    CXQuestionEvent,
    CXAnswerEvent,
    EvidenceResultEvent,
    JudgingStartedEvent,
    JudgeResultEvent,
    ErrorEvent,
    BeliefTreeEvent,
]

for _cls in _ALL_EVENTS:
    register_event(_cls.model_fields["type"].default, _cls)


def event_from_dict(data: Dict[str, Any]) -> DebateEvent:
    """Construct a typed event from a normalised message dict.

    Falls back to the generic :class:`DebateEvent` for unknown types.
    """
    from .protocol import get_event_class

    type_str = data.get("type", "")
    cls = get_event_class(type_str) or DebateEvent
    return cls(raw=data, **{k: v for k, v in data.items() if k != "raw"})


# ---------------------------------------------------------------------------
# Handler base class
# ---------------------------------------------------------------------------

class DebateEventHandler:
    """Override any method to handle specific events.

    All methods are async no-ops by default.
    """

    async def on_debate_initializing(self, event: DebateInitializingEvent) -> None: ...
    async def on_debate_ready(self, event: DebateReadyEvent) -> None: ...
    async def on_turn_signal(self, event: TurnSignalEvent) -> None: ...
    async def on_speech_text(self, event: SpeechTextEvent) -> None: ...
    async def on_speech_progress(self, event: SpeechProgressEvent) -> None: ...
    async def on_flow_update(self, event: FlowUpdateEvent) -> None: ...
    async def on_coaching_hint(self, event: CoachingHintEvent) -> None: ...
    async def on_speech_scored(self, event: SpeechScoredEvent) -> None: ...
    async def on_cx_question(self, event: CXQuestionEvent) -> None: ...
    async def on_cx_answer(self, event: CXAnswerEvent) -> None: ...
    async def on_evidence_result(self, event: EvidenceResultEvent) -> None: ...
    async def on_judging_started(self, event: JudgingStartedEvent) -> None: ...
    async def on_judge_result(self, event: JudgeResultEvent) -> None: ...
    async def on_error(self, event: ErrorEvent) -> None: ...
    async def on_belief_tree(self, event: BeliefTreeEvent) -> None: ...
    async def on_unknown(self, event: DebateEvent) -> None: ...
    async def on_disconnect(self, reason: str = "") -> None: ...


# Map type string → handler method name
EVENT_HANDLER_MAP: Dict[str, str] = {
    "debate_initializing": "on_debate_initializing",
    "debate_ready": "on_debate_ready",
    "turn_signal": "on_turn_signal",
    "speech_text": "on_speech_text",
    "speech_progress": "on_speech_progress",
    "flow_update": "on_flow_update",
    "coaching_hint": "on_coaching_hint",
    "speech_scored": "on_speech_scored",
    "cx_question_server": "on_cx_question",
    "cx_answer_server": "on_cx_answer",
    "evidence_result": "on_evidence_result",
    "judging_started": "on_judging_started",
    "judge_result": "on_judge_result",
    "error": "on_error",
    "belief_tree": "on_belief_tree",
}

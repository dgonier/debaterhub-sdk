"""Structured Pydantic models for debate data.

These models provide typed access to belief trees, flow state, evidence,
coaching hints, speech scores, and judge decisions. They map directly to
the wire-format JSON emitted by the debate agent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Belief Tree
# ---------------------------------------------------------------------------

class EvidenceCard(BaseModel):
    """A piece of evidence supporting an argument."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    tag: str = ""
    fulltext: str = Field(default="", alias="fullText")
    source: str = ""
    cite: str = ""
    fullcite: str = Field(default="", alias="fullCite")
    selected_texts: List[str] = Field(default_factory=list, alias="selectedTexts")
    source_url: str = Field(default="", alias="sourceUrl")


class Argument(BaseModel):
    """A single argument within a belief."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    claim: str = ""
    warrant: str = ""
    impact: str = ""
    evidence: List[EvidenceCard] = Field(default_factory=list)
    label: str = ""


class Belief(BaseModel):
    """A top-level belief in the tree (e.g. a contention)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    label: str = ""
    claim: str = ""
    side: str = ""
    arguments: List[Argument] = Field(default_factory=list)


class BeliefTree(BaseModel):
    """Full belief tree generated during debate prep.

    Access via ``BeliefTreeEvent.belief_tree``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    beliefs: List[Belief] = Field(default_factory=list)
    topic: str = ""
    generated_at: str = Field(default="", alias="generatedAt")
    prep_time_seconds: float = Field(default=0.0, alias="prepTimeSeconds")

    @property
    def aff_beliefs(self) -> List[Belief]:
        return [b for b in self.beliefs if b.side == "aff"]

    @property
    def neg_beliefs(self) -> List[Belief]:
        return [b for b in self.beliefs if b.side == "neg"]

    @property
    def all_arguments(self) -> List[Argument]:
        return [a for b in self.beliefs for a in b.arguments]

    @property
    def all_evidence(self) -> List[EvidenceCard]:
        return [e for a in self.all_arguments for e in a.evidence]


# ---------------------------------------------------------------------------
# Flow State
# ---------------------------------------------------------------------------

class ArgumentStatus(str, Enum):
    STANDING = "standing"
    ATTACKED = "attacked"
    DROPPED = "dropped"
    EXTENDED = "extended"
    TURNED = "turned"


class FlowArgument(BaseModel):
    """An argument as tracked in the flow."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    label: str = ""
    full_text: str = Field(default="", alias="fullText")
    side: str = ""
    status: str = "standing"
    speech_introduced: str = Field(default="", alias="speechIntroduced")
    responses: List[str] = Field(default_factory=list)
    warrant: str = ""
    impact: str = ""
    evidence_tag: str = Field(default="", alias="evidenceTag")
    argument_category: str = Field(default="", alias="argumentCategory")
    attack_type: str = Field(default="", alias="attackType")
    attacks: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = Field(default=None, alias="parentId")


class VotingIssue(BaseModel):
    """A key voting issue identified in the flow."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    label: str = ""
    description: str = ""
    aff_position: str = Field(default="", alias="affPosition")
    neg_position: str = Field(default="", alias="negPosition")
    advantage: str = ""


class ClashPoint(BaseModel):
    """A point of direct clash between sides."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = ""
    label: str = ""
    aff_argument_id: str = Field(default="", alias="affArgumentId")
    neg_argument_id: str = Field(default="", alias="negArgumentId")
    status: str = ""


class FlowState(BaseModel):
    """Full flow state after a speech.

    Access via ``FlowUpdateEvent.flow_state``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    arguments: List[FlowArgument] = Field(default_factory=list)
    voting_issues: List[VotingIssue] = Field(default_factory=list, alias="votingIssues")
    clash_points: List[ClashPoint] = Field(default_factory=list, alias="clashPoints")
    summary: str = ""

    # Legacy flat format support
    standing: List[str] = Field(default_factory=list)
    attacked: List[str] = Field(default_factory=list)
    dropped: List[str] = Field(default_factory=list)

    @property
    def standing_arguments(self) -> List[FlowArgument]:
        return [a for a in self.arguments if a.status == "standing"]

    @property
    def attacked_arguments(self) -> List[FlowArgument]:
        return [a for a in self.arguments if a.status == "attacked"]

    @property
    def dropped_arguments(self) -> List[FlowArgument]:
        return [a for a in self.arguments if a.status == "dropped"]

    @property
    def aff_arguments(self) -> List[FlowArgument]:
        return [a for a in self.arguments if a.side == "aff"]

    @property
    def neg_arguments(self) -> List[FlowArgument]:
        return [a for a in self.arguments if a.side == "neg"]


# ---------------------------------------------------------------------------
# Speech Scoring
# ---------------------------------------------------------------------------

class ScoringDimension(BaseModel):
    """A single scoring dimension for a speech."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = ""
    score: float = 0.0
    max_score: float = Field(default=1.0, alias="maxScore")
    reasoning: str = ""

    @property
    def normalized_score(self) -> float:
        if self.max_score == 0:
            return 0.0
        return self.score / self.max_score


class SpeechScore(BaseModel):
    """Detailed scoring for a single speech."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    speech_type: str = Field(default="", alias="speechType")
    score: float = 0.0
    feedback: str = ""
    dimensions: List[ScoringDimension] = Field(default_factory=list)

    @property
    def dimension_map(self) -> Dict[str, ScoringDimension]:
        return {d.name: d for d in self.dimensions}


# ---------------------------------------------------------------------------
# Judge Decision
# ---------------------------------------------------------------------------

class PerSpeechFeedback(BaseModel):
    """Judge feedback for a single speech."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    speech_type: str = Field(default="", alias="speechType")
    score: float = 0.0
    max_score: float = Field(default=1.0, alias="maxScore")
    feedback: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)


class JudgeDecision(BaseModel):
    """Full judge decision including per-speech feedback.

    Access via ``JudgeResultEvent.decision_detail``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    winner: str = ""
    aff_score: float = Field(default=0.0, alias="affScore")
    neg_score: float = Field(default=0.0, alias="negScore")
    margin: str = "close"
    decision: str = ""
    voting_issues: List[str] = Field(default_factory=list, alias="votingIssues")
    per_speech_feedback: List[PerSpeechFeedback] = Field(
        default_factory=list, alias="perSpeechFeedback"
    )

    @property
    def spread(self) -> float:
        return abs(self.aff_score - self.neg_score)

    def feedback_for(self, speech_type: str) -> Optional[PerSpeechFeedback]:
        for fb in self.per_speech_feedback:
            if fb.speech_type == speech_type:
                return fb
        return None


# ---------------------------------------------------------------------------
# Coaching
# ---------------------------------------------------------------------------

class CoachingPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CoachingCategory(str, Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    EXTEND = "extend"
    FRAMEWORK = "framework"
    VOTING = "voting"
    CX = "cx"
    GENERAL = "general"


class CoachingHint(BaseModel):
    """A single coaching hint."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    text: str = ""
    type: str = ""
    priority: str = "medium"
    category: str = "general"
    related_argument: Optional[str] = Field(default=None, alias="relatedArgument")

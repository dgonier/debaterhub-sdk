"""Page-grouped flow data schema.

This is the wire contract between flow generation (server side, DSPy in
packages/debate/flow/flow_generator.py) and the frontend flow grid
(apps/front/components/debate/flow/types.ts).

The shape is **page-grouped** (arguments clustered into flow pages per speech),
distinct from the flat `FlowState` in models.py which is used for live
rebuttal planning during a running debate.

Keep field names and aliases in sync with:
    apps/front/components/debate/flow/types.ts
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Side = Literal["aff", "neg"]
FlowStatus = Literal["draft", "generating", "complete", "published"]


class PageEvidenceCard(BaseModel):
    """Evidence card attached to a page flow argument.

    Mirrors frontend EvidenceCard (components/debate/flow/types.ts).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    citation: str = ""
    tag: Optional[str] = None
    text: str = ""
    source_url: Optional[str] = Field(default=None, alias="sourceUrl")
    source_document_id: Optional[str] = Field(default=None, alias="sourceDocumentId")


class PageFlowArgument(BaseModel):
    """An argument as it appears on a single flow page for a single speech.

    Named `PageFlowArgument` to avoid clashing with the flat live-flow
    `FlowArgument` in models.py. They are different shapes with different
    use cases.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    tag: str
    argument_type: str = Field(default="", alias="argumentType")
    content: str = ""
    word_count: int = Field(default=0, alias="wordCount")
    answered: bool = False
    is_dropped: bool = Field(default=False, alias="isDropped")
    rebuttal_to_id: Optional[str] = Field(default=None, alias="rebuttalToId")
    order: int = 0
    script: Optional[str] = None
    evidence_cards: List[PageEvidenceCard] = Field(
        default_factory=list, alias="evidenceCards"
    )


class FlowPageSpeech(BaseModel):
    """A single speech's slot within a flow page."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    speech_name: str = Field(alias="speechName")
    word_allocation: int = Field(default=0, alias="wordAllocation")
    arguments: List[PageFlowArgument] = Field(default_factory=list)
    order: int = 0


class FlowPage(BaseModel):
    """A single flow page (e.g. an advantage, DA, kritik) across all speeches."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    name: str
    page_type: str = Field(alias="pageType")
    order: int = 0
    is_dropped: bool = Field(default=False, alias="isDropped")
    side: Side
    speeches: List[FlowPageSpeech] = Field(default_factory=list)


class CXExchange(BaseModel):
    """A single question/answer turn inside a cross-examination period.

    Rendered as a chat bubble in the CX panel below the flow grid.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    turn: Literal["Q", "A"]
    speaker: Side
    text: str
    order: int = 0


class CXPeriod(BaseModel):
    """All exchanges in a single CX period (e.g. CX1, CX2)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    speech_name: str = Field(alias="speechName")
    asker: Side
    answerer: Side
    exchanges: List[CXExchange] = Field(default_factory=list)


class FlowData(BaseModel):
    """Complete page-grouped flow for a debate.

    Mirrors frontend FlowData. This is the outer envelope both user-filled
    and system-generated flows round-trip through.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    topic: str
    format: str = "ipda"
    status: FlowStatus = "complete"
    pages: List[FlowPage] = Field(default_factory=list)
    speeches: List[str] = Field(default_factory=list)
    cx_periods: List[CXPeriod] = Field(
        default_factory=list,
        alias="cxPeriods",
        description="CX periods, kept separate from pages so the UI can render them as a chat panel.",
    )
    created_at: str = Field(default="", alias="createdAt")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")


class FlowGenerateRequest(BaseModel):
    """Request payload for POST /generate_flow.

    The caller provides the transcripts; the server extracts arguments,
    groups into pages, and links rebuttals.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    topic: str
    format: str = "ipda"
    debate_id: str = Field(default="", alias="debateId")
    speeches: List["SpeechTranscript"] = Field(default_factory=list)


class SpeechTranscript(BaseModel):
    """A single speech transcript used as input to flow generation."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    speech_name: str = Field(alias="speechName")
    side: Side
    text: str
    is_cx: bool = Field(default=False, alias="isCx")


FlowGenerateRequest.model_rebuild()


__all__ = [
    "Side",
    "FlowStatus",
    "PageEvidenceCard",
    "PageFlowArgument",
    "FlowPageSpeech",
    "FlowPage",
    "CXExchange",
    "CXPeriod",
    "FlowData",
    "FlowGenerateRequest",
    "SpeechTranscript",
]

"""Configuration models for the debaterhub SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from .exceptions import ConfigValidationError
from .formats import FORMAT_REGISTRY


class DebateClientConfig(BaseModel):
    """Credentials and endpoints needed by :class:`DebateClient`."""

    livekit_url: str = Field(description="wss:// URL of the LiveKit server")
    livekit_api_key: str
    livekit_api_secret: str
    agent_name: str = Field(
        default="human-debate-agent",
        description="Name of the deployed LiveKit agent to dispatch",
    )
    warmup_url: Optional[str] = Field(
        default=None,
        description="Optional Modal warmup endpoint URL",
    )


class DebateConfig(BaseModel):
    """Per-debate configuration passed to the agent via dispatch metadata.

    Supports two modes:
    - ``"ai_human"`` (default): one side is human, one is AI
    - ``"ai_ai"``: both sides are AI-generated
    """

    topic: str = Field(min_length=1)
    debate_mode: str = Field(default="ai_human", pattern=r"^(ai_human|ai_ai)$")
    human_side: str = Field(default="aff", pattern=r"^(aff|neg)$")
    format: str = Field(default="ipda", description="ipda | ld | pf")

    # Feature flags (all on by default)
    coaching_enabled: bool = True
    evidence_enabled: bool = True
    enable_prep: bool = True
    enable_flow_study: bool = True
    enable_scoring: bool = True

    # Prep wizard / case reuse
    ai_case_mode: Optional[str] = Field(default=None, description="generate or reuse")
    ai_reuse_case_id: Optional[str] = None
    ai_reuse_mode: Optional[str] = Field(default=None, description="blind or select")
    human_speech_text: Optional[str] = None

    # PF-only: which side speaks first (typically coin-flipped). Ignored for
    # other formats. Defaults to None (callers can set it for PF).
    pf_first_speaker: Optional[str] = Field(
        default=None,
        pattern=r"^(aff|neg)$",
        description="For PF only: which side speaks first (coin flip).",
    )

    @model_validator(mode="after")
    def _validate_config(self) -> "DebateConfig":
        if self.format.lower() not in FORMAT_REGISTRY:
            raise ConfigValidationError(
                f"Unknown format '{self.format}'. "
                f"Known: {sorted(FORMAT_REGISTRY.keys())}"
            )
        if self.debate_mode == "ai_human":
            if self.human_side not in ("aff", "neg"):
                raise ConfigValidationError(
                    f"human_side must be 'aff' or 'neg', got {self.human_side!r}"
                )
        return self

    @property
    def is_ai_ai(self) -> bool:
        return self.debate_mode == "ai_ai"

    def to_dispatch_metadata(self) -> Dict[str, Any]:
        """Serialize to the dict the orchestrator agent expects.

        Emits BOTH snake_case and camelCase keys so the agent can read
        either format (see orchestrator_agent.py metadata parsing).
        """
        fmt = self.format.lower()
        d: Dict[str, Any] = {
            # snake_case
            "topic": self.topic,
            "debate_mode": self.debate_mode,
            "human_side": self.human_side,
            "format": fmt,
            "coaching_enabled": self.coaching_enabled,
            "evidence_enabled": self.evidence_enabled,
            "enable_prep": self.enable_prep,
            "enable_flow_study": self.enable_flow_study,
            "enable_scoring": self.enable_scoring,
            # camelCase duplicates
            "debateMode": self.debate_mode,
            "humanSide": self.human_side,
            "coachingEnabled": self.coaching_enabled,
            "evidenceEnabled": self.evidence_enabled,
            "enablePrep": self.enable_prep,
            "enableFlowStudy": self.enable_flow_study,
            "enableScoring": self.enable_scoring,
        }
        # Prep wizard fields (only include when set)
        _extra: dict[str, tuple[str, str]] = {
            "ai_case_mode": ("ai_case_mode", "aiCaseMode"),
            "ai_reuse_case_id": ("ai_reuse_case_id", "aiReuseCaseId"),
            "ai_reuse_mode": ("ai_reuse_mode", "aiReuseMode"),
            "human_speech_text": ("human_speech_text", "humanSpeechText"),
        }
        for attr, (snake, camel) in _extra.items():
            val = getattr(self, attr)
            if val is not None:
                d[snake] = val
                d[camel] = val
        # PF-only first-speaker selector
        if self.pf_first_speaker is not None:
            d["pf_first_speaker"] = self.pf_first_speaker
            d["pfFirstSpeaker"] = self.pf_first_speaker
        return d


class ConnectionDetails(BaseModel):
    """Returned by :meth:`DebateClient.create_session` (Mode 1)."""

    server_url: str
    room_name: str
    participant_token: str

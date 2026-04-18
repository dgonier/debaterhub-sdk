"""Local turn state machine for tracking debate progress."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .formats import FormatSpec, get_format_spec


@dataclass
class DebateTurnTracker:
    """Tracks the current debate turn and records transcripts.

    Updated from :class:`TurnSignalEvent` payloads. Consults the
    format registry for speech order, side ownership, and CX semantics.
    """

    human_side: str = "aff"
    debate_mode: str = "ai_human"
    format: str = "ipda"
    _current_speech: Optional[str] = field(default=None, repr=False)
    _current_speaker: Optional[str] = field(default=None, repr=False)
    _speech_index: int = field(default=0, repr=False)
    _status: str = field(default="waiting", repr=False)
    _transcripts: Dict[str, str] = field(default_factory=dict, repr=False)

    # --- Format ---

    @property
    def format_spec(self) -> FormatSpec:
        return get_format_spec(self.format)

    # --- Properties ---

    @property
    def current_speech(self) -> Optional[str]:
        return self._current_speech

    @property
    def current_speaker(self) -> Optional[str]:
        return self._current_speaker

    @property
    def speech_index(self) -> int:
        return self._speech_index

    @property
    def phase(self) -> str:
        """One of: waiting, active, prep_time, complete."""
        return self._status

    @property
    def is_human_turn(self) -> bool:
        if self.debate_mode == "ai_ai":
            return False
        if self._current_speech is None:
            return False
        fmt = self.format_spec
        if self.human_side == "aff":
            return self._current_speech in fmt.aff_active
        return self._current_speech in fmt.neg_active

    @property
    def is_cx(self) -> bool:
        if self._current_speech is None:
            return False
        return self.format_spec.is_cx_speech.get(self._current_speech, False)

    @property
    def is_complete(self) -> bool:
        return self._status == "complete"

    @property
    def transcripts(self) -> Dict[str, str]:
        return dict(self._transcripts)

    @property
    def completed_speeches(self) -> List[str]:
        order = self.format_spec.speech_ids
        return [s for s in order if s in self._transcripts]

    # --- Mutators ---

    def update_from_turn_signal(
        self,
        speech_type: str,
        speaker: str,
        speech_index: int = 0,
        status: str = "active",
        **_kwargs: object,
    ) -> None:
        """Apply a turn-signal payload to update state."""
        self._current_speech = speech_type
        self._current_speaker = speaker
        self._speech_index = speech_index
        self._status = status

    def record_speech(self, speech_type: str, transcript: str) -> None:
        """Record a completed speech transcript."""
        self._transcripts[speech_type] = transcript

    def get_side_for_speech(self, speech_type: str) -> str:
        sides = self.format_spec.speech_side
        return sides.get(speech_type, "unknown")

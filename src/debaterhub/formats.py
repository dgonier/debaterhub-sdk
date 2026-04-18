"""Client-side mirror of the backend format registry.

Exposes only the fields a UI needs: speech ids, timings, side labels,
display names. Does NOT include prompt preambles or judge weights --
those live server-side only.

Kept in sync manually with packages/debate/formats/ in the monorepo.
If backend specs change, this file must be updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Side = Literal["aff", "neg", "both"]


@dataclass(frozen=True)
class SpeechSpec:
    """A single speech (or CX/crossfire period) within a debate format."""

    id: str
    display_name: str
    side: Side
    time_limit_sec: int
    is_cx: bool = False
    cx_asker: Optional[Side] = None
    word_budget: int = 0


@dataclass(frozen=True)
class FormatSpec:
    """Client-visible specification of a debate format."""

    id: str
    display_name: str
    speech_order: tuple[SpeechSpec, ...]
    prep_time_sec: int = 0
    first_speaker_configurable: bool = False

    @property
    def speech_ids(self) -> list[str]:
        return [s.id for s in self.speech_order]

    @property
    def speech_time_limits(self) -> dict[str, int]:
        return {s.id: s.time_limit_sec for s in self.speech_order}

    @property
    def aff_speeches(self) -> set[str]:
        return {s.id for s in self.speech_order if s.side == "aff" and not s.is_cx}

    @property
    def neg_speeches(self) -> set[str]:
        return {s.id for s in self.speech_order if s.side == "neg" and not s.is_cx}

    @property
    def aff_active(self) -> set[str]:
        """Speeches where AFF speaks or asks CX / participates in crossfire."""
        out: set[str] = set()
        for s in self.speech_order:
            if s.side == "aff" and not s.is_cx:
                out.add(s.id)
            elif s.is_cx and s.side == "both":
                out.add(s.id)
            elif s.is_cx and s.cx_asker == "aff":
                out.add(s.id)
        return out

    @property
    def neg_active(self) -> set[str]:
        """Speeches where NEG speaks or asks CX / participates in crossfire."""
        out: set[str] = set()
        for s in self.speech_order:
            if s.side == "neg" and not s.is_cx:
                out.add(s.id)
            elif s.is_cx and s.side == "both":
                out.add(s.id)
            elif s.is_cx and s.cx_asker == "neg":
                out.add(s.id)
        return out

    @property
    def is_cx_speech(self) -> dict[str, bool]:
        return {s.id: s.is_cx for s in self.speech_order}

    @property
    def speech_side(self) -> dict[str, str]:
        """Who is *active* for each speech.

        For non-CX speeches this is the owning side ("aff" or "neg").
        For CX periods this is the asker (opposing side).
        For two-way crossfires (side="both") this is "both".
        """
        out: dict[str, str] = {}
        for s in self.speech_order:
            if s.is_cx:
                if s.side == "both":
                    out[s.id] = "both"
                elif s.cx_asker is not None:
                    out[s.id] = s.cx_asker
                else:
                    out[s.id] = s.side
            else:
                out[s.id] = s.side
        return out

    def get_speech(self, speech_id: str) -> SpeechSpec:
        for s in self.speech_order:
            if s.id == speech_id:
                return s
        raise KeyError(f"Unknown speech '{speech_id}' in format '{self.id}'")


# ---------------------------------------------------------------------------
# IPDA
# ---------------------------------------------------------------------------
IPDA_SPEC = FormatSpec(
    id="ipda",
    display_name="IPDA",
    speech_order=(
        SpeechSpec("AC", "Affirmative Constructive", "aff", 300, word_budget=800),
        SpeechSpec("AC-CX", "AC Cross-Examination", "aff", 180, is_cx=True, cx_asker="neg"),
        SpeechSpec("NC", "Negative Constructive", "neg", 360, word_budget=800),
        SpeechSpec("NC-CX", "NC Cross-Examination", "neg", 180, is_cx=True, cx_asker="aff"),
        SpeechSpec("1AR", "First Affirmative Rebuttal", "aff", 300, word_budget=500),
        SpeechSpec("NR", "Negative Rebuttal", "neg", 300, word_budget=500),
        SpeechSpec("2AR", "Second Affirmative Rebuttal", "aff", 180, word_budget=400),
    ),
)

# ---------------------------------------------------------------------------
# Lincoln-Douglas
# ---------------------------------------------------------------------------
LD_SPEC = FormatSpec(
    id="ld",
    display_name="Lincoln-Douglas",
    speech_order=(
        SpeechSpec("AC", "Affirmative Constructive (1AC)", "aff", 360, word_budget=900),
        SpeechSpec("AC-CX", "AC Cross-Examination", "aff", 180, is_cx=True, cx_asker="neg"),
        SpeechSpec("NC", "Negative Constructive (1NC)", "neg", 420, word_budget=1050),
        SpeechSpec("NC-CX", "NC Cross-Examination", "neg", 180, is_cx=True, cx_asker="aff"),
        SpeechSpec("1AR", "First Affirmative Rebuttal", "aff", 240, word_budget=600),
        SpeechSpec("NR", "Negative Rebuttal (NR/2NR)", "neg", 360, word_budget=900),
        SpeechSpec("2AR", "Second Affirmative Rebuttal", "aff", 180, word_budget=450),
    ),
    prep_time_sec=240,
)

# ---------------------------------------------------------------------------
# Public Forum
# ---------------------------------------------------------------------------
PF_SPEC = FormatSpec(
    id="pf",
    display_name="Public Forum",
    speech_order=(
        SpeechSpec("PF-AC", "Affirmative Constructive", "aff", 240, word_budget=600),
        SpeechSpec("PF-NC", "Negative Constructive", "neg", 240, word_budget=600),
        SpeechSpec("PF-CF1", "Crossfire 1", "both", 180, is_cx=True),
        SpeechSpec("PF-AR", "Affirmative Rebuttal", "aff", 240, word_budget=600),
        SpeechSpec("PF-NR", "Negative Rebuttal", "neg", 240, word_budget=600),
        SpeechSpec("PF-CF2", "Crossfire 2", "both", 180, is_cx=True),
        SpeechSpec("PF-ASUM", "Affirmative Summary", "aff", 180, word_budget=450),
        SpeechSpec("PF-NSUM", "Negative Summary", "neg", 180, word_budget=450),
        SpeechSpec("PF-GCF", "Grand Crossfire", "both", 180, is_cx=True),
        SpeechSpec("PF-AFF-FF", "Affirmative Final Focus", "aff", 120, word_budget=300),
        SpeechSpec("PF-NEG-FF", "Negative Final Focus", "neg", 120, word_budget=300),
    ),
    prep_time_sec=180,
    first_speaker_configurable=True,
)


FORMAT_REGISTRY: dict[str, FormatSpec] = {
    "ipda": IPDA_SPEC,
    "ld": LD_SPEC,
    "pf": PF_SPEC,
}


def get_format_spec(format_id: str | None) -> FormatSpec:
    """Return the client-side FormatSpec for a format id (case-insensitive).

    Defaults to IPDA when passed None or empty string.
    Raises ValueError for unknown formats.
    """
    key = (format_id or "ipda").lower().strip()
    if key not in FORMAT_REGISTRY:
        raise ValueError(
            f"Unknown debate format '{format_id}'. "
            f"Known: {sorted(FORMAT_REGISTRY.keys())}"
        )
    return FORMAT_REGISTRY[key]

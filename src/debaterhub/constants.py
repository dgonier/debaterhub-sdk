"""IPDA debate constants (legacy names -- resolved from format registry).

New code should prefer :func:`debaterhub.formats.get_format_spec` from
:mod:`debaterhub.formats`. These names are kept for backwards compatibility.
"""

from __future__ import annotations

from .formats import get_format_spec

_IPDA = get_format_spec("ipda")

# IPDA speech order (hyphens are canonical internally)
IPDA_SPEECH_ORDER: list[str] = list(_IPDA.speech_ids)

# Time limits in seconds for each speech
SPEECH_TIME_LIMITS: dict[str, int] = dict(_IPDA.speech_time_limits)

# Speeches belonging to each side (constructives/rebuttals only)
AFF_SPEECHES: set[str] = set(_IPDA.aff_speeches)
NEG_SPEECHES: set[str] = set(_IPDA.neg_speeches)

# CX: the OTHER side asks questions
AFF_CX_ASKING: set[str] = {
    s.id for s in _IPDA.speech_order if s.is_cx and s.cx_asker == "aff"
}
NEG_CX_ASKING: set[str] = {
    s.id for s in _IPDA.speech_order if s.is_cx and s.cx_asker == "neg"
}

# All speeches where each side is active (speaking or questioning)
AFF_ACTIVE: set[str] = set(_IPDA.aff_active)
NEG_ACTIVE: set[str] = set(_IPDA.neg_active)

# Whether a speech type is a CX period
IS_CX_SPEECH: dict[str, bool] = dict(_IPDA.is_cx_speech)

# Which side is *active* for each speech (owning side; CX asker for CX periods)
SPEECH_SIDE: dict[str, str] = dict(_IPDA.speech_side)

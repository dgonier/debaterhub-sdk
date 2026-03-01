"""IPDA debate constants.

Self-contained copy of constants from the debate pipeline so the SDK
is installable without the monorepo.
"""

from __future__ import annotations

# IPDA speech order (hyphens are canonical internally)
IPDA_SPEECH_ORDER: list[str] = ["AC", "AC-CX", "NC", "NC-CX", "1AR", "NR", "2AR"]

# Time limits in seconds for each speech
SPEECH_TIME_LIMITS: dict[str, int] = {
    "AC": 300,       # 5 minutes
    "AC-CX": 180,    # 3 minutes
    "NC": 360,       # 6 minutes
    "NC-CX": 180,    # 3 minutes
    "1AR": 300,      # 5 minutes
    "NR": 300,       # 5 minutes
    "2AR": 180,      # 3 minutes
}

# Speeches belonging to each side
AFF_SPEECHES: set[str] = {"AC", "1AR", "2AR"}
NEG_SPEECHES: set[str] = {"NC", "NR"}

# CX: the OTHER side asks questions
AFF_CX_ASKING: set[str] = {"NC-CX"}  # AFF examines during NC-CX
NEG_CX_ASKING: set[str] = {"AC-CX"}  # NEG examines during AC-CX

# All speeches where each side is active (speaking or questioning)
AFF_ACTIVE: set[str] = AFF_SPEECHES | AFF_CX_ASKING
NEG_ACTIVE: set[str] = NEG_SPEECHES | NEG_CX_ASKING

# Whether a speech type is a CX period
IS_CX_SPEECH: dict[str, bool] = {s: s.endswith("-CX") for s in IPDA_SPEECH_ORDER}

# Which side owns each speech
SPEECH_SIDE: dict[str, str] = {}
for _s in IPDA_SPEECH_ORDER:
    if _s in AFF_ACTIVE:
        SPEECH_SIDE[_s] = "aff"
    else:
        SPEECH_SIDE[_s] = "neg"

"""Wire message parsing for the LiveKit data channel protocol.

Handles JSON decoding, key normalisation (the agent sends both
camelCase and snake_case), and speech-type normalisation (hyphens vs
underscores).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Type

from .exceptions import ProtocolError

# camelCase → snake_case converter
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")


def _camel_to_snake(name: str) -> str:
    return _CAMEL_RE.sub(r"_\1", name).lower()


def _normalize_speech_type(value: str) -> str:
    """Normalise speech type to canonical hyphen form (e.g. AC-CX)."""
    return value.replace("_", "-").upper()


def normalize_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a dict with all keys converted to snake_case.

    Preserves originals so field lookup works with either convention.
    """
    out: Dict[str, Any] = {}
    for k, v in data.items():
        snake = _camel_to_snake(k)
        out[k] = v            # keep original
        if snake != k:
            out[snake] = v    # add snake_case alias
    return out


def parse_server_message(raw: bytes) -> Dict[str, Any]:
    """Decode a raw data-channel payload into a normalised dict.

    Returns the dict with:
    - All keys available in *both* their original and snake_case forms
    - ``speech_type`` (if present) normalised to hyphen form
    - A ``type`` key guaranteed to exist (raises :class:`ProtocolError` otherwise)
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProtocolError(f"Expected JSON object, got {type(data).__name__}")

    normalised = normalize_keys(data)

    if "type" not in normalised:
        raise ProtocolError("Message missing 'type' field")

    # Normalise speech type fields
    for key in ("speech_type", "speechType", "for_speech", "forSpeech"):
        if key in normalised and isinstance(normalised[key], str):
            normalised[key] = _normalize_speech_type(normalised[key])

    return normalised


# ---------------------------------------------------------------------------
# Message type registry (type string → event class)
# Populated by events.py at import time
# ---------------------------------------------------------------------------

_EVENT_REGISTRY: Dict[str, Type[Any]] = {}


def register_event(type_str: str, cls: Type[Any]) -> None:
    _EVENT_REGISTRY[type_str] = cls


def get_event_class(type_str: str) -> Optional[Type[Any]]:
    return _EVENT_REGISTRY.get(type_str)

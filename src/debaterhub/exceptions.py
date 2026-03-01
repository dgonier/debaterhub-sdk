"""Exception hierarchy for the debaterhub SDK."""

from __future__ import annotations


class DebatehubError(Exception):
    """Base exception for all SDK errors."""


class ConfigValidationError(DebatehubError):
    """Invalid configuration values."""


class ConnectionError(DebatehubError):  # noqa: A001 — intentional shadow
    """Failed to connect to LiveKit or the debate agent."""


class DispatchError(DebatehubError):
    """Failed to dispatch the debate agent to the room."""


class WarmupError(DebatehubError):
    """Agent warmup request failed."""


class SessionNotConnectedError(DebatehubError):
    """Operation attempted on a session that is not connected."""


class ProtocolError(DebatehubError):
    """Malformed or unrecognised wire message."""

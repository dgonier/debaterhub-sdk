"""Opt-in verbose logging for the debaterhub SDK.

Debugging a stuck session (e.g. "debate stays at debate_initializing forever")
is a lot easier when you can see every event the SDK receives, every message
it sends, and every handler error. By default the SDK is quiet; setting an
environment variable flips on a structured log stream.

Env vars
--------
``DEBATERHUB_LOG_LEVEL``
    One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``. Sets the minimum
    level for the ``debaterhub`` logger namespace. Default: unset (no
    auto-configured handler — callers use their own logging config).

``DEBATERHUB_VERBOSE``
    Shorthand for ``DEBATERHUB_LOG_LEVEL=DEBUG`` when set to any truthy
    value (``1``, ``true``, ``yes``, ``on``). If both are set,
    ``DEBATERHUB_LOG_LEVEL`` wins.

When either variable triggers configuration, a single StreamHandler is
attached to the ``debaterhub`` logger (idempotent — repeat imports won't
stack handlers) with a simple, timestamped format. The root logger is
untouched, so host apps with their own logging config keep control.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

# Module-level guard so we only attach the handler once even if this
# module is imported multiple times (tests, re-exports, etc.).
_CONFIGURED = False

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class _TaggedFormatter(logging.Formatter):
    """Format records with a `[EVENT]` vs `[LOG]` prefix.

    Records emitted via `logger.info/debug(..., extra={"event": True})`
    are tagged `[EVENT]` — one-liner server event traces, scannable top
    to bottom. Everything else is `[LOG]` — framework/library chatter.

    Having the two separated lets users grep one or the other out of a
    busy session log: `grep EVENT smoke.log` shows the debate
    phase-by-phase; `grep LOG smoke.log` shows connection/parse/handler
    noise.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        tag = "EVENT" if getattr(record, "event", False) else "LOG"
        ts = self.formatTime(record, datefmt="%H:%M:%S")
        return f"{ts} [{tag}] {record.getMessage()}"


def _truthy(val: Optional[str]) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_level() -> Optional[str]:
    explicit = os.environ.get("DEBATERHUB_LOG_LEVEL")
    if explicit:
        lvl = explicit.strip().upper()
        return lvl if lvl in _VALID_LEVELS else None
    if _truthy(os.environ.get("DEBATERHUB_VERBOSE")):
        return "DEBUG"
    return None


def configure_from_env() -> None:
    """Attach a stream handler to the debaterhub logger if env says so.

    Safe to call repeatedly. If neither env var is set, this is a no-op
    — callers that configure their own logging see no change.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = _resolve_level()
    if level is None:
        return

    logger = logging.getLogger("debaterhub")
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Only add our handler if the caller hasn't already attached one.
    has_our_handler = any(
        getattr(h, "_debaterhub_sdk", False) for h in logger.handlers
    )
    if not has_our_handler:
        handler = logging.StreamHandler()
        handler._debaterhub_sdk = True  # type: ignore[attr-defined]
        handler.setFormatter(_TaggedFormatter())
        logger.addHandler(handler)
        # Don't propagate — avoids duplicate lines when the host also
        # configures a root handler.
        logger.propagate = False

    _CONFIGURED = True
    logger.debug(
        "SDK verbose logging enabled (level=%s via %s)",
        level,
        "DEBATERHUB_LOG_LEVEL" if os.environ.get("DEBATERHUB_LOG_LEVEL") else "DEBATERHUB_VERBOSE",
    )

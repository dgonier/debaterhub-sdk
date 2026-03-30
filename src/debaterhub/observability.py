"""Optional Langfuse observability for debate sessions.

Traces the session lifecycle: create -> connect -> speeches -> disconnect.
Fully opt-in: no-ops when LANGFUSE_PUBLIC_KEY is not set or langfuse
is not installed.

Compatible with Langfuse SDK v4+.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_langfuse = None
_checked = False


def _get_langfuse():
    """Get or create a Langfuse client. Returns None if not configured."""
    global _langfuse, _checked
    if _checked:
        return _langfuse
    _checked = True

    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse()
        logger.info("Langfuse client initialized for session tracing")
        return _langfuse
    except ImportError:
        logger.debug("langfuse not installed, skipping session tracing")
        return None
    except Exception:
        logger.warning("Failed to initialize Langfuse client", exc_info=True)
        return None


class SessionTracer:
    """Traces a debate session as a Langfuse trace with spans.

    Uses Langfuse v4 API (start_as_current_observation / create_event).

    All methods are safe to call even when Langfuse is not available —
    they silently no-op.
    """

    def __init__(self, session_id: str, metadata: Optional[dict] = None):
        self._lf = _get_langfuse()
        self._session_id = session_id
        self._root_span = None
        if self._lf:
            try:
                self._root_span = self._lf.start_observation(
                    as_type="span",
                    name="debate_session",
                    metadata={**(metadata or {}), "session_id": session_id},
                )
            except Exception:
                logger.debug("Failed to create Langfuse trace", exc_info=True)

    @property
    def active(self) -> bool:
        return self._root_span is not None

    def span(self, name: str, **kwargs: Any):
        """Create a child span. Returns the span or None."""
        if not self._lf:
            return None
        try:
            return self._lf.start_observation(as_type="span", name=name, **kwargs)
        except Exception:
            logger.debug("Failed to create Langfuse span %s", name, exc_info=True)
            return None

    def event(self, name: str, **kwargs: Any):
        """Log a point-in-time event."""
        if not self._lf:
            return
        try:
            self._lf.create_event(name=name, **kwargs)
        except Exception:
            logger.debug("Failed to log Langfuse event %s", name, exc_info=True)

    def end(self):
        """End the root span and flush pending data."""
        if self._root_span:
            try:
                self._root_span.end()
            except Exception:
                logger.debug("Failed to end Langfuse span", exc_info=True)
        if self._lf:
            try:
                self._lf.flush()
            except Exception:
                logger.debug("Failed to flush Langfuse", exc_info=True)

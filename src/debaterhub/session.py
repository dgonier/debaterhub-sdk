"""ManagedDebateSession — Mode 2: server-managed debate sessions.

Composes a data-only LiveKit participant, a turn tracker, and an event
handler to provide a high-level interface for backend integrations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ._data_channel import DataOnlyParticipant
from .events import (
    EVENT_HANDLER_MAP,
    DebateEvent,
    DebateEventHandler,
    TurnSignalEvent,
    event_from_dict,
)
from .exceptions import SessionNotConnectedError
from .observability import SessionTracer
from .protocol import parse_server_message
from .state import DebateTurnTracker

logger = logging.getLogger(__name__)


class ManagedDebateSession:
    """Server-managed debate session (Mode 2).

    Joins the LiveKit room as a data-only participant, parses incoming
    messages into typed events, and dispatches them to the handler.

    Parameters
    ----------
    participant:
        An already-constructed (but not yet connected) :class:`DataOnlyParticipant`.
    handler:
        User-supplied event handler.
    human_side:
        ``"aff"`` or ``"neg"`` — used to initialise the turn tracker.
    """

    def __init__(
        self,
        participant: DataOnlyParticipant,
        handler: DebateEventHandler,
        human_side: str = "aff",
        debate_mode: str = "ai_human",
        format: str = "ipda",
        tracer: Optional[SessionTracer] = None,
    ) -> None:
        self._participant = participant
        self._handler = handler
        self._tracer = tracer
        self._debate_mode = debate_mode
        self._format = format
        self.tracker = DebateTurnTracker(
            human_side=human_side,
            debate_mode=debate_mode,
            format=format,
        )

    @property
    def connected(self) -> bool:
        return self._participant.connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect the data-only participant to the room."""
        self._participant._on_data = self._on_data_received
        await self._participant.connect()
        if self._tracer:
            self._tracer.event("session_connected")

    async def disconnect(self) -> None:
        """Disconnect from the room."""
        await self._participant.disconnect()
        await self._handler.on_disconnect("client requested disconnect")
        if self._tracer:
            self._tracer.event("session_disconnected")
            self._tracer.end()

    # ------------------------------------------------------------------
    # Client → Server methods
    # ------------------------------------------------------------------

    async def submit_speech(
        self,
        speech_type: str,
        transcript: str,
        duration_seconds: float = 0.0,
        word_count: Optional[int] = None,
    ) -> None:
        """Submit a completed human speech to the agent."""
        self._ensure_connected()
        wc = word_count if word_count is not None else len(transcript.split())
        await self._send({
            "type": "speech_end",
            "speechType": speech_type,
            "transcript": transcript,
            "durationSeconds": duration_seconds,
            "wordCount": wc,
        })
        self.tracker.record_speech(speech_type, transcript)
        if self._tracer:
            self._tracer.event("speech_submitted", metadata={
                "speech_type": speech_type,
                "word_count": wc,
                "duration_seconds": duration_seconds,
            })

    async def submit_cx_question(self, question: str, turn_number: int = 0) -> None:
        """Send a CX question from the human."""
        self._ensure_connected()
        await self._send({
            "type": "cx_question",
            "question": question,
            "turnNumber": turn_number,
        })

    async def submit_cx_answer(self, answer: str, question_ref: Optional[str] = None) -> None:
        """Send a CX answer from the human."""
        self._ensure_connected()
        msg: dict[str, Any] = {"type": "cx_answer", "answer": answer}
        if question_ref:
            msg["questionRef"] = question_ref
        await self._send(msg)

    async def end_cx(self, speech_type: str) -> None:
        """Signal the end of a CX period."""
        self._ensure_connected()
        await self._send({
            "type": "cx_end",
            "speechType": speech_type,
        })

    async def end_prep_time(self) -> None:
        """Signal the end of prep time."""
        self._ensure_connected()
        await self._send({"type": "prep_time_end"})

    async def request_coaching(self, for_speech: str) -> None:
        """Request coaching hints for an upcoming speech."""
        self._ensure_connected()
        await self._send({
            "type": "request_coaching",
            "forSpeech": for_speech,
        })

    async def request_evidence(self, query: str, limit: int = 5) -> None:
        """Request evidence search results."""
        self._ensure_connected()
        await self._send({
            "type": "evidence_request",
            "query": query,
            "limit": limit,
        })

    async def skip_cx(self, speech_type: str) -> None:
        """Skip a CX period."""
        self._ensure_connected()
        await self._send({
            "type": "cx_end",
            "speechType": speech_type,
            "exchanges": [],
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self.connected:
            raise SessionNotConnectedError("Session is not connected")

    async def _send(self, data: dict[str, Any]) -> None:
        await self._participant.send(data)

    async def _on_data_received(self, raw: bytes, topic: str) -> None:
        """Parse incoming data and dispatch to the handler."""
        try:
            normalised = parse_server_message(raw)
        except Exception:
            logger.warning("Failed to parse message: %s", raw[:200])
            return

        event = event_from_dict(normalised)

        # Update turn tracker from turn signals
        if isinstance(event, TurnSignalEvent):
            self.tracker.update_from_turn_signal(
                speech_type=event.speech_type,
                speaker=event.speaker,
                speech_index=event.speech_index,
                status=event.status,
            )

        # Dispatch to handler
        type_str = normalised.get("type", "")
        method_name = EVENT_HANDLER_MAP.get(type_str, "on_unknown")
        method = getattr(self._handler, method_name, self._handler.on_unknown)
        try:
            await method(event)
        except Exception:
            logger.exception("Handler %s raised an exception", method_name)

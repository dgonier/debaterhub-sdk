"""ManagedDebateSession — Mode 2: server-managed debate sessions.

Composes a data-only LiveKit participant, a turn tracker, and an event
handler to provide a high-level interface for backend integrations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional

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


# Type of an optional stall callback.
#
# Called when no server-originated event has arrived for `stall_after_seconds`.
# Args: (elapsed_since_connect, elapsed_since_last_event, last_phase_message).
# The SDK does NOT disconnect on stall — the callback decides what to do
# (fail a test, notify a user, start a new session, etc.). It fires at
# most once per stall; if events resume and pause again, it can re-fire.
OnStallCallback = Callable[[float, float, str], Awaitable[None]]


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
        *,
        on_stall: Optional[OnStallCallback] = None,
        stall_after_seconds: float = 120.0,
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

        # Phase/timing bookkeeping. Populated on connect() + every
        # inbound event. `last_phase_message` holds the most recent
        # human-readable progress line we received (e.g. the agent's
        # `debate_initializing` `message` field) so diagnostics can
        # show "stalled at: [beliefs] Generating NEG beliefs".
        self._connected_at: Optional[float] = None
        self._last_event_at: Optional[float] = None
        self._last_event_type: Optional[str] = None
        self._last_phase_message: str = ""
        self._event_count: int = 0

        # Stall detection. When set, a background task checks for
        # silence every few seconds and fires `on_stall` at most once
        # per stall window. Re-arms when the next event arrives.
        self._on_stall = on_stall
        self._stall_after = float(stall_after_seconds)
        self._stall_task: Optional[asyncio.Task[None]] = None
        self._stall_fired: bool = False

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
        self._connected_at = time.monotonic()
        self._last_event_at = self._connected_at
        if self._on_stall is not None:
            self._stall_task = asyncio.create_task(
                self._watchdog_loop(), name="debaterhub-stall-watchdog"
            )
        if self._tracer:
            self._tracer.event("session_connected")

    async def disconnect(self) -> None:
        """Disconnect from the room."""
        if self._stall_task is not None:
            self._stall_task.cancel()
            try:
                await self._stall_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stall_task = None
        await self._participant.disconnect()
        await self._handler.on_disconnect("client requested disconnect")
        if self._tracer:
            self._tracer.event("session_disconnected")
            self._tracer.end()

    # ------------------------------------------------------------------
    # Diagnostic properties — read-only snapshot of session timing
    # ------------------------------------------------------------------

    @property
    def last_phase_message(self) -> str:
        """Most recent human-readable progress message from the server.

        Empty until the first `debate_initializing` (or other event with
        a `message` field) arrives. Useful in `on_stall` callbacks so a
        user sees *where* the server was when it went silent.
        """
        return self._last_phase_message

    @property
    def seconds_since_last_event(self) -> float:
        """Seconds since the last inbound event. `inf` if not connected."""
        if self._last_event_at is None:
            return float("inf")
        return time.monotonic() - self._last_event_at

    @property
    def seconds_since_connect(self) -> float:
        """Seconds since the session connected. `inf` if not connected."""
        if self._connected_at is None:
            return float("inf")
        return time.monotonic() - self._connected_at

    @property
    def event_count(self) -> int:
        """Total server-originated events observed by this session."""
        return self._event_count

    async def _watchdog_loop(self) -> None:
        """Fires `on_stall` once per stall window when no events arrive.

        Wakes every few seconds and compares `now - last_event_at`
        against `stall_after_seconds`. Re-arms when a new event arrives
        (see `_on_data_received` which resets `_stall_fired`).
        """
        assert self._on_stall is not None
        # Check at 25% of the window, min 5s, max 30s.
        interval = max(5.0, min(30.0, self._stall_after * 0.25))
        try:
            while True:
                await asyncio.sleep(interval)
                if self._last_event_at is None:
                    continue
                silence = time.monotonic() - self._last_event_at
                if silence < self._stall_after:
                    continue
                if self._stall_fired:
                    continue
                self._stall_fired = True
                since_connect = (
                    time.monotonic() - self._connected_at
                    if self._connected_at
                    else silence
                )
                try:
                    await self._on_stall(
                        since_connect, silence, self._last_phase_message
                    )
                except Exception:
                    logger.exception(
                        "on_stall callback raised after %.1fs of silence",
                        silence,
                    )
        except asyncio.CancelledError:
            pass

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

    @staticmethod
    def _event_summary(
        type_str: str, normalised: dict[str, Any], message: str
    ) -> str:
        """Build a short human-readable summary for one inbound event.

        Used by the `[EVENT]`-tagged INFO line. Keep it to one line:
        the full payload is already available via the DEBUG `recv`
        dump for deep-dive. The goal here is scannability — a user
        reading the log should see each phase progression without
        parsing JSON.
        """
        if message:
            return str(message)[:160]
        if type_str == "belief_tree":
            tree = normalised.get("tree") or {}
            if isinstance(tree, dict):
                beliefs = tree.get("beliefs") or []
                return f"{len(beliefs)} belief(s) received"
            return "tree received"
        if type_str == "debate_ready":
            return str(normalised.get("topic", ""))[:120]
        if type_str == "turn_signal":
            sp = normalised.get("speech_type") or normalised.get("speechType") or "?"
            st = normalised.get("status") or ""
            return f"{sp} ({st})" if st else str(sp)
        if type_str == "speech_text":
            text = normalised.get("text") or normalised.get("transcript") or ""
            return f"{str(text)[:100]}…" if len(str(text)) > 100 else str(text)
        if type_str == "error":
            return str(normalised.get("error") or normalised.get("message") or "")[:160]
        # Default: short list of the non-type keys so unknown events
        # are at least recognizable.
        keys = [k for k in normalised.keys() if k != "type"]
        return ", ".join(keys[:5])

    async def _send(self, data: dict[str, Any]) -> None:
        # At DEBUG level, log every outgoing message so the user can
        # see what the SDK sent before the server stalled. Trimmed to
        # 400 chars to avoid dumping full transcripts.
        if logger.isEnabledFor(logging.DEBUG):
            summary = json.dumps(data, default=str)[:400]
            logger.debug("→ send type=%s payload=%s", data.get("type", "?"), summary)
        await self._participant.send(data)

    async def _on_data_received(self, raw: bytes, topic: str) -> None:
        """Parse incoming data and dispatch to the handler."""
        try:
            normalised = parse_server_message(raw)
        except Exception as parse_err:
            # Promoted from WARNING to ERROR with the full payload when
            # verbose — parse failures at debate_initializing usually
            # mean a schema-version mismatch between the SDK and the
            # backend, which is exactly what the user needs to see.
            logger.error(
                "parse failed: %s — raw=%s",
                parse_err,
                raw[:400].decode("utf-8", errors="replace"),
            )
            return

        event = event_from_dict(normalised)
        type_str = normalised.get("type", "")

        # Maintain diagnostic bookkeeping BEFORE dispatching to the
        # handler so even if the handler raises, the watchdog sees the
        # event arrived. This also re-arms stall detection — any event
        # (including the agent's periodic progress proxies) counts as
        # "still alive".
        self._last_event_at = time.monotonic()
        self._last_event_type = type_str
        self._event_count += 1
        self._stall_fired = False
        message = normalised.get("message") or normalised.get("error") or ""
        if message:
            self._last_phase_message = str(message)[:200]

        # Two layers of trace:
        #
        # [EVENT]  — one clean line per inbound server event, emitted at
        #            INFO so `DEBATERHUB_VERBOSE=1` or an explicit
        #            `DEBATERHUB_LOG_LEVEL=INFO` both show it. Format
        #            is always `[+{elapsed}s] {type}{summary}` so a
        #            user can scan the full session top-to-bottom.
        #
        # [LOG]    — deeper framework chatter (parse errors, handler
        #            exceptions, raw-frame dumps) at DEBUG. Keep the
        #            older `← recv type=... {preview}` dump for
        #            deep-dive diagnosis when events aren't enough.
        elapsed = self.seconds_since_connect
        summary = self._event_summary(type_str, normalised, message)
        logger.info(
            "[+%6.1fs] %s%s",
            elapsed,
            type_str or "?",
            f" — {summary}" if summary else "",
            extra={"event": True},
        )
        if logger.isEnabledFor(logging.DEBUG):
            preview = {
                k: (str(v)[:120] if isinstance(v, (str, int, float, bool)) else type(v).__name__)
                for k, v in normalised.items()
                if k != "type"
            }
            logger.debug("recv type=%s %s", type_str, preview)

        # Update turn tracker from turn signals
        if isinstance(event, TurnSignalEvent):
            self.tracker.update_from_turn_signal(
                speech_type=event.speech_type,
                speaker=event.speaker,
                speech_index=event.speech_index,
                status=event.status,
            )

        # Dispatch to handler
        method_name = EVENT_HANDLER_MAP.get(type_str, "on_unknown")
        method = getattr(self._handler, method_name, self._handler.on_unknown)
        try:
            await method(event)
        except Exception:
            logger.exception(
                "Handler %s raised an exception on event type=%s",
                method_name,
                type_str,
            )

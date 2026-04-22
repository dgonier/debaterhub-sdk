"""E2E smoke test — does an IPDA session actually reach debate_ready?

This exists specifically to catch the "stuck at debate_initializing"
failure mode reported by external SDK users. It:

1. Creates a managed IPDA session against the live LiveKit agent.
2. Waits up to 120 seconds for the `debate_ready` event.
3. If it doesn't arrive, prints every event that DID arrive plus any
   errors, then fails loudly — giving us (and the user) enough signal
   to diagnose the stall without needing SSH into the backend.

Run with: pytest tests/e2e/test_ipda_handoff_smoke.py -m slow --timeout=180

Marker: slow (requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET).
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from debaterhub.client import DebateClient
from debaterhub.config import DebateConfig
from debaterhub.events import DebateEventHandler

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")

if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    pytestmark.append(pytest.mark.skip(reason="LIVEKIT_* env vars not set"))


class _InitHandler(DebateEventHandler):
    """Minimal handler that records every event + flags debate_ready."""

    def __init__(self) -> None:
        self.events: list[tuple[float, str, dict]] = []
        self.errors: list[str] = []
        self.ready_at: float | None = None
        self.initializing_at: float | None = None
        self._ready_evt = asyncio.Event()
        self._t0 = time.monotonic()

    def _t(self) -> float:
        return round(time.monotonic() - self._t0, 2)

    def _record(self, type_str: str, payload: dict) -> None:
        self.events.append((self._t(), type_str, payload))

    async def on_debate_initializing(self, event):
        self.initializing_at = self._t()
        self._record("debate_initializing", {"message": getattr(event, "message", "")})

    async def on_debate_ready(self, event):
        self.ready_at = self._t()
        self._record("debate_ready", {"topic": getattr(event, "topic", "")})
        self._ready_evt.set()

    async def on_error(self, event):
        msg = getattr(event, "message", "") or str(event)
        self.errors.append(msg)
        self._record("error", {"message": msg[:200]})

    async def on_turn_signal(self, event):
        self._record(
            "turn_signal",
            {
                "speech_type": getattr(event, "speech_type", ""),
                "status": getattr(event, "status", ""),
            },
        )

    # No-op catch-alls so the dispatcher is happy even though we don't
    # care about the bodies — the session still records them via `events`.
    async def on_unknown(self, event):
        self._record(
            "unknown", {"type": getattr(event, "type", "?")}
        )

    async def on_speech_text(self, event): self._record("speech_text", {})
    async def on_speech_progress(self, event): self._record("speech_progress", {})
    async def on_belief_tree(self, event): self._record("belief_tree", {})
    async def on_flow_update(self, event): self._record("flow_update", {})
    async def on_coaching_hint(self, event): self._record("coaching_hint", {})
    async def on_speech_scored(self, event): self._record("speech_scored", {})
    async def on_cx_question(self, event): self._record("cx_question", {})
    async def on_cx_answer(self, event): self._record("cx_answer", {})
    async def on_evidence_result(self, event): self._record("evidence_result", {})
    async def on_judging_started(self, event): self._record("judging_started", {})
    async def on_judge_result(self, event): self._record("judge_result", {})
    async def on_disconnect(self, reason: str = ""):
        self._record("disconnect", {"reason": reason})

    async def wait_ready(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._ready_evt.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_ready_or_timeout(
        self,
        predicate,
        timeout: float,
        poll_interval: float = 0.25,
    ) -> bool:
        """Return True as soon as `predicate()` is truthy, else False on timeout."""
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            if predicate():
                return True
            await asyncio.sleep(poll_interval)
        return predicate()

    async def wait_for_any(
        self,
        _types_ignored,   # kept for signature stability; predicate drives it
        predicate,
        timeout: float,
        poll_interval: float = 0.5,
    ) -> bool:
        """Same as wait_ready_or_timeout but with coarser polling."""
        return await self.wait_ready_or_timeout(
            predicate=predicate, timeout=timeout, poll_interval=poll_interval
        )


# Milestone budgets. Each must arrive within the listed wall-clock
# seconds OR the test fails fast with a descriptive message pointing
# at the stuck phase. We intentionally check intermediate events, not
# just `debate_ready`, because the most common failure mode is "stuck
# part-way through prep" — a single 10-min wait for `debate_ready`
# can't distinguish that from "dispatch never landed at all".
_MS_INITIALIZING = 20.0       # agent must emit its first event promptly
_MS_FIRST_PROGRESS = 60.0     # values/beliefs phase should start inside a minute
_MS_BELIEF_TREE = 720.0       # minimal prep: values→beliefs→research→args→clash
_MS_DEBATE_READY = 900.0      # + persist + finalize
_STALL_WINDOW = 180.0         # if no event for this long, fail fast with a diag


@pytest.mark.asyncio
async def test_ipda_session_reaches_debate_ready():
    """End-to-end: a freshly-created IPDA session must emit debate_ready.

    This is the pre-release gate. Passes ⇒ the agent is reachable, the
    data channel stays alive under a real prep run, and the prep
    pipeline produces a usable tree. Fails ⇒ the test prints which
    milestone was missed plus the full event trail up to that point.
    """
    client = DebateClient(
        livekit_url=LIVEKIT_URL,
        livekit_api_key=LIVEKIT_API_KEY,
        livekit_api_secret=LIVEKIT_API_SECRET,
    )
    handler = _InitHandler()

    # Stall-detection callback — if the data channel goes silent for
    # `_STALL_WINDOW` seconds before we reach `debate_ready`, record a
    # structured stall so the final diag can print it.
    stalls: list[tuple[float, float, str]] = []

    async def _on_stall(since_connect: float, silence: float, last_phase: str) -> None:
        stalls.append((since_connect, silence, last_phase))

    config = DebateConfig(
        topic="Resolved: social media platforms should require identity verification",
        format="ipda",
        human_side="aff",
        debate_mode="ai_human",
        # Minimal prep so the smoke test completes in ~5 min. Real
        # callers omit this to get the full-breadth default tree.
        prep_config={
            "values_per_side": 1,
            "beliefs_per_value": 1,
            "research_per_belief": 1,
            "arguments_per_leaf": 1,
            "max_depth": 1,
        },
    )

    def _render_diag(reason: str) -> str:
        seen_types = sorted({t for _, t, _ in handler.events})
        log_lines = [
            f"  [{t:>6.2f}s] {name} {payload}"
            for t, name, payload in handler.events
        ]
        stall_lines = [
            f"  stall: {silence:.1f}s of silence at {phase!r} "
            f"(elapsed {sc:.1f}s from connect)"
            for sc, silence, phase in stalls
        ]
        return (
            f"\n{reason}\n"
            f"Saw event types: {seen_types}\n"
            f"debate_initializing at: {handler.initializing_at}\n"
            f"Errors: {handler.errors or 'none'}\n"
            + ("Stalls:\n" + "\n".join(stall_lines) + "\n" if stall_lines else "")
            + "Full event log:\n"
            + "\n".join(log_lines or ["  (no events)"])
        )

    session = None
    try:
        session = await client.create_managed_session(
            config=config,
            handler=handler,
            on_stall=_on_stall,
            stall_after_seconds=_STALL_WINDOW,
        )

        # Milestone 1: first event (typically `debate_initializing`).
        got_init = await handler.wait_ready_or_timeout(
            predicate=lambda: handler.initializing_at is not None,
            timeout=_MS_INITIALIZING,
        )
        if not got_init:
            pytest.fail(_render_diag(
                f"MILESTONE MISS: no `debate_initializing` inside {_MS_INITIALIZING}s"
                f" — agent dispatch likely failed or worker isn't running."
            ))

        # Milestone 2: first research-phase progress event (values or
        # beliefs). This is the "am I doing something?" check; if we
        # never see it, the agent either isn't delegating to debate-prep
        # or debate-prep itself is dead.
        got_progress = await handler.wait_for_any(
            {"belief_tree"}
            | set(),  # extra types if we want
            predicate=lambda: any(
                "[values]" in (payload.get("message", "") or "")
                or "[beliefs]" in (payload.get("message", "") or "")
                or "[research]" in (payload.get("message", "") or "")
                for _, _, payload in handler.events
            ),
            timeout=_MS_FIRST_PROGRESS,
        )
        if not got_progress:
            pytest.fail(_render_diag(
                f"MILESTONE MISS: no `[values]/[beliefs]/[research]` progress "
                f"inside {_MS_FIRST_PROGRESS}s of connect — debate-prep "
                f"delegation isn't happening."
            ))

        # Milestone 3: full belief tree arrived.
        got_tree = await handler.wait_for_any(
            {"belief_tree"},
            predicate=lambda: any(t == "belief_tree" for _, t, _ in handler.events),
            timeout=_MS_BELIEF_TREE,
        )
        if not got_tree:
            pytest.fail(_render_diag(
                f"MILESTONE MISS: no `belief_tree` inside {_MS_BELIEF_TREE}s — "
                f"prep pipeline either hung or produced no tree."
            ))

        # Milestone 4: debate_ready — the ultimate gate.
        got_ready = await handler.wait_ready(timeout=_MS_DEBATE_READY - _MS_BELIEF_TREE)
        if not got_ready:
            pytest.fail(_render_diag(
                f"MILESTONE MISS: `belief_tree` arrived but no `debate_ready` "
                f"inside {_MS_DEBATE_READY}s total — agent couldn't finalize "
                f"(likely LiveKit publisher connection timeout)."
            ))

        # Basic ordering sanity.
        assert handler.initializing_at is not None
        assert handler.ready_at is not None
        assert handler.ready_at >= handler.initializing_at, (
            f"Event ordering wrong: ready@{handler.ready_at} preceded "
            f"initializing@{handler.initializing_at}"
        )
    finally:
        if session is not None:
            try:
                await session.disconnect()
            except Exception:
                pass
        try:
            await client.close()
        except Exception:
            pass

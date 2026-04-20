"""Topic-prep client (v1 API).

Kicks off tree-shaped belief-prep runs against the Modal `debate-prep` app
and streams per-event updates over SSE until the run finishes.

The underlying wire contract:
- `POST /v1/start`  →  {call_id, events_url, status_url}
- `GET /v1/events/{call_id}` (SSE)  →  stream of typed events
- `GET /v1/status/{call_id}`  →  one-shot drain (fallback)

Every event payload includes `schema_version` so older clients can
cleanly ignore unrecognised fields on newer wire formats.

This client is intentionally small — one class, two async methods, no
dependency on LiveKit. Runs equally well from a Next.js API route or a
standalone Python script.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Literal, Optional

import httpx

logger = logging.getLogger("debaterhub.topics")


# Default production Modal URLs for v1. Override via `TopicPrepClient(
# start_url=..., events_url_template=..., status_url_template=...)` for
# staging or self-hosted deploys.
_DEFAULT_START_URL = "https://debaterhub--v1-start.modal.run"
_DEFAULT_EVENTS_URL = "https://debaterhub--v1-events.modal.run"
_DEFAULT_STATUS_URL = "https://debaterhub--v1-status.modal.run"


EventType = Literal[
    "progress",
    "node_created",
    "clash_detected",
    "done",
    "error",
]


@dataclass
class TopicPrepEvent:
    """One event from the SSE stream. `raw` keeps the untouched payload so
    callers with bespoke needs don't have to re-parse."""

    type: EventType
    data: Dict[str, Any]
    raw: str = field(default="", repr=False)

    @property
    def schema_version(self) -> str:
        return str(self.data.get("schema_version", "0"))


@dataclass
class TopicPrepStart:
    """Return value of start_prep — call_id plus the URLs the caller can use
    to attach later (e.g. for reconnect / tab-switch scenarios)."""

    call_id: str
    events_url: str
    status_url: str
    schema_version: str


class TopicPrepClient:
    """v1 client for the Modal debate-prep service.

    Usage (async):
        client = TopicPrepClient()
        started = await client.start_prep(topic="Should UBI replace welfare?")
        async for evt in client.stream_events(started.call_id):
            if evt.type == "done":
                break
            print(evt.type, evt.data)
    """

    def __init__(
        self,
        *,
        start_url: str = _DEFAULT_START_URL,
        events_url: str = _DEFAULT_EVENTS_URL,
        status_url: str = _DEFAULT_STATUS_URL,
        http_client: Optional[httpx.AsyncClient] = None,
        request_timeout: float = 30.0,
    ) -> None:
        self._start_url = start_url.rstrip("/")
        self._events_url = events_url.rstrip("/")
        self._status_url = status_url.rstrip("/")
        self._owns_client = http_client is None
        # Default client has no read timeout — SSE streams stay open for
        # minutes. Caller-supplied clients can set whatever timeouts they want.
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=request_timeout, read=None, write=request_timeout, pool=request_timeout),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> "TopicPrepClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # ---- start ------------------------------------------------------------

    async def start_prep(
        self,
        *,
        topic: str,
        config: Optional[Dict[str, Any]] = None,
        call_id: Optional[str] = None,
    ) -> TopicPrepStart:
        """Kick off a prep run. Returns fast with a `call_id`; the actual
        work runs in a Modal spawn and emits events on the queue.

        `config` accepts:
            - max_depth (int, default 1)
            - arguments_per_leaf (int, default 1)
            - research_per_belief (int, default 1)
            - values_per_side (int, default 2)
            - beliefs_per_value (int, default 2)

        `call_id` can be supplied to pin a deterministic ID (useful for idempotent
        retries); if omitted the server generates one.
        """
        payload: Dict[str, Any] = {"topic": topic}
        if config:
            payload["config"] = config
        if call_id:
            payload["call_id"] = call_id

        resp = await self._http.post(self._start_url, json=payload)
        resp.raise_for_status()
        body = resp.json()

        if "error" in body:
            raise TopicPrepError(body["error"])

        return TopicPrepStart(
            call_id=body["call_id"],
            events_url=body["events_url"],
            status_url=body["status_url"],
            schema_version=str(body.get("schema_version", "0")),
        )

    # ---- stream -----------------------------------------------------------

    async def stream_events(self, call_id: str) -> AsyncIterator[TopicPrepEvent]:
        """Yield events as they arrive. Terminates after a `done` or `error`
        event — the server closes the connection right after its terminal
        sentinel, so the async iterator naturally exhausts.

        Callers typically want:
            async for evt in client.stream_events(call_id):
                if evt.type == "done":
                    ...
                elif evt.type == "error":
                    raise RuntimeError(evt.data["message"])
        """
        url = f"{self._events_url}?call_id={call_id}"

        async with self._http.stream("GET", url) as resp:
            resp.raise_for_status()
            # SSE frames: `event: <type>\ndata: <json>\n\n`. We keep state
            # across lines because either field can repeat within a frame.
            current_type: Optional[str] = None
            current_data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if not line:
                    if current_type and current_data_lines:
                        data_raw = "\n".join(current_data_lines)
                        try:
                            data = json.loads(data_raw)
                        except json.JSONDecodeError:
                            logger.warning("dropping malformed SSE data: %s", data_raw[:200])
                            data = {"raw": data_raw}
                        yield TopicPrepEvent(type=current_type, data=data, raw=data_raw)  # type: ignore[arg-type]
                    current_type = None
                    current_data_lines = []
                    continue

                if line.startswith(":"):
                    # Keep-alive comment; ignore.
                    continue
                if line.startswith("event:"):
                    current_type = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    current_data_lines.append(line[len("data:"):].lstrip())

    # ---- one-shot drain ---------------------------------------------------

    async def get_status(self, call_id: str) -> Dict[str, Any]:
        """Drain whatever's on the queue right now (non-blocking). Useful
        for clients that can't hold an SSE connection open, or for quick
        diagnostic polls. Does NOT consume the terminal sentinel, so a
        later `stream_events` call can still see the run's end marker."""
        resp = await self._http.get(f"{self._status_url}?call_id={call_id}")
        resp.raise_for_status()
        return resp.json()


class TopicPrepError(Exception):
    """Raised when the v1 server returns an `error` field in a response."""

    pass

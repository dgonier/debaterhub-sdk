"""Counter-argument client (v1 API).

Given an Argument + its context, kicks off the Modal debate-prep
counter generator and streams the generated counters back over SSE.

A Counter is a typed analytical attack on a specific Argument:
    - TAKEOUT: deny the claim outright
    - LINK_TURN: accept the warrant but flip its direction
    - IMPACT_TURN: accept the link but flip the impact polarity
    - DELINK: break a specific link in the chain

Counters are purely analytical — no web research involved — so runs
finish in ~10-30 seconds.

Wire contract:
    POST /v1/counter/start              → {call_id, events_url, status_url}
    GET  /v1/counter/events/{call_id}   (SSE) → counter_created | done | error
    GET  /v1/counter/status/{call_id}   → one-shot drain
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Literal, Optional

import httpx

logger = logging.getLogger("debaterhub.counters")


_DEFAULT_START_URL = "https://debaterhub--v1-counter-start.modal.run"
_DEFAULT_EVENTS_URL = "https://debaterhub--v1-counter-events.modal.run"
_DEFAULT_STATUS_URL = "https://debaterhub--v1-counter-status.modal.run"


CounterType = Literal["TAKEOUT", "LINK_TURN", "IMPACT_TURN", "DELINK"]

CounterEventType = Literal[
    "progress",
    "counter_created",
    "done",
    "error",
]


@dataclass
class CounterEvent:
    type: CounterEventType
    data: Dict[str, Any]
    raw: str = field(default="", repr=False)

    @property
    def schema_version(self) -> str:
        return str(self.data.get("schema_version", "0"))


@dataclass
class CounterPrepStart:
    call_id: str
    events_url: str
    status_url: str
    schema_version: str


class CounterPrepClient:
    """v1 client for the Modal counter-generator service."""

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
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=request_timeout,
                read=None,
                write=request_timeout,
                pool=request_timeout,
            ),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> "CounterPrepClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def start_counters(
        self,
        *,
        source_argument_uuid: str,
        topic: str,
        source_claim: str,
        source_warrant: str = "",
        source_impact: str = "",
        source_side: str = "AFF",
        call_id: Optional[str] = None,
    ) -> CounterPrepStart:
        """Kick off a counter-generation run. Returns a call_id quickly;
        the actual generation streams over /counter/events/{call_id}."""

        payload: Dict[str, Any] = {
            "source_argument_uuid": source_argument_uuid,
            "topic": topic,
            "source_claim": source_claim,
            "source_warrant": source_warrant,
            "source_impact": source_impact,
            "source_side": source_side,
        }
        if call_id:
            payload["call_id"] = call_id

        resp = await self._http.post(self._start_url, json=payload)
        resp.raise_for_status()
        body = resp.json()

        if "error" in body:
            raise CounterPrepError(body["error"])

        return CounterPrepStart(
            call_id=body["call_id"],
            events_url=body["events_url"],
            status_url=body["status_url"],
            schema_version=str(body.get("schema_version", "0")),
        )

    async def stream_events(self, call_id: str) -> AsyncIterator[CounterEvent]:
        """Yield events as they arrive; terminates after done/error."""
        url = f"{self._events_url}?call_id={call_id}"

        async with self._http.stream("GET", url) as resp:
            resp.raise_for_status()
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
                        yield CounterEvent(type=current_type, data=data, raw=data_raw)  # type: ignore[arg-type]
                    current_type = None
                    current_data_lines = []
                    continue

                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_type = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    current_data_lines.append(line[len("data:"):].lstrip())

    async def get_status(self, call_id: str) -> Dict[str, Any]:
        resp = await self._http.get(f"{self._status_url}?call_id={call_id}")
        resp.raise_for_status()
        return resp.json()


class CounterPrepError(Exception):
    """Raised when the counter server returns an `error` in its response."""

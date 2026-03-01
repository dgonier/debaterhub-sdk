"""Internal: data-only LiveKit room participant.

Joins a room with no audio/video grants and routes incoming data
channel messages through a callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

from livekit import api, rtc

from .exceptions import ConnectionError, SessionNotConnectedError

logger = logging.getLogger(__name__)

OnDataCallback = Callable[[bytes, str], Coroutine[Any, Any, None]]


class DataOnlyParticipant:
    """Joins a LiveKit room purely for data-channel communication.

    Parameters
    ----------
    livekit_url:
        The ``wss://`` URL of the LiveKit server.
    token:
        A JWT token with ``room_join`` and ``can_publish_data`` grants
        (no audio/video needed).
    on_data:
        Async callback ``(raw_bytes, topic) -> None`` invoked for every
        incoming data packet.
    """

    TOPIC = "debate"

    def __init__(
        self,
        livekit_url: str,
        token: str,
        on_data: OnDataCallback,
    ) -> None:
        self._url = livekit_url
        self._token = token
        self._on_data = on_data
        self._room: Optional[rtc.Room] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to the LiveKit room."""
        self._room = rtc.Room()

        @self._room.on("data_received")
        def _handle_data(packet: rtc.DataPacket) -> None:
            topic = getattr(packet, "topic", "") or ""
            asyncio.ensure_future(self._on_data(packet.data, topic))

        @self._room.on("disconnected")
        def _handle_disconnect(*_args: Any) -> None:
            self._connected = False
            logger.info("DataOnlyParticipant disconnected from room")

        try:
            await self._room.connect(self._url, self._token)
            self._connected = True
            logger.info("DataOnlyParticipant connected to room")
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to LiveKit room: {exc}") from exc

    async def send(self, data: dict[str, Any], *, topic: str | None = None) -> None:
        """Publish a JSON message on the data channel."""
        if not self._connected or self._room is None:
            raise SessionNotConnectedError("Not connected to a room")
        payload = json.dumps(data).encode()
        await self._room.local_participant.publish_data(
            payload,
            reliable=True,
            topic=topic or self.TOPIC,
        )

    async def disconnect(self) -> None:
        """Disconnect from the room."""
        if self._room is not None:
            await self._room.disconnect()
        self._connected = False

"""Shared test fixtures for debaterhub-sdk."""

from __future__ import annotations

from typing import Callable, List, Optional

import pytest

from debaterhub._data_channel import DataOnlyParticipant
from debaterhub.config import DebateConfig


# ---------------------------------------------------------------------------
# DebateConfig fixtures (pre-existing)
# ---------------------------------------------------------------------------

@pytest.fixture
def aff_config() -> DebateConfig:
    return DebateConfig(topic="Resolved: AI does more good than harm.", human_side="aff")


@pytest.fixture
def neg_config() -> DebateConfig:
    return DebateConfig(topic="Resolved: AI does more good than harm.", human_side="neg")


# ---------------------------------------------------------------------------
# Fake LiveKit data channel for integration tests
# ---------------------------------------------------------------------------

class FakeDataChannel:
    """In-memory stand-in for a LiveKit data channel.

    Captures messages sent by the SDK and lets tests inject incoming messages.
    """

    def __init__(self) -> None:
        self.sent: List[dict] = []
        self._recv_handler: Optional[Callable] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send(self, data: dict) -> None:
        self.sent.append(data)

    async def inject(self, raw: bytes, topic: str = "debate") -> None:
        """Simulate an incoming message from the server."""
        if self._recv_handler is not None:
            await self._recv_handler(raw, topic)


@pytest.fixture
def fake_participant(monkeypatch):
    """Monkey-patches DataOnlyParticipant with an in-memory fake channel.

    Usage:
        def test_something(fake_participant):
            participant = DataOnlyParticipant(
                livekit_url="wss://fake", token="fake", on_data=lambda r, t: None,
            )
            # participant now uses the fake under the hood
            await fake_participant.inject(json.dumps({"type": "..."}).encode())
            assert fake_participant.sent[0]["type"] == "..."
    """
    fake = FakeDataChannel()

    def patched_init(self, livekit_url, token, on_data):
        # Keep the same public attributes as the real __init__ so other SDK code
        # that pokes at `self._on_data` / `self._connected` keeps working.
        self._url = livekit_url
        self._token = token
        self._on_data = on_data
        self._room = None
        self._connected = False
        self._fake = fake
        fake._recv_handler = on_data

    async def patched_connect(self):
        # Mirror ManagedDebateSession.connect() which swaps _on_data before
        # calling participant.connect(). Re-bind the handler to whatever the
        # session attached.
        self._fake._recv_handler = self._on_data
        await self._fake.connect()
        self._connected = True

    async def patched_disconnect(self):
        await self._fake.disconnect()
        self._connected = False

    async def patched_send(self, data, *, topic=None):
        await self._fake.send(data)

    monkeypatch.setattr(DataOnlyParticipant, "__init__", patched_init)
    monkeypatch.setattr(DataOnlyParticipant, "connect", patched_connect)
    monkeypatch.setattr(DataOnlyParticipant, "disconnect", patched_disconnect)
    monkeypatch.setattr(DataOnlyParticipant, "send", patched_send)

    return fake

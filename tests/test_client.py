"""Tests for DebateClient — mock LiveKit API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from debaterhub.client import DebateClient
from debaterhub.config import DebateClientConfig, DebateConfig
from debaterhub.exceptions import WarmupError


@pytest.fixture
def client() -> DebateClient:
    """Client fixture — LiveKitAPI is lazy so no event loop needed here."""
    return DebateClient(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
        agent_name="test-agent",
    )


@pytest.fixture
def debate_config() -> DebateConfig:
    return DebateConfig(topic="Resolved: UBI is beneficial.", human_side="aff")


class TestFromConfig:
    def test_creates_client(self) -> None:
        cfg = DebateClientConfig(
            livekit_url="wss://example.com",
            livekit_api_key="key",
            livekit_api_secret="secret",
            agent_name="my-agent",
            warmup_url="https://warmup.example.com",
        )
        c = DebateClient.from_config(cfg)
        assert c._url == "wss://example.com"
        assert c._agent_name == "my-agent"
        assert c._warmup_url == "https://warmup.example.com"


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_room_and_dispatches(
        self, client: DebateClient, debate_config: DebateConfig
    ) -> None:
        with (
            patch("debaterhub.client._livekit.create_room", new_callable=AsyncMock) as mock_room,
            patch("debaterhub.client._livekit.dispatch_agent", new_callable=AsyncMock) as mock_dispatch,
            patch("debaterhub.client._livekit.create_participant_token", return_value="jwt-token"),
        ):
            details = await client.create_session(
                debate_config,
                room_name="test-room",
                warmup=False,
            )

            assert details.server_url == "wss://test.livekit.cloud"
            assert details.room_name == "test-room"
            assert details.participant_token == "jwt-token"

            mock_room.assert_awaited_once()
            mock_dispatch.assert_awaited_once()
            # Verify dispatch received the metadata
            call_args = mock_dispatch.call_args
            assert call_args[0][1] == "test-room"
            assert call_args[0][2] == "test-agent"
            metadata = call_args[0][3]
            assert metadata["topic"] == debate_config.topic
            assert metadata["humanSide"] == "aff"

    @pytest.mark.asyncio
    async def test_auto_generates_room_name(
        self, client: DebateClient, debate_config: DebateConfig
    ) -> None:
        with (
            patch("debaterhub.client._livekit.create_room", new_callable=AsyncMock),
            patch("debaterhub.client._livekit.dispatch_agent", new_callable=AsyncMock),
            patch("debaterhub.client._livekit.create_participant_token", return_value="jwt"),
        ):
            details = await client.create_session(debate_config, warmup=False)
            assert details.room_name.startswith("debate-")


class TestWarmup:
    @pytest.mark.asyncio
    async def test_no_url_returns_none(self, client: DebateClient) -> None:
        result = await client.warmup_agent()
        assert result is None

    @pytest.mark.asyncio
    async def test_warmup_failure_non_fatal(self) -> None:
        c = DebateClient(
            livekit_url="wss://test.com",
            livekit_api_key="k",
            livekit_api_secret="s",
            warmup_url="https://bad.example.com/warmup",
        )
        with patch(
            "debaterhub.client.warmup_agent",
            new_callable=AsyncMock,
            side_effect=WarmupError("fail"),
        ):
            result = await c._try_warmup()
            assert result is None

    @pytest.mark.asyncio
    async def test_warmup_success(self) -> None:
        c = DebateClient(
            livekit_url="wss://test.com",
            livekit_api_key="k",
            livekit_api_secret="s",
            warmup_url="https://warmup.example.com",
        )
        with patch("debaterhub.client.warmup_agent", new_callable=AsyncMock, return_value="ok"):
            result = await c._try_warmup()
            assert result == "ok"

"""DebateClient — main entry point for the debaterhub SDK."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx
from livekit import api

from . import _livekit
from ._data_channel import DataOnlyParticipant
from .config import ConnectionDetails, DebateClientConfig, DebateConfig
from .events import DebateEventHandler
from .exceptions import WarmupError
from .observability import SessionTracer
from .session import ManagedDebateSession
from .warmup import warmup_agent

logger = logging.getLogger(__name__)


class DebateClient:
    """High-level client for creating human-vs-AI debate sessions.

    **Mode 1** — :meth:`create_session`: returns connection details so
    your *frontend* connects to LiveKit directly.

    **Mode 2** — :meth:`create_managed_session`: the SDK joins the room
    as a data-only participant and routes events to a handler your
    *backend* provides.

    Parameters
    ----------
    livekit_url:
        ``wss://`` URL of the LiveKit server.
    livekit_api_key:
        LiveKit API key.
    livekit_api_secret:
        LiveKit API secret.
    agent_name:
        Name of the deployed debate agent (default ``"human-debate-agent"``).
    warmup_url:
        Optional Modal warmup endpoint.
    """

    def __init__(
        self,
        livekit_url: str,
        livekit_api_key: str,
        livekit_api_secret: str,
        *,
        agent_name: str = "human-debate-agent",
        warmup_url: Optional[str] = None,
    ) -> None:
        self._url = livekit_url
        self._api_key = livekit_api_key
        self._api_secret = livekit_api_secret
        self._agent_name = agent_name
        self._warmup_url = warmup_url

        # Lazily initialised (require a running event loop)
        self._http: Optional[httpx.AsyncClient] = None
        self._lk_api: Optional[api.LiveKitAPI] = None

    @property
    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient()
        return self._http

    @property
    def _get_lk_api(self) -> api.LiveKitAPI:
        if self._lk_api is None:
            self._lk_api = api.LiveKitAPI(
                self._url.replace("wss://", "https://"),
                self._api_key,
                self._api_secret,
            )
        return self._lk_api

    @classmethod
    def from_config(cls, config: DebateClientConfig) -> "DebateClient":
        """Construct from a :class:`DebateClientConfig`."""
        return cls(
            livekit_url=config.livekit_url,
            livekit_api_key=config.livekit_api_key,
            livekit_api_secret=config.livekit_api_secret,
            agent_name=config.agent_name,
            warmup_url=config.warmup_url,
        )

    # ------------------------------------------------------------------
    # Mode 1: Token-only
    # ------------------------------------------------------------------

    async def create_session(
        self,
        config: DebateConfig,
        *,
        participant_identity: Optional[str] = None,
        participant_name: str = "Human Debater",
        room_name: Optional[str] = None,
        warmup: bool = True,
    ) -> ConnectionDetails:
        """Create a debate room and return connection details.

        The caller's **frontend** connects to LiveKit with the returned
        token and communicates with the agent directly.
        """
        room_name = room_name or f"debate-{uuid.uuid4().hex[:12]}"
        identity = participant_identity or f"human-{uuid.uuid4().hex[:8]}"

        # Optional warmup (non-fatal)
        if warmup and self._warmup_url:
            await self._try_warmup()

        # Create room
        await _livekit.create_room(self._get_lk_api, room_name)

        # Dispatch agent
        metadata = config.to_dispatch_metadata()
        await _livekit.dispatch_agent(
            self._get_lk_api, room_name, self._agent_name, metadata
        )

        # Generate participant token
        token = _livekit.create_participant_token(
            self._api_key,
            self._api_secret,
            identity=identity,
            name=participant_name,
            room=room_name,
        )

        return ConnectionDetails(
            server_url=self._url,
            room_name=room_name,
            participant_token=token,
        )

    # ------------------------------------------------------------------
    # Mode 2: Server-managed
    # ------------------------------------------------------------------

    async def create_managed_session(
        self,
        config: DebateConfig,
        handler: DebateEventHandler,
        *,
        room_name: Optional[str] = None,
        warmup: bool = True,
    ) -> ManagedDebateSession:
        """Create a debate room and return a managed session.

        The SDK joins the room as a data-only participant and routes
        events to *handler*.
        """
        room_name = room_name or f"debate-{uuid.uuid4().hex[:12]}"

        # Optional warmup
        if warmup and self._warmup_url:
            await self._try_warmup()

        # Create room + dispatch agent
        await _livekit.create_room(self._get_lk_api, room_name)
        metadata = config.to_dispatch_metadata()
        await _livekit.dispatch_agent(
            self._get_lk_api, room_name, self._agent_name, metadata
        )

        # Generate a data-only token for the SDK participant
        sdk_identity = f"sdk-manager-{uuid.uuid4().hex[:8]}"
        token = _livekit.create_participant_token(
            self._api_key,
            self._api_secret,
            identity=sdk_identity,
            name="SDK Manager",
            room=room_name,
            can_subscribe=True,
        )

        # Build and connect the session
        participant = DataOnlyParticipant(
            livekit_url=self._url,
            token=token,
            on_data=lambda raw, topic: None,  # replaced on connect
        )
        tracer = SessionTracer(
            session_id=room_name,
            metadata={"human_side": config.human_side, "resolution": getattr(config, "resolution", "")},
        )
        session = ManagedDebateSession(
            participant=participant,
            handler=handler,
            human_side=config.human_side,
            debate_mode=config.debate_mode,
            tracer=tracer,
        )
        await session.connect()
        return session

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    async def warmup_agent(self) -> Optional[str]:
        """Explicitly warm up the Modal agent containers.

        Returns the status string or ``None`` on failure.
        """
        if not self._warmup_url:
            logger.warning("No warmup_url configured")
            return None
        return await self._try_warmup()

    async def _try_warmup(self) -> Optional[str]:
        try:
            return await warmup_agent(
                self._warmup_url,  # type: ignore[arg-type]
                http_client=self._get_http,
            )
        except WarmupError:
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release shared resources."""
        if self._http is not None:
            await self._http.aclose()
        if self._lk_api is not None:
            await self._lk_api.aclose()

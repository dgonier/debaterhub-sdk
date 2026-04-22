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
from .exceptions import DebatehubError, WarmupError
from .flow_schema import FlowData, FlowGenerateRequest, SpeechTranscript
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
        flow_generate_url: Optional[str] = None,
    ) -> None:
        self._url = livekit_url
        self._api_key = livekit_api_key
        self._api_secret = livekit_api_secret
        self._agent_name = agent_name
        self._warmup_url = warmup_url
        self._flow_generate_url = flow_generate_url

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
            flow_generate_url=getattr(config, "flow_generate_url", None),
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
        on_stall: Optional[Any] = None,
        stall_after_seconds: float = 120.0,
    ) -> ManagedDebateSession:
        """Create a debate room and return a managed session.

        The SDK joins the room as a data-only participant and routes
        events to *handler*.

        Parameters
        ----------
        on_stall
            Optional async callback invoked when no server event has
            arrived for ``stall_after_seconds`` seconds. Signature:
            ``async (elapsed_since_connect, silence_duration,
            last_phase_message) -> None``. The SDK does NOT disconnect
            on stall — the callback decides what to do. Useful for
            tests, user notifications, or alternate fallback paths.
        stall_after_seconds
            How long silence must persist before ``on_stall`` fires.
            Defaults to 120s. Ignored if ``on_stall`` is ``None``.
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
            format=config.format,
            tracer=tracer,
            on_stall=on_stall,
            stall_after_seconds=stall_after_seconds,
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
    # Flow generation
    # ------------------------------------------------------------------

    async def generate_flow(
        self,
        *,
        topic: str,
        speeches: list[SpeechTranscript],
        format: str = "ipda",
        debate_id: str = "",
        url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> FlowData:
        """Generate a page-grouped flow from debate speech transcripts.

        Calls the Modal `debate-flow-generator` app and returns a
        :class:`FlowData` object that matches the frontend wire contract.

        Parameters
        ----------
        topic:
            Debate resolution.
        speeches:
            Ordered list of :class:`SpeechTranscript` (one per speech, CX
            periods included with ``is_cx=True``).
        format:
            Debate format id (``ipda``, ``ld``, ``pf``).
        debate_id:
            Optional debate id for traceability. Generated if empty.
        url:
            Override the Modal endpoint URL. Defaults to the
            ``flow_generate_url`` passed to the client.
        timeout:
            HTTP timeout in seconds.
        """
        endpoint = url or self._flow_generate_url
        if not endpoint:
            raise DebatehubError(
                "generate_flow requires flow_generate_url (pass at client "
                "construction or via the url= kwarg)"
            )

        payload = FlowGenerateRequest(
            topic=topic,
            format=format,
            debate_id=debate_id,
            speeches=list(speeches),
        ).model_dump(by_alias=True, mode="json")

        resp = await self._get_http.post(
            endpoint,
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return FlowData.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release shared resources."""
        if self._http is not None:
            await self._http.aclose()
        if self._lk_api is not None:
            await self._lk_api.aclose()

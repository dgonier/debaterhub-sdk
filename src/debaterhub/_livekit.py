"""Internal LiveKit helpers: room creation, token generation, agent dispatch."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict

from livekit import api

from .exceptions import DispatchError


async def create_room(
    lk_api: api.LiveKitAPI,
    room_name: str,
    *,
    empty_timeout: int = 300,
    max_participants: int = 10,
) -> Any:
    """Create a LiveKit room, returning the room info."""
    return await lk_api.room.create_room(
        api.CreateRoomRequest(
            name=room_name,
            empty_timeout=empty_timeout,
            max_participants=max_participants,
        )
    )


def create_participant_token(
    api_key: str,
    api_secret: str,
    *,
    identity: str,
    name: str,
    room: str,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
    can_update_own_metadata: bool = True,
    ttl: int = 900,  # 15 minutes
) -> str:
    """Generate a JWT access token for a LiveKit participant."""
    token = api.AccessToken(api_key, api_secret)
    token.with_identity(identity)
    token.with_name(name)
    token.with_ttl(datetime.timedelta(seconds=ttl))
    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=can_publish_data,
            can_update_own_metadata=can_update_own_metadata,
        )
    )
    return token.to_jwt()


async def dispatch_agent(
    lk_api: api.LiveKitAPI,
    room_name: str,
    agent_name: str,
    metadata: Dict[str, Any],
) -> Any:
    """Dispatch the debate agent to a room with config metadata."""
    try:
        return await lk_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name=agent_name,
                metadata=json.dumps({"debate_config": metadata}),
            )
        )
    except Exception as exc:
        raise DispatchError(f"Failed to dispatch agent '{agent_name}': {exc}") from exc

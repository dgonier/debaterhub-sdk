"""Optional Modal container warmup."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .exceptions import WarmupError

logger = logging.getLogger(__name__)


async def warmup_agent(
    url: str,
    *,
    timeout: float = 15.0,
    http_client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Hit the Modal warmup endpoint so containers are ready.

    Returns the status string from the response.  On failure, logs a
    warning and raises :class:`WarmupError` (callers can catch or ignore).
    """
    client = http_client or httpx.AsyncClient()
    own_client = http_client is None
    try:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "ok")
        logger.info("Agent warmup succeeded: %s", status)
        return status
    except Exception as exc:
        msg = f"Agent warmup failed ({url}): {exc}"
        logger.warning(msg)
        raise WarmupError(msg) from exc
    finally:
        if own_client:
            await client.aclose()

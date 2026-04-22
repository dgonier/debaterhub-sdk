"""TopicSearchClient — basic vector search over a prepped topic's tree.

Hits the debaterhub backend endpoint `POST /api/debate/topics/{id}/search`
which embeds the query + every belief / argument / evidence node in the
topic's belief tree, returns the top-K cosine-similarity matches.

Usage:
    from debaterhub import TopicSearchClient

    async with TopicSearchClient(
        base_url="https://debaterhub.vercel.app",
        auth_token="<session_token or bearer jwt>",
    ) as client:
        hits = await client.search(
            topic_id="c72f93fa-80f7-41da-ac0f-1918fd9a0d6e",
            query="military deployment authority",
            top_k=10,
        )
        for h in hits:
            print(f"{h.score:.2f}  {h.kind:10s} {h.preview}")

Authentication: the backend gates this endpoint behind the same
`session_token` JWT cookie / `Authorization: Bearer ...` header the
rest of the debate routes use. Pass `auth_token=...` and the SDK sends
it as a Bearer header.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://debaterhub.vercel.app"


class TopicSearchError(RuntimeError):
    """Raised when the backend returns a non-2xx response or a malformed body."""


@dataclass
class SearchHit:
    """One ranked node from a topic's tree.

    Attributes:
        node_id: Walker-local id of the matching node (belief_id,
            argument_id, or evidence_id — depends on `kind`).
        kind: One of "belief" | "argument" | "evidence".
        score: Cosine similarity, roughly 0..1 (higher = closer).
        preview: Short text snippet describing the node (statement for
            beliefs, claim for arguments, tag/cite for evidence).
    """

    node_id: str
    kind: str
    score: float
    preview: str

    @classmethod
    def from_api(cls, raw: Any) -> "SearchHit":
        if not isinstance(raw, dict):
            raise TopicSearchError(f"Unexpected hit payload: {raw!r}")
        try:
            return cls(
                node_id=str(raw["node_id"]),
                kind=str(raw["kind"]),
                score=float(raw["score"]),
                preview=str(raw.get("preview") or ""),
            )
        except KeyError as ke:
            raise TopicSearchError(f"Hit missing field {ke}: {raw!r}") from ke


class TopicSearchClient:
    """Async client for semantic search over a prepped topic's tree.

    All requests go to the debaterhub backend (not Modal directly),
    because the backend owns auth + access control to a user's topics.
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        auth_token: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        request_timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> "TopicSearchClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def search(
        self,
        topic_id: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> List[SearchHit]:
        """Rank the topic's tree nodes by semantic similarity to `query`.

        Results are filtered to a single topic — the backend never
        returns matches from other topics, since the endpoint is
        scoped to the `topic_id` in the URL.

        Args:
            topic_id: The UUID of the topic whose tree to search.
            query: Natural-language search string.
            top_k: Max number of hits to return (1..100).

        Raises:
            TopicSearchError: non-2xx response, or unparseable body.
            ValueError: invalid arguments.
        """
        if not topic_id:
            raise ValueError("topic_id is required")
        q = (query or "").strip()
        if not q:
            raise ValueError("query must be non-empty")
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be in [1, 100]")

        url = f"{self._base_url}/api/debate/topics/{topic_id}/search"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        try:
            resp = await self._http.post(url, headers=headers, json={"query": q, "top_k": top_k})
        except httpx.HTTPError as exc:
            raise TopicSearchError(f"HTTP error calling search: {exc}") from exc

        if resp.status_code == 401:
            raise TopicSearchError(
                "unauthorized — pass auth_token='<session_token jwt>' to the client"
            )
        if resp.status_code == 404:
            raise TopicSearchError(f"topic {topic_id} not found")
        if resp.status_code >= 400:
            raise TopicSearchError(
                f"search failed: {resp.status_code} {resp.text[:200]}"
            )

        body = resp.json()
        if not isinstance(body, list):
            raise TopicSearchError(f"expected list response, got {type(body).__name__}")
        return [SearchHit.from_api(h) for h in body]

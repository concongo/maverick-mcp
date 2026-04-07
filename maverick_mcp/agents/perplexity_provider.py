"""
Perplexity Search API provider for MaverickMCP.

Isolated module — all Perplexity-specific code lives here.
The only upstream touch-points are:
  - settings.py     : PERPLEXITY_API_KEY field (read-only from here)
  - deep_research.py: ~8 lines in initialize() that lazily import this module

Uses the Perplexity Search API (POST https://api.perplexity.ai/search) which
returns structured search results (title, url, snippet, date) — mapping
directly to the pipeline's standardized result format without any LLM parsing.

API reference: https://docs.perplexity.ai/docs/getting-started/search-api
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from maverick_mcp.agents.circuit_breaker import circuit_manager
from maverick_mcp.agents.deep_research import WebSearchProvider
from maverick_mcp.exceptions import WebSearchError

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.perplexity.ai/search"

# Financial domains to prefer in results
_FINANCIAL_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "marketwatch.com",
    "cnbc.com",
    "seekingalpha.com",
    "sec.gov",
    "investor.gov",
    "finance.yahoo.com",
]


class PerplexitySearchProvider(WebSearchProvider):
    """
    Perplexity Search API provider.

    Calls POST /search and converts each result (title, url, snippet, date)
    into the standardized format used by the rest of the research pipeline.
    Supports domain allowlisting and language/country filtering.
    """

    def __init__(
        self,
        api_key: str,
        search_domain_filter: list[str] | None = None,
    ) -> None:
        super().__init__(api_key)
        # Optional domain allowlist — defaults to financial domains
        self.search_domain_filter: list[str] = (
            search_domain_filter
            if search_domain_filter is not None
            else _FINANCIAL_DOMAINS
        )

    # ------------------------------------------------------------------
    # Public interface (required by WebSearchProvider)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        num_results: int = 10,
        timeout_budget: float | None = None,
    ) -> list[dict[str, Any]]:
        if not self.is_healthy():
            raise WebSearchError(
                "Perplexity provider disabled due to repeated failures"
            )

        timeout = self._calculate_timeout(query, timeout_budget)
        circuit_breaker = await circuit_manager.get_or_create(
            "perplexity_search",
            failure_threshold=8,
            recovery_timeout=30,
        )

        async def _call(**_: Any) -> list[dict[str, Any]]:
            # **_ absorbs the `timeout` kwarg the circuit breaker forwards to all callables
            return await self._call_api(query, num_results, timeout)

        try:
            results = await circuit_breaker.call(_call, timeout=timeout)
            self._record_success()
            return results
        except Exception as exc:
            error_type = "timeout" if "timeout" in str(exc).lower() else "unknown"
            self._record_failure(error_type)
            raise WebSearchError(f"Perplexity search failed: {exc}") from exc

    async def get_content(self, url: str) -> dict[str, Any]:
        """Perplexity Search API does not support direct URL content extraction."""
        return {"url": url, "content": "", "provider": "perplexity"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_api(
        self, query: str, num_results: int, timeout: float
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": query,
            "max_results": min(num_results, 20),  # API cap is 20
        }
        if self.search_domain_filter:
            payload["search_domain_filter"] = self.search_domain_filter

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(_SEARCH_URL, json=payload, headers=headers)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        return self._process_response(data, num_results)

    def _process_response(
        self,
        data: dict[str, Any],
        num_results: int,
    ) -> list[dict[str, Any]]:
        """Convert a Perplexity Search API response into the standardized result list."""
        timestamp = datetime.now(UTC).isoformat()
        raw_results: list[dict[str, Any]] = data.get("results", [])
        results: list[dict[str, Any]] = []

        for i, item in enumerate(raw_results[:num_results]):
            url = item.get("url", "")
            domain = urlparse(url).netloc.replace("www.", "")
            snippet = item.get("snippet", "")
            results.append(
                {
                    "url": url,
                    "title": item.get("title", ""),
                    "content": snippet[:2000],
                    "raw_content": snippet,
                    "published_date": item.get("date") or item.get("last_updated"),
                    # Rank by position — Perplexity returns results best-first
                    "score": round(max(0.0, 1.0 - i * 0.05), 2),
                    "provider": "perplexity",
                    "domain": domain,
                    "search_timestamp": timestamp,
                }
            )

        return results

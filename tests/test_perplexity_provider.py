"""
Test suite for the Perplexity Search API provider.

Follows the same structure as test_exa_research_integration.py:
mocked at the HTTP client level so no real API calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick_mcp.agents.perplexity_provider import (
    _FINANCIAL_DOMAINS,
    _SEARCH_URL,
    PerplexitySearchProvider,
)
from maverick_mcp.exceptions import WebSearchError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_api_response(
    results: list[dict] | None = None,
) -> dict:
    """Build a minimal Perplexity Search API response payload."""
    if results is None:
        results = [
            {
                "title": "Apple Q4 Earnings Beat Expectations",
                "url": "https://reuters.com/apple-earnings",
                "snippet": "Apple reported strong quarterly earnings with iPhone sales growth of 15%.",
                "date": "2024-01-15",
                "last_updated": "2024-01-15",
            },
            {
                "title": "Apple Stock Technical Analysis",
                "url": "https://marketwatch.com/apple-technical",
                "snippet": "Apple stock shows bullish patterns with support at $180.",
                "date": "2024-01-14",
                "last_updated": "2024-01-14",
            },
        ]
    return {"id": "test-request-id", "results": results}


def _mock_httpx_client(response_data: dict):
    """Return a context-manager mock for httpx.AsyncClient that yields a fixed response."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_ctx, mock_client


# ---------------------------------------------------------------------------
# PerplexitySearchProvider unit tests
# ---------------------------------------------------------------------------


class TestPerplexitySearchProviderInit:
    """Initialisation and configuration tests."""

    @pytest.mark.unit
    def test_default_initialization(self):
        """Provider initialises with API key and default financial domain filter."""
        provider = PerplexitySearchProvider("test-key-123")

        assert provider.api_key == "test-key-123"
        assert provider.is_healthy() is True
        assert provider._failure_count == 0
        assert provider.search_domain_filter == _FINANCIAL_DOMAINS

    @pytest.mark.unit
    def test_custom_domain_filter(self):
        """Provider accepts a custom domain allowlist."""
        custom_domains = ["wsj.com", "ft.com"]
        provider = PerplexitySearchProvider(
            "test-key", search_domain_filter=custom_domains
        )

        assert provider.search_domain_filter == custom_domains

    @pytest.mark.unit
    def test_empty_domain_filter(self):
        """An explicit empty list disables domain filtering."""
        provider = PerplexitySearchProvider("test-key", search_domain_filter=[])

        assert provider.search_domain_filter == []

    @pytest.mark.unit
    def test_timeout_calculation_simple_query(self):
        """Short queries get a lower base timeout."""
        provider = PerplexitySearchProvider("test-key")
        timeout = provider._calculate_timeout("AAPL", None)

        assert timeout >= 30.0  # Base minimum for search operations

    @pytest.mark.unit
    def test_timeout_calculation_complex_query(self):
        """Complex queries get a higher timeout than simple ones."""
        provider = PerplexitySearchProvider("test-key")
        simple = provider._calculate_timeout("AAPL", None)
        complex_q = "comprehensive financial analysis of Apple Inc earnings valuation and market position"
        complex_ = provider._calculate_timeout(complex_q, None)

        assert complex_ >= simple

    @pytest.mark.unit
    def test_timeout_respects_budget(self):
        """Timeout is capped to the supplied budget (with a 30s floor)."""
        provider = PerplexitySearchProvider("test-key")
        timeout = provider._calculate_timeout("AAPL", 40.0)

        assert 30.0 <= timeout <= 40.0


class TestPerplexitySearchProviderHealth:
    """Health tracking and circuit-breaker behaviour."""

    @pytest.mark.unit
    def test_initial_health(self):
        provider = PerplexitySearchProvider("test-key")
        assert provider.is_healthy() is True

    @pytest.mark.unit
    def test_timeout_failures_accumulate(self):
        """Timeout failures increment counter but don't trip until threshold."""
        provider = PerplexitySearchProvider("test-key")

        for _ in range(5):
            provider._record_failure("timeout")

        assert provider._failure_count == 5
        assert provider.is_healthy() is True  # threshold not yet reached

    @pytest.mark.unit
    def test_provider_disabled_after_threshold(self):
        """Provider becomes unhealthy after exceeding the timeout failure threshold.

        _record_failure uses getattr(..., 'search_timeout_failure_threshold', 12)
        so the default threshold is 12 — iterate past it without touching settings.
        """
        provider = PerplexitySearchProvider("test-key")

        for _ in range(13):  # 13 > default threshold of 12
            provider._record_failure("timeout")

        assert provider.is_healthy() is False

    @pytest.mark.unit
    def test_success_resets_failure_count(self):
        """A successful call resets failure counter and restores health."""
        provider = PerplexitySearchProvider("test-key")

        for _ in range(5):
            provider._record_failure("timeout")

        provider._record_success()

        assert provider._failure_count == 0
        assert provider.is_healthy() is True


class TestPerplexitySearchProviderSearch:
    """search() method — happy path, error handling, result structure."""

    @pytest.mark.unit
    async def test_search_success_result_structure(self):
        """search() returns results with all required standardised fields."""
        provider = PerplexitySearchProvider("test-key")
        mock_ctx, _ = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            results = await provider.search("AAPL financial analysis", num_results=5)

        assert len(results) == 2
        required_fields = {
            "url",
            "title",
            "content",
            "raw_content",
            "published_date",
            "score",
            "provider",
            "domain",
            "search_timestamp",
        }
        for result in results:
            assert required_fields.issubset(result.keys())
            assert result["provider"] == "perplexity"

    @pytest.mark.unit
    async def test_search_results_ranked_by_position(self):
        """First result has a higher score than subsequent ones."""
        provider = PerplexitySearchProvider("test-key")
        mock_ctx, _ = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            results = await provider.search("AAPL", num_results=5)

        assert results[0]["score"] > results[1]["score"]

    @pytest.mark.unit
    async def test_search_sends_correct_payload(self):
        """search() passes query, max_results, and domain filter to the API."""
        provider = PerplexitySearchProvider(
            "test-key", search_domain_filter=["reuters.com"]
        )
        mock_ctx, mock_client = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            await provider.search("AAPL earnings", num_results=7)

        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == _SEARCH_URL
        payload = call_kwargs[1]["json"]
        assert payload["query"] == "AAPL earnings"
        assert payload["max_results"] == 7
        assert payload["search_domain_filter"] == ["reuters.com"]

    @pytest.mark.unit
    async def test_search_omits_domain_filter_when_empty(self):
        """When domain filter is empty, key is not sent to the API."""
        provider = PerplexitySearchProvider("test-key", search_domain_filter=[])
        mock_ctx, mock_client = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            await provider.search("AAPL", num_results=3)

        payload = mock_client.post.call_args[1]["json"]
        assert "search_domain_filter" not in payload

    @pytest.mark.unit
    async def test_search_caps_max_results_at_20(self):
        """API cap of 20 results is enforced even if caller requests more."""
        provider = PerplexitySearchProvider("test-key")
        mock_ctx, mock_client = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            await provider.search("AAPL", num_results=50)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["max_results"] == 20

    @pytest.mark.unit
    async def test_search_sends_auth_header(self):
        """Authorization header contains the correct Bearer token."""
        provider = PerplexitySearchProvider("my-secret-key")
        mock_ctx, mock_client = _mock_httpx_client(_make_api_response())

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            await provider.search("AAPL", num_results=3)

        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer my-secret-key"

    @pytest.mark.unit
    async def test_search_raises_on_unhealthy_provider(self):
        """search() raises WebSearchError immediately when provider is unhealthy."""
        provider = PerplexitySearchProvider("test-key")
        provider._is_healthy = False

        with pytest.raises(WebSearchError, match="disabled due to repeated failures"):
            await provider.search("AAPL")

    @pytest.mark.unit
    async def test_search_records_failure_on_http_error(self):
        """HTTP errors are wrapped as WebSearchError and failure is recorded."""
        provider = PerplexitySearchProvider("test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 401 Unauthorized")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            with pytest.raises(WebSearchError, match="Perplexity search failed"):
                await provider.search("AAPL")

        assert provider._failure_count > 0

    @pytest.mark.unit
    async def test_search_empty_results(self):
        """search() returns an empty list when the API returns no results."""
        provider = PerplexitySearchProvider("test-key")
        mock_ctx, _ = _mock_httpx_client(_make_api_response(results=[]))

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            results = await provider.search("obscure query", num_results=5)

        assert results == []

    @pytest.mark.unit
    async def test_search_respects_num_results_limit(self):
        """Results are truncated to num_results even if the API returns more."""
        many_results = [
            {
                "title": f"Result {i}",
                "url": f"https://reuters.com/{i}",
                "snippet": f"Content {i}",
                "date": None,
                "last_updated": None,
            }
            for i in range(15)
        ]
        provider = PerplexitySearchProvider("test-key")
        mock_ctx, _ = _mock_httpx_client(_make_api_response(results=many_results))

        with patch(
            "maverick_mcp.agents.perplexity_provider.httpx.AsyncClient",
            return_value=mock_ctx,
        ):
            results = await provider.search("query", num_results=5)

        assert len(results) == 5


class TestPerplexitySearchProviderGetContent:
    """get_content() — not supported by the Search API."""

    @pytest.mark.unit
    async def test_get_content_returns_empty(self):
        """get_content() returns a stub — Perplexity Search doesn't extract URLs."""
        provider = PerplexitySearchProvider("test-key")
        result = await provider.get_content("https://reuters.com/some-article")

        assert result["url"] == "https://reuters.com/some-article"
        assert result["content"] == ""
        assert result["provider"] == "perplexity"


class TestPerplexityProcessResponse:
    """_process_response() — result normalisation logic."""

    @pytest.mark.unit
    def test_domain_extracted_from_url(self):
        """Domain is extracted from the URL with www. stripped."""
        provider = PerplexitySearchProvider("test-key")
        data = _make_api_response(
            results=[
                {
                    "title": "Test",
                    "url": "https://www.reuters.com/article",
                    "snippet": "text",
                    "date": None,
                    "last_updated": None,
                }
            ]
        )

        results = provider._process_response(data, num_results=5)

        assert results[0]["domain"] == "reuters.com"

    @pytest.mark.unit
    def test_published_date_prefers_date_field(self):
        """published_date uses 'date' when available."""
        provider = PerplexitySearchProvider("test-key")
        data = _make_api_response(
            results=[
                {
                    "title": "Test",
                    "url": "https://reuters.com/a",
                    "snippet": "text",
                    "date": "2024-01-15",
                    "last_updated": "2024-01-16",
                }
            ]
        )

        results = provider._process_response(data, num_results=5)

        assert results[0]["published_date"] == "2024-01-15"

    @pytest.mark.unit
    def test_published_date_falls_back_to_last_updated(self):
        """published_date falls back to 'last_updated' when 'date' is absent."""
        provider = PerplexitySearchProvider("test-key")
        data = _make_api_response(
            results=[
                {
                    "title": "Test",
                    "url": "https://reuters.com/a",
                    "snippet": "text",
                    "date": None,
                    "last_updated": "2024-01-16",
                }
            ]
        )

        results = provider._process_response(data, num_results=5)

        assert results[0]["published_date"] == "2024-01-16"

    @pytest.mark.unit
    def test_content_truncated_to_2000_chars(self):
        """content field is capped at 2000 characters."""
        provider = PerplexitySearchProvider("test-key")
        long_snippet = "x" * 5000
        data = _make_api_response(
            results=[
                {
                    "title": "Test",
                    "url": "https://reuters.com/a",
                    "snippet": long_snippet,
                    "date": None,
                    "last_updated": None,
                }
            ]
        )

        results = provider._process_response(data, num_results=5)

        assert len(results[0]["content"]) == 2000
        assert results[0]["raw_content"] == long_snippet

    @pytest.mark.unit
    def test_search_timestamp_is_present(self):
        """Each result includes a search_timestamp ISO string."""
        provider = PerplexitySearchProvider("test-key")
        data = _make_api_response()
        results = provider._process_response(data, num_results=5)

        for result in results:
            assert "search_timestamp" in result
            assert result["search_timestamp"]  # non-empty

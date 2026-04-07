# Changelog

All notable custom changes to this fork are documented here.
Upstream changes from [wshobson/maverick-mcp](https://github.com/wshobson/maverick-mcp) are not listed.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.0] - 2026-04-07

### Added

- **Perplexity Search Provider** (`maverick_mcp/agents/perplexity_provider.py`)
  - New isolated `PerplexitySearchProvider` class extending `WebSearchProvider`
  - Calls the Perplexity Search API (`POST https://api.perplexity.ai/search`)
  - Defaults to a financial domain allowlist (`reuters.com`, `bloomberg.com`, `sec.gov`, etc.)
  - Plugs into the deep-research parallel search pipeline automatically when `PERPLEXITY_API_KEY` is set
  - Inherits circuit breaker, health tracking, and timeout management from base class
- **26 unit tests** (`tests/test_perplexity_provider.py`) covering initialization, health tracking, search payload, result structure, error handling, and response parsing
- **`CUSTOM_CHANGES.md`** — fork-specific change log kept separate from upstream `README.md`

### Changed

- `maverick_mcp/config/settings.py` — added `perplexity_api_key` field and `get_perplexity_api_key()` to `ResearchSettings`
- `maverick_mcp/agents/deep_research.py` — 9 lines added inside `initialize()` to lazy-load `PerplexitySearchProvider` when API key is present
- `.env.example` — added commented `PERPLEXITY_API_KEY` entry alongside Exa and Tavily

---

## [0.1.0] - 2026-04-07

### Added

- Initial fork of [wshobson/maverick-mcp](https://github.com/wshobson/maverick-mcp)
- Fork configured with `upstream` remote pointing to original repo for easy syncing

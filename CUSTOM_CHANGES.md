# Custom Changes

This file tracks modifications made to the upstream
[wshobson/maverick-mcp](https://github.com/wshobson/maverick-mcp) fork.

It is intentionally separate from `README.md` so that upstream merges do not
cause conflicts. Add a new entry here whenever a custom feature is introduced
or changed.

---

## [2026-04-07] Perplexity Search Provider

### What was added

| File | Change |
|---|---|
| `maverick_mcp/agents/perplexity_provider.py` | New file — all Perplexity logic lives here |
| `maverick_mcp/config/settings.py` | Added `perplexity_api_key` field and `get_perplexity_api_key()` to `ResearchSettings` |
| `maverick_mcp/agents/deep_research.py` | 9 lines inside `initialize()` — lazy-imports and registers the provider |
| `.env.example` | Added commented `PERPLEXITY_API_KEY` entry |
| `tests/test_perplexity_provider.py` | 26 unit tests covering init, health, search, payload, and response parsing |

### How it works

`PerplexitySearchProvider` extends `WebSearchProvider` (the same base class used
by Exa and Tavily) and calls the
[Perplexity Search API](https://docs.perplexity.ai/docs/getting-started/search-api)
(`POST https://api.perplexity.ai/search`).

When `PERPLEXITY_API_KEY` is set, the provider is automatically appended to the
agent's provider list during `initialize()`. In the main deep-research workflow
(`_execute_searches`), all providers — including Perplexity — are queried
**in parallel** via `asyncio.gather()` and their results are merged and
deduplicated before analysis.

By default the provider sends a financial domain allowlist
(`reuters.com`, `bloomberg.com`, `sec.gov`, etc.) as the
`search_domain_filter` parameter so results stay relevant.

### Enabling it

Add to your `.env` file:

```
PERPLEXITY_API_KEY=pplx-...
```

No other configuration needed — the server picks it up on the next start.

### Upstream conflict surface

Only `settings.py` and `deep_research.py` were modified. The changes are:

- `settings.py` — two new fields appended inside `ResearchSettings`, unlikely to conflict
- `deep_research.py` — 9 lines appended at the end of the `initialize()` try block, unlikely to conflict

If an upstream merge produces a conflict in either file, resolve by keeping
both the upstream changes and the Perplexity block.

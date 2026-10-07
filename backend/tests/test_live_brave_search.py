"""Opt-in live integration tests communicating with Brave Web Search API.

Excluded by default from normal test runs. To run explicitly:
    pytest -m live_search

Requires both:
    RUN_LIVE_SEARCH_TESTS=1
    BRAVE_SEARCH_API_KEY=<valid_key>
"""

import os
import pytest

from app.config import settings
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.evidence.search_provider import SearchResultItem


@pytest.mark.live_search
def test_live_brave_web_search() -> None:
    """Live test calling real Brave Web Search API with structural assertions.

    Requires BOTH:
    - RUN_LIVE_SEARCH_TESTS=1
    - BRAVE_SEARCH_API_KEY (non-empty)
    Otherwise skips safely.
    """
    run_flag = os.environ.get("RUN_LIVE_SEARCH_TESTS") == "1"
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY") or settings.BRAVE_SEARCH_API_KEY

    if not run_flag or not api_key or not api_key.strip():
        pytest.skip("RUN_LIVE_SEARCH_TESTS=1 and BRAVE_SEARCH_API_KEY are required for live search tests.")

    provider = BraveSearchProvider(api_key=api_key.strip())
    results = provider.search(query="B2B SaaS pricing research", max_results=3)

    assert isinstance(results, list)
    assert len(results) >= 1

    first = results[0]
    assert isinstance(first, SearchResultItem)
    assert first.url.startswith("http://") or first.url.startswith("https://")
    assert len(first.title.strip()) > 0
    assert len(first.snippet.strip()) > 0
    assert first.raw_content is None

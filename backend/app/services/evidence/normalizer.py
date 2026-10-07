"""AURA Source Normalizer.

Transforms provider-neutral SearchResultItem records into canonical Source
domain entities while strictly preserving requirement-to-query-to-source
retrieval lineage.

Guarantees:
- Canonicalizes URLs (strips tracking parameters, fragments, normalizes scheme/host).
- Deduplicates Source entities by canonical URL.
- Preserves full retrieval lineage in NormalizedSourceResult.
- Merges metadata deterministically when multiple search results resolve to the same URL.
- Classifies SourceType conservatively (GOVERNMENT, REGULATORY_FILING, or OTHER).
- Day 3 reliability_score is strictly None.
- Zero search provider calls and zero LLM calls.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import Source, SourceType
from app.services.evidence.retriever import RequirementSearchResults
from app.services.evidence.search_provider import SearchResultItem


# ------------------------------------------------------------------------------
# 1. Typed Exceptions
# ------------------------------------------------------------------------------

class SourceNormalizationError(Exception):
    """Raised when an unrecoverable failure occurs during source normalization."""
    pass


# ------------------------------------------------------------------------------
# 2. Bridge Model: NormalizedSourceResult
# ------------------------------------------------------------------------------

class NormalizedSourceResult(BaseModel):
    """Associates a canonical Source with the requirement and query that retrieved it.

    Preserves full retrieval lineage:
    EvidenceRequirement -> search query -> SearchResultItem -> Source.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    requirement_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of parent EvidenceRequirement.",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="Executed search query that retrieved this source.",
    )
    source: Source = Field(
        ...,
        description="Canonical, deduplicated Source domain entity.",
    )
    search_result: Optional[SearchResultItem] = Field(
        default=None,
        description="Originating raw search result containing snippet and raw_content.",
    )


# ------------------------------------------------------------------------------
# 3. URL Canonicalization & Classification Utilities
# ------------------------------------------------------------------------------

# Known tracking parameters to strip during canonicalization
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
    "mc_eid",
}


def canonicalize_url(raw_url: str) -> str:
    """Normalizes a raw URL for deterministic deduplication.

    Rules applied:
    - Strips leading and trailing whitespace.
    - Lowercases scheme and netloc (host).
    - Removes default web ports (:80 for http, :443 for https).
    - Removes fragments (#section).
    - Removes UTM and common tracking query parameters.
    - Preserves meaningful query parameters sorted deterministically.
    - Preserves path casing (paths may be case-sensitive on web servers).
    - Normalizes trailing slashes for non-root paths.

    Raises:
        SourceNormalizationError: If URL is empty, invalid, or cannot be parsed.
    """
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise SourceNormalizationError("URL cannot be empty or contain only whitespace.")

    cleaned = raw_url.strip()
    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise SourceNormalizationError(f"Malformed URL '{cleaned}': {exc}") from exc

    if not parsed.netloc and not parsed.path:
        raise SourceNormalizationError(f"Invalid URL structure: '{cleaned}'.")

    # 1. Scheme & netloc normalization
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()

    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # 2. Path normalization (preserve case, strip redundant trailing slash if not root)
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # 3. Query normalization (strip tracking, preserve meaningful parameters)
    if parsed.query:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_pairs = [
            (k, v) for k, v in query_pairs
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
        # Sort query pairs deterministically by key, then value
        filtered_pairs.sort(key=lambda item: (item[0], item[1]))
        new_query = urlencode(filtered_pairs)
    else:
        new_query = ""

    # 4. Strip fragment completely
    fragment = ""

    canonical = urlunparse((scheme, netloc, path, parsed.params, new_query, fragment))
    return canonical


def classify_source_type(canonical_url: str, publisher: Optional[str] = None) -> SourceType:
    """Conservatively classifies authority source type based on verified domains.

    Rules:
    - REGULATORY_FILING: SEC EDGAR or statutory registry portals.
    - GOVERNMENT: .gov, .mil, or public agency top-level domains.
    - OTHER: Conservative fallback for all other sources.
    """
    try:
        parsed = urlparse(canonical_url)
        host = parsed.netloc.lower()
        if ":" in host:
            host = host.split(":")[0]
    except Exception:
        return SourceType.OTHER

    # 1. Regulatory Filings
    if host == "sec.gov" or host.endswith(".sec.gov") or host == "edgar.sec.gov":
        return SourceType.REGULATORY_FILING
    if host in ("companieshouse.gov.uk", "find-and-update.company-information.service.gov.uk"):
        return SourceType.REGULATORY_FILING

    # 2. Government Entities
    if host.endswith(".gov") or ".gov." in host or host.endswith(".mil") or ".mil." in host or host.endswith(".fed.us"):
        return SourceType.GOVERNMENT

    # Conservative default
    return SourceType.OTHER


# ------------------------------------------------------------------------------
# 4. SourceNormalizer Implementation
# ------------------------------------------------------------------------------

class SourceNormalizer:
    """Normalizes raw SearchResultItem records into canonical Source models.

    Responsibilities:
    - Canonicalizes URLs for deduplication.
    - Deduplicates sources by canonical URL while preserving full retrieval lineage.
    - Merges metadata deterministically when multiple search results resolve to the same URL.
    - Classifies SourceType conservatively.
    - Assigns deterministic, collision-safe IDs (src_1, src_2, ...).
    - Zero LLM dependencies and zero SearchProvider dependencies.
    """

    @staticmethod
    def _merge_source_metadata(
        existing_source: Source,
        incoming_item: SearchResultItem,
        canonical_url: str,
    ) -> Source:
        """Deterministically merges metadata from incoming search result into existing canonical source.

        Policy:
        - title: Prefer longer, more descriptive title.
        - publisher: Prefer non-empty publisher; retain existing if both present.
        - publication_date: Prefer non-null date; if both present, keep earliest date deterministically.
        - source_type: Update from OTHER to specialized type if incoming has verified classification.
        """
        # 1. Title: prefer longer non-empty title (bounded to Source max_length 250)
        chosen_title = existing_source.title
        incoming_title = incoming_item.title.strip() if incoming_item.title else ""
        if incoming_title and len(incoming_title) > len(existing_source.title):
            chosen_title = incoming_title[:250].strip()

        # 2. Publisher: prefer non-empty publisher (bounded to Source max_length 120)
        chosen_publisher = existing_source.publisher
        if not chosen_publisher and incoming_item.publisher and incoming_item.publisher.strip():
            chosen_publisher = incoming_item.publisher.strip()[:120].strip()

        # 3. Publication Date: prefer non-null date; retain deterministic first-seen value on conflict
        chosen_pub_date = existing_source.publication_date
        if chosen_pub_date is None:
            chosen_pub_date = incoming_item.published_date
        # If both are non-null and differ, retain deterministic first-seen value without manufacturing certainty

        # 4. SourceType: update from OTHER if more specific
        chosen_source_type = existing_source.source_type
        if chosen_source_type == SourceType.OTHER:
            new_type = classify_source_type(canonical_url, chosen_publisher)
            if new_type != SourceType.OTHER:
                chosen_source_type = new_type

        return existing_source.model_copy(
            update={
                "title": chosen_title,
                "publisher": chosen_publisher,
                "publication_date": chosen_pub_date,
                "source_type": chosen_source_type,
            }
        )

    def normalize(
        self,
        search_results: List[RequirementSearchResults],
    ) -> List[NormalizedSourceResult]:
        """Converts search results into canonical Source models preserving lineage.

        Args:
            search_results: List of RequirementSearchResults from retrieval stage.

        Returns:
            List of NormalizedSourceResult preserving requirement_id, query, and canonical Source.

        Raises:
            SourceNormalizationError: If an invalid or unparseable URL is encountered.
        """
        lineage_records: List[NormalizedSourceResult] = []
        canonical_sources: Dict[str, Source] = {}
        source_counter = 1

        for req_result in search_results:
            # Skip empty search results (no sources to fabricate)
            if not req_result.results:
                continue

            for item in req_result.results:
                # 1. Canonicalize URL
                canon_url = canonicalize_url(item.url)

                # 2. Check if canonical source already exists
                if canon_url in canonical_sources:
                    # Merge metadata deterministically into existing canonical source
                    merged_source = self._merge_source_metadata(
                        existing_source=canonical_sources[canon_url],
                        incoming_item=item,
                        canonical_url=canon_url,
                    )
                    canonical_sources[canon_url] = merged_source
                    source_instance = merged_source
                else:
                    # 3. Construct new canonical Source
                    source_id = f"src_{source_counter}"
                    source_counter += 1

                    source_type = classify_source_type(canon_url, item.publisher)
                    bounded_title = item.title.strip()[:250].strip()
                    bounded_publisher = (
                        item.publisher.strip()[:120].strip() if item.publisher and item.publisher.strip() else None
                    )

                    new_source = Source(
                        id=source_id,
                        url=canon_url[:2048],
                        title=bounded_title,
                        publisher=bounded_publisher,
                        source_type=source_type,
                        publication_date=item.published_date,
                        retrieval_timestamp=datetime.now(timezone.utc),
                        reliability_score=None,  # Always None in Day 3
                    )
                    canonical_sources[canon_url] = new_source
                    source_instance = new_source

                # 4. Record lineage bridge
                lineage_records.append(
                    NormalizedSourceResult(
                        requirement_id=req_result.requirement_id,
                        query=req_result.query,
                        source=source_instance,
                        search_result=item,
                    )
                )

        # 5. Ensure all lineage records pointing to the same canonical URL reference the merged Source
        # (in case a later item enriched an earlier source)
        for record in lineage_records:
            if record.source.url and record.source.url in canonical_sources:
                record.source = canonical_sources[record.source.url]

        return lineage_records

    @staticmethod
    def extract_unique_sources(lineage_results: List[NormalizedSourceResult]) -> List[Source]:
        """Helper to extract deduplicated list of Source domain entities from lineage records."""
        seen_ids: Set[str] = set()
        unique_sources: List[Source] = []
        for record in lineage_results:
            if record.source.id not in seen_ids:
                seen_ids.add(record.source.id)
                unique_sources.append(record.source)
        return unique_sources

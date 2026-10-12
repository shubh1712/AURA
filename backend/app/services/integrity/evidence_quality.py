"""Evidence Quality and Source Classification Service (Day 8G-B).

Implements transparent evidence categorization and deduplication:
- Primary empirical research (.edu, peer-reviewed, arxiv, clinical, benchmark)
- Official regulatory or standards sources (.gov, iso, nist, w3c)
- Independent secondary research (reuters, bloomberg, statista, gartner)
- Vendor-produced material (product marketing, corporate whitepapers)
- Opinion or commentary (blogs, opinion columns, substack, medium)
- Duplicate URL detection and citation tracking
"""

import logging
import re
from typing import Dict, List, Set
from urllib.parse import urlparse

from app.schemas.decision_integrity import (
    EvidenceQualityReport,
    SourceCategory,
    SourceQualityClassification,
)
from app.schemas.evidence import EvidencePackage, Source

logger = logging.getLogger(__name__)


class EvidenceQualityService:
    """Evaluates evidence quality, classifies sources transparently, and detects duplicates."""

    def evaluate_evidence(self, evidence_package: EvidencePackage) -> EvidenceQualityReport:
        """Classifies and deduplicates all sources in the evidence package."""
        classified_sources: List[SourceQualityClassification] = []
        seen_urls: Dict[str, str] = {}

        primary_cnt = 0
        secondary_cnt = 0
        vendor_cnt = 0
        duplicate_cnt = 0

        for src in evidence_package.sources:
            url = (src.url or "").strip()
            url_norm = url.lower().rstrip("/")
            is_dup = False
            dup_of: str = ""

            if url_norm and len(url_norm) > 10:
                if url_norm in seen_urls:
                    is_dup = True
                    dup_of = seen_urls[url_norm]
                    duplicate_cnt += 1
                else:
                    seen_urls[url_norm] = src.id

            category, is_independent, limitations = self._classify_source(src)

            if category == SourceCategory.PRIMARY_RESEARCH:
                primary_cnt += 1
            elif category == SourceCategory.INDEPENDENT_SECONDARY:
                secondary_cnt += 1
            elif category == SourceCategory.VENDOR_PRODUCED:
                vendor_cnt += 1

            classified_sources.append(
                SourceQualityClassification(
                    source_id=src.id,
                    title=src.title,
                    url=src.url,
                    category=category,
                    is_independent=is_independent,
                    is_duplicate=is_dup,
                    limitations=limitations,
                    stance="supporting",
                )
            )

        total = len(classified_sources)
        independent_cnt = sum(1 for s in classified_sources if s.is_independent and not s.is_duplicate)
        independence_ratio = (independent_cnt / total) if total > 0 else 1.0

        summary = (
            f"Evaluated {total} evidence source(s): {primary_cnt} primary/empirical, "
            f"{secondary_cnt} independent secondary, {vendor_cnt} vendor-produced, "
            f"and {duplicate_cnt} duplicate reference(s). "
            f"Independence ratio: {independence_ratio * 100:.1f}%."
        )

        return EvidenceQualityReport(
            sources=classified_sources,
            primary_count=primary_cnt,
            secondary_count=secondary_cnt,
            vendor_count=vendor_cnt,
            duplicate_count=duplicate_cnt,
            independence_ratio=round(independence_ratio, 3),
            summary=summary,
        )

    def _classify_source(self, source: Source) -> tuple[SourceCategory, bool, List[str]]:
        """Classifies source based on URL domain and title cues."""
        url = (source.url or "").lower()
        title = (source.title or "").lower()
        limitations: List[str] = []

        domain = ""
        if url:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
            except Exception:
                domain = ""

        # 1. Official Standards or Regulatory
        if any(d in domain for d in [".gov", "nist.gov", "iso.org", "w3.org", "ietf.org", "sec.gov", "europa.eu"]):
            return (
                SourceCategory.OFFICIAL_STANDARDS,
                True,
                ["Standards provide normative guidance but may lag cutting-edge vendor releases."],
            )

        # 2. Primary Empirical Research
        if any(d in domain for d in [".edu", "arxiv.org", "ncbi.nlm.nih.gov", "ieee.org", "acm.org", "nature.com", "sciencedirect.com"]):
            return (
                SourceCategory.PRIMARY_RESEARCH,
                True,
                ["Academic or lab benchmarks may reflect specialized testbeds rather than enterprise production."],
            )

        # 3. Opinion or Commentary
        if any(d in domain for d in ["medium.com", "substack.com", "wordpress.com", "blogspot.com"]) or "opinion" in title:
            return (
                SourceCategory.OPINION_COMMENTARY,
                True,
                ["Subjective practitioner editorial; lacks peer-reviewed statistical validation."],
            )

        # 4. Independent Secondary Research / News
        if any(d in domain for d in ["reuters.com", "bloomberg.com", "statista.com", "gartner.com", "forrester.com", "wsj.com", "ft.com", "techcrunch.com"]):
            return (
                SourceCategory.INDEPENDENT_SECONDARY,
                True,
                ["Secondary synthesis based on survey samples or reporter interviews."],
            )

        # 5. Vendor-Produced Material
        vendor_cues = ["pricing", "features", "solution", "product", "docs", "blog", "customer-story", "case-study"]
        if any(cue in url for cue in vendor_cues) or any(d in domain for d in [".io", ".com", ".ai"]):
            return (
                SourceCategory.VENDOR_PRODUCED,
                False,
                ["Commercial vendor material; inherent incentive to emphasize benefits and understate operational overhead."],
            )

        return (
            SourceCategory.UNKNOWN,
            True,
            ["Source origin could not be definitively matched against trusted classification registries."],
        )

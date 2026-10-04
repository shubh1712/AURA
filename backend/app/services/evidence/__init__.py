"""AURA Evidence Service Package."""

from app.services.evidence.gaps import (
    EvidenceGapDetectionResult,
    EvidenceGapDetector,
)
from app.services.evidence.mapper import (
    CandidateEvidenceMappingPayload,
    CandidateFinding,
    CandidateNumericEvidence,
    EvidenceMapper,
    EvidenceMappingResult,
    build_mapping_prompt,
    get_default_candidate_findings,
)
from app.services.evidence.normalizer import (
    NormalizedSourceResult,
    SourceNormalizationError,
    SourceNormalizer,
    canonicalize_url,
    classify_source_type,
)
from app.services.evidence.requirements import (
    CandidateEvidenceRequirement,
    CandidateRequirementsPayload,
    EvidenceRequirementEngine,
    build_requirements_prompt,
    validate_target_reference,
)
from app.services.evidence.brave_search import (
    BRAVE_SEARCH_API_ENDPOINT,
    BraveSearchProvider,
)
from app.services.evidence.retriever import (
    EvidenceRetriever,
    EvidenceRetrieverError,
    RequirementSearchResults,
)
from app.services.evidence.search_provider import (
    FakeSearchProvider,
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProvider,
    SearchProviderError,
    SearchRateLimitError,
    SearchResponseError,
    SearchResultItem,
    SearchTimeoutError,
    UnknownSearchQueryError,
)

from app.services.evidence.service import (
    EvidenceService,
    EvidenceServiceError,
    build_deterministic_summary,
)

__all__ = [
    # Search Provider
    "SearchResultItem",
    "SearchProvider",
    "FakeSearchProvider",
    "BraveSearchProvider",
    "BRAVE_SEARCH_API_ENDPOINT",
    "SearchProviderError",
    "SearchAuthenticationError",
    "SearchRateLimitError",
    "SearchTimeoutError",
    "SearchNetworkError",
    "SearchResponseError",
    "UnknownSearchQueryError",
    # Requirements Engine
    "CandidateEvidenceRequirement",
    "CandidateRequirementsPayload",
    "EvidenceRequirementEngine",
    "build_requirements_prompt",
    "validate_target_reference",
    # Evidence Retriever
    "EvidenceRetriever",
    "EvidenceRetrieverError",
    "RequirementSearchResults",
    # Source Normalizer
    "SourceNormalizer",
    "NormalizedSourceResult",
    "SourceNormalizationError",
    "canonicalize_url",
    "classify_source_type",
    # Evidence Mapper
    "EvidenceMapper",
    "EvidenceMappingResult",
    "CandidateEvidenceMappingPayload",
    "CandidateFinding",
    "CandidateNumericEvidence",
    "build_mapping_prompt",
    "get_default_candidate_findings",
    # Evidence Gap Detector
    "EvidenceGapDetector",
    "EvidenceGapDetectionResult",
    # Evidence Service
    "EvidenceService",
    "EvidenceServiceError",
    "build_deterministic_summary",
]






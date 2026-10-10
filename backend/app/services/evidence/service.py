"""AURA Evidence Service.

Coordinates end-to-end evidence gathering, source normalization, factual mapping,
and empirical gap detection to assemble a validated EvidencePackage.

Guarantees:
- Pure orchestration: coordinates existing subcomponents without duplicating domain logic.
- Fully dependency-injected: accepts engines/providers; never instantiates Gemini or search providers directly.
- Deterministic assembly: uses gap-detector updated requirements, canonical unique sources, and deterministic summary.
- Comprehensive referential and cross-model validation against the DecisionModel.
- Strict error propagation preserving stage context and causal exceptions.
- Zero LLM calls and zero external network calls in EvidenceService itself.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import (
    EvidenceGap,
    EvidenceItem,
    EvidencePackage,
    EvidenceRequirement,
    RequirementStatus,
    Source,
)
from app.services.evidence.gaps import EvidenceGapDetector
from app.services.evidence.mapper import (
    MAX_EVIDENCE_MAPPING_BATCHES,
    MAX_EVIDENCE_MAPPING_WORKERS,
    EvidenceMapper,
)
from app.services.evidence.normalizer import SourceNormalizer
from app.services.evidence.requirements import (
    EvidenceRequirementEngine,
    validate_target_reference,
)
from app.services.evidence.retriever import (
    MAX_SEARCH_QUERIES_PER_ANALYSIS,
    EvidenceRetriever,
)
from app.services.evidence.search_provider import SearchProvider, SearchTimeoutError
from app.services.llm.client import LLMClient, LLMTimeoutError


# ------------------------------------------------------------------------------
# 1. Typed Exception
# ------------------------------------------------------------------------------

class EvidenceServiceError(Exception):
    """Raised when an unrecoverable failure occurs during evidence pipeline orchestration."""

    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.details = details or {}


# ------------------------------------------------------------------------------
# 2. Deterministic Summary Builder
# ------------------------------------------------------------------------------

def build_deterministic_summary(
    requirements: List[EvidenceRequirement],
    sources: List[Source],
    items: List[EvidenceItem],
    gaps: List[EvidenceGap],
) -> str:
    """Builds a strictly deterministic, factual synthesis of package state."""
    total_reqs = len(requirements)

    status_counts: Dict[RequirementStatus, int] = {}
    for r in requirements:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    status_parts = []
    for st in [
        RequirementStatus.FULFILLED,
        RequirementStatus.CONTESTED,
        RequirementStatus.INCONCLUSIVE,
        RequirementStatus.UNSUPPORTED,
        RequirementStatus.PENDING,
    ]:
        cnt = status_counts.get(st, 0)
        if cnt > 0:
            status_parts.append(f"{cnt} {st.value}")

    if total_reqs == 0:
        req_summary = "0 evidence requirements"
    elif status_parts:
        req_summary = f"{total_reqs} evidence requirements: {', '.join(status_parts)}"
    else:
        req_summary = f"{total_reqs} evidence requirements"

    total_sources = len(sources)
    total_items = len(items)
    total_gaps = len(gaps)

    gap_suffix = "gap remains" if total_gaps == 1 else "gaps remain"

    lines = [
        f"{req_summary}.",
        f"{total_sources} unique sources and {total_items} evidence findings were identified.",
        f"{total_gaps} evidence {gap_suffix}.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# 3. EvidenceService Implementation
# ------------------------------------------------------------------------------

class EvidenceService:
    """Coordinates evidence requirements, retrieval, normalization, mapping, and gap analysis."""

    def __init__(
        self,
        requirement_engine: EvidenceRequirementEngine,
        retriever: EvidenceRetriever,
        normalizer: SourceNormalizer,
        mapper: EvidenceMapper,
        gap_detector: EvidenceGapDetector,
    ) -> None:
        """Initializes EvidenceService with injected subcomponents.

        Args:
            requirement_engine: Engine deriving investigative requirements from DecisionModel.
            retriever: Component executing external research queries.
            normalizer: Component normalizing and deduplicating sources.
            mapper: Component extracting findings and binding them to decision entities.
            gap_detector: Engine identifying deficiencies and determining requirement statuses.
        """
        self.requirement_engine = requirement_engine
        self.retriever = retriever
        self.normalizer = normalizer
        self.mapper = mapper
        self.gap_detector = gap_detector

    @classmethod
    def create_default(
        cls,
        llm_client: LLMClient,
        search_provider: SearchProvider,
        max_search_queries: int = MAX_SEARCH_QUERIES_PER_ANALYSIS,
        max_mapping_workers: int = MAX_EVIDENCE_MAPPING_WORKERS,
        max_mapping_batches: int = MAX_EVIDENCE_MAPPING_BATCHES,
    ) -> "EvidenceService":
        """Factory helper creating an EvidenceService wired with provided LLM and Search providers."""
        retriever = EvidenceRetriever(search_provider=search_provider)
        retriever.max_total_queries = max_search_queries
        mapper = EvidenceMapper(llm_client=llm_client)
        mapper.max_workers = max_mapping_workers
        mapper.max_batches = max_mapping_batches
        return cls(
            requirement_engine=EvidenceRequirementEngine(llm_client=llm_client),
            retriever=retriever,
            normalizer=SourceNormalizer(),
            mapper=mapper,
            gap_detector=EvidenceGapDetector(),
        )

    def build_evidence_package(
        self,
        decision_model: DecisionModel,
        deadline_monotonic: Optional[float] = None,
    ) -> EvidencePackage:
        """Orchestrates evidence gathering and produces a validated EvidencePackage.

        Sequence:
        1. requirement_engine.generate_requirements(decision_model)
        2. retriever.retrieve(requirements)
        3. normalizer.normalize(retrieval_results)
        4. mapper.map_evidence(decision_model, requirements, normalized_sources)
        5. gap_detector.detect_gaps(decision_model, requirements, mapping_result)
        6. Extract unique canonical Sources
        7. Cross-model target validation
        8. Construct validated EvidencePackage

        Args:
            decision_model: Canonical DecisionModel to evaluate.
            deadline_monotonic: Optional absolute monotonic deadline for the evidence orchestration.

        Returns:
            Fully assembled, referentially validated EvidencePackage.

        Raises:
            EvidenceServiceError: On unrecoverable failure at any pipeline stage.
        """
        # Stage 1: Requirement Generation
        t_start_evidence = time.monotonic()
        t0_sub = time.monotonic()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise LLMTimeoutError("Operation timed out before evidence requirements could begin.")

        try:
            requirements = self.requirement_engine.generate_requirements(
                decision_model,
                deadline_monotonic=deadline_monotonic,
            )
            t_req = time.monotonic() - t0_sub
            logger.info(
                "Evidence substage 'requirement_generation' completed in %.2fs (requirements=%d)",
                t_req,
                len(requirements),
            )
        except Exception as err:
            t_fail = time.monotonic() - t0_sub
            logger.warning(
                "Evidence substage 'requirement_generation' failed after %.2fs with %s",
                t_fail,
                type(err).__name__,
            )
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'requirement_generation': {err}",
                stage="requirement_generation",
            ) from err

        # Stage 2: Retrieval
        t0_sub = time.monotonic()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise SearchTimeoutError("Operation timed out before evidence retrieval could begin.")

        try:
            retrieval_results = self.retriever.retrieve(
                requirements,
                deadline_monotonic=deadline_monotonic,
            )
            t_ret = time.monotonic() - t0_sub
            total_items = sum(len(r.results) for r in retrieval_results)
            logger.info(
                "Evidence substage 'retrieval' completed in %.2fs (queries=%d, results=%d)",
                t_ret,
                len(retrieval_results),
                total_items,
            )
        except Exception as err:
            t_fail = time.monotonic() - t0_sub
            logger.warning(
                "Evidence substage 'retrieval' failed after %.2fs with %s",
                t_fail,
                type(err).__name__,
            )
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'retrieval': {err}",
                stage="retrieval",
            ) from err

        # Stage 3: Normalization
        t0_sub = time.monotonic()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise SearchTimeoutError("Operation timed out before source normalization could begin.")

        try:
            normalized_sources = self.normalizer.normalize(retrieval_results)
            t_norm = time.monotonic() - t0_sub
            logger.info(
                "Evidence substage 'normalization' completed in %.2fs (normalized_sources=%d)",
                t_norm,
                len(normalized_sources),
            )
        except Exception as err:
            t_fail = time.monotonic() - t0_sub
            logger.warning(
                "Evidence substage 'normalization' failed after %.2fs with %s",
                t_fail,
                type(err).__name__,
            )
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'normalization': {err}",
                stage="normalization",
            ) from err

        # Stage 4: Evidence Mapping
        t0_sub = time.monotonic()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise LLMTimeoutError("Operation timed out before evidence mapping could begin.")

        try:
            mapping_result = self.mapper.map_evidence(
                decision_model=decision_model,
                requirements=requirements,
                normalized_sources=normalized_sources,
                deadline_monotonic=deadline_monotonic,
            )
            t_map = time.monotonic() - t0_sub
            logger.info(
                "Evidence substage 'mapping' completed in %.2fs (items=%d, claim_links=%d)",
                t_map,
                len(mapping_result.items),
                len(mapping_result.claim_links),
            )
        except Exception as err:
            t_fail = time.monotonic() - t0_sub
            err_details = getattr(err, "details", {}) if hasattr(err, "details") else {}
            err_cat = getattr(err, "category", None) or (err_details.get("category") if isinstance(err_details, dict) else None) or type(err).__name__
            err_schema = err_details.get("schema") if isinstance(err_details, dict) else None
            err_fields = err_details.get("field_paths") if isinstance(err_details, dict) else None
            logger.warning(
                "Evidence substage 'mapping' failed after %.2fs with %s (category=%s, schema=%s, field_paths=%s)",
                t_fail,
                type(err).__name__,
                err_cat,
                err_schema,
                err_fields,
            )
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'mapping': {err}",
                stage="mapping",
                details=err_details if isinstance(err_details, dict) else {},
            ) from err

        # Stage 5: Gap Detection & Status Resolution
        t0_sub = time.monotonic()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise LLMTimeoutError("Operation timed out before gap detection could begin.")

        try:
            gap_result = self.gap_detector.detect_gaps(
                decision_model=decision_model,
                requirements=requirements,
                mapping_result=mapping_result,
            )
            t_gap = time.monotonic() - t0_sub
            logger.info(
                "Evidence substage 'gap_detection' completed in %.2fs (gaps=%d)",
                t_gap,
                len(gap_result.gaps),
            )
        except Exception as err:
            t_fail = time.monotonic() - t0_sub
            logger.warning(
                "Evidence substage 'gap_detection' failed after %.2fs with %s",
                t_fail,
                type(err).__name__,
            )
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'gap_detection': {err}",
                stage="gap_detection",
            ) from err

        # Stage 6: Source Collection (Extract unique canonical Sources)
        seen_source_ids: Set[str] = set()
        unique_sources: List[Source] = []
        for norm in normalized_sources:
            if norm.source.id not in seen_source_ids:
                seen_source_ids.add(norm.source.id)
                unique_sources.append(norm.source)

        # Stage 7: Cross-Model Target Validation
        try:
            for r in gap_result.requirements:
                validate_target_reference(
                    decision_model=decision_model,
                    target_id=r.target_entity_id,
                    target_type=r.target_entity_type,
                )
            for link in mapping_result.claim_links:
                validate_target_reference(
                    decision_model=decision_model,
                    target_id=link.target_entity_id,
                    target_type=link.target_entity_type,
                )
            for gap in gap_result.gaps:
                validate_target_reference(
                    decision_model=decision_model,
                    target_id=gap.target_entity_id,
                    target_type=gap.target_entity_type,
                )
        except Exception as err:
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'cross_model_validation': {err}",
                stage="cross_model_validation",
            ) from err

        # Stage 8: Package Assembly & Validation
        summary = build_deterministic_summary(
            requirements=gap_result.requirements,
            sources=unique_sources,
            items=mapping_result.items,
            gaps=gap_result.gaps,
        )
        package_id = f"evpkg_{decision_model.id}"[:64]

        try:
            pkg = EvidencePackage(
                id=package_id,
                decision_model_id=decision_model.id,
                requirements=gap_result.requirements,  # Updated requirements from gap detector
                sources=unique_sources,
                items=mapping_result.items,
                claim_links=mapping_result.claim_links,
                gaps=gap_result.gaps,
                summary=summary,
                created_at=datetime.now(timezone.utc),
            )
            logger.info(
                "Evidence orchestration completed successfully in %.2fs (sources=%d, items=%d, gaps=%d)",
                time.monotonic() - t_start_evidence,
                len(unique_sources),
                len(mapping_result.items),
                len(gap_result.gaps),
            )
            return pkg
        except Exception as err:
            raise EvidenceServiceError(
                f"Evidence orchestration failed at stage 'packaging': {err}",
                stage="packaging",
            ) from err

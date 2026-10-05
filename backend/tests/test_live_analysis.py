"""Opt-in live integration test for end-to-end Decision Analysis with EvidenceService.

Excluded by default from normal test runs. To execute explicitly:
    RUN_LIVE_ANALYSIS_TESTS=1 pytest tests/test_live_analysis.py -m live_analysis -v

Requires:
    RUN_LIVE_ANALYSIS_TESTS=1
    GEMINI_API_KEY
    BRAVE_SEARCH_API_KEY
"""

import os
from typing import Set
import pytest

from app.config import settings
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.decision_model import DecisionModel
from app.schemas.evidence import EvidencePackage
from app.services.analysis_service import AnalysisService
from app.services.evidence.brave_search import BraveSearchProvider
from app.services.evidence.service import EvidenceService
from app.services.llm.gemini import GeminiLLMClient


@pytest.mark.live_analysis
def test_live_end_to_end_analysis() -> None:
    """Performs a live, real end-to-end analysis using Gemini and Brave Search.

    Validates structural invariants without asserting non-deterministic wording or rankings:
    - DecisionModel exists and is valid.
    - EvidencePackage exists and is valid.
    - Source IDs are unique.
    - EvidenceItem.source_id references resolve to Sources in the package.
    - ClaimEvidenceLink.evidence_item_id references resolve to EvidenceItems in the package.
    - ClaimEvidenceLink.requirement_id references resolve to Requirements in the package.
    - Source.reliability_score remains strictly None.
    - No recommendation field exists anywhere in schemas or responses.
    """
    run_flag = os.environ.get("RUN_LIVE_ANALYSIS_TESTS") == "1"
    gemini_key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY") or settings.BRAVE_SEARCH_API_KEY

    if not run_flag or not gemini_key or not gemini_key.strip() or not brave_key or not brave_key.strip():
        pytest.skip(
            "RUN_LIVE_ANALYSIS_TESTS=1, GEMINI_API_KEY, and BRAVE_SEARCH_API_KEY are required for live analysis tests."
        )

    real_llm = GeminiLLMClient(api_key=gemini_key.strip())
    real_search = BraveSearchProvider(api_key=brave_key.strip())
    real_evidence_svc = EvidenceService.create_default(
        llm_client=real_llm,
        search_provider=real_search,
    )
    analysis_svc = AnalysisService(
        llm_client=real_llm,
        evidence_service=real_evidence_svc,
    )

    request = AnalysisRequest(
        question="Should our SaaS startup reduce pricing by 20% to increase customer acquisition?"
    )
    response = analysis_svc.analyze(request)

    # 1. DecisionModel exists and matches contract
    assert response.decision_model is not None
    assert isinstance(response.decision_model, DecisionModel)
    assert len(response.decision_model.objectives) >= 1
    assert len(response.decision_model.variables) >= 1

    # 2. EvidencePackage exists and matches contract
    assert response.evidence_package is not None
    assert isinstance(response.evidence_package, EvidencePackage)
    pkg = response.evidence_package
    assert pkg.decision_model_id == response.decision_model.id

    # 3. Source IDs are unique
    source_ids = [s.id for s in pkg.sources]
    assert len(source_ids) == len(set(source_ids))
    source_id_set = set(source_ids)

    # 4. EvidenceItem.source_id references resolve
    item_id_set: Set[str] = set()
    for item in pkg.items:
        item_id_set.add(item.id)
        assert item.source_id in source_id_set

    # 5. ClaimEvidenceLink references resolve
    req_id_set = {r.id for r in pkg.requirements}
    for link in pkg.claim_links:
        # evidence_item_id resolves to an EvidenceItem in the package
        assert link.evidence_item_id in item_id_set
        # requirement_id resolves to an EvidenceRequirement in the package if present
        if link.requirement_id:
            assert link.requirement_id in req_id_set

    # 6. Source reliability_score remains strictly None in Day 3
    for s in pkg.sources:
        assert s.reliability_score is None
    assert not hasattr(EvidencePackage, "reliability_score")

    # 7. No recommendation field exists
    assert "recommendation" not in AnalysisResponse.model_fields
    assert not hasattr(response, "recommendation")
    response_dict = response.model_dump()
    assert "recommendation" not in response_dict
    assert "recommendation" not in response_dict["evidence_package"]

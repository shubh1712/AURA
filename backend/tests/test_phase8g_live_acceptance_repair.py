"""Realistic Regression Tests for Day 8G Live Acceptance Repair.

Verifies:
- Live/legacy persisted analysis schemas (e.g. Constraint without .statement, IntelligentActionItem without .phase).
- Deterministic integrity report generation with legitimate warnings.
- Shared report, Summary report, Detailed report JSON generation via TestClient.
- Vector PDF endpoints (Summary & Detailed) returning valid application/pdf with expected content.
- Zero extra Gemini calls made during report viewing or PDF downloads.
"""

from pathlib import Path
import zlib
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfbase.pdfutils import asciiBase85Decode

from app.main import app
from app.services.jobs.storage import SQLiteJobStorage
from app.services.jobs.manager import AnalysisJobManager
from app.services.report.service import ReportService
from app.services.integrity.service import DecisionIntegrityService
from app.services.report.pdf_generator import AuraPDFGenerator


@pytest.fixture
def real_analysis_id():
    return "b2abf510-aacb-44d7-8a11-7cc40806cca1"


@pytest.fixture
def test_client():
    return TestClient(app)


def extract_pdf_decompressed_streams(pdf_bytes: bytes) -> str:
    """Extracts and decompresses AsciiBase85 + FlateDecode streams from ReportLab PDF."""
    text_content = ""
    idx = 0
    while True:
        st = pdf_bytes.find(b"stream\n", idx)
        if st == -1:
            break
        st_data = st + len(b"stream\n")
        en = pdf_bytes.find(b"endstream", st_data)
        if en == -1:
            break
        raw = pdf_bytes[st_data:en]
        try:
            decoded = asciiBase85Decode(raw)
            decomp = zlib.decompress(decoded).decode("latin1", errors="ignore")
            text_content += decomp + "\n"
        except Exception:
            pass
        idx = en + len(b"endstream")
    return text_content


def test_real_saved_analysis_integrity_endpoint(test_client, real_analysis_id):
    """GET /api/analysis/{analysis_id}/integrity returns HTTP 200 with valid schema."""
    resp = test_client.get(f"/api/analysis/{real_analysis_id}/integrity")
    assert resp.status_code == 200, f"Integrity endpoint failed: {resp.text}"
    data = resp.json()

    # Verify required schema fields and aliases
    assert "overall_status" in data or "overall_integrity_status" in data
    assert "findings" in data
    assert "calculations" in data
    assert "option_comparison" in data
    assert "evidence_quality" in data
    assert "uncertainty_calibration" in data

    # Verify legitimate unresolved findings exist (not fake success)
    status_val = data.get("overall_status") or data.get("overall_integrity_status")
    assert status_val in ("warning", "critical_concerns", "insufficient_data")
    assert len(data["findings"]) > 0

    # Ensure calculations contain unresolved findings without throwing
    calc_statuses = [c.get("status") for c in data["calculations"]]
    assert "unresolved" in calc_statuses


def test_real_saved_analysis_report_json_endpoints(test_client, real_analysis_id):
    """GET /api/analysis/{analysis_id}/report, /summary, /detailed all return HTTP 200."""
    modes = [
        (f"/api/analysis/{real_analysis_id}/report", "shared"),
        (f"/api/analysis/{real_analysis_id}/report/summary", "summary"),
        (f"/api/analysis/{real_analysis_id}/report/detailed", "detailed"),
    ]

    for endpoint, expected_mode in modes:
        resp = test_client.get(endpoint)
        assert resp.status_code == 200, f"Report endpoint {endpoint} failed: {resp.text}"
        data = resp.json()

        assert data["analysis_id"] == real_analysis_id
        assert data["report_mode"] == expected_mode
        assert "overview" in data
        assert data["overview"]["title"] != ""
        assert "calculations" in data
        assert "evidence_quality" in data
        assert "uncertainty_calibration" in data
        assert "integrity_findings" in data
        assert "action_roadmap" in data or "roadmap" in data


def test_real_saved_analysis_summary_pdf_endpoint(test_client, real_analysis_id):
    """GET /api/analysis/{analysis_id}/report/summary/pdf returns valid PDF."""
    resp = test_client.get(f"/api/analysis/{real_analysis_id}/report/summary/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-1.4")
    assert len(resp.content) > 5000

    # Inspect PDF byte stream for core markers
    content_text = extract_pdf_decompressed_streams(resp.content)
    assert "AURA" in content_text
    assert "EXECUTIVE DECISION SUMMARY" in content_text
    assert "RECOMMENDED" in content_text


def test_real_saved_analysis_detailed_pdf_endpoint(test_client, real_analysis_id):
    """GET /api/analysis/{analysis_id}/report/detailed/pdf returns valid multi-page audit PDF."""
    resp = test_client.get(f"/api/analysis/{real_analysis_id}/report/detailed/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-1.4")
    assert len(resp.content) > 10000

    # Inspect PDF byte stream for core markers
    content_text = extract_pdf_decompressed_streams(resp.content)
    assert "AURA" in content_text
    assert "Comprehensive Audit" in content_text or "Decision" in content_text


def test_zero_gemini_calls_on_report_and_pdf_generation(real_analysis_id, monkeypatch):
    """Ensure report assembly and PDF rendering execute zero Gemini/LLM network calls."""
    from app.services.llm.gemini import GeminiLLMClient

    def bomb(*args, **kwargs):
        raise AssertionError("Gemini / LLM client was called during report viewing or PDF generation!")

    # Guard all potential LLM entrypoints
    monkeypatch.setattr(GeminiLLMClient, "generate_structured", bomb)

    storage = SQLiteJobStorage(db_path="aura_jobs.db")
    mgr = AnalysisJobManager(storage=storage)
    svc = ReportService(manager=mgr)
    pdf_gen = AuraPDFGenerator()

    # Assembly
    rep = svc.get_shared_report(real_analysis_id, mode="detailed")
    assert rep.analysis_id == real_analysis_id

    # PDF generation
    summary_pdf = pdf_gen.generate_summary_pdf(rep)
    assert summary_pdf.startswith(b"%PDF-1.4")

    detailed_pdf = pdf_gen.generate_detailed_pdf(rep)
    assert detailed_pdf.startswith(b"%PDF-1.4")

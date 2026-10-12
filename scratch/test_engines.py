import sys, os
sys.path.insert(0, os.path.abspath("backend"))
import sqlite3
import json
import traceback

from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.integrity.calculator import DeterministicCalculator
from app.services.integrity.checker import CrossStageConsistencyChecker
from app.services.integrity.options import OptionComparisonService
from app.services.integrity.evidence_quality import EvidenceQualityService
from app.services.integrity.uncertainty import UncertaintyCalibrationService

storage = SQLiteJobStorage(db_path="backend/aura_jobs.db")
job = storage.get_job("79b47ad0-79ff-4875-a47d-e7dd01c9a415")
assert job and job.response
analysis = job.response

calc = DeterministicCalculator()
calcs = calc.evaluate_all(analysis.decision_model, analysis.recommendation, {})

opt_svc = OptionComparisonService()
opts = opt_svc.compare_options(analysis.decision_model, analysis.evidence_package, analysis.recommendation)

ev_svc = EvidenceQualityService()
ev_qual = ev_svc.evaluate_evidence(analysis.evidence_package)
print("3. Evidence Quality:")
print("   sources:", len(ev_qual.sources), "dup:", ev_qual.duplicate_count)

print("4. Testing UncertaintyCalibrationService...")
unc_svc = UncertaintyCalibrationService()
scenarios = getattr(analysis, "scenarios", None) or getattr(analysis, "scenario_set", None)
unc = unc_svc.evaluate_uncertainty(analysis.decision_model, analysis.evidence_package, analysis.recommendation, scenarios, calcs)
print("   Uncertainty: is_calibrated:", unc.is_calibrated, "ranked_gaps:", len(unc.ranked_gaps))
for g in unc.ranked_gaps:
    print("    -", g.rank, g.decision_impact, g.description[:60])

print("5. Testing ConsistencyChecker...")
checker = CrossStageConsistencyChecker()
resilience = getattr(analysis, "resilience", None) or getattr(analysis, "resilience_report", None)
findings = checker.evaluate_all(
    decision_model=analysis.decision_model,
    evidence_package=analysis.evidence_package,
    reasoning_board=analysis.reasoning_board,
    recommendation=analysis.recommendation,
    scenario_set=scenarios,
    resilience_report=resilience,
    calculations=calcs,
    action_plan=None,
)
print("   Findings count:", len(findings))
for f in findings:
    print(f"    - [{f.severity.value}] {f.rule_code}: {f.title}")

print("\nALL 5 INTEGRITY ENGINES RAN SUCCESSFULLY!")

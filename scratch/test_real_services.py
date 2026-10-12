import sys, os
sys.path.insert(0, os.path.abspath("backend"))
import sqlite3
import json
import traceback

from app.services.jobs.manager import AnalysisJobManager
from app.services.jobs.storage import SQLiteJobStorage
from app.services.integrity.service import DecisionIntegrityService
from app.services.report.service import ReportService
from app.schemas.analysis import AnalysisResponse

storage = SQLiteJobStorage(db_path="backend/aura_jobs.db")
job = storage.get_job("79b47ad0-79ff-4875-a47d-e7dd01c9a415")
print("Job loaded:", bool(job))
if job:
    print("Job status:", job.status)
    print("Job response type:", type(job.response))
    if job.response:
        print("Analysis ID:", job.response.analysis_id)
        resp = job.response
        print("resp.decision_model type:", type(resp.decision_model))
        print("resp.recommendation type:", type(resp.recommendation))
        print("resp.scenarios type:", type(resp.scenarios))
        print("resp.resilience type:", type(resp.resilience))

manager = AnalysisJobManager(storage=storage)
integ_service = DecisionIntegrityService(manager=manager)
report_service = ReportService(manager=manager, integrity_service=integ_service)

print("\n--- Testing integrity_service.get_integrity_report ---")
try:
    report = integ_service.get_integrity_report("79b47ad0-79ff-4875-a47d-e7dd01c9a415")
    print("Integrity report success!", report.overall_status)
except Exception as e:
    print("Integrity service FAILED with error:", e)
    traceback.print_exc()

print("\n--- Testing by analysis_id b2abf510-aacb-44d7-8a11-7cc40806cca1 ---")
try:
    # Also check if get_job_result supports analysis_id vs job_id!
    res = manager.get_job_result("b2abf510-aacb-44d7-8a11-7cc40806cca1")
    print("manager.get_job_result by analysis_id succeeded!")
except Exception as e:
    print("manager.get_job_result by analysis_id failed:", e)

print("\n--- Testing report_service.get_shared_report ---")
try:
    s_report = report_service.get_shared_report("79b47ad0-79ff-4875-a47d-e7dd01c9a415")
    print("Shared report success!", s_report.overview.title)
except Exception as e:
    print("Report service FAILED with error:", e)
    traceback.print_exc()

import sqlite3
import json

conn = sqlite3.connect("backend/aura_jobs.db")
cur = conn.cursor()
cur.execute("SELECT job_id, status, stage, response_json FROM analysis_jobs WHERE job_id = ?", ("79b47ad0-79ff-4875-a47d-e7dd01c9a415",))
row = cur.fetchone()
if row:
    job_id, status, stage, resp_json = row
    print("Found job:", job_id)
    print("Status:", status)
    print("Stage:", stage)
    if resp_json:
        data = json.loads(resp_json)
        print("Analysis ID in response:", data.get("analysis_id") or data.get("id"))
        print("Keys in response:", list(data.keys()))
        print("Decision Model keys:", list(data.get("decision_model", {}).keys()) if "decision_model" in data else "None")
        if "decision_model" in data and "constraints" in data["decision_model"]:
            print("Constraints sample:", data["decision_model"]["constraints"][:2])
    else:
        print("No response_json!")
else:
    print("Job not found in backend/aura_jobs.db!")

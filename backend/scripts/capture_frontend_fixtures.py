"""Capture real API responses as frontend test fixtures.

Start a backend on a throwaway database, then:

    cd backend && uv run python scripts/capture_frontend_fixtures.py http://localhost:8765

Writes frontend/src/__tests__/fixtures/{api,ids}.json. Re-run it when an API response shape changes; the
frontend tests that use these fixtures then fail if the UI no longer matches the contract.
"""

import json
import re
import sys
from pathlib import Path

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765").rstrip("/")
out = Path(__file__).resolve().parents[2] / "frontend" / "src" / "__tests__" / "fixtures"
out.mkdir(parents=True, exist_ok=True)

c = httpx.Client(base_url=base + "/api", headers={"Origin": "http://localhost:5173"}, timeout=60)
c.post("/demo/workspace").raise_for_status()
family = c.get("/family").json()
mother = next(m for m in family["members"] if m["relation"] == "mother")
data = {
    "me": c.get("/auth/me").json(),
    "dashboard": c.get("/dashboard").json(),
    "loan_recommend": c.post("/loans/recommend", json={"purpose": "personal", "amount": 300000, "tenure_months": 36}).json(),
    "emergency": c.post("/insurance/emergency", json={"member_key": mother["id"], "event": "hospitalisation"}).json(),
    "insurance_events": c.get("/insurance/events").json(),
    "family": family,
    "reminders": c.get("/reminders").json(),
    "documents": c.get("/documents").json(),
    "cards": c.get("/cards").json(),
}
text = re.sub(r"sample-[0-9a-f]{8}@", "sample-fixture@", json.dumps(data, indent=1, ensure_ascii=False))
(out / "api.json").write_text(text)
(out / "ids.json").write_text(json.dumps({"mother": mother["id"], "emi": c.get("/emis").json()["emis"][0]["id"]}))
print("wrote", out)

"""
Procore connector.

Two clients share one interface:

  MockProcoreClient  reads the JSON fixtures in mock/procore/ (built by mock/build_fixtures.py)
  LiveProcoreClient  calls the Procore REST API (rest/v1.0). Untested against a real tenant;
                     the endpoint paths and field names follow Procore's public docs and the
                     normalizer below expects the same shapes the fixtures use.

Both return a ProjectSnapshot. Nothing downstream knows which one produced it.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from .model import (BudgetLine, ChangeOrder, DailyLog, Manpower, Milestone, Project,
                    ProjectSnapshot, RFI, Submittal)


# --------------------------------------------------------------- helpers ---
def _d(value: Any) -> Optional[date]:
    """Parse a Procore date or datetime string into a date."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _bic(raw: Any) -> str:
    if isinstance(raw, list) and raw:
        return raw[0].get("name", "")
    if isinstance(raw, dict):
        return raw.get("name", "")
    return str(raw or "")


# ------------------------------------------------------------ normalizer ---
def normalize(raw: dict[str, Any], period_start: date, period_end: date) -> ProjectSnapshot:
    """Turn a dict of raw Procore payloads into a ProjectSnapshot."""
    p = raw["project"]
    cf = p.get("custom_fields", {})
    project = Project(
        id=p["id"], name=p["name"], number=p.get("project_number", ""),
        address=", ".join(x for x in [p.get("address"), p.get("city"), p.get("state_code")] if x),
        description=p.get("description", ""),
        start_date=_d(p["start_date"]), completion_date=_d(p["completion_date"]),
        contract_value=float(p.get("total_value") or 0),
        owner=(p.get("owner") or {}).get("name", ""),
        owners_rep=cf.get("owners_rep", ""), lender=cf.get("lender", ""),
        gc_name=cf.get("gc_name", ""), project_executive=cf.get("project_executive", ""),
        project_manager=cf.get("project_manager", ""), superintendent=cf.get("superintendent", ""),
        rfi_window_bdays=int(cf.get("rfi_response_window_business_days", 10)),
        submittal_window_bdays=int(cf.get("submittal_review_window_business_days", 14)),
    )

    rfis = [RFI(
        ref=f"RFI-{r['number']:03d}", number=r["number"], subject=r["subject"], status=r["status"],
        created=_d(r["created_at"]), due=_d(r.get("due_date")), closed=_d(r.get("closed_at")),
        ball_in_court=_bic(r.get("ball_in_court")),
        spec_section=(r.get("specification_section") or {}).get("number", ""),
        question=(r.get("questions") or [{}])[0].get("body", ""),
        answer=(r.get("answers") or [{}])[0].get("body") if r.get("answers") else None,
        cost_impact=(r.get("cost_impact") or {}).get("status") == "yes",
        schedule_impact=(r.get("schedule_impact") or {}).get("status") == "yes",
        link=r.get("link", ""),
    ) for r in raw["rfis"]]

    submittals = [Submittal(
        ref=f"SUB-{s['number']}" + (f".R{s['revision']}" if s.get("revision") else ""),
        number=str(s["number"]), revision=int(s.get("revision") or 0), title=s["title"],
        spec_section=(s.get("specification_section") or {}).get("number", ""), status=s["status"],
        received=_d(s["received_date"]), due=_d(s.get("due_date")), returned=_d(s.get("returned_date")),
        ball_in_court=_bic(s.get("ball_in_court")),
        schedule_critical=bool((s.get("custom_fields") or {}).get("schedule_critical")),
        note=(s.get("custom_fields") or {}).get("note") or "", link=s.get("link", ""),
    ) for s in raw["submittals"]]

    change_orders = [ChangeOrder(
        ref=c["number"], number=c["number"], title=c["title"], status=c["status"],
        amount=c.get("amount"), created=_d(c["created_at"]),
        submitted_to_owner=_d(c.get("submitted_to_owner_at")), approved=_d(c.get("approved_at")),
        executed_number=c.get("executed_change_order"), schedule_days=c.get("schedule_days"),
        description=c.get("description", ""),
    ) for c in raw["change_orders"]]

    budget = [BudgetLine(
        ref=f"SOV-{b['cost_code']['full_code']}", code=b["cost_code"]["full_code"],
        description=b["cost_code"]["name"], original=float(b["original_budget_amount"]),
        approved_changes=float(b.get("approved_change_orders") or 0), revised=float(b["revised_budget"]),
        committed=float(b.get("committed_costs") or 0), cost_to_date=float(b.get("job_to_date_costs") or 0),
        billed_to_date=float(b.get("billed_to_date") or 0), percent_complete=float(b.get("percent_complete") or 0),
    ) for b in raw["budget"]]

    milestones = [Milestone(
        ref=f"MS-{m['id']}", name=m["name"], baseline=_d(m["baseline"]), current=_d(m["current"]),
        actual=_d(m.get("actual")),
    ) for m in raw["milestones"]]

    logs = []
    for lg in raw["daily_logs"]:
        day = _d(lg["date"])
        if not (period_start <= day <= period_end):
            continue
        w = (lg.get("weather_logs") or [{}])[0]
        logs.append(DailyLog(
            ref=f"LOG-{day.isoformat()}", day=day, conditions=w.get("conditions", ""),
            temp_high_f=int(w.get("temperature_high_f") or 0), weather_delay_hours=float(w.get("delay_hours") or 0),
            weather_note=w.get("notes", ""),
            manpower=[Manpower(m["company"], m.get("trade", ""), int(m["workers"]), int(m.get("hours") or 0))
                      for m in lg.get("manpower_logs", [])],
            work=" ".join(x.get("description", "") for x in lg.get("work_logs", [])),
            safety=[x.get("description", "") for x in lg.get("safety_violation_logs", [])],
            link=lg.get("link", ""),
        ))

    return ProjectSnapshot(project=project, period_start=period_start, period_end=period_end,
                           rfis=rfis, submittals=submittals, change_orders=change_orders,
                           budget=budget, milestones=milestones, daily_logs=logs)


# ------------------------------------------------------------ mock client ---
class MockProcoreClient:
    def __init__(self, fixtures_dir: Path):
        self.dir = Path(fixtures_dir)

    def _load(self, name: str):
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def snapshot(self, project_id: int, period_start: date, period_end: date) -> ProjectSnapshot:
        raw = {
            "project": self._load("project.json"),
            "rfis": self._load("rfis.json"),
            "submittals": self._load("submittals.json"),
            "change_orders": self._load("change_orders.json"),
            "budget": self._load("budget.json"),
            "milestones": self._load("schedule_milestones.json"),
            "daily_logs": self._load("daily_logs.json"),
        }
        assert raw["project"]["id"] == project_id, "fixture project id mismatch"
        return normalize(raw, period_start, period_end)


# ------------------------------------------------------------ live client ---
class LiveProcoreClient:
    """
    Minimal read-only client for Procore's REST API. Requires an OAuth access token
    (customer-issued for a pilot) and the company id. Read scope only.

    Not yet run against a real tenant. Field names in the responses will differ in
    places from the fixtures (notably budget views and daily log sub-resources), so
    expect to adjust normalize() the first time this runs for real.
    """
    BASE = "https://api.procore.com/rest/v1.0"

    def __init__(self, access_token: str, company_id: int):
        self.token = access_token
        self.company_id = company_id

    def _get(self, path: str, **params) -> Any:
        url = f"{self.BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Procore-Company-Id": str(self.company_id),
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def snapshot(self, project_id: int, period_start: date, period_end: date) -> ProjectSnapshot:
        pid = project_id
        raw = {
            "project": self._get(f"/projects/{pid}"),
            "rfis": self._get(f"/projects/{pid}/rfis", per_page=250),
            "submittals": self._get(f"/projects/{pid}/submittals", per_page=250),
            "change_orders": self._get(f"/projects/{pid}/change_order_packages", per_page=250),
            "budget": self._get(f"/projects/{pid}/budget_line_items", per_page=500),
            "milestones": self._get(f"/projects/{pid}/schedule/milestones", per_page=250),
            "daily_logs": self._get(f"/projects/{pid}/daily_logs",
                                    start_date=period_start.isoformat(), end_date=period_end.isoformat()),
        }
        return normalize(raw, period_start, period_end)

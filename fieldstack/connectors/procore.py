"""
Procore connector (project management system of record).

Settings (fieldstack.toml):
  mode      = "mock" | "live"
  fixtures  = "mock/procore"          (mock)
  token     = "${PROCORE_TOKEN}"      (live; OAuth access token, read scope)
  company_id = 1234                   (live)

The live client follows Procore REST v1.0 paths. It has not been run against a real
tenant; expect to adjust field mapping in normalize() on first contact, especially
budget views and daily log sub-resources.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from ..model import (BudgetLine, ChangeOrder, DailyLog, Manpower, Milestone, Project, RFI, Submittal)
from . import Capability, Partial, register


def _d(value: Any) -> Optional[date]:
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


def normalize(raw: dict[str, Any], period_start: date, period_end: date, source: str) -> Partial:
    p = raw["project"]
    cf = p.get("custom_fields", {})
    project = Project(
        id=str(p["id"]), name=p["name"], number=p.get("project_number", ""),
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
        source=source,
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
        link=r.get("link", ""), source=source,
    ) for r in raw.get("rfis", [])]

    submittals = [Submittal(
        ref=f"SUB-{s['number']}" + (f".R{s['revision']}" if s.get("revision") else ""),
        number=str(s["number"]), revision=int(s.get("revision") or 0), title=s["title"],
        spec_section=(s.get("specification_section") or {}).get("number", ""), status=s["status"],
        received=_d(s["received_date"]), due=_d(s.get("due_date")), returned=_d(s.get("returned_date")),
        ball_in_court=_bic(s.get("ball_in_court")),
        schedule_critical=bool((s.get("custom_fields") or {}).get("schedule_critical")),
        note=(s.get("custom_fields") or {}).get("note") or "", link=s.get("link", ""), source=source,
    ) for s in raw.get("submittals", [])]

    change_orders = [ChangeOrder(
        ref=c["number"], number=c["number"], title=c["title"], status=c["status"],
        amount=c.get("amount"), created=_d(c["created_at"]),
        submitted_to_owner=_d(c.get("submitted_to_owner_at")), approved=_d(c.get("approved_at")),
        executed_number=c.get("executed_change_order"), schedule_days=c.get("schedule_days"),
        description=c.get("description", ""), link=c.get("link", ""), source=source,
    ) for c in raw.get("change_orders", [])]

    budget = [BudgetLine(
        ref=f"SOV-{b['cost_code']['full_code']}", code=b["cost_code"]["full_code"],
        description=b["cost_code"]["name"], original=float(b["original_budget_amount"]),
        approved_changes=float(b.get("approved_change_orders") or 0), revised=float(b["revised_budget"]),
        committed=float(b.get("committed_costs") or 0), cost_to_date=float(b.get("job_to_date_costs") or 0),
        billed_to_date=float(b.get("billed_to_date") or 0), percent_complete=float(b.get("percent_complete") or 0),
        source=source,
    ) for b in raw.get("budget", [])]

    milestones = [Milestone(
        ref=f"MS-{m['id']}", name=m["name"], baseline=_d(m["baseline"]), current=_d(m["current"]),
        actual=_d(m.get("actual")), source=source,
    ) for m in raw.get("milestones", [])]

    logs = []
    for lg in raw.get("daily_logs", []):
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
            link=lg.get("link", ""), source=source,
        ))

    return Partial(project=project, rfis=rfis, submittals=submittals, change_orders=change_orders,
                   budget=budget, milestones=milestones, daily_logs=logs)


@register("procore")
class ProcoreConnector:
    capabilities = frozenset({Capability.PROJECT, Capability.RFIS, Capability.SUBMITTALS, Capability.CHANGE_ORDERS,
                              Capability.BUDGET, Capability.MILESTONES, Capability.DAILY_LOGS})
    BASE = "https://api.procore.com/rest/v1.0"

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.mode = settings.get("mode", "mock")
        self.fixtures = Path(settings.get("fixtures", "mock/procore"))
        self.token = settings.get("token")
        self.company_id = settings.get("company_id")

    # ---- mock
    def _load(self, fname: str):
        return json.loads((self.fixtures / fname).read_text(encoding="utf-8"))

    def _fetch_mock(self, project_ref) -> dict:
        raw = {k: self._load(f) for k, f in [
            ("project", "project.json"), ("rfis", "rfis.json"), ("submittals", "submittals.json"),
            ("change_orders", "change_orders.json"), ("budget", "budget.json"),
            ("milestones", "schedule_milestones.json"), ("daily_logs", "daily_logs.json")]}
        if str(raw["project"]["id"]) != str(project_ref):
            raise ValueError(f"fixture project {raw['project']['id']} != requested {project_ref}")
        return raw

    # ---- live
    def _get(self, path: str, **params) -> Any:
        url = f"{self.BASE}{path}" + (("?" + urllib.parse.urlencode(params, doseq=True)) if params else "")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}", "Procore-Company-Id": str(self.company_id),
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_live(self, pid, ps: date, pe: date) -> dict:
        return {
            "project": self._get(f"/projects/{pid}"),
            "rfis": self._get(f"/projects/{pid}/rfis", per_page=250),
            "submittals": self._get(f"/projects/{pid}/submittals", per_page=250),
            "change_orders": self._get(f"/projects/{pid}/change_order_packages", per_page=250),
            "budget": self._get(f"/projects/{pid}/budget_line_items", per_page=500),
            "milestones": self._get(f"/projects/{pid}/schedule/milestones", per_page=250),
            "daily_logs": self._get(f"/projects/{pid}/daily_logs", start_date=ps.isoformat(), end_date=pe.isoformat()),
        }

    # ---- protocol
    def fetch(self, project_ref, period_start: date, period_end: date) -> Partial:
        raw = self._fetch_live(project_ref, period_start, period_end) if self.mode == "live" else self._fetch_mock(project_ref)
        return normalize(raw, period_start, period_end, self.name)

    def health(self) -> tuple[bool, str]:
        if self.mode == "live":
            if not (self.token and self.company_id):
                return False, "live mode needs token and company_id"
            return True, "live (untested against a real tenant)"
        ok = (self.fixtures / "project.json").exists()
        return ok, f"mock fixtures at {self.fixtures}" if ok else f"no fixtures at {self.fixtures}"

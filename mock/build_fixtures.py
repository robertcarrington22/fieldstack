"""
Builds a deterministic set of Procore-shaped JSON fixtures for one sample project.

Everything here is invented. The project, owner, lender, subcontractors, and people
are fictional. Field names follow Procore's REST API (v1.0) closely enough that the
normalizer in fieldstack/procore.py can be pointed at a real tenant later with
minimal changes.

Run:  python mock/build_fixtures.py
Out:  mock/procore/*.json
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "procore"
OUT.mkdir(parents=True, exist_ok=True)

PROJECT_ID = 2264101
PERIOD_START = date(2026, 8, 1)
PERIOD_END = date(2026, 8, 31)

rng = random.Random(20260904)


def iso(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%dT%H:%M:%SZ")
    return d.isoformat()


def dump(name: str, payload) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {name}")


# ---------------------------------------------------------------- project ---
project = {
    "id": PROJECT_ID,
    "name": "Bergen Street Apartments",
    "project_number": "26-014",
    "address": "1188 Bergen Street",
    "city": "Brooklyn",
    "state_code": "NY",
    "zip": "11216",
    "description": "9-story, 96-unit affordable housing building with ground-floor community facility and cellar.",
    "start_date": "2026-02-02",
    "completion_date": "2027-11-30",
    "total_value": 48500000.00,
    "project_stage": {"name": "Course of Construction"},
    "owner": {"name": "Bergen Street Housing LP"},
    "custom_fields": {
        "owners_rep": "Meridian Development Advisory",
        "lender": "Atlantic Community Lending Fund",
        "rfi_response_window_business_days": 10,
        "submittal_review_window_business_days": 14,
        "gc_name": "Sample Builders LLC",
        "project_executive": "D. Okafor",
        "project_manager": "L. Reyes",
        "superintendent": "M. Kowalski",
    },
}
dump("project.json", project)

# ------------------------------------------------------------------- rfis ---
def rfi(num, subject, created, due, status, bic, spec, question, cost=False, sched=False, closed=None, answer=None):
    return {
        "id": 700000 + num,
        "number": num,
        "subject": subject,
        "status": status,
        "created_at": iso(datetime.combine(created, datetime.min.time())),
        "due_date": iso(due),
        "closed_at": iso(datetime.combine(closed, datetime.min.time())) if closed else None,
        "ball_in_court": [{"name": bic}],
        "specification_section": {"number": spec[0], "description": spec[1]},
        "cost_impact": {"status": "yes" if cost else "no"},
        "schedule_impact": {"status": "yes" if sched else "no"},
        "questions": [{"body": question}],
        "answers": [{"body": answer}] if answer else [],
        "link": f"https://app.procore.com/{PROJECT_ID}/project/rfi/show/{700000 + num}",
    }

rfis = [
    rfi(38, "Rebar cover at cellar slab-on-grade edge", date(2026, 7, 14), date(2026, 7, 28), "closed",
        "Structural Engineer of Record", ("03 20 00", "Concrete Reinforcing"),
        "Confirm 3 in. cover at exterior slab edge per S-101 note 7.", closed=date(2026, 8, 3),
        answer="3 in. confirmed. See SK-S-014."),
    rfi(39, "Location of cellar sump pump discharge", date(2026, 7, 20), date(2026, 8, 3), "closed",
        "MEP Engineer", ("22 14 29", "Sump Pumps"),
        "P-001 shows discharge to storm; DEP letter requires sanitary. Clarify.", closed=date(2026, 8, 6),
        answer="Route to sanitary. Revised P-001 issued 08/06."),
    rfi(40, "Level 2 corridor ceiling height at duct crossing", date(2026, 7, 27), date(2026, 8, 10), "closed",
        "Architect", ("09 51 13", "Acoustical Panel Ceilings"),
        "Duct at grid C/4 leaves 7 ft 8 in. clear; drawings show 8 ft 0 in.", closed=date(2026, 8, 12),
        answer="7 ft 8 in. accepted at crossing only."),
    rfi(41, "Conflict between S-201 and A-401 at slab edge, Level 5", date(2026, 8, 5), date(2026, 8, 19), "open",
        "Structural Engineer of Record", ("03 30 00", "Cast-in-Place Concrete"),
        "S-201 shows slab edge at 1 ft 6 in. from grid A; A-401 wall section shows 1 ft 2 in. Level 5 formwork "
        "is scheduled to start 09/08. Which governs?", cost=True, sched=True),
    rfi(42, "Fireproofing thickness at transfer beam TB-3", date(2026, 8, 6), date(2026, 8, 20), "closed",
        "Architect", ("07 81 00", "Applied Fireproofing"),
        "Confirm 2-hr rating and required thickness for W24x131 at TB-3.", closed=date(2026, 8, 18),
        answer="2-hr. 1-3/8 in. per UL N706."),
    rfi(43, "Trash chute discharge door swing", date(2026, 8, 10), date(2026, 8, 24), "closed",
        "Architect", ("11 82 26", "Facility Waste Compactors"),
        "Door swing conflicts with compactor clearance in cellar room C-07.", closed=date(2026, 8, 21),
        answer="Reverse swing. Revised A-110 attached."),
    rfi(44, "Elevator pit waterproofing detail", date(2026, 8, 12), date(2026, 8, 26), "open",
        "Architect", ("07 13 00", "Sheet Waterproofing"),
        "A-501 detail 6 references a waterproofing membrane not in the spec. Provide product or detail."),
    rfi(45, "Backer rod at window sill flashing", date(2026, 8, 13), date(2026, 8, 27), "closed",
        "Architect", ("07 92 00", "Joint Sealants"),
        "Confirm closed-cell backer rod at sill per detail 3/A-502.", closed=date(2026, 8, 25),
        answer="Confirmed."),
    rfi(46, "Gas meter room ventilation", date(2026, 8, 17), date(2026, 8, 31), "closed",
        "MEP Engineer", ("23 05 00", "Common Work Results for HVAC"),
        "Utility requires 1 sq in. per 1,000 BTU; M-101 shows louver undersized.", closed=date(2026, 8, 28),
        answer="Louver upsized to 24x24. SK-M-009."),
    rfi(47, "Transformer vault louver size", date(2026, 8, 19), date(2026, 9, 2), "open",
        "MEP Engineer", ("26 12 19", "Pad-Mounted Transformers"),
        "Utility standard calls for 36x36 louver; E-201 shows 30x30. Confirm.", cost=True),
    rfi(48, "Handrail bracket spacing at Stair 1", date(2026, 8, 24), date(2026, 9, 8), "closed",
        "Architect", ("05 52 13", "Pipe and Tube Railings"),
        "Confirm 4 ft 0 in. max bracket spacing.", closed=date(2026, 8, 31), answer="4 ft 0 in. max confirmed."),
    rfi(49, "Unit kitchen exhaust routing, floors 3 and 4", date(2026, 8, 26), date(2026, 9, 10), "open",
        "MEP Engineer", ("23 34 00", "HVAC Fans"),
        "Exhaust duct on M-302 crosses the corridor rated wall without a damper. Confirm routing or add damper.",
        cost=True, sched=True),
    rfi(50, "Stair 2 handrail extension at Level 1", date(2026, 8, 28), date(2026, 9, 11), "open",
        "Architect", ("05 52 13", "Pipe and Tube Railings"),
        "12 in. extension at bottom run conflicts with door swing. Confirm."),
]
dump("rfis.json", rfis)

# ------------------------------------------------------------- submittals ---
def sub(num, rev, title, spec, status, submitted, due, bic, received=None, returned=None, note=None, critical=False):
    return {
        "id": 810000 + num * 10 + rev,
        "number": str(num),
        "revision": rev,
        "title": title,
        "specification_section": {"number": spec[0], "description": spec[1]},
        "status": status,
        "submit_by": None,
        "received_date": iso(submitted),
        "due_date": iso(due),
        "returned_date": iso(returned) if returned else None,
        "ball_in_court": [{"name": bic}],
        "custom_fields": {"schedule_critical": critical, "note": note},
        "link": f"https://app.procore.com/{PROJECT_ID}/project/submittals/{810000 + num * 10 + rev}",
    }

submittals = [
    sub(118, 2, "Curtain Wall Shop Drawings, North and East Elevations", ("08 44 13", "Glazed Aluminum Curtain Walls"),
        "In Review", date(2026, 7, 21), date(2026, 8, 10), "Architect", critical=True,
        note="Rev 1 returned Revise and Resubmit 07/10. Rev 2 in review 45 days. Fabrication lead time 14 weeks."),
    sub(121, 0, "Elevator Equipment and Machine Room Layout", ("14 21 00", "Electric Traction Elevators"),
        "Approved as Noted", date(2026, 7, 28), date(2026, 8, 17), "GC", returned=date(2026, 8, 14)),
    sub(123, 1, "Concrete Mix Design, 6000 psi Columns Levels 5-9", ("03 30 00", "Cast-in-Place Concrete"),
        "Approved", date(2026, 8, 3), date(2026, 8, 21), "GC", returned=date(2026, 8, 11)),
    sub(125, 0, "Rooftop Units RTU-1 and RTU-2", ("23 74 13", "Packaged Rooftop Air-Conditioning Units"),
        "Revise and Resubmit", date(2026, 7, 30), date(2026, 8, 19), "Subcontractor: Harbor Mechanical",
        returned=date(2026, 8, 20), note="Returned R&R 08/20; resubmittal due 09/03, not yet received."),
    sub(126, 0, "Fireproofing Product Data", ("07 81 00", "Applied Fireproofing"),
        "Approved", date(2026, 8, 6), date(2026, 8, 25), "GC", returned=date(2026, 8, 19)),
    sub(127, 1, "Window Package, Typical Unit Windows", ("08 53 13", "Vinyl Windows"),
        "In Review", date(2026, 8, 11), date(2026, 8, 31), "Architect", critical=True,
        note="Rev 0 returned R&R 08/04 for U-value. Rev 1 in review."),
    sub(128, 0, "Unit Entry Doors and Frames", ("08 11 13", "Hollow Metal Doors and Frames"),
        "In Review", date(2026, 8, 18), date(2026, 9, 8), "Architect"),
    sub(130, 0, "Fire Alarm System Shop Drawings", ("28 31 00", "Fire Detection and Alarm"),
        "Submitted", date(2026, 8, 31), date(2026, 9, 21), "MEP Engineer"),
]
dump("submittals.json", submittals)

# ---------------------------------------------------------- change orders ---
change_orders = [
    {
        "id": 910005, "number": "PCO-005", "title": "Unforeseen rock excavation at cellar, grids A-C",
        "status": "approved", "amount": 312450.00, "created_at": "2026-06-22T00:00:00Z",
        "submitted_to_owner_at": "2026-06-30T00:00:00Z", "approved_at": "2026-07-15T00:00:00Z",
        "executed_change_order": "CO-002", "schedule_days": 6,
        "description": "Rock encountered 2 ft above boring log elevation; hoe-ram and haul-off.",
    },
    {
        "id": 910007, "number": "PCO-007", "title": "Owner-requested lobby finish upgrade",
        "status": "pending_owner_signature", "amount": 186200.00, "created_at": "2026-07-29T00:00:00Z",
        "submitted_to_owner_at": "2026-08-08T00:00:00Z", "approved_at": None,
        "executed_change_order": None, "schedule_days": 0,
        "description": "Terrazzo in lieu of porcelain tile; wood slat ceiling; upgraded lighting per owner ASI-04.",
    },
    {
        "id": 910008, "number": "PCO-008", "title": "Utility conflict at Third Avenue water service",
        "status": "pending_owner_review", "amount": 94800.00, "created_at": "2026-08-14T00:00:00Z",
        "submitted_to_owner_at": "2026-08-21T00:00:00Z", "approved_at": None,
        "executed_change_order": None, "schedule_days": 4,
        "description": "Existing 12 in. main not shown on survey; reroute service tap 40 ft east.",
    },
    {
        "id": 910009, "number": "PCO-009", "title": "Kitchen exhaust rerouting, floors 3 and 4 (RFI-049)",
        "status": "pricing", "amount": None, "created_at": "2026-08-27T00:00:00Z",
        "submitted_to_owner_at": None, "approved_at": None,
        "executed_change_order": None, "schedule_days": None,
        "description": "Pending RFI-049 response. Rough order of magnitude $40,000 to $65,000.",
    },
]
dump("change_orders.json", change_orders)

# ------------------------------------------------------------------ budget ---
# Schedule-of-values style lines. Dollars are invented but internally consistent.
budget_lines = [
    # code, description, original, approved_changes, committed, cost_to_date, billed_to_date, pct_complete
    ("01-000", "General Conditions", 3_880_000, 0, 3_880_000, 1_268_000, 1_240_000, 0.33),
    ("02-000", "Sitework, Excavation, Foundations", 4_650_000, 312_450, 4_962_450, 4_815_000, 4_760_000, 0.97),
    ("03-000", "Cast-in-Place Concrete", 9_700_000, 0, 9_640_000, 5_780_000, 5_640_000, 0.60),
    ("04-000", "Masonry", 2_150_000, 0, 2_120_000, 210_000, 190_000, 0.10),
    ("05-000", "Structural and Misc. Steel", 1_420_000, 0, 1_395_000, 640_000, 620_000, 0.45),
    ("07-000", "Roofing and Waterproofing", 1_960_000, 0, 1_910_000, 240_000, 230_000, 0.12),
    ("08-000", "Windows and Curtain Wall", 4_120_000, 0, 4_060_000, 380_000, 360_000, 0.09),
    ("09-000", "Finishes", 6_380_000, 0, 5_910_000, 0, 0, 0.00),
    ("14-000", "Elevators", 1_480_000, 0, 1_455_000, 220_000, 210_000, 0.15),
    ("21-000", "Fire Protection", 940_000, 0, 925_000, 95_000, 90_000, 0.10),
    ("22-000", "Plumbing", 3_260_000, 0, 3_190_000, 740_000, 710_000, 0.23),
    ("23-000", "HVAC", 3_640_000, 0, 3_590_000, 610_000, 590_000, 0.17),
    ("26-000", "Electrical", 3_540_000, 0, 3_480_000, 640_000, 620_000, 0.18),
    ("99-000", "GC Fee and Insurance", 1_380_000, 0, 1_380_000, 400_000, 400_000, 0.29),
]
budget = []
for code, desc, orig, chg, committed, jtd, billed, pct in budget_lines:
    budget.append({
        "id": int("11" + code.replace("-", "")),
        "cost_code": {"full_code": code, "name": desc},
        "original_budget_amount": orig,
        "approved_change_orders": chg,
        "revised_budget": orig + chg,
        "committed_costs": committed,
        "job_to_date_costs": jtd,
        "billed_to_date": billed,
        "percent_complete": pct,
        "forecast_to_complete": None,
    })
dump("budget.json", budget)

# -------------------------------------------------------------- schedule ---
milestones = [
    {"id": 1, "name": "Notice to Proceed", "baseline": "2026-02-02", "current": "2026-02-02", "actual": "2026-02-02"},
    {"id": 2, "name": "Foundations Complete", "baseline": "2026-05-29", "current": "2026-06-05", "actual": "2026-06-05"},
    {"id": 3, "name": "Superstructure Level 5 Formwork Start", "baseline": "2026-09-01", "current": "2026-09-08", "actual": None},
    {"id": 4, "name": "Superstructure Topping Out", "baseline": "2026-10-16", "current": "2026-10-30", "actual": None},
    {"id": 5, "name": "MEP Rough-In Complete, Floors 1-4", "baseline": "2026-11-13", "current": "2026-11-13", "actual": None},
    {"id": 6, "name": "Building Watertight", "baseline": "2027-01-29", "current": "2027-02-19", "actual": None},
    {"id": 7, "name": "Elevators Operational", "baseline": "2027-07-30", "current": "2027-07-30", "actual": None},
    {"id": 8, "name": "Substantial Completion", "baseline": "2027-11-30", "current": "2027-12-14", "actual": None},
]
dump("schedule_milestones.json", milestones)

# ------------------------------------------------------------ daily logs ---
crews = [
    ("Sample Builders LLC", "GC supervision and labor", 6, 8),
    ("Kings County Concrete Corp.", "Concrete superstructure", 26, 38),
    ("Ironline Rebar Inc.", "Reinforcing steel", 12, 18),
    ("Harbor Mechanical", "HVAC rough-in", 4, 9),
    ("Brightwire Electric", "Electrical rough-in", 5, 10),
    ("Five Boro Plumbing", "Plumbing rough-in", 5, 9),
    ("Atlas Hoist and Crane", "Tower crane and hoist", 2, 3),
]
work_notes = {
    date(2026, 8, 3): "Level 4 slab pour, 410 CY. Pour complete 14:20. Cylinders taken.",
    date(2026, 8, 4): "Level 4 shoring and reshoring. Column rebar Level 5 started.",
    date(2026, 8, 5): "Column pour Level 5 east half. RFI-041 issued on slab edge conflict.",
    date(2026, 8, 6): "Column pour Level 5 west half. Cellar sump discharge rerouted per RFI-039.",
    date(2026, 8, 7): "Level 5 deck forming started. Plumbing rough-in Level 2 continues.",
    date(2026, 8, 10): "Level 5 deck forming. HVAC rough-in Level 1 started.",
    date(2026, 8, 11): "Level 5 deck forming and rebar. Electrical rough-in Level 2.",
    date(2026, 8, 12): "Level 5 rebar. Formwork at grid A slab edge held pending RFI-041.",
    date(2026, 8, 13): "Level 5 rebar and embeds. MEP sleeve coordination Level 5.",
    date(2026, 8, 14): "Level 5 slab pour delayed to 08/17 pending RFI-041 at grid A edge.",
    date(2026, 8, 17): "Level 5 slab pour, partial, 340 CY excluding grid A edge strip (RFI-041).",
    date(2026, 8, 18): "Level 5 reshoring. Column rebar Level 6 started.",
    date(2026, 8, 19): "Column pour Level 6 east half. Transformer vault louver RFI-047 issued.",
    date(2026, 8, 20): "Column pour Level 6 west half. RTU submittal returned R&R.",
    date(2026, 8, 21): "Level 6 deck forming started. PCO-008 submitted to owner.",
    date(2026, 8, 24): "Level 6 deck forming. Elevator rail brackets Level 1-2.",
    date(2026, 8, 25): "Level 6 deck forming and rebar. Plumbing rough-in Level 3 started.",
    date(2026, 8, 26): "Level 6 rebar. Kitchen exhaust conflict found at rated corridor wall; RFI-049 issued.",
    date(2026, 8, 27): "Level 6 rebar and embeds. Fireproofing at TB-3 complete.",
    date(2026, 8, 28): "Level 6 slab pour, 405 CY, complete 15:05. Grid A strip Level 5 still open.",
    date(2026, 8, 31): "Level 6 reshoring. Column rebar Level 7 started. Fire alarm shop drawings submitted.",
}
weather_events = {
    date(2026, 8, 6): ("Thunderstorms", 2.0, "Pour finished; deck forming stopped 13:00 for lightning."),
    date(2026, 8, 13): ("Heavy rain", 4.0, "Rebar work stopped 11:00. Half day lost."),
    date(2026, 8, 25): ("Heat advisory, 97F", 1.5, "Extended breaks per heat plan; no lost pours."),
}
safety_events = {
    date(2026, 8, 11): "Near miss: rebar bundle shifted during hoist. No injury. Rigging retrained 08/12.",
    date(2026, 8, 20): "First aid: laceration to hand, Ironline Rebar. Returned to work same day.",
}

daily_logs = []
d = PERIOD_START
while d <= PERIOD_END:
    if d.weekday() < 5:
        manpower = []
        for company, trade, lo, hi in crews:
            workers = rng.randint(lo, hi)
            if company == "Harbor Mechanical" and d < date(2026, 8, 10):
                workers = 0
            manpower.append({"company": company, "trade": trade, "workers": workers, "hours": workers * 8})
        weather = weather_events.get(d)
        daily_logs.append({
            "date": iso(d),
            "weather_logs": [{
                "conditions": weather[0] if weather else rng.choice(["Clear", "Partly cloudy", "Sunny", "Overcast"]),
                "temperature_high_f": rng.randint(78, 92) if not weather else (97 if "Heat" in weather[0] else 76),
                "delay_hours": weather[1] if weather else 0.0,
                "notes": weather[2] if weather else "",
            }],
            "manpower_logs": manpower,
            "work_logs": [{"description": work_notes.get(d, "Superstructure and MEP rough-in continue per plan.")}],
            "safety_violation_logs": [{"description": safety_events[d]}] if d in safety_events else [],
            "delivery_logs": [],
            "link": f"https://app.procore.com/{PROJECT_ID}/project/daily_log/list?date={iso(d)}",
        })
    d += timedelta(days=1)
dump("daily_logs.json", daily_logs)

# ------------------------------------------------------------ prior style ---
(OUT.parent / "prior_owner_report_excerpt.md").write_text(
    """# Bergen Street Apartments, Monthly Owner Report, July 2026 (excerpt)

Prepared by Sample Builders LLC for Bergen Street Housing LP, Meridian Development Advisory, and Atlantic Community Lending Fund.

## Executive Summary
Superstructure concrete reached Level 4 this month, one week behind baseline due to the rock condition at the cellar (CO-002). MEP rough-in has started on Level 1. The project remains within budget; one owner-requested change (PCO-007) is in pricing. We are tracking one submittal, the curtain wall shop drawings, as critical to the watertight milestone.

## Progress
Work this period focused on ... [style note: short declarative sentences, no adjectives, dollar figures to the nearest hundred, dates as MM/DD]
""",
    encoding="utf-8",
)
print("wrote prior_owner_report_excerpt.md")

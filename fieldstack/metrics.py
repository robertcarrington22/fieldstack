"""
Deterministic facts for the Owner Report.

Everything a reader could dispute is computed here in plain Python, never by the
model: aging, overdue counts, dollars at stake, percent complete, headcount, lost
hours. The model only writes prose around these numbers and must cite the refs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Optional

from .model import ProjectSnapshot


def business_days_between(start: date, end: date) -> int:
    """Whole business days from start (exclusive) to end (inclusive). Negative if end < start."""
    if end < start:
        return -business_days_between(end, start)
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


@dataclass
class OpenItem:
    ref: str
    kind: str                 # rfi | submittal | change_order
    title: str
    ball_in_court: str
    opened: date
    due: Optional[date]
    days_overdue_bdays: int   # business days past due (0 if not yet due)
    amount: Optional[float] = None
    schedule_impact: bool = False
    cost_impact: bool = False
    note: str = ""
    link: str = ""


@dataclass
class ReportFacts:
    project_name: str
    period_label: str
    as_of: date
    contract_value: float
    revised_contract: float
    approved_changes: float
    pending_changes: float
    cost_to_date: float
    billed_to_date: float
    committed: float
    percent_complete_cost: float       # cost_to_date / revised contract
    percent_complete_sov: float        # dollar-weighted SOV percent complete
    projected_cost: float              # committed + unbought scope at budget
    projected_variance: float          # revised budget - projected cost (positive = under)
    schedule_variance_days: int        # substantial completion current - baseline
    working_days: int
    avg_headcount: float
    peak_headcount: int
    weather_delay_hours: float
    weather_days: list[str]
    safety_events: list[dict]
    rfis_opened: int
    rfis_closed: int
    rfis_open_total: int
    rfi_avg_response_bdays: Optional[float]
    rfis_overdue: list[OpenItem]
    submittals_overdue: list[OpenItem]
    submittals_critical_open: list[OpenItem]
    change_orders_pending: list[OpenItem]
    milestones: list[dict]
    budget_lines: list[dict]
    work_log: list[dict]
    attention: list[str] = field(default_factory=list)   # short, cited, ordered by severity

    def to_dict(self) -> dict:
        return asdict(self)


def compute(snap: ProjectSnapshot, as_of: date) -> ReportFacts:
    p = snap.project
    ps, pe = snap.period_start, snap.period_end

    # ---- RFIs
    opened = [r for r in snap.rfis if ps <= r.created <= pe]
    closed = [r for r in snap.rfis if r.closed and ps <= r.closed <= pe]
    open_now = [r for r in snap.rfis if r.status == "open"]
    resp = [business_days_between(r.created, r.closed) for r in closed]
    avg_resp = round(sum(resp) / len(resp), 1) if resp else None
    rfis_overdue = []
    for r in open_now:
        due = r.due or (r.created + timedelta(days=14))
        over = business_days_between(due, as_of)
        if over > 0:
            rfis_overdue.append(OpenItem(
                ref=r.ref, kind="rfi", title=r.subject, ball_in_court=r.ball_in_court, opened=r.created,
                due=due, days_overdue_bdays=over, schedule_impact=r.schedule_impact, cost_impact=r.cost_impact,
                note=r.question, link=r.link))
    rfis_overdue.sort(key=lambda x: (-x.schedule_impact, -x.days_overdue_bdays))

    # ---- Submittals
    sub_overdue, sub_critical = [], []
    for s in snap.submittals:
        is_open = s.status in ("Submitted", "In Review", "Revise and Resubmit")
        if not is_open:
            continue
        due = s.due or (s.received + timedelta(days=21))
        over = business_days_between(due, as_of)
        item = OpenItem(ref=s.ref, kind="submittal", title=s.title, ball_in_court=s.ball_in_court,
                        opened=s.received, due=due, days_overdue_bdays=max(over, 0),
                        schedule_impact=s.schedule_critical, note=s.note, link=s.link)
        if over > 0:
            sub_overdue.append(item)
        if s.schedule_critical:
            sub_critical.append(item)
    sub_overdue.sort(key=lambda x: (-x.schedule_impact, -x.days_overdue_bdays))

    # ---- Change orders
    approved_changes = sum(c.amount or 0 for c in snap.change_orders if c.status == "approved")
    pending_items, pending_total = [], 0.0
    for c in snap.change_orders:
        if c.status in ("pending_owner_review", "pending_owner_signature", "pricing"):
            pending_total += c.amount or 0
            since = c.submitted_to_owner or c.created
            pending_items.append(OpenItem(
                ref=c.ref, kind="change_order", title=c.title, ball_in_court="Owner" if c.submitted_to_owner else p.gc_name,
                opened=since, due=None, days_overdue_bdays=business_days_between(since, as_of),
                amount=c.amount, schedule_impact=bool(c.schedule_days), cost_impact=True,
                note=f"{c.status.replace('_', ' ')}. {c.description}"))
    pending_items.sort(key=lambda x: -(x.amount or 0))

    # ---- Budget
    revised_budget = sum(b.revised for b in snap.budget)
    committed = sum(b.committed for b in snap.budget)
    cost_to_date = sum(b.cost_to_date for b in snap.budget)
    billed = sum(b.billed_to_date for b in snap.budget)
    # projected cost: committed where bought out, budget where not yet committed
    projected = sum(max(b.committed, b.cost_to_date) if b.committed > 0 else b.revised for b in snap.budget)
    variance = revised_budget - projected
    pct_cost = cost_to_date / revised_budget if revised_budget else 0
    pct_sov = sum(b.revised * b.percent_complete for b in snap.budget) / revised_budget if revised_budget else 0

    # ---- Schedule
    sc = next((m for m in snap.milestones if "Substantial" in m.name), None)
    sched_var = (sc.current - sc.baseline).days if sc else 0
    milestones = [{
        "ref": m.ref, "name": m.name, "baseline": m.baseline.isoformat(), "current": m.current.isoformat(),
        "actual": m.actual.isoformat() if m.actual else None,
        "variance_days": (m.current - m.baseline).days,
        "status": "complete" if m.actual else ("slipping" if m.current > m.baseline else "on track"),
    } for m in snap.milestones]

    # ---- Field
    logs = snap.daily_logs
    counts = [l.headcount for l in logs]
    weather_days = [f"{l.ref}: {l.conditions}, {l.weather_delay_hours:g} h lost. {l.weather_note}".strip()
                    for l in logs if l.weather_delay_hours > 0]
    safety = [{"ref": l.ref, "date": l.day.isoformat(), "description": s} for l in logs for s in l.safety]
    work_log = [{"ref": l.ref, "date": l.day.isoformat(), "headcount": l.headcount, "work": l.work} for l in logs]

    facts = ReportFacts(
        project_name=p.name, period_label=ps.strftime("%B %Y"), as_of=as_of,
        contract_value=p.contract_value, revised_contract=p.contract_value + approved_changes,
        approved_changes=approved_changes, pending_changes=pending_total,
        cost_to_date=cost_to_date, billed_to_date=billed, committed=committed,
        percent_complete_cost=round(pct_cost, 4), percent_complete_sov=round(pct_sov, 4),
        projected_cost=projected, projected_variance=variance, schedule_variance_days=sched_var,
        working_days=len(logs), avg_headcount=round(sum(counts) / len(counts), 1) if counts else 0,
        peak_headcount=max(counts) if counts else 0,
        weather_delay_hours=sum(l.weather_delay_hours for l in logs), weather_days=weather_days,
        safety_events=safety, rfis_opened=len(opened), rfis_closed=len(closed), rfis_open_total=len(open_now),
        rfi_avg_response_bdays=avg_resp, rfis_overdue=rfis_overdue, submittals_overdue=sub_overdue,
        submittals_critical_open=sub_critical, change_orders_pending=pending_items,
        milestones=milestones,
        budget_lines=[asdict(b) for b in snap.budget], work_log=work_log,
    )

    # ---- Attention list: the five things a PX would want on page one, cited.
    att = []
    for r in rfis_overdue:
        if r.schedule_impact:
            att.append(f"{r.ref} is {r.days_overdue_bdays} business days past its response date with {r.ball_in_court} "
                       f"and carries schedule impact.")
    for s in sub_critical:
        if s.days_overdue_bdays > 0:
            att.append(f"{s.ref} ({s.title}) is schedule-critical and {s.days_overdue_bdays} business days past its "
                       f"review date with {s.ball_in_court}.")
    for c in pending_items:
        if c.amount and c.days_overdue_bdays >= 10:
            att.append(f"{c.ref} (${c.amount:,.0f}) has been with the owner {c.days_overdue_bdays} business days.")
    for m in milestones:
        if m["status"] == "slipping" and "Substantial" in m["name"]:
            att.append(f"{m['ref']} Substantial Completion forecast is {m['variance_days']} days behind baseline.")
    facts.attention = att[:6]
    return facts

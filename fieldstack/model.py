"""
Unified construction data model.

Every source (Procore, Autodesk Build, Sage 300 CRE via hh2, Viewpoint Vista, P6,
MS Project, a CSV export) is normalized into these dataclasses so metrics, modules,
and reports never touch a vendor shape.

Each record carries:
  ref      a stable citation id (RFI-041, SUB-118.R2, PCO-007, LOG-2026-08-14, MS-4, SOV-03-000)
  source   the connector name that produced it (provenance, shown in the report footer)
  link     a URL back to the source system when one exists
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any, Optional, get_args, get_origin, get_type_hints


@dataclass
class Project:
    id: str
    name: str
    number: str
    address: str
    description: str
    start_date: date
    completion_date: date
    contract_value: float
    owner: str
    owners_rep: str
    lender: str
    gc_name: str
    project_executive: str
    project_manager: str
    superintendent: str
    rfi_window_bdays: int = 10
    submittal_window_bdays: int = 14
    source: str = ""


@dataclass
class RFI:
    ref: str
    number: int
    subject: str
    status: str                    # open | closed
    created: date
    due: Optional[date]
    closed: Optional[date]
    ball_in_court: str
    spec_section: str
    question: str
    answer: Optional[str]
    cost_impact: bool
    schedule_impact: bool
    link: str = ""
    source: str = ""


@dataclass
class Submittal:
    ref: str
    number: str
    revision: int
    title: str
    spec_section: str
    status: str                    # Submitted | In Review | Approved | Approved as Noted | Revise and Resubmit
    received: date
    due: Optional[date]
    returned: Optional[date]
    ball_in_court: str
    schedule_critical: bool
    note: str
    link: str = ""
    source: str = ""


@dataclass
class ChangeOrder:
    ref: str
    number: str
    title: str
    status: str                    # pricing | pending_owner_review | pending_owner_signature | approved | rejected
    amount: Optional[float]
    created: date
    submitted_to_owner: Optional[date]
    approved: Optional[date]
    executed_number: Optional[str]
    schedule_days: Optional[int]
    description: str
    link: str = ""
    source: str = ""


@dataclass
class BudgetLine:
    ref: str
    code: str
    description: str
    original: float
    approved_changes: float
    revised: float
    committed: float
    cost_to_date: float
    billed_to_date: float
    percent_complete: float
    link: str = ""
    source: str = ""


@dataclass
class Milestone:
    ref: str
    name: str
    baseline: date
    current: date
    actual: Optional[date]
    link: str = ""
    source: str = ""


@dataclass
class Manpower:
    company: str
    trade: str
    workers: int
    hours: int


@dataclass
class DailyLog:
    ref: str
    day: date
    conditions: str
    temp_high_f: int
    weather_delay_hours: float
    weather_note: str
    manpower: list[Manpower]
    work: str
    safety: list[str]
    link: str = ""
    source: str = ""

    @property
    def headcount(self) -> int:
        return sum(m.workers for m in self.manpower)


@dataclass
class ProjectSnapshot:
    """Everything a module needs about one project for one period, from all sources."""
    project: Project
    period_start: date
    period_end: date
    rfis: list[RFI] = field(default_factory=list)
    submittals: list[Submittal] = field(default_factory=list)
    change_orders: list[ChangeOrder] = field(default_factory=list)
    budget: list[BudgetLine] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    daily_logs: list[DailyLog] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)   # capability -> connector name
    notes: list[str] = field(default_factory=list)          # merge warnings, skipped connectors

    def to_dict(self) -> dict:
        return _to_plain(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectSnapshot":
        return _from_plain(cls, d)


# ---------------------------------------------------- (de)serialization ---
_NESTED = {"project": Project, "rfis": RFI, "submittals": Submittal, "change_orders": ChangeOrder,
           "budget": BudgetLine, "milestones": Milestone, "daily_logs": DailyLog, "manpower": Manpower}


def _to_plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_plain(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, list):
        return [_to_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _is_date_type(tp) -> bool:
    if tp is date:
        return True
    if get_origin(tp) is not None:
        return any(a is date for a in get_args(tp))
    return False


def _from_plain(cls, d: dict):
    hints = get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name not in d:
            continue
        v = d[f.name]
        tp = hints.get(f.name)
        if v is None:
            kwargs[f.name] = None
        elif f.name in _NESTED and isinstance(v, list):
            kwargs[f.name] = [_from_plain(_NESTED[f.name], x) for x in v]
        elif f.name in _NESTED and isinstance(v, dict):
            kwargs[f.name] = _from_plain(_NESTED[f.name], v)
        elif _is_date_type(tp) and isinstance(v, str):
            kwargs[f.name] = date.fromisoformat(v)
        else:
            kwargs[f.name] = v
    return cls(**kwargs)

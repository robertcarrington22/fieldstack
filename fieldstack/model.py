"""
Unified construction data model.

Every source (Procore today, Autodesk Build, Sage 300 CRE, P6 later) is normalized
into these dataclasses so the metrics and the report never touch a vendor shape.
Each record carries a `ref` (RFI-041, SUB-118, PCO-007, LOG-2026-08-14, SOV-03-000,
MS-4) that the report uses as a citation and a `link` back to the source system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Project:
    id: int
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
    link: str


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
    link: str


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


@dataclass
class Milestone:
    ref: str
    name: str
    baseline: date
    current: date
    actual: Optional[date]


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
    link: str

    @property
    def headcount(self) -> int:
        return sum(m.workers for m in self.manpower)


@dataclass
class ProjectSnapshot:
    project: Project
    period_start: date
    period_end: date
    rfis: list[RFI] = field(default_factory=list)
    submittals: list[Submittal] = field(default_factory=list)
    change_orders: list[ChangeOrder] = field(default_factory=list)
    budget: list[BudgetLine] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    daily_logs: list[DailyLog] = field(default_factory=list)

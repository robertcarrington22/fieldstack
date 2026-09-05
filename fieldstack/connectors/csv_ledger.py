"""
Job-cost ledger from a CSV export (Sage 300 CRE, Viewpoint Vista, Foundation, or any
ERP that can export job cost by cost code). Provides BUDGET, which by default takes
precedence over the PM tool's budget because accounting is the system of record for
dollars.

Expected columns (header names are matched case-insensitively, extra columns ignored):
  job, cost_code, description, original_budget, approved_changes, committed, cost_to_date, billed_to_date, percent_complete

Settings:
  path = "mock/ledger.csv"
  job_column = "job"        (optional; used to filter rows to the project ref)
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ..model import BudgetLine
from . import Capability, Partial, register


def _f(v) -> float:
    v = (v or "").replace("$", "").replace(",", "").strip()
    return float(v) if v else 0.0


@register("csv_ledger")
class CsvLedgerConnector:
    capabilities = frozenset({Capability.BUDGET})

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.path = Path(settings["path"])
        self.job_column = settings.get("job_column", "job")

    def fetch(self, project_ref, period_start: date, period_end: date) -> Partial:
        lines = []
        with self.path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
            for row in reader:
                if self.job_column in row and str(row[self.job_column]).strip() != str(project_ref):
                    continue
                code = row["cost_code"].strip()
                orig, chg = _f(row.get("original_budget")), _f(row.get("approved_changes"))
                pct = _f(row.get("percent_complete"))
                lines.append(BudgetLine(
                    ref=f"SOV-{code}", code=code, description=row.get("description", "").strip(),
                    original=orig, approved_changes=chg, revised=orig + chg,
                    committed=_f(row.get("committed")), cost_to_date=_f(row.get("cost_to_date")),
                    billed_to_date=_f(row.get("billed_to_date")),
                    percent_complete=pct / 100 if pct > 1 else pct, source=self.name))
        return Partial(budget=lines)

    def health(self) -> tuple[bool, str]:
        return self.path.exists(), str(self.path)

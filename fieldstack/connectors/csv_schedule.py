"""
Milestones from a CSV export (Primavera P6 or MS Project milestone filter, or a hand
kept list). Provides MILESTONES, which by default takes precedence over the PM tool's
schedule because the scheduler's file is the system of record for dates.

Expected columns: id, name, baseline, current, actual   (dates YYYY-MM-DD; actual may be blank)
Optional:         job                                   (filters rows to the project ref)

Settings:
  path = "mock/schedule.csv"
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ..model import Milestone
from . import Capability, Partial, register


def _d(v):
    v = (v or "").strip()
    return date.fromisoformat(v) if v else None


@register("csv_schedule")
class CsvScheduleConnector:
    capabilities = frozenset({Capability.MILESTONES})

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.path = Path(settings["path"])

    def fetch(self, project_ref, period_start: date, period_end: date) -> Partial:
        ms = []
        with self.path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
            for row in reader:
                if "job" in row and str(row["job"]).strip() != str(project_ref):
                    continue
                ms.append(Milestone(ref=f"MS-{row['id'].strip()}", name=row["name"].strip(),
                                    baseline=_d(row["baseline"]), current=_d(row["current"]) or _d(row["baseline"]),
                                    actual=_d(row.get("actual")), source=self.name))
        return Partial(milestones=ms)

    def health(self) -> tuple[bool, str]:
        return self.path.exists(), str(self.path)

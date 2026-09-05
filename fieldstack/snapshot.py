"""
SnapshotBuilder: asks every configured connector for what it can provide and merges
the results into one ProjectSnapshot by capability, in precedence order.

Rules:
- For each capability, the first connector in precedence order that returns data wins.
  Later connectors are recorded as fallbacks and ignored for that capability.
- Default precedence is the order connectors appear in the config. Override per
  capability under [precedence] in fieldstack.toml, e.g. budget = ["ledger", "procore"].
- A connector that fails health() or raises during fetch() is skipped with a note,
  never a crash. The report footer shows which sources produced which sections.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .connectors import Capability, Connector, Partial
from .model import ProjectSnapshot


class SnapshotBuilder:
    def __init__(self, connectors: list[Connector], precedence: Optional[dict[str, list[str]]] = None):
        self.connectors = connectors
        self.precedence = {k: list(v) for k, v in (precedence or {}).items()}

    def _order_for(self, cap: Capability) -> list[Connector]:
        by_name = {c.name: c for c in self.connectors}
        preferred = [by_name[n] for n in self.precedence.get(cap.value, []) if n in by_name]
        rest = [c for c in self.connectors if c not in preferred]
        return [c for c in preferred + rest if cap in c.capabilities]

    def build(self, project_ids: dict[str, object], period_start: date, period_end: date) -> ProjectSnapshot:
        partials: dict[str, Partial] = {}
        notes: list[str] = []

        for c in self.connectors:
            ref = project_ids.get(c.name)
            if ref is None:
                notes.append(f"{c.name}: no project id configured, skipped")
                continue
            ok, msg = c.health()
            if not ok:
                notes.append(f"{c.name}: unavailable ({msg}), skipped")
                continue
            try:
                partials[c.name] = c.fetch(ref, period_start, period_end)
            except NotImplementedError as e:
                notes.append(f"{c.name}: {e}")
            except Exception as e:  # a bad source must not kill the report
                notes.append(f"{c.name}: fetch failed ({type(e).__name__}: {e})")

        chosen: dict[str, object] = {}
        sources: dict[str, str] = {}
        for cap in Capability:
            for c in self._order_for(cap):
                part = partials.get(c.name)
                if part is None:
                    continue
                value = part.get(cap)
                if value is None or (isinstance(value, list) and not value):
                    continue
                chosen[cap.value] = value
                sources[cap.value] = c.name
                break

        if "project" not in chosen:
            raise RuntimeError("No connector provided the project record. " + "; ".join(notes))

        return ProjectSnapshot(
            project=chosen["project"], period_start=period_start, period_end=period_end,
            rfis=chosen.get("rfis", []), submittals=chosen.get("submittals", []),
            change_orders=chosen.get("change_orders", []), budget=chosen.get("budget", []),
            milestones=chosen.get("milestones", []), daily_logs=chosen.get("daily_logs", []),
            sources=sources, notes=notes,
        )

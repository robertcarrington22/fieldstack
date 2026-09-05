"""
hh2 connector (Sage 300 CRE and Sage 100 Contractor via hh2's Universal Construction
Model). Declared, not implemented.

hh2 is Sage's authorized integration platform for CRE. Its UCM exposes jobs, cost
codes, budgets, commitments, commitment change orders, AP invoices, and pay
applications through a REST API once the on-prem sync client is installed on the
customer's accounting server. Until a pilot customer grants hh2 access, the
csv_ledger connector covers the same BUDGET capability from a Sage export.

Vista support in hh2 is limited; a Viewpoint customer likely needs a direct
Vista connector (declare it the same way as this one).
"""
from __future__ import annotations

from datetime import date

from . import Capability, Partial, register


@register("hh2")
class Hh2Connector:
    capabilities = frozenset({Capability.BUDGET})

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.api_key = settings.get("api_key")
        self.tenant = settings.get("tenant")

    def fetch(self, project_ref, period_start: date, period_end: date) -> Partial:
        raise NotImplementedError("hh2 connector is declared but not implemented. Use csv_ledger with a Sage export.")

    def health(self) -> tuple[bool, str]:
        return False, "not implemented"

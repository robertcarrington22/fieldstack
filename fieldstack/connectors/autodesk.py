"""
Autodesk Construction Cloud (Build) connector. Declared, not implemented.

ACC covers the same capabilities as Procore for a GC that standardized on Autodesk.
The endpoints are known; the mapping work is the first real task when a pilot
customer is on ACC:

  RFIs           GET /construction/rfis/v2/projects/{projectId}/rfis
  Submittals     GET /construction/submittals/v2/projects/{projectId}/items
  Issues/Logs    GET /construction/issues/v1/projects/{projectId}/issues
  Cost           GET /cost/v1/containers/{containerId}/budgets
  Schedule       GET /construction/schedule/v1/projects/{projectId}/activities (milestones filter)

Auth is a 3-legged OAuth token with data:read scope. Settings: token, account_id.
"""
from __future__ import annotations

from datetime import date

from . import Capability, Partial, register


@register("autodesk_build")
class AutodeskBuildConnector:
    capabilities = frozenset({Capability.PROJECT, Capability.RFIS, Capability.SUBMITTALS,
                              Capability.BUDGET, Capability.MILESTONES})

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.token = settings.get("token")
        self.account_id = settings.get("account_id")

    def fetch(self, project_ref, period_start: date, period_end: date) -> Partial:
        raise NotImplementedError("Autodesk Build connector is declared but not implemented. See module docstring.")

    def health(self) -> tuple[bool, str]:
        return False, "not implemented"

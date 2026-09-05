"""
Connector layer.

A connector reads one source system and returns a Partial: whichever slices of the
unified model that system can provide. It declares those slices as capabilities so
the SnapshotBuilder knows what to ask it for and how to merge it with the others.

Adding a source is one file:

    @register("vista")
    class VistaConnector:
        capabilities = frozenset({Capability.BUDGET})
        def __init__(self, name, settings): ...
        def fetch(self, project_ref, period_start, period_end) -> Partial: ...
        def health(self) -> tuple[bool, str]: ...

Then list it in fieldstack.toml under [[connectors]] with kind = "vista".
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from ..model import BudgetLine, ChangeOrder, DailyLog, Milestone, Project, RFI, Submittal


class Capability(str, Enum):
    PROJECT = "project"
    RFIS = "rfis"
    SUBMITTALS = "submittals"
    CHANGE_ORDERS = "change_orders"
    BUDGET = "budget"
    MILESTONES = "milestones"
    DAILY_LOGS = "daily_logs"


@dataclass
class Partial:
    """What one connector returned. None means 'this source does not provide it'."""
    project: Optional[Project] = None
    rfis: Optional[list[RFI]] = None
    submittals: Optional[list[Submittal]] = None
    change_orders: Optional[list[ChangeOrder]] = None
    budget: Optional[list[BudgetLine]] = None
    milestones: Optional[list[Milestone]] = None
    daily_logs: Optional[list[DailyLog]] = None

    def get(self, cap: Capability):
        return getattr(self, cap.value)


@runtime_checkable
class Connector(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def fetch(self, project_ref: Any, period_start: date, period_end: date) -> Partial: ...
    def health(self) -> tuple[bool, str]: ...


REGISTRY: dict[str, type] = {}


def register(kind: str):
    def deco(cls):
        cls.kind = kind
        REGISTRY[kind] = cls
        return cls
    return deco


def _load_all() -> None:
    """Import every module in this package so @register runs."""
    for m in pkgutil.iter_modules(__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{__name__}.{m.name}")


def build(kind: str, name: str, settings: dict) -> Connector:
    if not REGISTRY:
        _load_all()
    if kind not in REGISTRY:
        _load_all()
    if kind not in REGISTRY:
        raise KeyError(f"unknown connector kind '{kind}'. Known: {sorted(REGISTRY)}")
    return REGISTRY[kind](name=name, settings=settings)


def kinds() -> list[str]:
    if not REGISTRY:
        _load_all()
    return sorted(REGISTRY)

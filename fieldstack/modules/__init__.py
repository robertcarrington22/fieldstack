"""
Module layer.

A module is a product surface built on the shared snapshot: Owner Report today;
Invoice Match, Claims Guard, Margin Watch, Lookahead later. Each declares the
capabilities it needs so the job runner can refuse to run it against a tenant whose
connectors cannot supply them, and returns a ModuleOutput the delivery layer knows
how to send.

    @register_module("invoice_match")
    class InvoiceMatch:
        requires = frozenset({Capability.BUDGET, Capability.CHANGE_ORDERS})
        def run(self, snapshot, ctx) -> ModuleOutput: ...
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol

from ..connectors import Capability
from ..llm import LLMGateway
from ..model import ProjectSnapshot


@dataclass
class RunContext:
    tenant: str
    project_key: str
    as_of: date
    llm: LLMGateway
    prior_report_excerpt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleOutput:
    module: str
    title: str
    summary: str                 # one paragraph, plain text, for chat/email delivery
    html: str
    markdown: str
    facts: dict
    narrative: dict
    attention: list[str] = field(default_factory=list)
    file_stem: str = "report"


class Module(Protocol):
    name: str
    requires: frozenset[Capability]

    def run(self, snapshot: ProjectSnapshot, ctx: RunContext) -> ModuleOutput: ...


REGISTRY: dict[str, type] = {}


def register_module(name: str):
    def deco(cls):
        cls.name = name
        REGISTRY[name] = cls
        return cls
    return deco


def _load_all() -> None:
    for m in pkgutil.iter_modules(__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{__name__}.{m.name}")


def get_module(name: str) -> Module:
    if name not in REGISTRY:
        _load_all()
    if name not in REGISTRY:
        raise KeyError(f"unknown module '{name}'. Known: {sorted(REGISTRY)}")
    return REGISTRY[name]()


def module_names() -> list[str]:
    if not REGISTRY:
        _load_all()
    return sorted(REGISTRY)


def missing_capabilities(module: Module, snapshot: ProjectSnapshot) -> list[str]:
    have = set(snapshot.sources.keys())
    return sorted(c.value for c in module.requires if c.value not in have)

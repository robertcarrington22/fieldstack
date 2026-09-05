"""
Job runner. One function a CLI, a cron entry, or a queue worker can call:

    run_module(config, project_key="bergen", module_name="owner_report", period=(start, end), as_of=today)

It builds connectors from the tenant config, merges a snapshot, stores it, runs the
module, records the run, and hands the output to every configured delivery.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from . import connectors as connector_registry
from . import delivery as delivery_registry
from .config import TenantConfig
from .llm import LLMGateway, make_gateway
from .modules import ModuleOutput, RunContext, get_module, missing_capabilities
from .snapshot import SnapshotBuilder
from .store import SnapshotStore

log = logging.getLogger("fieldstack")


@dataclass
class RunResult:
    output: ModuleOutput
    sources: dict[str, str]
    notes: list[str]
    deliveries: list[str] = field(default_factory=list)
    llm_usage: dict = field(default_factory=dict)


def build_connectors(cfg: TenantConfig):
    return [connector_registry.build(c.kind, c.name, c.settings) for c in cfg.connectors]


def run_module(cfg: TenantConfig, project_key: str, module_name: str, period: tuple[date, date], as_of: date,
               llm: Optional[LLMGateway] = None, deliver: bool = True, store: bool = True,
               sample: Optional[bool] = None) -> RunResult:
    project = cfg.project(project_key)
    ps, pe = period

    conns = build_connectors(cfg)
    log.info("connectors: %s", ", ".join(f"{c.name}({c.kind})" for c in conns))
    snap = SnapshotBuilder(conns, cfg.precedence).build(project.ids, ps, pe)
    for n in snap.notes:
        log.warning(n)
    log.info("sources: %s", snap.sources)

    module = get_module(module_name)
    missing = missing_capabilities(module, snap)
    if missing:
        raise RuntimeError(f"module '{module_name}' needs {missing} and no connector supplied them. Notes: {snap.notes}")

    gateway = llm or make_gateway(cfg.llm_provider, cfg.llm_model)
    prior = ""
    if project.prior_report:
        p = cfg.resolve(project.prior_report)
        prior = p.read_text(encoding="utf-8") if p.exists() else ""
    if sample is None:
        sample = any(c.settings.get("mode", "") == "mock" for c in cfg.connectors)
    ctx = RunContext(tenant=cfg.name, project_key=project_key, as_of=as_of, llm=gateway,
                     prior_report_excerpt=prior, extra={"sample": sample})
    output = module.run(snap, ctx)
    usage = getattr(gateway, "usage", {}) or {}

    if store:
        st = SnapshotStore(cfg.resolve(cfg.store_path))
        st.save_snapshot(cfg.name, project_key, as_of, snap)
        st.save_run(cfg.name, project_key, module_name, as_of, gateway.provider, gateway.model, usage, output.facts)
        st.close()

    sent = []
    if deliver:
        for d in cfg.deliveries:
            settings = dict(d.settings)
            if d.kind == "file":
                settings["dir"] = str(cfg.resolve(settings.get("dir", "out")))
            sent.append(delivery_registry.build(d.kind, settings).send(output))

    return RunResult(output=output, sources=snap.sources, notes=snap.notes, deliveries=sent, llm_usage=usage)

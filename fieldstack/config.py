"""
Tenant configuration, loaded from a TOML file. One file per customer.

    [tenant]
    name = "Sample Builders LLC"

    [[connectors]]            # order = default precedence
    name = "procore"
    kind = "procore"
    mode = "mock"
    fixtures = "mock/procore"

    [[connectors]]
    name = "ledger"
    kind = "csv_ledger"
    path = "mock/ledger.csv"

    [precedence]              # per-capability override
    budget = ["ledger", "procore"]

    [[projects]]
    key = "bergen"
    name = "Bergen Street Apartments"
    ids = { procore = 2264101, ledger = "26-014" }

    [llm]
    provider = "auto"         # auto | claude | mock
    model = "claude-opus-5"

    [[delivery]]
    kind = "file"
    dir = "out"

Any string value of the form "${ENV_VAR}" is replaced from the environment, so
tokens never live in the file.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ENV = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def _expand(v: Any) -> Any:
    if isinstance(v, str):
        m = _ENV.match(v)
        return os.environ.get(m.group(1), "") if m else v
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


@dataclass
class ConnectorConfig:
    name: str
    kind: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectConfig:
    key: str
    name: str
    ids: dict[str, Any]
    prior_report: str = ""          # path to a prior owner report excerpt for voice matching


@dataclass
class DeliveryConfig:
    kind: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantConfig:
    name: str
    connectors: list[ConnectorConfig]
    projects: list[ProjectConfig]
    precedence: dict[str, list[str]]
    llm_provider: str = "auto"
    llm_model: str = "claude-opus-5"
    deliveries: list[DeliveryConfig] = field(default_factory=list)
    store_path: str = "out/fieldstack.sqlite"
    drafts_path: str = "out/drafts"
    approved_path: str = "out/approved"
    root: Path = Path(".")

    def project(self, key: str) -> ProjectConfig:
        for p in self.projects:
            if p.key == key:
                return p
        raise KeyError(f"no project '{key}' in config. Known: {[p.key for p in self.projects]}")

    def resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)


def load(path: str | Path) -> TenantConfig:
    path = Path(path)
    raw = _expand(tomllib.loads(path.read_text(encoding="utf-8")))
    root = path.parent
    connectors = [ConnectorConfig(name=c["name"], kind=c["kind"],
                                  settings={k: v for k, v in c.items() if k not in ("name", "kind")})
                  for c in raw.get("connectors", [])]
    # make relative paths in connector settings relative to the config file
    for c in connectors:
        for k in ("path", "fixtures"):
            if k in c.settings and not Path(c.settings[k]).is_absolute():
                c.settings[k] = str(root / c.settings[k])
    projects = [ProjectConfig(key=p["key"], name=p.get("name", p["key"]), ids=p.get("ids", {}),
                              prior_report=p.get("prior_report", "")) for p in raw.get("projects", [])]
    deliveries = [DeliveryConfig(kind=d["kind"], settings={k: v for k, v in d.items() if k != "kind"})
                  for d in raw.get("delivery", [])] or [DeliveryConfig("file", {"dir": "out"})]
    llm = raw.get("llm", {})
    return TenantConfig(
        name=raw.get("tenant", {}).get("name", "Tenant"), connectors=connectors, projects=projects,
        precedence=raw.get("precedence", {}), llm_provider=llm.get("provider", "auto"),
        llm_model=llm.get("model", "claude-opus-5"), deliveries=deliveries,
        store_path=raw.get("store", {}).get("path", "out/fieldstack.sqlite"),
        drafts_path=raw.get("review", {}).get("drafts", "out/drafts"),
        approved_path=raw.get("review", {}).get("approved", "out/approved"), root=root,
    )

"""
Snapshot store. Every nightly pull is kept, so modules that need history
(Margin Watch's fade detection, Cash and WIP Forecast, response-time trends) have
it without a second pipeline. SQLite for the prototype; the interface is what a
Postgres implementation would keep.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .model import ProjectSnapshot


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY, tenant TEXT, project_key TEXT, period_start TEXT, period_end TEXT,
            as_of TEXT, pulled_at TEXT, sources TEXT, payload TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS module_runs (
            id INTEGER PRIMARY KEY, tenant TEXT, project_key TEXT, module TEXT, as_of TEXT, ran_at TEXT,
            llm_provider TEXT, llm_model TEXT, usage TEXT, facts TEXT)""")
        self.db.commit()

    def save_snapshot(self, tenant: str, project_key: str, as_of: date, snap: ProjectSnapshot) -> int:
        cur = self.db.execute(
            "INSERT INTO snapshots (tenant, project_key, period_start, period_end, as_of, pulled_at, sources, payload) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (tenant, project_key, snap.period_start.isoformat(), snap.period_end.isoformat(), as_of.isoformat(),
             datetime.now().isoformat(timespec="seconds"), json.dumps(snap.sources), json.dumps(snap.to_dict())))
        self.db.commit()
        return cur.lastrowid

    def latest_snapshot(self, tenant: str, project_key: str) -> Optional[ProjectSnapshot]:
        row = self.db.execute("SELECT payload FROM snapshots WHERE tenant=? AND project_key=? ORDER BY id DESC LIMIT 1",
                              (tenant, project_key)).fetchone()
        return ProjectSnapshot.from_dict(json.loads(row[0])) if row else None

    def history(self, tenant: str, project_key: str) -> list[tuple[str, str]]:
        """(as_of, pulled_at) pairs, oldest first."""
        return self.db.execute("SELECT as_of, pulled_at FROM snapshots WHERE tenant=? AND project_key=? ORDER BY id",
                               (tenant, project_key)).fetchall()

    def save_run(self, tenant: str, project_key: str, module: str, as_of: date, provider: str, model: str,
                 usage: Optional[dict], facts: dict) -> int:
        cur = self.db.execute(
            "INSERT INTO module_runs (tenant, project_key, module, as_of, ran_at, llm_provider, llm_model, usage, facts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant, project_key, module, as_of.isoformat(), datetime.now().isoformat(timespec="seconds"),
             provider, model, json.dumps(usage or {}), json.dumps(facts, default=str)))
        self.db.commit()
        return cur.lastrowid

    def close(self) -> None:
        self.db.close()

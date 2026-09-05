"""
Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fieldstack import config as cfg_mod                       # noqa: E402
from fieldstack.connectors import Capability, Partial, build   # noqa: E402
from fieldstack.jobs import run_module                         # noqa: E402
from fieldstack.llm import MockGateway                         # noqa: E402
from fieldstack.metrics import business_days_between, compute  # noqa: E402
from fieldstack.model import Milestone, Project, ProjectSnapshot  # noqa: E402
from fieldstack.snapshot import SnapshotBuilder                # noqa: E402
from fieldstack.store import SnapshotStore                     # noqa: E402

PERIOD = (date(2026, 8, 1), date(2026, 8, 31))
AS_OF = date(2026, 9, 4)


def _project(source="x"):
    return Project(id="1", name="P", number="1", address="", description="", start_date=date(2026, 1, 1),
                   completion_date=date(2027, 1, 1), contract_value=1.0, owner="", owners_rep="", lender="",
                   gc_name="", project_executive="", project_manager="", superintendent="", source=source)


class FakeConnector:
    def __init__(self, name, caps, partial, healthy=True):
        self.name, self.capabilities, self._p, self._ok = name, frozenset(caps), partial, healthy

    def fetch(self, ref, ps, pe):
        return self._p

    def health(self):
        return self._ok, "fake"


class BusinessDays(unittest.TestCase):
    def test_counts_weekdays_only(self):
        self.assertEqual(business_days_between(date(2026, 8, 19), date(2026, 9, 4)), 12)   # Wed -> Fri, 2 weeks + 2
        self.assertEqual(business_days_between(date(2026, 8, 28), date(2026, 8, 31)), 1)   # Fri -> Mon
        self.assertEqual(business_days_between(date(2026, 9, 4), date(2026, 8, 19)), -12)


class Merge(unittest.TestCase):
    def test_precedence_and_fallback(self):
        pm = FakeConnector("pm", {Capability.PROJECT, Capability.MILESTONES},
                           Partial(project=_project("pm"), milestones=[Milestone("MS-1", "a", AS_OF, AS_OF, None, source="pm")]))
        sched = FakeConnector("sched", {Capability.MILESTONES},
                              Partial(milestones=[Milestone("MS-1", "a", AS_OF, AS_OF, None, source="sched")]))
        snap = SnapshotBuilder([pm, sched], {"milestones": ["sched", "pm"]}).build({"pm": "1", "sched": "1"}, *PERIOD)
        self.assertEqual(snap.sources["milestones"], "sched")
        self.assertEqual(snap.sources["project"], "pm")

    def test_unhealthy_connector_is_skipped_not_fatal(self):
        pm = FakeConnector("pm", {Capability.PROJECT}, Partial(project=_project("pm")))
        bad = FakeConnector("bad", {Capability.MILESTONES}, Partial(), healthy=False)
        snap = SnapshotBuilder([pm, bad]).build({"pm": "1", "bad": "1"}, *PERIOD)
        self.assertNotIn("milestones", snap.sources)
        self.assertTrue(any("bad" in n for n in snap.notes))


class CsvConnectors(unittest.TestCase):
    def test_ledger_and_schedule_parse(self):
        ledger = build("csv_ledger", "ledger", {"path": str(ROOT / "mock" / "ledger.csv")})
        part = ledger.fetch("26-014", *PERIOD)
        self.assertEqual(len(part.budget), 14)
        self.assertAlmostEqual(part.budget[2].cost_to_date, 5_812_000)
        self.assertAlmostEqual(part.budget[2].percent_complete, 0.60)
        sched = build("csv_schedule", "schedule", {"path": str(ROOT / "mock" / "schedule.csv")})
        ms = sched.fetch("26-014", *PERIOD).milestones
        self.assertEqual(len(ms), 8)
        self.assertEqual(ms[-1].current, date(2027, 12, 14))

    def test_ledger_filters_by_job(self):
        ledger = build("csv_ledger", "ledger", {"path": str(ROOT / "mock" / "ledger.csv")})
        self.assertEqual(ledger.fetch("99-999", *PERIOD).budget, [])


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg_mod.load(ROOT / "fieldstack.toml")

    def test_owner_report_from_three_sources(self):
        res = run_module(self.cfg, "bergen", "owner_report", PERIOD, AS_OF, llm=MockGateway(), deliver=False, store=False)
        self.assertEqual(res.sources["budget"], "ledger")
        self.assertEqual(res.sources["milestones"], "schedule")
        self.assertEqual(res.sources["rfis"], "procore")
        f = res.output.facts
        self.assertEqual(f["rfis_opened"], 10)
        self.assertEqual(f["rfis_closed"], 8)
        self.assertEqual(f["rfis_open_total"], 5)
        self.assertEqual(f["rfis_overdue"][0]["ref"], "RFI-041")
        self.assertEqual(f["rfis_overdue"][0]["days_overdue_bdays"], 12)
        self.assertAlmostEqual(f["cost_to_date"], 16_070_000)      # ledger wins over Procore budget
        self.assertIn("RFI-041", res.output.html)
        self.assertIn("SAMPLE DATA", res.output.html)

    def test_missing_capability_is_refused(self):
        cfg = cfg_mod.load(ROOT / "fieldstack.toml")
        cfg.connectors = [c for c in cfg.connectors if c.name == "ledger"]
        with self.assertRaises(RuntimeError):
            run_module(cfg, "bergen", "owner_report", PERIOD, AS_OF, llm=MockGateway(), deliver=False, store=False)


class Store(unittest.TestCase):
    def test_snapshot_roundtrip(self):
        cfg = cfg_mod.load(ROOT / "fieldstack.toml")
        res = run_module(cfg, "bergen", "owner_report", PERIOD, AS_OF, llm=MockGateway(), deliver=False, store=False)
        from fieldstack.jobs import build_connectors
        snap = SnapshotBuilder(build_connectors(cfg), cfg.precedence).build(cfg.project("bergen").ids, *PERIOD)
        with tempfile.TemporaryDirectory() as td:
            st = SnapshotStore(Path(td) / "t.sqlite")
            st.save_snapshot("t", "bergen", AS_OF, snap)
            back = st.latest_snapshot("t", "bergen")
            st.close()
        self.assertIsInstance(back, ProjectSnapshot)
        self.assertEqual(back.project.name, snap.project.name)
        self.assertEqual(len(back.daily_logs), len(snap.daily_logs))
        self.assertEqual(back.daily_logs[0].day, snap.daily_logs[0].day)
        self.assertEqual(compute(back, AS_OF).rfis_open_total, res.output.facts["rfis_open_total"])


if __name__ == "__main__":
    unittest.main()

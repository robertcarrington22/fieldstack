"""Review layer: draft package, edits, approval rendering."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fieldstack import config as cfg_mod                      # noqa: E402
from fieldstack.jobs import run_module                        # noqa: E402
from fieldstack.llm import MockGateway                        # noqa: E402
from fieldstack.review import drafts                          # noqa: E402

PERIOD = (date(2026, 8, 1), date(2026, 8, 31))
AS_OF = date(2026, 9, 4)


class ReviewFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = cfg_mod.load(ROOT / "fieldstack.toml")
        self.cfg.drafts_path = str(self.tmp / "drafts")
        self.cfg.approved_path = str(self.tmp / "approved")
        self.cfg.store_path = str(self.tmp / "s.sqlite")
        self.cfg.deliveries = []
        self.res = run_module(self.cfg, "bergen", "owner_report", PERIOD, AS_OF, llm=MockGateway(), deliver=False, store=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_written_and_listed(self):
        lst = drafts.list_drafts(self.cfg)
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["status"], "draft")
        d = drafts.load_draft(self.cfg, lst[0]["id"])
        self.assertNotIn("snapshot", d)
        self.assertIn("RFI-041", d["links"])
        self.assertEqual(d["edits"]["executive_summary"], d["narrative"]["executive_summary"])

    def test_edit_then_approve_renders_edits(self):
        did = drafts.list_drafts(self.cfg)[0]["id"]
        drafts.save_draft(self.cfg, did, {"executive_summary": "Edited summary sentence (RFI-041).",
                                          "owner_actions": [{"text": "Sign PCO-007 now (PCO-007).", "include": True},
                                                            {"text": "Dropped line (MS-8).", "include": False}]}, edit_seconds=840)
        d = drafts.load_draft(self.cfg, did)
        self.assertEqual(d["edit_seconds"], 840)
        html, md = drafts.render_current(self.cfg, did)
        self.assertIn("Edited summary sentence", html)
        self.assertIn("Sign PCO-007 now", html)
        self.assertNotIn("Dropped line", html)
        self.assertIn("SAMPLE DATA", html)
        r = drafts.approve_draft(self.cfg, did, deliver=False)
        self.assertEqual(r["status"], "approved")
        self.assertTrue(Path(r["path"]).exists())
        with self.assertRaises(PermissionError):
            drafts.save_draft(self.cfg, did, {"executive_summary": "too late"})
        again = drafts.approve_draft(self.cfg, did)
        self.assertEqual(again["path"], r["path"])

    def test_regenerate_returns_sections_without_overwriting(self):
        did = drafts.list_drafts(self.cfg)[0]["id"]
        drafts.save_draft(self.cfg, did, {"look_ahead": "My own look ahead (MS-3)."})
        n = drafts.regenerate(self.cfg, did, gateway=MockGateway())
        self.assertTrue(n["look_ahead"])
        self.assertEqual(drafts.load_draft(self.cfg, did)["edits"]["look_ahead"], "My own look ahead (MS-3).")


if __name__ == "__main__":
    unittest.main()

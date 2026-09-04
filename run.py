"""
Fieldstack Owner Report, command line.

  python run.py                                  # mock Procore, auto-pick narrator, August 2026
  python run.py --period 2026-08 --narrator mock
  python run.py --narrator claude                # requires ANTHROPIC_API_KEY or `ant auth login`
  python run.py --live --token $TOKEN --company 1234 --project 5678

Writes out/<project>-<period>.html, .md, and facts.json.
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date
from pathlib import Path

from fieldstack.metrics import compute
from fieldstack.narrative import make_narrator
from fieldstack.procore import LiveProcoreClient, MockProcoreClient
from fieldstack.render import render_html, render_markdown

ROOT = Path(__file__).parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate an Owner Report from Procore data.")
    ap.add_argument("--period", default="2026-08", help="YYYY-MM")
    ap.add_argument("--as-of", default=None, help="Report date, YYYY-MM-DD (default: today)")
    ap.add_argument("--project", type=int, default=2264101)
    ap.add_argument("--narrator", choices=["auto", "claude", "mock"], default="auto")
    ap.add_argument("--live", action="store_true", help="Use the live Procore API instead of fixtures")
    ap.add_argument("--token", default=None)
    ap.add_argument("--company", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args()

    year, month = (int(x) for x in args.period.split("-"))
    ps = date(year, month, 1)
    pe = date(year, month, calendar.monthrange(year, month)[1])
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    if args.live:
        if not (args.token and args.company):
            print("--live needs --token and --company", file=sys.stderr)
            return 2
        client = LiveProcoreClient(args.token, args.company)
    else:
        client = MockProcoreClient(ROOT / "mock" / "procore")

    print(f"Pulling {'live' if args.live else 'mock'} Procore data for project {args.project}, {ps} to {pe} ...")
    snap = client.snapshot(args.project, ps, pe)
    print(f"  {len(snap.rfis)} RFIs, {len(snap.submittals)} submittals, {len(snap.change_orders)} change orders, "
          f"{len(snap.budget)} budget lines, {len(snap.milestones)} milestones, {len(snap.daily_logs)} daily logs")

    facts = compute(snap, as_of)
    print(f"  {facts.percent_complete_sov * 100:.0f}% complete, {len(facts.rfis_overdue)} RFIs overdue, "
          f"{len(facts.submittals_overdue)} submittals overdue, {len(facts.change_orders_pending)} COs pending")

    narrator = make_narrator(None if args.narrator == "auto" else args.narrator)
    print(f"Writing narrative with {type(narrator).__name__} ...")
    prior = ROOT / "mock" / "prior_owner_report_excerpt.md"
    nar = narrator.write(facts, prior.read_text(encoding="utf-8") if prior.exists() else "")
    if nar.usage:
        print(f"  tokens: {nar.usage}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{snap.project.name.lower().replace(' ', '-')}-{args.period}"
    (out / f"{stem}.html").write_text(render_html(snap, facts, nar, sample=not args.live), encoding="utf-8")
    (out / f"{stem}.md").write_text(render_markdown(snap, facts, nar), encoding="utf-8")
    (out / f"{stem}.facts.json").write_text(json.dumps(facts.to_dict(), indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out / (stem + '.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

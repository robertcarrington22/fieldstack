"""
Fieldstack, command line.

  python run.py                                     # fieldstack.toml, project bergen, owner_report, August 2026
  python run.py --period 2026-08 --as-of 2026-09-04 --llm claude
  python run.py --config customers/acme.toml --project tower --module owner_report
  python run.py --list                              # connectors and modules available
"""
from __future__ import annotations

import argparse
import calendar
import logging
import sys
from datetime import date
from pathlib import Path

from fieldstack import config as cfg_mod
from fieldstack.connectors import kinds as connector_kinds
from fieldstack.jobs import run_module
from fieldstack.llm import make_gateway
from fieldstack.modules import module_names

ROOT = Path(__file__).parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a Fieldstack module for one project and period.")
    ap.add_argument("--config", default=str(ROOT / "fieldstack.toml"))
    ap.add_argument("--project", default=None, help="project key from the config (default: first)")
    ap.add_argument("--module", default="owner_report")
    ap.add_argument("--period", default="2026-08", help="YYYY-MM")
    ap.add_argument("--as-of", default=None, help="Report date, YYYY-MM-DD (default: today)")
    ap.add_argument("--llm", choices=["auto", "claude", "mock"], default=None, help="override [llm].provider")
    ap.add_argument("--no-deliver", action="store_true")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.list:
        print("connectors:", ", ".join(connector_kinds()))
        print("modules:   ", ", ".join(module_names()))
        return 0

    cfg = cfg_mod.load(args.config)
    project_key = args.project or cfg.projects[0].key
    year, month = (int(x) for x in args.period.split("-"))
    period = (date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    llm = make_gateway(args.llm, cfg.llm_model) if args.llm else None

    print(f"{cfg.name} / {project_key} / {args.module} / {args.period} as of {as_of}")
    res = run_module(cfg, project_key, args.module, period, as_of, llm=llm,
                     deliver=not args.no_deliver, store=not args.no_store)
    print("sources:  " + ", ".join(f"{k}<-{v}" for k, v in res.sources.items()))
    for n in res.notes:
        print("note:     " + n)
    if res.llm_usage:
        print(f"llm:      {res.llm_usage}")
    for d in res.deliveries:
        print("sent:     " + d)
    print(f"attention: {len(res.output.attention)} item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

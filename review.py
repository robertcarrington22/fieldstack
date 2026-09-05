"""
Start the review screen.

  python review.py                       # fieldstack.toml, http://127.0.0.1:8787/
  python review.py --config customers/acme.toml --port 9000
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fieldstack import config as cfg_mod
from fieldstack.review.server import serve

ROOT = Path(__file__).parent

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "fieldstack.toml"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    serve(cfg_mod.load(a.config), a.host, a.port)

"""
Review server. Standard library only.

  python review.py --config fieldstack.toml --port 8787
  open http://127.0.0.1:8787/

API
  GET  /api/drafts                       list
  GET  /api/drafts/{id}                  draft without snapshot
  PUT  /api/drafts/{id}                  {edits, edit_seconds}
  POST /api/drafts/{id}/regenerate       fresh narrative from the stored snapshot (returns, does not overwrite)
  POST /api/drafts/{id}/approve          render final, deliver, lock
  GET  /api/drafts/{id}/preview.html     render current edits
  GET  /api/drafts/{id}/final.html       approved file
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..config import TenantConfig
from . import drafts

APP = Path(__file__).parent / "app.html"
ROUTE = re.compile(r"^/api/drafts/([A-Za-z0-9._-]+)(?:/(regenerate|approve|preview\.html|final\.html))?$")


def make_handler(cfg: TenantConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fieldstack/0.1"

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, default=str).encode("utf-8"))

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

        def log_message(self, fmt, *args):  # quieter
            if "/api/" in (args[0] if args else ""):
                super().log_message(fmt, *args)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, APP.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/drafts":
                return self._json(200, drafts.list_drafts(cfg))
            m = ROUTE.match(path)
            if not m:
                return self._json(404, {"error": "not found"})
            did, action = m.group(1), m.group(2)
            if action is None:
                d = drafts.load_draft(cfg, did)
                return self._json(200, d) if d else self._json(404, {"error": "no such draft"})
            if action == "preview.html":
                html, _ = drafts.render_current(cfg, did)
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if action == "final.html":
                d = drafts.load_draft(cfg, did)
                if not d or not d.get("approved_path"):
                    return self._json(404, {"error": "not approved"})
                return self._send(200, Path(d["approved_path"]).read_bytes(), "text/html; charset=utf-8")
            return self._json(405, {"error": "method"})

        def do_PUT(self):
            m = ROUTE.match(urlparse(self.path).path)
            if not m or m.group(2):
                return self._json(404, {"error": "not found"})
            body = self._body()
            try:
                d = drafts.save_draft(cfg, m.group(1), body.get("edits", {}), body.get("edit_seconds"))
            except PermissionError as e:
                return self._json(409, {"error": str(e)})
            except KeyError:
                return self._json(404, {"error": "no such draft"})
            return self._json(200, {"ok": True, "updated_at": d["updated_at"], "edit_seconds": d["edit_seconds"]})

        def do_POST(self):
            m = ROUTE.match(urlparse(self.path).path)
            if not m or not m.group(2):
                return self._json(404, {"error": "not found"})
            did, action = m.group(1), m.group(2)
            try:
                if action == "approve":
                    return self._json(200, drafts.approve_draft(cfg, did))
                if action == "regenerate":
                    return self._json(200, drafts.regenerate(cfg, did))
            except KeyError:
                return self._json(404, {"error": "no such draft"})
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            return self._json(405, {"error": "method"})

    return Handler


def serve(cfg: TenantConfig, host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(cfg))
    print(f"Fieldstack review: http://{host}:{port}/   (drafts in {drafts.drafts_dir(cfg)})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

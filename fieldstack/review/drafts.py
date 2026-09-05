"""
Draft packages on disk. One JSON file per module run, editable by the review UI.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from ..config import TenantConfig
from ..metrics import compute
from ..model import ProjectSnapshot
from ..modules import ModuleOutput
from ..narrative import Narrative
from ..render import render_html, render_markdown

SECTIONS = ("executive_summary", "progress_narrative", "open_items_commentary", "look_ahead")
SAFE = re.compile(r"[^A-Za-z0-9._-]")


def drafts_dir(cfg: TenantConfig) -> Path:
    d = cfg.resolve(cfg.drafts_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def approved_dir(cfg: TenantConfig) -> Path:
    d = cfg.resolve(cfg.approved_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _links(snap: ProjectSnapshot) -> dict[str, str]:
    m: dict[str, str] = {}
    for coll in (snap.rfis, snap.submittals, snap.change_orders, snap.daily_logs, snap.milestones, snap.budget):
        for r in coll:
            if getattr(r, "link", ""):
                m[r.ref] = r.link
    return m


def write_draft(cfg: TenantConfig, project_key: str, module_name: str, as_of: date, snap: ProjectSnapshot,
                output: ModuleOutput, sample: bool) -> Path:
    p = snap.project
    draft_id = SAFE.sub("-", output.file_stem)
    now = datetime.now().isoformat(timespec="seconds")
    nar = output.narrative
    pkg = {
        "id": draft_id, "tenant": cfg.name, "project_key": project_key, "module": module_name,
        "as_of": as_of.isoformat(), "created_at": now, "updated_at": now, "status": "draft", "sample": sample,
        "title": output.title, "project_name": p.name, "period_label": output.facts.get("period_label", ""),
        "recipients": [x for x in (p.owner, p.owners_rep, p.lender) if x],
        "people": {"px": p.project_executive, "pm": p.project_manager, "super": p.superintendent, "gc": p.gc_name},
        "sources": snap.sources, "notes": snap.notes, "links": _links(snap),
        "snapshot": snap.to_dict(), "facts": output.facts, "narrative": nar,
        "edits": {**{k: nar.get(k, "") for k in SECTIONS},
                  "owner_actions": [{"text": t, "include": True} for t in nar.get("owner_actions", [])]},
        "edit_seconds": 0, "history": [{"at": now, "event": "drafted", "by": nar.get("model") or nar.get("backend")}],
        "approved_path": None,
    }
    path = drafts_dir(cfg) / f"{draft_id}.json"
    path.write_text(json.dumps(pkg, indent=1, default=str), encoding="utf-8")
    return path


def list_drafts(cfg: TenantConfig) -> list[dict[str, Any]]:
    out = []
    for f in sorted(drafts_dir(cfg).glob("*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({k: d.get(k) for k in ("id", "title", "status", "as_of", "project_name", "period_label",
                                          "edit_seconds", "updated_at", "sample")})
    return out


def load_draft(cfg: TenantConfig, draft_id: str, with_snapshot: bool = False) -> Optional[dict[str, Any]]:
    path = drafts_dir(cfg) / f"{SAFE.sub('-', draft_id)}.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    if not with_snapshot:
        d = {k: v for k, v in d.items() if k != "snapshot"}
    return d


def save_draft(cfg: TenantConfig, draft_id: str, edits: dict[str, Any], edit_seconds: Optional[int] = None,
               event: str = "saved") -> dict[str, Any]:
    d = load_draft(cfg, draft_id, with_snapshot=True)
    if d is None:
        raise KeyError(draft_id)
    if d["status"] == "approved":
        raise PermissionError("draft is approved; edits are closed")
    for k in SECTIONS:
        if k in edits and isinstance(edits[k], str):
            d["edits"][k] = edits[k]
    if "owner_actions" in edits and isinstance(edits["owner_actions"], list):
        d["edits"]["owner_actions"] = [{"text": str(a.get("text", "")), "include": bool(a.get("include", True))}
                                       for a in edits["owner_actions"] if isinstance(a, dict)]
    if edit_seconds is not None:
        d["edit_seconds"] = max(int(edit_seconds), int(d.get("edit_seconds", 0)))
    now = datetime.now().isoformat(timespec="seconds")
    d["updated_at"] = now
    d["history"].append({"at": now, "event": event})
    (drafts_dir(cfg) / f"{d['id']}.json").write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    return {k: v for k, v in d.items() if k != "snapshot"}


def edited_narrative(d: dict[str, Any]) -> Narrative:
    e = d["edits"]
    return Narrative(
        executive_summary=e["executive_summary"], progress_narrative=e["progress_narrative"],
        open_items_commentary=e["open_items_commentary"], look_ahead=e["look_ahead"],
        owner_actions=[a["text"] for a in e["owner_actions"] if a.get("include", True) and a.get("text", "").strip()],
        backend=d["narrative"].get("backend", "unknown"), model=d["narrative"].get("model"),
    )


def render_current(cfg: TenantConfig, draft_id: str) -> tuple[str, str]:
    """Render HTML and Markdown from the draft's current edits."""
    d = load_draft(cfg, draft_id, with_snapshot=True)
    if d is None:
        raise KeyError(draft_id)
    snap = ProjectSnapshot.from_dict(d["snapshot"])
    facts = compute(snap, date.fromisoformat(d["as_of"]))
    nar = edited_narrative(d)
    return render_html(snap, facts, nar, sample=d.get("sample", True)), render_markdown(snap, facts, nar)


def approve_draft(cfg: TenantConfig, draft_id: str, deliver: bool = True) -> dict[str, Any]:
    from .. import delivery as delivery_registry
    from ..modules import ModuleOutput as MO

    d = load_draft(cfg, draft_id, with_snapshot=True)
    if d is None:
        raise KeyError(draft_id)
    if d["status"] == "approved":
        return {"status": "approved", "path": d["approved_path"], "deliveries": []}
    html, md = render_current(cfg, draft_id)
    out_dir = approved_dir(cfg)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    html_path = out_dir / f"{d['id']}-approved-{stamp}.html"
    html_path.write_text(html, encoding="utf-8")
    (out_dir / f"{d['id']}-approved-{stamp}.md").write_text(md, encoding="utf-8")

    sent: list[str] = []
    if deliver:
        nar = edited_narrative(d)
        summary = nar.executive_summary
        attention = d["facts"].get("attention", [])
        if attention:
            summary += "\n\nRequires attention:\n" + "\n".join(f"- {a}" for a in attention)
        output = MO(module=d["module"], title=d["title"], summary=summary, html=html, markdown=md,
                    facts=d["facts"], narrative=nar.to_dict(), attention=attention, file_stem=f"{d['id']}-approved")
        for dc in cfg.deliveries:
            if dc.kind == "file":
                continue  # already written to the approved directory
            try:
                sent.append(delivery_registry.build(dc.kind, dict(dc.settings)).send(output))
            except Exception as e:  # report, do not lose the approval
                sent.append(f"{dc.kind}: failed ({type(e).__name__}: {e})")

    now = datetime.now().isoformat(timespec="seconds")
    d["status"] = "approved"
    d["approved_path"] = str(html_path)
    d["updated_at"] = now
    d["history"].append({"at": now, "event": "approved", "deliveries": sent})
    (drafts_dir(cfg) / f"{d['id']}.json").write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    return {"status": "approved", "path": str(html_path), "deliveries": sent}


def regenerate(cfg: TenantConfig, draft_id: str, gateway=None) -> dict[str, Any]:
    """Re-run the narrator on the stored snapshot and return fresh sections (does not overwrite edits)."""
    from ..llm import make_gateway
    from ..narrative import write_narrative

    d = load_draft(cfg, draft_id, with_snapshot=True)
    if d is None:
        raise KeyError(draft_id)
    snap = ProjectSnapshot.from_dict(d["snapshot"])
    facts = compute(snap, date.fromisoformat(d["as_of"]))
    gw = gateway or make_gateway(cfg.llm_provider, cfg.llm_model)
    prior = ""
    proj = cfg.project(d["project_key"])
    if proj.prior_report:
        pp = cfg.resolve(proj.prior_report)
        prior = pp.read_text(encoding="utf-8") if pp.exists() else ""
    nar = write_narrative(facts, gw, prior)
    return nar.to_dict()

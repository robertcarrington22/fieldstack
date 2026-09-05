"""
Renders the Owner Report as a single self-contained HTML file (print-friendly, both
themes) and as Markdown. Citations like (RFI-041) become links to the source record
when a link is known.
"""
from __future__ import annotations

import html
import re
from datetime import date

from .metrics import ReportFacts
from .model import ProjectSnapshot
from .narrative import Narrative

CITE_RE = re.compile(r"\((?:RFI|SUB|PCO|CO|LOG|MS|SOV)-[A-Za-z0-9.\-]+(?:,\s*(?:RFI|SUB|PCO|CO|LOG|MS|SOV)-[A-Za-z0-9.\-]+)*\)")


def _money(n: float) -> str:
    return f"${n:,.0f}"


def _md(day: date) -> str:
    return day.strftime("%m/%d")


def _link_map(snap: ProjectSnapshot) -> dict[str, str]:
    m = {}
    for r in snap.rfis:
        m[r.ref] = r.link
    for s in snap.submittals:
        m[s.ref] = s.link
    for l in snap.daily_logs:
        m[l.ref] = l.link
    return m


def _cite_html(text: str, links: dict[str, str]) -> str:
    def repl(match):
        inner = match.group(0)[1:-1]
        parts = []
        for ref in [x.strip() for x in inner.split(",")]:
            href = links.get(ref)
            parts.append(f'<a class="cite" href="{html.escape(href)}" target="_blank" rel="noopener">{html.escape(ref)}</a>'
                         if href else f'<span class="cite">{html.escape(ref)}</span>')
        return "(" + ", ".join(parts) + ")"
    return CITE_RE.sub(repl, html.escape(text))


def _paras(text: str, links: dict[str, str]) -> str:
    return "".join(f"<p>{_cite_html(p.strip(), links)}</p>" for p in text.split("\n\n") if p.strip())


def render_html(snap: ProjectSnapshot, facts: ReportFacts, nar: Narrative, sample: bool = True) -> str:
    p = snap.project
    links = _link_map(snap)
    pct = facts.percent_complete_sov * 100
    var_word = "under" if facts.projected_variance >= 0 else "over"
    sched_word = (f"{facts.schedule_variance_days} days behind baseline" if facts.schedule_variance_days > 0
                  else "on baseline")

    def item_rows(items, show_amount=False):
        rows = []
        for it in items:
            amt = f"<td class='num'>{_money(it.amount) if it.amount else 'TBD'}</td>" if show_amount else ""
            flags = " ".join(x for x in [
                "<span class='flag sched'>schedule</span>" if it.schedule_impact else "",
                "<span class='flag cost'>cost</span>" if it.cost_impact and it.kind != "change_order" else ""] if x)
            ref = (f"<a href='{html.escape(it.link)}' target='_blank' rel='noopener'>{html.escape(it.ref)}</a>"
                   if it.link else html.escape(it.ref))
            rows.append(
                f"<tr><td class='ref'>{ref}</td><td>{html.escape(it.title)} {flags}</td>"
                f"<td>{html.escape(it.ball_in_court)}</td><td class='num'>{_md(it.opened)}</td>"
                f"<td class='num'>{_md(it.due) if it.due else '—'}</td>"
                f"<td class='num{' bad' if it.days_overdue_bdays > 0 else ''}'>{it.days_overdue_bdays}</td>{amt}</tr>")
        return "".join(rows) or "<tr><td colspan='7' class='muted'>None</td></tr>"

    budget_rows = "".join(
        f"<tr><td class='ref'>{b['code']}</td><td>{html.escape(b['description'])}</td>"
        f"<td class='num'>{_money(b['revised'])}</td><td class='num'>{_money(b['committed'])}</td>"
        f"<td class='num'>{_money(b['cost_to_date'])}</td><td class='num'>{_money(b['billed_to_date'])}</td>"
        f"<td class='num'>{b['percent_complete'] * 100:.0f}%</td></tr>"
        for b in facts.budget_lines)
    ms_rows = "".join(
        f"<tr><td class='ref'>{m['ref']}</td><td>{html.escape(m['name'])}</td><td class='num'>{m['baseline'][5:].replace('-', '/')}</td>"
        f"<td class='num'>{(m['actual'] or m['current'])[5:].replace('-', '/')}</td>"
        f"<td class='num{' bad' if m['variance_days'] > 0 else ''}'>{m['variance_days']:+d}</td>"
        f"<td><span class='pill {m['status'].replace(' ', '-')}'>{m['status']}</span></td></tr>"
        for m in facts.milestones)
    safety_rows = "".join(f"<li>{_md(date.fromisoformat(s['date']))}: {html.escape(s['description'])} ({html.escape(s['ref'])})</li>"
                          for s in facts.safety_events) or "<li>No recordable incidents.</li>"
    weather_rows = "".join(f"<li>{html.escape(w)}</li>" for w in facts.weather_days) or "<li>No weather delays.</li>"
    actions = "".join(f"<li>{_cite_html(a, links)}</li>" for a in nar.owner_actions)
    attention = "".join(f"<li>{_cite_html(a, links)}</li>" for a in facts.attention)

    banner = ("<div class='banner'>SAMPLE DATA. This report was generated from invented fixture data for a "
              "fictional project. No real owner, lender, contractor, or job is described.</div>") if sample else ""
    backend_note = (f"Narrative written by {html.escape(nar.model or 'Claude')}." if nar.backend == "claude"
                    else "Narrative is placeholder text from the mock writer; set ANTHROPIC_API_KEY to have Claude write it.")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(p.name)} Owner Report {html.escape(facts.period_label)}</title>
<style>
:root{{--bg:#FAFAF7;--ink:#1B1F1D;--muted:#5F6662;--rule:#D8DAD4;--accent:#B9470E;--bad:#8A2F2F;--ok:#2E7D4F;--soft:#F0F0EB;--cite:#2F5D7C}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171A18;--ink:#ECEDE9;--muted:#A3A8A2;--rule:#2F3430;--accent:#F2793A;--bad:#E08484;--ok:#6CC08E;--soft:#202421;--cite:#7FB0D3}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans","Segoe UI",Helvetica,Arial,sans-serif}}
.page{{max-width:900px;margin:0 auto;padding:32px 24px 80px}}
.banner{{background:var(--accent);color:#fff;font-weight:600;padding:10px 14px;margin-bottom:20px;letter-spacing:.02em}}
header{{border:1.5px solid var(--ink);padding:20px 22px;margin-bottom:28px}}
header .k{{font:11px/1.4 "IBM Plex Mono",Consolas,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
h1{{font:700 34px/1.05 "Barlow Semi Condensed","Arial Narrow",sans-serif;margin:4px 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}}.grid div{{border-top:1px solid var(--rule);padding-top:6px;font-size:13px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--rule);margin:0 0 28px}}
.kpis div{{padding:12px 14px;border-right:1px solid var(--rule)}}.kpis div:last-child{{border-right:0}}
.kpis .v{{font:700 26px/1 "Barlow Semi Condensed",sans-serif;margin-top:4px}}.kpis .k{{font:11px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}}
h2{{font:600 22px/1.1 "Barlow Semi Condensed",sans-serif;margin:32px 0 10px;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}}
h3{{font:600 16px/1.2 "Barlow Semi Condensed",sans-serif;margin:18px 0 6px}}
p{{margin:0 0 10px;max-width:70ch}}
.cite{{font:12px "IBM Plex Mono",monospace;color:var(--cite);text-decoration:none}}a.cite:hover{{text-decoration:underline}}
.attention{{border-left:3px solid var(--accent);background:var(--soft);padding:12px 16px;margin:12px 0 4px}}
.attention ul,.actions ul{{margin:0;padding-left:18px}}.attention li,.actions li{{margin-bottom:6px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0 16px}}th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--rule);vertical-align:top}}
th{{font:11px "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:500}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace;font-size:12.5px}}td.ref{{font-family:"IBM Plex Mono",monospace;font-size:12.5px;white-space:nowrap}}
td.bad{{color:var(--bad);font-weight:600}}.muted{{color:var(--muted)}}
.flag{{font:10px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.08em;padding:1px 5px;border:1px solid currentColor;margin-left:4px}}.flag.sched{{color:var(--bad)}}.flag.cost{{color:var(--accent)}}
.pill{{font:10.5px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.08em;padding:2px 6px;border:1px solid currentColor}}.pill.complete{{color:var(--ok)}}.pill.slipping{{color:var(--bad)}}.pill.on-track{{color:var(--muted)}}
.tw{{overflow-x:auto}}footer{{margin-top:40px;font-size:12px;color:var(--muted);border-top:1px solid var(--rule);padding-top:10px}}
@media print{{.banner{{display:none}}body{{font-size:12px}}h2{{page-break-after:avoid}}}}
@media (max-width:640px){{.grid,.kpis{{grid-template-columns:1fr 1fr}}}}
</style></head><body><div class="page">
{banner}
<header>
  <div class="k">Monthly Owner Report · {html.escape(facts.period_label)}</div>
  <h1>{html.escape(p.name)}</h1>
  <div>{html.escape(p.address)} · Project {html.escape(p.number)} · {html.escape(p.description)}</div>
  <div class="grid">
    <div><div class="k">Prepared for</div>{html.escape(p.owner)}<br>{html.escape(p.owners_rep)}<br>{html.escape(p.lender)}</div>
    <div><div class="k">Prepared by</div>{html.escape(p.gc_name)}<br>{html.escape(p.project_executive)}, PX<br>{html.escape(p.project_manager)}, PM</div>
    <div><div class="k">Contract</div>{_money(p.contract_value)} original<br>{_money(facts.revised_contract)} revised<br>NTP {_md(p.start_date)}</div>
    <div><div class="k">Report date</div>{facts.as_of.strftime('%m/%d/%Y')}<br>Period {_md(snap.period_start)} to {_md(snap.period_end)}</div>
  </div>
</header>

<div class="kpis">
  <div><div class="k">Complete (SOV)</div><div class="v">{pct:.0f}%</div></div>
  <div><div class="k">Cost to date</div><div class="v">{_money(facts.cost_to_date)}</div></div>
  <div><div class="k">Projected at completion</div><div class="v">{_money(facts.projected_cost)}</div><div class="muted" style="font-size:12px">{_money(abs(facts.projected_variance))} {var_word}</div></div>
  <div><div class="k">Substantial completion</div><div class="v">{facts.milestones[-1]['current'][5:].replace('-', '/')}/{facts.milestones[-1]['current'][2:4]}</div><div class="muted" style="font-size:12px">{sched_word}</div></div>
</div>

<h2>Executive summary</h2>
{_paras(nar.executive_summary, links)}
<div class="attention"><strong>Requires attention</strong><ul>{attention or '<li>Nothing overdue.</li>'}</ul></div>

<h2>Owner decisions requested</h2>
<div class="actions"><ul>{actions or '<li>None this period.</li>'}</ul></div>

<h2>Progress this period</h2>
{_paras(nar.progress_narrative, links)}
<h3>Field summary</h3>
<p>{facts.working_days} working days. Average {facts.avg_headcount:.0f} workers on site, peak {facts.peak_headcount}. {facts.weather_delay_hours:g} hours lost to weather.</p>
<h3>Weather</h3><ul>{weather_rows}</ul>
<h3>Safety</h3><ul>{safety_rows}</ul>

<h2>Open items</h2>
{_paras(nar.open_items_commentary, links)}
<h3>RFIs past response date <span class="muted">({facts.rfis_opened} opened, {facts.rfis_closed} closed this period; {facts.rfis_open_total} open; average response {facts.rfi_avg_response_bdays if facts.rfi_avg_response_bdays is not None else '—'} business days against a {p.rfi_window_bdays}-day window)</span></h3>
<div class="tw"><table><thead><tr><th>Ref</th><th>Subject</th><th>Ball in court</th><th class="num">Opened</th><th class="num">Due</th><th class="num">Bdays over</th></tr></thead><tbody>{item_rows(facts.rfis_overdue)}</tbody></table></div>
<h3>Submittals past review date</h3>
<div class="tw"><table><thead><tr><th>Ref</th><th>Title</th><th>Ball in court</th><th class="num">Received</th><th class="num">Due</th><th class="num">Bdays over</th></tr></thead><tbody>{item_rows(facts.submittals_overdue)}</tbody></table></div>
<h3>Change orders pending <span class="muted">({_money(facts.pending_changes)} priced and pending)</span></h3>
<div class="tw"><table><thead><tr><th>Ref</th><th>Title</th><th>With</th><th class="num">Since</th><th class="num">Due</th><th class="num">Bdays</th><th class="num">Amount</th></tr></thead><tbody>{item_rows(facts.change_orders_pending, show_amount=True)}</tbody></table></div>

<h2>Schedule</h2>
<div class="tw"><table><thead><tr><th>Ref</th><th>Milestone</th><th class="num">Baseline</th><th class="num">Current</th><th class="num">Var. days</th><th>Status</th></tr></thead><tbody>{ms_rows}</tbody></table></div>

<h2>Cost</h2>
<div class="tw"><table><thead><tr><th>Code</th><th>Schedule of values</th><th class="num">Revised budget</th><th class="num">Committed</th><th class="num">Cost to date</th><th class="num">Billed to date</th><th class="num">Complete</th></tr></thead><tbody>{budget_rows}
<tr><td></td><td><strong>Total</strong></td><td class="num"><strong>{_money(sum(b['revised'] for b in facts.budget_lines))}</strong></td><td class="num"><strong>{_money(facts.committed)}</strong></td><td class="num"><strong>{_money(facts.cost_to_date)}</strong></td><td class="num"><strong>{_money(facts.billed_to_date)}</strong></td><td class="num"><strong>{pct:.0f}%</strong></td></tr>
</tbody></table></div>
<p class="muted" style="font-size:13px">Approved changes to date {_money(facts.approved_changes)}. Projected cost uses committed value where bought out and revised budget where not. Percent complete is dollar-weighted by schedule of values.</p>

<h2>Look ahead</h2>
{_paras(nar.look_ahead, links)}

<footer>Generated by Fieldstack as of {facts.as_of.isoformat()}. Sources: {html.escape(", ".join(f"{k} from {v}" for k, v in snap.sources.items()) or "Procore")}. Every figure above is computed from the source record cited; the narrative is drafted from those figures only. {backend_note}{(" Notes: " + html.escape("; ".join(snap.notes))) if snap.notes else ""}</footer>
</div></body></html>"""


def render_markdown(snap: ProjectSnapshot, facts: ReportFacts, nar: Narrative) -> str:
    p = snap.project
    lines = [f"# {p.name} — Owner Report, {facts.period_label}", "",
             f"Prepared by {p.gc_name} for {p.owner}, {p.owners_rep}, {p.lender}. Report date {facts.as_of.isoformat()}.", "",
             "## Executive summary", nar.executive_summary, ""]
    if facts.attention:
        lines += ["**Requires attention**"] + [f"- {a}" for a in facts.attention] + [""]
    lines += ["## Owner decisions requested"] + [f"- {a}" for a in nar.owner_actions] + ["",
              "## Progress this period", nar.progress_narrative, "",
              f"{facts.working_days} working days; average {facts.avg_headcount:.0f} workers, peak {facts.peak_headcount}; {facts.weather_delay_hours:g} weather hours lost.", "",
              "## Open items", nar.open_items_commentary, "",
              "| Ref | Item | With | Bdays over |", "|---|---|---|---|"]
    for it in facts.rfis_overdue + facts.submittals_overdue + facts.change_orders_pending:
        lines.append(f"| {it.ref} | {it.title} | {it.ball_in_court} | {it.days_overdue_bdays} |")
    lines += ["", "## Schedule", "| Milestone | Baseline | Current | Var |", "|---|---|---|---|"]
    for m in facts.milestones:
        lines.append(f"| {m['name']} | {m['baseline']} | {m['actual'] or m['current']} | {m['variance_days']:+d} |")
    lines += ["", "## Cost",
              f"Cost to date {_money(facts.cost_to_date)} of revised contract {_money(facts.revised_contract)}; projected {_money(facts.projected_cost)}.", "",
              "## Look ahead", nar.look_ahead, ""]
    return "\n".join(lines)

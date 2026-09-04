"""
Narrative layer.

Takes ReportFacts (already computed, already cited) and writes the prose sections of
the Owner Report in the GC's voice. Two backends:

  ClaudeNarrator   calls the Claude API with structured output so every section comes
                   back as a JSON object the renderer can trust. Uses the facts as the
                   only source of truth and must cite refs inline, e.g. "(RFI-041)".
  MockNarrator     template prose from the same facts. Used when no credentials are
                   present so the pipeline still runs end to end.

Pick with make_narrator(). If ANTHROPIC_API_KEY / an `ant auth login` profile is
present, Claude is used; otherwise the mock, with a visible note in the report.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .metrics import ReportFacts

MODEL = "claude-opus-5"

SECTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string",
                              "description": "3 to 5 sentences. Status, money, schedule, the one thing the owner must act on."},
        "progress_narrative": {"type": "string",
                               "description": "What was built this period, by system, in past tense. 1 to 3 short paragraphs."},
        "open_items_commentary": {"type": "string",
                                  "description": "Why each overdue RFI, submittal, and pending change matters and who holds it."},
        "look_ahead": {"type": "string",
                       "description": "Next period's work and the decisions the owner or design team must make, with dates."},
        "owner_actions": {"type": "array", "items": {"type": "string"},
                          "description": "Each a single sentence asking the owner for one specific thing, with the ref."},
    },
    "required": ["executive_summary", "progress_narrative", "open_items_commentary", "look_ahead", "owner_actions"],
    "additionalProperties": False,
}

SYSTEM = """You write the monthly owner report for a general contractor. The audience is the owner, the owner's representative, and the construction lender. They will forward it with a draw request without editing it.

Rules:
- Use only the facts in the JSON you are given. Do not invent numbers, dates, names, or events. If a fact is missing, say it is not yet available.
- Cite the source record for every claim that refers to a specific item, in parentheses after the sentence: (RFI-041), (SUB-118.R2), (PCO-007), (LOG-2026-08-14), (MS-4), (SOV-03-000). A sentence with a number in it needs a citation.
- Short declarative sentences. No adjectives of praise or blame. Never use "unfortunately", "excited", "pleased", "robust", or "significant".
- Dollar figures to the nearest hundred. Dates as MM/DD.
- Match the voice of the prior report excerpt if one is provided.
- Attribute delay to the record, not to a person: "with the Structural Engineer of Record since 08/05", not "the engineer is late".
- Ask for owner decisions plainly and give the date by which the decision is needed."""


@dataclass
class Narrative:
    executive_summary: str
    progress_narrative: str
    open_items_commentary: str
    look_ahead: str
    owner_actions: list[str]
    backend: str
    model: Optional[str] = None
    usage: Optional[dict] = None


def _facts_for_prompt(facts: ReportFacts) -> dict:
    d = facts.to_dict()
    d["as_of"] = facts.as_of.isoformat()
    # Trim the daily work log to the substantive entries to keep the prompt lean.
    d["work_log"] = [w for w in d["work_log"] if "per plan" not in w["work"]]
    return d


class ClaudeNarrator:
    def __init__(self, model: str = MODEL):
        import anthropic  # imported here so the mock path has no SDK dependency
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def write(self, facts: ReportFacts, prior_excerpt: str = "") -> Narrative:
        user = (
            "Write the narrative sections of the owner report from these facts.\n\n"
            f"<facts>\n{json.dumps(_facts_for_prompt(facts), indent=1, default=str)}\n</facts>\n"
        )
        if prior_excerpt:
            user += f"\n<prior_report_excerpt>\n{prior_excerpt}\n</prior_report_excerpt>\n"
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": SECTIONS_SCHEMA}},
            ) as stream:
                response = stream.get_final_message()
        except self.anthropic.AuthenticationError:
            raise RuntimeError("Claude credentials rejected. Set ANTHROPIC_API_KEY or run `ant auth login`.")
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request: "
                               f"{getattr(response.stop_details, 'explanation', '') or 'no detail'}")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
                 "cache_read_input_tokens": response.usage.cache_read_input_tokens}
        return Narrative(backend="claude", model=response.model, usage=usage, **data)


class MockNarrator:
    """Template prose from the facts. Deterministic, cited, and obviously a placeholder."""

    def write(self, facts: ReportFacts, prior_excerpt: str = "") -> Narrative:
        f = facts
        pct = f.percent_complete_sov * 100
        sched = (f"{abs(f.schedule_variance_days)} days behind baseline" if f.schedule_variance_days > 0
                 else "on baseline")
        top_rfi = f.rfis_overdue[0] if f.rfis_overdue else None
        top_sub = next((s for s in f.submittals_critical_open if s.days_overdue_bdays > 0), None)
        top_co = next((c for c in f.change_orders_pending if c.days_overdue_bdays >= 10 and c.amount), None)

        exec_lines = [
            f"{f.project_name} is {pct:.0f} percent complete by schedule of values as of {f.as_of.strftime('%m/%d')} (SOV-01-000 through SOV-99-000).",
            f"Cost to date is ${f.cost_to_date:,.0f} against a revised contract of ${f.revised_contract:,.0f}; projected cost at completion is ${f.projected_cost:,.0f}, "
            f"{'under' if f.projected_variance >= 0 else 'over'} budget by ${abs(f.projected_variance):,.0f}.",
            f"Substantial Completion is forecast {sched} (MS-8).",
        ]
        if top_rfi:
            exec_lines.append(f"The item requiring owner attention is {top_rfi.ref}, open {top_rfi.days_overdue_bdays} business days past its response date with {top_rfi.ball_in_court} and carrying schedule impact ({top_rfi.ref}).")

        first_log = f.work_log[0]["ref"] if f.work_log else "LOG"
        last_log = f.work_log[-1]["ref"] if f.work_log else "LOG"
        ms3 = next((m for m in f.milestones if m["ref"] == "MS-3"), None)
        ms3_date = ms3["current"][5:].replace("-", "/") if ms3 else "the next formwork milestone"
        prog = [f"The site averaged {f.avg_headcount:.0f} workers per day across {f.working_days} working days, peaking at {f.peak_headcount} ({first_log} through {last_log})."]
        for w in f.work_log:
            if any(k in w["work"] for k in ("pour", "started", "complete")):
                prog.append(f"{w['date'][5:].replace('-', '/')}: {w['work']} ({w['ref']}).")
        if f.weather_delay_hours:
            prog.append(f"Weather cost {f.weather_delay_hours:g} hours across {len(f.weather_days)} days ({', '.join(x.split(':')[0] for x in f.weather_days)}).")

        oi = []
        for r in f.rfis_overdue:
            oi.append(f"{r.ref} {r.title} has been with {r.ball_in_court} since {r.opened.strftime('%m/%d')}, {r.days_overdue_bdays} business days past the response date ({r.ref}).")
        for s in f.submittals_overdue:
            oi.append(f"{s.ref} {s.title} is {s.days_overdue_bdays} business days past its review date with {s.ball_in_court}{' and is schedule-critical' if s.schedule_impact else ''} ({s.ref}).")
        for c in f.change_orders_pending:
            amt = f"${c.amount:,.0f}" if c.amount else "not yet priced"
            oi.append(f"{c.ref} {c.title}, {amt}, has been {c.note.split('.')[0]} for {c.days_overdue_bdays} business days ({c.ref}).")

        la = [f"Next period continues superstructure and MEP rough-in per the current schedule (MS-3, MS-4)."]
        if top_rfi:
            la.append(f"A response to {top_rfi.ref} is needed before the next formwork milestone to hold the current forecast (MS-3).")
        if top_sub:
            la.append(f"Approval of {top_sub.ref} is needed to release fabrication and hold the watertight date (MS-6).")

        actions = []
        if top_co:
            actions.append(f"Sign {top_co.ref} (${top_co.amount:,.0f}) so the work can be released; it has been with the owner {top_co.days_overdue_bdays} business days ({top_co.ref}).")
        if top_rfi:
            actions.append(f"Direct the design team to answer {top_rfi.ref} before the {ms3_date} formwork start so the current forecast holds ({top_rfi.ref}, MS-3).")
        if top_sub:
            actions.append(f"Ask the architect to return {top_sub.ref} this week; fabrication lead time runs to the watertight milestone ({top_sub.ref}, MS-6).")

        return Narrative(
            executive_summary=" ".join(exec_lines), progress_narrative="\n\n".join(prog),
            open_items_commentary="\n\n".join(oi) or "No overdue items.", look_ahead=" ".join(la),
            owner_actions=actions, backend="mock",
        )


def credentials_present() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "anthropic"
    return cfg.exists() and any(cfg.iterdir())


def make_narrator(force: Optional[str] = None):
    """force: 'claude' | 'mock' | None (auto)."""
    if force == "mock" or (force is None and not credentials_present()):
        return MockNarrator()
    return ClaudeNarrator()

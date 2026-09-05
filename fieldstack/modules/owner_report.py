"""
Owner Report module: the wedge product. Monthly report for the owner, owner's rep,
and lender, assembled from whatever sources the tenant has connected.
"""
from __future__ import annotations

from ..connectors import Capability
from ..metrics import compute
from ..model import ProjectSnapshot
from ..narrative import write_narrative
from ..render import render_html, render_markdown
from . import ModuleOutput, RunContext, register_module


@register_module("owner_report")
class OwnerReport:
    requires = frozenset({Capability.PROJECT, Capability.RFIS, Capability.SUBMITTALS,
                          Capability.CHANGE_ORDERS, Capability.BUDGET, Capability.DAILY_LOGS})

    def run(self, snapshot: ProjectSnapshot, ctx: RunContext) -> ModuleOutput:
        facts = compute(snapshot, ctx.as_of)
        narrative = write_narrative(facts, ctx.llm, ctx.prior_report_excerpt)
        sample = ctx.extra.get("sample", True)
        html = render_html(snapshot, facts, narrative, sample=sample)
        md = render_markdown(snapshot, facts, narrative)
        period = snapshot.period_start.strftime("%Y-%m")
        stem = f"{snapshot.project.name.lower().replace(' ', '-')}-{period}"
        summary = narrative.executive_summary
        if facts.attention:
            summary += "\n\nRequires attention:\n" + "\n".join(f"- {a}" for a in facts.attention)
        return ModuleOutput(
            module=self.name, title=f"{snapshot.project.name} Owner Report, {facts.period_label}",
            summary=summary, html=html, markdown=md, facts=facts.to_dict(), narrative=narrative.to_dict(),
            attention=facts.attention, file_stem=stem,
        )

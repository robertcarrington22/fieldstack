# Fieldstack architecture

Six layers, top to bottom, matching the concept brief. Every module is a set of
computations, prompts, and scheduled jobs against the shared layers, never a separate
application.

```
 sources      Procore · Autodesk Build · Sage 300 CRE (hh2) · Vista · P6 / MS Project · CSV exports · (email, SMS, photos)
                │
 connectors   one file per source; declares capabilities; returns a Partial          fieldstack/connectors/
                │
 snapshot     SnapshotBuilder merges Partials by capability in precedence order       fieldstack/snapshot.py
                │            ┌──────────────────────────────────────────────────┐
 data         ProjectSnapshot (unified model, every record has ref + source + link)   fieldstack/model.py
              SnapshotStore keeps every pull for history                            fieldstack/store.py
                │            └──────────────────────────────────────────────────┘
 modules      OwnerReport today; InvoiceMatch, ClaimsGuard, MarginWatch, Lookahead next   fieldstack/modules/
                │  metrics (deterministic) → narrative (LLM gateway, structured) → render
 delivery     file · Slack/Teams webhook · email                                     fieldstack/delivery/
```

Configuration is one TOML file per tenant (`fieldstack.toml`). The job runner
(`fieldstack/jobs.py`) is the only orchestration code: build connectors, merge, store,
run module, deliver. A cron entry, a queue worker, or the CLI all call the same function.

## Connectors

A connector declares what it can provide and returns only that:

```python
@register("vista")
class VistaConnector:
    capabilities = frozenset({Capability.BUDGET})
    def __init__(self, name, settings): ...
    def fetch(self, project_ref, period_start, period_end) -> Partial: ...
    def health(self) -> tuple[bool, str]: ...
```

Capabilities: `project`, `rfis`, `submittals`, `change_orders`, `budget`, `milestones`,
`daily_logs`. Adding a capability (say `invoices` for Invoice Match) means adding a
field to `Partial`, a list to `ProjectSnapshot`, and a value to the enum; existing
connectors are unaffected because absent fields are `None`.

| kind | status | provides |
|---|---|---|
| `procore` | mock works; live written, untested | everything |
| `csv_ledger` | works | budget, from any ERP export |
| `csv_schedule` | works | milestones, from P6 / MS Project export |
| `autodesk_build` | declared; endpoints documented | project, rfis, submittals, budget, milestones |
| `hh2` | declared | budget (Sage 300 CRE, Sage 100) |

## Merge rules

For each capability, the first connector in precedence order that returns data wins.
Precedence defaults to config order and is overridable per capability. The sample
tenant sends dollars to the ledger and dates to the scheduler:

```toml
[precedence]
budget = ["ledger", "procore"]
milestones = ["schedule", "procore"]
```

A connector that is unhealthy, raises, or is not yet implemented is skipped with a
note. The note lands in the report footer. A module that needs a capability nobody
supplied is refused before any LLM call is made.

## Data model

Every record carries `ref` (the citation id), `source` (connector name), and `link`
(URL back to the source system). Refs are stable across sources: `SOV-03-000` is the
same cost code whether it came from Procore or Sage, so a module can join field data
and dollars on the same axis, which is the point of the shared layer.

`ProjectSnapshot.to_dict()` / `from_dict()` round-trip through JSON, which is how the
store persists them and how a future API would serve them.

## Modules

```python
@register_module("invoice_match")
class InvoiceMatch:
    requires = frozenset({Capability.BUDGET, Capability.CHANGE_ORDERS, Capability.INVOICES})
    def run(self, snapshot, ctx: RunContext) -> ModuleOutput: ...
```

`RunContext` carries the tenant, the as-of date, the LLM gateway, and the prior
report excerpt for voice matching. `ModuleOutput` carries html, markdown, facts,
narrative, an attention list, and a one-paragraph summary, so every delivery channel
works for every module.

Inside a module the discipline is fixed: **metrics compute, the model writes.**
Anything a reader could dispute (aging, dollars, percents, dates) comes from plain
Python. The narrative prompt receives those facts as JSON, is told to invent nothing,
and must cite a ref for every claim. The renderer turns refs into links.

## LLM gateway

`fieldstack/llm.py`. One `structured()` call: system prompt (cached), user prompt,
JSON schema, purpose tag. Claude Opus 5 with adaptive thinking by default; a mock
that returns `None` so callers fall back to templates. Usage is recorded per call and
stored with the module run. Model choice per task is a config change, not a code change.

## Store

SQLite in the prototype (`out/fieldstack.sqlite`), two tables: `snapshots` (every pull,
full payload) and `module_runs` (facts, provider, tokens). Margin Watch's fade
detection and the WIP forecast read history from here. Postgres keeps the same
interface; add pgvector alongside when Docs Copilot needs a document index.

## Review

`fieldstack/review/`. The job runner writes a draft package per run (`out/drafts/*.json`:
snapshot, facts, narrative, links, edits, history). `server.py` is a standard-library HTTP
server exposing the package as a small JSON API and serving `app.html`, the editor.
`drafts.py` owns the rules: edits are stored separately from the generated narrative so
Reset always works; approval re-runs `metrics.compute` on the stored snapshot and renders
through the same `render_html` as the pipeline, so what is sent is exactly what the numbers
say; an approved draft is locked. Regenerate calls the narrator again on the stored snapshot
and returns text without overwriting edits.

The editor is one HTML file with no build step. Citations are non-editable chips inside
`contenteditable` blocks and serialize back to `(REF)` text, so the approval validator can
check every citation against the facts index and warn on unknown refs or uncited numbers.

## Delivery

`file`, `webhook` (Slack and Teams both accept `{"text": ...}`), `email` (SMTP).
Nothing posts back to a source system. The approval gate is a person opening the report.

## What is deliberately not here yet

- Document index (page-level chunks, embeddings). Needed by Docs Copilot, not by the wedge.
- Write-back to any source system. Every module is read-only until a customer asks and an approval step exists.
- A web UI. Reports are static HTML by design; the PX edits in their editor of choice.
- Scheduling. `jobs.run_module` is what a nightly cron calls; the cron itself is the deployment's job.

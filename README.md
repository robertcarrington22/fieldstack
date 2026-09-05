# Fieldstack

An AI operating layer for mid-size general contractors. First module: the **Owner Report**,
the monthly report a project executive sends to the owner, owner's rep, and construction
lender, assembled from Procore, the accounting system, and the schedule. Every number is
computed in code; the model writes the prose around them and cites the record behind
every claim.

Demo site: https://robertcarrington22.github.io/fieldstack/ · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## Run it

```bash
pip install -r requirements.txt
python run.py --as-of 2026-09-04                 # sample tenant, mock Procore + CSV ledger + CSV schedule
python run.py --as-of 2026-09-04 --llm claude    # Claude writes the narrative (ANTHROPIC_API_KEY or `ant auth login`)
python run.py --list                             # connectors and modules available
python -m unittest discover -s tests -v          # 8 tests
```

Output lands in `out/`: HTML report, Markdown, computed facts as JSON, a draft package for
the review screen, and a SQLite store of every snapshot and run.

## Review screen

```bash
python review.py                                 # http://127.0.0.1:8787/
```

The one screen a project executive touches. Each draft the pipeline produces opens as an
editor: the narrative sections are editable with citations kept as chips, the left rail shows
the computed record behind every citation in the section you are in (and flags any citation
that matches no record), owner decisions are a checklist, the right rail holds the numbers.
Save is automatic. Preview renders the current edits through the real renderer. Approve
locks the draft, writes the final report to `out/approved/`, and runs the tenant's webhook
and email deliveries. Nothing goes to the owner before that click.

## How a tenant is wired

One TOML file per customer. Connectors declare what they provide; precedence says who
wins when two sources overlap; modules declare what they need.

```toml
[[connectors]]
name = "procore"
kind = "procore"
mode = "live"
token = "${PROCORE_TOKEN}"
company_id = 1234

[[connectors]]
name = "ledger"
kind = "csv_ledger"          # or "hh2" once the customer grants access
path = "exports/sage_jobcost.csv"

[precedence]
budget = ["ledger", "procore"]

[[projects]]
key = "tower"
ids = { procore = 5678, ledger = "24-101" }
```

See [fieldstack.toml](fieldstack.toml) for the full sample and [ARCHITECTURE.md](ARCHITECTURE.md)
for how to add a connector, a capability, a module, or a delivery channel.

## Layout

```
fieldstack.toml            sample tenant config
run.py                     CLI
fieldstack/
  model.py                 unified data model; every record has ref, source, link; JSON round-trip
  connectors/              procore (mock + live), csv_ledger, csv_schedule, autodesk_build (declared), hh2 (declared)
  snapshot.py              SnapshotBuilder: merge Partials by capability with precedence
  store.py                 SQLite snapshot and run history
  llm.py                   LLM gateway: Claude (structured output, adaptive thinking) or mock
  metrics.py               deterministic facts for the Owner Report
  narrative.py             prompt, schema, and template fallback for the Owner Report
  render.py                HTML and Markdown
  modules/                 owner_report; registry for the next modules
  delivery/                file, webhook (Slack/Teams), email
  jobs.py                  run_module(): connectors -> snapshot -> store -> module -> delivery
mock/                      fixtures for the fictional Bergen Street Apartments job
docs/                      GitHub Pages demo site
tests/                     unittest suite
```

## What a pilot needs from the customer

- A Procore API token with read scope on one project.
- The last two owner reports, so the narrator matches their voice.
- A job-cost export from Sage or Vista (CSV) until an hh2 connection is approved.
- The contract's RFI and submittal response windows in business days.

## Known gaps

- The live Procore client has not run against a real tenant. Budget views and daily log sub-resources will need field mapping.
- Autodesk Build and hh2 connectors are declared with documented endpoints, not implemented.
- Percent complete is dollar-weighted from budget line `percent_complete`; a real deployment should take it from the pay application schedule of values.

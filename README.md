# Fieldstack — Owner Report prototype

Generates a monthly owner-and-lender-facing report for a general contractor from Procore
records. Numbers are computed deterministically in Python; Claude writes the prose around
them and must cite the source record for every claim.

This is the wedge product from the Fieldstack concept brief, repositioned per the
Sept 4, 2026 wedge review: not an internal daily digest (Procore Helix does that), but the
report a project executive sends to the owner, owner's rep, and construction lender.

## Run it

```bash
pip install -r requirements.txt
python mock/build_fixtures.py        # regenerate the sample Procore data (already committed)
python run.py                        # mock data, mock narrator unless credentials exist
python run.py --narrator claude      # needs ANTHROPIC_API_KEY or `ant auth login`
```

Output lands in `out/`: an HTML report, a Markdown version, and the computed facts as JSON.

## Layout

```
mock/build_fixtures.py     invents one project (Bergen Street Apartments, fictional) in Procore's shapes
mock/procore/*.json        the fixtures: project, rfis, submittals, change_orders, budget, milestones, daily_logs
fieldstack/model.py        unified data model; every record carries a ref (RFI-041, SUB-118.R2, PCO-007, LOG-2026-08-14, MS-4, SOV-03-000)
fieldstack/procore.py      MockProcoreClient (fixtures) and LiveProcoreClient (REST v1.0, untested) -> ProjectSnapshot
fieldstack/metrics.py      deterministic facts: RFI aging in business days, overdue submittals, pending COs and dollars, SOV percent complete, projected cost, headcount, weather hours
fieldstack/narrative.py    ClaudeNarrator (structured output, cited prose) and MockNarrator (template prose)
fieldstack/render.py       HTML (print-friendly, light and dark) and Markdown
run.py                     CLI
```

## Design rules

- **The model never computes.** Aging, dollars, percents, and dates come from `metrics.py`.
  The narrative prompt receives those facts as JSON and is told not to invent anything.
- **Every claim cites a record.** Citations render as links back to Procore where a link exists.
- **Approval gate.** Nothing is sent. The PX reads and edits the HTML before it goes to the owner.
- **Swap the source, keep the report.** `LiveProcoreClient` returns the same `ProjectSnapshot`
  as the mock. Autodesk Build, Sage 300 CRE (via hh2), and P6 would each be another client
  feeding the same model; the cost section is the first place accounting data would replace
  Procore budget data.

## What a pilot needs from the customer

- A Procore API token with read scope on one project (or an installed Fieldstack app once one exists in the marketplace).
- The last two owner reports, so the narrator matches their voice (`mock/prior_owner_report_excerpt.md` shows the shape).
- The contract's RFI and submittal response windows in business days (stored as project custom fields).

## Known gaps

- `LiveProcoreClient` has not been run against a real tenant. Budget views and daily log sub-resources will need field mapping.
- Percent complete is dollar-weighted from budget line `percent_complete`; a real deployment should take it from the pay application schedule of values.
- Weekly internal report variant not built yet; the monthly owner report is the demo.

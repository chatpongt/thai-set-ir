---
name: thai-set-ir
description: >-
  Maintain the Thai SET IR Universe dataset — validate Investor Relations URLs,
  add/remove companies, and run the quarterly health report. Use whenever the
  user wants to update, audit, or query the Thai SET IR company list.
metadata:
  version: 1.0.0
  category: data-maintenance
  requires:
    bins: [python3]
  cliHelp: python scripts/update.py --help
---

# thai-set-ir

Agent skill for the **Thai SET IR Universe** dashboard. All company data lives in
a single source of truth — `data/companies.js` — and is maintained through one
tool: `scripts/update.py`. Data refreshes **quarterly** (Q1=Apr, Q2=Jul,
Q3=Oct, Q4=Jan).

## Prerequisites

- Run every command from the repo root (paths below assume it).
- `pip install -r scripts/requirements.txt` once per environment.
- **Golden rule:** edit company data ONLY in `data/companies.js`. Never edit
  data in `index.html` — its action URLs are auto-generated from the ticker.

## Syntax

```
python scripts/update.py <command> [flags]
```

Read commands (`check`, `report`, `list`) accept `--json` to emit a structured
JSON envelope on stdout instead of the human report — pipe it to `jq` or parse
it directly. Write commands (`add`, `remove`, `stamp`) mutate `companies.js`.

## Commands

| Command | What it does | JSON? |
|---------|--------------|:-----:|
| `check [--verbose]` | Validate every active IR URL (HTTP status); exit 1 if any broken | ✅ |
| `report` | Quarterly health report: counts, sector breakdown, missing fields | ✅ |
| `list [--all]` | Dump company records incl. auto-generated SEC/SET links (`--all` = include inactive) | ✅ |
| `add TICKER "Name" "Sector" "URL"` | Add a new company (URL may be `null`) | — |
| `remove TICKER` | Soft-delete: set `active:false` (record is kept) | — |
| `stamp` | Set `lastVerified` = today for all active companies | — |
| `export [out.csv]` | Export active companies to CSV | — |

`Sector` must be one of: Banking, Energy, Healthcare, Property, REIT, Commerce,
Finance, Industrial, Food, Hospitality, Telecom, Tech, Transport, Utilities,
Media, Insurance, Education, Infra.

## Structured JSON output

`--json` makes the tool agent-consumable — no scraping human text. Shapes:

```bash
# Which IR links are broken right now?
python scripts/update.py --check --json | jq -r '.broken[].ticker'

# Companies with no IR page on file
python scripts/update.py --list --json | jq -r '.companies[] | select(.ir==null) | .ticker'

# Is the dataset healthy (no missing required fields)?
python scripts/update.py --report --json | jq '.healthy'
```

- `check`  → `{ checked, ok, skipped[], broken[{ticker,url,status,error}], pass }`
  (exit code 0 when `pass`, else 1)
- `report` → `{ date, active, inactive, missingIr[], missingYt[], sectors{}, missingFields[], healthy }`
- `list`   → `{ count, companies[{...record, links:{ir,yt,sec561,fs,mda,oppday}}] }`

## Quarterly update workflow

Run these in order; do not push until `check` reports 0 broken URLs.

1. `python scripts/update.py --report --json` — snapshot current health.
2. `python scripts/update.py --check` — find broken IR links.
3. Fix broken URLs in `data/companies.js` (or `--add` / `--remove` companies).
4. `python scripts/update.py --check` again until it passes (exit 0).
5. `python scripts/update.py --stamp` — update `lastVerified`.
6. Commit with the quarter in the message, e.g. `Q2 2026 data update — verified <date>`, then push. GitHub Actions deploys automatically.

## Discovery

```bash
python scripts/update.py --help          # all commands
python scripts/update.py --check --help  # flags for one command
python scripts/update.py --list --json | jq 'keys'   # inspect output shape
```

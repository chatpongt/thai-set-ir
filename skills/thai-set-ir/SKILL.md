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
| `check [--verbose] [--all-links]` | Validate every active IR URL (HTTP status); `--all-links` also hits SEC 56-1 + SET FS/MD&A/OppDay + YT; exit 1 if any broken | ✅ |
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

## Filings audit (GROKBOT Drive `filings/` folder)

`scripts/audit_filings.py` checks that every FS + MD&A filing in the Drive
`GROKBOT/filings/` folder is **complete for every period and actually is the
period it claims to be**. It reads the folder's `filings-index` Google Sheet
(as CSV) and optionally a local copy of the files. Rules (non-calendar fiscal
years, documented not-filed exemptions, SEC code aliases, name aliases) live in
`scripts/filings_rules.json`. Edit that file, not the script.

```bash
# 1) get the index as CSV: Sheets → File → Download → CSV, or (agent) Drive MCP
#    download_file_content(fileId=<filings-index id>, exportMimeType="text/csv")
# 2) index-only audit (completeness + consistency)
python scripts/audit_filings.py --index filings-index.csv --md audit.md --csv issues.csv
# 3) full audit incl. file bytes + content (Drive for desktop / rclone copy)
python scripts/audit_filings.py --index filings-index.csv \
  --root "$HOME/Library/CloudStorage/GoogleDrive-<account>/My Drive/GROKBOT/filings"
# narrow down / machine output
python scripts/audit_filings.py --index filings-index.csv --ticker AEONTS --year 2024 --json | jq '.findings'
```

| Tier | Needs | Catches |
|------|-------|---------|
| completeness | index | due period with no usable row (`C-MISSING`, `C-NOT-INDEXED`), preferred-row problems |
| index | index | title period-end ≠ expected (`I-PERIOD-END`), SEC filing date before period end = previous period's doc (`I-FILED-BEFORE`), foreign SEC company code (`I-SEC-CODE`), wrong doc kind/lang, bad `drive_path`, file kept outside `filings/`, duplicate sha256 across periods |
| files | `--root` | file absent, size/sha256 mismatch, corrupt zip/pdf, **content names another period** (`F-WRONG-PERIOD`) or no recognisable company/period |

Content check: text comes from PDFs (pdftotext → pypdf fallback) and from the
DOCX/XLSX inside SEC fs-full zips. A period counts as verified when the text
has the expected period-end date (EN/TH, CE/BE formats) or a period label
(`3Q25`, `Q3/2025`, `ไตรมาสที่ 3/2568`, `FY2025`). When neither is there but
the prior/next period is, the file is flagged as the wrong period.

A slot is due at period end + 45 days (quarter) / + 60 days (FY); before that it is `NOT_DUE`.
Exit code is 1 when there are errors (`--strict`: warnings count too), so it can gate CI.
JSON → `{ summary{per_year, severity, by_code}, findings[{severity,code,ticker,year,period,type,row,message}], file_stats, not_in_index[] }`.

## Discovery

```bash
python scripts/update.py --help          # all commands
python scripts/update.py --check --help  # flags for one command
python scripts/update.py --list --json | jq 'keys'   # inspect output shape
```

#!/usr/bin/env python3
"""
Thai SET IR Universe — Quarterly Update Tool
=============================================
Usage:
  python update.py --check              Validate all IR URLs (HTTP status)
  python update.py --check --verbose    Show all URLs including OK ones
  python update.py --stamp              Update lastVerified dates to today
  python update.py --add TICKER "Name" "Sector" "https://ir-url.com"
  python update.py --remove TICKER      Mark company as active:false
  python update.py --export out.csv     Export to CSV
  python update.py --report             Full quarterly health report
  python update.py --list               Dump all companies (use with --json)

Structured output (gws-style — agent friendly):
  Add --json to any read command (check/report/list) to emit machine-readable
  JSON on stdout instead of the human report, e.g.:
      python update.py --check --json | jq '.broken[].ticker'
      python update.py --list  --json | jq '[.companies[] | select(.ir==null)]'
"""

import sys, os, re, json, csv, argparse, datetime
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
DATA_FILE   = ROOT / "data" / "companies.js"
TIMEOUT     = 10  # HTTP request timeout seconds
CONCURRENCY = 10  # Parallel requests

VALID_SECTORS = {
    "Banking","Energy","Healthcare","Property","REIT","Commerce",
    "Finance","Industrial","Food","Hospitality","Telecom","Tech",
    "Transport","Utilities","Media","Insurance","Education","Infra"
}

REQUIRED_FIELDS = ["ticker","name","nameFull","sector","ir","yt","notes","lastVerified","active"]

# ── Structured (JSON) output ──────────────────────────────────────────────────
# gws-style: read commands emit machine-readable JSON when --json is set, so an
# LLM agent or `jq` can consume the result without scraping human text.
JSON_OUT = False

def emit(payload):
    """Print a structured JSON envelope to stdout (only when --json is active)."""
    print(json.dumps(payload, ensure_ascii=False, indent=2))

# Auto-generated URL patterns (same as index.html)
def url_561(ticker):  return f"https://market.sec.or.th/public/idisc/en/companyprofile/listed/{ticker}"
def url_fs(ticker):   return f"https://www.set.or.th/en/market/product/stock/quote/{ticker.lower()}/financial-statement/company-highlights"
def url_mda(ticker):  return f"https://www.set.or.th/en/market/product/stock/quote/{ticker.lower()}/news"
def url_opp(ticker):  return f"https://www.set.or.th/en/market/product/stock/quote/{ticker.lower()}/company-profile/oppday-company-snapshot"


# ── Parse companies.js ─────────────────────────────────────────────────────────
def load_companies():
    """Parse companies from companies.js (extracts the JS array as JSON)."""
    text = DATA_FILE.read_text(encoding="utf-8")
    # Extract array between first [ and last ]
    start = text.index("[")
    end   = text.rindex("]") + 1
    js_array = text[start:end]

    # Convert JS object literals to JSON
    # Fix: single-quoted strings → double-quoted (careful with apostrophes)
    # We use a simple regex approach for this well-structured file
    js_array = re.sub(r"(?<!:)//.*", "", js_array)     # remove // comments (keep :// in URLs)
    js_array = re.sub(r",\s*\n\s*\]", "\n]", js_array) # trailing comma before ]
    js_array = re.sub(r",\s*\}", "}", js_array)         # trailing comma in object

    # Quote only the known schema keys (anchored to { or , so colons inside
    # string values — e.g. "https://" — are never mistaken for keys).
    key_re = "|".join(re.escape(k) for k in REQUIRED_FIELDS)
    js_array = re.sub(rf"([{{,]\s*)({key_re})(\s*):", r'\1"\2"\3:', js_array)

    # Replace single-quoted strings with double-quoted
    # Handle escaped apostrophes and ampersands
    def fix_quotes(m):
        inner = m.group(1)
        inner = inner.replace('"', '\\"')
        return '"' + inner + '"'
    js_array = re.sub(r"'([^']*)'", fix_quotes, js_array)

    try:
        return json.loads(js_array)
    except json.JSONDecodeError as e:
        print(f"❌ Parse error in companies.js: {e}")
        print("   Run with --debug to see cleaned JSON")
        sys.exit(1)


def save_companies(companies):
    """Write companies back to companies.js, preserving file header/footer."""
    text = DATA_FILE.read_text(encoding="utf-8")
    # Keep everything before the opening [
    header_end = text.index("[")
    header = text[:header_end]
    # Keep footer after last ]
    footer_start = text.rindex("]") + 1
    footer = text[footer_start:]

    lines = ["[\n"]
    for i, c in enumerate(companies):
        sep = "," if i < len(companies)-1 else ""
        ir_val  = f"'{c['ir']}'" if c['ir'] else "null"
        yt_val  = f"'{c['yt']}'" if c.get('yt') else "null"
        notes   = c.get('notes','').replace("'","\"")
        active  = "true" if c.get('active', True) else "false"
        verified= "true" if c.get('verified', True) else "true"
        lines.append(
            f"  {{ ticker:'{c['ticker']}', name:'{c['name']}', "
            f"nameFull:'{c['nameFull']}', sector:'{c['sector']}', "
            f"ir:{ir_val}, yt:{yt_val}, "
            f"notes:'{notes}', lastVerified:'{c['lastVerified']}', active:{active} }}{sep}\n"
        )
    lines.append("]\n")

    DATA_FILE.write_text(header + "".join(lines) + footer, encoding="utf-8")
    print(f"✅ Saved {len(companies)} companies to {DATA_FILE.relative_to(ROOT)}")


# ── URL Checker ────────────────────────────────────────────────────────────────
def check_url(url, timeout=TIMEOUT):
    """Return (status_code, ok, error_msg)."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ThaiSET-IRChecker/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.status < 400, None
    except Exception as e:
        code = getattr(e, 'code', 0)
        return code, False, str(e)[:60]


def cmd_check(args):
    """Validate all active IR URLs and report broken ones."""
    companies = load_companies()
    active = [c for c in companies if c.get('active', True)]
    if not JSON_OUT:
        print(f"\n🔍 Checking {len(active)} companies (IR links only)...\n")

    broken, ok, skipped = [], [], []
    for c in active:
        ticker = c['ticker']
        if not c['ir']:
            skipped.append(ticker)
            continue
        status, good, err = check_url(c['ir'])
        if good:
            ok.append(ticker)
            if args.verbose and not JSON_OUT:
                print(f"  ✅ {ticker:<12} {status}  {c['ir']}")
        else:
            broken.append((ticker, c['ir'], status, err))
            if not JSON_OUT:
                print(f"  ❌ {ticker:<12} {status or '---'}  {c['ir']}")
                if err: print(f"              {err}")

    if JSON_OUT:
        emit({
            "command": "check",
            "checked": len(active),
            "ok": len(ok),
            "skipped": skipped,
            "broken": [
                {"ticker": t, "url": url, "status": code, "error": err}
                for t, url, code, err in broken
            ],
            "pass": len(broken) == 0,
        })
        sys.exit(0 if not broken else 1)

    print(f"\n{'─'*60}")
    print(f"  ✅ OK:      {len(ok)}")
    print(f"  ❌ Broken:  {len(broken)}")
    print(f"  ⏭️  Skipped: {len(skipped)} (ir=null)")
    print(f"{'─'*60}")

    if broken:
        print("\n⚠️  Fix these IR URLs in data/companies.js:")
        for t, url, code, err in broken:
            print(f"  {t}: {url}")
        print("\nThen re-run: python update.py --check")
        sys.exit(1)
    else:
        print("\n✅ All IR URLs are valid! Safe to push.\n")


# ── Stamp ──────────────────────────────────────────────────────────────────────
def cmd_stamp(args):
    """Update lastVerified to today for all active companies."""
    companies = load_companies()
    today = datetime.date.today().isoformat()
    count = 0
    for c in companies:
        if c.get('active', True):
            c['lastVerified'] = today
            count += 1
    save_companies(companies)
    print(f"📅 Stamped {count} companies with lastVerified={today}")


# ── Add company ───────────────────────────────────────────────────────────────
def cmd_add(args):
    """Add a new company to companies.js."""
    companies = load_companies()
    tickers = {c['ticker'] for c in companies}

    ticker = args.ticker.upper()
    if ticker in tickers:
        print(f"❌ {ticker} already exists. Use --check or edit manually.")
        sys.exit(1)

    if args.sector not in VALID_SECTORS:
        print(f"❌ Invalid sector '{args.sector}'. Valid: {sorted(VALID_SECTORS)}")
        sys.exit(1)

    new = {
        "ticker":       ticker,
        "name":         args.name,
        "nameFull":     args.name,
        "sector":       args.sector,
        "ir":           args.ir_url if args.ir_url != "null" else None,
        "yt":           f"https://www.youtube.com/results?search_query=Opportunity+Day+{ticker}+SET",
        "notes":        "",
        "lastVerified": datetime.date.today().isoformat(),
        "active":       True
    }
    companies.append(new)
    companies.sort(key=lambda x: x['ticker'])
    save_companies(companies)
    print(f"✅ Added {ticker} — {args.name} ({args.sector})")


# ── Remove company ────────────────────────────────────────────────────────────
def cmd_remove(args):
    """Mark company as active:false (soft delete, keeps history)."""
    companies = load_companies()
    ticker = args.ticker.upper()
    found = False
    for c in companies:
        if c['ticker'] == ticker:
            c['active'] = False
            found = True
            print(f"⛔ Marked {ticker} as inactive (active=false)")
            break
    if not found:
        print(f"❌ Ticker '{ticker}' not found.")
        sys.exit(1)
    save_companies(companies)


# ── Export CSV ────────────────────────────────────────────────────────────────
def cmd_export(args):
    """Export active companies to CSV."""
    companies = load_companies()
    active = [c for c in companies if c.get('active', True)]
    out = Path(args.output)

    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(["Ticker","Name","Sector","IR","56-1 (SEC)","FS (SET)","MD&A (SET)","OppDay SET","OppDay YT","Notes","LastVerified"])
        for c in active:
            t = c['ticker']
            w.writerow([
                t, c['name'], c['sector'],
                c['ir'] or "",
                url_561(t), url_fs(t), url_mda(t), url_opp(t),
                c.get('yt') or "",
                c.get('notes',''),
                c.get('lastVerified','')
            ])
    print(f"📥 Exported {len(active)} companies → {out}")


# ── Quarterly Report ──────────────────────────────────────────────────────────
def cmd_report(args):
    """Print a full quarterly health report."""
    companies = load_companies()
    active    = [c for c in companies if c.get('active', True)]
    inactive  = [c for c in companies if not c.get('active', True)]

    from collections import Counter
    sectors   = Counter(c['sector'] for c in active)
    no_ir     = [c['ticker'] for c in active if not c['ir']]
    no_yt     = [c['ticker'] for c in active if not c.get('yt')]

    # Check for missing required fields
    missing = []
    for c in active:
        for f in REQUIRED_FIELDS:
            if f not in c:
                missing.append(f"{c['ticker']}.{f}")

    today = datetime.date.today().isoformat()

    if JSON_OUT:
        emit({
            "command": "report",
            "date": today,
            "active": len(active),
            "inactive": len(inactive),
            "missingIr": no_ir,
            "missingYt": no_yt,
            "sectors": dict(sectors),
            "missingFields": missing,
            "healthy": not missing,
        })
        return

    print(f"\n{'═'*60}")
    print(f"  Thai SET IR Universe — Quarterly Report  {today}")
    print(f"{'═'*60}")
    print(f"  📊 Active companies:   {len(active)}")
    print(f"  ⛔ Inactive/delisted:  {len(inactive)}")
    print(f"  🔗 IR links missing:   {len(no_ir)}  {no_ir or ''}")
    print(f"  ▶  YT links missing:   {len(no_yt)}  {no_yt or ''}")
    print(f"\n  Sector breakdown:")
    for s, n in sorted(sectors.items(), key=lambda x: -x[1]):
        bar = "█" * n
        print(f"    {s:<14} {n:>3}  {bar}")
    if missing:
        print(f"\n  ⚠️  Missing fields: {missing}")
    else:
        print(f"\n  ✅ All required fields present")
    print(f"\n  Next steps:")
    print(f"    1. python update.py --check        (validate IR URLs)")
    print(f"    2. Fix broken URLs in data/companies.js")
    print(f"    3. python update.py --stamp        (update verified dates)")
    print(f"    4. git commit -m 'Q_ YYYY data update'")
    print(f"{'═'*60}\n")


# ── List (agent-facing dump) ──────────────────────────────────────────────────
def cmd_list(args):
    """Dump companies as structured records, incl. auto-generated SET/SEC URLs.

    Designed for agents/jq: `python update.py --list --json`. Without --json it
    prints a compact human table.
    """
    companies = load_companies()
    rows = companies if args.all else [c for c in companies if c.get('active', True)]

    def enrich(c):
        t = c['ticker']
        return {
            **c,
            "links": {
                "ir":    c.get('ir'),
                "yt":    c.get('yt'),
                "sec561": url_561(t),
                "fs":     url_fs(t),
                "mda":    url_mda(t),
                "oppday": url_opp(t),
            },
        }

    enriched = [enrich(c) for c in rows]

    if JSON_OUT:
        emit({"command": "list", "count": len(enriched), "companies": enriched})
        return

    print(f"\n  {'TICKER':<12}{'SECTOR':<14}{'IR':<6}NAME")
    print(f"  {'─'*58}")
    for c in rows:
        ir_flag = "✅" if c.get('ir') else "—"
        print(f"  {c['ticker']:<12}{c['sector']:<14}{ir_flag:<6}{c['name']}")
    print(f"\n  {len(rows)} companies\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Thai SET IR Universe — Update Tool")
    sub = ap.add_subparsers(dest="cmd")

    ap.add_argument("--json", action="store_true",
                    help="Emit structured JSON (check/report/list) for agents/jq")

    p_check = sub.add_parser("check", help="Validate IR URLs")
    p_check.add_argument("--verbose", action="store_true")
    p_check.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    sub.add_parser("stamp", help="Update lastVerified to today")

    p_report = sub.add_parser("report", help="Quarterly health report")
    p_report.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    p_list = sub.add_parser("list", help="Dump companies (use with --json)")
    p_list.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    p_list.add_argument("--all", action="store_true", help="Include inactive companies")

    p_add = sub.add_parser("add", help="Add new company")
    p_add.add_argument("ticker")
    p_add.add_argument("name")
    p_add.add_argument("sector")
    p_add.add_argument("ir_url")

    p_rm = sub.add_parser("remove", help="Deactivate company")
    p_rm.add_argument("ticker")

    p_exp = sub.add_parser("export", help="Export to CSV")
    p_exp.add_argument("output", nargs="?", default="companies_export.csv")

    # Allow --flag style args too (in addition to subcommand style)
    if len(sys.argv) < 2:
        ap.print_help()
        sys.exit(0)

    # Normalize: treat '--check' as subcommand 'check' etc., but leave
    # '--help'/'-h' (and anything that isn't a real command) untouched.
    args_in = sys.argv[1:]
    COMMANDS = {"check","stamp","report","list","add","remove","export"}
    if args_in[0].startswith("--") and args_in[0][2:] in COMMANDS:
        args_in[0] = args_in[0][2:]

    args = ap.parse_args(args_in)

    global JSON_OUT
    JSON_OUT = getattr(args, "json", False)

    dispatch = {
        "check":   cmd_check,
        "stamp":   cmd_stamp,
        "add":     cmd_add,
        "remove":  cmd_remove,
        "export":  cmd_export,
        "report":  cmd_report,
        "list":    cmd_list,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()

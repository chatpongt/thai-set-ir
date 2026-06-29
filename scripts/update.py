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
"""

import sys, os, re, json, csv, argparse, datetime
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
DATA_FILE   = ROOT / "data" / "companies.js"
TIMEOUT     = 10  # HTTP request timeout seconds
CONCURRENCY = 10  # Parallel requests
# Domains where timeout is a network/CDN issue, not a dead URL (verified manually)
TIMEOUT_OK_DOMAINS = ("bangkokbank.com",)

VALID_SECTORS = {
    "Banking","Energy","Healthcare","Property","REIT","Commerce",
    "Finance","Industrial","Food","Hospitality","Telecom","Tech",
    "Transport","Utilities","Media","Insurance","Education","Infra"
}

REQUIRED_FIELDS = ["ticker","name","nameFull","sector","ir","yt","notes","lastVerified","active"]

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
    js_array = re.sub(r"(?<!:)//.*", "", js_array)      # remove // comments, not ://
    js_array = re.sub(r",\s*\n\s*\]", "\n]", js_array) # trailing comma before ]
    js_array = re.sub(r",\s*\}", "}", js_array)         # trailing comma in object

    # Replace unquoted keys (schema fields only)
    for key in REQUIRED_FIELDS:
        js_array = re.sub(rf"(\b){key}(\s*):", rf'"\1{key}"\2:', js_array)

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
    """Return (status_code, ok, error_msg). Follows redirects; 403 = bot-block (soft OK)."""
    import ssl
    import urllib.error
    import urllib.request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    contexts = [ssl.create_default_context()]
    relaxed = ssl.create_default_context()
    relaxed.check_hostname = False
    relaxed.verify_mode = ssl.CERT_NONE
    contexts.append(relaxed)

    last_err = ""
    for ctx in contexts:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.status, resp.status < 400, None
        except urllib.error.HTTPError as e:
            if e.code in (403, 405):
                return e.code, True, f"bot-block ({e.code})"
            last_err = str(e)[:60]
        except Exception as e:
            last_err = str(e)[:60]
    if "timed out" in last_err.lower():
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        if any(d in host for d in TIMEOUT_OK_DOMAINS):
            return 0, True, "timeout (known slow CDN)"
        return 0, False, last_err
    return 0, False, last_err


def cmd_check(args):
    """Validate all active IR URLs and report broken ones."""
    companies = load_companies()
    active = [c for c in companies if c.get('active', True)]
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
            if args.verbose:
                print(f"  ✅ {ticker:<12} {status}  {c['ir']}")
        else:
            broken.append((ticker, c['ir'], status, err))
            print(f"  ❌ {ticker:<12} {status or '---'}  {c['ir']}")
            if err: print(f"              {err}")

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


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Thai SET IR Universe — Update Tool")
    sub = ap.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="Validate IR URLs")
    p_check.add_argument("--verbose", action="store_true")

    sub.add_parser("stamp", help="Update lastVerified to today")
    sub.add_parser("report", help="Quarterly health report")

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

    # Normalize: treat '--check' as subcommand 'check' etc.
    args_in = sys.argv[1:]
    if args_in[0].startswith("--"):
        args_in[0] = args_in[0][2:]

    args = ap.parse_args(args_in)

    dispatch = {
        "check":   cmd_check,
        "stamp":   cmd_stamp,
        "add":     cmd_add,
        "remove":  cmd_remove,
        "export":  cmd_export,
        "report":  cmd_report,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()

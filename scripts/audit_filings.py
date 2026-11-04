#!/usr/bin/env python3
"""
Thai SET IR — Filings Audit (ตรวจสอบไฟล์งบการเงิน / MD&A ทุกงวด)
=================================================================
Audits the GROKBOT ``filings/`` Drive folder through its ``filings-index`` sheet
(exported as CSV) and, optionally, the files themselves.

Three tiers — each one adds to the previous:

  1. completeness  every ticker x year x period (FY,Q1,Q2,Q3) x type (FS,MDA)
                   that is already due must have a usable row in the index
  2. index         each row is internally consistent: the period-end date in the
                   title, the SEC filing date / company code / doc kind / language
                   encoded in the SEC FILEID, the Drive path, hashes, duplicates
  3. files         (needs --root) the file exists, size + sha256 match the index,
                   the zip/pdf is not corrupt, and the TEXT inside names the right
                   company and the right period-end date

Usage:
  python scripts/audit_filings.py --index filings-index.csv
  python scripts/audit_filings.py --index filings-index.csv --root "/path/to/GROKBOT/filings"
  python scripts/audit_filings.py --index filings-index.csv --md audit.md --csv issues.csv
  python scripts/audit_filings.py --index filings-index.csv --json | jq '.summary'
  python scripts/audit_filings.py --index filings-index.csv --ticker AEONTS --year 2024

--index also accepts an http(s) URL (e.g. a Sheets CSV export link).
--root is a local copy of the Drive ``filings`` folder (Google Drive for desktop,
``rclone sync``, or a manual download).  --existing-root is the base folder that
the ``existing_path`` column is relative to (rows kept outside filings/).

Exit code: 0 = no errors, 1 = errors found (with --strict, warnings count too),
2 = bad input.  Rules (fiscal years, exemptions, SEC code aliases) live in
scripts/filings_rules.json.
"""

import argparse, csv, datetime as dt, hashlib, io, json, re, shutil, subprocess, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT / "scripts" / "filings_rules.json"
COMPANIES_FILE = ROOT / "data" / "companies.js"

OK_STATUS = {"DOWNLOADED", "EXISTING"}
Q_OFFSET = {"FY": 0, "Q3": 3, "Q2": 6, "Q1": 9}  # months before fiscal-year end

# code -> (severity, Thai explanation)
CODES = {
    # completeness
    "C-MISSING":        ("error", "งวดที่ครบกำหนดแล้วแต่ index ระบุ MISSING"),
    "C-NOT-INDEXED":    ("error", "งวดที่ครบกำหนดแล้วแต่ไม่มีแถวใน index เลย (ยังไม่ได้ดึง)"),
    "C-NO-PREFERRED":   ("warn",  "มีไฟล์แต่ไม่มีแถวที่ preferred=yes"),
    "C-MULTI-PREFERRED":("error", "มี preferred=yes มากกว่า 1 แถวในงวดเดียวกัน"),
    # index consistency
    "I-PERIOD-END":     ("error", "วันสิ้นงวดใน title ไม่ตรงกับงวดที่ระบุ"),
    "I-FILED-BEFORE":   ("error", "SEC ได้รับไฟล์ก่อนวันสิ้นงวด → น่าจะเป็นเอกสารของงวดก่อน"),
    "I-FILED-LATE":     ("warn",  "SEC ได้รับไฟล์หลังกำหนดส่งนานผิดปกติ (ฉบับแก้ไข หรือผิดงวด)"),
    "I-SEC-CODE":       ("error", "รหัสบริษัทใน SEC FILEID ไม่ตรงกับไฟล์อื่นของ ticker นี้ (อาจเป็นไฟล์ของบริษัทอื่น)"),
    "I-SEC-KIND":       ("warn",  "ประเภทเอกสารใน FILEID ไม่ตรงกับ type (FS=FIN, MDA=NWS)"),
    "I-LANG":           ("warn",  "ภาษาใน FILEID (E/T) ไม่ตรงกับคอลัมน์ lang"),
    "I-PATH":           ("warn",  "drive_path ไม่ตรงรูปแบบ TICKER/YEAR/PERIOD"),
    "I-OUTSIDE-FOLDER": ("warn",  "ไฟล์ preferred อยู่นอกโฟลเดอร์ filings/ (มีแค่ existing_path)"),
    "I-NO-FILE-ID":     ("error", "สถานะมีไฟล์ แต่ไม่มี drive_file_id"),
    "I-HASH":           ("warn",  "ไม่มี sha256 หรือรูปแบบไม่ถูกต้อง"),
    "I-SMALL":          ("warn",  "ขนาดไฟล์เล็กผิดปกติ"),
    "I-DUP-HASH":       ("error", "ไฟล์เดียวกัน (sha256 ซ้ำ) ถูกใช้ในหลายงวด"),
    "I-UNKNOWN":        ("warn",  "period หรือ type ไม่อยู่ในรายการที่รู้จัก"),
    # files
    "F-FILE-MISSING":   ("error", "ไม่พบไฟล์ใน --root ตาม drive_path/file_name"),
    "F-SIZE":           ("error", "ขนาดไฟล์จริงไม่ตรงกับ size_bytes"),
    "F-SHA":            ("error", "sha256 ของไฟล์จริงไม่ตรงกับ index"),
    "F-CORRUPT":        ("error", "ไฟล์เสีย / ไม่ใช่ zip หรือ pdf ที่ถูกต้อง"),
    "F-WRONG-PERIOD":   ("error", "เนื้อหาในไฟล์เป็นของงวดอื่น (ไม่พบวันสิ้นงวดที่ถูกต้อง แต่พบวันของงวดอื่น)"),
    "F-PERIOD-UNVERIFIED": ("warn", "ไม่พบวันสิ้นงวดในเนื้อหา ยืนยันงวดไม่ได้"),
    "F-ENTITY-UNVERIFIED": ("warn", "ไม่พบชื่อบริษัทในเนื้อหา"),
    "F-NO-TEXT":        ("warn",  "ดึงข้อความจากไฟล์ไม่ได้ (อาจเป็นไฟล์สแกน)"),
    "F-STRAY":          ("info",  "มีไฟล์ในโฟลเดอร์ที่ไม่อยู่ใน index"),
}

EN_M = ["January","February","March","April","May","June","July","August",
        "September","October","November","December"]
TH_M = ["มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน","กรกฎาคม",
        "สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"]
TH_MA = ["ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.","ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."]


# ── date helpers ──────────────────────────────────────────────────────────────
def month_end(y, m):
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)

def shift_month_end(d, months):
    idx = d.year * 12 + (d.month - 1) + months
    return month_end(idx // 12, idx % 12 + 1)

def period_end(ticker, year, period, rules):
    f = rules.get("fiscal", {}).get(ticker, {})
    m = int(f.get("fye_month", 12))
    end_year = year + 1 if (f.get("label", "end") == "start" and m != 12) else year
    return shift_month_end(month_end(end_year, m), -Q_OFFSET[period])

def due_date(pe, period, rules):
    days = rules.get("due_days", {}).get("FY" if period == "FY" else "Q", 60 if period == "FY" else 45)
    return pe + dt.timedelta(days=days)

def _year(y):
    y = int(y)
    return y - 543 if y > 2400 else y

def parse_title_date(title):
    """Return the period-end date written in an SEC title, or None."""
    if not title:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", title)
    try:
        if m:
            return dt.date(_year(m[3]), int(m[2]), int(m[1]))
        alt = "|".join(re.escape(x) for x in TH_MA + TH_M)
        m = re.search(r"(\d{1,2})\s*(" + alt + r")\s*(\d{4})", title)
        if m:
            mon = (TH_MA.index(m[2]) if m[2] in TH_MA else TH_M.index(m[2])) + 1
            return dt.date(_year(m[3]), mon, int(m[1]))
    except ValueError:
        return None
    return None

FILEID_RE = re.compile(r"FILEID=dat/news/(\d{6})/(\d{4})([A-Z]{3})(\d{8})\d*([ET])\.(\w+)", re.I)

def parse_fileid(url):
    m = FILEID_RE.search(url or "")
    if not m:
        return None
    try:
        filed = dt.datetime.strptime(m[4], "%d%m%Y").date()
    except ValueError:
        filed = None
    return {"code": m[2], "kind": m[3].upper(), "filed": filed,
            "lang": "en" if m[5].upper() == "E" else "th", "ext": m[6].lower()}


# ── loaders ───────────────────────────────────────────────────────────────────
def load_rules(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def load_index(src):
    if re.match(r"https?://", src):
        import urllib.request
        with urllib.request.urlopen(src, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
    else:
        text = Path(src).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"ticker", "year", "period", "type", "status"}
    if not rows or not need <= set(rows[0]):
        raise ValueError(f"index is missing columns {sorted(need - set(rows[0] if rows else []))}")
    for i, r in enumerate(rows, start=2):  # row 1 = header (matches the sheet)
        r["_row"] = i
        for k in list(r):
            if isinstance(r[k], str):
                r[k] = r[k].strip()
        r["ticker"] = r["ticker"].upper()
    return rows

def load_companies():
    out = {}
    if not COMPANIES_FILE.exists():
        return out
    for line in COMPANIES_FILE.read_text(encoding="utf-8").splitlines():
        t = re.search(r"ticker:\s*'([^']+)'", line)
        if not t:
            continue
        nf = re.search(r"nameFull:\s*'((?:[^'\\]|\\.)*)'", line)
        nm = re.search(r"\bname:\s*'((?:[^'\\]|\\.)*)'", line)
        out[t[1].upper()] = {
            "nameFull": nf[1].replace("\\'", "'") if nf else "",
            "name": nm[1].replace("\\'", "'") if nm else "",
            "active": "active:false" not in line.replace(" ", ""),
        }
    return out


# ── audit state ───────────────────────────────────────────────────────────────
class Audit:
    def __init__(self):
        self.findings = []

    def add(self, code, ticker="", year="", period="", typ="", msg="", row=None):
        sev = CODES[code][0]
        self.findings.append({
            "severity": sev, "code": code, "ticker": ticker, "year": str(year),
            "period": period, "type": typ, "row": row, "message": msg,
        })


def slot_key(r):
    return (r["ticker"], int(r["year"]), r["period"], r["type"])

def is_exempt(rules, t, y, p, typ):
    for e in rules.get("exempt", {}).get(t, []):
        if int(e["year"]) == y and e.get("period", p) == p and e.get("type", typ) == typ:
            return e.get("reason", "exempt")
    return None


# ── tier 1: completeness ──────────────────────────────────────────────────────
def check_completeness(rows, rules, tickers, years, today, audit):
    by_slot = defaultdict(list)
    for r in rows:
        by_slot[slot_key(r)].append(r)
    coverage = {}   # (t, y, p, typ) -> OK|MISSING|NOT_INDEXED|NOT_DUE|EXEMPT
    types = rules["required_types"]
    for t in tickers:
        for y in years:
            for p in rules["periods"]:
                pe = period_end(t, y, p, rules)
                due = due_date(pe, p, rules)
                for typ in types:
                    rs = by_slot.get((t, y, p, typ), [])
                    ok = [r for r in rs if r["status"] in OK_STATUS]
                    reason = is_exempt(rules, t, y, p, typ)
                    if ok:
                        state = "OK"
                    elif reason:
                        state = "EXEMPT"
                    elif today < due:
                        state = "NOT_DUE"
                    elif rs:
                        state = "MISSING"
                        note = "; ".join(sorted({r.get("note", "") for r in rs if r.get("note")}))
                        audit.add("C-MISSING", t, y, p, typ,
                                  f"สิ้นงวด {pe}, ครบกำหนด {due}" + (f" — {note}" if note else ""),
                                  rs[0]["_row"])
                    else:
                        state = "NOT_INDEXED"
                        audit.add("C-NOT-INDEXED", t, y, p, typ, f"สิ้นงวด {pe}, ครบกำหนด {due}")
                    coverage[(t, y, p, typ)] = state
    # preferred-row hygiene (all slots that appear in the index, incl. optional types)
    for (t, y, p, typ), rs in by_slot.items():
        if y not in years or t not in tickers:
            continue
        ok = [r for r in rs if r["status"] in OK_STATUS]
        pref = [r for r in ok if r.get("preferred", "").lower() == "yes"]
        if ok and not pref:
            audit.add("C-NO-PREFERRED", t, y, p, typ,
                      f"{len(ok)} แถวมีไฟล์ แต่ preferred = " +
                      ",".join(sorted({repr(r.get('preferred', '')) for r in ok})), ok[0]["_row"])
        if len(pref) > 1:
            audit.add("C-MULTI-PREFERRED", t, y, p, typ,
                      "แถว " + ", ".join(str(r["_row"]) for r in pref), pref[0]["_row"])
    return coverage


# ── tier 2: index consistency ─────────────────────────────────────────────────
def check_index(rows, rules, tickers, years, audit):
    known_p, known_t = set(rules["periods"]), set(rules["required_types"]) | set(rules.get("optional_types", []))
    min_size = rules.get("min_size_bytes", {})
    grace = int(rules.get("filing_grace_days", 45))
    aliases = {t: set(v) for t, v in rules.get("sec_code_aliases", {}).items()}

    # dominant SEC company code per ticker
    codes = defaultdict(Counter)
    for r in rows:
        f = parse_fileid(r.get("source_url"))
        if f:
            codes[r["ticker"]][f["code"]] += 1
    main_code = {t: c.most_common(1)[0][0] for t, c in codes.items()}

    sha_slots = defaultdict(set)
    for r in rows:
        t, p, typ = r["ticker"], r["period"], r["type"]
        try:
            y = int(r["year"])
        except ValueError:
            audit.add("I-UNKNOWN", t, r["year"], p, typ, f"year={r['year']!r}", r["_row"]); continue
        if t not in tickers or y not in years:
            continue
        if p not in known_p or typ not in known_t:
            audit.add("I-UNKNOWN", t, y, p, typ, f"period={p!r} type={typ!r}", r["_row"]); continue
        if r["status"] not in OK_STATUS:
            continue
        row = r["_row"]
        pe = period_end(t, y, p, rules)

        td = parse_title_date(r.get("title"))
        if td and td != pe:
            audit.add("I-PERIOD-END", t, y, p, typ, f"title บอก {td} แต่งวดนี้ควรสิ้นสุด {pe}", row)

        f = parse_fileid(r.get("source_url"))
        if f:
            if f["filed"]:
                if f["filed"] < pe:
                    audit.add("I-FILED-BEFORE", t, y, p, typ,
                              f"ส่ง SEC {f['filed']} ก่อนวันสิ้นงวด {pe} ({(pe - f['filed']).days} วัน)", row)
                elif f["filed"] > due_date(pe, p, rules) + dt.timedelta(days=grace):
                    audit.add("I-FILED-LATE", t, y, p, typ,
                              f"ส่ง SEC {f['filed']} ({(f['filed'] - pe).days} วันหลังสิ้นงวด {pe})", row)
            ok_codes = {main_code.get(t)} | aliases.get(t, set())
            if f["code"] not in ok_codes:
                audit.add("I-SEC-CODE", t, y, p, typ,
                          f"รหัส {f['code']} แต่ไฟล์ส่วนใหญ่ของ {t} ใช้ {main_code.get(t)}", row)
            want = {"FS": "FIN", "MDA": "NWS"}.get(typ)
            if want and f["kind"] != want:
                audit.add("I-SEC-KIND", t, y, p, typ, f"FILEID เป็น {f['kind']} (ควรเป็น {want})", row)
            if r.get("lang") in ("en", "th") and f["lang"] != r["lang"]:
                audit.add("I-LANG", t, y, p, typ, f"FILEID = {f['lang']}, lang = {r['lang']}", row)

        dp = r.get("drive_path", "")
        if dp and dp != f"{t}/{y}/{p}":
            audit.add("I-PATH", t, y, p, typ, f"drive_path = {dp!r}", row)
        if not dp and r.get("preferred", "").lower() == "yes":
            audit.add("I-OUTSIDE-FOLDER", t, y, p, typ, f"existing_path = {r.get('existing_path') or '-'}", row)
        if not r.get("drive_file_id"):
            audit.add("I-NO-FILE-ID", t, y, p, typ, "", row)
        sha = r.get("sha256", "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            audit.add("I-HASH", t, y, p, typ, f"sha256 = {sha or '(ว่าง)'}", row)
        else:
            sha_slots[sha].add((t, y, p, typ, row))
        sz = r.get("size_bytes", "")
        if sz.isdigit() and int(sz) < int(min_size.get(typ, 0)):
            audit.add("I-SMALL", t, y, p, typ, f"{int(sz):,} bytes", row)

    for sha, slots in sha_slots.items():
        distinct = {s[:4] for s in slots}
        if len(distinct) > 1:
            names = ", ".join(f"{a} {b} {c} {d} (แถว {e})" for a, b, c, d, e in sorted(slots))
            first = sorted(slots)[0]
            audit.add("I-DUP-HASH", first[0], first[1], first[2], first[3], f"{sha[:12]}… ใช้ใน: {names}", first[4])


# ── tier 3: files ─────────────────────────────────────────────────────────────
def _norm(s):
    return re.sub(r"\s+", " ", s.replace(",", " ")).lower()

def date_forms(d):
    dd, mm, y, be = f"{d.day:02d}", f"{d.month:02d}", d.year, d.year + 543
    en, ab, th, tha = EN_M[d.month - 1], EN_M[d.month - 1][:3], TH_M[d.month - 1], TH_MA[d.month - 1]
    forms = [f"{d.day} {en} {y}", f"{en} {d.day} {y}", f"{d.day} {ab} {y}", f"{ab} {d.day} {y}",
             f"{dd}/{mm}/{y}", f"{d.day}/{d.month}/{y}", f"{dd}.{mm}.{y}", f"{y}-{mm}-{dd}",
             f"{d.day} {th} {be}", f"{d.day} {tha} {be}", f"{d.day} {th} {y}", f"{d.day} {tha} {y}",
             f"{dd}/{mm}/{be}", f"{d.day}{tha}{be}", f"{d.day}{th}{be}"]
    return {_norm(x) for x in forms}

def period_label_re(y, p):
    """Regex for period labels such as 3Q25, Q3/2025, ไตรมาสที่ 3/2568, FY2025."""
    yy, be = f"{y % 100:02d}", y + 543
    if p == "FY":
        alts = [rf"fy\s?{y}", rf"fy\s?{yy}", rf"full[- ]year {y}", rf"{y} full[- ]year",
                rf"fiscal year {y}", rf"ประจำปี {be}", rf"ปี {be}"]
    else:
        q = p[1]
        alts = [rf"{q}q\s?{yy}", rf"{q}q\s?{y}", rf"q{q}\s?[/'’-]?\s?{y}", rf"q{q}\s?[/'’-]\s?{yy}",
                rf"{q}q/{y}", rf"ไตรมาส(?:ที่)?\s?{q}\s?(?:/|ปี)\s?{be}", rf"ไตรมาส(?:ที่)?\s?{q}\s?(?:/|ปี)\s?{y}"]
    return re.compile(r"(?<![0-9a-z])(?:" + "|".join(alts) + r")(?![0-9])")

def _ooxml_text(data):
    """Plain text from a .docx/.xlsx (stdlib only)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            parts = [n for n in z.namelist()
                     if n in ("word/document.xml", "xl/sharedStrings.xml") or n.startswith("xl/worksheets/sheet1")]
            xml = " ".join(z.read(n)[:3_000_000].decode("utf-8", "replace") for n in parts)
    except (zipfile.BadZipFile, KeyError):
        return ""
    return re.sub(r"<[^>]+>", " ", xml)

def _pdf_text(data, pages):
    if shutil.which("pdftotext"):
        try:
            p = subprocess.run(["pdftotext", "-l", str(pages), "-enc", "UTF-8", "-", "-"],
                               input=data, capture_output=True, timeout=60)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.decode("utf-8", "replace")
        except (subprocess.SubprocessError, OSError):
            pass
    try:
        import pypdf
        rd = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((pg.extract_text() or "") for pg in rd.pages[:pages])
    except Exception:
        return ""

def extract_text(path, pages=6):
    data = path.read_bytes()
    if data[:4] == b"%PDF":
        return _pdf_text(data, pages)
    if path.suffix.lower() in (".docx", ".xlsx"):
        return _ooxml_text(data)
    if zipfile.is_zipfile(io.BytesIO(data)):
        parts = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            low = {n: n.lower() for n in names}
            for n in [n for n in names if low[n].endswith(".pdf")][:3]:
                parts.append(_pdf_text(z.read(n), pages))
            # SEC fs-full zips: AUDITOR_REPORT.DOCX, FINANCIAL_STATEMENTS.XLSX, NOTES.DOCX
            for n in sorted([n for n in names if low[n].endswith((".docx", ".xlsx"))],
                            key=lambda n: ("auditor" not in low[n], "financial" not in low[n]))[:3]:
                parts.append(_ooxml_text(z.read(n)))
            for n in [n for n in names if low[n].endswith((".xml", ".txt", ".htm", ".html"))][:2]:
                parts.append(z.read(n)[:200000].decode("utf-8", "replace"))
        return "\n".join(parts)
    return ""

def check_format(path):
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf" or data[:4] == b"%PDF":
        return data[:4] == b"%PDF" and b"%%EOF" in data[-2048:], "pdf"
    if path.suffix.lower() == ".zip" or data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return z.testzip() is None and bool(z.namelist()), "zip"
        except zipfile.BadZipFile:
            return False, "zip"
    return True, path.suffix.lower()

def entity_terms(t, companies, rules):
    c = companies.get(t, {})
    terms = {t}
    for n in (c.get("nameFull", ""), c.get("name", "")):
        n = re.sub(r"\b(public company limited|pcl|plc)\b\.?", "", n, flags=re.I).strip(" .,")
        if len(n) >= 4:
            terms.add(n)
    terms |= set(rules.get("name_aliases", {}).get(t, []))
    return {_norm(x) for x in terms}

def check_files(rows, rules, tickers, years, companies, root, existing_root, content, audit, progress):
    stats = Counter()
    referenced = set()
    todo = [r for r in rows if r["status"] in OK_STATUS and r["ticker"] in tickers
            and r["year"].isdigit() and int(r["year"]) in years and r["period"] in Q_OFFSET]
    for i, r in enumerate(todo, 1):
        t, y, p, typ, row = r["ticker"], int(r["year"]), r["period"], r["type"], r["_row"]
        dp = r.get("drive_path", "")
        if dp and re.search(r"\.(zip|pdf|xlsx?|docx?)$", dp, re.I):
            path = root / dp                      # drive_path already holds the file name
        elif dp and r.get("file_name"):
            path = root / dp / r["file_name"]
        elif r.get("existing_path") and existing_root:
            path = existing_root / r["existing_path"]
        else:
            stats["skipped_no_path"] += 1
            continue
        referenced.add(path.resolve())
        if progress and i % 25 == 0:
            print(f"  … {i}/{len(todo)} files", file=sys.stderr)
        if not path.is_file():
            audit.add("F-FILE-MISSING", t, y, p, typ, str(path), row); stats["missing"] += 1; continue
        stats["checked"] += 1
        size = path.stat().st_size
        if r.get("size_bytes", "").isdigit() and int(r["size_bytes"]) != size:
            audit.add("F-SIZE", t, y, p, typ, f"จริง {size:,} / index {int(r['size_bytes']):,}", row)
        if re.fullmatch(r"[0-9a-fA-F]{64}", r.get("sha256", "")):
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            if h != r["sha256"].lower():
                audit.add("F-SHA", t, y, p, typ, f"จริง {h[:12]}… / index {r['sha256'][:12]}…", row)
        ok, kind = check_format(path)
        if not ok:
            audit.add("F-CORRUPT", t, y, p, typ, f"{path.name} ({kind})", row); continue
        if not content or typ not in ("FS", "MDA"):
            continue
        text = _norm(extract_text(path))
        if len(text) < 200:
            audit.add("F-NO-TEXT", t, y, p, typ, path.name, row); stats["no_text"] += 1; continue
        stats["content_checked"] += 1
        pe = period_end(t, y, p, rules)
        if any(f in text for f in date_forms(pe)) or period_label_re(y, p).search(text):
            stats["period_ok"] += 1
        else:
            alts = []
            for shift, label in ((-12, "ปีก่อน"), (12, "ปีถัดไป"), (-3, "ไตรมาสก่อน"), (3, "ไตรมาสถัดไป")):
                d = shift_month_end(pe, shift)
                if any(f in text for f in date_forms(d)):
                    alts.append(f"{d} ({label})")
            for dy, label in ((-1, "ปีก่อน"), (1, "ปีถัดไป")):
                m = period_label_re(y + dy, p).search(text)
                if m:
                    alts.append(f"'{m[0]}' ({label})")
            if alts:
                audit.add("F-WRONG-PERIOD", t, y, p, typ,
                          f"{path.name}: ไม่พบ {pe} แต่พบ " + ", ".join(alts), row)
            else:
                audit.add("F-PERIOD-UNVERIFIED", t, y, p, typ, f"{path.name}: ไม่พบ {pe}", row)
        if not any(term in text for term in entity_terms(t, companies, rules)):
            audit.add("F-ENTITY-UNVERIFIED", t, y, p, typ, f"{path.name} (lang={r.get('lang')})", row)

    # stray files inside the filings tree
    if root.is_dir():
        for t in sorted(tickers):
            for y in years:
                d = root / t / str(y)
                if not d.is_dir():
                    continue
                for f in d.rglob("*"):
                    if f.is_file() and f.resolve() not in referenced and not f.name.startswith("."):
                        audit.add("F-STRAY", t, y, f.parent.name, "", str(f.relative_to(root)))
    return dict(stats)


# ── reporting ─────────────────────────────────────────────────────────────────
SYM = {"OK": "✅", "MISSING": "❌", "NOT_INDEXED": "⬜", "NOT_DUE": "⏳", "EXEMPT": "➖"}

def summarize(coverage, findings, years, rules):
    per_year = {}
    for y in years:
        c = Counter(s for (t, yy, p, typ), s in coverage.items() if yy == y)
        per_year[y] = {k: c.get(k, 0) for k in SYM}
    sev = Counter(f["severity"] for f in findings)
    by_code = Counter(f["code"] for f in findings)
    return {"per_year": per_year, "severity": dict(sev), "by_code": dict(by_code.most_common())}

def cell(coverage, t, y, p, types):
    states = [coverage.get((t, y, p, typ), "NOT_INDEXED") for typ in types]
    if all(s == states[0] for s in states):
        return SYM[states[0]]
    return "".join(SYM[s] for s in states)

def write_md(path, payload, coverage, tickers, years, rules):
    s, L = payload["summary"], []
    L.append(f"# รายงานตรวจสอบ filings — {payload['generated_at']}\n")
    L.append(f"แหล่งข้อมูล: `{payload['index']}` ({payload['rows']} แถว) · ticker {len(tickers)} ตัว · "
             f"ปี {', '.join(map(str, years))} · ตรวจไฟล์: {'ใช่' if payload['files'] else 'ไม่ (ไม่ได้ระบุ --root)'}\n")
    L.append(f"**ผลรวม:** error {s['severity'].get('error', 0)} · warn {s['severity'].get('warn', 0)} · "
             f"info {s['severity'].get('info', 0)}\n")
    L.append("## ความครบถ้วนต่อปี (นับเป็นช่อง ticker × งวด × ประเภท)\n")
    L.append("| ปี | ✅ ครบ | ❌ MISSING | ⬜ ยังไม่ดึง | ⏳ ยังไม่ครบกำหนด | ➖ ยกเว้น |")
    L.append("|---|---|---|---|---|---|")
    for y in years:
        c = s["per_year"][y]
        L.append(f"| {y} | {c['OK']} | {c['MISSING']} | {c['NOT_INDEXED']} | {c['NOT_DUE']} | {c['EXEMPT']} |")
    L.append("\n## ปัญหาแยกตามประเภท\n")
    L.append("| code | ระดับ | จำนวน | ความหมาย |\n|---|---|---|---|")
    for code, n in s["by_code"].items():
        L.append(f"| `{code}` | {CODES[code][0]} | {n} | {CODES[code][1]} |")
    by_code = defaultdict(list)
    for f in payload["findings"]:
        by_code[f["code"]].append(f)
    L.append("\n## รายละเอียด (error และ warn)\n")
    for code, fs in by_code.items():
        if CODES[code][0] == "info":
            continue
        L.append(f"### `{code}` — {CODES[code][1]} ({len(fs)})\n")
        if code == "C-NOT-INDEXED":
            g = defaultdict(list)
            for f in fs:
                g[(f["year"], f["ticker"])].append(f"{f['period']}-{f['type']}")
            byy = defaultdict(list)
            for (y, t), v in sorted(g.items()):
                byy[y].append(t if len(v) == 2 * len(rules["periods"]) else f"{t} ({', '.join(v)})")
            for y, ts in byy.items():
                L.append(f"- **{y}** ({len(ts)} ticker): " + ", ".join(ts))
            L.append("")
            continue
        for f in fs[:200]:
            loc = f"{f['ticker']} {f['year']} {f['period']} {f['type']}".strip()
            r = f" · แถว {f['row']}" if f["row"] else ""
            L.append(f"- **{loc}**{r} — {f['message']}")
        if len(fs) > 200:
            L.append(f"- … อีก {len(fs) - 200} รายการ (ดูใน --csv / --json)")
        L.append("")
    L.append("## ตารางความครบถ้วน (FS+MDA)\n")
    L.append("✅ ครบ · ❌ MISSING · ⬜ ยังไม่ดึง · ⏳ ยังไม่ครบกำหนด · ➖ ยกเว้น (ถ้า FS กับ MDA ต่างกันจะแสดงสองตัว FS|MDA)\n")
    ps = rules["periods"]
    head = "| ticker | " + " | ".join(f"{y} {p}" for y in years for p in ps) + " |"
    L.append(head)
    L.append("|---" * (1 + len(years) * len(ps)) + "|")
    for t in tickers:
        L.append(f"| {t} | " + " | ".join(cell(coverage, t, y, p, rules["required_types"])
                                          for y in years for p in ps) + " |")
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")

def write_csv(path, findings):
    cols = ["severity", "code", "ticker", "year", "period", "type", "row", "message", "meaning"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for f in findings:
            w.writerow({**{k: f.get(k, "") for k in cols[:-1]}, "meaning": CODES[f["code"]][1]})


# ── main ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit the GROKBOT filings folder via filings-index")
    ap.add_argument("--index", required=True, help="filings-index CSV path or URL")
    ap.add_argument("--root", help="local copy of the Drive 'filings' folder (enables file checks)")
    ap.add_argument("--existing-root", help="base folder for the existing_path column")
    ap.add_argument("--rules", default=str(RULES_FILE))
    ap.add_argument("--ticker", action="append", help="limit to ticker(s); repeatable or comma-separated")
    ap.add_argument("--year", action="append", type=int, help="limit to year(s)")
    ap.add_argument("--universe", choices=["index", "companies", "both"], default="index",
                    help="which tickers must be complete (default: tickers present in the index)")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD) for due-date logic")
    ap.add_argument("--no-content", action="store_true", help="skip text extraction in file checks")
    ap.add_argument("--md", help="write a Markdown report here")
    ap.add_argument("--csv", help="write all findings as CSV here (paste into a sheet tab)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the text summary")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    a = ap.parse_args(argv)

    try:
        rules = load_rules(a.rules)
        rows = load_index(a.index)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    companies = load_companies()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    years = sorted(set(a.year or rules["years"]))

    idx_t = {r["ticker"] for r in rows}
    comp_t = {t for t, c in companies.items() if c["active"]}
    tickers = {"index": idx_t, "companies": comp_t, "both": idx_t | comp_t}[a.universe]
    if a.ticker:
        want = {x.strip().upper() for s in a.ticker for x in s.split(",") if x.strip()}
        tickers = tickers & want if tickers & want else want
    tickers = sorted(tickers)

    audit = Audit()
    coverage = check_completeness(rows, rules, set(tickers), years, today, audit)
    check_index(rows, rules, set(tickers), years, audit)
    file_stats = None
    if a.root:
        root = Path(a.root).expanduser()
        if not root.is_dir():
            print(f"❌ --root not found: {root}", file=sys.stderr)
            return 2
        er = Path(a.existing_root).expanduser() if a.existing_root else None
        file_stats = check_files(rows, rules, set(tickers), years, companies, root, er,
                                 not a.no_content, audit, progress=not a.json)

    order = {"error": 0, "warn": 1, "info": 2}
    audit.findings.sort(key=lambda f: (order[f["severity"]], f["code"], f["ticker"], f["year"], f["period"], f["type"]))
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "today": str(today), "index": a.index, "rows": len(rows), "years": years,
        "tickers": tickers, "files": bool(a.root), "file_stats": file_stats,
        "not_in_companies_js": sorted(idx_t - set(companies)) if companies else [],
        "not_in_index": sorted(comp_t - idx_t),
        "summary": summarize(coverage, audit.findings, years, rules),
        "findings": audit.findings,
    }
    if a.md:
        write_md(a.md, payload, coverage, tickers, years, rules)
    if a.csv:
        write_csv(a.csv, audit.findings)

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        s = payload["summary"]
        print(f"📂 filings audit — {len(rows)} rows, {len(tickers)} tickers, years {years}, today {today}")
        for y in years:
            c = s["per_year"][y]
            tot = sum(c.values())
            print(f"  {y}: ✅ {c['OK']}/{tot}  ❌ {c['MISSING']}  ⬜ {c['NOT_INDEXED']}  ⏳ {c['NOT_DUE']}  ➖ {c['EXEMPT']}")
        if file_stats:
            print(f"  files: {file_stats}")
        print(f"  findings: error {s['severity'].get('error', 0)} · warn {s['severity'].get('warn', 0)} · info {s['severity'].get('info', 0)}")
        for code, n in s["by_code"].items():
            print(f"    {CODES[code][0]:5} {code:22} {n:5}  {CODES[code][1]}")
        if payload["not_in_index"]:
            print(f"  ℹ️  companies.js tickers with no filings rows: {', '.join(payload['not_in_index'])}")
        if a.md:
            print(f"  📝 {a.md}")
        if a.csv:
            print(f"  📄 {a.csv}")

    sev = payload["summary"]["severity"]
    return 1 if sev.get("error") or (a.strict and sev.get("warn")) else 0


if __name__ == "__main__":
    sys.exit(main())

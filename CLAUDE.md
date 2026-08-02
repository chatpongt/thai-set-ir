# 🤖 Thai SET IR Universe — Claude Code Instructions

## Project Purpose
Dashboard สำหรับ Jon's RSI Cluster System ติดตาม Investor Relations links,
56-1 One Report, Financial Statements, MD&A และ Opportunity Day ของหุ้น Thai SET
ข้อมูลอัพเดทราย**ไตรมาส** (Q1=เม.ย., Q2=ก.ค., Q3=ต.ค., Q4=ม.ค.)

---

## 📁 File Structure
```
thai-set-ir-web/
├── CLAUDE.md                   ← You are here
├── README.md                   ← Setup & deployment guide
├── index.html                  ← Main web app (DO NOT edit data here)
├── data/
│   └── companies.js            ← ✏️ ONLY edit this file for data updates
├── scripts/
│   ├── update.py               ← URL validator & quarterly update tool
│   └── requirements.txt
├── skills/
│   └── thai-set-ir/
│       └── SKILL.md            ← Agent skill (gws-style): how to drive update.py
└── .github/
    └── workflows/
        └── deploy.yml          ← Auto-deploy to GitHub Pages on push
```

> **Agent skill:** `skills/thai-set-ir/SKILL.md` documents every `update.py`
> command in a single self-contained file (frontmatter + JSON output shapes),
> modeled on the Google Workspace CLI (`gws`) skill format. Read it first when
> automating data maintenance. Read commands (`--check`, `--report`, `--list`)
> support `--json` for machine-readable output: e.g.
> `python scripts/update.py --check --json | jq -r '.broken[].ticker'`.

**Golden Rule:** ข้อมูลบริษัทอยู่ใน `data/companies.js` เท่านั้น
ห้ามแก้ข้อมูลใน `index.html`

---

## 🔄 Quarterly Update Workflow (ทำทุกไตรมาส)

### Step 1: Validate existing URLs
```bash
cd scripts
pip install -r requirements.txt
python update.py --check
```
Output: รายการ URLs ที่ใช้ไม่ได้ (status ≠ 200/301/302)

### Step 2: Fix broken IR links
แก้ไขใน `data/companies.js` ตาม output จาก Step 1:
```javascript
{ ticker: 'EXAMPLE', ir: 'https://NEW-URL.com/ir', ... }
```

### Step 3: Add new companies (ถ้ามี)
```bash
python update.py --add TICKER "Company Name" "Sector" "https://ir-url.com"
```
หรือแก้ `data/companies.js` โดยตรงตาม schema ด้านล่าง

### Step 4: Remove delisted companies
```bash
python update.py --remove TICKER
```

### Step 5: Stamp verified date & push
```bash
python update.py --stamp          # อัพเดท lastVerified = today
git add data/companies.js
git commit -m "Q[N] YYYY data update — verified $(date +%Y-%m-%d)"
git push
```
GitHub Actions จะ deploy ให้อัตโนมัติใน ~2 นาที

---

## 📋 Company Data Schema

```javascript
{
  ticker:       "CPALL",                          // SET ticker (UPPERCASE)
  name:         "CP All",                          // Short display name
  nameFull:     "CP All Public Company Limited",   // Full legal name
  sector:       "Commerce",                        // See VALID SECTORS below
  ir:           "https://www.cpall.co.th/en/investor-relations",  // IR page URL (null if N/A)
  yt:           "https://www.youtube.com/results?search_query=Opportunity+Day+CPALL+SET",
  notes:        "",                                // Optional notes
  lastVerified: "2026-05-17",                      // ISO date, updated by --stamp
  active:       true                               // false = delisted (hidden from UI)
}
```

### Valid Sectors
`Banking` | `Energy` | `Healthcare` | `Property` | `REIT` | `Commerce` |
`Finance` | `Industrial` | `Food` | `Hospitality` | `Telecom` | `Tech` |
`Transport` | `Utilities` | `Media` | `Insurance` | `Education` | `Infra`

---

## 🔗 Auto-Generated URLs (ไม่ต้องแก้ไขเอง)

URL เหล่านี้ generate อัตโนมัติจาก ticker ใน `index.html`:

| ปุ่ม | URL Pattern |
|------|-------------|
| 📋 56-1 | `https://market.sec.or.th/public/idisc/en/companyprofile/listed/{TICKER}` |
| 📊 FS | `https://www.set.or.th/en/market/product/stock/quote/{ticker}/financial-statement/company-highlights` |
| 📝 MD&A | `https://www.set.or.th/en/market/product/stock/quote/{ticker}/news` |
| 🎯 OppDay SET | `https://www.set.or.th/en/market/product/stock/quote/{ticker}/company-profile/oppday-company-snapshot` |

---

## ✨ Common Tasks

### เพิ่ม field ใหม่ (เช่น targetPrice, analystRating)
1. เพิ่ม field ใน schema ของ `data/companies.js` ทุก record
2. เพิ่ม column ใน `index.html` → function `renderRow()` และ `<thead>`
3. อัพเดท `update.py` → `REQUIRED_FIELDS` list

### เพิ่ม sector ใหม่
1. เพิ่ม entry ใน `SECTOR_COLORS` object ใน `index.html`
2. เพิ่มปุ่ม filter ใน `<div id="fbar">` ใน `index.html`
3. เพิ่ม CSS class `.s-NewSector` ใน `index.html`

### Export ข้อมูลเป็น CSV
กดปุ่ม "📥 Export CSV" ใน UI, หรือรัน:
```bash
python update.py --export companies.csv
```

### ดู URL status ทั้งหมด
```bash
python update.py --check --verbose > url_report.txt
```

---

## 🚀 Initial Setup (ครั้งแรก)

```bash
# 1. Install dependencies
pip install -r scripts/requirements.txt

# 2. Test locally
python -m http.server 8080
# เปิด http://localhost:8080

# 3. Deploy to GitHub Pages
git init
git remote add origin https://github.com/USERNAME/thai-set-ir.git
git add .
git commit -m "Initial commit"
git push -u origin main
# ไปที่ Settings → Pages → Source: GitHub Actions
```

---

## ⚠️ Rules
- ห้าม hardcode URL ใน `index.html` (ใช้ auto-generate จาก ticker เสมอ)
- `ir: null` = แสดงปุ่ม N/A (ไม่ใช่ string ว่าง)
- `active: false` = ซ่อนจาก UI แต่ยังอยู่ใน JSON (ไม่ลบ record)
- commit message ต้องระบุ quarter เสมอ: `"Q2 2026 data update"`
- ก่อน push ต้อง run `--check` ผ่านก่อน (0 broken URLs)

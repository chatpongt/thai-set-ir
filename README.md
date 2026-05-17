# 🇹🇭 Thai SET IR Universe

Web dashboard สำหรับติดตาม Investor Relations ของหุ้น Thai SET 81 ตัว
พร้อมลิงก์ 56-1, Financial Statements, MD&A และ Opportunity Day

**Live URL:** `https://USERNAME.github.io/thai-set-ir/`

---

## 🚀 Quick Start

### Local Preview (ไม่ต้อง install อะไร)
```bash
# Python 3
python -m http.server 8080
# เปิด http://localhost:8080
```

### Deploy to GitHub Pages (ฟรี, auto-update on push)
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/thai-set-ir.git
git push -u origin main

# จากนั้น: GitHub repo → Settings → Pages → Source: GitHub Actions
# ✅ Live ใน ~2 นาที
```

---

## 🔄 Quarterly Update (ทำทุกไตรมาส)

```bash
# 1. ตรวจสอบ URL ที่พัง
python scripts/update.py --check

# 2. แก้ไข data/companies.js ตาม output

# 3. อัพเดทวันที่ verified
python scripts/update.py --stamp

# 4. Push → auto-deploy
git add data/companies.js
git commit -m "Q2 2026 data update"
git push
```

---

## 📁 Project Structure

```
thai-set-ir/
├── index.html          ← Web app (ไม่ต้องแตะบ่อย)
├── data/
│   └── companies.js    ← ✏️ แก้ตรงนี้เท่านั้น
├── scripts/
│   ├── update.py       ← Quarterly maintenance tool
│   └── requirements.txt
├── .github/
│   └── workflows/
│       └── deploy.yml  ← Auto-deploy GitHub Pages
├── CLAUDE.md           ← Claude Code instructions
└── README.md
```

---

## ✨ Features

- 🔍 **Search** ด้วย Ticker หรือชื่อบริษัท
- 🏷️ **Filter** ตาม Sector (13 sectors)
- 🔗 **7 links** ต่อบริษัท: IR · 56-1 · FS · MD&A · OppDay SET · OppDay YT
- 📥 **Export CSV** พร้อมใช้
- 📅 **Last Verified** date แสดงทุกแถว
- ⛔ **Delisted toggle** — ซ่อน/แสดงบริษัทที่ออกจาก SET
- 🔃 **Sortable** Ticker และ Sector
- 📱 **Mobile responsive**

---

## ➕ เพิ่มบริษัทใหม่

```bash
python scripts/update.py --add TICKER "ชื่อบริษัท" "Sector" "https://ir-url.com"
```

หรือแก้ `data/companies.js` โดยตรง:
```javascript
{ ticker:'NEW',  name:'New Company',  nameFull:'New Company PCL',
  sector:'Banking', ir:'https://ir.newcompany.com/',
  yt:'https://www.youtube.com/results?search_query=Opportunity+Day+NEW+SET',
  notes:'', lastVerified:'2026-07-01', active:true },
```

---

## ⛔ ลบ/ซ่อนบริษัทที่ออกจาก SET

```bash
python scripts/update.py --remove TICKER
# → ตั้ง active:false (ไม่แสดงใน UI ปกติ แต่ยังอยู่ใน data)
```

---

## 🤖 Claude Code Integration

ดู `CLAUDE.md` สำหรับ instructions ครบถ้วน

**Prompt ที่ใช้บ่อยกับ Claude Code:**
```
อัพเดท data/companies.js สำหรับ Q2 2026:
- รัน python scripts/update.py --check แล้วแก้ URL ที่พัง
- เพิ่มบริษัท [TICKER] เข้า universe
- stamp และ commit
```

---

## 📋 Valid Sectors

`Banking` `Energy` `Healthcare` `Property` `REIT` `Commerce`
`Finance` `Industrial` `Food` `Hospitality` `Telecom` `Tech`
`Transport` `Utilities` `Media` `Insurance` `Education` `Infra`

---

*Jon's RSI Cluster System — Thai SET IR Universe v2.1*

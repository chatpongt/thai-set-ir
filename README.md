# 🇹🇭 Thai SET IR Universe

Web dashboard สำหรับติดตาม Investor Relations ของหุ้น Thai SET 81 ตัว
พร้อมลิงก์ 56-1, Financial Statements, MD&A และ Opportunity Day

**Live URL:** `https://USERNAME.github.io/thai-set-ir/`

---

## 🚀 Quick Start

### 🖥️ เปิดบน PC (Windows) — ดับเบิลคลิกอย่างเดียว
1. ดาวน์โหลดโปรเจกต์ (GitHub → **Code → Download ZIP**) แล้วแตกไฟล์
2. ดับเบิลคลิก **`Open-Dashboard-Windows.bat`** → เปิดในเบราว์เซอร์ทันที ไม่ต้องลงอะไรเพิ่ม
3. อยากมีไอคอนบน Desktop: ดับเบิลคลิก `scripts\windows-desktop-shortcut.bat` ครั้งเดียว จะได้ไอคอน **Thai SET IR**

> จะดับเบิลคลิก `index.html` ตรงๆ ก็ได้ ใช้ได้ทั้ง Windows, macOS และ Linux แบบออฟไลน์
> (ต้องเก็บ `index.html` กับโฟลเดอร์ `data/` ไว้ด้วยกัน)

### Local Preview ผ่าน server (สำหรับนักพัฒนา)
```bash
# Python 3
python -m http.server 8080
# เปิด http://localhost:8080
```

**macOS — เปิดด้วยการดับเบิลคลิก:** ดับเบิลคลิก `scripts/open-dashboard.command`
มันจะ serve จากเครื่อง (อ่าน `data/companies.js` ล่าสุด) แล้วเปิด browser ให้อัตโนมัติ
วาง shortcut บน Desktop โดยลากไฟล์ไป Desktop พร้อมกดค้าง ⌘ + ⌥ (สร้าง alias) หรือ:
```bash
chmod +x scripts/open-dashboard.command        # ครั้งแรกครั้งเดียว
ln -s "$(pwd)/scripts/open-dashboard.command" ~/Desktop/
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
# 1. ตรวจสอบ URL ที่พัง (IR + 56-1 + SET FS/MD&A/OppDay + YT)
python scripts/update.py --check --all-links

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
├── Open-Dashboard-Windows.bat ← 🖥️ ดับเบิลคลิกเปิดบน Windows
├── data/
│   └── companies.js    ← ✏️ แก้ตรงนี้เท่านั้น
├── scripts/
│   ├── update.py       ← Quarterly maintenance tool
│   ├── audit_filings.py ← ตรวจไฟล์งบ/MD&A ใน Drive ว่าครบทุกงวด
│   ├── open-dashboard.command      ← 🍎 ดับเบิลคลิกเปิดบน macOS
│   ├── windows-desktop-shortcut.bat ← สร้างไอคอนบน Desktop (Windows)
│   └── requirements.txt
├── .github/
│   └── workflows/
│       └── deploy.yml  ← Auto-deploy GitHub Pages
├── CLAUDE.md           ← Claude Code instructions
└── README.md
```

---

## ✨ Features

- 🧒 **ใช้ง่ายแม้เด็ก**: วิธีใช้ 3 ขั้นบนหัวเว็บ, ปุ่มใหญ่ 6 สีพร้อมชื่อภาษาไทย, หน้า "❓ ปุ่มแต่ละสีคืออะไร" อธิบายแบบง่ายๆ
- 🔍 **ค้นหา** ด้วย Ticker, ชื่อบริษัท หรือคำไทย (เช่น "ธนาคาร", "โรงพยาบาล")
- 🗂️ **หมวดแบบรูปภาพ** สร้างจากข้อมูลอัตโนมัติ พร้อมจำนวนบริษัท (มือถือ: ปัดซ้าย-ขวา)
- ⭐ **ที่ฉันชอบ** — กดดาวเก็บบริษัทไว้ (จำไว้ในเครื่องนั้น)
- 🃏 / 📋 **การ์ด หรือ ตาราง** (ตารางเรียงตาม ticker / หมวด / วันที่ตรวจ ได้)
- 🔗 ปุ่มต่อบริษัท: 🏠 เว็บบริษัท (IR) · 📘 รายงานประจำปี (56-1) · 💰 งบการเงิน · 💬 ผู้บริหารอธิบาย (MD&A) · 🎤 งานพบนักลงทุน (Opp Day) · ▶️ วิดีโอ
- 🌙 โหมดมืด · 📥 ดาวน์โหลด CSV · ⛔ แสดง/ซ่อนหุ้นที่ออกจากตลาด · 📱 ใช้บนมือถือได้

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
- รัน python scripts/update.py --check --all-links แล้วแก้ URL ที่พัง
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

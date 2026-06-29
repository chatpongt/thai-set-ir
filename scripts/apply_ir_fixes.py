#!/usr/bin/env python3
"""Apply verified IR URL fixes to companies.js"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from update import load_companies, save_companies

FIXES = {
    "BCH": "https://www.bangkokchainhospital.com/en/investor-relations/home",
    "BDMS": "https://investor.bdms.co.th/en",
    "CBG": "https://cbg.listedcompany.com/",
    "CHG": "https://chg.listedcompany.com/",
    "CPALL": "https://www.cpall.co.th/en/investor/",
    "CPAXT": "https://www.cpaxtra.com/en/investor-relations/home",
    "CPN": "https://investor.centralpattana.co.th/en/home",
    "ERW": "https://www.theerawan.com/en/investor-relations/home",
    "GPSC": "https://gpsc.listedcompany.com/",
    "GULF": "https://investor.gulf.co.th/en/home",
    "HANA": "https://www.hanagroup.com/Investor/FinancialInfo",
    "HL": "https://www.healthleadgroup.com/en/investor-relations/home",
    "HMPRO": "https://hmpro.listedcompany.com/",
    "HUMAN": "https://www.humanica.com/global/investors/",
    "INTUCH": "https://investor.gulf.co.th/en/home",
    "ITC": "https://www.i-tail.com/en/investor-relations/home",
    "IVL": "https://www.indoramaventures.com/en/investor-relations",
    "KBANK": "https://kbank.listedcompany.com/",
    "KCE": "https://kce.listedcompany.com/",
    "KCG": "https://kcg.listedcompany.com/",
    "KTB": "https://krungthai.com/en/ir",
    "LHSC": "https://www.lhscreit.com/",
    "M": "https://m.listedcompany.com/",
    "MEGA": "https://investor.megawecare.com/en/home",
    "MOSHI": "https://www.moshimoshi.co.th/en/investor-relations/resource-center",
    "OR": "https://investor.pttor.com/",
    "OSP": "https://www.osotspa.com/en/investor-relations/home",
    "PTT": "https://ptt-th.listedcompany.com/home.html",
    "PTTEP": "https://pttep.listedcompany.com/",
    "RBF": "https://investor.rbfoodsupply.co.th/en/home",
    "ROJNA": "https://rojna.listedcompany.com/home.html",
    "SABINA": "https://investor.sabina.co.th/en/home",
    "SFLEX": "https://sflex.listedcompany.com/",
    "SISB": "https://sisb.ac.th/financial-statements/",
    "SJWD": "https://sjwd.listedcompany.com/",
    "TCAP": "https://tcap.listedcompany.com/",
    "TIDLOR": "https://tidlor.listedcompany.com/",
    "TISCO": "https://www.tisco.co.th/en/investor",
    "TTB": "https://www.ttbbank.com/en/ir",
    "TTW": "https://www.ttwplc.com/en/investor-relations/home",
    "WHA": "https://wha.listedcompany.com/home.html",
    "WHAIR": "https://wha-ir.com/",
    "WHART": "https://whart.listedcompany.com/",
    "WHAUP": "https://whaup.listedcompany.com/",
}

NOTES = {
    "INTUCH": "merged into Gulf — IR via Gulf",
    "TCAP": "merged into TISCO — historical IR portal",
}

today = datetime.date.today().isoformat()
companies = load_companies()
changed = 0
for c in companies:
    t = c["ticker"]
    if t in FIXES:
        old = c["ir"]
        c["ir"] = FIXES[t]
        c["lastVerified"] = today
        if t in NOTES:
            c["notes"] = NOTES[t]
        if old != c["ir"]:
            print(f"  {t}: {old}")
            print(f"    -> {c['ir']}")
            changed += 1
    if t == "NNCL" and not c.get("yt"):
        c["yt"] = "https://www.youtube.com/results?search_query=Opportunity+Day+NNCL+SET"
        c["lastVerified"] = today
        print(f"  NNCL: added YT link")
        changed += 1

save_companies(companies)
print(f"\nUpdated {changed} entries, stamped lastVerified={today}")
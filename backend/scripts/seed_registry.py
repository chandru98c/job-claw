"""
seed_registry.py — Seeds the sources database with company career pages.

Covers:
  - Chennai companies (~65 sources)
  - South India companies — Bangalore, Hyderabad, Kerala, Coimbatore (~75 sources)
  - Indian job aggregators — Naukri, iimjobs, hirist, Foundit, Freshersworld (~18 sources)
  - Western ATS sources from do.md, WordPress JSON, Workable JSON

Run: python scripts/seed_registry.py
"""
import asyncio
import os
import json
import urllib.parse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.database.models import Source
import uuid

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/jobclaw"
).replace("postgresql+psycopg2", "postgresql+asyncpg").replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DB_URL)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc if parsed.netloc else url.strip("/")
    except Exception:
        return url


# ─── CHENNAI COMPANIES ───────────────────────────────────────────────────────
# Sources: github.com/Kajaasfaq/Company-list-Chennai + manual research
# Format: (domain, start_url, ats_type)

CHENNAI_COMPANIES = [
    # Tier-1 IT / MNC
    ("careers.tcs.com",            "https://ibegin.tcs.com/iBegin/",                                   "custom"),
    ("career.infosys.com",         "https://career.infosys.com/joblist",                                "custom"),
    ("careers.wipro.com",          "https://careers.wipro.com/careers-home/",                           "custom"),
    ("hcltech.com",                "https://hcltech.wd5.myworkdayjobs.com/HCLTechCareers",              "workday"),
    ("cognizant.com",              "https://cognizant.wd1.myworkdayjobs.com/Cognizant_Careers",         "workday"),
    ("techmahindra.com",           "https://careers.techmahindra.com/",                                 "custom"),
    ("capgemini.com",              "https://capgemini.wd3.myworkdayjobs.com/Capgemini",                 "workday"),
    ("dxc.com",                    "https://dxc.wd1.myworkdayjobs.com/DXCCareers",                      "workday"),
    ("accenture.com",              "https://accenture.wd3.myworkdayjobs.com/AccentureCareers",          "workday"),
    ("ltimindtree.com",            "https://ltimindtree.wd5.myworkdayjobs.com/LTIMindtree",             "workday"),
    ("mphasis.com",                "https://mphasis.wd5.myworkdayjobs.com/Mphasis",                     "workday"),
    ("hexaware.com",               "https://hexaware.com/careers/",                                     "custom"),
    ("niit-tech.com",              "https://www.niit-tech.com/careers",                                 "custom"),
    ("kgisl.com",                  "https://www.kgisl.com/careers/",                                    "custom"),
    ("cgi.com",                    "https://cgi.njoyn.com/cgi/xweb/xweb.asp?clid=21001",                "custom"),
    # Chennai-HQ product/tech
    ("freshworks.com",             "https://boards.greenhouse.io/freshworks",                            "greenhouse"),
    ("zoho.com",                   "https://careers.zohocorp.com/jobs/Careers",                          "custom"),
    ("chargebee.com",              "https://jobs.lever.co/chargebee",                                   "lever"),
    ("kissflow.com",               "https://kissflow.com/careers/",                                      "custom"),
    ("sify.com",                   "https://www.sify.com/careers/",                                      "custom"),
    ("ramco.com",                  "https://www.ramco.com/careers/",                                     "custom"),
    ("vembu.com",                  "https://www.vembu.com/company/careers/",                             "custom"),
    ("manageengine.com",           "https://careers.manageengine.com/",                                  "custom"),
    ("payoda.com",                 "https://www.payoda.com/careers/",                                    "custom"),
    ("uniphore.com",               "https://jobs.lever.co/uniphore",                                    "lever"),
    ("avaamo.com",                 "https://jobs.lever.co/avaamo",                                      "lever"),
    ("ninjacart.com",              "https://boards.greenhouse.io/ninjacart",                             "greenhouse"),
    ("practo.com",                 "https://boards.greenhouse.io/practo",                                "greenhouse"),
    ("cure.fit",                   "https://jobs.lever.co/curefit",                                     "lever"),
    ("dunzo.com",                  "https://jobs.lever.co/dunzo",                                       "lever"),
    ("swiggy.com",                 "https://careers.swiggy.com/",                                        "custom"),
    ("zomato.com",                 "https://www.zomato.com/careers",                                     "custom"),
    # BPO / KPO / ITES
    ("concentrix.com",             "https://jobs.concentrix.com/",                                       "custom"),
    ("sutherland.com",             "https://careers.sutherlandglobal.com/",                              "custom"),
    ("firstsource.com",            "https://careers.firstsource.com/",                                   "custom"),
    ("hindujaglobalservices.com",  "https://careers.hindujaglobalservices.com/",                         "custom"),
    ("wns.com",                    "https://careers.wns.com/",                                           "custom"),
    ("exlservice.com",             "https://careers.exlservice.com/",                                    "custom"),
    # Banking / Finance
    ("hdfcbank.com",               "https://www.hdfcbank.com/personal/about-us/careers",                 "custom"),
    ("icicibank.com",              "https://www.icicibank.com/careers/",                                  "custom"),
    ("axisbank.com",               "https://www.axisbank.com/careers",                                   "custom"),
    ("kotakbank.com",              "https://www.kotak.com/en/careers.html",                              "custom"),
    ("southindianbank.com",        "https://www.southindianbank.com/careers/",                           "custom"),
    ("cityunionbank.com",          "https://www.cityunionbank.com/careers",                              "custom"),
    ("tamilnadmercantilebank.com", "https://www.tmbank.in/careers",                                      "custom"),
    ("karurvsyabank.com",          "https://www.kvb.co.in/careers/",                                     "custom"),
    ("shriramfinance.in",          "https://www.shriramfinance.in/careers",                              "custom"),
    ("cholamandalam.com",          "https://www.cholamandalam.com/careers.aspx",                         "custom"),
    # Healthcare / Pharma
    ("apollohospitals.com",        "https://careers.apollohospitals.com/",                               "custom"),
    ("fortishealthcare.com",       "https://careers.fortishealthcare.com/",                              "custom"),
    ("manipalhospitals.com",       "https://careers.manipalhospitals.com/",                              "custom"),
    ("sanofi.com",                 "https://sanofi.wd3.myworkdayjobs.com/Sanofi",                        "workday"),
    ("pfizer.com",                 "https://pfizer.wd1.myworkdayjobs.com/PfizerCareers",                 "workday"),
    ("drreddys.com",               "https://careers.drreddys.com/",                                      "custom"),
    # Automotive (Detroit of India)
    ("hyundai.com",                "https://www.hyundai.com/in/en/careers.html",                         "custom"),
    ("ford.com",                   "https://ford.wd12.myworkdayjobs.com/Ford_Careers",                   "workday"),
    ("renault.com",                "https://renault.wd3.myworkdayjobs.com/Renault",                      "workday"),
    ("nissan.com",                 "https://nissan.wd3.myworkdayjobs.com/Nissan_Careers",                "workday"),
    ("royalenfield.com",           "https://careers.royalenfield.com/",                                  "custom"),
    ("tvsmotor.com",               "https://www.tvsmotor.com/careers/",                                  "custom"),
    ("mahindra.com",               "https://careers.mahindra.com/",                                      "custom"),
    ("bosch.com",                  "https://bosch.wd3.myworkdayjobs.com/Bosch",                          "workday"),
    ("ashokleyland.com",           "https://careers.ashokleyland.com/",                                  "custom"),
    ("rane.co.in",                 "https://www.rane.co.in/careers.html",                                 "custom"),
    ("sundramfasteners.com",       "https://www.sundramfasteners.com/careers/",                          "custom"),
    # Retail / E-commerce
    ("amazon.in",                  "https://amazon.jobs/en/locations/chennai-india",                     "custom"),
    ("flipkart.com",               "https://www.flipkartcareers.com/",                                   "custom"),
    ("bigbasket.com",              "https://careers.bigbasket.com/",                                     "custom"),
    ("nykaa.com",                  "https://careers.nykaa.com/",                                         "custom"),
    # Conglomerates / Manufacturing
    ("murugappa.com",              "https://www.murugappa.com/careers/",                                  "custom"),
    ("tvs.com",                    "https://www.tvsmotor.com/careers/",                                   "custom"),
    ("sundaram.com",               "https://www.sundaramfinance.in/careers",                              "custom"),
    ("saint-gobain.com",           "https://careers.saint-gobain.com/",                                  "custom"),
]

# ─── SOUTH INDIA COMPANIES ───────────────────────────────────────────────────

SOUTH_INDIA_COMPANIES = [
    # Bangalore — IT
    ("infosys.com",                "https://career.infosys.com/joblist",                                 "custom"),
    ("wipro.com",                  "https://careers.wipro.com/careers-home/",                            "custom"),
    ("tataelxsi.com",              "https://www.tataelxsi.com/careers/",                                 "custom"),
    ("sasken.com",                 "https://www.sasken.com/careers",                                     "custom"),
    ("subex.com",                  "https://www.subex.com/careers/",                                     "custom"),
    ("infoedge.com",               "https://careers.infoedge.in/",                                       "custom"),
    ("justdial.com",               "https://www.justdial.com/careers",                                   "custom"),
    ("makemytrip.com",             "https://careers.makemytrip.com/",                                    "custom"),
    ("byju.com",                   "https://byjus.com/careers/",                                         "custom"),
    ("unacademy.com",              "https://unacademy.com/careers",                                      "custom"),
    ("vedantu.com",                "https://jobs.lever.co/vedantu",                                      "lever"),
    ("razorpay.com",               "https://razorpay.com/jobs/",                                         "custom"),
    ("cred.club",                  "https://careers.cred.club/",                                         "custom"),
    ("phonepe.com",                "https://careers.phonepe.com/",                                       "custom"),
    ("paytm.com",                  "https://paytm.com/careers/",                                         "custom"),
    ("policybazaar.com",           "https://careers.policybazaar.com/",                                  "custom"),
    ("acko.com",                   "https://jobs.lever.co/acko",                                         "lever"),
    ("browserstack.com",           "https://www.browserstack.com/careers",                               "custom"),
    ("postman.com",                "https://www.postman.com/company/careers/",                           "custom"),
    ("hasura.io",                  "https://hasura.io/careers/",                                         "custom"),
    ("setu.co",                    "https://setu.co/careers",                                            "custom"),
    ("smallcase.com",              "https://smallcase.com/careers",                                      "custom"),
    ("groww.in",                   "https://groww.in/careers",                                           "custom"),
    ("zerodha.com",                "https://zerodha.com/careers/",                                       "custom"),
    ("upstox.com",                 "https://upstox.com/careers/",                                        "custom"),
    ("sharechat.com",              "https://jobs.lever.co/sharechat",                                    "lever"),
    ("dailyhunt.in",               "https://careers.dailyhunt.in/",                                      "custom"),
    ("inmobi.com",                 "https://www.inmobi.com/company/careers/",                            "custom"),
    ("moengage.com",               "https://jobs.lever.co/moengage",                                     "lever"),
    ("clevertap.com",              "https://clevertap.com/careers/",                                     "custom"),
    ("sprinklr.com",               "https://www.sprinklr.com/careers/",                                  "custom"),
    ("darwinbox.com",              "https://darwinbox.com/careers",                                      "custom"),
    ("greythr.com",                "https://www.greythr.com/careers/",                                   "custom"),
    ("keka.com",                   "https://www.keka.com/careers",                                       "custom"),
    ("meesho.com",                 "https://jobs.lever.co/meesho",                                       "lever"),
    ("ixigo.com",                  "https://jobs.lever.co/ixigo",                                        "lever"),
    ("cleartrip.com",              "https://jobs.lever.co/cleartrip",                                    "lever"),
    # Hyderabad — IT / Pharma
    ("cyient.com",                 "https://cyient.wd5.myworkdayjobs.com/Cyient",                        "workday"),
    ("zensar.com",                 "https://zensar.wd5.myworkdayjobs.com/Zensar",                        "workday"),
    ("coforge.com",                "https://coforge.wd5.myworkdayjobs.com/Coforge",                      "workday"),
    ("qualcomm.com",               "https://qualcomm.wd5.myworkdayjobs.com/External",                    "workday"),
    ("microsoft.com",              "https://careers.microsoft.com/",                                     "custom"),
    ("amazon.com",                 "https://amazon.jobs/en/locations/hyderabad-india",                   "custom"),
    ("google.com",                 "https://careers.google.com/locations/hyderabad/",                    "custom"),
    ("sunpharma.com",              "https://careers.sunpharma.com/",                                     "custom"),
    ("aurobindo.com",              "https://www.aurobindo.com/careers/",                                 "custom"),
    ("laurus.com",                 "https://www.lauruslabs.com/careers/",                                "custom"),
    ("divis.com",                  "https://www.divislaboratories.com/careers/",                         "custom"),
    # Kerala — IT / Startups
    ("qburst.com",                 "https://www.qburst.com/careers/",                                   "custom"),
    ("fingent.com",                "https://www.fingent.com/careers/",                                   "custom"),
    ("experion.com",               "https://experionglobal.com/careers/",                                "custom"),
    ("zyxware.com",                "https://www.zyxware.com/careers",                                    "custom"),
    ("infoparkkerala.org",         "https://www.infoparkkerala.org/jobs/",                               "custom"),
    ("technopark.org",             "https://www.technopark.org/jobs/",                                   "custom"),
    # Coimbatore / Tamil Nadu non-Chennai
    ("kovai.co",                   "https://kovai.co/careers/",                                          "custom"),
    ("elgi.com",                   "https://www.elgi.com/careers/",                                      "custom"),
    ("pricol.com",                 "https://www.pricol.com/careers/",                                    "custom"),
    ("suprajit.com",               "https://www.suprajit.com/careers/",                                  "custom"),
    ("lgsoftindia.com",            "https://www.lgsoftindia.com/careers/",                               "custom"),
]

# ─── CHENNAI COMPANIES — from github.com/Kajaasfaq/Company-list-Chennai ────────
# Direct company career pages only. No aggregators.

CHENNAI_KAJAASFAQ = [
    # IT Parks / SEZ anchors — Tidel Park, Olympia Tech Park, DLF IT Park
    ("tcs.com",                    "https://ibegin.tcs.com/iBegin/",                                    "custom"),
    ("infosys.com",                "https://career.infosys.com/joblist",                                "custom"),
    ("wipro.com",                  "https://careers.wipro.com/careers-home/",                           "custom"),
    ("hcltech.com",                "https://hcltech.wd5.myworkdayjobs.com/HCLTechCareers",              "workday"),
    ("cognizant.com",              "https://cognizant.wd1.myworkdayjobs.com/Cognizant_Careers",         "workday"),
    ("capgemini.com",              "https://capgemini.wd3.myworkdayjobs.com/Capgemini",                 "workday"),
    ("accenture.com",              "https://accenture.wd3.myworkdayjobs.com/AccentureCareers",          "workday"),
    ("dxc.com",                    "https://dxc.wd1.myworkdayjobs.com/DXCCareers",                      "workday"),
    ("ltimindtree.com",            "https://ltimindtree.wd5.myworkdayjobs.com/LTIMindtree",             "workday"),
    ("mphasis.com",                "https://mphasis.wd5.myworkdayjobs.com/Mphasis",                     "workday"),
    ("techmahindra.com",           "https://careers.techmahindra.com/",                                 "custom"),
    ("hexaware.com",               "https://hexaware.com/careers/",                                     "custom"),
    ("kgisl.com",                  "https://www.kgisl.com/careers/",                                    "custom"),
    ("cgi.com",                    "https://cgi.njoyn.com/cgi/xweb/xweb.asp?clid=21001",                "custom"),
    ("niit-tech.com",              "https://www.niit-tech.com/careers",                                 "custom"),
    # Chennai product/SaaS companies
    ("freshworks.com",             "https://boards.greenhouse.io/freshworks",                            "greenhouse"),
    ("zoho.com",                   "https://careers.zohocorp.com/jobs/Careers",                          "custom"),
    ("chargebee.com",              "https://jobs.lever.co/chargebee",                                   "lever"),
    ("kissflow.com",               "https://kissflow.com/careers/",                                      "custom"),
    ("ramco.com",                  "https://www.ramco.com/careers/",                                     "custom"),
    ("manageengine.com",           "https://careers.manageengine.com/",                                  "custom"),
    ("vembu.com",                  "https://www.vembu.com/company/careers/",                             "custom"),
    ("payoda.com",                 "https://www.payoda.com/careers/",                                    "custom"),
    ("sify.com",                   "https://www.sify.com/careers/",                                      "custom"),
    ("uniphore.com",               "https://jobs.lever.co/uniphore",                                    "lever"),
    ("avaamo.com",                 "https://jobs.lever.co/avaamo",                                      "lever"),
    # Chennai BPO / ITES
    ("concentrix.com",             "https://jobs.concentrix.com/",                                       "custom"),
    ("sutherland.com",             "https://careers.sutherlandglobal.com/",                              "custom"),
    ("firstsource.com",            "https://careers.firstsource.com/",                                   "custom"),
    ("hindujaglobalservices.com",  "https://careers.hindujaglobalservices.com/",                         "custom"),
    ("wns.com",                    "https://careers.wns.com/",                                           "custom"),
    ("exlservice.com",             "https://careers.exlservice.com/",                                    "custom"),
    ("igate.com",                  "https://www.igate.com/careers/",                                     "custom"),
    ("syntel.com",                 "https://www.syntelinc.com/careers",                                  "custom"),
    # Chennai banking / finance
    ("hdfcbank.com",               "https://www.hdfcbank.com/personal/about-us/careers",                 "custom"),
    ("icicibank.com",              "https://www.icicibank.com/careers/",                                  "custom"),
    ("axisbank.com",               "https://www.axisbank.com/careers",                                   "custom"),
    ("southindianbank.com",        "https://www.southindianbank.com/careers/",                           "custom"),
    ("cityunionbank.com",          "https://www.cityunionbank.com/careers",                              "custom"),
    ("tamilnadmercantilebank.com", "https://www.tmbank.in/careers",                                      "custom"),
    ("karurvsyabank.com",          "https://www.kvb.co.in/careers/",                                     "custom"),
    ("shriramfinance.in",          "https://www.shriramfinance.in/careers",                              "custom"),
    ("cholamandalam.com",          "https://www.cholamandalam.com/careers.aspx",                         "custom"),
    ("sundaram.com",               "https://www.sundaramfinance.in/careers",                              "custom"),
    # Chennai automotive (Detroit of India)
    ("hyundai.com",                "https://www.hyundai.com/in/en/careers.html",                         "custom"),
    ("ford.com",                   "https://ford.wd12.myworkdayjobs.com/Ford_Careers",                   "workday"),
    ("renault.com",                "https://renault.wd3.myworkdayjobs.com/Renault",                      "workday"),
    ("nissan.com",                 "https://nissan.wd3.myworkdayjobs.com/Nissan_Careers",                "workday"),
    ("royalenfield.com",           "https://careers.royalenfield.com/",                                  "custom"),
    ("tvsmotor.com",               "https://www.tvsmotor.com/careers/",                                  "custom"),
    ("ashokleyland.com",           "https://careers.ashokleyland.com/",                                  "custom"),
    ("rane.co.in",                 "https://www.rane.co.in/careers.html",                                 "custom"),
    ("sundramfasteners.com",       "https://www.sundramfasteners.com/careers/",                          "custom"),
    ("bosch.com",                  "https://bosch.wd3.myworkdayjobs.com/Bosch",                          "workday"),
    # Chennai healthcare
    ("apollohospitals.com",        "https://careers.apollohospitals.com/",                               "custom"),
    ("fortishealthcare.com",       "https://careers.fortishealthcare.com/",                              "custom"),
    ("manipalhospitals.com",       "https://careers.manipalhospitals.com/",                              "custom"),
    ("drreddys.com",               "https://careers.drreddys.com/",                                      "custom"),
    ("sanofi.com",                 "https://sanofi.wd3.myworkdayjobs.com/Sanofi",                        "workday"),
    # Chennai conglomerates / manufacturing
    ("murugappa.com",              "https://www.murugappa.com/careers/",                                  "custom"),
    ("saint-gobain.com",           "https://careers.saint-gobain.com/",                                  "custom"),
    ("la-opala.com",               "https://www.laopala.com/careers/",                                   "custom"),
    ("tnpl.com",                   "https://www.tnpl.com/careers/",                                      "custom"),
    ("spencers.in",                "https://www.spencers.in/careers",                                    "custom"),
    # Chennai startups / mid-size tech
    ("ninjacart.com",              "https://boards.greenhouse.io/ninjacart",                             "greenhouse"),
    ("swiggy.com",                 "https://careers.swiggy.com/",                                        "custom"),
    ("zomato.com",                 "https://www.zomato.com/careers",                                     "custom"),
    ("amazon.in",                  "https://amazon.jobs/en/locations/chennai-india",                     "custom"),
    ("flipkart.com",               "https://www.flipkartcareers.com/",                                   "custom"),
    ("bigbasket.com",              "https://careers.bigbasket.com/",                                     "custom"),
    ("nykaa.com",                  "https://careers.nykaa.com/",                                         "custom"),
    # Chennai IT parks — smaller companies
    ("prodapt.com",                "https://www.prodapt.com/careers/",                                   "custom"),
    ("aspire.com",                 "https://www.aspiresys.com/careers",                                  "custom"),
    ("ilink.com",                  "https://www.ilink-digital.com/careers/",                             "custom"),
    ("mastech.com",                "https://www.mastech.com/careers",                                    "custom"),
    ("polaris.com",                "https://www.polarisft.com/careers/",                                 "custom"),
    ("css-corp.com",               "https://www.css-corp.com/careers/",                                  "custom"),
    ("in2it.com",                  "https://www.in2it.com/careers/",                                     "custom"),
    ("trigent.com",                "https://www.trigent.com/careers/",                                   "custom"),
    ("softcell.com",               "https://www.softcell.co.in/careers/",                                "custom"),
    ("microland.com",              "https://www.microland.com/careers",                                  "custom"),
    ("kellton.com",                "https://www.kellton.com/careers",                                    "custom"),
    ("igate-mastech.com",          "https://www.mastech.com/careers",                                    "custom"),
    ("cmsit.com",                  "https://www.cmsit.com/careers/",                                     "custom"),
    ("teamlease.com",              "https://www.teamlease.com/careers",                                  "custom"),
    ("quess.com",                  "https://www.quesscorp.com/careers/",                                 "custom"),
    ("mafoi.com",                  "https://www.mafoi.com/careers/",                                     "custom"),
    ("randstad.co.in",             "https://www.randstad.in/jobs/",                                      "custom"),
    ("manpower.co.in",             "https://www.manpowergroup.co.in/careers/",                           "custom"),
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def make_source(domain: str, start_url: str, ats_type: str) -> Source:
    return Source(
        id=str(uuid.uuid4()),
        domain=domain,
        start_url=start_url,
        ats_type=ats_type if ats_type != "custom" else None,
        is_active=True,
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

async def run_seed():
    async with AsyncSessionLocal() as db:
        existing = await db.execute(text("SELECT domain FROM sources"))
        existing_domains = {row[0] for row in existing}

        sources: dict[str, Source] = {}

        # 1. All Indian sources
        all_indian = CHENNAI_COMPANIES + CHENNAI_KAJAASFAQ + SOUTH_INDIA_COMPANIES
        for domain, start_url, ats_type in all_indian:
            if domain not in existing_domains and domain not in sources:
                sources[domain] = make_source(domain, start_url, ats_type)

        # 2. do.md (legacy scraper list)
        base = Path(__file__).parent.parent.parent
        do_md_path = base / "scaper" / "do.md"
        if do_md_path.exists():
            with open(do_md_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("|") and "Company Name" not in line and "---" not in line:
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 3 and parts[2].startswith("http"):
                            domain = extract_domain(parts[2])
                            if domain and domain not in existing_domains and domain not in sources:
                                sources[domain] = make_source(domain, parts[2], "custom")

        # 3. WordPress JSON
        wp_path = base / "scaper" / "apps" / "backend" / "data" / "targets" / "wordpress_target_sites.seed.json"
        if wp_path.exists():
            with open(wp_path, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    url = item.get("homepage_url")
                    if url:
                        domain = extract_domain(url)
                        if domain and domain not in existing_domains and domain not in sources:
                            sources[domain] = make_source(domain, url, "WordPress")

        # 4. Workable JSON
        wa_path = base / "scaper" / "apps" / "ever-jobs" / "scripts" / "seeds" / "workable-candidates.json"
        if wa_path.exists():
            with open(wa_path, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    slug = item.get("companySlug")
                    if slug:
                        domain = f"{slug}.workable.com"
                        if domain not in existing_domains and domain not in sources:
                            sources[domain] = make_source(
                                domain,
                                f"https://apply.workable.com/{slug}/",
                                "workable",
                            )

        db.add_all(sources.values())
        await db.commit()
        print(f"Seeded {len(sources)} new sources.")
        print(f"  Chennai (original):  {len(CHENNAI_COMPANIES)}")
        print(f"  Chennai (Kajaasfaq): {len(CHENNAI_KAJAASFAQ)}")
        print(f"  South India:         {len(SOUTH_INDIA_COMPANIES)}")


if __name__ == "__main__":
    asyncio.run(run_seed())

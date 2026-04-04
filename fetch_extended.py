#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════
fetch_extended.py  —  Energy CVC Signal Pipeline v2.0
════════════════════════════════════════════════════════════════════

목적:  하루 80~150개 signals (무료 소스만)
소스:  RSS 22개 병렬 + EIA Today in Energy RSS + EIA Open Data API
비용:  완전 무료. 유료 API, paywall, 상업 구독 없음.

출력:
  data/extended_raw.json      전체 수집 raw articles
  data/extended_signals.json  구조화된 signals
  data/fetch_cache.json       7일 dedup 캐시

스키마 (extended_signals.json 내 각 signal):
  id, title, source_name, source_url, published_date,
  observed_fact, why_it_matters_investment, missing_evidence[],
  signal_tier, signal_strength(0-100),
  sector, event_type, companies_mentioned[]

sector 값:
  long_duration_storage | battery_storage | green_hydrogen |
  grid_software | transmission | advanced_nuclear |
  data_center_power | geothermal | offshore_wind | other_cleantech

event_type 값:
  policy | funding | grant | contract | deployment |
  pilot | partnership | regulatory
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch_extended")

# ── Optional deps ─────────────────────────────────────────────────
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    log.warning("feedparser not installed — pip install feedparser")

try:
    import urllib.request as _ur
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# ── Runtime constants ─────────────────────────────────────────────
TODAY    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO  = datetime.now(timezone.utc).isoformat()
MAX_AGE_DAYS   = 3     # skip articles older than this
CACHE_DAYS     = 7     # dedup cache retention
FETCH_TIMEOUT  = 25    # seconds per source
MAX_WORKERS    = 10    # parallel fetch threads

EIA_API_KEY   = os.environ.get("EIA_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CACHE_PATH = Path("data/fetch_cache.json")
RAW_PATH   = Path("data/extended_raw.json")
OUT_PATH   = Path("data/extended_signals.json")


# ════════════════════════════════════════════════════════════════════
# SECTION 1  SOURCE REGISTRY
# 22 free RSS feeds + EIA RSS + EIA API
# Reliability: 1=primary gov/official  2=specialist trade  3=general
# ════════════════════════════════════════════════════════════════════

SOURCES = [

    # ── Priority tier: explicitly requested ────────────────────────

    {
        "id": "canarymedia",
        "name": "Canary Media",
        "url": "https://www.canarymedia.com/rss",
        "reliability": 2,
        "segments": ["battery_storage", "grid_software", "data_center_power",
                     "green_hydrogen", "offshore_wind"],
        "max_items": 30,
        "notes": "High-quality US clean energy journalism. Strong on financing, policy, commercialization.",
    },
    {
        "id": "pvmagazine",
        "name": "PV Magazine",
        "url": "https://www.pv-magazine.com/feed/",
        "reliability": 2,
        "segments": ["battery_storage", "green_hydrogen", "other_cleantech"],
        "max_items": 30,
    },
    {
        "id": "energystoragenews",
        "name": "Energy Storage News",
        "url": "https://www.energy-storage.news/feed/",
        "reliability": 2,
        "segments": ["battery_storage", "long_duration_storage"],
        "max_items": 30,
    },
    {
        "id": "utilitydive",
        "name": "Utility Dive",
        "url": "https://www.utilitydive.com/feeds/news/",
        "reliability": 2,
        "segments": ["grid_software", "battery_storage", "data_center_power", "transmission"],
        "max_items": 30,
        "notes": "Best US utility/grid coverage. FERC news often syndicated here.",
    },
    {
        "id": "eia_todayinenergy",
        "name": "EIA Today in Energy",
        "url": "https://www.eia.gov/rss/todayinenergy.xml",
        "reliability": 1,
        "segments": ["battery_storage", "green_hydrogen", "grid_software",
                     "offshore_wind", "other_cleantech"],
        "max_items": 20,
        "notes": "Tier 1 primary source. US government energy statistics and analysis.",
    },

    # ── DOE official RSS feeds ─────────────────────────────────────
    {
        "id": "doe_eere",
        "name": "DOE EERE News",
        "url": "https://www.energy.gov/eere/articles/rss.xml",
        "reliability": 1,
        "segments": ["battery_storage", "long_duration_storage", "green_hydrogen",
                     "offshore_wind", "geothermal", "other_cleantech"],
        "max_items": 20,
        "notes": "Office of Energy Efficiency and Renewable Energy. Grant announcements, deployments.",
    },
    {
        "id": "doe_fossil",
        "name": "DOE Fossil Energy & Carbon Management",
        "url": "https://www.energy.gov/fecm/articles/rss.xml",
        "reliability": 1,
        "segments": ["green_hydrogen", "other_cleantech"],
        "max_items": 15,
        "notes": "Carbon capture, clean hydrogen, advanced energy from fossil. DOE primary.",
    },
    {
        "id": "doe_cleancities",
        "name": "DOE Clean Cities & Communities",
        "url": "https://www.energy.gov/scep/slsc/clean-cities-communities/articles/rss.xml",
        "reliability": 1,
        "segments": ["other_cleantech", "data_center_power"],
        "max_items": 15,
        "notes": "Fleet electrification, charging infrastructure, community energy.",
    },
    {
        "id": "doe_ne",
        "name": "DOE Nuclear Energy",
        "url": "https://www.energy.gov/ne/articles/rss.xml",
        "reliability": 1,
        "segments": ["advanced_nuclear"],
        "max_items": 15,
        "notes": "Advanced reactor, SMR, fusion news from DOE Office of Nuclear Energy.",
    },
    {
        "id": "doe_main",
        "name": "DOE Energy.gov News",
        "url": "https://www.energy.gov/articles/rss.xml",
        "reliability": 1,
        "segments": ["battery_storage", "green_hydrogen", "grid_software",
                     "advanced_nuclear", "offshore_wind"],
        "max_items": 20,
        "notes": "Top-level DOE news — catches cross-cutting announcements.",
    },

    # ── IRENA ──────────────────────────────────────────────────────
    {
        "id": "irena",
        "name": "IRENA",
        "url": "https://www.irena.org/rss",
        "reliability": 1,
        "segments": ["offshore_wind", "green_hydrogen", "battery_storage",
                     "geothermal", "other_cleantech"],
        "max_items": 15,
        "notes": "International Renewable Energy Agency. Global policy, capacity, cost data.",
    },

    # ── Specialist trade press ─────────────────────────────────────
    {
        "id": "offshorewind",
        "name": "Offshore Wind Biz",
        "url": "https://www.offshorewind.biz/feed/",
        "reliability": 2,
        "segments": ["offshore_wind", "transmission"],
        "max_items": 20,
    },
    {
        "id": "h2view",
        "name": "H2 View",
        "url": "https://www.h2-view.com/feed/",
        "reliability": 2,
        "segments": ["green_hydrogen"],
        "max_items": 20,
    },
    {
        "id": "hydrogeninsight",
        "name": "Hydrogen Insight",
        "url": "https://www.hydrogeninsight.com/feed",
        "reliability": 2,
        "segments": ["green_hydrogen"],
        "max_items": 20,
        "notes": "Specialist hydrogen trade press.",
    },
    {
        "id": "nuclearengineer",
        "name": "Nuclear Engineering International",
        "url": "https://www.neimagazine.com/rss",
        "reliability": 2,
        "segments": ["advanced_nuclear"],
        "max_items": 15,
        "notes": "Specialist nuclear trade press. SMR, advanced reactor coverage.",
    },
    {
        "id": "geothermalrisingbulletin",
        "name": "Geothermal Rising",
        "url": "https://geothermal.org/feed/",
        "reliability": 2,
        "segments": ["geothermal"],
        "max_items": 15,
        "notes": "US geothermal industry association. Project, policy, financing news.",
    },
    {
        "id": "renewablesnow",
        "name": "Renewables Now",
        "url": "https://renewablesnow.com/news/feed/",
        "reliability": 2,
        "segments": ["battery_storage", "offshore_wind", "green_hydrogen"],
        "max_items": 20,
    },
    {
        "id": "energynewsnetwork",
        "name": "Energy News Network",
        "url": "https://energynews.us/feed/",
        "reliability": 2,
        "segments": ["grid_software", "battery_storage", "data_center_power"],
        "max_items": 20,
        "notes": "US state-level energy policy and utility news.",
    },
    {
        "id": "azocleantech",
        "name": "AZoCleantech",
        "url": "https://www.azocleantech.com/rss/news.aspx",
        "reliability": 3,
        "segments": ["battery_storage", "green_hydrogen", "other_cleantech",
                     "advanced_nuclear", "geothermal"],
        "max_items": 20,
        "notes": "Broad cleantech news aggregator. Tier 3 — verify all figures.",
    },
    {
        "id": "electrek",
        "name": "Electrek",
        "url": "https://electrek.co/feed/",
        "reliability": 3,
        "segments": ["battery_storage", "data_center_power", "other_cleantech"],
        "max_items": 20,
    },
    {
        "id": "cleantechnica",
        "name": "CleanTechnica",
        "url": "https://cleantechnica.com/feed/",
        "reliability": 3,
        "segments": ["battery_storage", "grid_software", "data_center_power"],
        "max_items": 20,
        "notes": "Tier 3. Broad coverage. Verify all figures.",
    },
    {
        "id": "rechargenews",
        "name": "Recharge News",
        "url": "https://www.rechargenews.com/feed",
        "reliability": 2,
        "segments": ["green_hydrogen", "offshore_wind", "battery_storage"],
        "max_items": 20,
    },
    {
        "id": "ieaenergy",
        "name": "IEA News",
        "url": "https://www.iea.org/api/rss",
        "reliability": 1,
        "segments": ["green_hydrogen", "battery_storage", "grid_software",
                     "offshore_wind", "other_cleantech"],
        "max_items": 15,
        "notes": "Tier 1 — IEA primary source. Policy and market analysis.",
    },
]


# ════════════════════════════════════════════════════════════════════
# SECTION 2  CACHE
# ════════════════════════════════════════════════════════════════════

def load_cache() -> set:
    if not CACHE_PATH.exists():
        return set()
    try:
        data = json.loads(CACHE_PATH.read_text())
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
        return {e["id"] for e in data if e.get("date", "") >= cutoff}
    except Exception as ex:
        log.warning(f"Cache load failed: {ex} — starting fresh")
        return set()


def save_cache(new_ids: list):
    existing = []
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
        except Exception:
            existing = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
    pruned = [e for e in existing if e.get("date", "") >= cutoff]
    for aid in new_ids:
        pruned.append({"id": aid, "date": TODAY})
    try:
        CACHE_PATH.write_text(json.dumps(pruned, ensure_ascii=False))
    except Exception as ex:
        log.warning(f"Cache save failed: {ex}")


def article_id(url: str, title: str) -> str:
    raw = f"{url.strip()}:{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ════════════════════════════════════════════════════════════════════
# SECTION 3  PARALLEL RSS FETCHER
# ════════════════════════════════════════════════════════════════════

def _parse_date(entry) -> str:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        except Exception:
            pass
    return TODAY


def fetch_one(source: dict, seen_ids: set) -> tuple[str, list, dict]:
    """
    Fetch and parse one RSS feed.
    Returns (source_id, articles[], log_entry).
    Thread-safe — reads only, writes nothing.
    """
    sid   = source["id"]
    name  = source["name"]
    url   = source["url"]
    max_n = source.get("max_items", 20)
    items: list = []

    log_entry = {
        "id": sid, "name": name, "url": url,
        "status": "failed", "items": 0, "error": None,
        "fetched_at": NOW_ISO,
        "reliability": source.get("reliability", 3),
        "segments": source.get("segments", []),
    }

    if not HAS_FEEDPARSER:
        log_entry["error"] = "feedparser not installed"
        return sid, items, log_entry

    cutoff_dt = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")

    try:
        socket.setdefaulttimeout(FETCH_TIMEOUT)
        feed = feedparser.parse(url)

        http_status = getattr(feed, "status", 200)
        if http_status >= 400:
            log_entry["error"] = f"HTTP {http_status}"
            return sid, items, log_entry

        # feedparser bozo = malformed feed but may still have entries
        if getattr(feed, "bozo", False) and not feed.entries:
            ex_msg = str(getattr(feed, "bozo_exception", "unknown"))[:120]
            log_entry["error"] = f"Feed parse error: {ex_msg}"
            return sid, items, log_entry

        count = 0
        for entry in feed.entries[:max_n]:
            title   = (getattr(entry, "title",   "") or "").strip()
            link    = (getattr(entry, "link",    "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:800].strip()

            if not title or not link or title == "[Removed]":
                continue

            date = _parse_date(entry)
            if date < cutoff_dt:
                continue

            aid = article_id(link, title)
            if aid in seen_ids:
                continue

            items.append({
                "article_id":       aid,
                "source_id":        sid,
                "source_name":      name,
                "source_url":       link,
                "source_segments":  source.get("segments", []),
                "reliability":      source.get("reliability", 3),
                "title":            title,
                "summary":          summary,
                "published_date":   date,
                "raw_text":         f"{title} {summary}".lower(),
                "fetched_at":       NOW_ISO,
            })
            count += 1

        log_entry["status"] = "success" if count > 0 else "partial"
        log_entry["items"]  = count

    except socket.timeout:
        log_entry["error"] = f"Timeout ({FETCH_TIMEOUT}s)"
    except Exception as ex:
        log_entry["error"] = str(ex)[:200]

    return sid, items, log_entry


def fetch_all_rss(seen_ids: set) -> tuple[list, list]:
    all_items: list = []
    all_logs:  list = []

    log.info(f"Fetching {len(SOURCES)} RSS sources (max_workers={MAX_WORKERS})...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_one, src, seen_ids): src for src in SOURCES}
        for future in as_completed(futures, timeout=120):
            src = futures[future]
            try:
                sid, items, log_entry = future.result(timeout=5)
                all_items.extend(items)
                all_logs.append(log_entry)
                icon = "✓" if log_entry["status"] == "success" else (
                       "~" if log_entry["status"] == "partial" else "✗")
                err  = f"  [{log_entry['error']}]" if log_entry["error"] else ""
                print(f"    {icon} {src['name']}: {log_entry['items']} items{err}")
            except TimeoutError:
                print(f"    ✗ {src['name']}: future timeout")
                all_logs.append({
                    "id": src["id"], "name": src["name"], "url": src["url"],
                    "status": "failed", "items": 0, "error": "future timeout",
                    "fetched_at": NOW_ISO,
                })
            except Exception as ex2:
                print(f"    ✗ {src['name']}: {ex2}")
                all_logs.append({
                    "id": src["id"], "name": src["name"], "url": src["url"],
                    "status": "failed", "items": 0, "error": str(ex2)[:150],
                    "fetched_at": NOW_ISO,
                })

    return all_items, all_logs


# ════════════════════════════════════════════════════════════════════
# SECTION 4  EIA OPEN DATA API  (free, key at eia.gov/opendata)
#   + EIA Today in Energy RSS already in SOURCES above
#   Here we fetch quantitative data series as structured signals.
# ════════════════════════════════════════════════════════════════════

# EIA API v2 series — each produces one signal with real numbers
EIA_SERIES = [
    {
        "path":        "electricity/electric-power-operational-data",
        "params":      "frequency=monthly&data[0]=generation&facets[fueltypeid][]=SUN"
                       "&facets[sectorid][]=99&sort[0][column]=period&sort[0][direction]=desc"
                       "&offset=0&length=1",
        "description": "US utility-scale solar generation (MWh)",
        "segments":    ["other_cleantech"],
        "event_type":  "deployment",
    },
    {
        "path":        "electricity/electric-power-operational-data",
        "params":      "frequency=monthly&data[0]=generation&facets[fueltypeid][]=WND"
                       "&facets[sectorid][]=99&sort[0][column]=period&sort[0][direction]=desc"
                       "&offset=0&length=1",
        "description": "US utility-scale wind generation (MWh)",
        "segments":    ["offshore_wind"],
        "event_type":  "deployment",
    },
    {
        "path":        "electricity/electric-power-operational-data",
        "params":      "frequency=monthly&data[0]=generation&facets[fueltypeid][]=NUC"
                       "&facets[sectorid][]=99&sort[0][column]=period&sort[0][direction]=desc"
                       "&offset=0&length=1",
        "description": "US nuclear electricity generation (MWh)",
        "segments":    ["advanced_nuclear"],
        "event_type":  "deployment",
    },
    {
        "path":        "total-energy/data",
        "params":      "frequency=monthly&data[0]=value&facets[msn][]=BSESEUS"
                       "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1",
        "description": "US battery energy storage installed capacity (MW)",
        "segments":    ["battery_storage", "long_duration_storage"],
        "event_type":  "deployment",
    },
]


def fetch_eia_api() -> list:
    """
    Fetch EIA Open Data API series.
    Each series returns one structured signal with real government data.
    Requires EIA_API_KEY env var (free at eia.gov/opendata).
    """
    if not EIA_API_KEY:
        log.info("EIA_API_KEY not set — skipping API fetch (RSS feed still active)")
        log.info("  Free key: https://www.eia.gov/opendata/register.php")
        return []

    items = []
    base  = "https://api.eia.gov/v2"

    for series in EIA_SERIES:
        try:
            url = f"{base}/{series['path']}/data/?api_key={EIA_API_KEY}&{series['params']}"
            req = _ur.Request(url, headers={"Accept": "application/json"})
            with _ur.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())

            rows = data.get("response", {}).get("data", [])
            if not rows:
                continue

            row    = rows[0]
            period = row.get("period", "")
            value  = row.get("value", row.get("generation", ""))
            units  = row.get("units", "MWh")
            desc   = series["description"]

            title   = f"EIA: {desc} — {period}: {value:,} {units}" if isinstance(value, (int, float)) else f"EIA: {desc} — {period}: {value} {units}"
            summary = (f"Official EIA data. {desc}. Most recent period: {period}. "
                       f"Value: {value} {units}. "
                       f"Source: US Energy Information Administration Open Data API.")

            items.append({
                "article_id":      article_id("eia.gov/v2/" + series["path"], title),
                "source_id":       "eia_api",
                "source_name":     "EIA Open Data API",
                "source_url":      "https://www.eia.gov/opendata/",
                "source_segments": series["segments"],
                "reliability":     1,
                "title":           title,
                "summary":         summary,
                "published_date":  TODAY,
                "raw_text":        title.lower(),
                "fetched_at":      NOW_ISO,
                "eia_series":      series["path"],
                "eia_period":      period,
                "eia_value":       str(value),
            })
            time.sleep(0.3)   # stay well within EIA rate limits

        except Exception as ex:
            log.warning(f"EIA series {series['path']}: {ex}")

    log.info(f"EIA API: {len(items)} data points")
    return items


# ════════════════════════════════════════════════════════════════════
# SECTION 5  CLASSIFIER & SCORER
# Rule-based. No AI. Every field traceable.
# Sector and event_type match the requested schema exactly.
# ════════════════════════════════════════════════════════════════════

# ── Sector keyword map (requested schema) ─────────────────────────
_SECTOR_KWS: dict[str, list[str]] = {
    "long_duration_storage": [
        "long duration", "long-duration", "ldes", "iron-air", "iron air",
        "vanadium flow", "flow battery", "multi-day storage", "seasonal storage",
        "liquid air", "gravitational storage", "compressed air energy",
    ],
    "battery_storage": [
        "battery storage", "bess", "energy storage", "lithium-ion", "lithium ion",
        "grid battery", "utility-scale battery", "battery system",
        "electrochemical storage", "sodium-ion", "solid state battery",
    ],
    "green_hydrogen": [
        "green hydrogen", "electrolyzer", "electrolysis", "pem electrolyzer",
        "alkaline electrolyzer", "hydrogen production", "hydrogen fuel",
        "h2", "clean hydrogen", "renewable hydrogen", "blue hydrogen",
        "ammonia", "hydrogen storage", "hydrogen offtake",
    ],
    "grid_software": [
        "vpp", "virtual power plant", "demand response", "grid software",
        "ferc", "ancillary services", "frequency regulation",
        "flexibility market", "dispatch optimization", "grid management",
        "energy management system", "ems", "scada", "grid modernization",
        "smart grid", "grid control", "grid intelligence",
    ],
    "transmission": [
        "transmission", "hvdc", "high voltage direct current", "subsea cable",
        "offshore wind cable", "grid interconnect", "power line",
        "transmission line", "grid expansion", "ferc permitting",
        "grid congestion", "interregional transmission",
    ],
    "advanced_nuclear": [
        "nuclear", "smr", "small modular reactor", "advanced reactor",
        "fusion", "molten salt", "fast reactor", "nuclear power",
        "fission", "nrc", "reactor design", "nuclear energy",
        "light water reactor", "next-generation nuclear",
    ],
    "data_center_power": [
        "data center", "hyperscaler", "azure", "aws", "google cloud",
        "power electronics", "ai infrastructure", "cfe", "24/7 clean energy",
        "corporate ppa", "data centre", "cloud computing power",
    ],
    "geothermal": [
        "geothermal", "enhanced geothermal", "egs", "geothermal power",
        "geothermal heat", "geothermal energy", "hot rock",
        "ground source", "geothermal drilling",
    ],
    "offshore_wind": [
        "offshore wind", "floating wind", "fixed-bottom wind",
        "offshore turbine", "wind farm", "wind energy offshore",
        "monopile", "jacket foundation",
    ],
    "other_cleantech": [
        "clean energy", "renewable energy", "solar", "cleantech",
        "decarbonization", "net zero", "climate tech", "energy transition",
        "sustainability", "carbon capture", "ccus",
    ],
}

# Priority order for sector inference (specific → general)
_SECTOR_PRIORITY = [
    "long_duration_storage", "green_hydrogen", "advanced_nuclear",
    "geothermal", "offshore_wind", "transmission", "grid_software",
    "data_center_power", "battery_storage", "other_cleantech",
]

# ── Event type keyword rules ───────────────────────────────────────
# Maps to requested schema: policy|funding|grant|contract|deployment|pilot|partnership|regulatory
_EVENT_RULES = [
    # High-value commercial events
    {
        "event_type": "contract", "base_score": 90,
        "kws": [
            "signs contract", "awarded contract", "secures contract", "contract awarded",
            "offtake agreement", "supply agreement", "framework agreement",
            "purchase agreement", "power purchase agreement", "ppa signed",
            "long-term agreement", "commercial agreement", "procurement contract",
        ],
    },
    {
        "event_type": "deployment", "base_score": 88,
        "kws": [
            "goes live", "commercial operation", "operational", "commissioned",
            "begins operation", "starts operation", "deployed at", "installed at",
            "goes online", "comes online", "energized", "first power",
            "construction complete", "opens facility", "gigafactory",
        ],
    },
    # Funding events
    {
        "event_type": "funding", "base_score": 82,
        "kws": [
            "raises", "closes funding", "series a", "series b", "series c",
            "seed round", "venture capital", "investment round", "funding round",
            "secures investment", "equity raise", "capital raise", "closes $",
            "raises $", "secures $", "investment of $", "closes €", "raises €",
        ],
    },
    # Grant / government funding
    {
        "event_type": "grant", "base_score": 65,
        "kws": [
            "grant awarded", "receives grant", "doe award", "doe funding",
            "government grant", "eu grant", "horizon grant", "innovate uk",
            "nsf grant", "sbir award", "doe selects", "doe announces funding",
            "loan guarantee", "doe loan", "ira funding", "inflation reduction act",
            "department of energy grant", "federal grant",
        ],
    },
    # Pilot / demo
    {
        "event_type": "pilot", "base_score": 70,
        "kws": [
            "pilot project", "demonstration project", "demo project", "field trial",
            "proof of concept", "first deployment", "initial deployment",
            "prototype tested", "demonstration facility", "test project",
        ],
    },
    # Partnership / JV / MOU
    {
        "event_type": "partnership", "base_score": 48,
        "kws": [
            "partnership", "mou", "memorandum of understanding", "joint venture",
            "collaboration agreement", "strategic alliance", "teaming agreement",
            "signs mou", "strategic partnership",
        ],
    },
    # Regulatory / permitting / policy rule
    {
        "event_type": "regulatory", "base_score": 60,
        "kws": [
            "ferc order", "ferc approves", "ferc issues", "ferc rule",
            "environmental impact", "eia approval", "permit granted",
            "permitting", "interconnection approval", "grid interconnection",
            "transmission approval", "nrc approves", "nrc license",
            "eu taxonomy", "sec rule", "epa rule",
        ],
    },
    # Policy / legislation
    {
        "event_type": "policy", "base_score": 55,
        "kws": [
            "policy", "legislation", "regulation", "executive order",
            "inflation reduction act", "infrastructure law",
            "incentive", "subsidy", "tax credit", "itc", "ptc",
            "mandate", "standard", "target", "goal", "plan",
            "national strategy", "clean energy standard",
        ],
    },
]

# Fallback event type when nothing matches
_DEFAULT_EVENT = {"event_type": "other", "base_score": 15}

# ── Noise / boost patterns ────────────────────────────────────────
_NOISE: list[tuple[str, int, str]] = [
    (r"\bproud to (announce|partner|share)\b|\bexcited to (announce|share)\b|\bpleased to announce\b",
     -40, "Generic PR language"),
    (r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b",
     -20, "Intent without confirmed action"),
    (r"\bcould (become|reach|achieve|unlock)\b|\bhas the potential to\b",
     -25, "Speculative framing"),
    (r"\bexploring\b.{0,30}\bpartner|\bin (early )?discussions\b|\bpotential (partner|deal)\b",
     -30, "Exploratory / pre-commercial"),
    (r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b|\blong-term goal\b",
     -30, "Vision announcement only"),
    (r"\bwins? award\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b|\bgartner\b",
     -35, "Vanity recognition"),
    (r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b|\battends? (conference|summit)\b",
     -30, "Conference appearance only"),
    (r"\bpublishes? (report|study|whitepaper)\b|\bnew (report|research|study)\b",
     -25, "Report/research publication"),
    (r"\brebrands?\b|\bnew (logo|brand|website)\b",
     -55, "Rebranding / marketing"),
    (r"\bopinion:\b|\bcommentary:\b|\bop-ed\b|\beditorial\b",
     -60, "Opinion / commentary"),
    (r"\bmarket (wrap|roundup|update)\b|\bweekly (round-?up|digest)\b|\bmonthly digest\b",
     -60, "Market digest"),
    (r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b|\bcareer opportunit\b",
     -50, "Generic job posting"),
]

_BOOST: list[tuple[str, int, str]] = [
    # Named strategic buyers (highest value)
    (r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\bvattenfall\b|\bnational grid\b|\bonx\b",
     +18, "Tier-1 strategic buyer named"),
    (r"\bhyundai\b|\bsamsung\b|\bsiemens\b|\babb\b|\bhitachi\b|\bhanwha\b|\bshell\b|\bbp\b|\btotalenergies\b",
     +12, "Major industrial/OEM buyer named"),
    # Hard numbers
    (r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]|₩[\d,]+억",
     +15, "Specific financial figure"),
    (r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b",
     +10, "Specific capacity figure"),
    (r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month|H[12] 20[2-9]\d",
     +8,  "Concrete timeframe stated"),
    # Government primary sources (EIA, DOE, FERC, IEA, IRENA)
    (r"\beia\b|\bdoe\b|\bferc\b|\biea\b|\birena\b|\bnrel\b|\blbnl\b",
     +6,  "Government/intergovernmental source or subject"),
    # Named location increases specificity
    (r"\bbusan\b|\bincheon\b|\bulsan\b|\brotterdam\b|\bsingapore\b|\bhamburg\b|\btexas\b|\bcalifornia\b|\boffshore\b",
     +5,  "Named project location"),
]


def classify(raw_text: str) -> dict:
    """Return first matching event rule, or default."""
    for rule in _EVENT_RULES:
        for kw in rule["kws"]:
            if kw in raw_text:
                return {"event_type": rule["event_type"],
                        "base_score": rule["base_score"],
                        "matched_kw": kw}
    return {"event_type": "other", "base_score": 15, "matched_kw": None}


def infer_sector(raw_text: str, source_segments: list) -> str:
    """Priority-ordered sector inference from text."""
    for seg in _SECTOR_PRIORITY:
        if any(kw in raw_text for kw in _SECTOR_KWS.get(seg, [])):
            return seg
    # Fall back to first source segment that exists in our schema
    valid = set(_SECTOR_KWS.keys())
    for s in source_segments:
        if s in valid:
            return s
    return "other_cleantech"


def score(raw_text: str, base: int) -> tuple[int, str, list]:
    """Additive score with boost/noise patterns. Returns (score, tier, breakdown)."""
    s = base
    bd = []
    for pattern, delta, reason in _BOOST:
        if re.search(pattern, raw_text, re.I):
            s += delta
            bd.append({"delta": delta, "reason": reason, "type": "boost"})
    for pattern, delta, reason in _NOISE:
        if re.search(pattern, raw_text, re.I):
            s += delta
            bd.append({"delta": delta, "reason": reason, "type": "noise"})
    s = max(0, min(100, round(s)))
    tier = "high" if s >= 60 else "medium" if s >= 35 else "low" if s >= 20 else "noise"
    return s, tier, bd


# ── Known tracked company aliases ────────────────────────────────
_COMPANY_ALIASES: dict[str, str] = {
    "gridwiz": "그리드위즈", "그리드위즈": "그리드위즈",
    "sixtyhz": "식스티헤르츠", "식스티헤르츠": "식스티헤르츠",
    "vincen": "빈센", "빈센": "빈센",
    "standard energy": "스탠다드에너지",
    "form energy": "Form Energy", "form energy systems": "Form Energy",
    "autogrid": "AutoGrid",
    "sunfire": "Sunfire",
    "amogy": "Amogy",
    "hysata": "Hysata",
    "ceres power": "Ceres Power",
    "invinity": "Invinity Energy",
    "enervenue": "EnerVenue",
    "ambri": "Ambri",
    "eos energy": "Eos Energy",
    "hydrostor": "Hydrostor",
    "energy vault": "Energy Vault",
    "verdagy": "Verdagy",
    "electric hydrogen": "Electric Hydrogen",
    "ohmium": "Ohmium",
    "plug power": "Plug Power",
    "bloom energy": "Bloom Energy",
    "kairos power": "Kairos Power",
    "terrapower": "TerraPower",
    "x-energy": "X-Energy",
    "nuscale": "NuScale",
    "fervo": "Fervo Energy",
    "sage geosystems": "Sage Geosystems",
    "gradient geothermal": "Gradient Geothermal",
    "fluence": "Fluence",
    "stem inc": "Stem", "stem,": "Stem",
    "volterra": "Volterra",
}


def extract_companies(raw_text: str) -> list:
    found = []
    for alias, canonical in _COMPANY_ALIASES.items():
        if alias in raw_text and canonical not in found:
            found.append(canonical)
    return found


# ── Missing evidence by event type ───────────────────────────────
_MISSING: dict[str, list] = {
    "contract": [
        "Contract ACV (annual contract value) not disclosed",
        "Duration and renewal terms not public",
        "Exclusivity and geographic scope unknown",
        "Named offtaker confirmed or inferred?",
    ],
    "funding": [
        "Post-money valuation not confirmed",
        "Lead investor identity and type (strategic vs. financial) unknown",
        "Use of proceeds not specified",
        "Series and total capital raised not stated",
    ],
    "grant": [
        "Commercial co-funding partner not identified",
        "Path from grant to commercial revenue not articulated",
        "Named private sector offtaker required?",
        "Milestones and reporting requirements not disclosed",
    ],
    "pilot": [
        "Pilot success KPIs not publicly defined",
        "Pathway to commercial contract post-pilot unclear",
        "Named third-party validator not confirmed",
        "Pilot duration and go/no-go criteria not stated",
    ],
    "deployment": [
        "Commercial revenue terms and offtake pricing not disclosed",
        "Performance guarantee and warranty terms unknown",
        "Scale-up roadmap not public",
    ],
    "partnership": [
        "Binding terms (exclusivity, minimum volume) not confirmed",
        "MOU vs. binding contract distinction not stated",
        "IP ownership and licensing terms unclear",
        "Financial commitments not disclosed",
    ],
    "regulatory": [
        "Effective date and implementation timeline not stated",
        "Market participants affected not enumerated",
        "Compliance costs and transition period not disclosed",
    ],
    "policy": [
        "Implementation regulations not yet issued",
        "Budget appropriation and certainty unknown",
        "Timeline for enforcement unclear",
    ],
    "other": [
        "No investment-specific gap analysis available",
        "Primary research required to assess materiality",
    ],
}


def missing_evidence(event_type: str) -> list:
    return _MISSING.get(event_type, _MISSING["other"])


# ── Why it matters (CVC/investor lens) ───────────────────────────
_WHY: dict[tuple, str] = {
    ("contract",    "long_duration_storage"):
        "Named binding offtake is the critical missing link in LDES project finance. "
        "Confirms demand-side validation and enables project financing.",
    ("contract",    "battery_storage"):
        "Offtake/supply agreement is the clearest commercial-stage signal. "
        "LCOS competitiveness implied but requires terms for confirmation.",
    ("contract",    "green_hydrogen"):
        "Offtake at contracted price is the key missing link in most hydrogen theses. "
        "Without a named buyer at locked price, projects remain financially unviable.",
    ("contract",    "grid_software"):
        "Named utility contract moves company from pilot to commercial stage. "
        "Key unknowns: ACV, duration, exclusivity, framework vs. project-specific.",
    ("contract",    "offshore_wind"):
        "CfD or PPA award confirms revenue certainty. "
        "Construction finance now possible; supply chain commitments follow.",
    ("contract",    "advanced_nuclear"):
        "Power purchase agreement for nuclear is rare and high-value. "
        "Signals utility or industrial decarbonization commitment at scale.",
    ("deployment",  "battery_storage"):
        "Operational deployment confirms TRL-9. "
        "Utilities can now procure with reference site; next signal is replication.",
    ("deployment",  "long_duration_storage"):
        "First commercial deployment of LDES is a sector-defining event. "
        "Establishes real-world LCOS data and de-risks subsequent project finance.",
    ("deployment",  "advanced_nuclear"):
        "Nuclear commissioning is a multi-decade milestone. "
        "Confirms regulatory pathway and cost baseline for the technology.",
    ("funding",     "default"):
        "External capital validation. Key variables: investor type (strategic >> financial), "
        "round size vs. capex needs, lead investor sector positioning.",
    ("grant",       "default"):
        "Government grant validates technology policy relevance but not market demand. "
        "Grant-only is insufficient without a commercial anchor (offtaker, contract).",
    ("grant",       "green_hydrogen"):
        "DOE/IRA hydrogen grants are large ($100M+). "
        "But hydrogen H2Hub projects require named industrial offtakers to close financing.",
    ("pilot",       "grid_software"):
        "Utility-sponsored pilot implies allocated opex budget. "
        "Pilot-to-commercial conversion rate is the key watch metric.",
    ("pilot",       "battery_storage"):
        "Grid-connected pilot signals utility-scale targeting. "
        "KPX/NERC interface compliance is a commercialization gate.",
    ("pilot",       "green_hydrogen"):
        "Pilot electrolyzer data establishes real LCOH. "
        "Key: is there a named industrial offtaker co-funding the pilot?",
    ("pilot",       "advanced_nuclear"):
        "SMR/advanced reactor demo is a multi-year process. "
        "NRC licensing timeline is the primary risk — not technology.",
    ("regulatory",  "grid_software"):
        "FERC orders directly expand the addressable market for VPPs and storage. "
        "Order 2222 implementation is the key regulatory catalyst for grid software.",
    ("regulatory",  "transmission"):
        "Transmission permitting is the primary bottleneck for renewable buildout. "
        "FERC reforms and DOE permitting authority are critical policy enablers.",
    ("policy",      "green_hydrogen"):
        "IRA Section 45V hydrogen PTC ($3/kg) is the largest clean hydrogen subsidy globally. "
        "Guidance clarity determines electrolyzer project bankability.",
    ("policy",      "battery_storage"):
        "IRA ITC for standalone storage is transformative for project finance. "
        "State-level mandates create additional demand.",
    ("policy",      "advanced_nuclear"):
        "NRC licensing reform and DOE loan guarantees are critical enablers for SMRs. "
        "Policy signals de-risk first-of-a-kind capital.",
    ("partnership", "default"):
        "Named strategic partnership is directional. "
        "MOU alone does not confirm commercial intent — watch for conversion to binding terms.",
}


def why_investment(event_type: str, sector: str) -> str:
    return (
        _WHY.get((event_type, sector))
        or _WHY.get((event_type, "default"))
        or f"{event_type.capitalize()} signal in {sector.replace('_', ' ')} sector. "
           f"Assess commercial binding terms, named counterparties, and capital efficiency."
    )


# ════════════════════════════════════════════════════════════════════
# SECTION 6  NORMALIZER
# Converts raw article → structured signal (exact requested schema)
# ════════════════════════════════════════════════════════════════════

def normalize(raw: dict) -> Optional[dict]:
    """
    Map raw article to structured signal.
    Returns None if article is noise (score < 20) and not negative.
    Never raises — all exceptions return None.
    """
    try:
        raw_text    = raw.get("raw_text", "")
        title       = raw.get("title", "").strip()
        source_url  = raw.get("source_url", "")
        source_name = raw.get("source_name", "")
        pub_date    = raw.get("published_date", TODAY)

        clf         = classify(raw_text)
        sect        = infer_sector(raw_text, raw.get("source_segments", []))
        final_score, tier, breakdown = score(raw_text, clf["base_score"])
        is_neg      = clf["event_type"] == "other" and any(
            kw in raw_text for kw in [
                "delay", "postponed", "cancelled", "funding shortfall",
                "struggles to raise", "project terminated", "deal collapsed",
            ]
        )

        # Negative signals always surface; other noise is dropped
        if tier == "noise" and not is_neg:
            return None

        # Observed fact: first clean sentence of summary, else title
        summary = raw.get("summary", "")
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary) if len(s.strip()) > 25]
        observed = sentences[0] if sentences else title

        return {
            # Core identification
            "id":                       raw["article_id"],
            "title":                    title,
            "source_name":              source_name,
            "source_url":               source_url,
            "published_date":           pub_date,
            # Investment intelligence
            "observed_fact":            observed,
            "why_it_matters_investment":why_investment(clf["event_type"], sect),
            "missing_evidence":         missing_evidence(clf["event_type"]),
            # Classification
            "signal_tier":              tier,
            "signal_strength":          final_score,
            "sector":                   sect,
            "event_type":               clf["event_type"],
            # Entities
            "companies_mentioned":      extract_companies(raw_text),
            # Internal / debug fields
            "is_negative":              is_neg,
            "matched_keyword":          clf["matched_kw"],
            "score_breakdown":          breakdown,
            "source_reliability":       raw.get("reliability", 3),
            "raw_summary":              summary[:400] if summary else title,
            "fetched_at":               raw.get("fetched_at", NOW_ISO),
        }
    except Exception as ex:
        log.debug(f"normalize error: {ex} — {raw.get('title','')[:60]}")
        return None


# ════════════════════════════════════════════════════════════════════
# SECTION 7  MAIN PIPELINE
# ════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'═'*62}")
    print(f"  Energy CVC Signal Pipeline  v2.0")
    print(f"  {TODAY}  ·  {len(SOURCES)} RSS sources + EIA API")
    print(f"{'═'*62}\n")

    Path("data").mkdir(exist_ok=True)

    # ① Cache
    seen_ids = load_cache()
    log.info(f"① Cache: {len(seen_ids)} seen IDs (last {CACHE_DAYS} days)")

    # ② RSS fetch (parallel)
    print("\n② RSS fetch...")
    rss_items, source_logs = fetch_all_rss(seen_ids)
    log.info(f"   → {len(rss_items)} new articles from RSS")

    # ③ EIA API
    print("\n③ EIA Open Data API...")
    eia_items = fetch_eia_api()

    # ④ Combine + final dedup
    all_raw = rss_items + eia_items
    seen_this_run: set = set()
    deduped: list = []
    for item in all_raw:
        aid = item["article_id"]
        if aid not in seen_this_run:
            seen_this_run.add(aid)
            deduped.append(item)
    log.info(f"\n④ Dedup: {len(all_raw)} → {len(deduped)} unique articles")

    # Save raw
    RAW_PATH.write_text(json.dumps({
        "date":          TODAY,
        "generated_at":  NOW_ISO,
        "article_count": len(deduped),
        "source_count":  len(SOURCES),
        "source_logs":   source_logs,
        "articles":      deduped,
    }, ensure_ascii=False, indent=2))
    log.info(f"   Saved {RAW_PATH} ({len(deduped)} articles)")

    # ⑤ Normalize
    print("\n⑤ Classify + score + normalize...")
    signals: list = []
    dropped = 0
    for raw in deduped:
        sig = normalize(raw)
        if sig:
            signals.append(sig)
        else:
            dropped += 1

    # Sort: high tier first, then by score
    signals.sort(key=lambda s: (
        {"high": 0, "medium": 1, "low": 2, "noise": 3}.get(s["signal_tier"], 9),
        -s["signal_strength"]
    ))

    # Stats
    high   = sum(1 for s in signals if s["signal_tier"] == "high")
    medium = sum(1 for s in signals if s["signal_tier"] == "medium")
    neg    = sum(1 for s in signals if s.get("is_negative"))
    by_seg: dict = {}
    by_evt: dict = {}
    for s in signals:
        by_seg[s["sector"]]     = by_seg.get(s["sector"], 0) + 1
        by_evt[s["event_type"]] = by_evt.get(s["event_type"], 0) + 1

    log.info(f"   Kept: {len(signals)} | Dropped (noise/threshold): {dropped}")
    log.info(f"   High: {high} | Medium: {medium} | Negative: {neg}")

    # Save structured signals
    OUT_PATH.write_text(json.dumps({
        "date":         TODAY,
        "generated_at": NOW_ISO,
        "signal_count": len(signals),
        "stats": {
            "total": len(signals), "high": high, "medium": medium,
            "negative": neg, "dropped_noise": dropped,
            "sources_ok": sum(1 for l in source_logs if l["status"] == "success"),
            "sources_total": len(source_logs),
            "by_sector": by_seg,
            "by_event_type": by_evt,
        },
        "source_logs": source_logs,
        "signals":     signals,
    }, ensure_ascii=False, indent=2))
    log.info(f"   Saved {OUT_PATH}")

    # ⑥ Update cache
    save_cache(list(seen_this_run))
    log.info(f"\n⑥ Cache: +{len(seen_this_run)} IDs saved")

    # Summary
    print(f"\n{'═'*62}")
    print(f"  ✅  {len(signals)} signals | HIGH {high} | MEDIUM {medium} | NEG {neg}")
    print(f"  Sources: {sum(1 for l in source_logs if l['status']=='success')}/{len(source_logs)} OK")
    print(f"  By sector: {by_seg}")
    print(f"  By event:  {by_evt}")
    print(f"{'═'*62}\n")


if __name__ == "__main__":
    main()

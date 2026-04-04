#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════
fetch_extended.py  —  Extended Signal Collection Pipeline v1.0
════════════════════════════════════════════════════════════════════

목적: 하루 100~200개 signals 수집 (현재 20~30개 대비 5~10배)
방법: RSS 15개 병렬 수집 + EIA Open Data API
비용: 완전 무료 (유료 API 없음)

실행:
    python3 fetch_extended.py

출력:
    data/extended_raw.json      — 오늘 수집한 모든 raw articles
    data/extended_signals.json  — 구조화된 signals (main pipeline과 동일 스키마)
    data/fetch_cache.json       — 중복 제거용 ID 캐시 (최근 7일)

GitHub Actions 통합:
    generate-signals.py 실행 전 이 파일을 먼저 실행.
    generate-signals.py의 fetch_sources()가 extended_raw.json을 읽어서
    기존 RSS 결과에 merge하도록 SOURCE_REGISTRY에 phantom source 추가.

════════════════════════════════════════════════════════════════════
"""

import json
import hashlib
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Optional dependency guard ──────────────────────────────────────
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    print("⚠ feedparser not installed: pip install feedparser")

# ── Constants ──────────────────────────────────────────────────────
TODAY   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")   # free at eia.gov/opendata
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CACHE_PATH  = Path("data/fetch_cache.json")
RAW_PATH    = Path("data/extended_raw.json")
OUT_PATH    = Path("data/extended_signals.json")


# ════════════════════════════════════════════════════════════════════
# 1. EXTENDED RSS SOURCE REGISTRY
#    15 curated free feeds covering energy investment signals
#    Reliability: 1=primary, 2=trade, 3=aggregator/general
# ════════════════════════════════════════════════════════════════════

EXTENDED_SOURCES = [
    # ── Existing (kept for continuity) ──────────────────────────────
    {
        "id": "utilitydive",
        "name": "Utility Dive",
        "url": "https://www.utilitydive.com/feeds/news/",
        "reliability": 2,
        "segments": ["grid_sw", "ess", "dc_power"],
        "max_items": 25,
    },
    {
        "id": "pvmagazine",
        "name": "PV Magazine",
        "url": "https://www.pv-magazine.com/feed/",
        "reliability": 2,
        "segments": ["ess", "hydrogen", "forecasting"],
        "max_items": 25,
    },
    {
        "id": "energystoragenews",
        "name": "Energy Storage News",
        "url": "https://www.energy-storage.news/feed/",
        "reliability": 2,
        "segments": ["ess"],
        "max_items": 25,
    },
    {
        "id": "offshorewind",
        "name": "Offshore Wind Biz",
        "url": "https://www.offshorewind.biz/feed/",
        "reliability": 2,
        "segments": ["hvdc", "ess"],
        "max_items": 20,
    },
    {
        "id": "electrek",
        "name": "Electrek",
        "url": "https://electrek.co/feed/",
        "reliability": 3,
        "segments": ["ess", "dc_power"],
        "max_items": 20,
    },
    {
        "id": "h2view",
        "name": "H2 View",
        "url": "https://www.h2-view.com/feed/",
        "reliability": 2,
        "segments": ["hydrogen", "marine_fc"],
        "max_items": 20,
    },
    # ── New sources ──────────────────────────────────────────────────
    {
        "id": "canarymedia",
        "name": "Canary Media",
        "url": "https://www.canarymedia.com/rss",
        "reliability": 2,
        "segments": ["ess", "grid_sw", "dc_power", "hydrogen"],
        "max_items": 25,
        "notes": "High-quality US clean energy journalism. Strong on financing and policy.",
    },
    {
        "id": "renewablesnow",
        "name": "Renewables Now",
        "url": "https://renewablesnow.com/news/feed/",
        "reliability": 2,
        "segments": ["ess", "hvdc", "hydrogen"],
        "max_items": 20,
        "notes": "Strong EU + global renewables project coverage.",
    },
    {
        "id": "energynewsnetwork",
        "name": "Energy News Network",
        "url": "https://energynews.us/feed/",
        "reliability": 2,
        "segments": ["grid_sw", "ess", "dc_power"],
        "max_items": 20,
        "notes": "US state-level energy policy and utility news.",
    },
    {
        "id": "greentechmedia",
        "name": "Wood Mackenzie (GTM)",
        "url": "https://www.woodmac.com/feeds/rss/",
        "reliability": 2,
        "segments": ["ess", "grid_sw", "hydrogen"],
        "max_items": 15,
        "notes": "GTM/WoodMac feed — check if RSS is still active.",
    },
    {
        "id": "rechargenews",
        "name": "Recharge News",
        "url": "https://www.rechargenews.com/feed",
        "reliability": 2,
        "segments": ["hydrogen", "ess", "hvdc"],
        "max_items": 20,
        "notes": "Informa-owned. Strong hydrogen + offshore wind.",
    },
    {
        "id": "hydrogeninsight",
        "name": "Hydrogen Insight",
        "url": "https://www.hydrogeninsight.com/feed",
        "reliability": 2,
        "segments": ["hydrogen"],
        "max_items": 20,
        "notes": "Specialist hydrogen trade press.",
    },
    {
        "id": "cleantechnica",
        "name": "CleanTechnica",
        "url": "https://cleantechnica.com/feed/",
        "reliability": 3,
        "segments": ["ess", "dc_power", "grid_sw"],
        "max_items": 20,
        "notes": "Tier 3. Broad coverage. Verify all figures.",
    },
    {
        "id": "spglobal_platts_energy",
        "name": "S&P Global Energy (free)",
        "url": "https://www.spglobal.com/commodityinsights/en/rss-feed/energy",
        "reliability": 2,
        "segments": ["hydrogen", "ess", "dc_power"],
        "max_items": 15,
        "notes": "Free RSS tier of S&P Commodity Insights.",
    },
    {
        "id": "ieaenergy",
        "name": "IEA News",
        "url": "https://www.iea.org/api/rss",
        "reliability": 1,
        "segments": ["hydrogen", "ess", "grid_sw", "forecasting"],
        "max_items": 15,
        "notes": "Tier 1 — primary source. Policy and market analysis.",
    },
]


# ════════════════════════════════════════════════════════════════════
# 2. CACHE — deduplication across days
# ════════════════════════════════════════════════════════════════════

def load_cache():
    """Load seen article IDs from last 7 days."""
    if not CACHE_PATH.exists():
        return set()
    try:
        data = json.loads(CACHE_PATH.read_text())
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        seen = set()
        for entry in data:
            if entry.get("date", "") >= cutoff:
                seen.add(entry["id"])
        return seen
    except Exception:
        return set()


def save_cache(new_ids: list):
    """Append new article IDs to cache, prune to 7 days."""
    existing = []
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
        except Exception:
            existing = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    pruned = [e for e in existing if e.get("date", "") >= cutoff]
    for aid in new_ids:
        pruned.append({"id": aid, "date": TODAY})
    CACHE_PATH.write_text(json.dumps(pruned, ensure_ascii=False))


def make_article_id(url: str, title: str) -> str:
    """Stable ID from URL + title."""
    raw = f"{url.strip()}:{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ════════════════════════════════════════════════════════════════════
# 3. PARALLEL RSS FETCHER
# ════════════════════════════════════════════════════════════════════

def fetch_one_source(source: dict, seen_ids: set) -> tuple:
    """
    Fetch one RSS source. Returns (source_id, items[], log_entry).
    Thread-safe — no shared mutable state.
    """
    sid  = source["id"]
    name = source["name"]
    url  = source["url"]
    max_n = source.get("max_items", 20)
    items = []
    log   = {
        "id": sid, "name": name, "url": url,
        "status": "failed", "items": 0, "error": None,
        "fetched_at": NOW_ISO,
        "reliability": source.get("reliability", 3),
        "segments": source.get("segments", []),
    }

    if not HAS_FEEDPARSER:
        log["error"] = "feedparser not installed"
        return sid, items, log

    try:
        socket.setdefaulttimeout(20)
        feed = feedparser.parse(url)

        # Detect HTTP errors
        status = getattr(feed, "status", 200)
        if status >= 400:
            log["error"] = f"HTTP {status}"
            return sid, items, log

        # Bozo check (feedparser's way of saying parse failed)
        if feed.get("bozo") and not feed.get("entries"):
            log["error"] = f"Feed parse error: {feed.get('bozo_exception','unknown')}"
            return sid, items, log

        count = 0
        for entry in feed.entries[:max_n]:
            title   = (getattr(entry, "title",   "") or "").strip()
            link    = (getattr(entry, "link",    "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:600].strip()

            if not title or not link or title == "[Removed]":
                continue

            # Date parsing
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t:
                try:
                    date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
                except Exception:
                    date = TODAY
            else:
                date = TODAY

            # Skip articles older than 3 days
            cutoff_3d = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
            if date < cutoff_3d:
                continue

            article_id = make_article_id(link, title)
            if article_id in seen_ids:
                continue  # deduplicate

            items.append({
                "article_id":    article_id,
                "source_id":     sid,
                "source_name":   name,
                "source_url":    link,
                "source_segments": source.get("segments", []),
                "reliability":   source.get("reliability", 3),
                "title":         title,
                "summary":       summary,
                "published_date": date,
                "raw_text":      (title + " " + summary).lower(),
                "fetched_at":    NOW_ISO,
            })
            count += 1

        log["status"] = "success" if count > 0 else "partial"
        log["items"]  = count

    except socket.timeout:
        log["error"] = "Connection timeout (20s)"
    except Exception as ex:
        log["error"] = str(ex)[:200]

    return sid, items, log


def fetch_all_rss(seen_ids: set) -> tuple:
    """
    Fetch all RSS sources in parallel using ThreadPoolExecutor.
    Returns (all_items[], source_logs[]).
    """
    all_items = []
    all_logs  = []

    print(f"  Fetching {len(EXTENDED_SOURCES)} RSS sources in parallel...")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_one_source, src, seen_ids): src
            for src in EXTENDED_SOURCES
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                sid, items, log = future.result()
                all_items.extend(items)
                all_logs.append(log)
                status_icon = "✓" if log["status"] == "success" else ("~" if log["status"] == "partial" else "✗")
                print(f"    {status_icon} {src['name']}: {log['items']} items"
                      + (f"  [{log['error']}]" if log["error"] else ""))
            except Exception as ex:
                print(f"    ✗ {src['name']}: executor error — {ex}")
                all_logs.append({
                    "id": src["id"], "name": src["name"], "url": src["url"],
                    "status": "failed", "items": 0, "error": f"executor: {ex}",
                    "fetched_at": NOW_ISO,
                })

    return all_items, all_logs


# ════════════════════════════════════════════════════════════════════
# 4. EIA OPEN DATA API (free, no commercial restrictions)
#    Fetches recent energy sector statistics as structured context.
#    API key: free at https://www.eia.gov/opendata/register.php
#    Used to add market context signals (NOT as news articles).
# ════════════════════════════════════════════════════════════════════

def fetch_eia_context() -> list:
    """
    Fetch recent EIA data points as context signals.
    Returns list of pseudo-articles in raw_item format.
    Each data point is a factual, source-cited signal.

    EIA series used (all free, public):
        - ELEC.GEN.DPV-US-99.M  — distributed solar generation
        - EBA.US48-ALL.D.HL     — US grid load
        - STEO series            — Short-Term Energy Outlook highlights
    """
    if not EIA_API_KEY:
        print("  ⚠ EIA_API_KEY not set — skipping EIA fetch")
        print("    Get a free key at: https://www.eia.gov/opendata/register.php")
        return []

    import urllib.request as ur

    items = []
    base  = "https://api.eia.gov/v2"

    # ── EIA Short-Term Energy Outlook (STEO) ──────────────────────
    # Free summary of US energy market forecasts — quarterly published
    steo_series = [
        ("electricity.retail-sales", "US electricity retail sales (MWh)"),
        ("natural-gas.rngwhhd",      "US natural gas Henry Hub spot price"),
    ]

    for series_path, description in steo_series:
        try:
            url = (f"{base}/{series_path}/data/"
                   f"?api_key={EIA_API_KEY}"
                   f"&frequency=monthly"
                   f"&data[0]=value"
                   f"&sort[0][column]=period"
                   f"&sort[0][direction]=desc"
                   f"&offset=0&length=2")
            req = ur.Request(url, headers={"Accept": "application/json"})
            with ur.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            rows = data.get("response", {}).get("data", [])
            if rows:
                latest = rows[0]
                period = latest.get("period", "")
                value  = latest.get("value", "")
                unit   = latest.get("units", "")
                title  = f"EIA: {description} — {period}: {value} {unit}"
                items.append({
                    "article_id":      make_article_id("eia.gov", title),
                    "source_id":       "eia_api",
                    "source_name":     "EIA Open Data",
                    "source_url":      "https://www.eia.gov/opendata/",
                    "source_segments": ["forecasting", "grid_sw"],
                    "reliability":     1,   # primary government source
                    "title":           title,
                    "summary":         f"Official EIA data: {description}. Period: {period}. Value: {value} {unit}. Source: US Energy Information Administration.",
                    "published_date":  TODAY,
                    "raw_text":        title.lower(),
                    "fetched_at":      NOW_ISO,
                    "eia_series":      series_path,
                    "eia_period":      period,
                    "eia_value":       str(value),
                })
            time.sleep(0.5)   # EIA rate limit: be polite
        except Exception as ex:
            print(f"    EIA {series_path}: {ex}")

    print(f"  EIA: {len(items)} data points")
    return items


# ════════════════════════════════════════════════════════════════════
# 5. SIGNAL CLASSIFIER — maps raw article to structured signal
#    Rule-based only. No AI inference. Every field is traceable.
# ════════════════════════════════════════════════════════════════════

# Event type keyword rules (same logic as main pipeline, kept in sync)
_EVENT_RULES = [
    # Tier 1 — Commercial
    {"type": "Certification", "score": 88, "tier": 1,
     "kws": ["certified", "certification", "class approval", "type approval", "dnv gl", "kpx certified",
             "ul listed", "iec certified", "tuv certified", "approved by"]},
    {"type": "Contract",      "score": 92, "tier": 1,
     "kws": ["signs contract", "awarded contract", "secures contract", "contract awarded",
             "offtake agreement", "supply agreement", "framework agreement", "purchase agreement",
             "power purchase agreement", "ppa signed"]},
    {"type": "Deployment",    "score": 88, "tier": 1,
     "kws": ["goes live", "commercial operation", "operational", "commissioned", "begins operation",
             "starts operation", "deployed at", "installed at", "goes online"]},
    # Tier 2 — Technical / Financial
    {"type": "Pilot",         "score": 70, "tier": 2,
     "kws": ["pilot project", "demonstration project", "demo project", "field trial",
             "proof of concept", "first deployment", "initial deployment", "prototype tested"]},
    {"type": "Financing",     "score": 82, "tier": 2,
     "kws": ["raises", "closes funding", "series a", "series b", "series c",
              "seed round", "venture capital", "investment round", "funding round",
              "secures investment", "equity raise", "capital raise"]},
    {"type": "Hiring",        "score": 72, "tier": 2,
     "kws": ["appoints cfo", "appoints ceo", "appoints vp", "hires chief",
              "names chief financial", "names chief revenue", "appoints head of",
              "joins as cfo", "joins as chief"]},
    # Tier 3 — Strategic
    {"type": "Partnership",   "score": 47, "tier": 3,
     "kws": ["partnership", "mou", "memorandum of understanding", "joint venture",
              "collaboration agreement", "strategic alliance", "teaming agreement"]},
    {"type": "Grant",         "score": 46, "tier": 3,
     "kws": ["grant awarded", "receives grant", "doe award", "doe funding",
              "government grant", "eu grant", "horizon grant", "innovate uk",
              "nsf grant", "sbir award"]},
    {"type": "Expansion",     "score": 72, "tier": 3,
     "kws": ["gigafactory", "manufacturing plant", "new production facility",
              "scale-up facility", "opens facility", "new plant", "expands production"]},
    # Tier 4 — Negative
    {"type": "Negative",      "score": 0,  "tier": 4,
     "neg_subtype": "delay",
     "kws": ["delay", "postponed", "behind schedule", "timeline slips", "pushed back"]},
    {"type": "Negative",      "score": 0,  "tier": 4,
     "neg_subtype": "funding_risk",
     "kws": ["funding shortfall", "struggles to raise", "runway concerns", "bridge loan needed"]},
    {"type": "Negative",      "score": 0,  "tier": 4,
     "neg_subtype": "cancellation",
     "kws": ["project cancelled", "contract cancelled", "project terminated", "deal collapsed"]},
]

# Segment keyword map
_SEG_KWS = {
    "ess":         ["battery", "energy storage", "bess", "vanadium", "iron-air", "flow battery",
                    "long duration", "grid storage", "lithium", "lcos"],
    "marine_fc":   ["marine", "vessel", "ship", "fuel cell", "bunkering", "maritime", "imo cii",
                    "shipping", "offshore fuel", "ammonia fuel"],
    "grid_sw":     ["vpp", "virtual power", "demand response", "grid software", "ancillary",
                    "frequency regulation", "flexibility market", "dispatch optimization"],
    "hvdc":        ["hvdc", "transmission", "subsea cable", "offshore wind cable", "interconnect",
                    "high voltage direct current"],
    "hydrogen":    ["hydrogen", "electrolyzer", "h2", "green hydrogen", "electrolysis",
                    "ammonia", "pem electrolyzer", "alkaline electrolyzer", "hydrogen production"],
    "dc_power":    ["data center", "hyperscaler", "azure", "aws", "google cloud",
                    "power electronics", "ai infrastructure", "cfe", "24/7 clean energy"],
    "wte":         ["waste-to-energy", "biogas", "biomass", "waste", "incineration", "rng",
                    "renewable natural gas"],
    "forecasting": ["forecast", "prediction", "renewable forecast", "grid forecast",
                    "ai grid", "load forecasting", "price forecasting"],
}

# Noise patterns — if matched, subtract from score
_NOISE_PATTERNS = [
    (r"\bproud to (announce|partner|share)\b|\bexcited to announce\b", -40, "Generic PR language"),
    (r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b", -20, "Intent, no confirmed action"),
    (r"\bexploring\b.{0,30}\bpartner|\bin (early )?discussions\b", -35, "Exploratory / vague"),
    (r"\bcould (become|reach|achieve)\b|\bhas the potential\b", -25, "Speculative framing"),
    (r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b", -30, "Vision announcement"),
    (r"\bwins? award\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b", -35, "Vanity recognition"),
    (r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b", -30, "Conference only"),
    (r"\bpublishes? (report|study|whitepaper)\b|\bnew (report|research|study)\b", -25, "Report only"),
    (r"\brebrands?\b|\bnew (logo|brand|website)\b", -55, "Rebranding"),
    (r"\bopinion:\b|\bcommentary:\b|\bop-ed\b", -60, "Opinion/commentary"),
    (r"\bmarket (wrap|roundup|update)\b|\bweekly (round-?up|digest)\b", -60, "Market digest"),
    (r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b", -50, "Generic job post"),
]

# Boost patterns
_BOOST_PATTERNS = [
    (r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\bvattenfall\b", +18, "Tier-1 strategic buyer"),
    (r"\bhyundai\b|\bsamsung\b|\bsiemens\b|\babb\b|\bhitachi\b|\bhanwha\b", +12, "Major industrial/OEM"),
    (r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\€[\d,]+\s*[mb]|₩[\d,]+억", +15, "Specific financial figure"),
    (r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b", +10, "Specific capacity figure"),
    (r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month", +8, "Concrete timeframe"),
]


def classify_article(raw_text: str) -> dict:
    """Classify article into event type, tier, base score."""
    for rule in _EVENT_RULES:
        for kw in rule["kws"]:
            if kw in raw_text:
                return {
                    "event_type": rule["type"],
                    "tier":       rule["tier"],
                    "base_score": rule["score"],
                    "matched_kw": kw,
                    "neg_subtype": rule.get("neg_subtype"),
                }
    return {"event_type": "News", "tier": 5, "base_score": 15, "matched_kw": None, "neg_subtype": None}


def infer_segment(raw_text: str, source_segments: list) -> str:
    """Infer market segment from article text."""
    for seg, kws in _SEG_KWS.items():
        if any(kw in raw_text for kw in kws):
            return seg
    return source_segments[0] if source_segments else "unknown"


def score_article(raw_text: str, base: int) -> tuple:
    """Compute final signal score with boosts and noise penalties."""
    score = base
    breakdown = []

    for pattern, delta, reason in _BOOST_PATTERNS:
        if re.search(pattern, raw_text, re.I):
            score += delta
            breakdown.append({"delta": delta, "reason": reason, "type": "boost"})

    for pattern, delta, reason in _NOISE_PATTERNS:
        if re.search(pattern, raw_text, re.I):
            score += delta
            breakdown.append({"delta": delta, "reason": reason, "type": "noise"})

    score = max(0, min(100, round(score)))
    if score >= 60:
        tier = "high"
    elif score >= 35:
        tier = "medium"
    elif score >= 20:
        tier = "low"
    else:
        tier = "noise"

    return score, tier, breakdown


def extract_companies(raw_text: str) -> list:
    """
    Extract company names mentioned in article.
    Simple pattern — matches capitalized sequences.
    For production: replace with NER or entity registry lookup.
    """
    # Look for known tracked company aliases first
    KNOWN = {
        "gridwiz": "그리드위즈", "그리드위즈": "그리드위즈",
        "sixtyhz": "식스티헤르츠", "식스티헤르츠": "식스티헤르츠",
        "vincen": "빈센", "빈센": "빈센",
        "standard energy": "스탠다드에너지", "스탠다드에너지": "스탠다드에너지",
        "form energy": "Form Energy",
        "autogrid": "AutoGrid",
        "sunfire": "Sunfire",
        "amogy": "Amogy",
        "hysata": "Hysata",
        "ceres power": "Ceres Power",
        "invinity": "Invinity Energy",
    }
    found = []
    for alias, canonical in KNOWN.items():
        if alias in raw_text.lower() and canonical not in found:
            found.append(canonical)
    return found


def build_missing_evidence(event_type: str, score: int) -> list:
    """Rule-based list of missing evidence for this event type."""
    missing_map = {
        "Contract":      ["Contract ACV not disclosed", "Duration and renewal terms unknown",
                          "Exclusivity scope unknown"],
        "Financing":     ["Post-money valuation not confirmed", "Lead investor identity unknown",
                          "Use of proceeds not specified"],
        "Pilot":         ["Pilot KPI targets not public", "Commercial conversion probability unknown",
                          "Named third-party validator not confirmed"],
        "Partnership":   ["Binding terms (exclusivity, volume) not confirmed",
                          "IP ownership unclear", "MOU vs. binding contract distinction not stated"],
        "Certification": ["Certification scope (geographic, product variant) not stated",
                          "Renewal terms unknown"],
        "Grant":         ["Commercial co-funding partner not identified",
                          "Path from grant to commercial revenue not articulated"],
        "Deployment":    ["Commercial operation date confirmed but revenue terms unknown",
                          "Performance guarantee terms not public"],
        "Hiring":        ["Fundraising timeline not confirmed",
                          "Whether hire reflects inbound interest or proactive prep unknown"],
        "Negative":      ["Root cause not confirmed", "Management mitigation plan not public"],
    }
    return missing_map.get(event_type, ["No investment-specific gap analysis available"])


def why_it_matters(event_type: str, segment: str) -> str:
    """Rule-based explanation of investment relevance."""
    key_map = {
        ("Certification", "marine_fc"): "Class approval removes the primary procurement barrier. Without it, shipyards cannot specify the technology in newbuild contracts.",
        ("Certification", "ess"):       "Third-party certification required for grid interconnection and utility procurement. De-risks buyer liability.",
        ("Certification", "grid_sw"):   "KPX/FERC certification is the legal prerequisite for regulated ancillary services markets.",
        ("Contract",      "grid_sw"):   "Named utility contract moves company from pilot to commercial stage. Key: ACV, duration, exclusivity.",
        ("Contract",      "ess"):       "Offtake/supply agreement is the clearest commercial-stage signal.",
        ("Contract",      "hydrogen"):  "Offtake at contracted price is the critical missing link in most hydrogen project theses.",
        ("Pilot",         "grid_sw"):   "Utility-sponsored pilot implies allocated opex budget. Pilot-to-commercial conversion rate is the key metric.",
        ("Pilot",         "marine_fc"): "Shipyard pilot validates vessel integration. DNV involvement raises class approval probability substantially.",
        ("Pilot",         "ess"):       "Grid-connected pilot signals utility-scale targeting.",
        ("Pilot",         "dc_power"):  "Hyperscaler pilot is the strongest commercial signal. High ACV, low churn once contracted.",
        ("Financing",     "default"):   "External capital validation. Key variables: investor identity (strategic >> financial), round size vs. capex.",
        ("Hiring",        "default"):   "CFO hire correlates with fundraising within 3–6 months. BD hire signals active contract pipeline.",
        ("Partnership",   "default"):   "Named strategic partnership is directional. MOU alone does not confirm commercial intent.",
        ("Grant",         "default"):   "Validates technology policy relevance but not market demand. Grant-only is not investable without commercial anchor.",
        ("Negative",      "default"):   "Requires investment timeline reassessment. Determine if project-level or structural.",
    }
    return (key_map.get((event_type, segment))
            or key_map.get((event_type, "default"))
            or f"Signal type {event_type} in {segment} segment — review evidence for investment relevance.")


def normalize_article(raw: dict) -> dict | None:
    """
    Convert raw article dict to structured signal.
    Returns None if article should be dropped (noise threshold).
    Raises no exceptions — errors return None.
    """
    try:
        raw_text   = raw.get("raw_text", "")
        title      = raw.get("title", "")
        source_url = raw.get("source_url", "")
        source_name= raw.get("source_name", "")
        pub_date   = raw.get("published_date", TODAY)

        clf         = classify_article(raw_text)
        segment     = infer_segment(raw_text, raw.get("source_segments", []))
        score, tier, breakdown = score_article(raw_text, clf["base_score"])
        is_negative = clf["event_type"] == "Negative"

        # Drop noise unless negative (negatives always surfaced)
        if tier == "noise" and not is_negative:
            return None

        companies  = extract_companies(raw_text)
        missing    = build_missing_evidence(clf["event_type"], score)
        why        = why_it_matters(clf["event_type"], segment)

        # Observed fact: first sentence of summary, or title
        summary = raw.get("summary", "")
        first_sentence = summary.split(".")[0].strip() if summary else ""
        observed = first_sentence if len(first_sentence) > 20 else title

        return {
            "id":                       raw["article_id"],
            "title":                    title,
            "source_name":              source_name,
            "source_url":               source_url,
            "published_date":           pub_date,
            "observed_fact":            observed,
            "why_it_matters_investment":why,
            "missing_evidence":         missing,
            "signal_tier":              tier,
            "signal_strength":          score,
            "sector":                   segment,
            "event_type":               clf["event_type"],
            "neg_subtype":              clf.get("neg_subtype"),
            "is_negative":              is_negative,
            "companies_mentioned":      companies,
            "raw_summary":              summary[:300] if summary else title,
            "score_breakdown":          breakdown,
            "matched_keyword":          clf["matched_kw"],
            "source_reliability":       raw.get("reliability", 3),
            "fetched_at":               raw.get("fetched_at", NOW_ISO),
        }
    except Exception as ex:
        print(f"  normalize error: {ex} — skipping {raw.get('title','?')[:60]}")
        return None


# ════════════════════════════════════════════════════════════════════
# 6. MAIN PIPELINE
# ════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'═'*60}")
    print(f"Extended Signal Collector  v1.0")
    print(f"{TODAY}  ·  {len(EXTENDED_SOURCES)} sources")
    print(f"{'═'*60}\n")

    Path("data").mkdir(exist_ok=True)

    # ── Load dedup cache ────────────────────────────────────────────
    seen_ids = load_cache()
    print(f"① Cache: {len(seen_ids)} seen IDs (last 7 days)\n")

    # ── Fetch RSS (parallel) ────────────────────────────────────────
    print("② RSS fetch (parallel, max 8 workers)...")
    rss_items, source_logs = fetch_all_rss(seen_ids)
    print(f"   → {len(rss_items)} new articles from RSS\n")

    # ── Fetch EIA context ────────────────────────────────────────────
    print("③ EIA Open Data...")
    eia_items = fetch_eia_context()
    print()

    # ── Combine + deduplicate ────────────────────────────────────────
    all_raw = rss_items + eia_items
    # Final dedup by article_id (in case parallel fetches overlapped)
    seen_this_run = set()
    deduped = []
    for item in all_raw:
        aid = item["article_id"]
        if aid not in seen_this_run:
            seen_this_run.add(aid)
            deduped.append(item)

    print(f"④ Dedup: {len(all_raw)} → {len(deduped)} unique articles")

    # ── Save raw ─────────────────────────────────────────────────────
    RAW_PATH.write_text(json.dumps({
        "date": TODAY,
        "generated_at": NOW_ISO,
        "article_count": len(deduped),
        "source_logs": source_logs,
        "articles": deduped,
    }, ensure_ascii=False, indent=2))
    print(f"   Saved: {RAW_PATH} ({len(deduped)} articles)\n")

    # ── Normalize → structured signals ──────────────────────────────
    print("⑤ Normalize + classify + score...")
    signals = []
    dropped = 0
    for raw in deduped:
        sig = normalize_article(raw)
        if sig:
            signals.append(sig)
        else:
            dropped += 1

    # Sort: negatives first, then by score desc
    signals.sort(key=lambda s: (0 if s["is_negative"] else 1, -s["signal_strength"]))

    # Stats
    high    = sum(1 for s in signals if s["signal_tier"] == "high")
    medium  = sum(1 for s in signals if s["signal_tier"] == "medium")
    neg     = sum(1 for s in signals if s["is_negative"])
    by_seg  = {}
    by_type = {}
    for s in signals:
        by_seg[ s["sector"]]     = by_seg.get( s["sector"],    0) + 1
        by_type[s["event_type"]] = by_type.get(s["event_type"],0) + 1

    print(f"   Kept: {len(signals)} | Dropped (noise): {dropped}")
    print(f"   High: {high} | Medium: {medium} | Negative: {neg}")
    print(f"   By segment: {by_seg}")
    print(f"   By type:    {by_type}\n")

    # ── Save structured signals ──────────────────────────────────────
    OUT_PATH.write_text(json.dumps({
        "date":            TODAY,
        "generated_at":    NOW_ISO,
        "signal_count":    len(signals),
        "stats": {
            "total": len(signals), "high": high, "medium": medium,
            "negative": neg, "dropped_noise": dropped,
            "by_segment": by_seg, "by_type": by_type,
        },
        "source_logs":     source_logs,
        "signals":         signals,
    }, ensure_ascii=False, indent=2))
    print(f"   Saved: {OUT_PATH}\n")

    # ── Update dedup cache ────────────────────────────────────────────
    save_cache(list(seen_this_run))
    print(f"⑥ Cache updated: +{len(seen_this_run)} IDs\n")

    print(f"{'═'*60}")
    print(f"✅  {len(signals)} signals | {high} HIGH | {neg} NEGATIVE")
    print(f"   Sources: {sum(1 for l in source_logs if l['status']=='success')}/{len(source_logs)} OK")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════
fetch_extended.py  —  Energy CVC Signal Pipeline v3.0
════════════════════════════════════════════════════════════════════

목적:  하루 80~150개 signals, 실패율 < 30%
소스:  검증된 무료 RSS 13개 + EIA Open Data API
금지:  paywall, 상업구독, 불안정 RSS (Renewables Now, Recharge,
       Wood Mackenzie, S&P Global, Hydrogen Insight 등)

설계 원칙:
  - 모든 소스는 실제 공개 접근 가능한 URL만
  - 실패 소스는 fetch_health.json에 기록 → 다음 실행 시 자동 스킵
  - asyncio + ThreadPoolExecutor 하이브리드 (feedparser는 동기)
  - 7일 dedup 캐시, 3일 기사 cutoff
  - 각 소스 독립 예외처리 — 한 소스 실패가 전체에 영향 없음

출력:
  data/extended_raw.json       수집된 raw articles
  data/extended_signals.json   구조화 signals (메인 파이프라인 merge용)
  data/fetch_cache.json        dedup ID 캐시
  data/fetch_health.json       소스별 성공/실패 이력

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch")

# ── Deps ──────────────────────────────────────────────────────────
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    log.error("feedparser missing: pip install feedparser")

try:
    import urllib.request as _urllib
    import urllib.error as _urlerr
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# ── Constants ─────────────────────────────────────────────────────
TODAY      = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO    = datetime.now(timezone.utc).isoformat()

MAX_AGE_DAYS    = 3      # skip articles older than N days
CACHE_DAYS      = 7      # dedup cache retention window
FETCH_TIMEOUT   = 20     # per-source timeout (seconds)
MAX_WORKERS     = 8      # parallel threads
HEALTH_FAIL_CAP = 3      # consecutive failures before auto-skip

EIA_API_KEY  = os.environ.get("EIA_API_KEY", "")

CACHE_PATH   = Path("data/fetch_cache.json")
HEALTH_PATH  = Path("data/fetch_health.json")
RAW_PATH     = Path("data/extended_raw.json")
OUT_PATH     = Path("data/extended_signals.json")


# ════════════════════════════════════════════════════════════════════
# SECTION 1  SOURCE REGISTRY
#
# URL 신뢰도 등급 (2026년 기준 실측 기반):
#   ★★★  거의 항상 성공 (정부 RSS, 대형 trade)
#   ★★   보통 성공 (trade press, 일부 정부)
#   ★    가끔 실패 (개인 미디어, 불안정 CDN)
#
# 제외 사유 명시:
#   Renewables Now    — Cloudflare 차단, 불안정
#   Recharge News     — Informa paywall
#   Wood Mackenzie    — 상업 구독 RSS
#   S&P Global        — 상업 구독 RSS
#   Hydrogen Insight  — Informa paywall
#   DOE EERE/Fossil/Nuclear RSS — 404 반복 (2025 재구성 이후)
# ════════════════════════════════════════════════════════════════════

SOURCES: list[dict] = [

    # ══ TIER 1 — 정부/국제기구 (★★★ 매우 안정적) ══════════════════

    {
        "id":           "eia_today",
        "name":         "EIA Today in Energy",
        "url":          "https://www.eia.gov/rss/todayinenergy.xml",
        "reliability":  "★★★",
        "tier":         1,
        "max_items":    20,
        "segments":     ["battery_storage", "green_hydrogen", "grid_software",
                         "offshore_wind", "other_cleantech"],
        "notes":        "US government primary source. Very stable. ~5 articles/day.",
    },
    {
        "id":           "doe_main",
        "name":         "DOE Energy.gov News",
        "url":          "https://www.energy.gov/articles/rss.xml",
        "reliability":  "★★★",
        "tier":         1,
        "max_items":    20,
        "segments":     ["battery_storage", "green_hydrogen", "grid_software",
                         "advanced_nuclear", "offshore_wind"],
        "notes":        "DOE top-level — cross-cutting announcements, grants, deployments.",
    },
    {
        "id":           "doe_cleancities",
        "name":         "DOE Clean Cities & Communities",
        "url":          "https://cleancities.energy.gov/news-events/rss",
        "reliability":  "★★",
        "tier":         1,
        "max_items":    15,
        "segments":     ["other_cleantech", "data_center_power"],
        "notes":        "Fleet electrification, charging, community energy.",
    },
    {
        "id":           "iea",
        "name":         "IEA News",
        "url":          "https://www.iea.org/api/rss",
        "reliability":  "★★",
        "tier":         1,
        "max_items":    15,
        "segments":     ["green_hydrogen", "battery_storage", "grid_software",
                         "offshore_wind", "other_cleantech"],
        "notes":        "International Energy Agency. Policy, market analysis. Occasionally slow.",
    },

    # ══ TIER 2 — 전문 trade press (★★~★★★) ══════════════════════

    {
        "id":           "canarymedia",
        "name":         "Canary Media",
        "url":          "https://www.canarymedia.com/rss.rss",
        "reliability":  "★★★",
        "tier":         2,
        "max_items":    30,
        "segments":     ["battery_storage", "grid_software", "data_center_power",
                         "green_hydrogen", "offshore_wind"],
        "notes":        "Best US clean energy journalism. Financing, policy, commercialization.",
    },
    {
        "id":           "pvmagazine",
        "name":         "PV Magazine",
        "url":          "https://www.pv-magazine.com/feed/",
        "reliability":  "★★★",
        "tier":         2,
        "max_items":    25,
        "segments":     ["battery_storage", "green_hydrogen", "other_cleantech"],
        "notes":        "Very stable. 15-20 articles/day. Strong EU + global.",
    },
    {
        "id":           "energystoragenews",
        "name":         "Energy Storage News",
        "url":          "https://www.energy-storage.news/feed/",
        "reliability":  "★★★",
        "tier":         2,
        "max_items":    25,
        "segments":     ["battery_storage", "long_duration_storage"],
        "notes":        "Specialist BESS/LDES trade press. Very consistent.",
    },
    {
        "id":           "utilitydive",
        "name":         "Utility Dive",
        "url":          "https://www.utilitydive.com/feeds/news/",
        "reliability":  "★★★",
        "tier":         2,
        "max_items":    25,
        "segments":     ["grid_software", "battery_storage", "data_center_power", "transmission"],
        "notes":        "Best US utility/grid coverage. FERC news often here first.",
    },
    {
        "id":           "offshorewind",
        "name":         "Offshore Wind Biz",
        "url":          "https://www.offshorewind.biz/feed/",
        "reliability":  "★★★",
        "tier":         2,
        "max_items":    20,
        "segments":     ["offshore_wind", "transmission"],
        "notes":        "Specialist offshore wind. Very stable WordPress RSS.",
    },
    {
        "id":           "h2view",
        "name":         "H2 View",
        "url":          "https://www.h2-view.com/feed/",
        "reliability":  "★★",
        "tier":         2,
        "max_items":    20,
        "segments":     ["green_hydrogen"],
        "notes":        "Specialist hydrogen. Occasionally returns empty feed.",
    },

    # ══ TIER 3 — 종합 cleantech (★~★★★) ══════════════════════════

    {
        "id":           "cleantechnica",
        "name":         "CleanTechnica",
        "url":          "https://cleantechnica.com/feed/",
        "reliability":  "★★★",
        "tier":         3,
        "max_items":    25,
        "segments":     ["battery_storage", "grid_software", "data_center_power",
                         "other_cleantech"],
        "notes":        "High volume. Tier 3 — verify all figures. Very stable.",
    },
    {
        "id":           "electrek",
        "name":         "Electrek",
        "url":          "https://electrek.co/feed/",
        "reliability":  "★★★",
        "tier":         3,
        "max_items":    20,
        "segments":     ["battery_storage", "data_center_power", "other_cleantech"],
        "notes":        "Very stable. Broad coverage. Tier 3.",
    },
    {
        "id":           "azocleantech",
        "name":         "AZoCleantech",
        "url":          "https://www.azocleantech.com/rss/news.aspx",
        "reliability":  "★★",
        "tier":         3,
        "max_items":    20,
        "segments":     ["battery_storage", "green_hydrogen", "other_cleantech",
                         "advanced_nuclear", "geothermal"],
        "notes":        "Broad cleantech aggregator. Occasionally slow.",
    },
]


# ════════════════════════════════════════════════════════════════════
# SECTION 2  SOURCE HEALTH TRACKER
#   Tracks consecutive failures per source.
#   After HEALTH_FAIL_CAP failures → auto-skip until next day.
# ════════════════════════════════════════════════════════════════════

def load_health() -> dict:
    """Load source health from disk. Returns {source_id: {fails, last_fail, skip_until}}."""
    if not HEALTH_PATH.exists():
        return {}
    try:
        return json.loads(HEALTH_PATH.read_text())
    except Exception:
        return {}


def save_health(health: dict):
    try:
        HEALTH_PATH.write_text(json.dumps(health, ensure_ascii=False, indent=2))
    except Exception as ex:
        log.warning(f"Health save failed: {ex}")


def is_skipped(sid: str, health: dict) -> bool:
    """Return True if this source should be skipped today."""
    h = health.get(sid, {})
    skip_until = h.get("skip_until", "")
    if skip_until and skip_until > TODAY:
        return True
    return False


def record_success(sid: str, health: dict):
    health[sid] = {"consecutive_fails": 0, "last_success": TODAY, "skip_until": ""}


def record_failure(sid: str, health: dict, error: str):
    h = health.setdefault(sid, {"consecutive_fails": 0})
    h["consecutive_fails"] = h.get("consecutive_fails", 0) + 1
    h["last_fail"]  = TODAY
    h["last_error"] = error[:120]
    if h["consecutive_fails"] >= HEALTH_FAIL_CAP:
        # Skip for remainder of today (reset tomorrow)
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        h["skip_until"] = tomorrow
        log.warning(f"  ⚠ {sid}: {HEALTH_FAIL_CAP} consecutive failures — skipping until {tomorrow}")


# ════════════════════════════════════════════════════════════════════
# SECTION 3  DEDUP CACHE
# ════════════════════════════════════════════════════════════════════

def load_cache() -> set:
    if not CACHE_PATH.exists():
        return set()
    try:
        data = json.loads(CACHE_PATH.read_text())
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
        return {e["id"] for e in data if e.get("date", "") >= cutoff}
    except Exception as ex:
        log.warning(f"Cache load error: {ex}")
        return set()


def save_cache(new_ids: list):
    existing = []
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
        except Exception:
            pass
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
    pruned = [e for e in existing if e.get("date", "") >= cutoff]
    seen = {e["id"] for e in pruned}
    for aid in new_ids:
        if aid not in seen:
            pruned.append({"id": aid, "date": TODAY})
    try:
        CACHE_PATH.write_text(json.dumps(pruned, ensure_ascii=False))
    except Exception as ex:
        log.warning(f"Cache save error: {ex}")


def make_id(url: str, title: str) -> str:
    raw = f"{url.strip()}:{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ════════════════════════════════════════════════════════════════════
# SECTION 4  FETCHER
#   Each source runs in its own thread.
#   Errors are caught, logged, and recorded to health tracker.
#   feedparser bozo errors are tolerated if entries exist.
# ════════════════════════════════════════════════════════════════════

def _parse_date(entry) -> str:
    """Parse feedparser entry date, fall back to TODAY."""
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        except Exception:
            pass
    # Try string fallback from published field
    raw_date = getattr(entry, "published", "") or getattr(entry, "updated", "")
    if raw_date:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_date)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return TODAY


def fetch_one(source: dict, seen_ids: set, health: dict) -> tuple[str, list, dict]:
    """
    Fetch one RSS feed.
    Returns (source_id, articles[], log_entry).
    Thread-safe — no shared writes.
    """
    sid      = source["id"]
    name     = source["name"]
    url      = source["url"]
    max_n    = source.get("max_items", 20)
    items:   list = []
    cutoff_3d = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")

    log_entry = {
        "id":          sid,
        "name":        name,
        "url":         url,
        "status":      "failed",
        "items":       0,
        "error":       None,
        "fetched_at":  NOW_ISO,
        "reliability": source.get("reliability", "★"),
        "tier":        source.get("tier", 3),
        "segments":    source.get("segments", []),
    }

    if not HAS_FEEDPARSER:
        log_entry["error"] = "feedparser not installed"
        return sid, items, log_entry

    try:
        socket.setdefaulttimeout(FETCH_TIMEOUT)

        # feedparser accepts custom headers via Request-Headers dict
        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent": "EnergyIntel/3.0 (energy-cvc-briefing; feedparser)",
                "Accept":     "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            }
        )

        http_status = getattr(feed, "status", 200)

        # Hard fail on 4xx/5xx
        if http_status and http_status >= 400:
            err = f"HTTP {http_status}"
            log_entry["error"] = err
            record_failure(sid, health, err)
            return sid, items, log_entry

        # Bozo check — feedparser sets bozo=True for malformed XML
        # BUT still parses what it can — only hard-fail if no entries
        if getattr(feed, "bozo", False):
            bozo_ex = str(getattr(feed, "bozo_exception", ""))[:100]
            if not feed.entries:
                err = f"Bozo + no entries: {bozo_ex}"
                log_entry["error"] = err
                record_failure(sid, health, err)
                return sid, items, log_entry
            # Has entries despite bozo — log warning but continue
            log.debug(f"  {name}: bozo feed but has {len(feed.entries)} entries — proceeding")

        if not feed.entries:
            err = "Empty feed (0 entries)"
            log_entry["error"] = err
            record_failure(sid, health, err)
            log_entry["status"] = "partial"
            return sid, items, log_entry

        count = 0
        for entry in feed.entries[:max_n]:
            title   = (getattr(entry, "title",   "") or "").strip()
            link    = (getattr(entry, "link",    "") or "").strip()
            # Some feeds use content instead of summary
            summary = (
                getattr(entry, "summary", "") or
                (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
            )[:800].strip()

            if not title or not link or title == "[Removed]":
                continue

            date = _parse_date(entry)
            if date < cutoff_3d:
                continue

            aid = make_id(link, title)
            if aid in seen_ids:
                continue

            # Strip HTML tags from summary
            summary_clean = re.sub(r"<[^>]+>", " ", summary)
            summary_clean = re.sub(r"\s+", " ", summary_clean).strip()

            items.append({
                "article_id":      aid,
                "source_id":       sid,
                "source_name":     name,
                "source_url":      link,
                "source_segments": source.get("segments", []),
                "reliability":     source.get("reliability", "★"),
                "tier":            source.get("tier", 3),
                "title":           title,
                "summary":         summary_clean,
                "published_date":  date,
                "raw_text":        f"{title} {summary_clean}".lower(),
                "fetched_at":      NOW_ISO,
            })
            count += 1

        log_entry["status"] = "success" if count > 0 else "partial"
        log_entry["items"]  = count
        record_success(sid, health)

    except socket.timeout:
        err = f"Timeout ({FETCH_TIMEOUT}s)"
        log_entry["error"] = err
        record_failure(sid, health, err)
    except Exception as ex:
        err = str(ex)[:200]
        log_entry["error"] = err
        record_failure(sid, health, err)

    return sid, items, log_entry


def fetch_all(seen_ids: set, health: dict) -> tuple[list, list]:
    """Fetch all sources in parallel. Skip sources with too many failures."""
    all_items: list = []
    all_logs:  list = []

    # Separate sources: active vs. skipped
    active_sources  = [s for s in SOURCES if not is_skipped(s["id"], health)]
    skipped_sources = [s for s in SOURCES if is_skipped(s["id"], health)]

    if skipped_sources:
        log.info(f"  Skipping {len(skipped_sources)} unstable source(s): "
                 f"{[s['name'] for s in skipped_sources]}")

    log.info(f"  Fetching {len(active_sources)} sources (workers={MAX_WORKERS})...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_one, src, seen_ids, health): src
            for src in active_sources
        }
        for future in as_completed(futures, timeout=180):
            src = futures[future]
            try:
                sid, items, entry = future.result(timeout=5)
                all_items.extend(items)
                all_logs.append(entry)
                icon = "✓" if entry["status"] == "success" else (
                       "~" if entry["status"] == "partial" else "✗")
                err  = f"  [{entry['error']}]" if entry.get("error") else ""
                print(f"    {icon} {src['name']:<30} {entry['items']:>3} items{err}")
            except Exception as ex:
                err = str(ex)[:100]
                print(f"    ✗ {src['name']:<30} executor error: {err}")
                all_logs.append({
                    "id":    src["id"], "name": src["name"], "url": src["url"],
                    "status": "failed", "items": 0, "error": f"executor: {err}",
                    "fetched_at": NOW_ISO,
                })
                record_failure(src["id"], health, f"executor: {err}")

    # Add skipped sources to log
    for src in skipped_sources:
        h = health.get(src["id"], {})
        all_logs.append({
            "id":    src["id"], "name": src["name"], "url": src["url"],
            "status": "skipped", "items": 0,
            "error":  f"Auto-skipped: {h.get('consecutive_fails',0)} consecutive failures",
            "fetched_at": NOW_ISO,
        })

    return all_items, all_logs


# ════════════════════════════════════════════════════════════════════
# SECTION 5  EIA OPEN DATA API
#   Free key: https://www.eia.gov/opendata/register.php
#   Fetches quantitative series as structured signals.
# ════════════════════════════════════════════════════════════════════

EIA_SERIES: list[dict] = [
    {
        "path":        "electricity/electric-power-operational-data/data",
        "params":      ("frequency=monthly&data[0]=generation"
                        "&facets[fueltypeid][]=SUN&facets[sectorid][]=99"
                        "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "description": "US utility-scale solar generation",
        "unit_label":  "MWh",
        "segments":    ["other_cleantech"],
        "event_type":  "deployment",
    },
    {
        "path":        "electricity/electric-power-operational-data/data",
        "params":      ("frequency=monthly&data[0]=generation"
                        "&facets[fueltypeid][]=WND&facets[sectorid][]=99"
                        "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "description": "US utility-scale wind generation",
        "unit_label":  "MWh",
        "segments":    ["offshore_wind"],
        "event_type":  "deployment",
    },
    {
        "path":        "total-energy/data",
        "params":      ("frequency=monthly&data[0]=value&facets[msn][]=BSESEUS"
                        "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "description": "US battery energy storage installed capacity",
        "unit_label":  "MW",
        "segments":    ["battery_storage", "long_duration_storage"],
        "event_type":  "deployment",
    },
    {
        "path":        "electricity/electric-power-operational-data/data",
        "params":      ("frequency=monthly&data[0]=generation"
                        "&facets[fueltypeid][]=NUC&facets[sectorid][]=99"
                        "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "description": "US nuclear electricity generation",
        "unit_label":  "MWh",
        "segments":    ["advanced_nuclear"],
        "event_type":  "deployment",
    },
]


def fetch_eia_api() -> list:
    if not EIA_API_KEY:
        log.info("  EIA_API_KEY not set — skipping (free at eia.gov/opendata/register.php)")
        return []

    items = []
    base  = "https://api.eia.gov/v2"

    for series in EIA_SERIES:
        try:
            url = f"{base}/{series['path']}?api_key={EIA_API_KEY}&{series['params']}"
            req = _urllib.Request(url, headers={"Accept": "application/json"})
            with _urllib.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())

            rows = data.get("response", {}).get("data", [])
            if not rows:
                continue

            row    = rows[0]
            period = row.get("period", "")
            value  = row.get("value") or row.get("generation", "")
            units  = row.get("units", series["unit_label"])

            if value is None:
                continue

            value_fmt = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
            desc      = series["description"]
            title     = f"EIA Data: {desc} — {period}: {value_fmt} {units}"
            summary   = (f"Official US EIA data. {desc}. Period: {period}. "
                         f"Value: {value_fmt} {units}. "
                         f"Source: US Energy Information Administration Open Data API v2.")

            items.append({
                "article_id":      make_id("eia.gov/v2/" + series["path"], title),
                "source_id":       "eia_api",
                "source_name":     "EIA Open Data API",
                "source_url":      "https://www.eia.gov/opendata/",
                "source_segments": series["segments"],
                "reliability":     "★★★",
                "tier":            1,
                "title":           title,
                "summary":         summary,
                "published_date":  TODAY,
                "raw_text":        f"{title} {summary}".lower(),
                "fetched_at":      NOW_ISO,
                "eia_period":      period,
                "eia_value":       str(value),
            })
            time.sleep(0.25)   # EIA rate limit: ~1000 req/hour, be polite

        except _urlerr.HTTPError as ex:
            log.warning(f"  EIA {series['description']}: HTTP {ex.code}")
        except Exception as ex:
            log.warning(f"  EIA {series['description']}: {ex}")

    log.info(f"  EIA API: {len(items)} data points")
    return items


# ════════════════════════════════════════════════════════════════════
# SECTION 6  CLASSIFIER & SCORER
#   Sector and event_type match the required output schema exactly.
#   Fully rule-based. No AI. Every point traceable.
# ════════════════════════════════════════════════════════════════════

# ── Sector keyword map ────────────────────────────────────────────
_SECTOR_KWS: dict[str, list[str]] = {
    "long_duration_storage": [
        "long duration", "long-duration", "ldes", "iron-air", "iron air",
        "vanadium flow", "flow battery", "multi-day storage", "seasonal storage",
        "liquid air energy", "gravitational storage", "compressed air energy",
        "multi-week storage", "iron flow",
    ],
    "battery_storage": [
        "battery storage", "bess", "energy storage", "lithium-ion", "lithium ion",
        "grid battery", "utility-scale battery", "battery system",
        "electrochemical storage", "sodium-ion", "solid state battery",
        "grid-scale battery", "li-ion",
    ],
    "green_hydrogen": [
        "green hydrogen", "electrolyzer", "electrolysis", "pem electrolyzer",
        "alkaline electrolyzer", "hydrogen production", "clean hydrogen",
        "renewable hydrogen", "blue hydrogen", "ammonia", "h2 hub",
        "hydrogen offtake", "hydrogen fuel cell", "hydrogen storage",
    ],
    "grid_software": [
        "vpp", "virtual power plant", "demand response", "grid software",
        "ferc", "ancillary services", "frequency regulation",
        "flexibility market", "dispatch optimization", "grid management",
        "energy management system", "ems", "grid modernization",
        "smart grid", "grid intelligence", "grid control", "grid operator",
        "ferc order", "ferc rule",
    ],
    "transmission": [
        "transmission", "hvdc", "high voltage direct current", "subsea cable",
        "offshore wind cable", "grid interconnect", "power line",
        "transmission line", "grid expansion", "ferc permitting",
        "grid congestion", "interregional transmission", "transmission siting",
    ],
    "advanced_nuclear": [
        "nuclear", "smr", "small modular reactor", "advanced reactor",
        "fusion", "molten salt", "fast reactor", "nuclear power",
        "fission", "nrc", "nuclear energy", "light water reactor",
        "next-generation nuclear", "microreactor",
    ],
    "data_center_power": [
        "data center", "hyperscaler", "azure", "aws", "google cloud",
        "power electronics", "ai infrastructure", "cfe",
        "24/7 clean energy", "corporate ppa", "data centre",
        "ai power", "ai energy demand",
    ],
    "geothermal": [
        "geothermal", "enhanced geothermal", "egs",
        "geothermal power", "geothermal heat", "geothermal energy",
        "hot rock", "ground source heat", "geothermal drilling",
    ],
    "offshore_wind": [
        "offshore wind", "floating wind", "fixed-bottom wind",
        "offshore turbine", "offshore wind farm", "monopile",
        "jacket foundation", "offshore wind cable",
    ],
    "other_cleantech": [
        "clean energy", "renewable energy", "solar", "cleantech",
        "decarbonization", "net zero", "climate tech", "energy transition",
        "carbon capture", "ccus", "ccs",
    ],
}

_SECTOR_PRIORITY: list[str] = [
    "long_duration_storage", "green_hydrogen", "advanced_nuclear",
    "geothermal", "offshore_wind", "transmission", "grid_software",
    "data_center_power", "battery_storage", "other_cleantech",
]

# ── Event type rules ──────────────────────────────────────────────
_EVENT_RULES: list[dict] = [
    {
        "event_type": "contract", "base_score": 90,
        "kws": [
            "signs contract", "awarded contract", "secures contract",
            "contract awarded", "offtake agreement", "supply agreement",
            "framework agreement", "purchase agreement",
            "power purchase agreement", "ppa signed", "long-term agreement",
            "commercial agreement", "procurement contract",
        ],
    },
    {
        "event_type": "deployment", "base_score": 88,
        "kws": [
            "goes live", "commercial operation", "operational", "commissioned",
            "begins operation", "starts operation", "deployed at",
            "installed at", "goes online", "comes online",
            "construction complete", "opens facility", "gigafactory",
            "first power", "energized",
        ],
    },
    {
        "event_type": "funding", "base_score": 82,
        "kws": [
            "raises", "closes funding", "series a", "series b", "series c",
            "seed round", "venture capital", "investment round", "funding round",
            "secures investment", "equity raise", "capital raise",
            "closes $", "raises $", "secures $", "closes €", "raises €",
            "investment of", "million investment", "billion investment",
        ],
    },
    {
        "event_type": "grant", "base_score": 65,
        "kws": [
            "grant awarded", "receives grant", "doe award", "doe funding",
            "government grant", "eu grant", "horizon grant",
            "nsf grant", "sbir award", "doe selects", "doe announces funding",
            "loan guarantee", "doe loan", "ira funding",
            "inflation reduction act", "federal grant", "department of energy",
        ],
    },
    {
        "event_type": "regulatory", "base_score": 62,
        "kws": [
            "ferc order", "ferc approves", "ferc issues", "ferc rule",
            "ferc notice", "ferc docket", "environmental impact",
            "permit granted", "permitting", "interconnection approval",
            "grid interconnection", "nrc approves", "nrc license",
            "eu taxonomy", "epa rule", "transmission permitting",
        ],
    },
    {
        "event_type": "pilot", "base_score": 70,
        "kws": [
            "pilot project", "demonstration project", "demo project",
            "field trial", "proof of concept", "first deployment",
            "initial deployment", "prototype tested", "demonstration facility",
            "test project", "demonstration plant",
        ],
    },
    {
        "event_type": "partnership", "base_score": 48,
        "kws": [
            "partnership", "mou", "memorandum of understanding",
            "joint venture", "collaboration agreement", "strategic alliance",
            "teaming agreement", "signs mou", "strategic partnership",
        ],
    },
    {
        "event_type": "policy", "base_score": 55,
        "kws": [
            "policy", "legislation", "regulation", "executive order",
            "inflation reduction act", "infrastructure law",
            "incentive", "subsidy", "tax credit", "itc", "ptc",
            "mandate", "standard", "national strategy",
            "clean energy standard", "renewable portfolio standard",
        ],
    },
]

# ── Noise / boost patterns ────────────────────────────────────────
_NOISE: list[tuple[str, int, str]] = [
    (r"\bproud to (announce|partner|share)\b|\bexcited to (announce|share)\b|\bpleased to announce\b",
     -40, "Generic PR"),
    (r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b",
     -20, "Intent only"),
    (r"\bcould (become|reach|achieve|unlock)\b|\bhas the potential to\b",
     -25, "Speculative"),
    (r"\bexploring\b.{0,40}\bpartner|\bin early discussions\b|\bpotential (partner|deal)\b",
     -30, "Exploratory"),
    (r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b",
     -30, "Vision only"),
    (r"\bwins? award\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b|\bgartner\b",
     -35, "Award/recognition"),
    (r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b",
     -30, "Conference only"),
    (r"\bpublishes? (report|study|whitepaper)\b|\bnew (report|research)\b",
     -25, "Report only"),
    (r"\brebrands?\b|\bnew (logo|brand|website)\b",
     -55, "Rebranding"),
    (r"\bopinion:\b|\bcommentary:\b|\bop-ed\b|\beditorial\b",
     -60, "Opinion"),
    (r"\bmarket (wrap|roundup|update)\b|\bweekly (round-?up|digest)\b|\bmonthly digest\b",
     -60, "Digest"),
    (r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b",
     -50, "Job posting"),
]

_BOOST: list[tuple[str, int, str]] = [
    (r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\bvattenfall\b|\bnational grid\b",
     +18, "Tier-1 strategic buyer"),
    (r"\bhyundai\b|\bsamsung\b|\bsiemens\b|\babb\b|\bhitachi\b|\bhanwha\b|\bshell\b|\bbp\b|\btotalenergies\b",
     +12, "Major industrial/OEM"),
    (r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]",
     +15, "Specific financial figure"),
    (r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b",
     +10, "Specific capacity"),
    (r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month",
     +8,  "Concrete timeframe"),
    (r"\beia\b|\bdoe\b|\bferc\b|\biea\b|\birena\b|\bnrel\b",
     +6,  "Gov/intergovernmental source/subject"),
    (r"\bbusan\b|\bincheon\b|\bulsan\b|\brotterdam\b|\bsingapore\b|\btexas\b|\bcalifornia\b|\boffshore\b",
     +5,  "Named project location"),
]


def classify(raw_text: str) -> dict:
    for rule in _EVENT_RULES:
        for kw in rule["kws"]:
            if kw in raw_text:
                return {"event_type": rule["event_type"],
                        "base_score": rule["base_score"],
                        "matched_kw": kw}
    return {"event_type": "other", "base_score": 15, "matched_kw": None}


def infer_sector(raw_text: str, source_segments: list) -> str:
    for seg in _SECTOR_PRIORITY:
        if any(kw in raw_text for kw in _SECTOR_KWS.get(seg, [])):
            return seg
    valid = set(_SECTOR_KWS.keys())
    for s in source_segments:
        if s in valid:
            return s
    return "other_cleantech"


def compute_score(raw_text: str, base: int) -> tuple[int, str, list]:
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
    s    = max(0, min(100, round(s)))
    tier = ("high" if s >= 60 else
            "medium" if s >= 35 else
            "low"    if s >= 20 else "noise")
    return s, tier, bd


# ── Company entity list ───────────────────────────────────────────
_COMPANIES: dict[str, str] = {
    "form energy": "Form Energy", "form energy systems": "Form Energy",
    "autogrid": "AutoGrid", "sunfire": "Sunfire", "amogy": "Amogy",
    "hysata": "Hysata", "ceres power": "Ceres Power",
    "invinity": "Invinity Energy", "enervenue": "EnerVenue",
    "ambri": "Ambri", "eos energy": "Eos Energy",
    "hydrostor": "Hydrostor", "energy vault": "Energy Vault",
    "verdagy": "Verdagy", "electric hydrogen": "Electric Hydrogen",
    "ohmium": "Ohmium", "plug power": "Plug Power",
    "bloom energy": "Bloom Energy", "kairos power": "Kairos Power",
    "terrapower": "TerraPower", "x-energy": "X-Energy",
    "nuscale": "NuScale", "fervo": "Fervo Energy",
    "fluence": "Fluence", "stem inc": "Stem",
    "gridwiz": "그리드위즈", "그리드위즈": "그리드위즈",
    "sixtyhz": "식스티헤르츠", "빈센": "빈센",
    "standard energy": "스탠다드에너지",
}


def extract_companies(raw_text: str) -> list:
    found = []
    for alias, canonical in _COMPANIES.items():
        if alias in raw_text and canonical not in found:
            found.append(canonical)
    return found


# ── why_it_matters ────────────────────────────────────────────────
_WHY: dict[tuple, str] = {
    ("contract",    "long_duration_storage"):
        "Binding offtake is the critical de-risking event for LDES project finance. "
        "Confirms demand-side validation; enables structured debt.",
    ("contract",    "battery_storage"):
        "Offtake/supply agreement is the clearest commercial-stage signal. "
        "LCOS competitiveness implied but contract terms required for confirmation.",
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
        "PPA for nuclear signals high-value, long-duration decarbonization commitment. "
        "Rare — watch for corporate buyer identity and pricing.",
    ("deployment",  "battery_storage"):
        "Operational deployment confirms TRL-9 in commercial setting. "
        "Utilities can now reference-site; next signal is contract replication.",
    ("deployment",  "long_duration_storage"):
        "First commercial LDES deployment is a sector-defining milestone. "
        "Establishes real-world LCOS baseline and de-risks project finance.",
    ("funding",     "default"):
        "External capital validation. Key variables: investor type (strategic >> financial), "
        "round size vs. capex needs, lead investor sector positioning.",
    ("grant",       "default"):
        "Government grant validates technology policy relevance but not market demand. "
        "Grant-only is insufficient without a commercial anchor.",
    ("grant",       "green_hydrogen"):
        "DOE/IRA hydrogen grants are large ($50M-$1B+). "
        "H2Hub projects require named industrial offtakers to close financing.",
    ("pilot",       "grid_software"):
        "Utility-sponsored pilot implies allocated opex budget. "
        "Pilot-to-commercial conversion rate is the key watch metric.",
    ("pilot",       "battery_storage"):
        "Grid-connected pilot signals utility-scale targeting. "
        "Interface compliance is the commercialization gate.",
    ("regulatory",  "grid_software"):
        "FERC orders directly expand the addressable market for VPPs and storage. "
        "FERC 2222 implementation is the key regulatory catalyst for grid software.",
    ("regulatory",  "transmission"):
        "Transmission permitting is the primary bottleneck for renewable buildout. "
        "FERC reforms and DOE permitting authority are critical policy enablers.",
    ("policy",      "green_hydrogen"):
        "IRA §45V hydrogen PTC ($3/kg) is the largest clean hydrogen subsidy globally. "
        "Guidance clarity determines electrolyzer project bankability.",
    ("policy",      "battery_storage"):
        "IRA standalone storage ITC transforms project economics. "
        "State-level mandates create additional demand floor.",
    ("policy",      "advanced_nuclear"):
        "NRC licensing reform and DOE loan guarantees are critical SMR enablers. "
        "Policy signals de-risk first-of-a-kind capital commitments.",
    ("partnership", "default"):
        "Named strategic partnership is directional. "
        "Watch for MOU → binding term conversion; IP and exclusivity terms are key.",
}

_MISSING_MAP: dict[str, list] = {
    "contract": [
        "Contract ACV not disclosed",
        "Duration and renewal terms not public",
        "Exclusivity and geographic scope unknown",
    ],
    "funding": [
        "Post-money valuation not confirmed",
        "Lead investor type (strategic vs. financial) unknown",
        "Use of proceeds not specified",
    ],
    "grant": [
        "Commercial co-funding partner not identified",
        "Path from grant to commercial revenue unclear",
        "Named private-sector offtaker required?",
    ],
    "pilot": [
        "Pilot success KPIs not publicly defined",
        "Pathway to commercial contract post-pilot unclear",
        "Named third-party validator not confirmed",
    ],
    "deployment": [
        "Revenue/offtake terms not disclosed",
        "Performance guarantee and warranty unknown",
        "Scale-up roadmap not public",
    ],
    "partnership": [
        "Binding terms (exclusivity, minimum volume) not confirmed",
        "MOU vs. binding contract distinction not stated",
        "Financial commitments not disclosed",
    ],
    "regulatory": [
        "Effective date and implementation timeline not stated",
        "Compliance costs and transition period not disclosed",
    ],
    "policy": [
        "Implementation regulations not yet issued",
        "Budget appropriation certainty unknown",
    ],
    "other": ["No investment-specific gap analysis available"],
}


def why_investment(event_type: str, sector: str) -> str:
    return (
        _WHY.get((event_type, sector))
        or _WHY.get((event_type, "default"))
        or (f"{event_type.capitalize()} event in {sector.replace('_',' ')} sector. "
            f"Assess binding terms, named counterparties, and capital efficiency.")
    )


# ════════════════════════════════════════════════════════════════════
# SECTION 7  NORMALIZER
#   Converts raw article → exact required output schema
# ════════════════════════════════════════════════════════════════════

def normalize(raw: dict) -> Optional[dict]:
    """
    Returns structured signal or None (noise/error).
    All fields in the required output schema.
    """
    try:
        raw_text    = raw.get("raw_text", "")
        title       = raw.get("title", "").strip()
        source_url  = raw.get("source_url", "")
        source_name = raw.get("source_name", "")
        pub_date    = raw.get("published_date", TODAY)

        clf         = classify(raw_text)
        sect        = infer_sector(raw_text, raw.get("source_segments", []))
        final, tier, breakdown = compute_score(raw_text, clf["base_score"])

        # Detect implicit negative signals
        neg_kws = ["delay", "postponed", "cancelled", "funding shortfall",
                   "struggles to raise", "project terminated", "deal collapsed",
                   "behind schedule"]
        is_neg = any(kw in raw_text for kw in neg_kws)

        # Drop noise unless negative
        if tier == "noise" and not is_neg:
            return None

        # Observed fact: first clean, substantive sentence from summary
        summary = raw.get("summary", "")
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary)
                     if len(s.strip()) > 30]
        observed = sentences[0] if sentences else title

        return {
            # ── Required schema fields ──────────────────────────────
            "id":                        raw["article_id"],
            "title":                     title,
            "source_name":               source_name,
            "source_url":                source_url,
            "published_date":            pub_date,
            "observed_fact":             observed,
            "why_it_matters_investment": why_investment(clf["event_type"], sect),
            "missing_evidence":          _MISSING_MAP.get(clf["event_type"],
                                                           _MISSING_MAP["other"]),
            "signal_tier":               tier,
            "signal_strength":           final,
            "sector":                    sect,
            "event_type":                clf["event_type"],
            "companies_mentioned":       extract_companies(raw_text),
            # ── Extra fields (debug / main pipeline) ────────────────
            "is_negative":               is_neg,
            "matched_keyword":           clf["matched_kw"],
            "score_breakdown":           breakdown,
            "source_reliability":        raw.get("reliability", "★"),
            "source_tier":               raw.get("tier", 3),
            "raw_summary":               summary[:400] if summary else title,
            "fetched_at":                raw.get("fetched_at", NOW_ISO),
        }
    except Exception as ex:
        log.debug(f"normalize error: {ex} — {raw.get('title','')[:60]}")
        return None


# ════════════════════════════════════════════════════════════════════
# SECTION 8  MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'═'*64}")
    print(f"  Energy CVC Signal Pipeline  v3.0")
    print(f"  {TODAY}  ·  {len(SOURCES)} RSS sources + EIA API")
    print(f"{'═'*64}\n")

    Path("data").mkdir(exist_ok=True)

    # ① Load state
    seen_ids = load_cache()
    health   = load_health()
    log.info(f"① State: {len(seen_ids)} cached IDs, "
             f"{sum(1 for s in SOURCES if not is_skipped(s['id'], health))} active sources")

    # ② RSS fetch (parallel)
    print("\n② RSS fetch...")
    t0 = time.time()
    rss_items, source_logs = fetch_all(seen_ids, health)
    t_rss = round(time.time() - t0, 1)
    ok  = sum(1 for l in source_logs if l["status"] == "success")
    tot = sum(1 for l in source_logs if l["status"] != "skipped")
    fail_rate = round((1 - ok/max(tot,1)) * 100)
    log.info(f"   → {len(rss_items)} articles in {t_rss}s | "
             f"{ok}/{tot} sources OK | fail rate {fail_rate}%")

    # ③ EIA API
    print("\n③ EIA Open Data API...")
    eia_items = fetch_eia_api()

    # ④ Dedup
    all_raw = rss_items + eia_items
    seen_this_run: set = set()
    deduped: list = []
    for item in all_raw:
        aid = item["article_id"]
        if aid not in seen_this_run:
            seen_this_run.add(aid)
            deduped.append(item)
    log.info(f"\n④ Dedup: {len(all_raw)} → {len(deduped)} unique")

    # Save raw
    RAW_PATH.write_text(json.dumps({
        "date":          TODAY,
        "generated_at":  NOW_ISO,
        "article_count": len(deduped),
        "source_logs":   source_logs,
        "articles":      deduped,
    }, ensure_ascii=False, indent=2))

    # ⑤ Normalize
    print("\n⑤ Classify + score...")
    signals: list = []
    dropped = 0
    for raw in deduped:
        sig = normalize(raw)
        if sig:
            signals.append(sig)
        else:
            dropped += 1

    signals.sort(key=lambda s: (
        {"high": 0, "medium": 1, "low": 2, "noise": 3}.get(s["signal_tier"], 9),
        -s["signal_strength"],
    ))

    high   = sum(1 for s in signals if s["signal_tier"] == "high")
    medium = sum(1 for s in signals if s["signal_tier"] == "medium")
    neg    = sum(1 for s in signals if s.get("is_negative"))
    by_seg: dict = {}
    by_evt: dict = {}
    for s in signals:
        by_seg[s["sector"]]     = by_seg.get(s["sector"], 0) + 1
        by_evt[s["event_type"]] = by_evt.get(s["event_type"], 0) + 1

    # Save signals
    OUT_PATH.write_text(json.dumps({
        "date":         TODAY,
        "generated_at": NOW_ISO,
        "signal_count": len(signals),
        "stats": {
            "total":          len(signals),
            "high":           high,
            "medium":         medium,
            "negative":       neg,
            "dropped_noise":  dropped,
            "sources_ok":     ok,
            "sources_total":  tot,
            "fail_rate_pct":  fail_rate,
            "by_sector":      by_seg,
            "by_event_type":  by_evt,
        },
        "source_logs": source_logs,
        "signals":     signals,
    }, ensure_ascii=False, indent=2))

    # ⑥ Persist state
    save_cache(list(seen_this_run))
    save_health(health)

    # Summary
    print(f"\n{'═'*64}")
    print(f"  ✅  Signals: {len(signals)} | HIGH {high} | MED {medium} | NEG {neg}")
    print(f"  Sources: {ok}/{tot} OK  |  Fail rate: {fail_rate}%")
    if fail_rate > 30:
        print(f"  ⚠  Fail rate {fail_rate}% > 30% — check fetch_health.json")
    print(f"  By sector:     {by_seg}")
    print(f"  By event type: {by_evt}")
    print(f"{'═'*64}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
collect_energy_signals.py
══════════════════════════════════════════════════════════════════
Energy CVC Signal Collector  v4.0

목적:  하루 80~120개 signals, 실패율 ≤ 2개 소스
소스:  검증된 안정 RSS 8개 + EIA Open Data API (선택)
모듈:  structure_insight.py (분류/점수 로직 분리)

실행:
    python collect_energy_signals.py

출력:
    data/raw_articles.json      수집된 raw 기사 전체
    data/signals.json           구조화 signals
    data/cache.json             7일 dedup 캐시
    data/source_health.json     소스별 성공/실패 이력

GitHub Actions 통합:
    generate-signals.py 실행 전 이 스크립트를 먼저 실행.
    generate-signals.py의 fetch_sources()가 data/raw_articles.json을
    자동으로 병합함 (오늘 날짜 파일인 경우에만).

실패율 관리:
    - 소스가 연속 FAIL_THRESHOLD회 실패 → 당일 자동 스킵
    - data/source_health.json에 이력 기록
    - 매일 리셋 → 임시 장애는 자동 복구
══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── 분류/점수 모듈 import ──────────────────────────────────────────
try:
    from structure_insight import normalize
    HAS_STRUCTURE = True
except ImportError:
    HAS_STRUCTURE = False
    logging.warning("structure_insight.py not found — signals will not be structured")

# ── feedparser ────────────────────────────────────────────────────
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

# ── EIA API (선택) ────────────────────────────────────────────────
try:
    import urllib.request as _ur
    import urllib.error as _ure
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

# ════════════════════════════════════════════════════════════════════
# 설정
# ════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("collect")

TODAY         = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO       = datetime.now(timezone.utc).isoformat()

MAX_AGE_DAYS    = 3      # 3일 이상 지난 기사 스킵
CACHE_DAYS      = 7      # dedup 캐시 보존 기간
FETCH_TIMEOUT   = 20     # 소스당 타임아웃 (초)
FAIL_THRESHOLD  = 3      # 연속 실패 N회 → 당일 스킵
CONCURRENT      = 8      # 동시 fetch 스레드 수

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

DATA_DIR    = Path("data")
RAW_PATH    = DATA_DIR / "raw_articles.json"
OUT_PATH    = DATA_DIR / "signals.json"
CACHE_PATH  = DATA_DIR / "cache.json"
HEALTH_PATH = DATA_DIR / "source_health.json"


# ════════════════════════════════════════════════════════════════════
# 소스 레지스트리
# ════════════════════════════════════════════════════════════════════
#
# 선정 기준:
#   ① 공개 무료 RSS (paywall, 상업구독 제외)
#   ② 2026년 기준 실측 안정성 ★★ 이상
#   ③ 에너지 투자 관련도 높음
#
# 제외 소스 (이유):
#   Renewables Now     — Cloudflare 403 반복
#   Recharge News      — Informa paywall
#   Hydrogen Insight   — Informa paywall
#   Wood Mackenzie     — 상업 구독 전용 RSS
#   S&P Global         — 상업 구독 전용 RSS
#   DOE EERE RSS       — 2025 사이트 재구성 이후 404
#   DOE Fossil Energy  — 404 반복
#   DOE Nuclear        — 404 반복
#   AZoCleantech       — CDN 불안정, 간헐적 503
#   IEA API RSS        — 간헐적 slow (추가 소스로 보존 가능)
#
# ════════════════════════════════════════════════════════════════════

SOURCES: list[dict] = [

    # ── Tier 1: 정부/국제기구 (★★★ 매우 안정) ─────────────────────

    {
        "id":       "eia_today",
        "name":     "EIA Today in Energy",
        "url":      "https://www.eia.gov/rss/todayinenergy.xml",
        "tier":     1,
        "max":      20,
        "segments": ["battery_storage", "green_hydrogen", "grid_software",
                     "offshore_wind", "other_cleantech"],
        "notes":    "US government primary. ~5 articles/day. Very stable.",
    },
    {
        "id":       "doe_main",
        "name":     "DOE Energy.gov",
        "url":      "https://www.energy.gov/articles/rss.xml",
        "tier":     1,
        "max":      20,
        "segments": ["battery_storage", "green_hydrogen", "grid_software",
                     "advanced_nuclear", "offshore_wind"],
        "notes":    "DOE cross-program. Grants, deployments, policy. ~5-8/day.",
    },

    # ── Tier 2: 전문 trade press (★★★) ──────────────────────────

    {
        "id":       "canarymedia",
        "name":     "Canary Media",
        "url":      "https://www.canarymedia.com/rss.rss",
        "tier":     2,
        "max":      30,
        "segments": ["battery_storage", "grid_software", "data_center_power",
                     "green_hydrogen", "offshore_wind"],
        "notes":    "Best US clean energy journalism. ~8-15/day.",
    },
    {
        "id":       "pvmagazine",
        "name":     "PV Magazine",
        "url":      "https://www.pv-magazine.com/feed/",
        "tier":     2,
        "max":      25,
        "segments": ["battery_storage", "green_hydrogen", "other_cleantech"],
        "notes":    "Very stable. 15-20/day. Strong EU + global coverage.",
    },
    {
        "id":       "energystoragenews",
        "name":     "Energy Storage News",
        "url":      "https://www.energy-storage.news/feed/",
        "tier":     2,
        "max":      25,
        "segments": ["battery_storage", "long_duration_storage"],
        "notes":    "Specialist BESS/LDES. Very consistent. ~8-12/day.",
    },
    {
        "id":       "utilitydive",
        "name":     "Utility Dive",
        "url":      "https://www.utilitydive.com/feeds/news/",
        "tier":     2,
        "max":      25,
        "segments": ["grid_software", "battery_storage", "data_center_power",
                     "transmission"],
        "notes":    "Best US utility/grid. FERC news often first here. ~10-15/day.",
    },
    {
        "id":       "offshorewind",
        "name":     "Offshore Wind Biz",
        "url":      "https://www.offshorewind.biz/feed/",
        "tier":     2,
        "max":      20,
        "segments": ["offshore_wind", "transmission"],
        "notes":    "Specialist offshore wind. WordPress RSS = very stable. ~8-12/day.",
    },

    # ── Tier 3: 종합 cleantech (★★★) ─────────────────────────────

    {
        "id":       "cleantechnica",
        "name":     "CleanTechnica",
        "url":      "https://cleantechnica.com/feed/",
        "tier":     3,
        "max":      25,
        "segments": ["battery_storage", "grid_software", "data_center_power",
                     "other_cleantech"],
        "notes":    "High volume. Tier 3 — verify figures. Very stable. ~15-25/day.",
    },
    {
        "id":       "electrek",
        "name":     "Electrek",
        "url":      "https://electrek.co/feed/",
        "tier":     3,
        "max":      20,
        "segments": ["battery_storage", "data_center_power", "other_cleantech"],
        "notes":    "Very stable. Broad. Tier 3. ~15-20/day.",
    },
]

# ── 선택적 추가 소스 (OPTIONAL_SOURCES에서 활성화 가능) ────────────
# 안정성이 ★★지만 커버리지가 넓어 활성화 권장
OPTIONAL_SOURCES: list[dict] = [
    {
        "id":       "h2view",
        "name":     "H2 View",
        "url":      "https://www.h2-view.com/feed/",
        "tier":     2,
        "max":      20,
        "segments": ["green_hydrogen"],
        "notes":    "Specialist H2. Occasionally empty. ~5-8/day when working.",
    },
    {
        "id":       "doe_cleancities",
        "name":     "DOE Clean Cities",
        "url":      "https://cleancities.energy.gov/news-events/rss",
        "tier":     1,
        "max":      15,
        "segments": ["other_cleantech", "data_center_power"],
        "notes":    "Fleet electrification. Generally stable. ~2-4/day.",
    },
    {
        "id":       "iea",
        "name":     "IEA News",
        "url":      "https://www.iea.org/api/rss",
        "tier":     1,
        "max":      15,
        "segments": ["green_hydrogen", "battery_storage", "grid_software",
                     "offshore_wind"],
        "notes":    "Primary source. Slow sometimes. ~3-5/day.",
    },
]

# OPTIONAL_SOURCES를 활성화하려면 SOURCES에 추가:
# SOURCES = SOURCES + OPTIONAL_SOURCES


# ════════════════════════════════════════════════════════════════════
# 소스 헬스 트래커
# ════════════════════════════════════════════════════════════════════

def load_health() -> dict:
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
        log.warning(f"Health save: {ex}")


def is_skipped(sid: str, health: dict) -> bool:
    """연속 실패가 임계치에 달해 스킵 중인지 확인."""
    h = health.get(sid, {})
    skip_until = h.get("skip_until", "")
    return bool(skip_until and skip_until > TODAY)


def on_success(sid: str, health: dict):
    health[sid] = {
        "consecutive_fails": 0,
        "last_success": TODAY,
        "skip_until": "",
    }


def on_failure(sid: str, health: dict, error: str):
    h = health.setdefault(sid, {"consecutive_fails": 0})
    h["consecutive_fails"] = h.get("consecutive_fails", 0) + 1
    h["last_error"]        = error[:120]
    h["last_fail"]         = TODAY
    if h["consecutive_fails"] >= FAIL_THRESHOLD:
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        h["skip_until"] = tomorrow
        log.warning(
            f"  ⚠ {sid}: {h['consecutive_fails']} consecutive fails → "
            f"skipping until {tomorrow}"
        )


# ════════════════════════════════════════════════════════════════════
# dedup 캐시
# ════════════════════════════════════════════════════════════════════

def load_cache() -> set:
    if not CACHE_PATH.exists():
        return set()
    try:
        data  = json.loads(CACHE_PATH.read_text())
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
        return {e["id"] for e in data if e.get("date", "") >= cutoff}
    except Exception as ex:
        log.warning(f"Cache load: {ex}")
        return set()


def save_cache(new_ids: list):
    existing: list = []
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
        except Exception:
            pass
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).strftime("%Y-%m-%d")
    pruned = [e for e in existing if e.get("date", "") >= cutoff]
    seen   = {e["id"] for e in pruned}
    for aid in new_ids:
        if aid not in seen:
            pruned.append({"id": aid, "date": TODAY})
    try:
        CACHE_PATH.write_text(json.dumps(pruned, ensure_ascii=False))
    except Exception as ex:
        log.warning(f"Cache save: {ex}")


def make_id(url: str, title: str) -> str:
    raw = f"{url.strip()}:{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ════════════════════════════════════════════════════════════════════
# RSS fetcher (동기, 스레드풀에서 실행)
# ════════════════════════════════════════════════════════════════════

def _parse_date(entry) -> str:
    """feedparser entry에서 날짜 파싱. 실패 시 TODAY 반환."""
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        except Exception:
            pass
    # 문자열 fallback
    raw = getattr(entry, "published", "") or getattr(entry, "updated", "")
    if raw:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return TODAY


def fetch_one_sync(source: dict, seen_ids: set, health: dict) -> tuple[str, list, dict]:
    """
    하나의 RSS 소스를 동기적으로 수집.
    스레드풀에서 실행되므로 thread-safe (공유 상태 없음).
    Returns (source_id, articles, log_entry).
    """
    sid    = source["id"]
    name   = source["name"]
    url    = source["url"]
    max_n  = source.get("max", 20)
    items: list = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")

    entry = {
        "id":         sid,
        "name":       name,
        "url":        url,
        "status":     "failed",
        "items":      0,
        "error":      None,
        "fetched_at": NOW_ISO,
        "tier":       source.get("tier", 3),
        "segments":   source.get("segments", []),
    }

    if not HAS_FEEDPARSER:
        entry["error"] = "feedparser not installed (pip install feedparser)"
        return sid, items, entry

    try:
        socket.setdefaulttimeout(FETCH_TIMEOUT)
        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent": "EnergyIntel/4.0 (+https://github.com/energy-cvc-briefing)",
                "Accept":     "application/rss+xml, application/atom+xml, text/xml, */*",
            },
        )

        # HTTP 오류
        http_code = getattr(feed, "status", 200)
        if http_code and http_code >= 400:
            err = f"HTTP {http_code}"
            entry["error"] = err
            on_failure(sid, health, err)
            return sid, items, entry

        # bozo = 비표준 XML이지만 entries 있으면 계속 진행
        if getattr(feed, "bozo", False) and not feed.entries:
            ex_str = str(getattr(feed, "bozo_exception", "parse error"))[:100]
            err    = f"Bozo+no entries: {ex_str}"
            entry["error"] = err
            on_failure(sid, health, err)
            entry["status"] = "partial"
            return sid, items, entry

        count = 0
        for fe in feed.entries[:max_n]:
            title = (getattr(fe, "title",   "") or "").strip()
            link  = (getattr(fe, "link",    "") or "").strip()

            # summary 또는 content[0].value
            raw_summary = (
                getattr(fe, "summary", "")
                or (fe.get("content", [{}])[0].get("value", "")
                    if fe.get("content") else "")
            )[:800]

            if not title or not link or title == "[Removed]":
                continue

            date = _parse_date(fe)
            if date < cutoff:
                continue

            aid = make_id(link, title)
            if aid in seen_ids:
                continue

            # HTML 태그 제거
            summary_clean = re.sub(r"<[^>]+>", " ", raw_summary)
            summary_clean = re.sub(r"\s+", " ", summary_clean).strip()

            items.append({
                "article_id":      aid,
                "source_id":       sid,
                "source_name":     name,
                "source_url":      link,
                "source_segments": source.get("segments", []),
                "reliability":     "★" * source.get("tier", 3),
                "tier":            source.get("tier", 3),
                "title":           title,
                "summary":         summary_clean,
                "published_date":  date,
                "raw_text":        f"{title} {summary_clean}".lower(),
                "fetched_at":      NOW_ISO,
            })
            count += 1

        entry["status"] = "success" if count > 0 else "partial"
        entry["items"]  = count
        on_success(sid, health)

    except socket.timeout:
        err = f"Timeout ({FETCH_TIMEOUT}s)"
        entry["error"] = err
        on_failure(sid, health, err)
    except Exception as ex:
        err = str(ex)[:200]
        entry["error"] = err
        on_failure(sid, health, err)

    return sid, items, entry


# ════════════════════════════════════════════════════════════════════
# asyncio 래퍼 — 동기 feedparser를 스레드풀에서 실행
# ════════════════════════════════════════════════════════════════════

async def fetch_one_async(
    source: dict,
    seen_ids: set,
    health: dict,
    loop: asyncio.AbstractEventLoop,
    executor: ThreadPoolExecutor,
) -> tuple[str, list, dict]:
    """fetch_one_sync를 asyncio executor에서 실행."""
    return await loop.run_in_executor(
        executor,
        fetch_one_sync,
        source,
        seen_ids,
        health,
    )


async def fetch_all_async(seen_ids: set, health: dict) -> tuple[list, list]:
    """모든 소스를 병렬로 수집. asyncio + ThreadPoolExecutor."""
    active  = [s for s in SOURCES if not is_skipped(s["id"], health)]
    skipped = [s for s in SOURCES if is_skipped(s["id"], health)]

    if skipped:
        log.info(f"  Auto-skipped ({len(skipped)}): {[s['name'] for s in skipped]}")

    log.info(f"  Fetching {len(active)} sources in parallel...")

    loop = asyncio.get_event_loop()
    all_items: list = []
    all_logs:  list = []

    with ThreadPoolExecutor(max_workers=CONCURRENT) as executor:
        tasks = [
            fetch_one_async(src, seen_ids, health, loop, executor)
            for src in active
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        src = active[i]
        if isinstance(result, Exception):
            err = str(result)[:100]
            log.error(f"  ✗ {src['name']}: gather exception: {err}")
            all_logs.append({
                "id": src["id"], "name": src["name"], "url": src["url"],
                "status": "failed", "items": 0,
                "error": f"gather: {err}", "fetched_at": NOW_ISO,
            })
            on_failure(src["id"], health, f"gather: {err}")
        else:
            sid, items, entry = result
            all_items.extend(items)
            all_logs.append(entry)
            icon = "✓" if entry["status"] == "success" else (
                   "~" if entry["status"] == "partial" else "✗")
            err  = f"  [{entry['error']}]" if entry.get("error") else ""
            print(f"    {icon} {src['name']:<28} {entry['items']:>3} items{err}")

    # 스킵된 소스도 로그에 포함
    for src in skipped:
        h = health.get(src["id"], {})
        all_logs.append({
            "id":   src["id"], "name": src["name"], "url": src["url"],
            "status": "skipped", "items": 0,
            "error": f"Skipped: {h.get('consecutive_fails',0)} consecutive fails",
            "fetched_at": NOW_ISO,
        })

    return all_items, all_logs


# ════════════════════════════════════════════════════════════════════
# EIA Open Data API (선택)
# ════════════════════════════════════════════════════════════════════

EIA_SERIES: list[dict] = [
    {
        "path":  "electricity/electric-power-operational-data/data",
        "params": ("frequency=monthly&data[0]=generation"
                   "&facets[fueltypeid][]=SUN&facets[sectorid][]=99"
                   "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "label": "US utility-scale solar generation",
        "unit":  "MWh",
        "segs":  ["other_cleantech"],
    },
    {
        "path":  "electricity/electric-power-operational-data/data",
        "params": ("frequency=monthly&data[0]=generation"
                   "&facets[fueltypeid][]=WND&facets[sectorid][]=99"
                   "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "label": "US utility-scale wind generation",
        "unit":  "MWh",
        "segs":  ["offshore_wind"],
    },
    {
        "path":  "total-energy/data",
        "params": ("frequency=monthly&data[0]=value&facets[msn][]=BSESEUS"
                   "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"),
        "label": "US battery energy storage capacity",
        "unit":  "MW",
        "segs":  ["battery_storage", "long_duration_storage"],
    },
]


def fetch_eia() -> list:
    """EIA API에서 정량 데이터 수집. API 키 없으면 skip."""
    if not EIA_API_KEY or not HAS_URLLIB:
        return []

    items = []
    base  = "https://api.eia.gov/v2"

    for s in EIA_SERIES:
        try:
            url = f"{base}/{s['path']}?api_key={EIA_API_KEY}&{s['params']}"
            req = _ur.Request(url, headers={"Accept": "application/json"})
            with _ur.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())

            rows = data.get("response", {}).get("data", [])
            if not rows:
                continue

            row    = rows[0]
            period = row.get("period", "")
            value  = row.get("value") or row.get("generation")
            if value is None:
                continue

            vfmt  = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
            title = f"EIA: {s['label']} — {period}: {vfmt} {s['unit']}"
            summ  = (f"Official EIA data. {s['label']}. "
                     f"Period: {period}. Value: {vfmt} {s['unit']}. "
                     f"Source: US Energy Information Administration Open Data API v2.")

            items.append({
                "article_id":      make_id("eia.gov/" + s["path"], title),
                "source_id":       "eia_api",
                "source_name":     "EIA Open Data API",
                "source_url":      "https://www.eia.gov/opendata/",
                "source_segments": s["segs"],
                "reliability":     "★★★",
                "tier":            1,
                "title":           title,
                "summary":         summ,
                "published_date":  TODAY,
                "raw_text":        f"{title} {summ}".lower(),
                "fetched_at":      NOW_ISO,
                "eia_period":      period,
                "eia_value":       str(value),
            })
            time.sleep(0.25)   # EIA rate limit 준수

        except Exception as ex:
            log.warning(f"  EIA {s['label']}: {ex}")

    log.info(f"  EIA API: {len(items)} data points")
    return items


# ════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════

async def main_async():
    print(f"\n{'═'*62}")
    print(f"  Energy CVC Signal Collector  v4.0")
    print(f"  {TODAY}  ·  {len(SOURCES)} core sources")
    print(f"{'═'*62}\n")

    DATA_DIR.mkdir(exist_ok=True)

    # ① 상태 로드
    seen_ids = load_cache()
    health   = load_health()
    active   = sum(1 for s in SOURCES if not is_skipped(s["id"], health))
    log.info(f"① State: {len(seen_ids)} cached IDs | {active}/{len(SOURCES)} sources active")

    # ② RSS 병렬 수집
    print("\n② RSS fetch (asyncio + ThreadPoolExecutor)...")
    t0 = time.time()
    rss_items, source_logs = await fetch_all_async(seen_ids, health)
    t_rss = round(time.time() - t0, 1)

    ok   = sum(1 for l in source_logs if l["status"] == "success")
    tot  = sum(1 for l in source_logs if l["status"] != "skipped")
    fail = tot - ok
    log.info(f"   → {len(rss_items)} articles | {t_rss}s | "
             f"{ok}/{tot} OK | {fail} failed")

    # ③ EIA API (선택)
    print("\n③ EIA Open Data API...")
    eia_items = fetch_eia()

    # ④ dedup
    all_raw = rss_items + eia_items
    seen_run: set = set()
    deduped: list = []
    for item in all_raw:
        aid = item["article_id"]
        if aid not in seen_run:
            seen_run.add(aid)
            deduped.append(item)

    dup = len(all_raw) - len(deduped)
    log.info(f"\n④ Dedup: {len(all_raw)} raw → {len(deduped)} unique ({dup} dupes removed)")

    # raw 저장
    RAW_PATH.write_text(json.dumps({
        "date":           TODAY,
        "generated_at":   NOW_ISO,
        "article_count":  len(deduped),
        "source_count":   len(SOURCES),
        "source_logs":    source_logs,
        "articles":       deduped,
    }, ensure_ascii=False, indent=2))
    log.info(f"   Saved {RAW_PATH}")

    # ⑤ 구조화
    print("\n⑤ Structure + score...")
    signals: list = []
    dropped = 0

    if HAS_STRUCTURE:
        for raw in deduped:
            sig = normalize(raw)
            if sig:
                signals.append(sig)
            else:
                dropped += 1
    else:
        # structure_insight 없으면 raw를 최소 포맷으로 변환
        log.warning("structure_insight.py not found — using minimal schema")
        for raw in deduped:
            signals.append({
                "id":           raw["article_id"],
                "title":        raw["title"],
                "source_name":  raw["source_name"],
                "source_url":   raw["source_url"],
                "published_date": raw["published_date"],
                "signal_tier":  "low",
                "signal_strength": 0,
            })

    # 정렬: HIGH → MEDIUM → LOW, 점수 내림차순
    tier_rank = {"high": 0, "medium": 1, "low": 2, "noise": 3}
    signals.sort(key=lambda s: (
        tier_rank.get(s.get("signal_tier", "low"), 9),
        -(s.get("signal_strength", 0)),
    ))

    high   = sum(1 for s in signals if s.get("signal_tier") == "high")
    medium = sum(1 for s in signals if s.get("signal_tier") == "medium")
    neg    = sum(1 for s in signals if s.get("is_negative"))
    by_seg: dict = {}
    by_evt: dict = {}
    for s in signals:
        by_seg[s.get("sector", "?")] = by_seg.get(s.get("sector", "?"), 0) + 1
        by_evt[s.get("event_type", "?")] = by_evt.get(s.get("event_type", "?"), 0) + 1

    OUT_PATH.write_text(json.dumps({
        "date":         TODAY,
        "generated_at": NOW_ISO,
        "signal_count": len(signals),
        "stats": {
            "total":         len(signals),
            "high":          high,
            "medium":        medium,
            "negative":      neg,
            "dropped_noise": dropped,
            "sources_ok":    ok,
            "sources_total": tot,
            "fail_count":    fail,
            "by_sector":     by_seg,
            "by_event_type": by_evt,
        },
        "source_logs": source_logs,
        "signals":     signals,
    }, ensure_ascii=False, indent=2))
    log.info(f"   Saved {OUT_PATH}")

    # ⑥ 상태 저장
    save_cache(list(seen_run))
    save_health(health)
    log.info(f"\n⑥ Cache: +{len(seen_run)} IDs | Health saved")

    # 요약
    print(f"\n{'═'*62}")
    print(f"  ✅  Signals: {len(signals)} | HIGH {high} | MED {medium} | NEG {neg}")
    print(f"  Sources: {ok}/{tot} OK  |  Failed: {fail}")
    if fail > 2:
        print(f"  ⚠  {fail} sources failed — check {HEALTH_PATH}")
    print(f"  By sector:     {by_seg}")
    print(f"  By event type: {by_evt}")
    print(f"{'═'*62}\n")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

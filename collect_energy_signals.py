"""
collect_energy_signals.py  v3.0
Energy CVC Intelligence Platform — Phase 1 Signal Collector

━━━ 이전 버전 대비 핵심 변경 ━━━

[Fix 1] 출력 형식을 data/extended_raw.json으로 통일
  - generate-signals.py의 fetch_sources()가 이 파일을 자동으로 읽어 머지
  - 이전: data/raw_signals/YYYY-MM-DD.json (연동 안 됨)
  - 이후: data/extended_raw.json (generate-signals.py와 바로 연동)

[Fix 2] 노이즈 필터 정밀화 (오탐 최소화)
  - "Bitcoin mining energy" → KEEP (에너지 기사)
  - "Bitcoin price rally" → FILTER (투기 기사)
  - "dividend cuts signal clean energy shift" → KEEP

[Fix 3] 수집량 대폭 확대
  - MAX_ITEMS_PER_FEED: 20 → 50
  - LOOKBACK_DAYS: 7 → 14
  - 피드 수: 6 → 14개 (stable 소스만)
  - 예상 하루 수집량: 80~150개

[Fix 4] feedparser 우선 + urllib fallback (둘 다 지원)
  - pip install feedparser 없어도 stdlib XML로 동작
  - feedparser 있으면 더 정확한 파싱

[Fix 5] generate-signals.py 세그먼트 ID와 정확히 매핑
  - ess, grid_sw, hydrogen, marine_fc, hvdc, dc_power, forecasting

실행:
  python collect_energy_signals.py
  python collect_energy_signals.py --dry-run        (저장 안 함)
  python collect_energy_signals.py --reset-health   (실패 이력 초기화)
  BASE_DIR=data python collect_energy_signals.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import email.utils
import hashlib
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

# ── feedparser 선택적 사용 ────────────────────────────────────────────────
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

# ─────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(os.environ.get("BASE_DIR", "data"))
OUT_PATH     = BASE_DIR / "extended_raw.json"   # generate-signals.py가 읽는 파일
HEALTH_PATH  = BASE_DIR / "feed_health.json"
CACHE_DIR    = BASE_DIR / "cache"
TODAY        = date.today().isoformat()

BASE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FETCH_TIMEOUT   = 20     # 초
MAX_WORKERS     = 10     # 병렬 fetch
MAX_ITEMS       = 50     # 피드당 최대 기사 수
LOOKBACK_DAYS   = 14     # 이 기간 내 기사만 포함
MAX_FAIL        = 3      # 연속 실패 N회 → 자동 비활성화

ATOM_NS = "http://www.w3.org/2005/Atom"

HTTP_HEADERS = {
    "User-Agent":     "Mozilla/5.0 (compatible; EnergyIntelBot/3.0)",
    "Accept":         "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language":"en-US,en;q=0.9",
    "Cache-Control":  "no-cache",
}

# ─────────────────────────────────────────────────────────────────────────
# 피드 레지스트리
# generate-signals.py SOURCE_REGISTRY와 source_segments 동기화됨
# ─────────────────────────────────────────────────────────────────────────
FEEDS = [
    # ── Priority 1: 핵심 (반드시 포함) ────────────────────────────────
    {
        "id":          "canarymedia",
        "name":        "Canary Media",
        "url":         "https://www.canarymedia.com/rss.rss",
        "segments":    ["ess", "grid_sw", "hydrogen", "dc_power"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["energy storage", "clean energy", "VPP", "hydrogen", "solar"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    {
        "id":          "eia",
        "name":        "EIA Today in Energy",
        "url":         "https://www.eia.gov/rss/todayinenergy.xml",
        "segments":    ["ess", "forecasting", "grid_sw"],
        "source_type": "government",
        "reliability": 1,
        "topics":      ["energy data", "storage capacity", "generation mix", "prices"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    {
        "id":          "pvmagazine",
        "name":        "PV Magazine",
        "url":         "https://www.pv-magazine.com/feed/",
        "segments":    ["ess", "hydrogen", "forecasting"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["solar PV", "energy storage", "hydrogen", "electrolyzer"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    {
        "id":          "energystoragenews",
        "name":        "Energy Storage News",
        "url":         "https://www.energy-storage.news/feed/",
        "segments":    ["ess"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["battery storage", "BESS", "flow battery", "LDES"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    {
        "id":          "cleantechnica",
        "name":        "CleanTechnica",
        "url":         "https://cleantechnica.com/feed/",
        "segments":    ["ess", "dc_power", "forecasting", "grid_sw"],
        "source_type": "industry",
        "reliability": 3,
        "topics":      ["clean energy", "EV", "battery storage", "solar", "wind"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    {
        "id":          "electrek",
        "name":        "Electrek",
        "url":         "https://electrek.co/feed/",
        "segments":    ["ess", "dc_power", "forecasting"],
        "source_type": "industry",
        "reliability": 3,
        "topics":      ["EV", "battery storage", "solar", "utility-scale"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    1,
    },
    # ── Priority 2: 안정적 추가 소스 ──────────────────────────────────
    {
        "id":          "utilitydive",
        "name":        "Utility Dive",
        "url":         "https://www.utilitydive.com/feeds/news/",
        "segments":    ["grid_sw", "ess", "dc_power"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["grid software", "demand response", "VPP", "utility", "regulatory"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    {
        "id":          "h2view",
        "name":        "H2 View",
        "url":         "https://www.h2-view.com/feed/",
        "segments":    ["hydrogen", "marine_fc"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["green hydrogen", "electrolyzer", "fuel cell", "hydrogen transport"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    {
        "id":          "offshorewind",
        "name":        "Offshore Wind Biz",
        "url":         "https://www.offshorewind.biz/feed/",
        "segments":    ["hvdc", "ess"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["offshore wind", "HVDC", "subsea cable", "grid connection"],
        "geography":   "EU",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    {
        "id":          "rechargenews",
        "name":        "Recharge News",
        "url":         "https://www.rechargenews.com/rss",
        "segments":    ["hydrogen", "ess", "hvdc"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["renewable energy", "hydrogen", "offshore wind", "storage"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    {
        "id":          "energymonitor",
        "name":        "Energy Monitor",
        "url":         "https://www.energymonitor.ai/feed/",
        "segments":    ["ess", "grid_sw", "hydrogen"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["energy transition", "storage", "grid", "policy"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    {
        "id":          "greentechmedia",
        "name":        "Greentech Media",
        "url":         "https://www.greentechmedia.com/feed",
        "segments":    ["ess", "grid_sw", "forecasting"],
        "source_type": "industry",
        "reliability": 2,
        "topics":      ["grid", "storage", "solar", "market intelligence"],
        "geography":   "US",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    2,
    },
    # ── Priority 3: 보조 ───────────────────────────────────────────────
    {
        "id":          "newatlas_energy",
        "name":        "New Atlas Energy",
        "url":         "https://newatlas.com/energy/rss/",
        "segments":    ["ess", "hydrogen", "forecasting"],
        "source_type": "industry",
        "reliability": 3,
        "topics":      ["energy technology", "battery", "hydrogen", "innovation"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    3,
    },
    {
        "id":          "azocleantech",
        "name":        "AZoCleantech",
        "url":         "https://www.azocleantech.com/rss.aspx",
        "segments":    ["ess", "hydrogen", "grid_sw"],
        "source_type": "industry",
        "reliability": 3,
        "topics":      ["cleantech", "battery", "hydrogen", "solar"],
        "geography":   "GLOBAL",
        "approved_by": "analyst",
        "approved_date": "2025-01-01",
        "priority":    3,
    },
]

# ─────────────────────────────────────────────────────────────────────────
# 노이즈 필터 (정밀 — 오탐 최소화)
# ─────────────────────────────────────────────────────────────────────────
_NOISE_PATTERNS = [
    # 투기/가격 crypto (에너지 문맥 제외)
    r"\bcrypto(currency)?\s+(price|market|rally|crash|surge|invest|trade)",
    r"\bethereum\s+(price|value|token|invest)",
    r"\bnft\s+(market|sale|drop|mint|collect)",
    r"\btoken\s+sale\b",
    r"\bbitcoin\s+(price|value|wallet|etf|halving|miner\s+profit)",
    # 순수 금융 기사
    r"\bearnings\s+per\s+share\b",
    r"\bshare\s+price\s+(rise|fall|drop|surge|crash|plunge)\b",
    r"\bstock\s+(tip|pick|alert|screener)\b",
    r"\bforex\s+(rate|trade|market)\b",
    # 완전히 무관한 카테고리
    r"\bweight\s+loss\b",
    r"\bcasino\b",
    r"\bsports\s+bet(ting)?\b",
    r"\bhealth\s+supplement\b",
    r"\bprescription\s+drug\b",
]
NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────
# HTML 스트리퍼
# ─────────────────────────────────────────────────────────────────────────
class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
    def handle_data(self, data: str):
        self._parts.append(data)

def strip_html(html: str) -> str:
    if not html:
        return ""
    s = _Stripper()
    try:
        s.feed(html)
        text = " ".join(s._parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

# ─────────────────────────────────────────────────────────────────────────
# 날짜 파싱
# ─────────────────────────────────────────────────────────────────────────
def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return email.utils.parsedate_to_datetime(raw).date().isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt[:len(raw[:19])]).date().isoformat()
        except Exception:
            continue
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except Exception:
        return None

def within_lookback(iso: Optional[str]) -> bool:
    if not iso:
        return True
    try:
        return (date.today() - date.fromisoformat(iso)).days <= LOOKBACK_DAYS
    except Exception:
        return True

# ─────────────────────────────────────────────────────────────────────────
# XML RSS/Atom 파서 (stdlib)
# ─────────────────────────────────────────────────────────────────────────
def parse_xml_feed(xml_bytes: bytes, feed: dict) -> list[dict]:
    sid   = feed["id"]
    sname = feed["name"]
    surl  = feed["url"]
    segs  = feed["segments"]
    articles: list[dict] = []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    tag = root.tag

    # ── Atom ──────────────────────────────────────────────────────────
    if ATOM_NS in tag or "atom" in tag.lower():
        ns = ATOM_NS
        for entry in root.findall(f"{{{ns}}}entry")[:MAX_ITEMS]:
            title   = (entry.findtext(f"{{{ns}}}title") or "").strip()
            if not title:
                continue
            summary = strip_html(
                entry.findtext(f"{{{ns}}}summary") or
                entry.findtext(f"{{{ns}}}content") or ""
            )
            pub     = (
                entry.findtext(f"{{{ns}}}updated") or
                entry.findtext(f"{{{ns}}}published") or ""
            )
            link_el = entry.find(f"{{{ns}}}link")
            link    = (
                (link_el.get("href", "") if link_el is not None else "") or
                entry.findtext(f"{{{ns}}}id") or
                surl
            )
            pub_date = parse_date(pub) or TODAY
            if not within_lookback(pub_date):
                continue
            articles.append(_make_article(sid, sname, link, segs, title, summary, pub_date))

    # ── RSS 2.0 ───────────────────────────────────────────────────────
    else:
        items = root.findall(".//item")
        for item in items[:MAX_ITEMS]:
            title = (item.findtext("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            desc = strip_html(
                item.findtext("description") or
                item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
            )
            pub  = (
                item.findtext("pubDate") or
                item.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
            )
            link = (
                item.findtext("link") or
                item.findtext("guid") or
                surl
            )
            pub_date = parse_date(pub) or TODAY
            if not within_lookback(pub_date):
                continue
            articles.append(_make_article(sid, sname, link, segs, title, desc, pub_date))

    return articles


def _make_article(sid, sname, link, segs, title, summary, pub_date) -> dict:
    raw_text = (title + " " + summary).lower()
    return {
        "source_id":       sid,
        "source_name":     sname,
        "source_url":      link,
        "source_segments": segs,
        "title":           title,
        "summary":         summary[:500],
        "published_date":  pub_date,
        "raw_text":        raw_text,
    }


# ─────────────────────────────────────────────────────────────────────────
# feedparser 파서 (설치된 경우 우선 사용)
# ─────────────────────────────────────────────────────────────────────────
def parse_feedparser(url: str, feed: dict) -> list[dict]:
    sid   = feed["id"]
    sname = feed["name"]
    segs  = feed["segments"]
    articles: list[dict] = []

    socket.setdefaulttimeout(FETCH_TIMEOUT)
    fp = feedparser.parse(url)
    status = getattr(fp, "status", 200)
    if status >= 400:
        raise Exception(f"HTTP {status}")

    for entry in fp.entries[:MAX_ITEMS]:
        title   = getattr(entry, "title", "").strip()
        if not title or title == "[Removed]":
            continue
        summary = strip_html(getattr(entry, "summary", "") or "")
        link    = getattr(entry, "link", "") or url
        t       = (
            getattr(entry, "published_parsed", None) or
            getattr(entry, "updated_parsed", None)
        )
        pub_date = (
            f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
            if t else TODAY
        )
        if not within_lookback(pub_date):
            continue
        articles.append(_make_article(sid, sname, link, segs, title, summary, pub_date))

    return articles


# ─────────────────────────────────────────────────────────────────────────
# HTTP fetch (urllib, sync → thread pool에서 실행)
# ─────────────────────────────────────────────────────────────────────────
def _http_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()


# ─────────────────────────────────────────────────────────────────────────
# Feed Health Registry
# ─────────────────────────────────────────────────────────────────────────
class HealthRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, dict] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
                disabled = sum(1 for v in self._data.values() if v.get("disabled"))
                print(f"[HEALTH] 로드: {len(self._data)}개 피드  (비활성화: {disabled}개)")
            except Exception:
                print("[HEALTH] 로드 실패 — 새로 시작")
        else:
            print("[HEALTH] 파일 없음 — 새로 생성")

    def get(self, feed_id: str, feed_name: str) -> dict:
        if feed_id not in self._data:
            self._data[feed_id] = {
                "id": feed_id, "name": feed_name,
                "consecutive_failures": 0,
                "total_runs": 0, "total_successes": 0,
                "last_success": "", "last_failure_reason": "",
                "disabled": False, "disabled_reason": "",
            }
        return self._data[feed_id]

    def success(self, feed_id: str, count: int):
        h = self._data.get(feed_id, {})
        h["total_runs"]        = h.get("total_runs", 0) + 1
        h["total_successes"]   = h.get("total_successes", 0) + 1
        h["consecutive_failures"] = 0
        h["last_success"]      = TODAY
        self._data[feed_id]    = h

    def failure(self, feed_id: str, reason: str):
        h = self._data.get(feed_id, {})
        h["total_runs"]        = h.get("total_runs", 0) + 1
        h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
        h["last_failure_reason"] = reason[:200]
        if h["consecutive_failures"] >= MAX_FAIL:
            h["disabled"]        = True
            h["disabled_reason"] = f"연속 {h['consecutive_failures']}회 실패. 최근: {reason[:100]}"
        self._data[feed_id] = h

    def is_disabled(self, feed_id: str) -> bool:
        return self._data.get(feed_id, {}).get("disabled", False)

    def reset(self):
        for v in self._data.values():
            v["consecutive_failures"] = 0
            v["disabled"] = False
            v["disabled_reason"] = ""
        self.save()
        print("[HEALTH] 초기화 완료")

    def save(self):
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def make_source_log(self, feed: dict, status: str, error: Optional[str], count: int) -> dict:
        return {
            "id":           feed["id"],
            "name":         feed["name"],
            "url":          feed["url"],
            "status":       status,
            "error":        error,
            "items":        count,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "source_type":  feed.get("source_type", "industry"),
            "reliability":  feed.get("reliability", 3),
            "topics":       feed.get("topics", []),
            "geography":    feed.get("geography", "GLOBAL"),
            "approved_by":  feed.get("approved_by", "analyst"),
            "approved_date":feed.get("approved_date", "2025-01-01"),
        }


# ─────────────────────────────────────────────────────────────────────────
# Deduplication_
# ─────────────────────────────────────────────────────────────────────────
def _dedup_key(url: str, title: str) -> str:
    norm_url = url.split("?")[0].split("#")[0].rstrip("/").lower()
    if norm_url and norm_url != "":
        return hashlib.md5(norm_url.encode()).hexdigest()
    return hashlib.md5(title.strip().lower().encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# 일별 캐시 (당일 재실행 시 중복 방지)
# ─────────────────────────────────────────────────────────────────────────
class DailyCache:
    def __init__(self):
        self.path = CACHE_DIR / f"{TODAY}.json"
        self._seen: set[str] = set()
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._seen = set(data.get("seen", []))
                print(f"[CACHE] 로드: {len(self._seen)}개 기존 키")
            except Exception:
                pass

    def seen(self, key: str) -> bool:
        return key in self._seen

    def mark(self, key: str):
        self._seen.add(key)

    def save(self):
        self.path.write_text(json.dumps({"date": TODAY, "seen": list(self._seen)}, indent=2))


# ─────────────────────────────────────────────────────────────────────────
# 단일 피드 수집 (async)
# ─────────────────────────────────────────────────────────────────────────
async def fetch_feed(
    feed: dict,
    health: HealthRegistry,
    cache: DailyCache,
    executor: concurrent.futures.ThreadPoolExecutor,
) -> tuple[list[dict], dict]:
    """
    Returns (new_articles, source_log)
    """
    fid   = feed["id"]
    fname = feed["name"]
    url   = feed["url"]

    if health.is_disabled(fid):
        h = health.get(fid, fname)
        print(f"  ⊘ {fname:28s} [비활성화] {h.get('disabled_reason','')[:50]}")
        return [], health.make_source_log(feed, "skipped", "disabled", 0)

    print(f"  ↓ {fname:28s} {url}")

    loop = asyncio.get_event_loop()

    try:
        # feedparser 우선
        if HAS_FEEDPARSER:
            articles = await asyncio.wait_for(
                loop.run_in_executor(executor, parse_feedparser, url, feed),
                timeout=FETCH_TIMEOUT + 5,
            )
        else:
            # urllib + xml fallback
            xml_bytes = await asyncio.wait_for(
                loop.run_in_executor(executor, _http_fetch, url),
                timeout=FETCH_TIMEOUT + 5,
            )
            articles = parse_xml_feed(xml_bytes, feed)

    except asyncio.TimeoutError:
        reason = f"Timeout ({FETCH_TIMEOUT}s)"
        health.failure(fid, reason)
        print(f"    ✗ {fname:28s} → {reason}")
        return [], health.make_source_log(feed, "failed", reason, 0)
    except urllib.error.HTTPError as e:
        reason = f"HTTP {e.code} {e.reason}"
        health.failure(fid, reason)
        print(f"    ✗ {fname:28s} → {reason}")
        return [], health.make_source_log(feed, "failed", reason, 0)
    except Exception as e:
        reason = f"{type(e).__name__}: {str(e)[:100]}"
        health.failure(fid, reason)
        print(f"    ✗ {fname:28s} → {reason}")
        return [], health.make_source_log(feed, "failed", reason, 0)

    if not articles:
        reason = "0개 기사 반환"
        health.failure(fid, reason)
        print(f"    ✗ {fname:28s} → {reason}")
        return [], health.make_source_log(feed, "partial", reason, 0)

    # 노이즈 필터 + 중복 제거
    new_articles: list[dict] = []
    skipped_noise = 0
    skipped_dedup = 0
    skipped_old   = 0

    for art in articles:
        title = art.get("title", "")
        link  = art.get("source_url", "")
        combined = title + " " + art.get("summary", "")

        if NOISE_RE.search(combined):
            skipped_noise += 1
            continue

        pub = art.get("published_date", "")
        if pub and not within_lookback(pub):
            skipped_old += 1
            continue

        key = _dedup_key(link, title)
        if cache.seen(key):
            skipped_dedup += 1
            continue

        cache.mark(key)
        new_articles.append(art)

    health.success(fid, len(new_articles))
    h_data = health.get(fid, fname)
    runs   = h_data.get("total_runs", 1)
    sr     = h_data.get("total_successes", 1) / runs * 100 if runs else 100

    print(
        f"    ✓ {fname:28s} → "
        f"새기사={len(new_articles):3d}  "
        f"(raw={len(articles)}  noise={skipped_noise}  dup={skipped_dedup}  old={skipped_old})  "
        f"성공률={sr:.0f}%"
    )
    return new_articles, health.make_source_log(feed, "success" if new_articles else "partial", None, len(new_articles))


# ─────────────────────────────────────────────────────────────────────────
# 메인 파이프라인
# ─────────────────────────────────────────────────────────────────────────
async def run(dry_run: bool = False) -> list[dict]:
    ts_start = datetime.now(timezone.utc)
    print(f"\n{'═'*62}")
    print(f"  collect_energy_signals.py  v3.0   {TODAY}")
    print(f"  feedparser: {'✓ 사용' if HAS_FEEDPARSER else '✗ urllib fallback'}")
    print(f"{'═'*62}\n")

    health = HealthRegistry(HEALTH_PATH)
    cache  = DailyCache()

    enabled  = [f for f in FEEDS if not health.is_disabled(f["id"])]
    disabled = [f for f in FEEDS if health.is_disabled(f["id"])]
    print(f"[FEEDS] 전체={len(FEEDS)}  활성={len(enabled)}  비활성={len(disabled)}\n")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    all_articles: list[dict] = []
    all_logs:     list[dict] = []

    # Priority 순으로 배치 실행
    for priority in [1, 2, 3]:
        batch = [f for f in enabled if f.get("priority", 2) == priority]
        if not batch:
            continue
        print(f"── Priority {priority} ({len(batch)}개 피드) ─────────────────────────")
        tasks = [fetch_feed(f, health, cache, executor) for f in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for feed, result in zip(batch, results):
            if isinstance(result, Exception):
                print(f"    ✗ {feed['name']} unhandled: {result}")
                all_logs.append(health.make_source_log(feed, "failed", str(result), 0))
            else:
                arts, log = result
                all_articles.extend(arts)
                all_logs.append(log)
        print()

    executor.shutdown(wait=False)

    # 교차-피드 중복 제거 (같은 기사 여러 피드에 있는 경우)
    seen_global: set[str] = set()
    unique: list[dict] = []
    cross_dup = 0
    for art in all_articles:
        key = _dedup_key(art["source_url"], art["title"])
        if key in seen_global:
            cross_dup += 1
        else:
            seen_global.add(key)
            unique.append(art)

    elapsed = (datetime.now(timezone.utc) - ts_start).total_seconds()

    # 소스별 통계
    by_source: dict[str, int] = defaultdict(int)
    by_seg:    dict[str, int] = defaultdict(int)
    for art in unique:
        by_source[art["source_name"]] += 1
        for seg in art.get("source_segments", []):
            by_seg[seg] += 1

    ok_count   = sum(1 for l in all_logs if l["status"] == "success")
    fail_count = sum(1 for l in all_logs if l["status"] == "failed")

    print(f"{'═'*62}")
    print(f"  수집 결과 ({elapsed:.1f}초)")
    print(f"  소스: 성공={ok_count}  실패={fail_count}  교차중복={cross_dup}")
    print(f"  최종 기사: {len(unique)}개")
    print()
    print(f"  소스별:")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {src:30s}: {cnt:3d}개")
    print()
    print(f"  세그먼트별:")
    for seg, cnt in sorted(by_seg.items(), key=lambda x: -x[1]):
        print(f"    {seg:20s}: {cnt:3d}개")
    print(f"{'═'*62}\n")

    if not dry_run:
        _save(unique, all_logs)
        cache.save()
        health.save()
    else:
        print(f"[DRY-RUN] 저장 안 함 — {len(unique)}개 기사 수집됨")

    return unique


def _save(articles: list[dict], logs: list[dict]) -> None:
    """
    data/extended_raw.json 으로 저장.
    generate-signals.py의 fetch_sources()가 이 파일을 자동으로 읽어 머지.
    기존 파일이 오늘 날짜면 중복 제거 후 머지, 아니면 새로 씀.
    """
    existing_articles: list[dict] = []
    existing_logs:     list[dict] = []

    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if prev.get("date") == TODAY:
                existing_articles = prev.get("articles", [])
                existing_logs     = prev.get("source_logs", [])
        except Exception:
            pass

    # 기존 기사와 중복 제거 후 머지
    seen_keys = {
        _dedup_key(a["source_url"], a["title"])
        for a in existing_articles
    }
    new_only = [
        a for a in articles
        if _dedup_key(a["source_url"], a["title"]) not in seen_keys
    ]
    merged_articles = existing_articles + new_only

    # source_logs: 같은 source_id는 최신 것으로 덮어쓰기
    log_map = {l["id"]: l for l in existing_logs}
    for l in logs:
        log_map[l["id"]] = l
    merged_logs = list(log_map.values())

    payload = {
        "date":        TODAY,
        "articles":    merged_articles,
        "source_logs": merged_logs,
    }
    OUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[SAVE] {OUT_PATH}"
        f"  총={len(merged_articles)}개  (이번 실행 신규={len(new_only)}개)"
    )


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--reset-health" in args:
        h = HealthRegistry(HEALTH_PATH)
        h.reset()
        print("피드 Health 초기화 완료.")
        if len(args) == 1:
            sys.exit(0)

    dry_run = "--dry-run" in args

    arts = asyncio.run(run(dry_run=dry_run))
    ok  = sum(1 for a in arts if a)
    print(f"완료: {ok}개 기사 수집.")


if __name__ == "__main__":
    main()

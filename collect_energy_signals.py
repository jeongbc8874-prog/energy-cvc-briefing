"""
collect_energy_signals.py
Energy CVC Intelligence Platform — Phase 1 Signal Collector  v2.0

설계 원칙:
  - 외부 의존성 ZERO: stdlib만 사용 (feedparser, aiohttp 불필요)
    urllib.request + asyncio + ThreadPoolExecutor + xml.etree.ElementTree
  - 실패 소스 자동 제외: consecutive_failures >= MAX_CONSECUTIVE → disabled
  - Deduplication: URL(쿼리 제외) + 제목 기반 MD5
  - 일별 캐시: data/cache/YYYY-MM-DD.json (재실행 시 중복 수집 방지)
  - 섹터 8개 이상 커버, 노이즈 자동 제거
  - 목표: 하루 80~150 signals (소스 6개 × 평균 15~25개)

실행:
  python collect_energy_signals.py              # 전체 실행
  python collect_energy_signals.py --dry-run    # 파싱만, 저장 안 함
  python collect_energy_signals.py --reset-health  # 실패 이력 초기화
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("collect_signals")

# ─────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────
BASE_DIR         = Path(os.environ.get("BASE_DIR", "data"))
SIGNALS_OUT_DIR  = BASE_DIR / "raw_signals"
CACHE_DIR        = BASE_DIR / "cache"
HEALTH_PATH      = BASE_DIR / "feed_health.json"

SIGNALS_OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TODAY_STR = date.today().isoformat()

# ─────────────────────────────────────────────────────────
# Tuning constants
# ─────────────────────────────────────────────────────────
FETCH_TIMEOUT_SEC   = 20      # per-feed HTTP timeout
MAX_WORKERS         = 8       # ThreadPoolExecutor size
MAX_CONSECUTIVE_FAIL= 3       # 연속 실패 N회 → auto-disable
MAX_ITEMS_PER_FEED  = 40      # 피드당 최대 수집 (중복 제거 전)
LOOKBACK_DAYS       = 7       # 이 기간 이내 기사만 수집
HTTP_HEADERS = {
    "User-Agent":    "Mozilla/5.0 (compatible; EnergyIntelBot/2.0; +https://github.com/energy-cvc)",
    "Accept":        "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ─────────────────────────────────────────────────────────
# Feed Registry
# ─────────────────────────────────────────────────────────
# priority: 1=최우선, 2=고안정, 3=보조
FEED_REGISTRY: list[dict] = [
    # ── Core / Tier-1 ──────────────────────────────────────
    {
        "name": "Canary Media",
        "url":  "https://www.canarymedia.com/rss.rss",
        "priority": 1,
        "format": "rss",
        "notes": "High-quality clean energy journalism",
    },
    {
        "name": "EIA Today in Energy",
        "url":  "https://www.eia.gov/rss/todayinenergy.xml",
        "priority": 1,
        "format": "rss",
        "notes": "Quantitative US energy data — high signal value",
    },
    {
        "name": "PV Magazine",
        "url":  "https://www.pv-magazine.com/feed/",
        "priority": 1,
        "format": "rss",
        "notes": "Solar PV focus, global coverage",
    },
    {
        "name": "Energy Storage News",
        "url":  "https://www.energy-storage.news/feed/",
        "priority": 1,
        "format": "rss",
        "notes": "Battery & storage focused",
    },
    {
        "name": "CleanTechnica",
        "url":  "https://cleantechnica.com/feed/",
        "priority": 1,
        "format": "rss",
        "notes": "Broad clean energy, EV, storage",
    },
    {
        "name": "Electrek",
        "url":  "https://electrek.co/feed/",
        "priority": 1,
        "format": "rss",
        "notes": "EV, solar, storage consumer + utility",
    },
    # ── Tier-2 / Supplementary ─────────────────────────────
    {
        "name": "Utility Dive Energy",
        "url":  "https://www.utilitydive.com/feeds/news/",
        "priority": 2,
        "format": "rss",
        "notes": "Utility sector, grid, regulation",
    },
    {
        "name": "Renewable Energy World",
        "url":  "https://www.renewableenergyworld.com/feed/",
        "priority": 2,
        "format": "rss",
        "notes": "Broad renewables",
    },
    {
        "name": "IRENA Newsroom",
        "url":  "https://www.irena.org/rss/IRENARSSFeed",
        "priority": 2,
        "format": "rss",
        "notes": "Global renewable policy + data",
    },
    {
        "name": "AZoCleantech",
        "url":  "https://www.azocleantech.com/rss.aspx",
        "priority": 2,
        "format": "rss",
        "notes": "Technology-focused cleantech news",
    },
    {
        "name": "Wood Mackenzie Insights",
        "url":  "https://www.woodmac.com/rss/insights/",
        "priority": 2,
        "format": "rss",
        "notes": "Energy market analysis",
    },
    {
        "name": "S&P Global Clean Energy",
        "url":  "https://www.spglobal.com/commodityinsights/en/rss-feed/oil/",
        "priority": 3,
        "format": "rss",
        "notes": "Commodity + energy markets",
    },
    {
        "name": "Greentech Media",
        "url":  "https://www.greentechmedia.com/feed",
        "priority": 2,
        "format": "rss",
        "notes": "Grid, storage, solar market intelligence",
    },
    {
        "name": "Energy Monitor",
        "url":  "https://www.energymonitor.ai/feed/",
        "priority": 2,
        "format": "rss",
        "notes": "Policy + market news",
    },
    {
        "name": "Hydrogen Insight",
        "url":  "https://www.hydrogeninsight.com/feed",
        "priority": 2,
        "format": "rss",
        "notes": "Green hydrogen focused",
    },
    {
        "name": "New Atlas Energy",
        "url":  "https://newatlas.com/energy/rss/",
        "priority": 3,
        "format": "rss",
        "notes": "Tech + energy innovation",
    },
]

# ─────────────────────────────────────────────────────────
# Classification: Noise Filter
# ─────────────────────────────────────────────────────────
_NOISE_TERMS = [
    r'\bcrypto\b', r'\bbitcoin\b', r'\bethereum\b', r'\bnft\b',
    r'\bcryptocurrency\b', r'\bblockchain token\b', r'\btoken sale\b',
    r'\bstock price\b', r'\bshare price\b', r'\bearnings per share\b',
    r'\bdividend\b', r'\bforex\b', r'\bsports betting\b', r'\bcasino\b',
    r'\bweight loss\b', r'\bhealth supplement\b',
]
NOISE_RE = re.compile("|".join(_NOISE_TERMS), re.IGNORECASE)

# ─────────────────────────────────────────────────────────
# Classification: Sector
# ─────────────────────────────────────────────────────────
# 순서가 중요 — 더 구체적인 패턴을 앞에 배치
SECTOR_MAP: list[tuple[str, list[str]]] = [
    ("long_duration_storage",  [
        r"iron.?air", r"long.?duration", r"LDES", r"flow battery",
        r"vanadium redox", r"zinc.?based", r"compressed air", r"liquid air",
        r"gravity storage", r"thermal energy storage",
    ]),
    ("battery_storage",        [
        r"lithium.?ion", r"li-?ion", r"BESS", r"battery storage",
        r"grid.?scale battery", r"battery system", r"battery energy storage",
        r"solid.?state battery", r"sodium.?ion",
    ]),
    ("green_hydrogen",         [
        r"green hydrogen", r"electroly[sz]er", r"electrolysis",
        r"hydrogen storage", r"fuel cell", r"ammonia fuel",
        r"proton exchange membrane", r"PEM electrolyzer",
        r"hydrogen production", r"blue hydrogen",
    ]),
    ("grid_software",          [
        r"virtual power plant", r"\bVPP\b", r"demand response",
        r"grid software", r"\bDERMS\b", r"energy management system",
        r"smart grid", r"grid orchestration", r"distributed energy resource",
    ]),
    ("advanced_nuclear",       [
        r"small modular reactor", r"\bSMR\b", r"advanced nuclear",
        r"molten salt reactor", r"nuclear fusion", r"microreactor",
        r"next.?gen nuclear", r"thorium reactor",
    ]),
    ("data_center_power",      [
        r"data center power", r"data centre power", r"hyperscaler",
        r"AI power demand", r"AI energy", r"colocation energy",
        r"server farm power",
    ]),
    ("geothermal",             [
        r"geothermal", r"enhanced geothermal", r"\bEGS\b",
        r"geothermal power plant", r"geothermal energy",
    ]),
    ("offshore_wind",          [
        r"offshore wind", r"floating wind", r"floating offshore",
        r"wind turbine install", r"wind farm",
    ]),
    ("solar_pv",               [
        r"solar panel", r"photovoltaic", r"\bPV\b", r"rooftop solar",
        r"utility.?scale solar", r"perovskite", r"thin.?film solar",
        r"bifacial", r"solar module",
    ]),
    ("onshore_wind",           [
        r"onshore wind", r"wind power", r"wind energy",
        r"wind turbine", r"wind park",
    ]),
    ("transmission_grid",      [
        r"transmission line", r"grid upgrade", r"\bHVDC\b",
        r"power line", r"intercon", r"grid interconnection",
        r"substation", r"grid capacity",
    ]),
    ("ev_charging",            [
        r"EV charging", r"electric vehicle charging", r"charging station",
        r"charging infrastructure", r"fast charge",
    ]),
    ("carbon_capture",         [
        r"carbon capture", r"\bCCUS?\b", r"direct air capture",
        r"\bDAC\b", r"carbon removal",
    ]),
]

def _build_sector_re():
    return [
        (sector, re.compile("|".join(pats), re.IGNORECASE))
        for sector, pats in SECTOR_MAP
    ]
SECTOR_RE_LIST = _build_sector_re()

def classify_sector(text: str) -> str:
    for sector, rx in SECTOR_RE_LIST:
        if rx.search(text):
            return sector
    return "other_energy"

# ─────────────────────────────────────────────────────────
# Classification: Event Type
# ─────────────────────────────────────────────────────────
EVENT_MAP: list[tuple[str, list[str]]] = [
    ("Contract",       [r"\bcontract\b", r"\bagreement\b", r"\bdeal\b",
                        r"\baward\b", r"\bsigns?\b.*deal", r"\bPPA\b"]),
    ("Deployment",     [r"\bdeploy", r"\binstall", r"\bcommission",
                        r"\boperational\b", r"\bgoes live\b", r"\bonline\b",
                        r"\bbreaks? ground\b", r"\bstarts? operation"]),
    ("Funding",        [r"\bfunding\b", r"\braises?\b", r"\binvestment\b",
                        r"\bseries [A-E]\b", r"\bventure\b", r"\bround\b.*\$",
                        r"\bIPO\b", r"\bSPAC\b"]),
    ("Certification",  [r"\bcertif", r"\bapprov", r"\bpermit",
                        r"\blicens", r"\bregulatory clearance\b"]),
    ("Partnership",    [r"\bpartner", r"\bcollaborat", r"\bjoint venture\b",
                        r"\bMOU\b", r"\bmemorandum\b", r"\balliance\b"]),
    ("Grant",          [r"\bgrant\b", r"\bsubsidy\b", r"\bfederal funding\b",
                        r"\bDOE\b.*award", r"\bstimulus\b"]),
    ("Pilot",          [r"\bpilot\b", r"\bdemonstrat", r"\btrial\b",
                        r"\bproof of concept\b", r"\bfield test\b"]),
    ("Product_Launch", [r"\blaunch", r"\bunveil", r"\bintroduc",
                        r"\bannounces? product\b", r"\bnew product\b"]),
    ("Patent",         [r"\bpatent\b", r"\bintellectual property\b",
                        r"\bIP filing\b"]),
    ("Regulation",     [r"\bregulat", r"\bpolicy\b", r"\blegislat",
                        r"\brule\b.*energy", r"\bmandate\b"]),
    ("Publication",    [r"\bstudy\b", r"\bresearch\b", r"\bpaper\b",
                        r"\breport\b", r"\banalysis\b", r"\bdata shows\b"]),
]
EVENT_RE_LIST = [
    (etype, re.compile("|".join(pats), re.IGNORECASE))
    for etype, pats in EVENT_MAP
]

def classify_event(text: str) -> str:
    for etype, rx in EVENT_RE_LIST:
        if rx.search(text):
            return etype
    return "News"

# ─────────────────────────────────────────────────────────
# Signal Strength + Tier
# ─────────────────────────────────────────────────────────
_HIGH_VALUE_EVENTS  = {"Contract", "Deployment", "Certification", "Funding"}
_MED_VALUE_EVENTS   = {"Partnership", "Grant", "Pilot", "Product_Launch"}
_QUANT_RE = re.compile(
    r"\d[\d,]*\s*(MW|GW|GWh|MWh|kW|TWh"
    r"|\$[\d,]+[BbMm]?"
    r"|\d+\s*(billion|million|trillion)"
    r"|tonne|metric ton)",
    re.IGNORECASE
)
_COMPANY_SIGNAL_RE = re.compile(
    r"\b(Form Energy|Amogy|AutoGrid|EnerVenue|Northvolt|Tesla|Fluence|Stem"
    r"|NextEra|Enel|Vestas|Orsted|BP|Shell|Chevron|ExxonMobil"
    r"|Google|Amazon|Microsoft|Meta|Apple|Bloom Energy|Plug Power"
    r"|Nel\b|ITM Power|H2 Green Steel|Commonwealth Fusion"
    r"|X-energy|Kairos Power|Oklo|NuScale|TerraPower"
    r"|Siemens Energy|Schneider Electric|ABB|GE Vernova"
    r"|Eos Energy|Energy Dome|Malta Inc|Gravitricity"
    r"|Redwood Materials|Li-Cycle|Ascend Elements"
    r"|Intersect Power|Ørsted|RWE|Iberdrola|Acciona"
    r"|Enphase|SunPower|First Solar|Array Technologies)\b",
    re.IGNORECASE
)

def compute_signal_strength(title: str, desc: str, event_type: str) -> tuple[float, str]:
    """Returns (strength 0.0-1.0, tier 'high'|'medium'|'low')"""
    score = 0.30  # base

    if event_type in _HIGH_VALUE_EVENTS:
        score += 0.35
    elif event_type in _MED_VALUE_EVENTS:
        score += 0.20

    combined = title + " " + desc
    if _QUANT_RE.search(combined):
        score += 0.20
    if _COMPANY_SIGNAL_RE.search(combined):
        score += 0.10

    score = round(min(score, 1.0), 2)
    tier = "high" if score >= 0.70 else "medium" if score >= 0.50 else "low"
    return score, tier

# ─────────────────────────────────────────────────────────
# Company extraction
# ─────────────────────────────────────────────────────────
def extract_companies(text: str) -> list[str]:
    return sorted({m.group() for m in _COMPANY_SIGNAL_RE.finditer(text)})

# ─────────────────────────────────────────────────────────
# HTML stripper
# ─────────────────────────────────────────────────────────
class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
    def handle_data(self, data: str):
        self._parts.append(data)
    def get_text(self) -> str:
        return " ".join(self._parts)

def strip_html(html: str) -> str:
    if not html:
        return ""
    s = _Stripper()
    try:
        s.feed(html)
        text = s.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

# ─────────────────────────────────────────────────────────
# Date parsing
# ─────────────────────────────────────────────────────────
import email.utils

def parse_date(raw: str) -> Optional[str]:
    """Returns ISO 8601 date string or None."""
    if not raw:
        return None
    raw = raw.strip()
    # RFC 2822 (RSS)
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return dt.date().isoformat()
    except Exception:
        pass
    # ISO 8601 (Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19], fmt[:len(raw[:19])])
            return dt.date().isoformat()
        except Exception:
            continue
    return None

def is_within_lookback(date_str: Optional[str], days: int = LOOKBACK_DAYS) -> bool:
    if not date_str:
        return True  # 날짜 불명 → 포함
    try:
        pub = date.fromisoformat(date_str)
        return (date.today() - pub).days <= days
    except Exception:
        return True

# ─────────────────────────────────────────────────────────
# Deduplication helpers
# ─────────────────────────────────────────────────────────
def _normalize_url(url: str) -> str:
    """Remove query params and fragments for dedup."""
    return url.split("?")[0].split("#")[0].rstrip("/").lower()

def _dedup_key(url: str, title: str) -> str:
    if url:
        return hashlib.md5(_normalize_url(url).encode()).hexdigest()
    return hashlib.md5(title.strip().lower().encode()).hexdigest()

def _signal_id(url: str, title: str) -> str:
    raw = f"{_normalize_url(url)}::{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

# ─────────────────────────────────────────────────────────
# Feed Health tracking
# ─────────────────────────────────────────────────────────
@dataclass
class FeedHealth:
    url:                  str
    name:                 str
    consecutive_failures: int  = 0
    total_runs:           int  = 0
    total_successes:      int  = 0
    last_success:         str  = ""
    last_failure_reason:  str  = ""
    disabled:             bool = False
    disabled_reason:      str  = ""

    @property
    def success_rate(self) -> float:
        return self.total_successes / self.total_runs if self.total_runs else 1.0

    def record_success(self, item_count: int) -> None:
        self.total_runs += 1
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success = TODAY_STR
        log.info(
            "  ✓ %-30s  items=%-3d  runs=%d  success_rate=%.0f%%",
            self.name, item_count, self.total_runs, self.success_rate * 100
        )

    def record_failure(self, reason: str) -> None:
        self.total_runs += 1
        self.consecutive_failures += 1
        self.last_failure_reason = reason
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAIL:
            self.disabled = True
            self.disabled_reason = (
                f"Auto-disabled after {self.consecutive_failures} consecutive "
                f"failures. Last error: {reason}"
            )
            log.warning(
                "  ✗ %-30s  DISABLED after %d consecutive failures. Last: %s",
                self.name, self.consecutive_failures, reason[:80]
            )
        else:
            log.warning(
                "  ✗ %-30s  failure %d/%d — %s",
                self.name, self.consecutive_failures, MAX_CONSECUTIVE_FAIL, reason[:80]
            )


class HealthRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, FeedHealth] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                for url, d in raw.items():
                    self._data[url] = FeedHealth(**d)
                log.info("[HEALTH] Loaded health registry — %d feeds tracked", len(self._data))
            except Exception as e:
                log.warning("[HEALTH] Could not load health registry: %s — starting fresh", e)

    def get(self, feed: dict) -> FeedHealth:
        url = feed["url"]
        if url not in self._data:
            self._data[url] = FeedHealth(url=url, name=feed["name"])
        return self._data[url]

    def save(self) -> None:
        self.path.write_text(
            json.dumps({url: asdict(h) for url, h in self._data.items()}, indent=2)
        )
        log.info("[HEALTH] Registry saved → %s", self.path)

    def reset(self) -> None:
        self._data = {}
        self.save()
        log.info("[HEALTH] Registry reset — all failure counts cleared")

# ─────────────────────────────────────────────────────────
# Daily cache (dedup across runs)
# ─────────────────────────────────────────────────────────
class DailyCache:
    def __init__(self, cache_dir: Path):
        self.path = cache_dir / f"{TODAY_STR}.json"
        self._seen: set[str] = set()
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text())
                self._seen = set(saved.get("seen_keys", []))
                log.info("[CACHE] Loaded — %d already-seen keys", len(self._seen))
            except Exception:
                log.warning("[CACHE] Could not load cache — starting fresh")

    def is_seen(self, key: str) -> bool:
        return key in self._seen

    def mark(self, key: str) -> None:
        self._seen.add(key)

    def save(self) -> None:
        self.path.write_text(json.dumps({"date": TODAY_STR, "seen_keys": list(self._seen)}, indent=2))
        log.info("[CACHE] Saved — %d seen keys → %s", len(self._seen), self.path)

# ─────────────────────────────────────────────────────────
# RSS / Atom XML Parser
# ─────────────────────────────────────────────────────────
ATOM_NS = "http://www.w3.org/2005/Atom"

def _text(el: Optional[ET.Element], tag: str, ns: Optional[str] = None) -> str:
    """Safe child text extraction."""
    if el is None:
        return ""
    child = el.find(f"{{{ns}}}{tag}" if ns else tag)
    return (child.text or "").strip() if child is not None else ""

def parse_rss(xml_bytes: bytes, source_name: str, source_base_url: str) -> list[dict]:
    """Parse RSS 2.0 or Atom 1.0 bytes into raw article dicts."""
    articles: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    tag = root.tag.lower()

    # ── Atom ─────────────────────────────────────────────
    if "atom" in tag or root.tag == f"{{{ATOM_NS}}}feed":
        ns = ATOM_NS
        entries = root.findall(f"{{{ns}}}entry")
        for entry in entries[:MAX_ITEMS_PER_FEED]:
            title   = _text(entry, "title", ns)
            summary = strip_html(_text(entry, "summary", ns) or _text(entry, "content", ns))
            pub     = _text(entry, "updated", ns) or _text(entry, "published", ns)
            link_el = entry.find(f"{{{ns}}}link")
            link    = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")
            guid = _text(entry, "id", ns) or link
            articles.append({
                "title":          title,
                "link":           link or source_base_url,
                "pub_date_raw":   pub,
                "description":    summary,
                "guid":           guid,
                "source_name":    source_name,
            })
        return articles

    # ── RSS 2.0 ──────────────────────────────────────────
    items = root.findall(".//item")
    if not items:
        # Some feeds wrap in <channel>
        channel = root.find("channel")
        if channel is not None:
            items = channel.findall("item")

    for item in items[:MAX_ITEMS_PER_FEED]:
        title   = _text(item, "title")
        desc    = strip_html(
            _text(item, "description") or
            _text(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
        )
        pub     = _text(item, "pubDate") or _text(item, "dc:date")
        link    = _text(item, "link") or _text(item, "guid")
        guid    = _text(item, "guid") or link
        articles.append({
            "title":          title,
            "link":           link or source_base_url,
            "pub_date_raw":   pub,
            "description":    desc,
            "guid":           guid,
            "source_name":    source_name,
        })
    return articles

# ─────────────────────────────────────────────────────────
# Article → Signal conversion
# ─────────────────────────────────────────────────────────
def article_to_signal(article: dict) -> Optional[dict]:
    """
    Convert a raw article dict to a structured signal dict.
    Returns None if the article is noise or out of lookback window.
    """
    title   = (article.get("title") or "").strip()
    desc    = (article.get("description") or "").strip()
    link    = (article.get("link") or "").strip()
    pub_raw = article.get("pub_date_raw", "")
    source  = article.get("source_name", "")

    if not title:
        return None

    combined = title + " " + desc

    # Noise filter
    if NOISE_RE.search(combined):
        return None

    # Date filter
    pub_date = parse_date(pub_raw)
    if not is_within_lookback(pub_date):
        return None

    # Classify
    sector     = classify_sector(combined)
    event_type = classify_event(combined)
    strength, tier = compute_signal_strength(title, desc, event_type)
    companies  = extract_companies(combined)

    # observed_fact: title is the fact; desc provides support
    observed_fact = title
    why_matters   = _why_it_matters(sector, event_type, title)
    missing_evid  = _missing_evidence(event_type, desc)

    sig_id = _signal_id(link, title)

    return {
        "id":                         sig_id,
        "title":                      title,
        "source_name":                source,
        "source_url":                 link,
        "published_date":             pub_date or TODAY_STR,
        "observed_fact":              observed_fact,
        "why_it_matters_investment":  why_matters,
        "missing_evidence":           missing_evid,
        "signal_tier":                tier,
        "signal_strength":            strength,
        "sector":                     sector,
        "event_type":                 event_type,
        "companies_mentioned":        companies,
        "collected_date":             TODAY_STR,
    }

def _why_it_matters(sector: str, event_type: str, title: str) -> str:
    templates = {
        ("Contract",      "long_duration_storage"):  "Validated commercial demand for LDES; de-risks revenue model for investors.",
        ("Deployment",    "long_duration_storage"):  "Real-world deployment evidence; key proof point beyond lab stage.",
        ("Funding",       "long_duration_storage"):  "Capital into LDES signals investor conviction and accelerates commercialization.",
        ("Contract",      "battery_storage"):        "Commercial offtake confirmation; reduces market risk for battery storage plays.",
        ("Deployment",    "battery_storage"):        "Operating asset evidence; critical for bankability of BESS projects.",
        ("Funding",       "green_hydrogen"):         "Electrolyzer or H2 infrastructure funding; watch for cost reduction trajectory.",
        ("Contract",      "green_hydrogen"):         "H2 offtake agreement; validates demand-side and enables project finance.",
        ("Funding",       "advanced_nuclear"):       "SMR funding signals utility/government conviction in nuclear baseload.",
        ("Contract",      "grid_software"):          "SaaS/platform contract win; validates enterprise go-to-market traction.",
        ("Deployment",    "grid_software"):          "Live deployment proves scalability; signals potential for network effects.",
        ("Grant",         "geothermal"):             "Government grant de-risks EGS technology; watch for DOE involvement.",
        ("Deployment",    "offshore_wind"):          "Offshore wind commissioning evidence; important for supply chain stocks.",
    }
    key = (event_type, sector)
    if key in templates:
        return templates[key]
    # Fallback
    sector_nice = sector.replace("_", " ").title()
    return (
        f"{event_type} event in {sector_nice}. "
        f"Monitor for follow-on deals, competitive response, and valuation impact."
    )

def _missing_evidence(event_type: str, desc: str) -> list[str]:
    missing = []
    if event_type == "Funding" and not re.search(r"\$[\d,]+|\d+\s*(million|billion)", desc, re.I):
        missing.append("Funding amount not disclosed")
    if event_type in ("Contract", "Deployment") and not re.search(r"\d+\s*(MW|GW|MWh|GWh)", desc, re.I):
        missing.append("Capacity / project size not specified")
    if event_type == "Contract" and not re.search(r"\b(counterpart|customer|utility|buyer|offtaker)\b", desc, re.I):
        missing.append("Contract counterparty not named")
    if not re.search(r"https?://", desc) and not desc:
        missing.append("No supporting description available")
    return missing

# ─────────────────────────────────────────────────────────
# HTTP Fetch (sync, runs in thread pool)
# ─────────────────────────────────────────────────────────
def _http_fetch(url: str, timeout: int = FETCH_TIMEOUT_SEC) -> bytes:
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

# ─────────────────────────────────────────────────────────
# Per-feed async pipeline
# ─────────────────────────────────────────────────────────
async def collect_feed(
    feed:       dict,
    health:     FeedHealth,
    cache:      DailyCache,
    executor:   concurrent.futures.ThreadPoolExecutor,
) -> list[dict]:
    """
    Fetch → parse → filter → convert for one feed.
    Returns list of new signal dicts (not yet in cache).
    """
    url  = feed["url"]
    name = feed["name"]

    if health.disabled:
        log.info("  ⊘ %-30s  [DISABLED — skipping]", name)
        return []

    log.info("  ↓ %-30s  fetching %s", name, url)

    loop = asyncio.get_event_loop()
    try:
        xml_bytes = await asyncio.wait_for(
            loop.run_in_executor(executor, _http_fetch, url),
            timeout=FETCH_TIMEOUT_SEC + 5,
        )
    except asyncio.TimeoutError:
        health.record_failure(f"Timeout after {FETCH_TIMEOUT_SEC}s")
        return []
    except urllib.error.HTTPError as e:
        health.record_failure(f"HTTP {e.code} {e.reason}")
        return []
    except urllib.error.URLError as e:
        health.record_failure(f"URLError: {e.reason}")
        return []
    except Exception as e:
        health.record_failure(f"{type(e).__name__}: {e}")
        return []

    # Parse
    try:
        articles = parse_rss(xml_bytes, name, url)
    except Exception as e:
        health.record_failure(f"Parse error: {e}")
        return []

    if not articles:
        health.record_failure("Feed returned 0 items (empty or unrecognized format)")
        return []

    # Filter + convert
    new_signals: list[dict] = []
    skipped_noise   = 0
    skipped_dedup   = 0
    skipped_old     = 0

    for art in articles:
        link  = art.get("link", "")
        title = art.get("title", "")
        key   = _dedup_key(link, title)

        if cache.is_seen(key):
            skipped_dedup += 1
            continue

        sig = article_to_signal(art)

        if sig is None:
            # Could be noise or old — check
            pub = parse_date(art.get("pub_date_raw", ""))
            if pub and not is_within_lookback(pub):
                skipped_old += 1
            else:
                skipped_noise += 1
            continue

        cache.mark(key)
        new_signals.append(sig)

    health.record_success(len(new_signals))
    log.info(
        "    → new=%-3d  noise=%-2d  dedup=%-2d  old=%-2d  (raw=%d)",
        len(new_signals), skipped_noise, skipped_dedup, skipped_old, len(articles)
    )
    return new_signals

# ─────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────
async def run_collection(dry_run: bool = False) -> list[dict]:
    log.info("═══ collect_energy_signals.py v2.0  date=%s ═══", TODAY_STR)

    health_reg = HealthRegistry(HEALTH_PATH)
    cache      = DailyCache(CACHE_DIR)

    # Sort by priority (1 first), then by name
    feeds = sorted(FEED_REGISTRY, key=lambda f: (f["priority"], f["name"]))

    enabled  = [f for f in feeds if not health_reg.get(f).disabled]
    disabled = [f for f in feeds if health_reg.get(f).disabled]

    log.info("[FEEDS] Total=%d  Enabled=%d  Disabled=%d",
             len(feeds), len(enabled), len(disabled))
    if disabled:
        for f in disabled:
            h = health_reg.get(f)
            log.info("  ⊘ %-30s  %s", f["name"], h.disabled_reason[:70])

    log.info("─── Collecting from %d active feeds ───────────────────────────", len(enabled))

    all_signals: list[dict] = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # Batch by priority tier
    for priority in [1, 2, 3]:
        tier_feeds = [f for f in enabled if f["priority"] == priority]
        if not tier_feeds:
            continue
        log.info("[PRIORITY %d] %d feeds", priority, len(tier_feeds))

        tasks = [
            collect_feed(f, health_reg.get(f), cache, executor)
            for f in tier_feeds
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for feed, result in zip(tier_feeds, results):
            if isinstance(result, Exception):
                log.error("  Unhandled exception for %s: %s", feed["name"], result)
            else:
                all_signals.extend(result)

    executor.shutdown(wait=False)

    # Global dedup across feeds (same article on multiple feeds)
    seen_global: set[str] = set()
    unique_signals: list[dict] = []
    cross_feed_dupes = 0
    for sig in all_signals:
        key = _dedup_key(sig["source_url"], sig["title"])
        if key in seen_global:
            cross_feed_dupes += 1
        else:
            seen_global.add(key)
            unique_signals.append(sig)

    # Sort: high tier first, then by published_date desc (newer first)
    # NOTE: published_date is "YYYY-MM-DD" string — ISO format sorts correctly
    # as a plain string; we negate tier_order and reverse=True for date desc.
    tier_order = {"high": 0, "medium": 1, "low": 2}
    unique_signals.sort(
        key=lambda s: (
            tier_order.get(s.get("signal_tier", "low"), 9),
            s.get("published_date") or "",
        ),
        reverse=False,          # tier ascending (0=high first)
    )
    # Secondary: within same tier, sort by date descending
    from itertools import groupby
    sorted_signals: list[dict] = []
    for _, group in groupby(unique_signals, key=lambda s: tier_order.get(s.get("signal_tier", "low"), 9)):
        sorted_signals.extend(
            sorted(group, key=lambda s: s.get("published_date") or "", reverse=True)
        )
    unique_signals = sorted_signals

    log.info("")
    log.info("═══ COLLECTION SUMMARY ════════════════════════════════════════════")
    log.info("  Total collected  : %d", len(all_signals))
    log.info("  Cross-feed dupes : %d", cross_feed_dupes)
    log.info("  Unique signals   : %d", len(unique_signals))

    # Sector breakdown
    by_sector: dict[str, int] = defaultdict(int)
    by_tier:   dict[str, int] = defaultdict(int)
    by_event:  dict[str, int] = defaultdict(int)
    for s in unique_signals:
        by_sector[s["sector"]] += 1
        by_tier[s["signal_tier"]] += 1
        by_event[s["event_type"]] += 1

    log.info("  By tier          : high=%d  medium=%d  low=%d",
             by_tier.get("high", 0), by_tier.get("medium", 0), by_tier.get("low", 0))
    log.info("  By sector:")
    for sec, cnt in sorted(by_sector.items(), key=lambda x: -x[1]):
        log.info("    %-30s  %d", sec, cnt)
    log.info("  Top event types:")
    for et, cnt in sorted(by_event.items(), key=lambda x: -x[1])[:8]:
        log.info("    %-20s  %d", et, cnt)
    log.info("═══════════════════════════════════════════════════════════════════")

    if not dry_run:
        # Save per-feed signal files (appended to existing)
        _save_signals(unique_signals)
        cache.save()
        health_reg.save()
    else:
        log.info("[DRY-RUN] Not saving — would have written %d signals", len(unique_signals))

    return unique_signals


def _save_signals(signals: list[dict]) -> None:
    """
    Save signals to data/raw_signals/YYYY-MM-DD.json
    AND append to per-company signals if companies_mentioned is populated.
    """
    # Daily dump
    daily_path = SIGNALS_OUT_DIR / f"{TODAY_STR}.json"
    existing: list[dict] = []
    if daily_path.exists():
        try:
            existing = json.loads(daily_path.read_text())
        except Exception:
            existing = []

    # Merge (avoid dupes by id)
    existing_ids = {s["id"] for s in existing}
    new_only = [s for s in signals if s["id"] not in existing_ids]
    merged = existing + new_only
    daily_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    log.info("[SAVE] Daily file → %s  (total=%d  new=%d)", daily_path, len(merged), len(new_only))

    # Also write a rolling 'latest.json' (last 500 signals)
    latest_path = SIGNALS_OUT_DIR / "latest.json"
    latest: list[dict] = []
    if latest_path.exists():
        try:
            latest = json.loads(latest_path.read_text())
        except Exception:
            latest = []
    latest_ids = {s["id"] for s in latest}
    for s in new_only:
        if s["id"] not in latest_ids:
            latest.append(s)
    latest = latest[-500:]  # keep last 500
    latest_path.write_text(json.dumps(latest, indent=2, ensure_ascii=False))
    log.info("[SAVE] latest.json → %s signals", len(latest))

# ─────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────
def main() -> None:
    args = sys.argv[1:]
    dry_run       = "--dry-run"       in args
    reset_health  = "--reset-health"  in args
    show_help     = "--help"          in args or "-h" in args

    if show_help:
        print(__doc__)
        sys.exit(0)

    if reset_health:
        HealthRegistry(HEALTH_PATH).reset()
        log.info("Feed health registry reset.")
        if "--dry-run" not in args and len(args) == 1:
            sys.exit(0)

    signals = asyncio.run(run_collection(dry_run=dry_run))
    high = sum(1 for s in signals if s["signal_tier"] == "high")
    log.info("Done. %d signals (%d high-tier).", len(signals), high)


if __name__ == "__main__":
    main()

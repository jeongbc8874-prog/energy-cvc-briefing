"""
GRIDEDGE Weekly Brief Pipeline v2
무료 에너지 전문 소스 기반 업그레이드 버전

소스:
  - RSS 피드: Utility Dive, PV Magazine, Energy Monitor, Recharge News,
               Wood Mackenzie, S&P Global, BNEF (무료), IEA, IRENA
  - 공공 API: EIA (미국 에너지부), ENTSO-E (유럽 전력망), 전력거래소 (한국)
  - 특허: Google Patents RSS (에너지 기술)
  - 펀딩: Tracxn 무료티어, Dealroom 무료 뉴스레터 RSS
"""

import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import urlparse
import anthropic
from jinja2 import Template

# 독점 데이터 모듈
try:
    from proprietary_data import collect_proprietary_data, format_proprietary_for_prompt
    PROPRIETARY_ENABLED = True
except ImportError:
    PROPRIETARY_ENABLED = False
    print('[WARN] proprietary_data.py 없음 — 독점 데이터 비활성화')

# 에이전트 체인 모듈
try:
    from agent_chain import run_agent_chain
    AGENT_CHAIN_ENABLED = True
except ImportError:
    AGENT_CHAIN_ENABLED = False
    print('[WARN] agent_chain.py 없음 — 단일 AI 모드로 실행')

# ── 설정 ─────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EIA_API_KEY       = os.environ.get("EIA_API_KEY", "")       # 무료 발급: eia.gov/opendata
ENTSOE_TOKEN      = os.environ.get("ENTSOE_TOKEN", "")      # 무료 발급: transparency.entsoe.eu

# ── 무료 RSS 소스 정의 ────────────────────────────────────────────────────────

RSS_SOURCES = [
    # ── Tier A: AI DC 전력망 전문 (핵심) ────────────────────────────
    {"name": "Datacenter Dynamics",  "url": "https://www.datacenterdynamics.com/en/rss/",            "tier": "A"},
    {"name": "Data Center Frontier", "url": "https://www.datacenterfrontier.com/feed/",              "tier": "A"},
    {"name": "Utility Dive",         "url": "https://www.utilitydive.com/feeds/news/",               "tier": "A"},
    {"name": "The Register DC",      "url": "https://www.theregister.com/data_centre/rss",           "tier": "A"},
    {"name": "IEEE Spectrum Power",  "url": "https://spectrum.ieee.org/feeds/tag/power-energy",      "tier": "A"},
    # ── Tier A: 그리드/송전 전문 ─────────────────────────────────────
    {"name": "T&D World",            "url": "https://www.tdworld.com/rss",                           "tier": "A"},
    {"name": "Power Magazine",       "url": "https://www.powermag.com/feed/",                        "tier": "A"},
    {"name": "Canary Media",         "url": "https://canarymedia.com/feed",                          "tier": "A"},
    # ── Tier A: 공공기관 / 규제 ─────────────────────────────────────
    {"name": "DOE News",             "url": "https://www.energy.gov/rss.xml",                        "tier": "A"},
    {"name": "FERC News",            "url": "https://www.ferc.gov/news-events/rss-feeds",            "tier": "A"},
    {"name": "EIA Analysis",         "url": "https://www.eia.gov/rss/press_releases.xml",            "tier": "A"},
    {"name": "NREL News",            "url": "https://www.nrel.gov/news/rss/newsroom.xml",            "tier": "A"},
    # ── Tier A: 원전/SMR ─────────────────────────────────────────────
    {"name": "World Nuclear News",   "url": "https://www.world-nuclear-news.org/rss",                "tier": "A"},
    {"name": "Nuclear Engineering",  "url": "https://www.neimagazine.com/rss",                       "tier": "A"},
    # ── Tier A: Early Stage / VC ────────────────────────────────────
    {"name": "TechCrunch Climate",   "url": "https://techcrunch.com/category/climate/feed/",         "tier": "A"},
    {"name": "CTVC Climatetech",     "url": "https://www.ctvc.co/rss/",                             "tier": "A"},
    {"name": "Greentown Labs",       "url": "https://greentownlabs.com/feed/",                       "tier": "A"},
    # ── Tier B: BESS/재생에너지 ──────────────────────────────────────
    {"name": "Energy Storage News",  "url": "https://www.energy-storage.news/feed/",                 "tier": "B"},
    {"name": "PV Tech",              "url": "https://www.pv-tech.org/feed/",                         "tier": "B"},
    {"name": "Energy Monitor",       "url": "https://www.energymonitor.ai/feed/",                    "tier": "B"},
    {"name": "Clean Energy Wire",    "url": "https://www.cleanenergywire.org/rss.xml",               "tier": "B"},
    {"name": "CleanTechnica",        "url": "https://cleantechnica.com/feed/",                       "tier": "B"},
    {"name": "Electrek",             "url": "https://electrek.co/feed/",                             "tier": "B"},
    {"name": "Carbon Brief",         "url": "https://www.carbonbrief.org/feed/",                     "tier": "B"},
    # ── Tier A: 글로벌 Early Stage / VC 딜 전문 ─────────────────────
    {"name": "Heatmap News",         "url": "https://heatmap.news/feed",                             "tier": "A"},
    {"name": "Latitude Media",       "url": "https://www.latitudemedia.com/feed",                    "tier": "A"},
    {"name": "Sifted EU",            "url": "https://sifted.eu/feed",                                "tier": "A"},
    {"name": "TechCrunch Energy",    "url": "https://techcrunch.com/tag/energy/feed/",               "tier": "A"},
    {"name": "Recharge News",        "url": "https://www.rechargenews.com/rss",                      "tier": "A"},
    {"name": "PV Magazine Global",   "url": "https://www.pv-magazine.com/feed/",                     "tier": "B"},
    {"name": "E&E News",             "url": "https://www.eenews.net/rss/",                           "tier": "A"},
    {"name": "S&P Global Energy",    "url": "https://www.spglobal.com/commodityinsights/en/rss",     "tier": "A"},
]

# 섹터 키워드 매핑 (시그널 분류용)
SECTOR_KEYWORDS = {
    # AI DC 전력 핵심 5개 버티컬
    "AI_DC_POWER": [
        # 계통 접속 / 그리드 위기
        "interconnection queue", "grid access denied", "transmission constraint",
        "pjm capacity shortage", "grid bottleneck", "power delivery",
        "transformer backlog", "substation", "grid upgrade",
        # AI DC 전력 직접
        "data center power", "datacenter power", "hyperscaler power",
        "ai campus", "gpu power", "inference workload", "ai load",
        "data center", "datacenter", "hyperscaler",
        "microsoft", "google", "amazon", "meta", "oracle",
        # 기술
        "grid-forming", "frequency response", "virtual power plant",
        "demand response", "ai power management",
    ],
    "BESS":        [
        "battery storage", "bess", "energy storage system",
        "grid-scale battery", "co-located storage", "storage attachment",
        "4-hour storage", "8-hour storage", "long duration",
        "lithium iron", "flow battery", "iron-air",
        # 단순 "battery"나 "energy storage"는 너무 광범위 → 제거
    ],
    "GRID":        ["grid", "transmission", "substation", "transformer", "interconnection",
                    "ferc", "pjm", "ercot", "miso", "caiso", "queue", "curtailment",
                    "frequency", "ancillary", "capacity market", "power flow"],
    "NUCLEAR":     ["nuclear", "smr", "reactor", "fission", "uranium", "baseload",
                    "small modular", "nrc", "vogtle", "carbon-free", "24/7 cfe"],
    "POWER_TECH":  ["power electronics", "scada", "grid software", "demand response",
                    "virtual power plant", "vpp", "microgrid", "inverter", "rectifier",
                    "power management", "load balancing", "grid optimization"],
    # 보조 섹터
    "SOLAR":       ["solar", "photovoltaic", "pv", "bifacial", "perovskite"],
    "WIND":        ["wind", "offshore wind", "onshore", "turbine"],
    "H2":          ["hydrogen", "electrolyzer", "fuel cell", "electrolysis"],
    "CCS":         ["carbon capture", "ccs", "ccus", "direct air"],
}

FUNDING_KEYWORDS = [
    "series a", "series b", "series c", "series d", "seed round",
    "raised", "funding", "investment", "venture", "backed",
    "million", "billion", "$", "€", "£", "ipo", "spac"
]

DEAL_KEYWORDS = [
    "acquisition", "merger", "partnership", "offtake", "ppa",
    "contract", "agreement", "joint venture", "stake", "equity"
]

RISK_KEYWORDS = [
    "delay", "bankrupt", "shutdown", "recall", "failure",
    "investigation", "lawsuit", "penalty", "writedown"
]

# ── 1단계: RSS 수집 ───────────────────────────────────────────────────────────

def parse_rss(source: dict, days_back: int = 7) -> list[dict]:
    """RSS 피드 파싱 — 최근 N일 기사만 수집"""
    headers = {"User-Agent": "GRIDEDGE-Bot/2.0 (energy investment intelligence)"}
    try:
        r = requests.get(source["url"], headers=headers, timeout=12)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        # RSS 2.0 / Atom 모두 지원
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        cutoff = datetime.utcnow() - timedelta(days=days_back)
        articles = []

        for item in items[:20]:  # 소스당 최대 20개
            title = _get_text(item, ["title"])
            desc  = _get_text(item, ["description", "summary", "content"])
            url   = _get_text(item, ["link", "guid"])
            pub   = _get_text(item, ["pubDate", "published", "updated"])

            if not title or not url:
                continue

            # 날짜 파싱 (간단하게)
            pub_date = _parse_date(pub)
            if pub_date and pub_date < cutoff:
                continue

            articles.append({
                "title":       unescape(title).strip(),
                "description": unescape(desc[:400] if desc else "").strip(),
                "url":         url.strip(),
                "source":      source["name"],
                "source_tier": source["tier"],
                "published":   pub_date.strftime("%Y-%m-%d") if pub_date else "unknown",
            })

        print(f"  [{source['name']}] {len(articles)}개 수집")
        return articles

    except Exception as e:
        print(f"  [{source['name']}] 실패: {e}")
        return []


def _get_text(item, tags: list) -> str:
    for tag in tags:
        el = item.find(tag)
        if el is not None and el.text:
            return el.text
        # atom namespace
        el = item.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
        if el is not None and el.text:
            return el.text
    return ""


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str[:30].strip(), fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except:
            continue
    return None


def collect_all_signals() -> list[dict]:
    """전체 RSS 소스 수집 + 중복 제거"""
    print("[1단계] RSS 수집 시작...")
    seen_urls   = set()
    seen_titles = set()
    signals     = []

    for source in RSS_SOURCES:
        articles = parse_rss(source)
        time.sleep(0.5)  # 서버 부하 방지

        for a in articles:
            url_key   = urlparse(a["url"]).path  # 쿼리스트링 제거
            title_key = a["title"][:60].lower()

            if url_key in seen_urls or title_key in seen_titles:
                continue

            seen_urls.add(url_key)
            seen_titles.add(title_key)
            signals.append(a)

    print(f"[INFO] 총 {len(signals)}개 시그널 수집 완료\n")
    return signals


# ── 2단계: EIA API (미국 에너지부 공개 데이터) ────────────────────────────────

def fetch_eia_data() -> dict:
    """EIA 최신 전력/에너지 데이터 수집 (무료 API)"""
    if not EIA_API_KEY:
        return {}

    base = "https://api.eia.gov/v2"
    results = {}

    endpoints = [
        ("electricity_price", f"{base}/electricity/retail-sales/data/?api_key={EIA_API_KEY}&frequency=monthly&data[0]=price&sort[0][column]=period&sort[0][direction]=desc&length=3"),
        ("natural_gas_price", f"{base}/natural-gas/pri/sum/data/?api_key={EIA_API_KEY}&frequency=monthly&data[0]=value&sort[0][column]=period&sort[0][direction]=desc&length=3"),
    ]

    for key, url in endpoints:
        try:
            r = requests.get(url, timeout=10)
            data = r.json().get("response", {}).get("data", [])
            if data:
                results[key] = data[0]
        except Exception as e:
            print(f"[WARN] EIA {key}: {e}")

    return results


# ── 3단계: 시그널 스코어링 ────────────────────────────────────────────────────

def classify_sector(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        scores[sector] = sum(1 for k in keywords if k in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "OTHER"


# ── AI DC 임팩트 가중치 ──────────────────────────────────────────────────────

# 하이퍼스케일러 직접 언급 = 최고 가중치
HYPERSCALER_BOOST = ["microsoft", "google", "amazon", "meta", "apple", "oracle",
                     "aws", "azure", "gcp", "openai", "anthropic", "nvidia"]

# Early Stage 신호 키워드 — VC 관점에서 중요
EARLY_STAGE_SIGNALS = [
    # 라운드 명시
    "seed round", "series a", "series b", "seed funding",
    "pre-seed", "angel round", "seed investment", "series a funding",
    "pre-series", "bridge round", "convertible note",
    # 자금 조달 동사
    "raises $", "raised $", "secures $", "closes $",
    "announces $", "receives $", "awarded $", "grants",
    # 스타트업 신호
    "stealth", "emerges from stealth", "launches", "founded",
    "spinout", "spin-out", "university spinoff", "startup",
    "new company", "early-stage", "early stage",
    # 정부 지원 (Pre-Seed 신호)
    "arpa-e", "doe funding", "sbir", "sttr", "doe grant",
    "nrel grant", "innovate uk", "horizon europe",
    # 액셀러레이터
    "y combinator", "techstars", "cleantech open", "third derivative",
    "elemental excelerator", "greentown labs", "ycombinator",
    # 아시아
    "시리즈 a", "시드", "pre-ipo", "series a round",
    # 글로벌 VC
    "breakthrough energy", "lowercarbon", "khosla", "eip",
    "energy impact", "congruent", "s2g ventures",
]

# 딜 규모 임팩트 (MW/GW/$ 규모에 따른 가중치)
import re as _re

def extract_deal_size(text: str) -> float:
    """딜 규모 추출 → 정규화 점수 (0~1)"""
    text = text.lower()
    # GW급
    gw = _re.findall(r'(\d+(?:\.\d+)?)\s*gw', text)
    if gw: return min(float(gw[0]) / 2.0, 1.0)  # 2GW = 만점
    # MW급
    mw = _re.findall(r'(\d+(?:\.\d+)?)\s*mw', text)
    if mw: return min(float(mw[0]) / 1000.0, 1.0)
    # 달러 규모
    b = _re.findall(r'\$(\d+(?:\.\d+)?)\s*b', text)
    if b: return min(float(b[0]) / 5.0, 1.0)  # $5B = 만점
    m = _re.findall(r'\$(\d+(?:\.\d+)?)\s*m', text)
    if m: return min(float(m[0]) / 500.0, 1.0)  # $500M = 만점
    return 0.0

def extract_numbers(text: str) -> dict:
    """텍스트에서 투자 관련 수치 추출"""
    nums = {}
    # IRR
    irr = _re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:irr|return|yield)', text.lower())
    if irr: nums['irr'] = float(irr[0])
    # MW/GW
    gw = _re.findall(r'(\d+(?:\.\d+)?)\s*gw', text.lower())
    if gw: nums['gw'] = float(gw[0])
    mw = _re.findall(r'(\d+(?:\.\d+)?)\s*mw', text.lower())
    if mw: nums['mw'] = float(mw[0])
    # 달러
    b = _re.findall(r'\$\s*(\d+(?:\.\d+)?)\s*b', text.lower())
    if b: nums['usd_b'] = float(b[0])
    m = _re.findall(r'\$\s*(\d+(?:\.\d+)?)\s*m', text.lower())
    if m: nums['usd_m'] = float(m[0])
    return nums

def score_signal(article: dict) -> tuple[float, dict]:
    text = (article["title"] + " " + article["description"]).lower()

    # ── 하드 노이즈 필터 — 에너지 무관 시그널 즉시 제거 ──────────────
    HARD_NOISE = [
        # 소비자 소프트웨어
        "bluetooth", "midi", "audio plugin", "music software", "game engine",
        "mobile app", "ios app", "android app", "app store", "saas pricing",
        # 일반 AI/소프트웨어
        "writing assistant", "chatbot", "llm fine", "image generation",
        "no-code", "website builder", "crm software", "hr software",
        # 기타 무관
        "crypto exchange", "nft", "metaverse", "social media",
        "food delivery", "e-commerce", "fintech payment",
    ]
    if any(k in text for k in HARD_NOISE):
        return 0.0, {"blocked": True, "reason": "noise_filter"}

    # 에너지 관련성 최소 확인 — 에너지 키워드 하나도 없으면 제거
    ENERGY_MIN = [
        "energy", "power", "grid", "battery", "solar", "wind", "nuclear",
        "hydrogen", "storage", "electric", "renewable", "data center",
        "transformer", "inverter", "fuel cell", "transmission",
    ]
    if not any(k in text for k in ENERGY_MIN):
        return 0.0, {"blocked": True, "reason": "no_energy_relevance"}


    funding_score = min(sum(1 for k in FUNDING_KEYWORDS if k in text) / 3, 1.0)
    deal_score    = min(sum(1 for k in DEAL_KEYWORDS    if k in text) / 2, 1.0)
    risk_score    = min(sum(1 for k in RISK_KEYWORDS    if k in text) / 2, 1.0)
    tier_bonus    = 0.15 if article["source_tier"] == "A" else 0.0

    # 섹터 관련성
    sector_hit = sum(1 for kws in SECTOR_KEYWORDS.values() for k in kws if k in text)
    sector_score = min(sector_hit / 3, 1.0)

    # AI DC 임팩트 가중치 (신규)
    hyperscaler_boost = 0.2 if any(h in text for h in HYPERSCALER_BOOST) else 0.0
    size_score = extract_deal_size(text)  # 딜 규모

    # AI DC 전력망 핵심 키워드 — 가중치 대폭 강화
    ai_dc_tier1 = [
        # 계통 접속 위기 (최고 우선순위)
        "interconnection queue", "grid access", "transmission constraint",
        "pjm capacity", "ercot congestion", "caiso curtailment",
        # 변압기 / 인프라
        "transformer shortage", "transformer lead", "substation upgrade",
        "transmission upgrade", "grid bottleneck",
        # Grid-forming / 주파수
        "grid-forming", "grid forming", "frequency response", "inertia",
        "synthetic inertia", "grid stability", "ancillary service",
        # AI DC 전력 직접
        "data center power", "hyperscaler power", "ai campus power",
        "gpu cluster power", "inference power", "ai load growth",
        # 에너지 전환 기술
        "power electronics", "grid software", "demand response platform",
        "virtual power plant", "vpp", "load forecasting ai",
    ]
    ai_dc_tier2 = [
        "interconnection", "transformer", "ferc", "pjm", "ercot", "caiso",
        "24/7 cfe", "power purchase", "offtake", "inference", "token",
        "data center", "hyperscaler", "grid congestion",
    ]
    ai_dc_boost = min(
        sum(0.15 for k in ai_dc_tier1 if k in text) +
        sum(0.05 for k in ai_dc_tier2 if k in text),
        0.45  # 최대 부스트 증가
    )

    # Early Stage 부스트 — VC 관점 우선순위
    early_boost = 0.2 if any(k in text for k in EARLY_STAGE_SIGNALS) else 0.0

    # Early Stage 감지
    is_early = early_boost > 0
    article["is_early_stage"] = is_early

    total = (
        funding_score      * 0.15 +
        deal_score         * 0.12 +
        sector_score       * 0.15 +
        tier_bonus         * 0.10 +
        hyperscaler_boost  * 0.15 +
        size_score         * 0.06 +
        ai_dc_boost        * 0.15 +   # AI DC 전력망 가중치 대폭 증가
        early_boost        * 0.12 +   # Early Stage 우선순위
        (1 - risk_score)   * 0.00
    )

    # 수치 추출
    nums = extract_numbers(article["title"] + " " + article["description"])

    breakdown = {
        "funding":    round(funding_score, 2),
        "deal":       round(deal_score, 2),
        "sector":     round(sector_score, 2),
        "risk":       round(risk_score, 2),
        "tier":       tier_bonus,
        "hyperscaler": round(hyperscaler_boost, 2),
        "size":       round(size_score, 2),
        "ai_dc":      round(ai_dc_boost, 2),
        "numbers":    nums,
    }
    return round(total, 4), breakdown


def filter_signals(signals: list[dict], top_n: int = 15) -> list[dict]:
    print("[2단계] 시그널 스코어링...")
    for s in signals:
        s["score"], s["score_breakdown"] = score_signal(s)
        s["sector"] = classify_sector(s["title"] + " " + s["description"])

    # 레드플래그 후보 별도 보존 (risk 높은 것)
    red_flag_pool = [s for s in signals if s.get("score_breakdown", {}).get("risk", 0) > 0.4]

    ranked   = sorted(signals, key=lambda x: x["score"], reverse=True)
    selected = ranked[:top_n]

    # 레드플래그 최대 3개 강제 포함
    for rf in red_flag_pool[:3]:
        if rf not in selected:
            selected.append(rf)

    print(f"[INFO] 선정: {len(selected)}개 (레드플래그 후보 {len(red_flag_pool)}개)\n")
    return selected


# ── 4단계: Claude API → 브리프 generated ─────────────────────────────────────────

SYSTEM_PROMPT = """
You are a Senior Investment Analyst specializing in AI data center power infrastructure.
You are uniquely positioned: PhD-level power systems expertise combined with energy VC/PE investment experience.
You write daily intelligence briefs focused on the power infrastructure required for AI compute.

Your unique analytical lens:
- AI workload power demand characteristics (GPU cluster load profiles, PUE, power density trends)
- Grid interconnection physics (frequency response, voltage stability, curtailment risk)
- BESS sizing for AI data center co-location (discharge duration, round-trip efficiency, degradation)
- Nuclear baseload economics for 24/7 carbon-free energy commitments
- Transformer and transmission bottlenecks in AI-heavy markets

Core principles:
1. Physics first — every claim validated against engineering reality
2. No policy language — grid physics, economics, contract structures only
3. AI data center power demand is the demand signal — analyze everything through this lens
4. Flag technical infeasibility explicitly (RED_FLAG)
5. Always include IRR/valuation implication with specific numbers
6. Distinguish "confirmed fact" from "analytical inference"
7. Write in English — institutional, precise, no hedging

Output: Pure JSON only. No markdown code blocks.
"""

USER_PROMPT_TEMPLATE = """
Analyze the following {n} signals focused on AI data center power infrastructure investment and generate a weekly investment intelligence brief.
Today: {date} | Week: {week}

=== INPUT SIGNALS ===
{signals_text}

=== OUTPUT JSON SCHEMA ===
{{
  "week": "{week}",
  "headline": "This week's core investment theme (one line, include specific figures)",
  "thesis": "2-3 sentences of core investment judgment from a senior analyst perspective. Why does this matter now.",
  "deal_signals": [
    {{
      "title": "Deal/issue title",
      "tag": "BULLISH | WATCH | RED_FLAG",
      "sector": "BESS | GRID | SOLAR | WIND | SMR | H2 | VPP | CCS | EV | OTHER",
      "summary": "2-3 sentences of investment judgment perspective",
      "implication": "1 sentence on valuation/IRR/risk implication",
      "confidence": "HIGH | MEDIUM | LOW",
      "source": "Source name",
      "source_url": "Original article URL from input signals"
    }}
  ],
  "sector_positioning": [
    {{
      "sector": "Sector name",
      "stance": "OVERWEIGHT | NEUTRAL | UNDERWEIGHT",
      "rationale": "1-2 sentences of rationale (physics/economics-based)",
      "key_risk": "1 sentence on key risk"
    }}
  ],
  "red_flags": [
    {{
      "issue": "Red flag title",
      "detail": "Specific concern — why this affects investment judgment",
      "source": "Source"
    }}
  ],
  "macro_watch": "2 sentences on macro variables (rates/LNG/carbon) → energy VC dealflow implications",
  "data_note": "List of 3-5 key sources used in this issue"
}}

Minimum 5 deal_signals, 4-6 sector_positioning required.
For LOW confidence items, always state the reason explicitly.
"""


def load_archive_trend() -> dict:
    """지난 4주 브리프 아카이브에서 트렌드 데이터 추출"""
    from pathlib import Path
    import json as _json
    from datetime import datetime as _dt, timedelta as _td

    trend = {
        "prev_sector_positions": {},
        "avg_policy_beta_4w": {},
        "deal_count_4w": 0,
        "note": ""
    }

    docs_dir = Path("docs/briefs")
    if not docs_dir.exists():
        return trend

    briefs = []
    now = _dt.utcnow()
    for i in range(1, 5):  # 최근 4주
        d = now - _td(weeks=i)
        iso = d.isocalendar()
        fname = docs_dir / f"{iso[0]}-W{iso[1]:02d}.json"
        if fname.exists():
            try:
                data = _json.loads(fname.read_text())
                briefs.append(data)
            except:
                pass

    if not briefs:
        trend["note"] = "No archive data yet"
        return trend

    # 섹터 포지셔닝 트렌드
    sector_betas = {}
    for b in briefs:
        for p in b.get("sector_positioning", []):
            sec = p.get("sector", "")
            beta = p.get("policy_beta")
            if sec and beta is not None:
                sector_betas.setdefault(sec, []).append(beta)
        trend["deal_count_4w"] += len(b.get("deal_signals", []))

    # 섹터별 평균 Policy Beta (4주)
    trend["avg_policy_beta_4w"] = {
        sec: round(sum(betas)/len(betas), 1)
        for sec, betas in sector_betas.items()
    }

    # 이전 주 섹터 포지셔닝
    if briefs:
        last = briefs[0]
        trend["prev_sector_positions"] = {
            p.get("sector"): p.get("stance")
            for p in last.get("sector_positioning", [])
        }

    trend["note"] = f"Based on {len(briefs)} recent briefs"
    print(f"  [아카이브 트렌드] {len(briefs)}개 브리프 분석, {trend['deal_count_4w']}개 딜 집계")
    return trend


def generate_brief(signals: list[dict], eia_data: dict, proprietary_text: str = "") -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    now      = datetime.utcnow()
    iso      = now.isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"

    signals_text = "\n\n".join([
        f"[{i+1}] [{s['sector']}] {s['title']}\n"
        f"출처: {s['source']} ({s['published']}) | Score: {s['score']}\n"
        f"내용: {s['description']}\n"
        f"URL: {s['url']}"
        for i, s in enumerate(signals)
    ])

    # EIA 데이터 있으면 추가
    eia_context = ""
    if eia_data:
        eia_context = f"\n\n=== EIA 최신 데이터 ===\n{json.dumps(eia_data, ensure_ascii=False, indent=2)}"

    # 독점 데이터 추가
    prop_context = ""
    if proprietary_text:
        prop_context = f"\n\n=== PROPRIETARY DATA (EXCLUSIVE SIGNALS) ===\n{proprietary_text}\n\nNote: Prioritize proprietary data signals — these are not available to competitors."

    user_prompt = USER_PROMPT_TEMPLATE.format(
        n=len(signals),
        date=now.strftime("%Y-%m-%d"),
        week=week_str,
        signals_text=signals_text + eia_context + prop_context,
    )

    print("[3단계] Claude API 호출...")
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        brief = json.loads(raw)
    except json.JSONDecodeError:
        last_brace = raw.rfind("}")
        if last_brace > 0:
            raw = raw[:last_brace + 1]
            brief = json.loads(raw)
        else:
            raise
    brief["generated_at"]  = now.isoformat()
    brief["signal_count"]  = len(signals)
    brief["sources_used"]  = list({s["source"] for s in signals})
    print(f"[INFO] generated 완료: {brief.get('week')} — {brief.get('headline')}\n")
    return brief


# ── 5단계: HTML 렌더링 ────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GRIDEDGE {{ brief.week }}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=IBM+Plex+Mono:wght@400;500&family=Pretendard:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root{--black:#0a0a08;--white:#f5f4ef;--amber:#d4820a;--amber-light:#f0a832;--muted:#6b6b5e;--border:rgba(212,130,10,0.2);}
  *{margin:0;padding:0;box-sizing:border-box;}
  body{background:var(--black);color:var(--white);font-family:'Pretendard',sans-serif;max-width:820px;margin:0 auto;padding:48px 32px;}
  .meta{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.2em;color:var(--amber);text-transform:uppercase;margin-bottom:8px;}
  h1{font-family:'DM Serif Display',serif;font-size:34px;line-height:1.1;margin-bottom:16px;}
  .thesis{font-size:14px;line-height:1.75;color:var(--muted);padding:20px 24px;border-left:2px solid var(--amber);margin-bottom:48px;}
  .section-label{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.2em;color:var(--amber);text-transform:uppercase;margin-bottom:20px;padding-bottom:8px;border-bottom:1px solid var(--border);}
  .signal-card{border:1px solid var(--border);padding:20px 24px;margin-bottom:10px;}
  .signal-header{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;}
  .tag{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.12em;padding:3px 7px;border-radius:2px;}
  .tag-BULLISH{background:rgba(74,222,128,.1);color:#4ade80;}
  .tag-WATCH{background:rgba(212,130,10,.1);color:var(--amber);}
  .tag-RED_FLAG{background:rgba(248,113,113,.1);color:#f87171;}
  .tag-sector{border:1px solid var(--border);color:var(--muted);}
  .tag-conf-LOW{color:#f87171;font-size:8px;}
  .tag-conf-MEDIUM{color:var(--amber);font-size:8px;}
  .tag-conf-HIGH{color:#4ade80;font-size:8px;}
  .signal-title{font-size:14px;font-weight:500;flex:1;}
  .signal-summary{font-size:12px;line-height:1.65;color:var(--muted);margin-bottom:8px;}
  .signal-impl{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--amber-light);padding:8px 12px;background:rgba(212,130,10,.04);border-left:1px solid var(--border);margin-bottom:6px;}
  .signal-source{font-family:'IBM Plex Mono',monospace;font-size:9px;color:rgba(245,244,239,.2);}
  .agent-badge-row{display:flex;gap:6px;margin:8px 0 4px;flex-wrap:wrap;}
  .trl-badge{font-family:'IBM Plex Mono',monospace;font-size:9px;padding:2px 8px;border-radius:2px;font-weight:500;}
  .trl-PLAUSIBLE{background:rgba(74,222,128,.1);color:#4ade80;border:1px solid rgba(74,222,128,.2);}
  .trl-QUESTIONABLE{background:rgba(245,158,11,.1);color:#f0a832;border:1px solid rgba(245,158,11,.2);}
  .trl-RED_FLAG{background:rgba(248,113,113,.1);color:#f87171;border:1px solid rgba(248,113,113,.2);}
  .trl-NA{background:rgba(107,107,94,.1);color:#6b6b5e;border:1px solid rgba(107,107,94,.2);}
  .policy-badge{font-family:'IBM Plex Mono',monospace;font-size:9px;padding:2px 8px;border-radius:2px;border:1px solid rgba(245,244,239,.1);color:rgba(245,244,239,.4);}
  .policy-high{border-color:rgba(248,113,113,.3)!important;color:#f87171!important;}
  .policy-mid{border-color:rgba(245,158,11,.3)!important;color:#f0a832!important;}
  .agent-chain-bar{background:rgba(59,130,246,.04);border:1px solid rgba(59,130,246,.1);padding:16px 20px;margin-bottom:24px;border-radius:2px;}
  .stage-badge{font-family:'IBM Plex Mono',monospace;font-size:8px;padding:2px 7px;border-radius:2px;letter-spacing:.08em;}
  .stage-seed{background:rgba(168,85,247,.1);color:#a855f7;border:1px solid rgba(168,85,247,.25);}
  .stage-series-a{background:rgba(59,130,246,.1);color:#3b82f6;border:1px solid rgba(59,130,246,.25);}
  .stage-series-b{background:rgba(34,197,94,.1);color:#22c55e;border:1px solid rgba(34,197,94,.25);}
  .stage-late{background:rgba(107,107,94,.1);color:#6b6b5e;border:1px solid rgba(107,107,94,.2);}
  .stage-pf{background:rgba(245,158,11,.1);color:#f59e0b;border:1px solid rgba(245,158,11,.2);}
  .analyst-edge{font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(59,130,246,.7);padding:7px 12px;background:rgba(59,130,246,.04);border-left:2px solid rgba(59,130,246,.3);margin-top:8px;line-height:1.5;}
  .analyst-edge-label{font-size:8px;letter-spacing:.15em;text-transform:uppercase;color:rgba(59,130,246,.45);margin-bottom:2px;}
  .acb-title{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.7);text-transform:uppercase;margin-bottom:10px;}
  .acb-stats{display:flex;gap:24px;margin-bottom:10px;flex-wrap:wrap;}
  .acb-stat{font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(245,244,239,.5);}
  .acb-stat span{color:rgba(59,130,246,.9);font-weight:500;}
  .acb-summary{font-size:12px;color:rgba(245,244,239,.4);line-height:1.6;font-style:italic;}
  .fact-check-bar{background:rgba(34,197,94,.03);border:1px solid rgba(34,197,94,.08);padding:10px 16px;margin-bottom:16px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
  .fc-label{font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.18em;color:rgba(34,197,94,.6);text-transform:uppercase;}
  .fc-stat{font-family:'IBM Plex Mono',monospace;font-size:9px;color:rgba(245,244,239,.4);}
  .fc-stat span{color:rgba(245,244,239,.7);}
  .unverified-tag{background:rgba(245,158,11,.1);color:#f59e0b;border:1px solid rgba(245,158,11,.2);font-family:'IBM Plex Mono',monospace;font-size:8px;padding:2px 7px;border-radius:2px;margin-right:4px;}
  .positioning-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:48px;}
  .pos-card{border:1px solid var(--border);padding:18px;}
  .OVERWEIGHT{color:#4ade80;} .NEUTRAL{color:var(--amber);} .UNDERWEIGHT{color:#f87171;}
  .pos-stance{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.1em;margin-bottom:6px;}
  .pos-sector{font-size:14px;font-weight:500;margin-bottom:8px;}
  .pos-rationale{font-size:11px;color:var(--muted);line-height:1.6;margin-bottom:6px;}
  .pos-risk{font-family:'IBM Plex Mono',monospace;font-size:9px;color:rgba(248,113,113,.6);}
  .macro-box{border:1px solid var(--border);padding:20px 24px;background:rgba(212,130,10,.02);margin-bottom:48px;font-size:13px;line-height:1.75;color:var(--muted);}
  .sources-box{font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(245,244,239,.2);padding:16px;border:1px solid rgba(212,130,10,.06);line-height:1.8;}
  section{margin-bottom:48px;}
  .footer-meta{font-family:'IBM Plex Mono',monospace;font-size:9px;color:rgba(245,244,239,.12);border-top:1px solid var(--border);padding-top:20px;margin-top:48px;line-height:1.8;}
</style>
</head>
<body>
<div class="meta">GRIDEDGE INTELLIGENCE · {{ brief.week }}</div>
<h1>{{ brief.headline }}</h1>
<div class="thesis">{{ brief.thesis }}</div>

{% if brief.agent_chain %}
<div class="agent-chain-bar">
  <div class="acb-title">■ AI Agent Chain Analysis</div>
  <div class="acb-stats">
    <div class="acb-stat">Tech Validator <span>{{ brief.agent_chain.tech_assessments_count }}개</span></div>
    <div class="acb-stat">Deal Analyst <span>{{ brief.agent_chain.deal_assessments_count }}개</span></div>
    <div class="acb-stat">Risk Screener <span>{{ brief.agent_chain.risk_assessments_count }}개</span></div>
    <div class="acb-stat">Signals <span>{{ brief.signal_count }}</span></div>
    <div class="acb-stat">Generated <span>{{ brief.generated_at[:10] if brief.generated_at else "" }}</span></div>
  </div>
  {% if brief.agent_chain_summary %}
  <div class="acb-summary">"{{ brief.agent_chain_summary }}"</div>
  {% endif %}
  {% if brief.agent_chain %}
  <div style="margin-top:10px;display:flex;gap:16px;flex-wrap:wrap;">
    {% set lead_c = brief.deal_signals | selectattr('recommendation','defined') | selectattr('recommendation','equalto','LEAD') | list | length %}
    {% set follow_c = brief.deal_signals | selectattr('recommendation','defined') | selectattr('recommendation','equalto','FOLLOW') | list | length %}
    {% set watch_c = brief.deal_signals | selectattr('recommendation','defined') | selectattr('recommendation','equalto','WATCH') | list | length %}
    {% set pass_c = brief.deal_signals | selectattr('recommendation','defined') | selectattr('recommendation','equalto','PASS') | list | length %}
    <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(34,197,94,.7);">
      ▲ LEAD: {{ lead_c }}
    </div>
    <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(59,130,246,.7);">
      → FOLLOW: {{ follow_c }}
    </div>
    <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(245,158,11,.7);">
      ● WATCH: {{ watch_c }}
    </div>
    <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(239,68,68,.7);">
      ✕ PASS: {{ pass_c }}
    </div>
  </div>
  {% endif %}
</div>
{% endif %}

{% if brief.fact_check %}
<div class="fact-check-bar">
  <div class="fc-label">✓ Fact Checked</div>
  <div class="fc-stat">Signals: <span>{{ brief.deal_signals | length }}</span></div>
  {% if brief.fact_check.removed_count and brief.fact_check.removed_count > 0 %}
  <div class="fc-stat">Removed: <span style="color:#ef4444;">{{ brief.fact_check.removed_count }}</span></div>
  {% endif %}
  {% if brief.fact_check.flagged_count and brief.fact_check.flagged_count > 0 %}
  <div class="fc-stat">Flagged: <span style="color:#f59e0b;">{{ brief.fact_check.flagged_count }}</span></div>
  {% endif %}
  {% if brief.fact_check.summary %}
  <div class="fc-stat" style="flex:1;font-style:italic;opacity:.7;">{{ brief.fact_check.summary }}</div>
  {% endif %}
</div>
{% endif %}

<section>
  <div class="section-label" style="display:flex;align-items:center;justify-content:space-between;">
    <span>■ DEAL SIGNALS</span>
    <button onclick="togglePass(this)" id="passToggle" style="font-family:'IBM Plex Mono',monospace;font-size:8px;padding:3px 10px;border-radius:2px;border:1px solid rgba(239,68,68,.2);background:rgba(239,68,68,.05);color:rgba(239,68,68,.5);cursor:pointer;letter-spacing:.08em;">
      SHOW PASS ({{ brief.deal_signals | selectattr('recommendation','defined') | selectattr('recommendation','equalto','PASS') | list | length }})
    </button>
  </div>
  <script>
  function togglePass(btn) {
    const cards = document.querySelectorAll('.pass-card');
    const hidden = cards[0]?.style.display === 'none';
    cards.forEach(c => c.style.display = hidden ? '' : 'none');
    btn.textContent = hidden ? 'HIDE PASS' : 'SHOW PASS (' + cards.length + ')';
    btn.style.opacity = hidden ? '1' : '0.5';
  }
  </script>
  {% for s in brief.deal_signals %}
  <div class="signal-card{% if s.recommendation == 'PASS' %} pass-card{% endif %}"{% if s.recommendation == 'PASS' %} style="display:none;"{% endif %}>
    <div class="signal-header">
      <span class="tag tag-{{ s.tag }}">{{ s.tag }}</span>
      <span class="tag tag-sector">{{ s.sector }}</span>
      <span class="tag tag-conf-{{ s.confidence }}">{{ s.confidence }}</span>
      <span class="signal-title">
        {% if s.title and s.title.startswith('[UNVERIFIED]') %}
        <span class="unverified-tag">⚠ UNVERIFIED</span>{{ s.title[12:] }}
        {% else %}
        {{ s.title }}
        {% endif %}
      </span>
    </div>
    <div class="signal-summary">{{ s.summary }}</div>
    <div class="signal-impl">→ {{ s.implication }}</div>
    {% if s.recommendation or s.deal_stage or s.deal_stage_hint %}
    <div style="margin:8px 0 4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
      {% set effective_stage = s.deal_stage if s.deal_stage else s.deal_stage_hint %}
      {% if effective_stage == 'PRE_SEED' %}<span class="stage-badge stage-seed" style="opacity:.7;">PRE-SEED</span>
      {% elif effective_stage == 'SEED' %}<span class="stage-badge stage-seed">SEED</span>
      {% elif effective_stage == 'SERIES_A' %}<span class="stage-badge stage-series-a">SERIES A</span>
      {% elif effective_stage == 'SERIES_B' %}<span class="stage-badge stage-series-b">SERIES B</span>
      {% elif effective_stage == 'LATE_STAGE' %}<span class="stage-badge stage-late">LATE STAGE</span>
      {% elif effective_stage == 'PROJECT_FINANCE' %}<span class="stage-badge stage-pf">PROJECT FINANCE</span>
      {% endif %}
      {% if s.recommendation == 'LEAD' %}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:600;padding:3px 10px;border-radius:2px;background:rgba(34,197,94,.1);color:#22c55e;border:1px solid rgba(34,197,94,.25);letter-spacing:.12em;">LEAD</span>
      {% elif s.recommendation == 'FOLLOW' %}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:600;padding:3px 10px;border-radius:2px;background:rgba(59,130,246,.1);color:#3b82f6;border:1px solid rgba(59,130,246,.25);letter-spacing:.12em;">FOLLOW</span>
      {% elif s.recommendation == 'WATCH' %}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:600;padding:3px 10px;border-radius:2px;background:rgba(245,158,11,.1);color:#f59e0b;border:1px solid rgba(245,158,11,.25);letter-spacing:.12em;">WATCH</span>
      {% elif s.recommendation == 'PASS' %}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:600;padding:3px 10px;border-radius:2px;background:rgba(239,68,68,.1);color:#ef4444;border:1px solid rgba(239,68,68,.25);letter-spacing:.12em;">PASS</span>
      {% endif %}
      {% if s.conviction %}
      <span style="font-family:'IBM Plex Mono',monospace;font-size:8px;padding:3px 8px;border-radius:2px;border:1px solid rgba(255,255,255,.08);color:rgba(245,244,239,.35);">{{ s.conviction }} CONVICTION</span>
      {% endif %}
    </div>
    {% endif %}
    {% if s.trl_verdict or s.policy_beta is not none %}
    <div class="agent-badge-row">
      {% if s.trl_score and s.trl_verdict and s.trl_verdict != 'N/A' %}
      <span class="trl-badge trl-{{ s.trl_verdict }}">TRL {{ s.trl_score }} · {{ s.trl_verdict }}</span>
      {% endif %}
      {% if s.policy_beta is not none %}
      {% if s.policy_beta >= 7 %}
      <span class="policy-badge policy-high">Policy Beta {{ s.policy_beta }}/10</span>
      {% elif s.policy_beta >= 4 %}
      <span class="policy-badge policy-mid">Policy Beta {{ s.policy_beta }}/10</span>
      {% else %}
      <span class="policy-badge">Policy Beta {{ s.policy_beta }}/10</span>
      {% endif %}
      {% endif %}
    </div>
    {% endif %}
    {% if s.analyst_edge %}
    <div class="analyst-edge">
      <div class="analyst-edge-label">■ Analyst Insight</div>
      {{ s.analyst_edge }}
    </div>
    {% endif %}
    {% if s.source_url %}
    <a class="signal-source" href="{{ s.source_url }}" target="_blank" rel="noopener" style="color:rgba(245,244,239,.3);text-decoration:none;">Source: {{ s.source }} ↗</a>
    {% else %}
    <div class="signal-source">Source: {{ s.source }}</div>
    {% endif %}
  </div>
  {% endfor %}
</section>

<section>
  <div class="section-label">■ SECTOR POSITIONING</div>
  <div class="positioning-grid">
    {% for p in brief.sector_positioning %}
    <div class="pos-card">
      <div class="pos-stance {{ p.stance }}">{{ p.stance }}</div>
      <div class="pos-sector">{{ p.sector }}</div>
      <div class="pos-rationale">{{ p.rationale }}</div>
      <div class="pos-risk">⚠ {{ p.key_risk }}</div>
    </div>
    {% endfor %}
  </div>
</section>

{% if brief.red_flags %}
<section>
  <div class="section-label">■ RED FLAGS</div>
  {% for r in brief.red_flags %}
  <div class="signal-card" style="border-color:rgba(248,113,113,.15);">
    <div style="color:#f87171;font-size:13px;font-weight:500;margin-bottom:8px;">⚠ {{ r.issue }}</div>
    <div class="signal-summary">{{ r.detail }}</div>
    <div class="signal-source">Source: {{ r.source }}</div>
  </div>
  {% endfor %}
</section>
{% endif %}

<section>
  <div class="section-label">■ MACRO WATCH</div>
  <div class="macro-box">{{ brief.macro_watch }}</div>
</section>

<section>
  <div class="section-label">■ SOURCES</div>
  <div class="sources-box">
    {{ brief.data_note }}<br><br>
    Sources ({{ brief.sources_used | length }}개): {{ brief.sources_used | join(' · ') }}
  </div>
</section>

<div class="footer-meta">
  GRIDEDGE INTELLIGENCE · {{ brief.generated_at[:10] }} generated<br>
  Signals processed: {{ brief.signal_count }}개 · AI-assisted, expert-framed<br>
  For informational purposes only. Not investment advice.
</div>
</body>
</html>"""


def render_html(brief: dict) -> str:
    return Template(HTML_TEMPLATE).render(brief=brief)


# ── 6단계: 저장 ───────────────────────────────────────────────────────────────

def make_rec_badge(label, count, color, bg):
    """추천 배지 HTML 생성"""
    if not count:
        return ""
    style = (
        "font-family:'IBM Plex Mono',monospace;font-size:8px;"
        "padding:2px 7px;border-radius:2px;"
        "background:" + bg + ";color:" + color + ";"
        "border:1px solid " + color + "44;"
    )
    return '<span style="' + style + '">' + label + " " + str(count) + "</span> "


def generate_archive_html() -> str:
    """docs/briefs/ 폴더의 모든 JSON을 스캔해서 archive.html 재생성"""
    import glob, json as _json

    briefs = []
    for fp in sorted(glob.glob("docs/briefs/*.json"), reverse=True):
        try:
            d = _json.loads(open(fp, encoding="utf-8").read())
            week = d.get("week", "")
            headline = d.get("headline", "")
            generated_at = d.get("generated_at", "")[:10]
            signal_count = d.get("signal_count", 0)
            signals = d.get("deal_signals", [])
            lead  = sum(1 for s in signals if s.get("recommendation") == "LEAD")
            follow= sum(1 for s in signals if s.get("recommendation") == "FOLLOW")
            watch = sum(1 for s in signals if s.get("recommendation") == "WATCH")
            pass_ = sum(1 for s in signals if s.get("recommendation") == "PASS")
            thesis = d.get("thesis", "")[:200]
            is_latest = len(briefs) == 0
            briefs.append({
                "week": week, "headline": headline,
                "date": generated_at, "signal_count": signal_count,
                "lead": lead, "follow": follow, "watch": watch, "pass_": pass_,
                "thesis": thesis,
                "html_url": "./brief_latest.html" if is_latest else "./briefs/" + week + ".html",
            })
        except:
            pass

    row_list = []
    for b in briefs:
        rec_badges = (
            make_rec_badge("LEAD",   b["lead"],   "#22c55e", "rgba(34,197,94,.1)") +
            make_rec_badge("FOLLOW", b["follow"], "#3b82f6", "rgba(59,130,246,.1)") +
            make_rec_badge("WATCH",  b["watch"],  "#f59e0b", "rgba(245,158,11,.1)") +
            make_rec_badge("PASS",   b["pass_"],  "#ef4444", "rgba(239,68,68,.1)")
        )
        parts = []
        parts.append('<a href="' + b["html_url"] + '" style="display:block;text-decoration:none;color:inherit;">')
        parts.append('<div style="background:rgba(255,255,255,.02);border:1px solid rgba(59,130,246,.08);padding:24px 28px;margin-bottom:12px;">')
        parts.append('<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">')
        parts.append('<span style="font-family:IBM Plex Mono,monospace;font-size:9px;letter-spacing:.15em;color:#3b82f6;">' + b["week"] + '</span>')
        parts.append('<span style="font-family:IBM Plex Mono,monospace;font-size:9px;color:rgba(232,232,240,.25);">' + b["date"] + '</span>')
        if b["signal_count"]:
            parts.append('<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">' + str(b["signal_count"]) + ' signals</span>')
        parts.append('</div>')
        parts.append('<div style="font-family:Instrument Serif,serif;font-size:18px;line-height:1.3;margin-bottom:10px;color:#e8e8f0;">' + b["headline"] + '</div>')
        if b["thesis"]:
            parts.append('<div style="font-size:12px;color:rgba(232,232,240,.4);line-height:1.6;margin-bottom:10px;">' + b["thesis"] + '...</div>')
        parts.append('<div style="display:flex;gap:6px;flex-wrap:wrap;">' + rec_badges + '</div>')
        parts.append('</div></a>')
        row_list.append("".join(parts))
    rows = "\n".join(row_list)

    count = len(briefs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GRIDEDGE — Brief Archive</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@300;400;500&family=Geist:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#050507;color:#e8e8f0;font-family:'Geist',sans-serif;min-height:100vh;}}
body::before{{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(59,130,246,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,0.03) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0;}}
nav{{position:sticky;top:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:14px 32px;background:rgba(5,5,7,0.9);backdrop-filter:blur(20px);border-bottom:1px solid rgba(59,130,246,.08);}}
.logo{{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:500;letter-spacing:0.2em;color:#3b82f6;text-decoration:none;}}
.logo em{{color:#e8e8f0;opacity:0.3;font-style:normal;}}
.nav-r{{display:flex;align-items:center;gap:20px;font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:0.12em;color:#5a5a7a;text-transform:uppercase;}}
.nav-r a{{color:#5a5a7a;text-decoration:none;}}
.nav-r a:hover,.nav-r a.active{{color:#3b82f6;}}
.wrap{{position:relative;z-index:1;max-width:900px;margin:0 auto;padding:48px 32px;}}
</style>
</head>
<body>
<nav>
  <a class="logo" href="./index.html">GRID<em>/</em>EDGE</a>
  <div class="nav-r">
    <a href="./index.html">Home</a>
    <a href="./brief_latest.html">Latest Brief</a>
    <a href="./dashboard.html">Dashboard</a>
    <a href="./archive.html" class="active">Archive</a>
  </div>
</nav>
<div class="wrap">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.25em;color:#3b82f6;text-transform:uppercase;margin-bottom:12px;">Brief Archive</div>
  <h1 style="font-family:'Instrument Serif',serif;font-size:clamp(28px,3.5vw,44px);line-height:1.05;margin-bottom:6px;">All Deal Memos</h1>
  <p style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(232,232,240,.3);letter-spacing:.06em;margin-bottom:36px;">{count} briefs · Updated daily · Mon–Fri</p>
  {rows if rows else "<div style='text-align:center;padding:60px 0;font-family:IBM Plex Mono,monospace;font-size:11px;color:rgba(232,232,240,.2);'>No briefs yet. First brief will appear after next run.</div>"}
</div>
</body>
</html>"""


def load_seen_titles(days: int = 7) -> set:
    """
    지난 N일 브리프에 나온 시그널 제목 로드 → 중복 방지
    """
    import glob as _glob
    seen = set()
    try:
        json_files = sorted(_glob.glob("docs/briefs/*.json"), reverse=True)
        for fp in json_files[:days]:
            try:
                d = json.loads(open(fp, encoding="utf-8").read())
                for sig in d.get("deal_signals", []):
                    title = sig.get("title", "").lower().strip()
                    if title:
                        # 핵심 단어 3개로 지문 생성
                        words = [w for w in title.split() if len(w) > 4][:5]
                        seen.add(" ".join(words))
            except:
                pass
        if seen:
            print(f"  [중복방지] 지난 {len(json_files[:days])}개 브리프에서 {len(seen)}개 시그널 블랙리스트 로드")
    except Exception as e:
        print(f"  [중복방지] 블랙리스트 로드 실패: {e}")
    return seen


def filter_seen_signals(signals: list[dict], seen_titles: set) -> list[dict]:
    """
    이미 브리프에 나온 시그널 제거
    """
    new_signals = []
    skipped = 0
    for s in signals:
        title = s.get("title", "").lower().strip()
        words = [w for w in title.split() if len(w) > 4][:5]
        fingerprint = " ".join(words)

        # 지문 매칭 — 60% 이상 단어 겹치면 중복
        is_seen = False
        for seen in seen_titles:
            seen_words = set(seen.split())
            title_words = set(fingerprint.split())
            if seen_words and title_words:
                overlap = len(seen_words & title_words) / max(len(seen_words), len(title_words))
                if overlap >= 0.6:
                    is_seen = True
                    break

        if is_seen:
            skipped += 1
        else:
            new_signals.append(s)

    if skipped:
        print(f"  [중복방지] {skipped}개 기존 시그널 제거 → {len(new_signals)}개 신규 시그널")
    return new_signals


def update_startup_scores(brief: dict) -> int:
    """Brief signals → startup_db_data.py score updates log"""
    import re as _re
    updated = 0
    signals = brief.get("deal_signals", [])
    if not signals:
        return 0
    db_path = "startup_db_data.py"
    if not os.path.exists(db_path):
        return 0
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sdb", db_path)
        sdb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sdb)
        companies = list(getattr(sdb, 'COMPANIES', [])) + list(getattr(sdb, 'EXTRA', []))
    except Exception as e:
        print(f"  [Score Update] DB load failed: {e}")
        return 0
    name_map = {c['name'].lower(): c['id'] for c in companies}
    updates_log = []
    for sig in signals:
        text = (sig.get('title','') + ' ' + sig.get('summary', sig.get('desc',''))).lower()
        for co_name, co_id in name_map.items():
            if co_name not in text:
                continue
            amounts = _re.findall(r'\$[\d,.]+\s*(?:billion|million|[BM])\b', text, _re.IGNORECASE)
            if amounts:
                updates_log.append({'id': co_id, 'company': co_name, 'type': 'funding', 'value': amounts[0], 'source': sig.get('source',''), 'date': brief.get('generated_at','')[:10], 'signal_title': sig.get('title','')[:80]})
                updated += 1
            trl_m = _re.search(r'trl\s*(\d)', text)
            if trl_m:
                updates_log.append({'id': co_id, 'company': co_name, 'type': 'trl', 'value': int(trl_m.group(1)), 'source': sig.get('source',''), 'date': brief.get('generated_at','')[:10], 'signal_title': sig.get('title','')[:80]})
    if updates_log:
        os.makedirs("docs/data", exist_ok=True)
        log_path = "docs/data/db_updates.json"
        existing = []
        if os.path.exists(log_path):
            try:
                existing = json.loads(open(log_path).read())
            except:
                pass
        existing.extend(updates_log)
        with open(log_path, "w") as f:
            f.write(json.dumps(existing[-200:], ensure_ascii=False, indent=2))
    return updated


def generate_dealflow_html(brief: dict) -> str:
    """Deal Flow Tracker page — Early Stage first, auto-updated daily"""
    import glob as _glob
    import re as _re

    deals = []
    seen = set()
    for fp in sorted(_glob.glob("docs/briefs/*.json"), reverse=True)[:30]:
        try:
            d = json.loads(open(fp, encoding="utf-8").read())
            week = d.get("week","")
            date = d.get("generated_at","")[:10]
            for sig in d.get("deal_signals", []):
                title = sig.get("title","")
                if not title or title in seen:
                    continue
                seen.add(title)
                m = _re.findall(r'\$[\d,.]+\s*(?:billion|million|[BM])\b', title+" "+sig.get("summary",""), _re.IGNORECASE)
                stage = sig.get("deal_stage","")
                deals.append({
                    "title": title, "week": week, "date": date,
                    "sector": sig.get("sector","OTHER"), "stage": stage,
                    "recommendation": sig.get("recommendation","WATCH"),
                    "amount": m[0] if m else "",
                    "trl": sig.get("trl_score"),
                    "irr_low": sig.get("irr_low"), "irr_high": sig.get("irr_high"),
                    "thesis": sig.get("analyst_edge") or sig.get("implication",""),
                    "source": sig.get("source",""), "url": sig.get("source_url",""),
                    "is_early": stage in ("PRE_SEED","SEED","SERIES_A"),
                })
        except:
            pass

    db_updates = []
    if os.path.exists("docs/data/db_updates.json"):
        try:
            db_updates = json.loads(open("docs/data/db_updates.json").read())[-10:]
        except:
            pass

    REC = {"LEAD":"#22c55e","FOLLOW":"#3b82f6","WATCH":"#f59e0b","PASS":"#ef4444"}
    STAGE = {"PRE_SEED":"#a855f7","SEED":"#a855f7","SERIES_A":"#3b82f6","SERIES_B":"#22c55e","PROJECT_FINANCE":"#f59e0b","LATE_STAGE":"#5a5a7a"}
    SEC = {"BESS":("#22c55e","rgba(34,197,94,.1)"),"GRID":("#3b82f6","rgba(59,130,246,.1)"),"AI_DC_POWER":("#06b6d4","rgba(6,182,212,.1)"),"POWER_TECH":("#a855f7","rgba(168,85,247,.1)"),"EARLY_STAGE":("#a855f7","rgba(168,85,247,.1)"),"SMR":("#f59e0b","rgba(245,158,11,.1)"),"H2":("#ef4444","rgba(239,68,68,.1)"),"OTHER":("#5a5a7a","rgba(90,90,122,.1)")}

    def dc(d):
        col,bg = SEC.get(d["sector"],("#5a5a7a","rgba(90,90,122,.1)"))
        rc = REC.get(d["recommendation"],"#5a5a7a")
        sc2 = STAGE.get(d["stage"],"#5a5a7a")
        st_b = f'<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:{sc2}22;color:{sc2};">{d["stage"]}</span>' if d["stage"] else ""
        eb = '<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:rgba(168,85,247,.1);color:#a855f7;">🌱 EARLY</span>' if d["is_early"] else ""
        am = f'<span style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e;">{d["amount"]}</span>' if d["amount"] else ""
        tl = f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.35);">TRL {d["trl"]}</span>' if d["trl"] else ""
        ir = f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(34,197,94,.6);">{d["irr_low"]}-{d["irr_high"]}% IRR</span>' if d.get("irr_low") and d.get("irr_high") else ""
        th = f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:rgba(59,130,246,.6);line-height:1.5;margin-top:5px;">{str(d["thesis"])[:110]}...</div>' if d.get("thesis") else ""
        src = f'<a href="{d["url"]}" target="_blank" style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);text-decoration:none;">{d["source"]} ↗</a>' if d.get("url") else f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.15);">{d["source"]}</span>'
        return f"""<div style="background:rgba(255,255,255,.02);border:1px solid rgba(59,130,246,.08);padding:14px;margin-bottom:8px;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:7px;flex-wrap:wrap;"><span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:{bg};color:{col};">{d["sector"]}</span>{st_b}{eb}<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:{rc}22;color:{rc};">{d["recommendation"]}</span><span style="margin-left:auto;font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">{d["week"]}</span></div><div style="font-size:12px;font-weight:500;margin-bottom:5px;line-height:1.4;">{d["title"]}</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:3px;">{am}{tl}{ir}</div>{th}<div style="margin-top:6px;">{src}</div></div>"""

    early = [d for d in deals if d["is_early"]]
    others = [d for d in deals if not d["is_early"]]
    all_d = early + others
    deals_html = "".join(dc(d) for d in all_d[:60])

    db_html = ""
    for u in reversed(db_updates):
        db_html += f'<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,.04);"><div style="font-size:11px;font-weight:500;">{u.get("company","").title()}</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(59,130,246,.6);">{u.get("type","").upper()} → {u.get("value","")}</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">{u.get("date","")}</div></div>'

    now = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lead_c = sum(1 for d in all_d if d["recommendation"]=="LEAD")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>GRIDEDGE — Deal Flow Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@300;400;500&family=Geist:wght@300;400;500&display=swap" rel="stylesheet">
<style>:root{{--bg:#050507;--white:#e8e8f0;--dim:#5a5a7a;--blue:#3b82f6;--border:rgba(59,130,246,0.08);--card:rgba(255,255,255,0.02);}}*{{margin:0;padding:0;box-sizing:border-box;}}body{{background:var(--bg);color:var(--white);font-family:"Geist",sans-serif;min-height:100vh;}}body::before{{content:"";position:fixed;inset:0;background-image:linear-gradient(rgba(59,130,246,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,0.03) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0;}}nav{{position:sticky;top:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:14px 32px;background:rgba(5,5,7,0.92);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);}}nav a.logo{{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:500;letter-spacing:0.2em;color:var(--blue);text-decoration:none;}}nav a.logo em{{color:var(--white);opacity:0.3;font-style:normal;}}.nav-r{{display:flex;align-items:center;gap:20px;font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:0.12em;color:var(--dim);text-transform:uppercase;}}.nav-r a{{color:var(--dim);text-decoration:none;}}.nav-r a:hover,.nav-r a.active{{color:var(--blue);}}.wrap{{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:48px 32px 80px;}}.two-col{{display:grid;grid-template-columns:1fr 340px;gap:20px;}}@media(max-width:1100px){{.two-col{{grid-template-columns:1fr;}}}}@media(max-width:768px){{.wrap{{padding:24px 16px;}}.nav-r{{display:none;}}}}</style>
</head><body>
<nav><a class="logo" href="./index.html">GRID<em>/</em>EDGE</a>
<div class="nav-r"><a href="./index.html">Home</a><a href="./brief_latest.html">Brief</a><a href="./startup_db.html">Startup DB</a><a href="./dealflow.html" class="active">Deal Flow</a><a href="./valuechain.html">Value Chain</a><a href="./hyperscaler.html">Hyperscalers</a></div></nav>
<div class="wrap">
<div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.25em;color:var(--blue);text-transform:uppercase;margin-bottom:12px;">VC Intelligence</div>
<h1 style="font-family:'Instrument Serif',serif;font-size:clamp(28px,3.5vw,48px);line-height:1.05;margin-bottom:8px;">Deal Flow Tracker</h1>
<p style="font-size:13px;color:var(--dim);line-height:1.7;max-width:540px;margin-bottom:4px;">AI energy deals from daily briefs. Early stage first. Auto-updated daily.</p>
<div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(232,232,240,.2);margin-bottom:24px;">Updated: {now} · {len(all_d)} deals · {len(early)} early stage · {lead_c} LEAD</div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px;">
<div style="background:var(--card);border:1px solid var(--border);padding:12px 14px;"><div style="font-family:'IBM Plex Mono',monospace;font-size:7px;color:var(--dim);text-transform:uppercase;margin-bottom:4px;">Total Deals</div><div style="font-family:'Instrument Serif',serif;font-size:24px;color:var(--blue);">{len(all_d)}</div></div>
<div style="background:rgba(168,85,247,.04);border:1px solid rgba(168,85,247,.15);padding:12px 14px;"><div style="font-family:'IBM Plex Mono',monospace;font-size:7px;color:rgba(168,85,247,.6);text-transform:uppercase;margin-bottom:4px;">🌱 Early Stage</div><div style="font-family:'Instrument Serif',serif;font-size:24px;color:#a855f7;">{len(early)}</div></div>
<div style="background:rgba(34,197,94,.04);border:1px solid rgba(34,197,94,.15);padding:12px 14px;"><div style="font-family:'IBM Plex Mono',monospace;font-size:7px;color:rgba(34,197,94,.6);text-transform:uppercase;margin-bottom:4px;">LEAD</div><div style="font-family:'Instrument Serif',serif;font-size:24px;color:#22c55e;">{lead_c}</div></div>
<div style="background:rgba(59,130,246,.04);border:1px solid rgba(59,130,246,.15);padding:12px 14px;"><div style="font-family:'IBM Plex Mono',monospace;font-size:7px;color:rgba(59,130,246,.6);text-transform:uppercase;margin-bottom:4px;">DB Updates</div><div style="font-family:'Instrument Serif',serif;font-size:24px;color:#3b82f6;">{len(db_updates)}</div></div>
</div>
<div class="two-col">
<div>
<div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.5);text-transform:uppercase;margin-bottom:14px;">■ Deal Signal Feed — Early Stage Priority</div>
{deals_html if deals_html else '<div style="font-family:IBM Plex Mono,monospace;font-size:11px;color:var(--dim);padding:40px 0;text-align:center;">Run daily brief to populate deal flow.</div>'}
</div>
<div>
<div style="background:rgba(59,130,246,.04);border:1px solid rgba(59,130,246,.1);padding:18px;margin-bottom:14px;">
<div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.6);text-transform:uppercase;margin-bottom:12px;">■ 🇰🇷 Korea CVC Radar</div>
<div style="font-size:11px;color:rgba(232,232,240,.6);line-height:1.8;">
<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);"><div style="font-weight:500;color:var(--white);">Samsung Ventures</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(59,130,246,.6);">GridBeyond ✅ Amperon ✅ Emerald AI ✅</div></div>
<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);"><div style="font-weight:500;color:var(--white);">SK Inc / SK Ventures</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(59,130,246,.6);">Bloom Energy ✅ Plug Power ✅ TerraPower ✅</div></div>
<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);"><div style="font-weight:500;color:var(--white);">KEPCO / Korea Power</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(245,158,11,.6);">Grid SW, Nuclear AI — gap exists</div></div>
<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);"><div style="font-weight:500;color:var(--white);">Hanwha / LS / HD Hyundai</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(245,158,11,.6);">Storage, power equipment M&A targets</div></div>
<div style="padding:5px 0;"><div style="font-weight:500;color:var(--white);">LG Nova / LG Tech Ventures</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(59,130,246,.6);">Cooling, power electronics, EV</div></div>
</div></div>
<div style="background:var(--card);border:1px solid var(--border);padding:18px;">
<div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.5);text-transform:uppercase;margin-bottom:12px;">■ DB Score Updates</div>
{db_html if db_html else '<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:var(--dim);">Auto-detected from brief signals.</div>'}
</div>
</div>
</div>
</div></body></html>"""


def save_outputs(brief: dict) -> None:
    os.makedirs("docs/briefs", exist_ok=True)

    # 브리프별 HTML도 저장 (아카이브 링크용)
    week = brief.get("week", "")
    brief_html = render_html(brief)

    for path, content in [
        ("docs/brief_latest.json", json.dumps(brief, ensure_ascii=False, indent=2)),
        ("docs/brief_latest.html", brief_html),
        (f"docs/briefs/{week}.json", json.dumps(brief, ensure_ascii=False, indent=2)),
        (f"docs/briefs/{week}.html", brief_html),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[INFO] 저장: {path}")

    # archive.html 자동 재생성
    archive_html = generate_archive_html()
    with open("docs/archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"[INFO] 아카이브 재생성 완료 ({len(open('docs/archive.html').readlines())} lines)")

    # hyperscaler.html 자동 재생성
    try:
        from proprietary_data import fetch_hyperscaler_news, generate_hyperscaler_html
        print("[INFO] Fetching hyperscaler news...")
        hs_news = fetch_hyperscaler_news()
        hs_html = generate_hyperscaler_html(hs_news)
        with open("docs/hyperscaler.html", "w", encoding="utf-8") as f:
            f.write(hs_html)
        total_hs = sum(len(v) for v in hs_news.values())
        print(f"[INFO] hyperscaler.html regenerated ({total_hs} news items)")
    except Exception as e:
        print(f"[WARN] hyperscaler.html regeneration failed: {e}")

    # ── Deal Flow Tracker 자동 재생성 ──────────────────────────────
    try:
        dealflow_html = generate_dealflow_html(brief)
        with open("docs/dealflow.html", "w", encoding="utf-8") as f:
            f.write(dealflow_html)
        print(f"[INFO] dealflow.html regenerated")
    except Exception as e:
        print(f"[WARN] dealflow.html failed: {e}")

    # ── Startup DB Score 자동 업데이트 ─────────────────────────────
    try:
        updated = update_startup_scores(brief)
        if updated:
            print(f"[INFO] Startup DB: {updated} companies updated")
    except Exception as e:
        print(f"[WARN] Startup DB update failed: {e}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("GRIDEDGE Brief Pipeline")
    print("=" * 60)

    signals  = collect_all_signals()
    filtered = filter_signals(signals, top_n=50)  # 소스 확대로 넉넉하게

    # 지난 브리프에 나온 시그널 제거
    seen_titles = load_seen_titles(days=5)
    if seen_titles:
        filtered = filter_seen_signals(filtered, seen_titles)
        # 제거 후 top_n 재적용
        filtered = filtered[:20]
    else:
        filtered = filtered[:20]

    print(f"[INFO] 최종 신규 시그널: {len(filtered)}개")
    eia_data = fetch_eia_data()

    # 독점 데이터 수집 + filtered에 직접 추가
    proprietary_text = ""
    if PROPRIETARY_ENABLED:
        try:
            prop_data = collect_proprietary_data()
            proprietary_text = format_proprietary_for_prompt(prop_data)

            # 독점 시그널을 RSS 시그널과 동일한 형식으로 변환 → filtered에 추가
            prop_signals = []
            for key in ["sec_form_d", "arxiv", "doe_grants", "hiring_signals", "hn_launches", "patents"]:
                for item in prop_data.get(key, []):
                    signal_text = item.get("signal", "")
                    if not signal_text:
                        continue
                    # 섹터 결정
                    raw_sector = item.get("sector", "OTHER")
                    sector_map = {
                        "EARLY_STAGE": "POWER_TECH",
                        "POWER_TECH": "POWER_TECH",
                        "GRID": "GRID",
                        "BESS": "BESS",
                    }
                    mapped_sector = sector_map.get(raw_sector, "POWER_TECH")

                    prop_signals.append({
                        "title": signal_text[:120],
                        "description": item.get("summary", signal_text)[:500],
                        "source": item.get("source", "Proprietary"),
                        "source_tier": "A",
                        "sector": mapped_sector,
                        "url": item.get("url", ""),
                        "published": item.get("filed_date", item.get("published", "")),
                        "score": 0.85,
                        "breakdown": {"funding": 0.8, "deal": 0.8, "sector": 0.9, "tier": 0.15},
                        "is_early_stage": item.get("is_early_stage", False),
                        "deal_stage_hint": item.get("deal_stage", ""),
                        "extracted_numbers": {},
                    })

            if prop_signals:
                print(f"[INFO] 독점 시그널 {len(prop_signals)}개 → filtered에 추가")
                # 중복 제거 후 상위 시그널에 합산
                filtered = prop_signals + filtered
                filtered = filtered[:25]  # 최대 25개로 제한

        except Exception as e:
            print(f"[WARN] 독점 데이터 수집 실패: {e}")

    # 에이전트 체인 or 단일 AI 분기
    if AGENT_CHAIN_ENABLED:
        print("[INFO] 에이전트 체인 모드 (4개 전문 에이전트)")
        _now      = datetime.utcnow()
        _iso      = _now.isocalendar()
        _week_str = f"{_iso[0]}-W{_iso[1]:02d}"
        _date_str = _now.strftime("%Y-%m-%d")
        brief = run_agent_chain(filtered, proprietary_text, _week_str, _date_str)
        brief["generated_at"] = _now.isoformat()
        brief["signal_count"] = len(filtered)
        brief["sources_used"] = list({s["source"] for s in filtered})

        # deal_stage 자동 보완 — 모든 시그널 처리
        import re as _re
        src_stage_map = {
            "arxiv": "PRE_SEED",
            "arpa-e": "PRE_SEED",
            "doe": "PRE_SEED",
            "hacker news": "SEED",
            "climatebase": "SERIES_A",
            "sec form d": "SEED",
            "uspto": "PRE_SEED",
        }
        fmap = {s["title"][:50]: s for s in filtered}

        for sig in brief.get("deal_signals", []):
            stage = sig.get("deal_stage", "")
            if stage and stage not in ("", "UNKNOWN", None):
                continue  # 이미 있으면 스킵

            # 1. 소스 기반
            src = sig.get("source", "").lower()
            for k, v in src_stage_map.items():
                if k in src:
                    sig["deal_stage"] = v
                    break

            # 2. deal_stage_hint 폴백
            if not sig.get("deal_stage") or sig.get("deal_stage") == "UNKNOWN":
                orig = fmap.get(sig.get("title", "")[:50], {})
                hint = orig.get("deal_stage_hint", "")
                if hint and hint not in ("UNKNOWN", "", None):
                    sig["deal_stage"] = hint

            # 3. 금액 기반 추론
            if not sig.get("deal_stage") or sig.get("deal_stage") == "UNKNOWN":
                text = (sig.get("title", "") + " " + sig.get("summary", "")).lower()
                billions = _re.findall(r"\$(\d+(?:\.\d+)?)\s*b(?:illion)?", text)
                millions = _re.findall(r"\$(\d+(?:\.\d+)?)\s*m(?:illion)?", text)
                if billions:
                    amt = float(billions[0])
                    sig["deal_stage"] = "PROJECT_FINANCE" if amt >= 0.5 else "LATE_STAGE"
                elif millions:
                    amt = float(millions[0])
                    if amt < 5:
                        sig["deal_stage"] = "SEED"
                    elif amt < 30:
                        sig["deal_stage"] = "SERIES_A"
                    elif amt < 100:
                        sig["deal_stage"] = "SERIES_B"
                    else:
                        sig["deal_stage"] = "LATE_STAGE"
                else:
                    # 기본값 — 대형 인프라 딜
                    mw = _re.findall(r"(\d+(?:\.\d+)?)\s*(?:gw|gwh)", text)
                    if mw:
                        sig["deal_stage"] = "PROJECT_FINANCE"
                    else:
                        sig["deal_stage"] = "LATE_STAGE"

        # 통계 출력
        stage_counts = {}
        for sig in brief.get("deal_signals", []):
            st = sig.get("deal_stage", "UNKNOWN")
            stage_counts[st] = stage_counts.get(st, 0) + 1
        print(f"[INFO] Stage 분포: {stage_counts}")
    else:
        print("[INFO] 단일 AI 모드")
        brief = generate_brief(filtered, eia_data, proprietary_text)

    save_outputs(brief)

    print("=" * 60)
    print(f"완료: {brief['week']} — {brief['headline']}")
    print("=" * 60)

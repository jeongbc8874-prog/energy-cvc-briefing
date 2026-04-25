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
    # ── Tier A: AI 데이터센터 전력 전문 ─────────────────────────────
    {"name": "Datacenter Dynamics",  "url": "https://www.datacenterdynamics.com/en/rss/",            "tier": "A"},
    {"name": "Data Center Knowledge", "url": "https://www.datacenterfrontier.com/feed/",             "tier": "A"},
    {"name": "Utility Dive",         "url": "https://www.utilitydive.com/feeds/news/",               "tier": "A"},
    {"name": "Energy Storage News",  "url": "https://www.energy-storage.news/feed/",                 "tier": "A"},
    {"name": "PV Tech",              "url": "https://www.pv-tech.org/feed/",                         "tier": "A"},
    {"name": "Canary Media",         "url": "https://canarymedia.com/feed",                          "tier": "A"},
    {"name": "CTVC Climatetech",     "url": "https://www.ctvc.co/rss/",                             "tier": "A"},
    {"name": "Electrek",             "url": "https://electrek.co/feed/",                             "tier": "A"},
    # ── Tier A: 공공기관 / 규제 ─────────────────────────────────────
    {"name": "DOE News",             "url": "https://www.energy.gov/rss.xml",                        "tier": "A"},
    {"name": "NREL News",            "url": "https://www.nrel.gov/news/rss/newsroom.xml",            "tier": "A"},
    {"name": "EIA Analysis",         "url": "https://www.eia.gov/rss/press_releases.xml",            "tier": "A"},
    # ── Tier B: 전력/그리드 인프라 ──────────────────────────────────
    {"name": "T&D World",            "url": "https://www.tdworld.com/rss",                           "tier": "B"},
    {"name": "Power Magazine",       "url": "https://www.powermag.com/feed/",                        "tier": "B"},
    {"name": "Nuclear Engineering",  "url": "https://www.neimagazine.com/rss",                       "tier": "B"},
    {"name": "Carbon Brief",         "url": "https://www.carbonbrief.org/feed/",                     "tier": "B"},
    {"name": "Offshore Wind Biz",    "url": "https://www.offshorewind.biz/feed/",                    "tier": "B"},
    {"name": "Clean Energy Wire",    "url": "https://www.cleanenergywire.org/rss.xml",               "tier": "B"},
    # ── Tier B: VC/딜 ───────────────────────────────────────────────
    {"name": "Greentown Labs",       "url": "https://greentownlabs.com/feed/",                       "tier": "B"},
    {"name": "Energy Monitor",       "url": "https://www.energymonitor.ai/feed/",                    "tier": "B"},
    {"name": "CleanTechnica",        "url": "https://cleantechnica.com/feed/",                       "tier": "B"},
]

# 섹터 키워드 매핑 (시그널 분류용)
SECTOR_KEYWORDS = {
    # AI DC 전력 핵심 5개 버티컬
    "AI_DC_POWER": ["data center", "datacenter", "hyperscaler", "ai power", "gpu cluster",
                    "microsoft", "google", "amazon", "meta", "ai campus", "digital infrastructure",
                    "compute", "inference", "training cluster", "ai load"],
    "BESS":        ["battery", "energy storage", "bess", "lithium", "flow battery",
                    "co-located storage", "grid-scale battery", "4-hour", "8-hour", "storage attachment"],
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

    # 기본 점수
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

    # AI DC 핵심 키워드 보너스
    ai_dc_keywords = ["interconnection", "transformer", "grid-forming", "frequency response",
                      "24/7 cfe", "power purchase", "offtake", "ferc", "pjm", "ercot",
                      "inference", "token", "gpu power", "data center power"]
    ai_dc_boost = min(sum(0.1 for k in ai_dc_keywords if k in text), 0.3)

    total = (
        funding_score      * 0.25 +
        deal_score         * 0.15 +
        sector_score       * 0.20 +
        tier_bonus         * 0.10 +
        hyperscaler_boost  * 0.15 +
        size_score         * 0.10 +
        ai_dc_boost        * 0.05 +
        (1 - risk_score)   * 0.00   # 리스크 기사 보존 (레드플래그용)
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
    red_flag_pool = [s for s in signals if s["score_breakdown"]["risk"] > 0.4]

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
  .analyst-edge{font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(59,130,246,.7);padding:7px 12px;background:rgba(59,130,246,.04);border-left:2px solid rgba(59,130,246,.3);margin-top:8px;line-height:1.5;}
  .analyst-edge-label{font-size:8px;letter-spacing:.15em;text-transform:uppercase;color:rgba(59,130,246,.45);margin-bottom:2px;}
  .acb-title{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.7);text-transform:uppercase;margin-bottom:10px;}
  .acb-stats{display:flex;gap:24px;margin-bottom:10px;flex-wrap:wrap;}
  .acb-stat{font-family:'IBM Plex Mono',monospace;font-size:10px;color:rgba(245,244,239,.5);}
  .acb-stat span{color:rgba(59,130,246,.9);font-weight:500;}
  .acb-summary{font-size:12px;color:rgba(245,244,239,.4);line-height:1.6;font-style:italic;}
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

<section>
  <div class="section-label">■ DEAL SIGNALS</div>
  {% for s in brief.deal_signals %}
  <div class="signal-card">
    <div class="signal-header">
      <span class="tag tag-{{ s.tag }}">{{ s.tag }}</span>
      <span class="tag tag-sector">{{ s.sector }}</span>
      <span class="tag tag-conf-{{ s.confidence }}">{{ s.confidence }}</span>
      <span class="signal-title">{{ s.title }}</span>
    </div>
    <div class="signal-summary">{{ s.summary }}</div>
    <div class="signal-impl">→ {{ s.implication }}</div>
    {% if s.recommendation %}
    <div style="margin:8px 0 4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
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

def save_outputs(brief: dict) -> None:
    os.makedirs("docs/briefs", exist_ok=True)

    for path, content in [
        ("docs/brief_latest.json", json.dumps(brief, ensure_ascii=False, indent=2)),
        ("docs/brief_latest.html", render_html(brief)),
        (f"docs/briefs/{brief['week']}.json", json.dumps(brief, ensure_ascii=False, indent=2)),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[INFO] 저장: {path}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("GRIDEDGE Brief Pipeline")
    print("=" * 60)

    signals  = collect_all_signals()
    filtered = filter_signals(signals, top_n=20)
    eia_data = fetch_eia_data()

    # 독점 데이터 수집
    proprietary_text = ""
    if PROPRIETARY_ENABLED:
        try:
            prop_data = collect_proprietary_data()
            proprietary_text = format_proprietary_for_prompt(prop_data)
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
    else:
        print("[INFO] 단일 AI 모드")
        brief = generate_brief(filtered, eia_data, proprietary_text)

    save_outputs(brief)

    print("=" * 60)
    print(f"완료: {brief['week']} — {brief['headline']}")
    print("=" * 60)

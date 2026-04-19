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

# ── 설정 ─────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EIA_API_KEY       = os.environ.get("EIA_API_KEY", "")       # 무료 발급: eia.gov/opendata
ENTSOE_TOKEN      = os.environ.get("ENTSOE_TOKEN", "")      # 무료 발급: transparency.entsoe.eu

# ── 무료 RSS 소스 정의 ────────────────────────────────────────────────────────

RSS_SOURCES = [
    # 에너지 전문 미디어
    {"name": "Utility Dive",       "url": "https://www.utilitydive.com/feeds/news/",               "tier": "A"},
    {"name": "PV Magazine",        "url": "https://www.pv-magazine.com/feed/",                      "tier": "A"},
    {"name": "Recharge News",      "url": "https://www.rechargenews.com/rss",                       "tier": "A"},
    {"name": "Energy Monitor",     "url": "https://www.energymonitor.ai/feed/",                     "tier": "A"},
    {"name": "PV Tech",            "url": "https://www.pv-tech.org/feed/",                          "tier": "A"},
    {"name": "Energy Storage News","url": "https://www.energy-storage.news/feed/",                  "tier": "A"},
    {"name": "Wind Power Monthly", "url": "https://www.windpowermonthly.com/rss-feeds",             "tier": "B"},
    {"name": "Hydrogen Insight",   "url": "https://www.hydrogeninsight.com/feed",                   "tier": "B"},
    {"name": "Nuclear Engineering","url": "https://www.neimagazine.com/rss",                        "tier": "B"},
    # 공공기관
    {"name": "IEA News",           "url": "https://www.iea.org/news/rss",                           "tier": "A"},
    {"name": "IRENA News",         "url": "https://www.irena.org/rss/News",                         "tier": "B"},
    {"name": "FERC News",          "url": "https://www.ferc.gov/news-events/news/rss.xml",          "tier": "B"},
    # VC/펀딩 관련
    {"name": "Greentown Labs",     "url": "https://greentownlabs.com/feed/",                        "tier": "B"},
    {"name": "CTVC (Climatetech)", "url": "https://www.ctvc.co/rss/",                              "tier": "A"},
    # 한국
    {"name": "전기신문",           "url": "https://www.electimes.com/rss/allArticle.xml",           "tier": "B"},
]

# 섹터 키워드 매핑 (시그널 분류용)
SECTOR_KEYWORDS = {
    "BESS":  ["battery", "energy storage", "bess", "lithium", "flow battery", "배터리", "ESS"],
    "GRID":  ["grid", "transmission", "substation", "transformer", "interconnection", "계통", "송전"],
    "SOLAR": ["solar", "photovoltaic", "pv", "bifacial", "perovskite", "태양광"],
    "WIND":  ["wind", "offshore wind", "onshore", "turbine", "풍력"],
    "SMR":   ["smr", "nuclear", "reactor", "fission", "원자력", "소형모듈"],
    "H2":    ["hydrogen", "electrolyzer", "fuel cell", "electrolysis", "수소"],
    "VPP":   ["virtual power", "vpp", "demand response", "flexibility", "분산에너지"],
    "CCS":   ["carbon capture", "ccs", "ccus", "direct air", "탄소포집"],
    "EV":    ["electric vehicle", "ev charging", "charging station", "전기차"],
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


def score_signal(article: dict) -> tuple[float, dict]:
    text = (article["title"] + " " + article["description"]).lower()

    # 세부 점수
    funding_score = min(sum(1 for k in FUNDING_KEYWORDS if k in text) / 3, 1.0)
    deal_score    = min(sum(1 for k in DEAL_KEYWORDS    if k in text) / 2, 1.0)
    risk_score    = min(sum(1 for k in RISK_KEYWORDS    if k in text) / 2, 1.0)
    tier_bonus    = 0.15 if article["source_tier"] == "A" else 0.0

    # 섹터 관련성
    sector_hit = sum(
        1 for kws in SECTOR_KEYWORDS.values()
        for k in kws if k in text
    )
    sector_score = min(sector_hit / 3, 1.0)

    total = (
        funding_score * 0.35 +
        deal_score    * 0.20 +
        sector_score  * 0.25 +
        tier_bonus    * 0.15 +
        (1 - risk_score) * 0.05   # 리스크 기사는 약간 감점 (단, 레드플래그용으로 보존)
    )

    breakdown = {
        "funding": round(funding_score, 2),
        "deal":    round(deal_score, 2),
        "sector":  round(sector_score, 2),
        "risk":    round(risk_score, 2),
        "tier":    tier_bonus,
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
You are a Senior Investment Analyst specializing in the global energy sector.
You write weekly intelligence briefs from the perspective of an experienced energy VC/PE investor
with deep expertise in power systems, clean energy technology, and global energy markets.

Core principles:
1. No policy language — analyze through physics, economics, and contract structures only
2. No plain news summaries — only insights that directly inform investment decisions
3. Flag technical feasibility concerns explicitly as RED_FLAG
4. Always include valuation and IRR implications
5. Clearly distinguish between "confirmed facts" and "analytical inference"
6. Write in English — concise, precise, institutional tone

Output: Pure JSON only. No markdown code blocks.
"""

USER_PROMPT_TEMPLATE = """
Analyze the following {n} energy sector signals and generate a weekly investment intelligence brief.
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


def generate_brief(signals: list[dict], eia_data: dict) -> dict:
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

    user_prompt = USER_PROMPT_TEMPLATE.format(
        n=len(signals),
        date=now.strftime("%Y-%m-%d"),
        week=week_str,
        signals_text=signals_text + eia_context,
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
    <div class="signal-source">출처: {{ s.source }}</div>
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
    <div class="signal-source">출처: {{ r.source }}</div>
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
    print("GRIDEDGE Weekly Brief Pipeline v2")
    print("=" * 60)

    signals  = collect_all_signals()
    filtered = filter_signals(signals, top_n=15)
    eia_data = fetch_eia_data()
    brief    = generate_brief(filtered, eia_data)
    save_outputs(brief)

    print("=" * 60)
    print(f"완료: {brief['week']} — {brief['headline']}")
    print("=" * 60)

"""
GRIDEDGE Weekly Brief Pipeline
실행: python pipeline/generate_brief.py
출력: docs/brief_latest.json, docs/brief_latest.html
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dateutil.isocalendar import IsoCalendarDate
import anthropic
from jinja2 import Template

# ── 설정 ─────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NEWSAPI_KEY       = os.environ.get("NEWSAPI_KEY", "")

# 커버할 에너지 서브섹터 키워드 (뉴스 수집용)
SECTOR_QUERIES = [
    "energy storage battery startup funding",
    "grid infrastructure investment",
    "small modular reactor SMR",
    "hydrogen electrolyzer startup",
    "virtual power plant VPP",
    "solar wind offshore investment",
    "carbon capture CCS venture",
    "EV charging infrastructure",
]

# 시그널 스코어링 가중치
SCORE_WEIGHTS = {
    "funding_round":   0.30,   # 펀딩 라운드 언급
    "trl_signal":      0.25,   # 기술 성숙도 관련
    "grid_relevance":  0.20,   # 계통/그리드 연관
    "policy_exposure": 0.15,   # 정책 의존도 (역방향 — 높을수록 감점)
    "market_timing":   0.10,   # 시장 타이밍
}

# ── 1단계: 뉴스 수집 ──────────────────────────────────────────────────────────

def fetch_news(query: str, days_back: int = 7) -> list[dict]:
    """NewsAPI에서 최근 N일 에너지 관련 기사 수집"""
    if not NEWSAPI_KEY:
        return _mock_news(query)

    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 5,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        articles = r.json().get("articles", [])
        return [
            {
                "title":       a["title"],
                "description": a.get("description", ""),
                "url":         a["url"],
                "source":      a["source"]["name"],
                "published":   a["publishedAt"][:10],
            }
            for a in articles
            if a.get("title") and "[Removed]" not in a["title"]
        ]
    except Exception as e:
        print(f"[WARN] NewsAPI 실패 ({query}): {e}")
        return []


def _mock_news(query: str) -> list[dict]:
    """NEWSAPI_KEY 없을 때 테스트용 더미 데이터"""
    return [
        {
            "title": f"[MOCK] {query} — Series B funding announced",
            "description": "Major energy startup secures growth-stage funding for grid-scale deployment.",
            "url": "https://example.com",
            "source": "Energy Monitor",
            "published": datetime.utcnow().strftime("%Y-%m-%d"),
        }
    ]


def collect_all_signals() -> list[dict]:
    """전체 서브섹터 뉴스 수집 후 중복 제거"""
    seen_urls = set()
    signals = []
    for query in SECTOR_QUERIES:
        articles = fetch_news(query)
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                a["query_tag"] = query
                signals.append(a)
    print(f"[INFO] 수집 시그널: {len(signals)}개")
    return signals


# ── 2단계: 시그널 스코어링 (키워드 기반 1차 필터) ────────────────────────────

FUNDING_KEYWORDS   = ["series a", "series b", "series c", "seed", "raised", "funding", "investment", "$"]
TRL_KEYWORDS       = ["commercial", "pilot", "demonstration", "trl", "scale-up", "deployed"]
GRID_KEYWORDS      = ["grid", "transmission", "interconnection", "ferc", "kepco", "utility"]
POLICY_KEYWORDS    = ["subsidy", "ira", "grant", "government", "regulation", "tax credit"]
TIMING_KEYWORDS    = ["2025", "2026", "expanding", "growing", "demand", "shortage", "bottleneck"]


def score_signal(article: dict) -> float:
    text = (article["title"] + " " + article["description"]).lower()

    funding   = sum(1 for k in FUNDING_KEYWORDS if k in text) / len(FUNDING_KEYWORDS)
    trl       = sum(1 for k in TRL_KEYWORDS    if k in text) / len(TRL_KEYWORDS)
    grid      = sum(1 for k in GRID_KEYWORDS   if k in text) / len(GRID_KEYWORDS)
    policy    = sum(1 for k in POLICY_KEYWORDS if k in text) / len(POLICY_KEYWORDS)
    timing    = sum(1 for k in TIMING_KEYWORDS if k in text) / len(TIMING_KEYWORDS)

    score = (
        funding   * SCORE_WEIGHTS["funding_round"] +
        trl       * SCORE_WEIGHTS["trl_signal"] +
        grid      * SCORE_WEIGHTS["grid_relevance"] +
        (1-policy)* SCORE_WEIGHTS["policy_exposure"] +   # 정책 의존도 높을수록 감점
        timing    * SCORE_WEIGHTS["market_timing"]
    )
    return round(score, 4)


def filter_signals(signals: list[dict], top_n: int = 12) -> list[dict]:
    for s in signals:
        s["score"] = score_signal(s)
    ranked = sorted(signals, key=lambda x: x["score"], reverse=True)
    selected = ranked[:top_n]
    print(f"[INFO] 상위 {top_n}개 시그널 선정 (최고점: {selected[0]['score'] if selected else 0})")
    return selected


# ── 3단계: Claude API → 브리프 생성 ─────────────────────────────────────────

SYSTEM_PROMPT = """
당신은 에너지 섹터 전문 투자 심사역(Senior Investment Analyst)입니다.
15년 경력의 에너지 VC/PE 심사역 관점에서 주간 인텔리전스 브리프를 작성합니다.

작성 원칙:
- 정책 언어 금지. 물리학·경제학·계약 구조 중심으로 분석
- 단순 뉴스 요약 금지. 투자 판단에 직접 연결되는 인사이트만
- 기술 타당성 의심 사례는 명시적으로 레드플래그 표시
- 밸류에이션 임플리케이션 항상 포함
- 한국어로 작성

출력 형식: 반드시 순수 JSON만 출력. 마크다운 코드블록 없이.
"""

USER_PROMPT_TEMPLATE = """
아래 {n}개의 에너지 섹터 뉴스 시그널을 분석해 주간 브리프를 생성하세요.
오늘 날짜: {date}
주차: {week}

=== 입력 시그널 ===
{signals_text}

=== 출력 JSON 스키마 ===
{{
  "week": "2025-W47",
  "headline": "이번 주 핵심 테마 한 줄",
  "thesis": "이번 주 핵심 투자 판단 2-3문장 (심사역 관점)",
  "deal_signals": [
    {{
      "title": "딜/기업명 또는 이슈",
      "tag": "BULLISH | WATCH | RED_FLAG",
      "sector": "BESS | GRID | SMR | H2 | SOLAR | WIND | VPP | CCS | EV | OTHER",
      "summary": "투자 판단 관점 2-3문장",
      "implication": "밸류에이션/IRR 임플리케이션 1문장",
      "source_title": "원본 기사 제목"
    }}
  ],
  "sector_positioning": [
    {{
      "sector": "섹터명",
      "stance": "OVERWEIGHT | NEUTRAL | UNDERWEIGHT",
      "rationale": "근거 1-2문장"
    }}
  ],
  "red_flags": [
    {{
      "issue": "레드플래그 제목",
      "detail": "구체적 우려 사항"
    }}
  ],
  "macro_watch": "매크로 변수 → 에너지 VC 임플리케이션 2문장"
}}

deal_signals는 최소 4개, sector_positioning은 3-5개 섹터 필수.
"""


def generate_brief(signals: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    now = datetime.utcnow()
    iso_cal = now.isocalendar()
    week_str = f"{iso_cal.year}-W{iso_cal.week:02d}"

    signals_text = "\n\n".join([
        f"[{i+1}] {s['title']}\n출처: {s['source']} ({s['published']})\n내용: {s['description']}\nScore: {s['score']}"
        for i, s in enumerate(signals)
    ])

    user_prompt = USER_PROMPT_TEMPLATE.format(
        n=len(signals),
        date=now.strftime("%Y-%m-%d"),
        week=week_str,
        signals_text=signals_text,
    )

    print("[INFO] Claude API 호출 중...")
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()
    # 혹시 코드블록 래핑된 경우 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    brief = json.loads(raw)
    brief["generated_at"] = now.isoformat()
    brief["signal_count"]  = len(signals)
    print(f"[INFO] 브리프 생성 완료: {brief.get('week')} — {brief.get('headline')}")
    return brief


# ── 4단계: HTML 렌더링 ────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GRIDEDGE {{ brief.week }}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=IBM+Plex+Mono:wght@400;500&family=Pretendard:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root { --black:#0a0a08;--white:#f5f4ef;--amber:#d4820a;--amber-light:#f0a832;--muted:#6b6b5e;--border:rgba(212,130,10,0.2); }
  *{margin:0;padding:0;box-sizing:border-box;}
  body{background:var(--black);color:var(--white);font-family:'Pretendard',sans-serif;max-width:800px;margin:0 auto;padding:48px 32px;}
  .meta{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.2em;color:var(--amber);text-transform:uppercase;margin-bottom:8px;}
  h1{font-family:'DM Serif Display',serif;font-size:36px;line-height:1.1;margin-bottom:16px;}
  .thesis{font-size:15px;line-height:1.7;color:var(--muted);padding:24px;border-left:2px solid var(--amber);margin-bottom:48px;font-weight:300;}
  .section-label{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.2em;color:var(--amber);text-transform:uppercase;margin-bottom:24px;padding-bottom:8px;border-bottom:1px solid var(--border);}
  .signal-card{border:1px solid var(--border);padding:24px;margin-bottom:12px;}
  .signal-header{display:flex;align-items:center;gap:12px;margin-bottom:12px;}
  .tag{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.15em;padding:3px 8px;border-radius:2px;}
  .tag-BULLISH{background:rgba(74,222,128,.1);color:#4ade80;}
  .tag-WATCH{background:rgba(212,130,10,.1);color:var(--amber);}
  .tag-RED_FLAG{background:rgba(248,113,113,.1);color:#f87171;}
  .signal-title{font-size:14px;font-weight:500;}
  .signal-summary{font-size:13px;line-height:1.65;color:var(--muted);margin-bottom:8px;font-weight:300;}
  .signal-implication{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--amber-light);padding:8px 12px;background:rgba(212,130,10,.04);border-left:1px solid var(--border);}
  .positioning-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:48px;}
  .pos-card{border:1px solid var(--border);padding:20px;}
  .pos-stance{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.1em;margin-bottom:8px;}
  .OVERWEIGHT{color:#4ade80;} .NEUTRAL{color:var(--amber);} .UNDERWEIGHT{color:#f87171;}
  .pos-sector{font-size:15px;font-weight:500;margin-bottom:8px;}
  .pos-rationale{font-size:12px;color:var(--muted);line-height:1.6;font-weight:300;}
  .macro-box{border:1px solid var(--border);padding:24px;background:rgba(212,130,10,.02);margin-bottom:48px;font-size:13px;line-height:1.7;color:var(--muted);}
  .footer-meta{font-family:'IBM Plex Mono',monospace;font-size:9px;color:rgba(245,244,239,.15);letter-spacing:.1em;border-top:1px solid var(--border);padding-top:24px;margin-top:48px;}
  section{margin-bottom:48px;}
</style>
</head>
<body>
<div class="meta">GRIDEDGE INTELLIGENCE · {{ brief.week }}</div>
<h1>{{ brief.headline }}</h1>
<div class="thesis">{{ brief.thesis }}</div>

<section>
  <div class="section-label">■ 딜 시그널</div>
  {% for s in brief.deal_signals %}
  <div class="signal-card">
    <div class="signal-header">
      <span class="tag tag-{{ s.tag }}">{{ s.tag }}</span>
      <span class="tag" style="border:1px solid var(--border);color:var(--muted);">{{ s.sector }}</span>
      <span class="signal-title">{{ s.title }}</span>
    </div>
    <div class="signal-summary">{{ s.summary }}</div>
    <div class="signal-implication">→ {{ s.implication }}</div>
  </div>
  {% endfor %}
</section>

<section>
  <div class="section-label">■ 섹터 포지셔닝</div>
  <div class="positioning-grid">
    {% for p in brief.sector_positioning %}
    <div class="pos-card">
      <div class="pos-stance {{ p.stance }}">{{ p.stance }}</div>
      <div class="pos-sector">{{ p.sector }}</div>
      <div class="pos-rationale">{{ p.rationale }}</div>
    </div>
    {% endfor %}
  </div>
</section>

{% if brief.red_flags %}
<section>
  <div class="section-label">■ 레드플래그</div>
  {% for r in brief.red_flags %}
  <div class="signal-card" style="border-color:rgba(248,113,113,.2);">
    <div class="signal-title" style="color:#f87171;margin-bottom:8px;">⚠ {{ r.issue }}</div>
    <div class="signal-summary">{{ r.detail }}</div>
  </div>
  {% endfor %}
</section>
{% endif %}

<section>
  <div class="section-label">■ 매크로 워치</div>
  <div class="macro-box">{{ brief.macro_watch }}</div>
</section>

<div class="footer-meta">
  GRIDEDGE INTELLIGENCE · 생성: {{ brief.generated_at[:10] }} · 
  분석 시그널 {{ brief.signal_count }}개 처리 · AI-assisted, expert-framed
</div>
</body>
</html>"""


def render_html(brief: dict) -> str:
    tmpl = Template(HTML_TEMPLATE)
    return tmpl.render(brief=brief)


# ── 5단계: 저장 ───────────────────────────────────────────────────────────────

def save_outputs(brief: dict) -> None:
    os.makedirs("docs", exist_ok=True)

    json_path = "docs/brief_latest.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    print(f"[INFO] JSON 저장: {json_path}")

    html_path = "docs/brief_latest.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(brief))
    print(f"[INFO] HTML 저장: {html_path}")

    # 아카이브 (날짜별 보관)
    archive_path = f"docs/briefs/{brief['week']}.json"
    os.makedirs("docs/briefs", exist_ok=True)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 아카이브: {archive_path}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("GRIDEDGE Weekly Brief Pipeline")
    print("=" * 60)

    signals  = collect_all_signals()
    filtered = filter_signals(signals, top_n=12)
    brief    = generate_brief(filtered)
    save_outputs(brief)

    print("=" * 60)
    print(f"완료: {brief['week']} — {brief['headline']}")
    print("=" * 60)

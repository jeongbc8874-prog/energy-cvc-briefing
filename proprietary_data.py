"""
GRIDEDGE Proprietary Data Collection v2
Early Stage 특화 — SIC 코드 기반 SEC Form D + arXiv + ARPA-E RSS + USPTO
"""

import requests
import json
import re
import time
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "GRIDEDGE Intelligence gridedge.intel@gmail.com"}

# ── 에너지 관련 SIC 코드 ──────────────────────────────────────────────────────
# Form D는 키워드 검색 안 됨 → SIC 코드로 필터링해야 함
ENERGY_SIC_CODES = {
    "4911": "Electric Services",
    "4931": "Electric & Other Services Combined",
    "4941": "Water Supply",
    "3559": "Special Industry Machinery (Battery Equipment)",
    "3621": "Motors & Generators",
    "3629": "Electrical Industrial Equipment",
    "3674": "Semiconductors (Power Electronics)",
    "3679": "Electronic Components (Inverters)",
    "3691": "Storage Batteries",
    "3692": "Primary Batteries",
    "3699": "Electronic Equipment",
    "3825": "Instruments for Measuring (Grid Software)",
    "7372": "Prepackaged Software (Grid/Energy Software)",
    "8711": "Engineering Services",
    "8731": "Commercial Physical & Biological Research",
}

ENERGY_KEYWORDS = [
    "battery", "bess", "energy storage", "solar", "wind", "grid",
    "nuclear", "smr", "hydrogen", "electrolyzer", "power", "electric",
    "renewable", "clean energy", "microgrid", "inverter", "data center power",
    "grid software", "demand response", "grid-forming", "frequency",
    "virtual power plant", "energy management", "storage", "charging",
]


# ── 1. SEC Form D — SIC 코드 기반 ─────────────────────────────────────────────

def fetch_sec_form_d_by_sic() -> list:
    """
    SIC 코드 기반 SEC Form D 수집
    에너지 스타트업 비공개 라운드 탐지 — 정확도 높음
    """
    results = []
    start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    # 주요 SIC 코드만 (API 과부하 방지)
    priority_sics = ["3691", "3692", "3679", "3674", "7372", "8731"]

    for sic in priority_sics:
        try:
            url = (
                "https://efts.sec.gov/LATEST/search-index"
                f"?q=&dateRange=custom"
                f"&startdt={start_date}"
                f"&enddt={datetime.utcnow().strftime('%Y-%m-%d')}"
                f"&forms=D&hits.hits._source.sics={sic}"
            )
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue

            hits = r.json().get("hits", {}).get("hits", [])
            for hit in hits[:5]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                if not entity:
                    continue
                if any(e.get("entity") == entity for e in results):
                    continue

                filed = src.get("file_date", "")
                amount = src.get("offering_amount", "")
                sic_desc = ENERGY_SIC_CODES.get(sic, "Energy")

                try:
                    amt_f = float(amount)
                    amt_str = f"${amt_f/1e6:.1f}M" if amt_f >= 1e6 else f"${amt_f/1e3:.0f}K"
                    # 금액으로 Stage 추정
                    if amt_f < 2e6:
                        stage = "PRE_SEED"
                    elif amt_f < 10e6:
                        stage = "SEED"
                    elif amt_f < 30e6:
                        stage = "SERIES_A"
                    else:
                        stage = "SERIES_B"
                except:
                    amt_str = "undisclosed"
                    stage = "SEED"

                results.append({
                    "source": "SEC Form D",
                    "type": "early_stage_filing",
                    "sector": "EARLY_STAGE",
                    "entity": entity,
                    "filed_date": filed,
                    "sic": sic,
                    "sic_desc": sic_desc,
                    "amount_str": amt_str,
                    "deal_stage": stage,
                    "signal": f"[SEC Form D] {entity} — {amt_str} private raise ({sic_desc}, {filed})",
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={entity.replace(' ','+')}&type=D&dateb=&owner=include&count=10",
                    "is_early_stage": True,
                })
            time.sleep(0.3)

        except Exception as e:
            print(f"  [SEC Form D/SIC {sic}] {e}")

    # 폴백: 텍스트 검색으로 에너지 특화 키워드
    fallback_terms = ["battery storage", "grid software", "clean energy tech", "energy storage"]
    for term in fallback_terms[:2]:
        try:
            encoded = term.replace(" ", "+")
            url = (
                f"https://efts.sec.gov/LATEST/search-index"
                f"?q=%22{encoded}%22"
                f"&dateRange=custom"
                f"&startdt={start_date}"
                f"&enddt={datetime.utcnow().strftime('%Y-%m-%d')}"
                f"&forms=D"
            )
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            for hit in r.json().get("hits", {}).get("hits", [])[:3]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                if not entity or any(e.get("entity") == entity for e in results):
                    continue
                amount = src.get("offering_amount", "")
                filed = src.get("file_date", "")
                try:
                    amt_f = float(amount)
                    amt_str = f"${amt_f/1e6:.1f}M" if amt_f >= 1e6 else f"${amt_f/1e3:.0f}K"
                    stage = "SEED" if amt_f < 10e6 else "SERIES_A"
                except:
                    amt_str = "undisclosed"
                    stage = "SEED"
                results.append({
                    "source": "SEC Form D",
                    "type": "early_stage_filing",
                    "sector": "EARLY_STAGE",
                    "entity": entity,
                    "filed_date": filed,
                    "amount_str": amt_str,
                    "deal_stage": stage,
                    "signal": f"[SEC Form D] {entity} — {amt_str} ({term}, {filed})",
                    "url": "https://efts.sec.gov/LATEST/search-index?forms=D",
                    "is_early_stage": True,
                })
        except Exception as e:
            print(f"  [SEC Form D fallback/{term}] {e}")

    print(f"  [SEC Form D] {len(results)}개 수집")
    return results


# ── 2. arXiv 에너지 논문 → 창업 6-18개월 전 신호 ─────────────────────────────

def fetch_arxiv_energy() -> list:
    """
    arXiv 최신 에너지 기술 논문
    PhD 연구 → 6-18개월 후 스핀아웃/창업 패턴
    지금 이 논문 저자가 미래의 Seed 라운드 창업자
    """
    results = []

    queries = [
        "grid-forming inverter battery storage",
        "AI data center power demand forecasting",
        "BESS energy storage control optimization",
        "hydrogen electrolyzer efficiency",
        "small modular reactor economics",
        "virtual power plant machine learning",
    ]

    for q in queries[:4]:
        try:
            url = (
                "http://export.arxiv.org/api/query"
                f"?search_query=ti:{q.replace(' ', '+')}"
                "&start=0&max_results=3"
                "&sortBy=submittedDate&sortOrder=descending"
            )
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue

            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                published = entry.find("atom:published", ns)
                authors = entry.findall("atom:author", ns)

                title_text = title.text.strip().replace("\n", " ") if title is not None else ""
                summary_text = summary.text.strip()[:300] if summary is not None else ""
                link_text = link.text.strip() if link is not None else ""
                pub_text = published.text[:10] if published is not None else ""
                author_list = [a.find("atom:name", ns).text for a in authors[:3] if a.find("atom:name", ns) is not None]

                # 투자 관련 키워드 체크
                text = (title_text + " " + summary_text).lower()
                if not any(k in text for k in ENERGY_KEYWORDS):
                    continue

                # 상업화 가능성 신호
                commercial_signals = [
                    "cost reduction", "scalable", "commercial", "deployment",
                    "grid-scale", "mw-scale", "gigawatt", "cost-effective",
                    "economic", "market", "techno-economic"
                ]
                commercial_score = sum(1 for s in commercial_signals if s in text)

                results.append({
                    "source": "arXiv",
                    "type": "research_paper",
                    "sector": "POWER_TECH",
                    "title": title_text,
                    "authors": author_list,
                    "published": pub_text,
                    "commercial_score": commercial_score,
                    "summary": summary_text[:200],
                    "signal": f"[arXiv] {title_text} — {', '.join(author_list[:2])} ({pub_text})" + (" [COMMERCIAL POTENTIAL]" if commercial_score >= 2 else ""),
                    "url": link_text,
                    "is_early_stage": True,
                    "deal_stage": "PRE_SEED",
                })

        except Exception as e:
            print(f"  [arXiv/{q[:30]}] {e}")

    # 상업화 가능성 높은 순으로 정렬
    results.sort(key=lambda x: x.get("commercial_score", 0), reverse=True)
    print(f"  [arXiv] {len(results)}개 논문 수집")
    return results


# ── 3. ARPA-E / DOE RSS — 안정적 버전 ────────────────────────────────────────

def fetch_doe_arpa_rss() -> list:
    """
    ARPA-E + DOE 뉴스 RSS
    그랜트 수상 = Pre-Seed, 12-18개월 후 Series A 패턴
    """
    results = []

    rss_sources = [
        ("https://arpa-e.energy.gov/news-and-media/rss.xml", "ARPA-E"),
        ("https://www.energy.gov/rss.xml", "DOE"),
        ("https://www.energy.gov/eere/articles/rss.xml", "DOE EERE"),
    ]

    try:
        import feedparser
        for url, source in rss_sources:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:8]:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    published = entry.get("published", "")[:10]

                    text = (title + " " + summary).lower()

                    # 에너지 관련 + 펀딩 신호
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                    funding_signals = ["award", "grant", "million", "funding",
                                       "selects", "announces", "$", "prize"]
                    is_funding = any(s in text for s in funding_signals)

                    # 금액 추출
                    amounts = re.findall(r"\$[\d,.]+\s*(?:million|billion|M|B)", text)
                    amt_str = amounts[0] if amounts else ""

                    results.append({
                        "source": source,
                        "type": "government_grant",
                        "sector": "EARLY_STAGE",
                        "signal": f"[{source}] {title}" + (f" — {amt_str}" if amt_str else ""),
                        "url": link,
                        "published": published,
                        "summary": summary[:200],
                        "is_funding": is_funding,
                        "is_early_stage": True,
                        "deal_stage": "PRE_SEED",
                    })
            except Exception as e:
                print(f"  [{source} RSS] {e}")

    except ImportError:
        print("  [DOE/ARPA-E] feedparser 없음")

    print(f"  [DOE/ARPA-E] {len(results)}개 수집")
    return results


# ── 4. 채용 신호 — 스타트업 탐지 ─────────────────────────────────────────────

def fetch_hiring_signals() -> list:
    """
    에너지 스타트업 채용공고 → Series A 직전 신호
    시니어 채용 시작 = 6-9개월 후 라운드 예상
    """
    results = []

    rss_sources = [
        ("https://climatebase.org/jobs.rss", "Climatebase"),
        ("https://jobs.lever.co/rss?department=Engineering", "Lever Jobs"),
    ]

    senior_roles = [
        "cto", "chief technology", "vp engineering", "vp of engineering",
        "founding engineer", "staff engineer", "principal engineer",
        "head of engineering", "director of engineering",
        "chief scientist", "head of research",
    ]

    try:
        import feedparser
        companies_seen = set()

        for url, source in rss_sources:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:25]:
                    title = entry.get("title", "")
                    company = entry.get("author", entry.get("company", ""))
                    link = entry.get("link", "")
                    summary = entry.get("summary", entry.get("description", ""))

                    text = (title + " " + summary + " " + company).lower()

                    # 에너지 관련 확인
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                    # 중복 회사 제거
                    company_key = company.lower().strip()
                    if company_key and company_key in companies_seen:
                        continue

                    is_senior = any(r in text for r in senior_roles)
                    is_founding = "founding" in text or "first" in text

                    if company_key:
                        companies_seen.add(company_key)

                    stage_hint = "SERIES_A" if is_senior else "SEED"

                    results.append({
                        "source": source,
                        "type": "hiring_signal",
                        "sector": "EARLY_STAGE",
                        "entity": company,
                        "signal": (
                            f"[Hiring] {company}: {title}"
                            + (" [SENIOR HIRE — Series A signal]" if is_senior else "")
                            + (" [FOUNDING ROLE — Seed stage]" if is_founding else "")
                        ),
                        "url": link,
                        "is_early_stage": True,
                        "is_senior_hire": is_senior,
                        "is_founding": is_founding,
                        "deal_stage": stage_hint,
                    })
            except Exception as e:
                print(f"  [{source}] {e}")

    except ImportError:
        print("  [Hiring] feedparser 없음")

    print(f"  [Hiring Signals] {len(results)}개 수집")
    return results


# ── 5. Hacker News "Show HN" — 스텔스 런칭 ───────────────────────────────────

def fetch_hn_launches() -> list:
    """
    Hacker News Show HN = 스타트업 공개 런칭 신호
    에너지 관련 Show HN = Seed 단계 창업자
    """
    results = []
    try:
        import feedparser
        feed = feedparser.parse("https://news.ycombinator.com/rss")

        for entry in feed.entries[:50]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            text = title.lower()

            # Show HN 또는 Ask HN: 우리가 만든 것
            is_show = (
                text.startswith("show hn") or
                text.startswith("ask hn") or
                "launch" in text or
                "we built" in text or
                "i built" in text
            )

            if not is_show:
                continue

            if not any(k in text for k in ENERGY_KEYWORDS):
                continue

            results.append({
                "source": "Hacker News",
                "type": "startup_launch",
                "sector": "EARLY_STAGE",
                "signal": f"[HN Launch] {title}",
                "url": link,
                "is_early_stage": True,
                "deal_stage": "SEED",
            })

    except Exception as e:
        print(f"  [HN] {e}")

    print(f"  [HN Launches] {len(results)}개 수집")
    return results


# ── 6. USPTO 특허 — 기술 Moat 조기 탐지 ─────────────────────────────────────

def fetch_energy_patents() -> list:
    """
    USPTO 최신 에너지 기술 특허
    특허 출원 → 창업/Series A 6-18개월 선행 신호
    대학/연구소 출원 = 스핀아웃 가능성
    """
    results = []
    try:
        start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        query = (
            '{"_and":['
            '{"_text_any":{"patent_abstract":"grid-forming battery storage '
            'AI data center power inverter electrolyzer hydrogen"}},'
            f'{{"_gte":{{"patent_date":"{start}"}}}}'
            ']}'
        )
        url = "https://search.patentsview.org/api/v1/patent/"
        params = {
            "q": query,
            "f": '["patent_id","patent_title","patent_date","assignees","inventors"]',
            "o": '{"per_page":8}',
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            for p in r.json().get("patents", []):
                title = p.get("patent_title", "")
                date = p.get("patent_date", "")
                assignees = p.get("assignees", [])
                inventors = p.get("inventors", [])

                if not title:
                    continue

                assignee = ""
                if assignees:
                    assignee = assignees[0].get("assignee_organization", "") or \
                               assignees[0].get("assignee_individual_name_last", "Unknown")

                # 대학/연구소 = 스핀아웃 가능성 높음
                is_academic = any(word in (assignee or "").lower() for word in
                                  ["university", "institute", "laboratory", "college",
                                   "research", "national lab", "MIT", "Stanford", "Caltech"])

                inventor_names = [
                    f"{inv.get('inventor_name_first','')} {inv.get('inventor_name_last','')}"
                    for inv in inventors[:2]
                ]

                results.append({
                    "source": "USPTO",
                    "type": "patent_filing",
                    "sector": "POWER_TECH",
                    "entity": assignee or "Unknown",
                    "inventors": inventor_names,
                    "signal": (
                        f"[Patent] {title} — {assignee} ({date})"
                        + (" [ACADEMIC — spinout candidate]" if is_academic else "")
                    ),
                    "url": "https://search.patentsview.org/",
                    "is_early_stage": True,
                    "is_academic": is_academic,
                    "deal_stage": "PRE_SEED" if is_academic else "SEED",
                })

    except Exception as e:
        print(f"  [USPTO] {e}")

    print(f"  [Patents] {len(results)}개 수집")
    return results


# ── 7. FERC 공시 ──────────────────────────────────────────────────────────────

def fetch_ferc_filings() -> list:
    results = []
    try:
        start = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")
        url = (
            "https://efts.sec.gov/LATEST/search-index"
            "?q=%22interconnection%22+%22data+center%22"
            f"&dateRange=custom&startdt={start}&enddt={end}&forms=8-K"
        )
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            for hit in r.json().get("hits", {}).get("hits", [])[:5]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                filed = src.get("file_date", "")
                if entity:
                    results.append({
                        "source": "SEC EDGAR 8-K",
                        "type": "regulatory_filing",
                        "sector": "GRID",
                        "entity": entity,
                        "signal": f"[8-K] {entity} — grid/DC interconnection disclosure ({filed})",
                        "url": "https://efts.sec.gov/LATEST/search-index?forms=8-K",
                        "filed_date": filed,
                    })
    except Exception as e:
        print(f"  [FERC/8-K] {e}")

    print(f"  [FERC/SEC] {len(results)}개 수집")
    return results


# ── 메인 수집 함수 ────────────────────────────────────────────────────────────

def collect_proprietary_data() -> dict:
    print("\n[독점 데이터 수집 시작 v2 — SIC 코드 기반]")

    data = {
        "sec_form_d": [],
        "arxiv": [],
        "doe_grants": [],
        "hiring_signals": [],
        "hn_launches": [],
        "patents": [],
        "ferc_filings": [],
        "collected_at": datetime.utcnow().isoformat(),
    }

    collectors = [
        ("sec_form_d",    fetch_sec_form_d_by_sic),
        ("arxiv",         fetch_arxiv_energy),
        ("doe_grants",    fetch_doe_arpa_rss),
        ("hiring_signals",fetch_hiring_signals),
        ("hn_launches",   fetch_hn_launches),
        ("patents",       fetch_energy_patents),
        ("ferc_filings",  fetch_ferc_filings),
    ]

    for key, fn in collectors:
        try:
            data[key] = fn()
        except Exception as e:
            print(f"  [{key}] 전체 실패: {e}")
            data[key] = []

    total = sum(len(v) for v in data.values() if isinstance(v, list))
    early = sum(
        1 for v in data.values() if isinstance(v, list)
        for item in v if item.get("is_early_stage")
    )
    print(f"[독점 데이터] 총 {total}개 신호 / Early Stage {early}개 수집 완료\n")
    return data


def format_proprietary_for_prompt(data: dict) -> str:
    lines = [
        "=== PROPRIETARY EARLY STAGE SIGNALS (v2) ===",
        "Sources: SEC Form D (SIC-based), arXiv, DOE/ARPA-E, Hiring, HN, USPTO",
        "Priority: SEED and SERIES_A stage deals for VC investment analysis.\n",
    ]

    sections = [
        ("sec_form_d",     "SEC FORM D — Private Rounds (SIC-filtered)"),
        ("arxiv",          "arXiv PAPERS — Pre-Seed Technology Signals"),
        ("doe_grants",     "DOE / ARPA-E GRANTS — Pre-Seed Funding"),
        ("hiring_signals", "HIRING SIGNALS — Series A Precursors"),
        ("hn_launches",    "HN LAUNCHES — Seed Stage Startups"),
        ("patents",        "USPTO PATENTS — Technical Moat Signals"),
        ("ferc_filings",   "REGULATORY FILINGS — Grid Infrastructure"),
    ]

    total_early = 0
    for key, label in sections:
        items = data.get(key, [])
        if not items:
            continue
        lines.append(f"── {label} ({len(items)}개) ──")
        for item in items[:5]:
            lines.append(f"• {item['signal']}")
            stage = item.get("deal_stage", "")
            if stage:
                lines.append(f"  Stage: {stage}")
            if item.get("is_academic"):
                lines.append(f"  → Academic spinout candidate")
            if item.get("is_senior_hire"):
                lines.append(f"  → Senior hire = Series A imminent")
            if item.get("is_early_stage"):
                total_early += 1
        lines.append("")

    lines.insert(3, f"Total early-stage signals: {total_early}\n")
    return "\n".join(lines) if len(lines) > 5 else "No proprietary signals collected."


if __name__ == "__main__":
    data = collect_proprietary_data()
    print(format_proprietary_for_prompt(data))


# ── 하이퍼스케일러 에너지 전용 수집 ─────────────────────────────────────────

HYPERSCALERS = {
    # ── 빅테크 하이퍼스케일러 ────────────────────────────────────────────
    "Microsoft": {
        "aliases": ["microsoft", "msft", "azure", "constellation crane", "three mile island", "helion"],
        "color": "#0078d4", "bg": "rgba(0,120,212,.15)", "group": "hyperscaler",
    },
    "Google": {
        "aliases": ["google", "alphabet", "deepmind", "intersect power", "kairos power", "google energy"],
        "color": "#ea4335", "bg": "rgba(234,67,53,.15)", "group": "hyperscaler",
    },
    "Amazon": {
        "aliases": ["amazon", "aws", "talen", "x-energy", "xe-100", "susquehanna", "amazon energy"],
        "color": "#ff9900", "bg": "rgba(255,153,0,.15)", "group": "hyperscaler",
    },
    "Meta": {
        "aliases": ["meta", "facebook", "constellation clinton", "noon energy", "vistra meta", "oklo meta"],
        "color": "#1877f2", "bg": "rgba(24,119,242,.15)", "group": "hyperscaler",
    },
    "Apple": {
        "aliases": ["apple", "apple energy", "apple data center renewable"],
        "color": "#555555", "bg": "rgba(85,85,85,.15)", "group": "hyperscaler",
    },
    "Oracle": {
        "aliases": ["oracle", "oracle cloud", "oracle data center power"],
        "color": "#ff0000", "bg": "rgba(255,0,0,.15)", "group": "hyperscaler",
    },
    "NVIDIA": {
        "aliases": ["nvidia", "jensen huang", "blackwell", "h100", "h200", "b200", "nvidia energy"],
        "color": "#76b900", "bg": "rgba(118,185,0,.15)", "group": "hyperscaler",
    },
    # ── 아시아 빅테크 ────────────────────────────────────────────────────
    "Samsung": {
        "aliases": ["samsung", "samsung sdi", "samsung ventures", "samsung next",
                    "samsung c&t", "gridbeyond", "amperon", "emerald ai"],
        "color": "#1428a0", "bg": "rgba(20,40,160,.15)", "group": "asia_tech",
    },
    "SK": {
        "aliases": ["sk on", "sk inc", "sk innovation", "sk e&s",
                    "bloom energy sk", "plug power sk", "sk hynix"],
        "color": "#e8001c", "bg": "rgba(232,0,28,.15)", "group": "asia_tech",
    },
    "SoftBank": {
        "aliases": ["softbank", "arm energy", "vision fund energy", "softbank energy"],
        "color": "#cc0000", "bg": "rgba(204,0,0,.15)", "group": "asia_tech",
    },
    # ── 글로벌 에너지 OEM / 인프라 ──────────────────────────────────────
    "GE Vernova": {
        "aliases": ["ge vernova", "general electric", "ge grid", "ge renewable",
                    "ge wind", "ge gas power", "vernova"],
        "color": "#00a3e0", "bg": "rgba(0,163,224,.15)", "group": "energy_oem",
    },
    "Siemens Energy": {
        "aliases": ["siemens energy", "siemens gamesa", "siemens grid",
                    "siemens offshore", "siemens power"],
        "color": "#009999", "bg": "rgba(0,153,153,.15)", "group": "energy_oem",
    },
    "ABB": {
        "aliases": ["abb", "abb electrification", "abb grid", "abb power",
                    "abb hvdc", "abb transformer"],
        "color": "#ff000f", "bg": "rgba(255,0,15,.15)", "group": "energy_oem",
    },
    "Schneider Electric": {
        "aliases": ["schneider electric", "schneider energy", "schneider grid",
                    "aveva", "schneider microgrid"],
        "color": "#3dcd58", "bg": "rgba(61,205,88,.15)", "group": "energy_oem",
    },
    "Eaton": {
        "aliases": ["eaton", "eaton electrical", "eaton power", "eaton grid"],
        "color": "#ffcc00", "bg": "rgba(255,204,0,.15)", "group": "energy_oem",
    },
    # ── 유틸리티 / 전력 기업 ────────────────────────────────────────────
    "Constellation": {
        "aliases": ["constellation energy", "constellation nuclear", "constellation brand"],
        "color": "#0057b8", "bg": "rgba(0,87,184,.15)", "group": "utility",
    },
    "NextEra": {
        "aliases": ["nextera", "nextera energy", "florida power", "nextera renewables"],
        "color": "#0072ce", "bg": "rgba(0,114,206,.15)", "group": "utility",
    },
    "Vistra": {
        "aliases": ["vistra", "vistra energy", "vistra nuclear", "vistra corp"],
        "color": "#7b2d8b", "bg": "rgba(123,45,139,.15)", "group": "utility",
    },
    "Fluence": {
        "aliases": ["fluence", "fluence energy", "fluence bess", "fluence storage"],
        "color": "#00b4d8", "bg": "rgba(0,180,216,.15)", "group": "energy_tech",
    },
}

ENERGY_DEAL_KEYWORDS = [
    "power", "energy", "nuclear", "solar", "wind", "bess", "battery",
    "storage", "ppa", "offtake", "grid", "transmission", "renewable",
    "hydrogen", "smr", "reactor", "electricity", "mw", "gw", "kwh",
    "clean energy", "carbon", "datacenter power", "data center power",
]


def fetch_hyperscaler_news() -> dict:
    """
    하이퍼스케일러별 최신 에너지 딜/투자 뉴스 수집
    SEC 8-K + RSS 소스 활용
    """
    import feedparser
    from datetime import datetime, timedelta

    results = {company: [] for company in HYPERSCALERS}

    # RSS 소스 — 하이퍼스케일러 에너지 딜 잘 잡는 곳
    rss_sources = [
        "https://www.utilitydive.com/feeds/news/",
        "https://www.datacenterdynamics.com/en/rss/",
        "https://www.datacenterfrontier.com/feed/",
        "https://canarymedia.com/feed",
        "https://heatmap.news/feed",
        "https://www.powermag.com/feed/",
        "https://www.energy-storage.news/feed/",
        "https://techcrunch.com/tag/energy/feed/",
        "https://www.rechargenews.com/rss",
        "https://electrek.co/feed/",
    ]

    cutoff = datetime.utcnow() - timedelta(days=60)  # 최근 60일

    for url in rss_sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                published = entry.get("published", "")[:10] if entry.get("published") else ""
                text = (title + " " + summary).lower()

                # 에너지 관련 확인
                if not any(k in text for k in ENERGY_DEAL_KEYWORDS):
                    continue

                # 하이퍼스케일러 매칭
                for company, info in HYPERSCALERS.items():
                    if any(alias in text for alias in info["aliases"]):
                        # 중복 제거
                        if any(e.get("title") == title for e in results[company]):
                            continue

                        # 딜 타입 분류
                        deal_type = "OTHER"
                        if any(k in text for k in ["acqui", "buy", "purchase", "m&a", "merger"]):
                            deal_type = "M&A"
                        elif any(k in text for k in ["ppa", "offtake", "contract", "agreement"]):
                            deal_type = "PPA"
                        elif any(k in text for k in ["invest", "fund", "round", "equity", "stake"]):
                            deal_type = "EQUITY"
                        elif any(k in text for k in ["partner", "deal", "sign"]):
                            deal_type = "PARTNERSHIP"

                        # 금액 추출
                        import re as _re
                        amounts = _re.findall(r"\$[\d,.]+\s*(?:billion|million|[BM])\b", title + " " + summary, _re.IGNORECASE)
                        amount = amounts[0] if amounts else ""

                        # MW/GW 추출
                        capacity = ""
                        cap_match = _re.findall(r"[\d,.]+\s*(?:GW|MW|GWh|MWh)\b", title + " " + summary, _re.IGNORECASE)
                        if cap_match:
                            capacity = cap_match[0]

                        results[company].append({
                            "title": title[:100],
                            "summary": summary[:300],
                            "link": link,
                            "published": published,
                            "deal_type": deal_type,
                            "amount": amount,
                            "capacity": capacity,
                            "source": feed.feed.get("title", url),
                        })
                        break  # 하나의 기사는 하나의 회사에만 매핑

        except Exception as e:
            print(f"  [Hyperscaler RSS/{url[:40]}] {e}")

    # 각 회사별 최신순 정렬, 상위 5개
    for company in results:
        results[company] = sorted(
            results[company],
            key=lambda x: x.get("published", ""),
            reverse=True
        )[:5]

    total = sum(len(v) for v in results.values())
    print(f"  [Hyperscaler] {total}개 latest deals collected")
    return results


def generate_hyperscaler_html(news_data: dict) -> str:
    """
    하이퍼스케일러 트래커 HTML 자동 생성
    최신 뉴스 + 하드코딩 핵심 딜 통합
    """
    from datetime import datetime

    # 하드코딩 핵심 딜 (검증된 실거래)
    VERIFIED_DEALS = {
        "Microsoft": [
            {"title": "Constellation / Three Mile Island 재가동 PPA", "amount": "~$110/MWh", "capacity": "835MW", "type": "NUCLEAR", "date": "Sep 2024", "note": "20yr PPA"},
            {"title": "Helion Energy 핵융합 투자", "amount": "$1.9B+", "capacity": "", "type": "EQUITY", "date": "2023–2024", "note": "선불 투자"},
        ],
        "Google": [
            {"title": "Intersect Power 인수 — 태양광+BESS 플랫폼", "amount": "$4.75B", "capacity": "3.6GW + 3.1GWh", "type": "M&A", "date": "Jan 2026", "note": "First hyperscaler direct asset acquisition"},
            {"title": "Kairos Power SMR 마스터 개발계약", "amount": "N/A", "capacity": "500MW", "type": "NUCLEAR", "date": "Oct 2024", "note": "COD 2030+"},
        ],
        "Amazon": [
            {"title": "Talen Energy Susquehanna 핵 오프테이크", "amount": "$18B", "capacity": "1,920MW", "type": "NUCLEAR", "date": "2025 재협상", "note": "17yr PPA ~$80/MWh"},
            {"title": "X-energy Cascade SMR 에쿼티 투자", "amount": "$500M", "capacity": "960MW", "type": "EQUITY", "date": "Oct 2025", "note": "Pre-FID"},
            {"title": "호주 9개 PPA — BESS 포함", "amount": "A$2.8B", "capacity": "430MW", "type": "PPA", "date": "2026", "note": "8/9 BESS 포함"},
        ],
        "Meta": [
            {"title": "Constellation Clinton 핵 PPA", "amount": "~$60–70/MWh", "capacity": "1,121MW", "type": "NUCLEAR", "date": "Jun 2025", "note": "20yr"},
            {"title": "Noon Energy LDES 100시간 배터리 예약", "amount": "N/A", "capacity": "1GW/100GWh", "type": "BESS", "date": "Apr 2026", "note": "TRL 6–7"},
            {"title": "Vistra / Oklo / TerraPower 핵 포트폴리오", "amount": "N/A", "capacity": "~5.5GW", "type": "NUCLEAR", "date": "2025–2026", "note": "최대 6.6GW 목표"},
        ],
        "NVIDIA": [
            {"title": "NVentures: Commonwealth Fusion Systems — SPARC tokamak fusion reactor", "amount": "$863M Series B2", "capacity": "N/A", "type": "EQUITY", "date": "Aug 2025",
             "note": "NVentures (NVIDIA CVC) · commercializing fusion energy · Google agreed to buy 200MW from ARC plant",
             "url": "https://www.cfs.energy/news-and-media/commonwealth-fusion-systems-raises-863-million-series-b2-round-to-accelerate-the-commercialization-of-fusion-energy"},
            {"title": "NVentures: Redwood Materials — battery recycling & AI DC energy storage", "amount": "$350M Series E", "capacity": "N/A", "type": "EQUITY", "date": "Oct 2025",
             "note": "NVentures strategic investment · JB Straubel (ex-Tesla CTO) · $6B valuation · US-built BESS for AI data centers",
             "url": "https://techcrunch.com/2025/10/23/redwood-materials-raises-another-350-million-to-power-up-its-energy-storage-business/"},
            {"title": "NVentures: Emerald AI — AI data center load flexibility platform", "amount": "$25M Strategic Round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026",
             "note": "NVentures + Samsung Ventures co-investment · EIP led · grid-interactive AI factories · NVIDIA Vera Rubin 96MW pilot",
             "url": "https://www.emeraldai.co/blog/sharing-our-strategic-expansion-round-emerald-ai-raises-25-million-to-transform-ai-data-centers-into-flexible-power-grid-assets"},
            {"title": "NVentures: TerraPower Natrium SMR — strategic co-investor", "amount": "Undisclosed", "capacity": "345MW", "type": "EQUITY", "date": "2022–2024",
             "note": "NVentures co-invested with SK Inc. · Bill Gates SMR · Wyoming · COD 2030",
             "url": "https://www.nventures.ai/"},
        ],
        "Samsung": [
            {"title": "Samsung Ventures: GridBeyond — AI grid optimization & DER trading", "amount": "€12M ($13.8M)", "capacity": "2.6GW+ managed", "type": "EQUITY", "date": "Mar 17, 2026",
             "note": "Samsung Ventures · Series D · alongside ABB, EIP, Constellation Ventures · UK/Ireland/US/Japan/Australia",
             "url": "https://gridbeyond.com/samsung-ventures-joins-gridbeyonds-shareholder-base-as-part-of-a-e12m-equity-investment/"},
            {"title": "Samsung Ventures: Amperon — AI energy forecasting (27 countries)", "amount": "Undisclosed", "capacity": "N/A", "type": "EQUITY", "date": "Jan 14, 2026",
             "note": "Samsung Ventures (NOT Samsung Next) · follows National Grid Partners & Acario (Tokyo Gas CVC) rounds",
             "url": "https://www.amperon.co/newsroom/amperon-secures-investment-from-samsung-ventures-to-advance-energy-forecasting-technology"},
            {"title": "Samsung Ventures + NVentures: Emerald AI — grid-flexible AI data centers", "amount": "$25M Strategic Round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 31, 2026",
             "note": "Co-invested with NVentures (NVIDIA) · EIP led · also Eaton, GE Vernova, Siemens, Lowercarbon · total $68M raised",
             "url": "https://www.emeraldai.co/blog/sharing-our-strategic-expansion-round-emerald-ai-raises-25-million-to-transform-ai-data-centers-into-flexible-power-grid-assets"},
            {"title": "Samsung SDI — BESS supply to Tesla, BMW, Ford, Rivian", "amount": "$2B+ capex", "capacity": "GWh-scale", "type": "BESS", "date": "2024–2026",
             "note": "Vertical integration: cell → pack → system · BlueOval SK JV with Ford",
             "url": "https://www.samsungsdi.com/"},
            {"title": "RE100 Declaration — 100% renewable by 2050", "amount": "N/A", "capacity": "N/A", "type": "RE100", "date": "2022",
             "note": "100% achieved at overseas operations (US, EU factories)",
             "url": "https://news.samsung.com/global/samsung-electronics-achieves-100-renewable-energy-at-all-its-sites-outside-of-korea"},
        ],
        "SK": [
            {"title": "Bloom Energy — SOFC fuel cell strategic equity stake", "amount": "$300M+", "capacity": "GW-scale pipeline", "type": "EQUITY", "date": "2021", "note": "SK Inc. · clean power for semiconductor fabs"},
            {"title": "Plug Power — hydrogen fuel cell & electrolyzer partnership", "amount": "$1.5B", "capacity": "1GW+ electrolyzer", "type": "EQUITY", "date": "2021", "note": "SK Inc. 9.9% stake · green hydrogen JV"},
            {"title": "TerraPower Natrium SMR — strategic investor", "amount": "Undisclosed", "capacity": "345MW", "type": "EQUITY", "date": "2022", "note": "SK Inc. · Bill Gates-founded SMR · COD 2030"},
            {"title": "SK On — US gigafactory renewable PPAs", "amount": "N/A", "capacity": "N/A", "type": "PPA", "date": "2024–2025", "note": "BlueOval SK (Ford JV) + Ultium Cells (GM JV)"},
            {"title": "SK E&S — LNG to hydrogen energy transition", "amount": "$3B+", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2023–2026", "note": "Clean ammonia, CCUS, hydrogen value chain"},
        ],
        "Apple": [
            {"title": "100% renewable operations — all global facilities", "amount": "N/A", "capacity": "N/A", "type": "RE100", "date": "2018", "note": "First Fortune 500 to achieve 100% renewable"},
            {"title": "Clean Energy Charging — grid demand response via iPhone", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2022", "note": "Largest demand response fleet globally"},
            {"title": "Apple Energy LLC — wholesale power seller license", "amount": "N/A", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2016", "note": "FERC-licensed wholesale power trader"},
        ],
        "Oracle": [
            {"title": "1.5GW nuclear PPA — unnamed US utility (multiple sites)", "amount": "Undisclosed", "capacity": "1.5GW", "type": "NUCLEAR", "date": "2024", "note": "Largest single corporate nuclear PPA to date"},
            {"title": "Data center power — 100+ GW buildout target by 2030", "amount": "$100B+", "capacity": "100GW+", "type": "PARTNERSHIP", "date": "2024–2030", "note": "Larry Ellison AI infrastructure push"},
        ],
        "SoftBank": [
            {"title": "Arm Holdings energy-efficient chip architecture", "amount": "N/A", "capacity": "N/A", "type": "EQUITY", "date": "2016–present", "note": "Power efficiency as AI DC competitive moat"},
            {"title": "SB Energy — 7GW US solar+storage development", "amount": "$1B+", "capacity": "7GW pipeline", "type": "BESS", "date": "2021–2024", "note": "US renewable development arm · sold assets to Hexagon"},
        ],
        "GE Vernova": [
            {"title": "Grid Solutions — HVDC & FACTS for AI DC interconnection", "amount": "$2B+ backlog", "capacity": "N/A", "type": "GRID TECH", "date": "2024–2026", "note": "EHV transformer 36-month backlog · key bottleneck"},
            {"title": "Haliade-X offshore wind turbine — 18MW", "amount": "N/A", "capacity": "18MW/unit", "type": "PARTNERSHIP", "date": "2024", "note": "Largest offshore turbine · GE Vernova spin-off"},
            {"title": "GE Vernova IPO — $35B market cap", "amount": "$35B mktcap", "capacity": "N/A", "type": "EQUITY", "date": "Apr 2024", "note": "Spun off from GE · grid + wind + gas power"},
            {"title": "Grid-forming inverter technology — AI DC stability", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2025", "note": "Critical for AI DC frequency response"},
        ],
        "Siemens Energy": [
            {"title": "Siemens Gamesa offshore wind — 14–15MW turbines", "amount": "€18B backlog", "capacity": "15MW/unit", "type": "PARTNERSHIP", "date": "2024–2026", "note": "Struggling with blade quality issues → delays"},
            {"title": "HVDC grid technology — NordLink, Viking Link", "amount": "€5B+", "capacity": "1.4GW each", "type": "GRID TECH", "date": "2023–2025", "note": "Intercontinental power transmission"},
            {"title": "Transformer capacity expansion — 20% ramp", "amount": "€500M capex", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2024–2026", "note": "Response to 36-month backlog crisis"},
        ],
        "ABB": [
            {"title": "ABB Electrification — EV charging & grid edge", "amount": "$3B revenue", "capacity": "N/A", "type": "GRID TECH", "date": "2024", "note": "Largest EV charger manufacturer globally"},
            {"title": "HVDC transformer supply — AI DC buildout critical path", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2024–2027", "note": "36-month lead time · IRR risk for hyperscalers"},
            {"title": "ABB Power Grids sale to Hitachi — strategic exit", "amount": "$11B", "capacity": "N/A", "type": "M&A", "date": "2020", "note": "Divested grid biz to Hitachi Energy"},
        ],
        "Schneider Electric": [
            {"title": "EcoStruxure microgrid for AI data centers", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2024–2025", "note": "AI-optimized microgrid control software"},
            {"title": "AVEVA acquisition — industrial energy management", "amount": "$11B", "capacity": "N/A", "type": "M&A", "date": "2023", "note": "Industrial IoT + energy management platform"},
            {"title": "Green Premium — sustainability product labeling", "amount": "N/A", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2021", "note": "Circular economy + energy efficiency initiative"},
        ],
        "Eaton": [
            {"title": "Power distribution for AI data centers — UPS/PDU", "amount": "$1.5B+ DC revenue", "capacity": "N/A", "type": "GRID TECH", "date": "2024–2026", "note": "Critical path for AI DC power delivery"},
            {"title": "eMobility — EV charging infrastructure", "amount": "$500M capex", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2023–2026", "note": "Grid-interactive EV charging"},
        ],
        "Constellation": [
            {"title": "Three Mile Island Unit 1 restart — Microsoft PPA", "amount": "$110/MWh est.", "capacity": "835MW", "type": "NUCLEAR", "date": "Sep 2024", "note": "First US nuclear restart for AI DC offtake"},
            {"title": "Clinton Power Station — Meta 20yr PPA", "amount": "$60–70/MWh est.", "capacity": "1,121MW", "type": "NUCLEAR", "date": "Jun 2025", "note": "20-year contract · Meta AI DC power"},
            {"title": "Calpine acquisition by Constellation", "amount": "$16.4B", "capacity": "26GW gas fleet", "type": "M&A", "date": "Jan 2025", "note": "Largest US power M&A — gas + nuclear portfolio"},
        ],
        "NextEra": [
            {"title": "NextEra Energy Resources — largest US renewable operator", "amount": "$10B+ capex/yr", "capacity": "35GW+ operating", "type": "BESS", "date": "2024–2026", "note": "BESS pipeline 20GW+ · #1 US wind+solar"},
            {"title": "AI DC power PPA portfolio — hyperscaler offtake", "amount": "Undisclosed", "capacity": "5GW+ pipeline", "type": "PPA", "date": "2024–2026", "note": "Primary renewable supplier to US hyperscalers"},
        ],
        "Vistra": [
            {"title": "Vistra Vision — 6.4GW nuclear fleet + battery", "amount": "N/A", "capacity": "6.4GW nuclear", "type": "NUCLEAR", "date": "2024–2026", "note": "Comanche Peak + Illinois nuclear · AI DC offtake"},
            {"title": "Energy Harbor acquisition", "amount": "$3.43B", "capacity": "4GW nuclear", "type": "M&A", "date": "Mar 2024", "note": "Added 4GW nuclear → now 6.4GW total"},
            {"title": "Vistra Zero — 7GW+ BESS pipeline", "amount": "$1B+ capex", "capacity": "7GW pipeline", "type": "BESS", "date": "2024–2027", "note": "Largest US utility BESS developer"},
        ],
        "Fluence": [
            {"title": "Fluence IQ — AI-powered BESS bidding platform", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2023–2025", "note": "Auto-bidding AI for BESS revenue optimization"},
            {"title": "Global BESS deployment — 15GW+ pipeline", "amount": "N/A", "capacity": "15GW+", "type": "BESS", "date": "2024–2026", "note": "Siemens+AES JV · leading BESS integrator"},
        ],
    }

    type_colors = {
        "NUCLEAR": ("#3b82f6", "rgba(59,130,246,.1)"),
        "M&A":     ("#a855f7", "rgba(168,85,247,.1)"),
        "PPA":     ("#ef4444", "rgba(239,68,68,.1)"),
        "EQUITY":  ("#f59e0b", "rgba(245,158,11,.1)"),
        "BESS":    ("#22c55e", "rgba(34,197,94,.1)"),
        "RE100":   ("#22c55e", "rgba(34,197,94,.1)"),
        "PARTNERSHIP": ("#5a5a7a", "rgba(90,90,122,.1)"),
        "OTHER":   ("#5a5a7a", "rgba(90,90,122,.1)"),
    }

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 회사 카드 생성 (group_html로 분류)
    total_new = 0
    for company, info in HYPERSCALERS.items():
        verified = VERIFIED_DEALS.get(company, [])
        latest = news_data.get(company, [])
        total_new += len(latest)

        # 검증된 딜 HTML
        verified_html = ""
        for d in verified:
            color, bg = type_colors.get(d["type"], ("#5a5a7a", "rgba(90,90,122,.1)"))
            verified_html += f"""
            <div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);">
              <div style="width:5px;height:5px;border-radius:50%;background:{color};flex-shrink:0;margin-top:5px;"></div>
              <div style="flex:1;">
                <div style="font-size:12px;font-weight:500;margin-bottom:3px;line-height:1.4;">{d['title']}</div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:3px;">
                  <span style="font-family:'IBM Plex Mono',monospace;font-size:7px;padding:1px 6px;border-radius:2px;background:{bg};color:{color};border:1px solid {color}44;">{d['type']}</span>
                  {f'<span style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e;">{d["amount"]}</span>' if d.get('amount') and d['amount'] != 'N/A' else ''}
                  {f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.4);">{d["capacity"]}</span>' if d.get('capacity') and d['capacity'] != 'N/A' else ''}
                  <span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.25);">{d.get('date','')}</span>
                </div>
                {f'<div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.3);margin-top:2px;">{d["note"]}</div>' if d.get('note') else ''}
              </div>
            </div>"""

        # 최신 뉴스 HTML
        latest_html = ""
        if latest:
            latest_html += '<div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(59,130,246,.1);">'
            latest_html += '<div style="font-family:IBM Plex Mono,monospace;font-size:8px;letter-spacing:.12em;color:rgba(59,130,246,.6);text-transform:uppercase;margin-bottom:8px;">■ Latest News</div>'
            for n in latest[:3]:
                color, bg = type_colors.get(n.get("deal_type","OTHER"), ("#5a5a7a","rgba(90,90,122,.1)"))
                latest_html += f"""
                <div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,.03);">
                  <a href="{n['link']}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;">
                    <div style="font-size:11px;color:rgba(232,232,240,.7);line-height:1.4;margin-bottom:3px;">{n['title'][:90]}...</div>
                    <div style="display:flex;gap:8px;">
                      <span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:{bg};color:{color};">{n['deal_type']}</span>
                      {f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:#22c55e;">{n["amount"]}</span>' if n.get('amount') else ''}
                      <span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">{n.get('published','')}</span>
                      <span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">{n.get('source','')[:20]}</span>
                    </div>
                  </a>
                </div>"""
            latest_html += "</div>"
        elif company not in ["NVIDIA"]:
            latest_html = '<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:rgba(232,232,240,.2);margin-top:10px;padding-top:10px;border-top:1px solid rgba(59,130,246,.08);">No new energy deals in last 60 days</div>'

        strategy_map = {
            "Microsoft":          "Nuclear offtake + SMR direct investment leader. $110/MWh sets market benchmark.",
            "Google":             "First hyperscaler to own assets directly. $4.75B Intersect Power = PPA → M&A shift.",
            "Amazon":             "Most diversified portfolio. PPA + equity ($500M X-energy) + $18B nuclear offtake.",
            "Meta":               "Nuclear-centric. Up to 6.6GW target. First hyperscaler commercial LDES contract.",
            "Apple":              "100% renewable since 2018. Clean Energy Charging = world's largest demand response fleet.",
            "Oracle":             "1.5GW nuclear PPA + $100B+ AI infrastructure buildout. Late but aggressive.",
            "NVIDIA":             "No direct energy M&A. B200 GPU 700W TDP — chip efficiency is the energy strategy.",
            "Samsung":            "AI grid software investor (GridBeyond, Amperon, Emerald AI) + BESS vertical integration.",
            "SK":                 "Bloom Energy $300M + Plug Power $1.5B + TerraPower SMR — diversified clean energy bets.",
            "SoftBank":           "SB Energy 7GW US solar+storage. Arm architecture as AI DC power efficiency moat.",
            "GE Vernova":         "$35B IPO Apr 2024. Grid bottleneck owner — transformer backlog is AI DC critical path.",
            "Siemens Energy":     "HVDC grid + offshore wind. Transformer capacity expansion 20% to address AI DC demand.",
            "ABB":                "HVDC transformer and EV charging. 36-month lead time = IRR risk for every hyperscaler.",
            "Schneider Electric": "EcoStruxure AI microgrid + AVEVA $11B. Dominant in AI DC power management software.",
            "Eaton":              "AI DC UPS/PDU critical infrastructure. $1.5B+ data center revenue growing 30%+ YoY.",
            "Constellation":      "TMI restart (MSFT) + Clinton (Meta) + Calpine $16.4B. America's nuclear AI power hub.",
            "NextEra":            "35GW+ operating. Primary renewable supplier to US hyperscalers. 20GW+ BESS pipeline.",
            "Vistra":             "6.4GW nuclear fleet + Energy Harbor $3.43B. Largest US nuclear+BESS platform.",
            "Fluence":            "Fluence IQ auto-bidding AI + 15GW+ BESS pipeline. Siemens+AES JV — BESS market leader.",
        }

        cards_html += f"""
        <div style="background:rgba(255,255,255,.02);border:1px solid rgba(59,130,246,.08);padding:24px;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
            <div style="width:36px;height:36px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:500;background:{info['bg']};color:{info['color']};">{company[:2].upper()}</div>
            <div>
              <div style="font-size:15px;font-weight:500;">{company}</div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(232,232,240,.35);margin-top:2px;">{strategy_map.get(company,'')}</div>
            </div>
            {f'<span style="margin-left:auto;font-family:IBM Plex Mono,monospace;font-size:8px;padding:2px 8px;border-radius:2px;background:rgba(59,130,246,.1);color:#3b82f6;">+{len(latest)} new</span>' if latest else ''}
          </div>
          <div style="padding-bottom:2px;">{verified_html}</div>
          {latest_html}
        </div>"""

    # 그룹별 분류
    group_html = {"hyperscaler": "", "asia_tech": "", "energy_oem": "", "utility": "", "energy_tech": ""}
    for company, info in HYPERSCALERS.items():
        # 위에서 만든 카드 찾기
        group = info.get("group", "utility")
        key = group if group in group_html else "utility"
        # 카드 재생성
        verified2 = VERIFIED_DEALS.get(company, [])
        latest2 = news_data.get(company, [])
        vhtml = ""
        for d in verified2:
            c2, b2 = type_colors.get(d["type"], ("#5a5a7a","rgba(90,90,122,.1)"))
            vhtml += (
                f'<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);">' +
                f'<div style="width:5px;height:5px;border-radius:50%;background:{c2};flex-shrink:0;margin-top:5px;"></div>' +
                f'<div style="flex:1;">' +
                f'<div style="font-size:12px;font-weight:500;margin-bottom:3px;line-height:1.4;">{d["title"]}</div>' +
                f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:3px;">' +
                f'<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 6px;border-radius:2px;background:{b2};color:{c2};border:1px solid {c2}44;">{d["type"]}</span>' +
                (f'<span style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e;">{d["amount"]}</span>' if d.get("amount") and d["amount"] != "N/A" else "") +
                (f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.4);">{d["capacity"]}</span>' if d.get("capacity") and d["capacity"] not in ("N/A","") else "") +
                f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.25);">{d.get("date","")}</span>' +
                '</div>' +
                (f'<div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.3);margin-top:2px;">{d["note"]}</div>' if d.get("note") else "") +
                '</div></div>'
            )
        lhtml = ""
        if latest2:
            lhtml = '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(59,130,246,.1);"><div style="font-family:IBM Plex Mono,monospace;font-size:8px;letter-spacing:.12em;color:rgba(59,130,246,.6);text-transform:uppercase;margin-bottom:6px;">■ Latest News</div>'
            for n2 in latest2[:3]:
                c2, b2 = type_colors.get(n2.get("deal_type","OTHER"),("#5a5a7a","rgba(90,90,122,.1)"))
                lhtml += (
                    f'<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.03);">' +
                    f'<a href="{n2["link"]}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;">' +
                    f'<div style="font-size:11px;color:rgba(232,232,240,.7);line-height:1.4;margin-bottom:2px;">{n2["title"][:85]}...</div>' +
                    f'<div style="display:flex;gap:6px;"><span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:{b2};color:{c2};">{n2["deal_type"]}</span>' +
                    (f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:#22c55e;">{n2["amount"]}</span>' if n2.get("amount") else "") +
                    f'<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">{n2.get("published","")}</span></div>' +
                    '</a></div>'
                )
            lhtml += '</div>'
        strat = strategy_map.get(company, "")
        badge = f'<span style="margin-left:auto;font-family:IBM Plex Mono,monospace;font-size:8px;padding:2px 8px;border-radius:2px;background:rgba(59,130,246,.1);color:#3b82f6;">+{len(latest2)} new</span>' if latest2 else ""
        card = (
            f'<div style="background:rgba(255,255,255,.02);border:1px solid rgba(59,130,246,.08);padding:20px;">' +
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
            f'<div style="width:32px;height:32px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-family:IBM Plex Mono,monospace;font-size:10px;font-weight:500;background:{info["bg"]};color:{info["color"]};flex-shrink:0;">{company[:2].upper()}</div>' +
            f'<div style="flex:1;min-width:0;">' +
            f'<div style="font-size:14px;font-weight:500;">{company}</div>' +
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.3);margin-top:1px;line-height:1.4;">{strat}</div>' +
            f'</div>{badge}</div>' +
            vhtml + lhtml +
            '</div>'
        )
        group_html[key] += card

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GRIDEDGE — Hyperscaler Energy Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@300;400;500&family=Geist:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#050507;--white:#e8e8f0;--dim:#5a5a7a;--blue:#3b82f6;--border:rgba(59,130,246,0.08);--card:rgba(255,255,255,0.02);}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--white);font-family:'Geist',sans-serif;min-height:100vh;}}
body::before{{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(59,130,246,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,0.03) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0;}}
nav{{position:sticky;top:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:14px 32px;background:rgba(5,5,7,0.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);}}
.logo{{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:500;letter-spacing:0.2em;color:var(--blue);text-decoration:none;}}
.logo em{{color:var(--white);opacity:0.3;font-style:normal;}}
.nav-r{{display:flex;align-items:center;gap:20px;font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:0.12em;color:var(--dim);text-transform:uppercase;}}
.nav-r a{{color:var(--dim);text-decoration:none;transition:color .2s;}}
.nav-r a:hover,.nav-r a.active{{color:var(--blue);}}
.wrap{{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:48px 32px;}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}}
.grid-3{{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:20px;}}
@media(max-width:1100px){{.grid-2,.grid-3{{grid-template-columns:1fr;}}}}
@media(max-width:768px){{.wrap{{padding:24px 16px;}}.nav-r{{display:none;}}}}
</style>
</head>
<body>
<nav>
  <a class="logo" href="./index.html">GRID<em>/</em>EDGE</a>
  <div class="nav-r">
    <a href="./index.html">Home</a>
    <a href="./brief_latest.html">Latest Brief</a>
    <a href="./dashboard.html">Dashboard</a>
    <a href="./hyperscaler.html" class="active">Hyperscalers</a>
    <a href="./archive.html">Archive</a>
  </div>
</nav>

<div class="wrap">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.25em;color:var(--blue);text-transform:uppercase;margin-bottom:12px;">Intelligence Layer</div>
  <h1 style="font-family:'Instrument Serif',serif;font-size:clamp(28px,3.5vw,48px);line-height:1.05;margin-bottom:8px;">Hyperscaler Energy Tracker</h1>
  <p style="font-size:13px;color:var(--dim);line-height:1.7;max-width:600px;margin-bottom:4px;">Big Tech의 에너지 M&A/PPA/직접투자 실시간 추적. 이들의 움직임이 다음 딜을 만든다.</p>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(232,232,240,.2);margin-bottom:32px;">
    Auto-updated: {updated} · Verified deals + last 60 days news · {total_new}개 latest news collected
  </div>

  <!-- 요약 메트릭 -->
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:32px;">
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Total Committed</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$40B+</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Big 4 energy capex 2024–2026</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Nuclear Offtake</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">5.8 GW</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">MSFT+Amazon+Meta signed PPAs</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Avg Nuclear Price</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$90/MWh</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">vs $40 spot · 2× premium</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Largest M&A</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$4.75B</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Google → Intersect Power</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Latest News</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">{total_new}</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Energy deal news, last 60 days</div>
    </div>
  </div>

  <!-- Company card 2-column grid -->
  <div class="grid-2">
    {cards_html}
  </div>

</div>
</body>
</html>"""

    return html

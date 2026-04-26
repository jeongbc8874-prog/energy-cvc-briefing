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

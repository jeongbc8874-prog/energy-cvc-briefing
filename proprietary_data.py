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
    "Microsoft": {
        "aliases": ["microsoft", "msft", "azure", "constellation crane", "three mile island"],
        "color": "#0078d4", "bg": "rgba(0,120,212,.15)",
    },
    "Google": {
        "aliases": ["google", "alphabet", "deepmind", "intersect power", "kairos power"],
        "color": "#ea4335", "bg": "rgba(234,67,53,.15)",
    },
    "Amazon": {
        "aliases": ["amazon", "aws", "talen", "x-energy", "xe-100", "susquehanna"],
        "color": "#ff9900", "bg": "rgba(255,153,0,.15)",
    },
    "Meta": {
        "aliases": ["meta", "facebook", "constellation clinton", "noon energy", "vistra", "oklo", "terrapower"],
        "color": "#1877f2", "bg": "rgba(24,119,242,.15)",
    },
    "NVIDIA": {
        "aliases": ["nvidia", "jensen huang", "blackwell", "h100", "h200", "b200"],
        "color": "#76b900", "bg": "rgba(118,185,0,.15)",
    },
    "Samsung": {
        "aliases": ["samsung", "삼성", "samsung sdi", "samsung c&t"],
        "color": "#1428a0", "bg": "rgba(20,40,160,.15)",
    },
    "SK": {
        "aliases": ["sk on", "sk hynix", "sk innovation", "sk텔레콤"],
        "color": "#e8001c", "bg": "rgba(232,0,28,.15)",
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
    print(f"  [Hyperscaler] {total}개 최신 딜 수집 완료")
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
            {"title": "Intersect Power 인수 — 태양광+BESS 플랫폼", "amount": "$4.75B", "capacity": "3.6GW + 3.1GWh", "type": "M&A", "date": "Jan 2026", "note": "하이퍼스케일러 최초 자산 직접 인수"},
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
        "NVIDIA": [],
        "Samsung": [
            {"title": "RE100 2050 목표 선언", "amount": "N/A", "capacity": "N/A", "type": "RE100", "date": "2022", "note": "해외 사업장 100% 달성"},
        ],
        "SK": [
            {"title": "SK On 미국 배터리 공장 재생에너지 PPA", "amount": "N/A", "capacity": "N/A", "type": "PPA", "date": "2024–2025", "note": ""},
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

    # 회사 카드 생성
    cards_html = ""
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
            "Microsoft": "핵 오프테이크 + SMR 직접투자 선도. $110/MWh 벤치마크 설정.",
            "Google": "하이퍼스케일러 최초 자산 직접 소유 전환. PPA → M&A 패러다임 전환.",
            "Amazon": "가장 다각화된 에너지 포트폴리오. PPA + 에쿼티 + SMR 병행.",
            "Meta": "핵 중심 최대 6.6GW 목표. LDES 첫 상업계약.",
            "NVIDIA": "직접 에너지 투자 없음. 칩 효율로 per-query 에너지 감소.",
            "Samsung": "RE100 이행 + 배터리 공급망 수직통합.",
            "SK": "SK On 배터리 공장 재생에너지 직접 조달.",
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
    자동 업데이트: {updated} · 검증 딜 + 최근 60일 뉴스 통합 · {total_new}개 최신 뉴스 수집
  </div>

  <!-- 요약 메트릭 -->
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:32px;">
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Total Committed</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$40B+</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Big 4 에너지 캐펙스 2024–2026</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Nuclear Offtake</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">5.8 GW</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">MSFT+Amazon+Meta 서명 PPA</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Avg Nuclear Price</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$90/MWh</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">vs $40 spot · 2× 프리미엄</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Largest M&A</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$4.75B</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Google → Intersect Power</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Latest News</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">{total_new}</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">최근 60일 에너지 딜 뉴스</div>
    </div>
  </div>

  <!-- 회사 카드 2열 그리드 -->
  <div class="grid-2">
    {cards_html}
  </div>

</div>
</body>
</html>"""

    return html

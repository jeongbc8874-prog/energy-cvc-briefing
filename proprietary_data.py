"""
GRIDEDGE Proprietary Data Collection v2
Early Stage """

import requests
import json
import re
import time
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "GRIDEDGE Intelligence gridedge.intel@gmail.com"}

# ── energy related SIC code ──────────────────────────────────────────────────────
# Form D has no keyword search → filter by SIC code
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


# ── 1. SEC Form D — SIC code based ─────────────────────────────────────────────

def fetch_sec_form_d_by_sic() -> list:
    """
    SIC """
    results = []
    start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Priority SIC codes only (prevent API overload)
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
                    # Estimate stage from amount
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

    # Fallback: text search for energy keywords
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

    print(f"  [SEC Form D] {len(results)} collected")
    return results


# ── 2. arXiv energy papers → startup founding 6-18months 전 signal ─────────────────────────────

def fetch_arxiv_energy() -> list:
    """
    arXiv """
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

                # Investment keyword check
                text = (title_text + " " + summary_text).lower()
                if not any(k in text for k in ENERGY_KEYWORDS):
                    continue

                # Commercialization potential signals
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

    # Sort by commercial potential
    results.sort(key=lambda x: x.get("commercial_score", 0), reverse=True)
    print(f"  [arXiv] {len(results)} papers collected")
    return results


# ── 3. ARPA-E / DOE RSS — stable version ────────────────────────────────────────

def fetch_doe_arpa_rss() -> list:
    """
    ARPA-E + DOE """
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

                    # Energy-related + funding signals
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                    funding_signals = ["award", "grant", "million", "funding",
                                       "selects", "announces", "$", "prize"]
                    is_funding = any(s in text for s in funding_signals)

                    # Extract amount
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
        print("  [DOE/ARPA-E] feedparser not found")

    print(f"  [DOE/ARPA-E] {len(results)} collected")
    return results


# ── 4. hiring signal — startup detection ─────────────────────────────────────────────

def fetch_hiring_signals() -> list:
    """
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

                    # Check energy relevance
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                    # Remove duplicate companies
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
        print("  [Hiring] feedparser not found")

    print(f"  [Hiring Signals] {len(results)} collected")
    return results


# ── 5. Hacker News "Show HN" — stealth launch ───────────────────────────────────

def fetch_hn_launches() -> list:
    """
    Hacker News Show HN = """
    results = []
    try:
        import feedparser
        feed = feedparser.parse("https://news.ycombinator.com/rss")

        for entry in feed.entries[:50]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            text = title.lower()

            # Show HN or Ask HN: we created 것
            is_show = (
                text.startswith("show hn") or
                text.startswith("ask hn") or
                "launch" in text or
                "we built" in text or
                "i built" in text
            )

            if not is_show:
                continue

            # 엄격한 에너지 전용 키워드 — "power" 같은 모호한 단어 제외
            STRICT_ENERGY = [
                "energy storage", "battery", "bess", "grid", "solar", "wind",
                "nuclear", "hydrogen", "electrolyzer", "fuel cell", "microgrid",
                "inverter", "data center power", "ai power", "grid software",
                "demand response", "virtual power plant", "transmission",
                "interconnection", "clean energy", "renewable",
            ]
            if not any(k in text for k in STRICT_ENERGY):
                continue

            # 명백한 노이즈 제거
            NOISE_SIGNALS = [
                "bluetooth", "midi", "game", "gaming", "music", "audio",
                "app store", "ios", "android", "saas pricing", "chatbot",
                "llm", "ai assistant", "writing", "productivity", "marketing",
            ]
            if any(k in text for k in NOISE_SIGNALS):
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

    print(f"  [HN Launches] {len(results)} collected")
    return results


# ── 6. USPTO patent — technology Moat early detection ─────────────────────────────────────

def fetch_energy_patents() -> list:
    """
    USPTO """
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

                # university/institute = spinout potential high
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

    print(f"  [Patents] {len(results)} collected")
    return results


# ── 7. FERC filing ──────────────────────────────────────────────────────────────

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

    print(f"  [FERC/SEC] {len(results)} collected")
    return results


# ── main collected function ────────────────────────────────────────────────────────────

def collect_proprietary_data() -> dict:
    print("\n[Proprietary data collection v2 — SIC code based]")

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
            print(f"  [{key}] total failure: {e}")
            data[key] = []

    total = sum(len(v) for v in data.values() if isinstance(v, list))
    early = sum(
        1 for v in data.values() if isinstance(v, list)
        for item in v if item.get("is_early_stage")
    )
    print(f"[Proprietary data] Total {total} signals / Early Stage {early} collected\n")
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


# ── hyperscaler energy dedicated collected ─────────────────────────────────────────

HYPERSCALERS = {
    # ── big tech hyperscaler ────────────────────────────────────────────
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
    # ── Asia Tech ────────────────────────────────────────────────────
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
    # ── Global Energy OEM / Infrastructure ──────────────────────────────────────
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
    # ── Utilities / Power Companies ────────────────────────────────────────────
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
    """
    import feedparser
    from datetime import datetime, timedelta

    results = {company: [] for company in HYPERSCALERS}

    # RSS sources good for hyperscaler energy deals
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

    cutoff = datetime.utcnow() - timedelta(days=60)  # Last 60 days

    for url in rss_sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                published = entry.get("published", "")[:10] if entry.get("published") else ""
                text = (title + " " + summary).lower()

                # Check energy relevance
                if not any(k in text for k in ENERGY_DEAL_KEYWORDS):
                    continue

                # Match hyperscaler
                for company, info in HYPERSCALERS.items():
                    if any(alias in text for alias in info["aliases"]):
                        # Dedup
                        if any(e.get("title") == title for e in results[company]):
                            continue

                        # Classify deal type
                        deal_type = "OTHER"
                        if any(k in text for k in ["acqui", "buy", "purchase", "m&a", "merger"]):
                            deal_type = "M&A"
                        elif any(k in text for k in ["ppa", "offtake", "contract", "agreement"]):
                            deal_type = "PPA"
                        elif any(k in text for k in ["invest", "fund", "round", "equity", "stake"]):
                            deal_type = "EQUITY"
                        elif any(k in text for k in ["partner", "deal", "sign"]):
                            deal_type = "PARTNERSHIP"

                        # Extract amount
                        import re as _re
                        amounts = _re.findall(r"\$[\d,.]+\s*(?:billion|million|[BM])\b", title + " " + summary, _re.IGNORECASE)
                        amount = amounts[0] if amounts else ""

                        # Extract MW/GW capacity
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
                        break  # single articles single to one company only mapping

        except Exception as e:
            print(f"  [Hyperscaler RSS/{url[:40]}] {e}")

    # Sort by date desc, top 5 per company
    for company in results:
        results[company] = sorted(
            results[company],
            key=lambda x: x.get("published", ""),
            reverse=True
        )[:5]

    total = sum(len(v) for v in results.values())
    print(f"  [Hyperscaler] {total} latest deals collected")
    return results


def generate_hyperscaler_html(news_data: dict) -> str:
    """Auto-generate Hyperscaler Energy Tracker HTML with verified deals + latest news."""
    from datetime import datetime

    VERIFIED_DEALS = {
        "Microsoft": [
            {"title": "Constellation / Three Mile Island Restart PPA", "amount": "~$110/MWh", "capacity": "835MW", "type": "NUCLEAR", "date": "Sep 2024", "note": "20yr PPA · sets nuclear offtake benchmark", "url": "https://www.constellation.com/"},
            {"title": "Helion Energy — Nuclear Fusion Investment", "amount": "$1.9B+", "capacity": "", "type": "EQUITY", "date": "2023-2024", "note": "Prepaid fusion energy investment", "url": "https://www.helionenergy.com/"},
        ],
        "Google": [
            {"title": "Intersect Power Acquisition — Solar+BESS Platform", "amount": "$4.75B", "capacity": "3.6GW + 3.1GWh", "type": "M&A", "date": "Jan 2026", "note": "First hyperscaler direct asset acquisition", "url": "https://www.intersectpower.com/"},
            {"title": "Kairos Power SMR Master Development Agreement", "amount": "N/A", "capacity": "500MW", "type": "NUCLEAR", "date": "Oct 2024", "note": "COD 2030+", "url": "https://kairospower.com/"},
        ],
        "Amazon": [
            {"title": "Talen Energy Susquehanna Nuclear Offtake", "amount": "$18B", "capacity": "1,920MW", "type": "NUCLEAR", "date": "2025 renegotiated", "note": "17yr PPA ~$80/MWh", "url": "https://www.talenergy.com/"},
            {"title": "X-energy Cascade SMR Equity Investment", "amount": "$500M", "capacity": "960MW", "type": "EQUITY", "date": "Oct 2025", "note": "Pre-FID · COD 2030+", "url": "https://x-energy.com/"},
            {"title": "Australia 9 PPAs — BESS Included", "amount": "A$2.8B", "capacity": "430MW", "type": "PPA", "date": "2026", "note": "8/9 with co-located BESS", "url": ""},
        ],
        "Meta": [
            {"title": "Constellation Clinton Nuclear PPA", "amount": "~$60-70/MWh", "capacity": "1,121MW", "type": "NUCLEAR", "date": "Jun 2025", "note": "20yr", "url": "https://www.constellation.com/"},
            {"title": "Noon Energy LDES 100-hour Battery Reservation", "amount": "N/A", "capacity": "1GW / 100GWh", "type": "BESS", "date": "Apr 2026", "note": "TRL 6-7 · first hyperscaler commercial LDES contract", "url": "https://www.noon.energy/"},
            {"title": "Vistra / Oklo / TerraPower Nuclear Portfolio", "amount": "N/A", "capacity": "~5.5GW", "type": "NUCLEAR", "date": "2025-2026", "note": "Up to 6.6GW target", "url": ""},
        ],
        "Apple": [
            {"title": "100% Renewable Operations — All Global Facilities", "amount": "N/A", "capacity": "N/A", "type": "RE100", "date": "2018", "note": "First Fortune 500 to achieve 100% renewable", "url": "https://www.apple.com/environment/"},
            {"title": "Clean Energy Charging — Grid Demand Response via iPhone", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2022", "note": "World's largest demand response fleet", "url": ""},
            {"title": "Apple Energy LLC — FERC Wholesale Power Seller License", "amount": "N/A", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2016", "note": "FERC-licensed wholesale power trader", "url": ""},
        ],
        "Oracle": [
            {"title": "1.5GW Nuclear PPA — Multiple US Sites", "amount": "Undisclosed", "capacity": "1.5GW", "type": "NUCLEAR", "date": "2024", "note": "Largest single corporate nuclear PPA to date", "url": ""},
            {"title": "AI Infrastructure Buildout — 100GW Target by 2030", "amount": "$100B+", "capacity": "100GW+", "type": "PARTNERSHIP", "date": "2024-2030", "note": "Larry Ellison AI infrastructure push", "url": ""},
        ],
        "NVIDIA": [
            {"title": "NVentures: Commonwealth Fusion Systems (SPARC Tokamak)", "amount": "$863M Series B2", "capacity": "N/A", "type": "EQUITY", "date": "Aug 2025", "note": "NVentures (NVIDIA CVC) · fusion energy · Google agreed to buy 200MW from ARC plant", "url": "https://www.cfs.energy/"},
            {"title": "NVentures: Redwood Materials — Battery Recycling & AI DC Storage", "amount": "$350M Series E", "capacity": "N/A", "type": "EQUITY", "date": "Oct 2025", "note": "NVentures strategic investment · JB Straubel (ex-Tesla CTO) · $6B valuation", "url": "https://www.redwoodmaterials.com/"},
            {"title": "NVentures: Emerald AI — Grid-Flexible AI Data Centers", "amount": "$25M Strategic Round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026", "note": "NVentures + Samsung Ventures co-investment · EIP led · NVIDIA Vera Rubin 96MW pilot", "url": "https://www.emeraldai.co/"},
            {"title": "NVentures: TerraPower Natrium SMR", "amount": "Undisclosed", "capacity": "345MW", "type": "EQUITY", "date": "2022-2024", "note": "NVentures co-invested with SK Inc. · Wyoming · COD 2030", "url": "https://www.terrapower.com/"},
        ],
        "Samsung": [
            {"title": "Samsung Ventures: GridBeyond — AI Grid Optimization & DER Trading", "amount": "€12M ($13.8M)", "capacity": "2.6GW+ managed", "type": "EQUITY", "date": "Mar 17, 2026", "note": "Samsung Ventures · Series D · alongside ABB, EIP, Constellation Ventures", "url": "https://gridbeyond.com/samsung-ventures-joins-gridbeyonds-shareholder-base-as-part-of-a-e12m-equity-investment/"},
            {"title": "Samsung Ventures: Amperon — AI Energy Forecasting (27 Countries)", "amount": "Undisclosed", "capacity": "N/A", "type": "EQUITY", "date": "Jan 14, 2026", "note": "Samsung Ventures (NOT Samsung Next) · follows National Grid Partners & Acario rounds", "url": "https://www.amperon.co/newsroom/amperon-secures-investment-from-samsung-ventures-to-advance-energy-forecasting-technology"},
            {"title": "Samsung Ventures + NVentures: Emerald AI — Grid-Flexible AI DC", "amount": "$25M Strategic Round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 31, 2026", "note": "Co-invested with NVentures (NVIDIA) · EIP led · Eaton, GE Vernova, Siemens, Lowercarbon", "url": "https://www.emeraldai.co/"},
            {"title": "Samsung SDI — BESS Supply to Tesla, BMW, Ford, Rivian", "amount": "$2B+ capex", "capacity": "GWh-scale", "type": "BESS", "date": "2024-2026", "note": "Vertical integration: cell to pack to system · BlueOval SK JV with Ford", "url": "https://www.samsungsdi.com/"},
            {"title": "RE100 Declaration — 100% Renewable by 2050", "amount": "N/A", "capacity": "N/A", "type": "RE100", "date": "2022", "note": "100% achieved at overseas operations (US, EU factories)", "url": ""},
        ],
        "SK": [
            {"title": "Bloom Energy — SOFC Fuel Cell Strategic Equity Stake", "amount": "$300M+", "capacity": "GW-scale pipeline", "type": "EQUITY", "date": "2021", "note": "SK Inc. · clean power for semiconductor fabs", "url": "https://www.bloomenergy.com/"},
            {"title": "Plug Power — Hydrogen Fuel Cell & Electrolyzer Partnership", "amount": "$1.5B", "capacity": "1GW+ electrolyzer", "type": "EQUITY", "date": "2021", "note": "SK Inc. 9.9% stake · green hydrogen JV", "url": "https://www.plugpower.com/"},
            {"title": "TerraPower Natrium SMR — Strategic Investor", "amount": "Undisclosed", "capacity": "345MW", "type": "EQUITY", "date": "2022", "note": "SK Inc. · Bill Gates SMR · Wyoming · COD 2030", "url": "https://www.terrapower.com/"},
            {"title": "SK On — US Gigafactory Renewable PPAs", "amount": "N/A", "capacity": "N/A", "type": "PPA", "date": "2024-2025", "note": "BlueOval SK (Ford JV) + Ultium Cells (GM JV)", "url": ""},
            {"title": "SK E&S — LNG to Hydrogen Energy Transition", "amount": "$3B+", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2023-2026", "note": "Clean ammonia, CCUS, hydrogen value chain", "url": ""},
        ],
        "SoftBank": [
            {"title": "SB Energy — 7GW US Solar+Storage Development", "amount": "$1B+", "capacity": "7GW pipeline", "type": "BESS", "date": "2021-2024", "note": "US renewable development arm", "url": ""},
            {"title": "Arm Holdings — Energy-Efficient Chip Architecture", "amount": "N/A", "capacity": "N/A", "type": "EQUITY", "date": "2016-present", "note": "Power efficiency as AI DC competitive moat", "url": "https://www.arm.com/"},
        ],
        "GE Vernova": [
            {"title": "GE Vernova IPO — Grid + Wind + Gas Power Platform", "amount": "$35B mktcap", "capacity": "N/A", "type": "EQUITY", "date": "Apr 2024", "note": "Spun off from GE · NYSE: GEV", "url": "https://www.gevernova.com/"},
            {"title": "Grid Solutions — HVDC & FACTS for AI DC Interconnection", "amount": "$2B+ backlog", "capacity": "N/A", "type": "GRID TECH", "date": "2024-2026", "note": "EHV transformer 36-month backlog · AI DC critical path", "url": "https://www.gevernova.com/grid-solutions"},
            {"title": "NVentures + GE Vernova: Emerald AI Strategic Investor", "amount": "$25M round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026", "note": "GE Vernova invested alongside NVIDIA & Samsung Ventures", "url": "https://www.emeraldai.co/"},
            {"title": "Grid-Forming Inverter Technology — AI DC Frequency Stability", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2025", "note": "Critical for AI DC ancillary services", "url": ""},
        ],
        "Siemens Energy": [
            {"title": "Siemens Gamesa Offshore Wind — 14-15MW Turbines", "amount": "€18B backlog", "capacity": "15MW/unit", "type": "PARTNERSHIP", "date": "2024-2026", "note": "Blade quality issues causing delays", "url": "https://www.siemens-gamesa.com/"},
            {"title": "HVDC Grid Technology — NordLink, Viking Link", "amount": "€5B+", "capacity": "1.4GW each", "type": "GRID TECH", "date": "2023-2025", "note": "Intercontinental power transmission", "url": "https://www.siemens-energy.com/"},
            {"title": "Siemens Energy + Emerald AI: Strategic Investor", "amount": "$25M round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026", "note": "Co-invested in Emerald AI alongside NVIDIA & Samsung Ventures", "url": "https://www.emeraldai.co/"},
            {"title": "Transformer Capacity Expansion — 20% Ramp", "amount": "€500M capex", "capacity": "N/A", "type": "PARTNERSHIP", "date": "2024-2026", "note": "Response to 36-month backlog crisis", "url": ""},
        ],
        "ABB": [
            {"title": "ABB Electrification — EV Charging & Grid Edge", "amount": "$3B revenue", "capacity": "N/A", "type": "GRID TECH", "date": "2024", "note": "Largest EV charger manufacturer globally", "url": "https://www.abb.com/"},
            {"title": "HVDC Transformer Supply — AI DC Buildout Critical Path", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2024-2027", "note": "36-month lead time · IRR risk for all hyperscalers", "url": ""},
            {"title": "ABB + GridBeyond: Existing Investor in Series D Round", "amount": "€12M round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026", "note": "ABB continued investment alongside Samsung Ventures", "url": "https://gridbeyond.com/"},
        ],
        "Schneider Electric": [
            {"title": "EcoStruxure Microgrid for AI Data Centers", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2024-2025", "note": "AI-optimized microgrid control software", "url": "https://www.se.com/"},
            {"title": "AVEVA Acquisition — Industrial Energy Management", "amount": "$11B", "capacity": "N/A", "type": "M&A", "date": "2023", "note": "Industrial IoT + energy management platform", "url": "https://www.aveva.com/"},
        ],
        "Eaton": [
            {"title": "Power Distribution for AI Data Centers — UPS/PDU", "amount": "$1.5B+ DC revenue", "capacity": "N/A", "type": "GRID TECH", "date": "2024-2026", "note": "Critical path for AI DC power delivery · 30%+ YoY growth", "url": "https://www.eaton.com/"},
            {"title": "Eaton + Emerald AI: Strategic Investor", "amount": "$25M round", "capacity": "N/A", "type": "EQUITY", "date": "Mar 2026", "note": "Strategic investment in grid-flexible AI DC platform", "url": "https://www.emeraldai.co/"},
        ],
        "Constellation": [
            {"title": "Three Mile Island Unit 1 Restart — Microsoft PPA", "amount": "~$110/MWh", "capacity": "835MW", "type": "NUCLEAR", "date": "Sep 2024", "note": "20-year contract · first US nuclear restart for AI DC", "url": "https://www.constellation.com/"},
            {"title": "Clinton Power Station — Meta 20yr PPA", "amount": "~$60-70/MWh", "capacity": "1,121MW", "type": "NUCLEAR", "date": "Jun 2025", "note": "20-year contract · Meta AI DC power", "url": "https://www.constellation.com/"},
            {"title": "Calpine Acquisition", "amount": "$16.4B", "capacity": "26GW gas fleet", "type": "M&A", "date": "Jan 2025", "note": "Largest US power M&A · gas + nuclear portfolio", "url": ""},
        ],
        "NextEra": [
            {"title": "NextEra Energy Resources — Largest US Renewable Operator", "amount": "$10B+ capex/yr", "capacity": "35GW+ operating", "type": "BESS", "date": "2024-2026", "note": "20GW+ BESS pipeline · #1 US wind+solar", "url": "https://www.nexteraenergy.com/"},
            {"title": "Hyperscaler AI DC Power PPA Portfolio", "amount": "Undisclosed", "capacity": "5GW+ pipeline", "type": "PPA", "date": "2024-2026", "note": "Primary renewable supplier to US hyperscalers", "url": ""},
        ],
        "Vistra": [
            {"title": "Energy Harbor Acquisition — 4GW Nuclear Addition", "amount": "$3.43B", "capacity": "4GW nuclear", "type": "M&A", "date": "Mar 2024", "note": "Now 6.4GW total nuclear fleet", "url": "https://www.vistracorp.com/"},
            {"title": "Vistra Zero — 7GW+ BESS Pipeline", "amount": "$1B+ capex", "capacity": "7GW pipeline", "type": "BESS", "date": "2024-2027", "note": "Largest US utility BESS developer", "url": ""},
        ],
        "Fluence": [
            {"title": "Fluence IQ — AI-Powered BESS Auto-Bidding Platform", "amount": "N/A", "capacity": "N/A", "type": "GRID TECH", "date": "2023-2025", "note": "AI auto-bidding for BESS revenue optimization", "url": "https://fluenceenergy.com/"},
            {"title": "Global BESS Deployment — 15GW+ Pipeline", "amount": "N/A", "capacity": "15GW+", "type": "BESS", "date": "2024-2026", "note": "Siemens+AES JV · leading global BESS integrator", "url": ""},
        ],
    }

    type_colors = {
        "NUCLEAR":     ("#3b82f6", "rgba(59,130,246,.1)"),
        "M&A":         ("#a855f7", "rgba(168,85,247,.1)"),
        "PPA":         ("#ef4444", "rgba(239,68,68,.1)"),
        "EQUITY":      ("#f59e0b", "rgba(245,158,11,.1)"),
        "BESS":        ("#22c55e", "rgba(34,197,94,.1)"),
        "RE100":       ("#22c55e", "rgba(34,197,94,.1)"),
        "GRID TECH":   ("#00b4d8", "rgba(0,180,216,.1)"),
        "PARTNERSHIP": ("#5a5a7a", "rgba(90,90,122,.1)"),
        "OTHER":       ("#5a5a7a", "rgba(90,90,122,.1)"),
    }

    strategy_map = {
        "Microsoft":          "Nuclear offtake + SMR direct investment leader. $110/MWh sets market benchmark.",
        "Google":             "First hyperscaler to own assets directly. $4.75B Intersect Power = PPA to M&A shift.",
        "Amazon":             "Most diversified portfolio. PPA + equity ($500M X-energy) + $18B nuclear offtake.",
        "Meta":               "Nuclear-centric. Up to 6.6GW target. First hyperscaler commercial LDES contract.",
        "Apple":              "100% renewable since 2018. Clean Energy Charging = world largest demand response fleet.",
        "Oracle":             "1.5GW nuclear PPA + $100B+ AI infrastructure. Late but aggressive.",
        "NVIDIA":             "NVentures CVC: CFS $863M + Redwood $350M + Emerald AI. B200 chip efficiency strategy.",
        "Samsung":            "Samsung Ventures: GridBeyond €12M + Amperon + Emerald AI. BESS vertical integration.",
        "SK":                 "Bloom Energy $300M + Plug Power $1.5B + TerraPower SMR. Diversified clean energy bets.",
        "SoftBank":           "SB Energy 7GW US solar+storage. Arm architecture as AI DC power efficiency moat.",
        "GE Vernova":         "$35B IPO Apr 2024. Grid bottleneck owner. Transformer backlog = AI DC critical path.",
        "Siemens Energy":     "HVDC grid + offshore wind. Transformer capacity expansion 20% for AI DC demand.",
        "ABB":                "HVDC transformer and EV charging. 36-month lead time = IRR risk for every hyperscaler.",
        "Schneider Electric": "EcoStruxure AI microgrid + AVEVA $11B. Dominant in AI DC power management software.",
        "Eaton":              "AI DC UPS/PDU critical infrastructure. $1.5B+ data center revenue growing 30%+ YoY.",
        "Constellation":      "TMI restart (MSFT) + Clinton (Meta) + Calpine $16.4B. America nuclear AI power hub.",
        "NextEra":            "35GW+ operating. Primary renewable supplier to US hyperscalers. 20GW+ BESS pipeline.",
        "Vistra":             "6.4GW nuclear fleet + Energy Harbor $3.43B. Largest US nuclear+BESS platform.",
        "Fluence":            "Fluence IQ auto-bidding AI + 15GW+ BESS pipeline. Siemens+AES JV BESS market leader.",
    }

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total_new = sum(len(v) for v in news_data.values())

    def make_deal_card(d, color, bg):
        title_html = d["title"]
        if d.get("url"):
            title_html = '<a href="' + d["url"] + '" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">' + d["title"] + ' <span style=\'font-size:10px;opacity:.5;\'>↗</span></a>'
        amount_html = '<span style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e;">' + d["amount"] + '</span>' if d.get("amount") and d["amount"] != "N/A" else ""
        cap_html = '<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.4);">' + d["capacity"] + '</span>' if d.get("capacity") and d["capacity"] not in ("N/A", "") else ""
        note_html = '<div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.3);margin-top:2px;">' + d["note"] + "</div>" if d.get("note") else ""
        return (
            '<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);">'
            '<div style="width:5px;height:5px;border-radius:50%;background:' + color + ';flex-shrink:0;margin-top:5px;"></div>'
            '<div style="flex:1;">'
            '<div style="font-size:12px;font-weight:500;margin-bottom:3px;line-height:1.4;">' + title_html + '</div>'
            '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:3px;">'
            '<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 6px;border-radius:2px;background:' + bg + ';color:' + color + ';border:1px solid ' + color + '44;">' + d["type"] + '</span>'
            + amount_html + cap_html +
            '<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.25);">' + d.get("date","") + '</span>'
            '</div>' + note_html +
            '</div></div>'
        )

    # Group cards by type
    groups = {
        "hyperscaler": ["Microsoft", "Google", "Amazon", "Meta", "Apple", "Oracle", "NVIDIA"],
        "asia_tech":   ["Samsung", "SK", "SoftBank"],
        "energy_oem":  ["GE Vernova", "Siemens Energy", "ABB", "Schneider Electric", "Eaton"],
        "utility":     ["Constellation", "NextEra", "Vistra", "Fluence"],
    }
    group_labels = {
        "hyperscaler": "Hyperscalers",
        "asia_tech":   "Asia Tech",
        "energy_oem":  "Energy OEM & Infrastructure",
        "utility":     "Utilities & Energy Tech",
    }

    group_html = {k: "" for k in groups}

    for company, info in HYPERSCALERS.items():
        verified = VERIFIED_DEALS.get(company, [])
        latest_news = news_data.get(company, [])

        v_html = "".join(make_deal_card(d, *type_colors.get(d["type"], ("#5a5a7a","rgba(90,90,122,.1)"))) for d in verified)

        n_html = ""
        if latest_news:
            n_html = '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(59,130,246,.1);"><div style="font-family:IBM Plex Mono,monospace;font-size:8px;letter-spacing:.12em;color:rgba(59,130,246,.6);text-transform:uppercase;margin-bottom:6px;">Latest News</div>'
            for n in latest_news[:3]:
                nc, nb = type_colors.get(n.get("deal_type","OTHER"), ("#5a5a7a","rgba(90,90,122,.1)"))
                n_html += (
                    '<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.03);">'
                    '<a href="' + n.get("link","#") + '" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;">'
                    '<div style="font-size:11px;color:rgba(232,232,240,.7);line-height:1.4;margin-bottom:2px;">' + n["title"][:85] + '...</div>'
                    '<div style="display:flex;gap:6px;">'
                    '<span style="font-family:IBM Plex Mono,monospace;font-size:7px;padding:1px 5px;border-radius:2px;background:' + nb + ';color:' + nc + ';">' + n.get("deal_type","OTHER") + '</span>'
                    + ('<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:#22c55e;">' + n["amount"] + '</span>' if n.get("amount") else "") +
                    '<span style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.2);">' + n.get("published","") + '</span>'
                    '</div></a></div>'
                )
            n_html += '</div>'
        elif company not in ("NVIDIA",):
            n_html = '<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:rgba(232,232,240,.15);margin-top:10px;padding-top:10px;border-top:1px solid rgba(59,130,246,.08);">No new energy deals in last 60 days</div>'

        badge = '<span style="margin-left:auto;font-family:IBM Plex Mono,monospace;font-size:8px;padding:2px 8px;border-radius:2px;background:rgba(59,130,246,.1);color:#3b82f6;">+' + str(len(latest_news)) + ' new</span>' if latest_news else ""

        card = (
            '<div style="background:rgba(255,255,255,.02);border:1px solid rgba(59,130,246,.08);padding:20px;">'
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">'
            '<div style="width:32px;height:32px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-family:IBM Plex Mono,monospace;font-size:10px;font-weight:500;background:' + info["bg"] + ';color:' + info["color"] + ';flex-shrink:0;">' + company[:2].upper() + '</div>'
            '<div style="flex:1;min-width:0;">'
            '<div style="font-size:14px;font-weight:500;">' + company + '</div>'
            '<div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:rgba(232,232,240,.3);margin-top:1px;line-height:1.4;">' + strategy_map.get(company,"") + '</div>'
            '</div>' + badge + '</div>'
            + v_html + n_html +
            '</div>'
        )

        for grp, cos in groups.items():
            if company in cos:
                group_html[grp] += card
                break

    # Build sections HTML
    sections_html = ""
    for grp, label in group_labels.items():
        if group_html[grp]:
            sections_html += (
                '<div style="margin-bottom:12px;font-family:IBM Plex Mono,monospace;font-size:9px;letter-spacing:.2em;color:rgba(59,130,246,.5);text-transform:uppercase;">■ ' + label + '</div>'
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px;">'
                + group_html[grp] +
                '</div>'
            )

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GRIDEDGE — Hyperscaler Energy Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@300;400;500&family=Geist:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#050507;--white:#e8e8f0;--dim:#5a5a7a;--blue:#3b82f6;--border:rgba(59,130,246,0.08);--card:rgba(255,255,255,0.02);}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--white);font-family:'Geist',sans-serif;min-height:100vh;}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(59,130,246,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,0.03) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0;}
nav{position:sticky;top:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:14px 32px;background:rgba(5,5,7,0.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);}
.logo{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:500;letter-spacing:0.2em;color:var(--blue);text-decoration:none;}
.logo em{color:var(--white);opacity:0.3;font-style:normal;}
.nav-r{display:flex;align-items:center;gap:20px;font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:0.12em;color:var(--dim);text-transform:uppercase;}
.nav-r a{color:var(--dim);text-decoration:none;transition:color .2s;}
.nav-r a:hover,.nav-r a.active{color:var(--blue);}
.wrap{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:48px 32px;}
@media(max-width:1100px){.grid-2{grid-template-columns:1fr!important;}}
@media(max-width:768px){.wrap{padding:24px 16px;}.nav-r{display:none;}}
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
  <p style="font-size:13px;color:var(--dim);line-height:1.7;max-width:600px;margin-bottom:4px;">Tracking Big Tech energy M&amp;A, PPAs, CVC investments, and direct infrastructure plays in real time.</p>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:rgba(232,232,240,.2);margin-bottom:32px;">Auto-updated: """ + updated + """ &middot; Verified deals + last 60 days news &middot; """ + str(total_new) + """ latest news items collected</div>

  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:40px;">
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Total Committed</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$40B+</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Big 4 energy capex 2024-2026</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Nuclear Offtake</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">5.8 GW</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">MSFT+Amazon+Meta signed PPAs</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Avg Nuclear Price</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$90/MWh</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">vs $40 spot &middot; 2x premium</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Largest M&amp;A</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">$4.75B</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Google &rarr; Intersect Power</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);padding:14px 16px;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;margin-bottom:6px;">Latest News</div>
      <div style="font-family:'Instrument Serif',serif;font-size:22px;color:var(--blue);">""" + str(total_new) + """</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--dim);margin-top:3px;">Energy deal news, last 60 days</div>
    </div>
  </div>

  """ + sections_html + """

</div>
</body>
</html>"""

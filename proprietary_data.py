"""
GRIDEDGE Proprietary Data Collection
Early Stage 특화 — SEC Form D, DOE/ARPA-E, YC, Hiring Signals, Patents
"""

import requests
import json
import re
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "GRIDEDGE Intelligence gridedge.intel@gmail.com"}

ENERGY_KEYWORDS = [
    "battery", "bess", "energy storage", "solar", "wind", "grid",
    "transmission", "nuclear", "smr", "hydrogen", "electrolyzer",
    "power", "electric", "renewable", "clean energy", "microgrid",
    "inverter", "data center power", "ai power", "grid software",
    "demand response", "grid-forming", "frequency regulation",
    "virtual power plant", "energy management",
]


# ── 1. SEC Form D ─────────────────────────────────────────────────────────────

def fetch_sec_form_d_energy() -> list:
    results = []
    keywords = ["energy storage", "battery storage", "grid software",
                "clean energy", "power systems"]
    for kw in keywords[:4]:
        try:
            encoded = kw.replace(" ", "+")
            start = (datetime.utcnow() - timedelta(days=21)).strftime("%Y-%m-%d")
            end = datetime.utcnow().strftime("%Y-%m-%d")
            url = (f"https://efts.sec.gov/LATEST/search-index"
                   f"?q=%22{encoded}%22&dateRange=custom"
                   f"&startdt={start}&enddt={end}&forms=D")
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", {}).get("hits", [])
            for hit in hits[:3]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                if not entity:
                    continue
                if any(e["entity"] == entity for e in results):
                    continue
                amount = src.get("offering_amount", "")
                filed = src.get("file_date", "")
                amt_str = f"${float(amount):,.0f}" if amount else "undisclosed"
                results.append({
                    "source": "SEC Form D",
                    "type": "early_stage_filing",
                    "sector": "EARLY_STAGE",
                    "entity": entity,
                    "filed_date": filed,
                    "amount_usd": float(amount) if amount else None,
                    "keyword_match": kw,
                    "signal": f"SEC Form D: {entity} — private offering {amt_str} ({kw})",
                    "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=D",
                    "is_early_stage": True,
                    "deal_stage_hint": "SEED",
                })
        except Exception as e:
            print(f"  [SEC Form D/{kw}] {e}")
    print(f"  [SEC Form D] {len(results)}개 수집")
    return results


# ── 2. DOE / ARPA-E ──────────────────────────────────────────────────────────

def fetch_doe_grants() -> list:
    results = []
    try:
        import feedparser
        feed = feedparser.parse("https://arpa-e.energy.gov/news-and-media/rss.xml")
        for entry in feed.entries[:8]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            text = (title + " " + summary).lower()
            if any(k in text for k in ["storage", "grid", "battery", "power", "hydrogen", "solar"]):
                results.append({
                    "source": "ARPA-E",
                    "type": "government_grant",
                    "sector": "EARLY_STAGE",
                    "signal": f"ARPA-E: {title}",
                    "url": link,
                    "summary": summary[:200],
                    "is_early_stage": True,
                    "deal_stage_hint": "PRE_SEED",
                })
    except Exception as e:
        print(f"  [ARPA-E] {e}")

    # grants.gov DOE
    try:
        url = "https://apply07.grants.gov/grantsws/rest/opportunities/search/"
        payload = {
            "keyword": "energy storage battery grid AI",
            "oppStatuses": "posted",
            "rows": 8,
            "sortBy": "openDate|desc",
        }
        r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for opp in r.json().get("oppHits", [])[:5]:
                title = opp.get("title", "")
                amount = opp.get("awardCeiling", 0)
                opp_id = opp.get("id", "")
                results.append({
                    "source": "DOE Grants.gov",
                    "type": "government_grant",
                    "sector": "EARLY_STAGE",
                    "signal": f"DOE Grant: {title} — ${amount:,.0f}" if amount else f"DOE Grant: {title}",
                    "url": f"https://www.grants.gov/search-results-detail/{opp_id}",
                    "amount_usd": amount,
                    "is_early_stage": True,
                    "deal_stage_hint": "PRE_SEED",
                })
    except Exception as e:
        print(f"  [DOE Grants] {e}")

    print(f"  [DOE/ARPA-E] {len(results)}개 수집")
    return results


# ── 3. YC / HackerNews Early Stage ───────────────────────────────────────────

def fetch_yc_energy() -> list:
    results = []
    try:
        import feedparser
        feed = feedparser.parse("https://news.ycombinator.com/rss")
        energy_kw = ["energy", "battery", "grid", "power", "solar", "nuclear",
                     "hydrogen", "storage", "bess", "inverter", "climate"]
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            text = title.lower()
            if any(k in text for k in energy_kw):
                # Show HN = 스타트업 런칭 신호
                is_launch = text.startswith("show hn") or "launch" in text
                results.append({
                    "source": "Hacker News" + (" (Launch)" if is_launch else ""),
                    "type": "early_stage_signal",
                    "sector": "EARLY_STAGE",
                    "signal": f"HN: {entry.get('title', '')}",
                    "url": link,
                    "is_early_stage": True,
                    "is_launch": is_launch,
                    "deal_stage_hint": "SEED" if is_launch else "UNKNOWN",
                })
    except Exception as e:
        print(f"  [HN] {e}")

    # Climatebase 채용 (에너지 스타트업 탐지)
    try:
        import feedparser
        feed = feedparser.parse("https://climatebase.org/jobs.rss")
        companies_seen = set()
        for entry in feed.entries[:20]:
            title = entry.get("title", "")
            company = entry.get("author", "")
            text = (title + " " + entry.get("summary", "")).lower()
            if company and company not in companies_seen:
                if any(k in text for k in ENERGY_KEYWORDS):
                    senior = any(s in text for s in ["cto", "vp engineering", "founding", "staff engineer"])
                    companies_seen.add(company)
                    results.append({
                        "source": "Climatebase",
                        "type": "hiring_signal",
                        "sector": "EARLY_STAGE",
                        "entity": company,
                        "signal": f"Hiring: {company} — {title}" + (" [SENIOR HIRE]" if senior else ""),
                        "url": entry.get("link", ""),
                        "is_early_stage": True,
                        "is_senior_hire": senior,
                        "deal_stage_hint": "SERIES_A" if senior else "SEED",
                    })
    except Exception as e:
        print(f"  [Climatebase] {e}")

    print(f"  [YC/HN/Climatebase] {len(results)}개 수집")
    return results


# ── 4. USPTO Patents ──────────────────────────────────────────────────────────

def fetch_energy_patents() -> list:
    results = []
    try:
        start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        url = "https://search.patentsview.org/api/v1/patent/"
        params = {
            "q": ('{"_and":['
                  '{"_text_any":{"patent_abstract":"grid-forming battery storage AI data center power inverter"}},'
                  f'{{"_gte":{{"patent_date":"{start}"}}}}'
                  ']}'),
            "f": '["patent_id","patent_title","patent_date","assignees"]',
            "o": '{"per_page":5}',
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for p in r.json().get("patents", [])[:5]:
                title = p.get("patent_title", "")
                date = p.get("patent_date", "")
                assignees = p.get("assignees", [])
                assignee = assignees[0].get("assignee_organization", "Unknown") if assignees else "Unknown"
                text = title.lower()
                if any(k in text for k in ENERGY_KEYWORDS):
                    results.append({
                        "source": "USPTO",
                        "type": "patent_filing",
                        "sector": "POWER_TECH",
                        "entity": assignee,
                        "signal": f"Patent: {title} — {assignee} ({date})",
                        "url": f"https://search.patentsview.org/",
                        "is_early_stage": True,
                        "deal_stage_hint": "PRE_SEED",
                    })
    except Exception as e:
        print(f"  [USPTO] {e}")
    print(f"  [Patents] {len(results)}개 수집")
    return results


# ── 5. FERC / SEC 8-K ────────────────────────────────────────────────────────

def fetch_ferc_filings() -> list:
    results = []
    try:
        start = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
        end = datetime.utcnow().strftime("%Y-%m-%d")
        url = (f"https://efts.sec.gov/LATEST/search-index"
               f"?q=%22interconnection%22+%22data+center%22"
               f"&dateRange=custom&startdt={start}&enddt={end}&forms=8-K")
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
                        "signal": f"8-K: {entity} — interconnection/DC disclosure ({filed})",
                        "url": "https://efts.sec.gov/LATEST/search-index?forms=8-K",
                        "filed_date": filed,
                    })
    except Exception as e:
        print(f"  [FERC/8-K] {e}")
    print(f"  [FERC/SEC] {len(results)}개 수집")
    return results


# ── 메인 ─────────────────────────────────────────────────────────────────────

def collect_proprietary_data() -> dict:
    print("\n[독점 데이터 수집 시작]")
    data = {
        "sec_form_d": [],
        "doe_grants": [],
        "yc_energy": [],
        "patents": [],
        "ferc_filings": [],
        "collected_at": datetime.utcnow().isoformat(),
    }
    for key, fn in [
        ("sec_form_d", fetch_sec_form_d_energy),
        ("doe_grants", fetch_doe_grants),
        ("yc_energy", fetch_yc_energy),
        ("patents", fetch_energy_patents),
        ("ferc_filings", fetch_ferc_filings),
    ]:
        try:
            data[key] = fn()
        except Exception as e:
            print(f"  [{key}] 전체 실패: {e}")

    total = sum(len(v) for v in data.values() if isinstance(v, list))
    print(f"[독점 데이터] 총 {total}개 신호 수집 완료\n")
    return data


def format_proprietary_for_prompt(data: dict) -> str:
    lines = [
        "=== PROPRIETARY EARLY STAGE SIGNALS ===",
        "NOT available in public RSS. Prioritize for SEED/SERIES A identification.\n",
    ]

    sections = [
        ("sec_form_d",   "SEC FORM D (Private Round Filings)"),
        ("doe_grants",   "DOE / ARPA-E GRANTS (Early Tech Signal)"),
        ("yc_energy",    "YC / HN / CLIMATEBASE (Startup Signals)"),
        ("patents",      "USPTO PATENTS (Technical Moat Signal)"),
        ("ferc_filings", "REGULATORY FILINGS (Grid Signal)"),
    ]

    for key, label in sections:
        items = data.get(key, [])
        if items:
            lines.append(f"── {label} ──")
            for item in items[:5]:
                lines.append(f"• {item['signal']}")
                if item.get("deal_stage_hint"):
                    lines.append(f"  Stage hint: {item['deal_stage_hint']}")
            lines.append("")

    return "\n".join(lines) if len(lines) > 3 else "No proprietary signals collected."


if __name__ == "__main__":
    data = collect_proprietary_data()
    print(format_proprietary_for_prompt(data))

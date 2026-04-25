"""
GRIDEDGE Proprietary Data Collection
Early Stage \ud2b9\ud654 \u2014 SEC Form D, DOE/ARPA-E, YC, LinkedIn \ucc44\uc6a9\uacf5\uace0
"""

import requests
import json
import re
from datetime import datetime, timedelta
from typing import Optional

# \u2500\u2500 \uc124\uc815 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

HEADERS = {
    "User-Agent": "GRIDEDGE Intelligence gridedge.intel@gmail.com",
    "Accept": "application/json",
}

ENERGY_KEYWORDS = [
    "battery", "bess", "energy storage", "solar", "wind", "grid",
    "transmission", "nuclear", "smr", "hydrogen", "electrolyzer",
    "fuel cell", "power", "electric", "renewable", "clean energy",
    "microgrid", "inverter", "data center power", "ai power",
    "grid software", "energy management", "virtual power plant",
    "demand response", "grid-forming", "frequency regulation",
]

EARLY_STAGE_AMOUNTS = [
    r"\$[0-9]+(?:\.[0-9]+)?[MK]\b",   # $5M, $500K
    r"\$[0-9]+(?:\.[0-9]+)? million",
    r"\$[0-9]+(?:\.[0-9]+)? thousand",
]


# \u2500\u2500 1. SEC Form D (\ubbf8\uad6d \ube44\uacf5\uac1c \ub77c\uc6b4\ub4dc \uacf5\uc2dc) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_sec_form_d() -> list[dict]:
    """
    SEC EDGAR Form D \ucd5c\uadfc \uc5d0\ub108\uc9c0 \uc139\ud130 \uacf5\uc2dc \uc218\uc9d1
    Seed/Series A \uc758\ubb34 \uacf5\uc2dc \u2014 \ub77c\uc6b4\ub4dc \ud6c4 2-4\uc8fc \ub0b4 \uc81c\ucd9c
    """
    results = []
    try:
        # EDGAR \ud480\ud14d\uc2a4\ud2b8 \uac80\uc0c9 API
        url = "https://efts.sec.gov/LATEST/search-index?q=%22energy+storage%22+%22battery%22&dateRange=custom&startdt={}&enddt={}&forms=D".format(
            (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
            datetime.utcnow().strftime("%Y-%m-%d")
        )

        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return results

        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:10]:
            src = hit.get("_source", {})
            entity = src.get("entity_name", "Unknown")
            filed = src.get("file_date", "")
            amount = src.get("offering_amount", "")

            # \uc5d0\ub108\uc9c0 \ud0a4\uc6cc\ub4dc \uccb4\ud06c
            desc = (src.get("description", "") + " " + entity).lower()
            if not any(k in desc for k in ENERGY_KEYWORDS):
                continue

            results.append({
                "source": "SEC Form D",
                "type": "early_stage_filing",
                "entity": entity,
                "filed_date": filed,
                "amount": amount,
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={entity.replace(' ', '+')}&type=D&dateb=&owner=include&count=10",
                "signal": f"[SEC Form D] {entity} \u2014 \ube44\uacf5\uac1c \uc790\uae08 \uc870\ub2ec \uacf5\uc2dc (${amount})" if amount else f"[SEC Form D] {entity} \u2014 \ube44\uacf5\uac1c \uc790\uae08 \uc870\ub2ec \uacf5\uc2dc",
            })

        print(f"  [SEC Form D] {len(results)}\uac1c \uc5d0\ub108\uc9c0 \uacf5\uc2dc \uc218\uc9d1")

    except Exception as e:
        print(f"  [SEC Form D] \uc218\uc9d1 \uc2e4\ud328: {e}")

    return results


def fetch_sec_form_d_energy() -> list[dict]:
    """
    \ub354 \ub113\uc740 \uc5d0\ub108\uc9c0 \ud0a4\uc6cc\ub4dc\ub85c SEC Form D \uc218\uc9d1
    """
    results = []
    keywords = [
        "energy storage", "battery storage", "grid software",
        "clean energy", "renewable energy", "nuclear", "hydrogen",
        "power systems", "microgrid", "smart grid"
    ]

    for kw in keywords[:5]:  # API \uacfc\ubd80\ud558 \ubc29\uc9c0
        try:
            encoded = kw.replace(" ", "+")
            url = (
                "https://efts.sec.gov/LATEST/search-index"
                f"?q=%22{encoded}%22"
                f"&dateRange=custom"
                f"&startdt={(datetime.utcnow() - timedelta(days=21)).strftime('%Y-%m-%d')}"
                f"&enddt={datetime.utcnow().strftime('%Y-%m-%d')}"
                "&forms=D"
            )
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue

            data = r.json()
            hits = data.get("hits", {}).get("hits", [])

            for hit in hits[:3]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                if not entity:
                    continue

                # \uc911\ubcf5 \uccb4\ud06c
                if any(e["entity"] == entity for e in results):
                    continue

                filed = src.get("file_date", "")
                amount = src.get("offering_amount", "")

                results.append({
                    "source": "SEC Form D",
                    "type": "early_stage_filing",
                    "sector": "EARLY_STAGE",
                    "entity": entity,
                    "filed_date": filed,
                    "amount_usd": float(amount) if amount else None,
                    "keyword_match": kw,
                    "signal": f"SEC Form D: {entity} files private offering ({kw}) \u2014 ${amount:,.0f}" if amount else f"SEC Form D: {entity} files private offering ({kw})",
                    "url": "https://efts.sec.gov/LATEST/search-index?forms=D",
                    "is_early_stage": True,
                })

        except Exception as e:
            print(f"  [SEC Form D/{kw}] \uc2e4\ud328: {e}")

    print(f"  [SEC Form D] {len(results)}\uac1c \uc5d0\ub108\uc9c0 \ub77c\uc6b4\ub4dc \uc218\uc9d1")
    return results


# \u2500\u2500 2. DOE / ARPA-E \uadf8\ub79c\ud2b8 \uacf5\uc2dc \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_doe_grants() -> list[dict]:
    """
    DOE / ARPA-E \ucd5c\uadfc \uadf8\ub79c\ud2b8 \uc218\uc0c1 \uacf5\uc2dc
    \uc5d0\ub108\uc9c0 \uae30\uc220 \ucd08\uae30 \ub2e8\uacc4 \ucd5c\uace0 \uc2e0\ud638 \u2014 \uc0c1\uc6a9\ud654 3-5\ub144 \uc804
    """
    results = []
    try:
        # grants.gov API \u2014 DOE \uc5d0\ub108\uc9c0 \uadf8\ub79c\ud2b8
        url = "https://apply07.grants.gov/grantsws/rest/opportunities/search/"
        payload = {
            "keyword": "energy storage battery grid",
            "oppStatuses": "posted,forecasted",
            "agencies": "DOE",
            "rows": 10,
            "sortBy": "openDate|desc",
        }
        r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            opps = data.get("oppHits", [])
            for opp in opps[:5]:
                title = opp.get("title", "")
                agency = opp.get("agencyName", "DOE")
                amount = opp.get("awardCeiling", 0)
                close_date = opp.get("closeDate", "")
                opp_num = opp.get("id", "")

                results.append({
                    "source": "DOE Grants.gov",
                    "type": "government_grant",
                    "sector": "EARLY_STAGE",
                    "title": title,
                    "agency": agency,
                    "amount_usd": amount,
                    "close_date": close_date,
                    "signal": f"DOE Grant: {title} \u2014 ${amount:,.0f} available ({agency})" if amount else f"DOE Grant: {title}",
                    "url": f"https://www.grants.gov/search-results-detail/{opp_num}",
                    "is_early_stage": True,
                })

    except Exception as e:
        print(f"  [DOE Grants] \uc218\uc9d1 \uc2e4\ud328: {e}")

    # ARPA-E \ub274\uc2a4 RSS \ucd94\uac00
    try:
        import feedparser
        feed = feedparser.parse("https://arpa-e.energy.gov/news-and-media/rss.xml")
        for entry in feed.entries[:5]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")

            # \uc5d0\ub108\uc9c0 \uc800\uc7a5, \uadf8\ub9ac\ub4dc \uad00\ub828\ub9cc
            text = (title + " " + summary).lower()
            if not any(k in text for k in ["storage", "grid", "battery", "power", "hydrogen"]):
                continue

            results.append({
                "source": "ARPA-E",
                "type": "government_grant",
                "sector": "EARLY_STAGE",
                "title": title,
                "signal": f"ARPA-E: {title}",
                "url": link,
                "summary": summary[:300],
                "is_early_stage": True,
            })

    except Exception as e:
        print(f"  [ARPA-E RSS] \uc218\uc9d1 \uc2e4\ud328: {e}")

    print(f"  [DOE/ARPA-E] {len(results)}\uac1c \uadf8\ub79c\ud2b8 \uc218\uc9d1")
    return results


# \u2500\u2500 3. Y Combinator \ubc30\uce58 \uc5d0\ub108\uc9c0 \uc2a4\ud0c0\ud2b8\uc5c5 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_yc_energy() -> list[dict]:
    """
    YC \ubc30\uce58\uc5d0\uc11c \uc5d0\ub108\uc9c0 \uad00\ub828 \uc2a4\ud0c0\ud2b8\uc5c5 \ud0d0\uc9c0
    YC Company Directory API (\uacf5\uac1c)
    """
    results = []
    try:
        # YC \uacf5\uac1c API
        url = "https://api.ycombinator.com/v0.1/companies?industry=Energy&page=1&limit=20"
        r = requests.get(url, headers={
            "User-Agent": "GRIDEDGE Intelligence gridedge.intel@gmail.com"
        }, timeout=10)

        if r.status_code == 200:
            data = r.json()
            companies = data.get("companies", [])

            # \ucd5c\uadfc 2\uac1c \ubc30\uce58\ub9cc (W26, S25, W25)
            recent_batches = ["W26", "S25", "W25", "S26"]

            for co in companies:
                batch = co.get("batch", "")
                if batch not in recent_batches:
                    continue

                name = co.get("name", "")
                desc = co.get("one_liner", "")
                website = co.get("website", "")
                tags = co.get("tags", [])

                # \uc5d0\ub108\uc9c0 \uad00\ub828 \ud0dc\uadf8 \ud655\uc778
                energy_tags = ["Energy", "Climate", "Grid", "Storage", "Power",
                               "Clean Energy", "Cleantech", "Nuclear"]
                if not any(t in energy_tags for t in tags):
                    text = (desc + " " + " ".join(tags)).lower()
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                results.append({
                    "source": f"YC {batch}",
                    "type": "vc_round",
                    "sector": "EARLY_STAGE",
                    "entity": name,
                    "description": desc,
                    "batch": batch,
                    "tags": tags,
                    "signal": f"YC {batch}: {name} \u2014 {desc}",
                    "url": website or f"https://www.ycombinator.com/companies/{name.lower().replace(' ', '-')}",
                    "is_early_stage": True,
                    "deal_stage_hint": "SEED",
                })

    except Exception as e:
        print(f"  [YC API] \uc218\uc9d1 \uc2e4\ud328: {e}")

    # YC \ub274\uc2a4 RSS \ud3f4\ubc31
    if not results:
        try:
            import feedparser
            feed = feedparser.parse("https://news.ycombinator.com/rss")
            for entry in feed.entries[:20]:
                title = entry.get("title", "").lower()
                link = entry.get("link", "")
                if any(k in title for k in ["energy", "battery", "grid", "power", "solar", "nuclear"]):
                    results.append({
                        "source": "Hacker News",
                        "type": "early_stage_signal",
                        "sector": "EARLY_STAGE",
                        "signal": f"HN: {entry.get('title', '')}",
                        "url": link,
                        "is_early_stage": True,
                    })
        except Exception as e:
            print(f"  [HN RSS] \uc2e4\ud328: {e}")

    print(f"  [YC/HN] {len(results)}\uac1c \ucd08\uae30 \uc2a4\ud0c0\ud2b8\uc5c5 \uc218\uc9d1")
    return results


# \u2500\u2500 4. LinkedIn \ucc44\uc6a9\uacf5\uace0 \uae30\ubc18 \uc2a4\ud154\uc2a4 \ud0d0\uc9c0 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_linkedin_energy_hiring() -> list[dict]:
    """
    \uc5d0\ub108\uc9c0 \uc2a4\ud0c0\ud2b8\uc5c5 \ucc44\uc6a9\uacf5\uace0 \u2192 \uc2a4\ud154\uc2a4 \uae30\uc5c5 \ud0d0\uc9c0
    \ud2b9\uc815 \uc5ed\ud560 \ucc44\uc6a9 = \uc2dc\ub9ac\uc988 \uc9c1\uc804 \uc2e0\ud638
    """
    results = []

    # LinkedIn \uc9c1\uc811 \uc2a4\ud06c\ub798\ud551 \ub300\uc2e0 \uacf5\uac1c RSS/API \ud65c\uc6a9
    startup_signals = [
        {
            "url": "https://angel.co/job-collections/climate-tech/rss",
            "source": "AngelList Climate",
        },
        {
            "url": "https://climatebase.org/jobs.rss",
            "source": "Climatebase Jobs",
        },
    ]

    try:
        import feedparser
        for sig in startup_signals:
            try:
                feed = feedparser.parse(sig["url"])
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    company = entry.get("author", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", "")

                    text = (title + " " + summary).lower()

                    # VP Engineering, CTO \ucc44\uc6a9 = \uc2dc\ub9ac\uc988 A \uc9c1\uc804 \uc2e0\ud638
                    seniority_signals = [
                        "vp engineering", "cto", "chief technology",
                        "head of engineering", "founding engineer",
                        "staff engineer", "principal engineer",
                    ]
                    is_senior_hire = any(s in text for s in seniority_signals)

                    # \uc5d0\ub108\uc9c0 \uad00\ub828 \ud655\uc778
                    if not any(k in text for k in ENERGY_KEYWORDS):
                        continue

                    results.append({
                        "source": sig["source"],
                        "type": "hiring_signal",
                        "sector": "EARLY_STAGE",
                        "signal": f"Hiring Signal: {title} at {company}" + (" [SENIOR HIRE \u2014 Series A signal]" if is_senior_hire else ""),
                        "url": link,
                        "is_early_stage": True,
                        "is_senior_hire": is_senior_hire,
                    })

            except Exception as e:
                print(f"  [{sig['source']}] \uc2e4\ud328: {e}")

    except ImportError:
        print("  [LinkedIn Hiring] feedparser \uc5c6\uc74c")

    print(f"  [Hiring Signals] {len(results)}\uac1c \ucc44\uc6a9 \uc2e0\ud638 \uc218\uc9d1")
    return results


# \u2500\u2500 5. Patent \uacf5\uc2dc (USPTO) \u2014 \uae30\uc220 Moat \uc870\uae30 \ud0d0\uc9c0 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_energy_patents() -> list[dict]:
    """
    USPTO \ucd5c\uadfc \uc5d0\ub108\uc9c0 \uae30\uc220 \ud2b9\ud5c8 \ucd9c\uc6d0
    \ud2b9\ud5c8 \ucd9c\uc6d0 \u2192 \ucc3d\uc5c5/Series A 6-18\uac1c\uc6d4 \uc120\ud589 \uc2e0\ud638
    """
    results = []
    try:
        # PatentsView API (\ubb34\ub8cc)
        url = "https://search.patentsview.org/api/v1/patent/"
        params = {
            "q": '{"_and":[{"_text_any":{"patent_abstract":"grid-forming inverter battery storage AI data center power"}},{"_gte":{"patent_date":"' + (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d") + '"}}]}',
            "f": '["patent_id","patent_title","patent_abstract","patent_date","assignees"]',
            "o": '{"per_page":5}',
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)

        if r.status_code == 200:
            data = r.json()
            patents = data.get("patents", [])

            for p in patents[:5]:
                title = p.get("patent_title", "")
                abstract = (p.get("patent_abstract", "") or "")[:300]
                date = p.get("patent_date", "")
                assignees = p.get("assignees", [])
                assignee_name = assignees[0].get("assignee_organization", "") if assignees else "Unknown"

                # \uc5d0\ub108\uc9c0 \uad00\ub828 \ud655\uc778
                text = (title + " " + abstract).lower()
                if not any(k in text for k in ENERGY_KEYWORDS):
                    continue

                results.append({
                    "source": "USPTO PatentsView",
                    "type": "patent_filing",
                    "sector": "POWER_TECH",
                    "entity": assignee_name,
                    "title": title,
                    "abstract": abstract,
                    "patent_date": date,
                    "signal": f"Patent: {title} ({assignee_name}, {date})",
                    "url": f"https://search.patentsview.org/api/v1/patent/{p.get('patent_id', '')}",
                    "is_early_stage": True,
                    "deal_stage_hint": "PRE_SEED",
                })

    except Exception as e:
        print(f"  [USPTO] \uc218\uc9d1 \uc2e4\ud328: {e}")

    print(f"  [Patents] {len(results)}\uac1c \uc5d0\ub108\uc9c0 \ud2b9\ud5c8 \uc218\uc9d1")
    return results


# \u2500\u2500 6. FERC \uacf5\uc2dc (\ub300\ud615 \ud504\ub85c\uc81d\ud2b8 \ucd08\uae30 \uc2e0\ud638) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def fetch_ferc_filings() -> list[dict]:
    """
    FERC \ucd5c\uadfc \uacf5\uc2dc \u2014 \uadf8\ub9ac\ub4dc \uc778\ud504\ub77c \ucd08\uae30 \uc2e0\ud638
    """
    results = []
    try:
        url = "https://efts.sec.gov/LATEST/search-index?q=%22interconnection%22+%22data+center%22&dateRange=custom&startdt={}&enddt={}&forms=8-K".format(
            (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d"),
            datetime.utcnow().strftime("%Y-%m-%d"),
        )
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            for hit in data.get("hits", {}).get("hits", [])[:5]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                filed = src.get("file_date", "")
                results.append({
                    "source": "SEC EDGAR 8-K",
                    "type": "regulatory_filing",
                    "sector": "GRID",
                    "entity": entity

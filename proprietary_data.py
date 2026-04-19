"""
GRIDEDGE Proprietary Data Pipeline
독점 데이터 수집 모듈 — generate_brief.py에서 import해서 사용

소스:
  1. FERC  — 미국 전력망 계통접속 대기 현황 (공개 API)
  2. SEC EDGAR — 에너지 기업 공시 자동 파싱
  3. USPTO — 에너지 기술 특허 출원 트렌드
  4. 전력거래소 — 한국 SMP/REC 가격
  5. KEPCO DART — 한국 전력 공시
  6. LinkedIn 채용 신호 — 스타트업 펀딩 선행지표 (RSS 기반)
"""

import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote

# ── 1. FERC 계통접속 대기 현황 ──────────────────────────────────────────────

def fetch_ferc_queue() -> dict:
    """
    FERC 전력망 계통접속 대기 큐 데이터
    - 미국 주요 계통운영자(PJM, ERCOT, MISO, SPP, CAISO) 대기 현황
    - 공개 API: ferc.gov
    """
    results = {
        "source": "FERC",
        "fetched_at": datetime.utcnow().isoformat(),
        "queue_data": [],
        "summary": {}
    }

    # FERC eLibrary RSS — 최신 계통접속 관련 공시
    ferc_rss_urls = [
        "https://www.ferc.gov/rss/ferc-news.xml",
        "https://www.ferc.gov/rss/electric.xml",
    ]

    headers = {"User-Agent": "GRIDEDGE-Intelligence/1.0"}
    queue_items = []

    for url in ferc_rss_urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            root = ET.fromstring(r.content)
            items = root.findall(".//item")

            for item in items[:10]:
                title = item.findtext("title", "")
                desc  = item.findtext("description", "")
                link  = item.findtext("link", "")
                pub   = item.findtext("pubDate", "")

                # 계통접속 관련 필터
                keywords = ["interconnection", "queue", "transmission", "generator", "capacity"]
                if any(k in (title + desc).lower() for k in keywords):
                    queue_items.append({
                        "title": title,
                        "description": desc[:300],
                        "url": link,
                        "published": pub[:25],
                        "source": "FERC"
                    })
        except Exception as e:
            print(f"  [FERC] {url} 실패: {e}")

    results["queue_data"] = queue_items[:8]
    results["summary"]["item_count"] = len(queue_items)
    print(f"  [FERC] {len(queue_items)}개 계통접속 시그널 수집")
    return results


# ── 2. SEC EDGAR 에너지 기업 공시 ────────────────────────────────────────────

def fetch_sec_edgar() -> dict:
    """
    SEC EDGAR 에너지 섹터 최신 공시
    - 8-K (중요 공시), S-1 (IPO), 424B (프로스펙터스)
    - 에너지 키워드 필터링
    - 무료 API: efts.sec.gov
    """
    results = {
        "source": "SEC EDGAR",
        "fetched_at": datetime.utcnow().isoformat(),
        "filings": []
    }

    # EDGAR Full-Text Search API
    energy_queries = [
        "solar energy storage battery",
        "wind farm offshore",
        "hydrogen electrolyzer",
        "nuclear small modular reactor",
        "grid transmission interconnection",
        "carbon capture CCS",
    ]

    headers = {
        "User-Agent": "GRIDEDGE Intelligence research@gridedge.io",
        "Accept": "application/json"
    }

    filings = []
    for query in energy_queries[:3]:  # API 부하 방지
        try:
            url = f"https://efts.sec.gov/LATEST/search-index?q={quote(query)}&dateRange=custom&startdt={(datetime.utcnow()-timedelta(days=7)).strftime('%Y-%m-%d')}&enddt={datetime.utcnow().strftime('%Y-%m-%d')}&forms=8-K,S-1"
            r = requests.get(url, headers=headers, timeout=12)
            data = r.json()

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:3]:
                src = hit.get("_source", {})
                filings.append({
                    "company":    src.get("entity_name", ""),
                    "form_type":  src.get("file_date", ""),
                    "filed_at":   src.get("file_date", ""),
                    "description": src.get("period_of_report", ""),
                    "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id', '')}/",
                    "query_tag": query,
                    "source": "SEC EDGAR"
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"  [SEC] '{query}' 실패: {e}")

    results["filings"] = filings[:10]
    print(f"  [SEC EDGAR] {len(filings)}개 공시 수집")
    return results


# ── 3. USPTO 에너지 기술 특허 트렌드 ─────────────────────────────────────────

def fetch_patent_signals() -> dict:
    """
    USPTO 특허 출원 트렌드 — 에너지 기술 섹터
    - 특허 급증 = 기술 성숙 + 상용화 임박 신호
    - PatentsView API (무료, 등록 불필요)
    """
    results = {
        "source": "USPTO PatentsView",
        "fetched_at": datetime.utcnow().isoformat(),
        "patents": [],
        "trends": {}
    }

    # Google Patents RSS (특허 공개 피드)
    patent_rss_queries = [
        ("BESS", "battery energy storage system grid"),
        ("Electrolyzer", "hydrogen electrolyzer efficiency"),
        ("SMR", "small modular reactor nuclear"),
        ("Grid Software", "grid software AI optimization"),
        ("Solar Tech", "perovskite solar cell efficiency"),
    ]

    patents = []
    headers = {"User-Agent": "GRIDEDGE-Bot/1.0"}

    for sector, query in patent_rss_queries:
        try:
            url = f"https://patents.google.com/xhr/query?url=q%3D{quote(query)}%26after%3Dpriority%3A{(datetime.utcnow()-timedelta(days=30)).strftime('%Y%m%d')}&exp=&download=false"
            # Google Patents RSS 대신 EPO Open Patent Services 사용
            epo_url = f"https://worldwide.espacenet.com/3.2/rest-services/search?q={quote(query)}&Range=1-5&output=application/json"
            r = requests.get(epo_url, headers=headers, timeout=10)

            if r.status_code == 200:
                data = r.json()
                entries = data.get("ops:world-patent-data", {}).get("ops:biblio-search", {}).get("ops:search-result", {}).get("ops:publication-reference", [])
                if isinstance(entries, dict):
                    entries = [entries]

                for entry in entries[:2]:
                    doc_id = entry.get("@document-id-type", "")
                    patents.append({
                        "sector": sector,
                        "query": query,
                        "doc_id": str(entry)[:100],
                        "source": "EPO/USPTO"
                    })
        except Exception as e:
            print(f"  [Patent] {sector} 실패: {e}")

        time.sleep(0.5)

    # 대안: arXiv 에너지 기술 논문 (특허 전 단계 기술 신호)
    try:
        # AI 데이터센터 전력 특화 쿼리
        arxiv_url = "http://export.arxiv.org/api/query?search_query=(cat:eess.SY+OR+cat:cs.SY)+AND+(data+center+OR+datacenter+OR+power+optimization+OR+grid+frequency+OR+energy+storage+control)&start=0&max_results=15&sortBy=submittedDate&sortOrder=descending"
        r = requests.get(arxiv_url, headers=headers, timeout=12)
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns)[:8]:
            title   = entry.findtext("atom:title", "", ns).strip()
            summary = entry.findtext("atom:summary", "", ns).strip()[:200]
            link    = entry.find("atom:link[@rel='alternate']", ns)
            pub     = entry.findtext("atom:published", "", ns)[:10]

            patents.append({
                "sector": "Tech Signal",
                "title": title,
                "summary": summary,
                "url": link.get("href", "") if link is not None else "",
                "published": pub,
                "source": "arXiv"
            })

        print(f"  [arXiv] {len(root.findall('atom:entry', ns))}개 기술 논문 수집")
    except Exception as e:
        print(f"  [arXiv] 실패: {e}")

    results["patents"] = patents[:12]
    print(f"  [Patent/Tech] 총 {len(patents)}개 기술 신호 수집")
    return results


# ── 4. 전력거래소 SMP/REC 가격 ───────────────────────────────────────────────

def fetch_korea_power_market() -> dict:
    """
    한국 전력시장 데이터
    - SMP (계통한계가격) — 발전 수익성 지표
    - REC (신재생에너지 공급인증서) 가격
    - 출처: 전력거래소 공개 API
    """
    results = {
        "source": "Korea Power Exchange (KPX)",
        "fetched_at": datetime.utcnow().isoformat(),
        "smp": {},
        "rec": {},
        "interpretation": ""
    }

    headers = {"User-Agent": "GRIDEDGE-Bot/1.0"}

    # 전력거래소 SMP 공개 데이터 (RSS/공개 페이지)
    try:
        # KPX 전력시장 통계 RSS
        kpx_url = "https://www.kpx.or.kr/rss/rssMarket.do"
        r = requests.get(kpx_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items[:5]:
                title = item.findtext("title", "")
                desc  = item.findtext("description", "")
                results["smp"]["latest_news"] = {"title": title, "desc": desc[:200]}
                break
    except Exception as e:
        print(f"  [KPX] SMP 실패: {e}")

    # DART (금융감독원) — KEPCO 공시
    try:
        dart_url = "https://opendart.fss.or.kr/api/list.json?crtfc_key=&corp_code=00254900&bgn_de={(datetime.utcnow()-timedelta(days=30)).strftime('%Y%m%d')}&end_de={datetime.utcnow().strftime('%Y%m%d')}&page_no=1&page_count=5"
        # DART API 키 없이 접근 가능한 공개 RSS 대신
        kepco_url = "https://www.kepco.co.kr/rss/kepcoNews.rss"
        r = requests.get(kepco_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            kepco_news = []
            for item in items[:5]:
                title = item.findtext("title", "")
                link  = item.findtext("link", "")
                kepco_news.append({"title": title, "url": link})
            results["kepco_news"] = kepco_news
            print(f"  [KEPCO] {len(kepco_news)}개 공시 수집")
    except Exception as e:
        print(f"  [KEPCO] 실패: {e}")

    # 한국 에너지 공단 REC 가격 (공개 RSS)
    try:
        knrec_url = "https://www.knrec.or.kr/rss/knrecNews.rss"
        r = requests.get(knrec_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            rec_news = []
            for item in items[:3]:
                title = item.findtext("title", "")
                rec_news.append({"title": title})
            results["rec"]["news"] = rec_news
    except Exception as e:
        print(f"  [REC] 실패: {e}")

    results["interpretation"] = "Korean power market data for Asia-Pacific investment context"
    return results


# ── 5. 스타트업 채용 신호 (펀딩 선행지표) ────────────────────────────────────

def fetch_hiring_signals() -> dict:
    """
    에너지 스타트업 채용 급증 = 펀딩 완료 선행지표
    - LinkedIn 채용공고 RSS (공개)
    - Greenhouse / Lever ATS 공개 피드
    - Y Combinator 포트폴리오 채용
    """
    results = {
        "source": "Hiring Signal Tracker",
        "fetched_at": datetime.utcnow().isoformat(),
        "signals": []
    }

    headers = {"User-Agent": "GRIDEDGE-Bot/1.0"}
    signals = []

    # YC 포트폴리오 에너지 스타트업 채용
    yc_urls = [
        ("YC Energy Jobs", "https://www.ycombinator.com/jobs/role/engineer?query=energy"),
    ]

    # Wellfound (AngelList) 에너지 스타트업 채용 RSS
    wellfound_categories = [
        ("BESS Startups",   "https://wellfound.com/role/r/software-engineer/energy-storage"),
        ("Grid Tech",       "https://wellfound.com/role/r/software-engineer/energy"),
        ("Clean Energy",    "https://wellfound.com/role/r/software-engineer/cleantech"),
    ]

    # Greenhouse ATS — 주요 에너지 스타트업 채용 모니터링
    # (공개 API 없이 RSS로 접근 가능한 곳)
    greenhouse_companies = [
        # AI DC 전력 인프라 스타트업
        ("Form Energy",       "https://boards.greenhouse.io/formenergy"),
        ("Antora Energy",     "https://boards.greenhouse.io/antoraenergy"),
        ("Electric Hydrogen", "https://boards.greenhouse.io/electrichydrogen"),
        ("Quanta Grid",       "https://boards.greenhouse.io/quantagrid"),
        ("Gridmatic",         "https://boards.greenhouse.io/gridmatic"),
        ("AutoGrid",          "https://boards.greenhouse.io/autogrid"),
        ("Swell Energy",      "https://boards.greenhouse.io/swellenergy"),
    ]

    for company, url in greenhouse_companies:
        try:
            r = requests.get(url + "/jobs", headers=headers, timeout=8)
            if r.status_code == 200:
                # 채용공고 수 파악 (간단 파싱)
                job_count = r.text.count('"title"')
                if job_count > 5:  # 급증 신호
                    signals.append({
                        "company": company,
                        "job_count": job_count,
                        "signal": "HIRING_SURGE" if job_count > 15 else "ACTIVE_HIRING",
                        "url": url,
                        "source": "Greenhouse ATS",
                        "interpretation": f"{company} posting {job_count} roles — potential post-funding scaling"
                    })
                    print(f"  [Hiring] {company}: {job_count} roles")
        except Exception as e:
            pass
        time.sleep(0.3)

    # Crunchbase 무료 RSS (최신 펀딩 공고)
    try:
        cb_url = "https://www.crunchbase.com/rss/funding-rounds?category_list=clean-energy,energy-storage,renewable-energy&sort=published_at"
        r = requests.get(cb_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:5]:
                title = item.findtext("title", "")
                desc  = item.findtext("description", "")[:200]
                link  = item.findtext("link", "")
                signals.append({
                    "company": title,
                    "signal": "FUNDING_ANNOUNCED",
                    "description": desc,
                    "url": link,
                    "source": "Crunchbase"
                })
    except Exception as e:
        print(f"  [Crunchbase] 실패: {e}")

    results["signals"] = signals[:10]
    print(f"  [Hiring Signal] 총 {len(signals)}개 신호 수집")
    return results


# ── 통합 수집 함수 ────────────────────────────────────────────────────────────

def collect_proprietary_data() -> dict:
    """모든 독점 데이터 소스 수집 후 통합"""
    print("\n[독점 데이터 수집 시작]")
    print("=" * 50)

    data = {}

    print("[1/5] FERC 계통접속 대기 현황...")
    data["ferc"]    = fetch_ferc_queue()
    time.sleep(1)

    print("[2/5] SEC EDGAR 에너지 공시...")
    data["sec"]     = fetch_sec_edgar()
    time.sleep(1)

    print("[3/5] 특허/기술 트렌드...")
    data["patents"] = fetch_patent_signals()
    time.sleep(1)

    print("[4/5] 한국 전력시장 데이터...")
    data["korea"]   = fetch_korea_power_market()
    time.sleep(1)

    print("[5/5] 스타트업 채용 신호...")
    data["hiring"]  = fetch_hiring_signals()

    # 요약 통계
    total_signals = (
        len(data["ferc"]["queue_data"]) +
        len(data["sec"]["filings"]) +
        len(data["patents"]["patents"]) +
        len(data["hiring"]["signals"])
    )

    print(f"\n[독점 데이터] 총 {total_signals}개 시그널 수집 완료")
    print("=" * 50)

    return data


def format_proprietary_for_prompt(data: dict) -> str:
    """독점 데이터를 Claude 프롬프트용 텍스트로 변환"""
    sections = []

    # FERC
    if data.get("ferc", {}).get("queue_data"):
        items = data["ferc"]["queue_data"][:4]
        ferc_text = "\n".join([f"  - {i['title']}" for i in items])
        sections.append(f"=== FERC INTERCONNECTION SIGNALS ===\n{ferc_text}")

    # SEC EDGAR
    if data.get("sec", {}).get("filings"):
        filings = data["sec"]["filings"][:4]
        sec_text = "\n".join([f"  - [{f.get('form_type','')}] {f.get('company','')} ({f.get('filed_at','')})" for f in filings])
        sections.append(f"=== SEC EDGAR ENERGY FILINGS ===\n{sec_text}")

    # Patents/Tech
    if data.get("patents", {}).get("patents"):
        patents = [p for p in data["patents"]["patents"] if p.get("title")][:5]
        patent_text = "\n".join([f"  - [{p.get('sector','')}] {p.get('title','')[:100]}" for p in patents])
        sections.append(f"=== TECH/PATENT SIGNALS (arXiv) ===\n{patent_text}")

    # Korea
    korea = data.get("korea", {})
    if korea.get("kepco_news"):
        kepco_text = "\n".join([f"  - {n['title']}" for n in korea["kepco_news"][:3]])
        sections.append(f"=== KOREA POWER MARKET (KEPCO) ===\n{kepco_text}")

    # Hiring
    if data.get("hiring", {}).get("signals"):
        hiring = data["hiring"]["signals"][:5]
        hiring_text = "\n".join([f"  - {h.get('company','')}: {h.get('signal','')} ({h.get('interpretation','')})" for h in hiring])
        sections.append(f"=== STARTUP HIRING SIGNALS (Funding Indicator) ===\n{hiring_text}")

    return "\n\n".join(sections) if sections else ""


if __name__ == "__main__":
    # 단독 테스트 실행
    data = collect_proprietary_data()
    formatted = format_proprietary_for_prompt(data)
    print("\n=== 프롬프트용 포맷 ===")
    print(formatted[:2000])

    # JSON 저장
    with open("proprietary_data_test.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n✅ proprietary_data_test.json 저장 완료")

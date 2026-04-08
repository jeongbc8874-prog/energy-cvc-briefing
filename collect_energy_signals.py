"""
collect_energy_signals.py
Energy Capital Flow — Raw Signal Collector (Option A Ver.)

목적: 에너지 분야 자본 흐름(투자, 전략적 투자, 오프테이커, 프로젝트 파이낸싱)을 중점으로 raw 데이터 수집
출력: data/raw/YYYY-MM-DD.json (단순 raw article 리스트)
"""

import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

# ====================== 설정 ======================
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = RAW_DIR / f"{TODAY}.json"

# ====================== RSS 소스 ======================
# 자본 흐름에 강한 소스 위주로 구성 (필요시 더 추가 가능)
RSS_SOURCES = [
    {"id": "utilitydive", "name": "Utility Dive", "url": "https://www.utilitydive.com/feeds/news/"},
    {"id": "pvmagazine", "name": "PV Magazine", "url": "https://www.pv-magazine.com/feed/"},
    {"id": "energystoragenews", "name": "Energy Storage News", "url": "https://www.energy-storage.news/feed/"},
    {"id": "electrek", "name": "Electrek", "url": "https://electrek.co/feed/"},
    {"id": "h2view", "name": "H2 View", "url": "https://www.h2-view.com/feed/"},
    {"id": "offshorewind", "name": "Offshore Wind Biz", "url": "https://www.offshorewind.biz/feed/"},
    # 추가하고 싶은 소스는 여기에 넣으세요
]

# ====================== 자본 흐름 강화 키워드 ======================
CAPITAL_KEYWORDS = [
    "raises", "raised", "funding", "series a", "series b", "series c", "series d", "series e",
    "investment round", "strategic investment", "offtake", "ppa", "power purchase agreement",
    "project finance", "capex", "financing", "led by", "participated", "investor", "venture",
    "hyperscaler", "utility", "shipyard", "of $", "of €", "$", "million", "billion"
]

NOISE_KEYWORDS = [
    "opinion", "commentary", "market wrap", "weekly digest", "rebrand", "hiring", "job opening"
]

def is_capital_related(text: str) -> bool:
    """자본 흐름 관련 기사인지 간단히 판단"""
    text_lower = text.lower()
    if any(kw in text_lower for kw in CAPITAL_KEYWORDS):
        return True
    if any(kw in text_lower for kw in NOISE_KEYWORDS):
        return False
    return True  # 기본적으로는 수집 (나중에 scoring에서 필터링)

async def fetch_feed(source: dict) -> List[dict]:
    articles = []
    try:
        if HAS_FEEDPARSER:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:30]:  # 최대 30개
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                link = entry.get("link", "")
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                
                if not title:
                    continue
                    
                date_str = TODAY
                if published:
                    try:
                        date_str = f"{published.tm_year:04d}-{published.tm_mon:02d}-{published.tm_mday:02d}"
                    except:
                        pass

                raw_text = (title + " " + summary).lower()
                
                if not is_capital_related(raw_text):
                    continue  # 자본 흐름과 무관한 기사는 스킵

                articles.append({
                    "id": hashlib.md5(f"{link}{title}".encode()).hexdigest()[:12],
                    "title": title,
                    "summary": summary[:500],
                    "url": link,
                    "published_date": date_str,
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "raw_text": raw_text
                })
    except Exception as e:
        print(f"  ✗ {source['name']}: {e}")
    
    return articles

async def main():
    print(f"\n=== Energy Capital Flow Collector ===\n{TODAY}\n")
    
    all_articles = []
    
    # 병렬 수집
    tasks = [fetch_feed(source) for source in RSS_SOURCES]
    results = await asyncio.gather(*tasks)
    
    for articles in results:
        all_articles.extend(articles)
    
    # 중복 제거 (URL 기준)
    seen = {}
    deduped = []
    for art in all_articles:
        key = art["url"]
        if key not in seen:
            seen[key] = True
            deduped.append(art)
    
    # 날짜 내림차순 정렬
    deduped.sort(key=lambda x: x["published_date"], reverse=True)
    
    # 저장
    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(deduped),
        "sources": len(RSS_SOURCES),
        "articles": deduped
    }
    
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"수집 완료: {len(deduped)}개 기사 → {OUTPUT_PATH}")
    print(f"자본 흐름 관련 키워드 기반으로 필터링 적용됨")

if __name__ == "__main__":
    asyncio.run(main())

"""
process_capital_flow.py
Energy Capital Flow — Capital Flow Processor (개선 버전)
"""

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = PROCESSED_DIR / "latest.json"

# 더 많은 회사명 패턴
COMPANY_PATTERNS = [
    r'\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,3})\b',  # 대문자로 시작하는 회사명
    r'\b(Tesla|Kia|BYD|Northvolt|Form Energy|EnerVenue|Amogy|Sunfire|Ceres|Gridwiz|SixtyHertz)\b'
]

def calculate_capital_score(article: dict) -> int:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    score = 15

    capital_keywords = [
        "raises", "raised", "funding", "series a", "series b", "series c", "series d", "series e",
        "investment", "strategic investment", "led by", "offtake", "ppa", "power purchase",
        "project finance", "capex", "financing", "grant", "doe award", "hyperscaler", "utility",
        "contract", "deployment", "pilot", "partnership"
    ]

    if any(kw in text for kw in capital_keywords):
        score += 40

    if any(x in text for x in ["$100m", "$200m", "$300m", "$400m", "million", "billion", "억", "조", "usd", "eur"]):
        score += 30

    return min(100, score)

def extract_company_name(title: str) -> str:
    # 알려진 회사명 우선 매칭
    known_companies = ["Tesla", "Kia", "BYD", "Northvolt", "Form Energy", "EnerVenue", "Amogy", "Sunfire", "Ceres", "Gridwiz", "SixtyHertz", "Boralex", "TenneT", "Entergy", "Xcel"]
    for co in known_companies:
        if co.lower() in title.lower():
            return co

    # 일반 패턴
    match = re.search(r'\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,2})\b', title)
    if match:
        candidate = match.group(1).strip()
        if len(candidate) > 3 and candidate.lower() not in ["the", "new", "first", "for", "with", "and", "video", "roundup"]:
            return candidate

    return "Unknown"

def main():
    print(f"\n=== Energy Capital Flow Processor ===\n{TODAY}\n")

    raw_file = RAW_DIR / f"{TODAY}.json"
    if not raw_file.exists():
        print(f"❌ raw 파일 없음: {raw_file}")
        return

    data = json.loads(raw_file.read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    print(f"로드된 raw 기사: {len(articles)}개")

    capital_events = []
    for art in articles:
        score = calculate_capital_score(art)
        if score < 25:
            continue

        company = extract_company_name(art.get("title", ""))

        event = {
            "id": hashlib.md5(art.get("title", "").encode()).hexdigest()[:12],
            "event_type": "funding" if any(k in art.get("title", "").lower() for k in ["raises", "series", "funding"]) else "capital_signal",
            "title": art.get("title", ""),
            "date": art.get("published_date", TODAY),
            "score": score,
            "company_name": company,
            "sector": "unknown",
            "source_name": art.get("source_name", ""),
            "source_url": art.get("url", ""),
            "why_important": "자본 흐름 관련 신호 감지"
        }
        capital_events.append(event)

    capital_events.sort(key=lambda x: (-x["score"], x["date"]), reverse=True)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_raw": len(articles),
        "total_capital_events": len(capital_events),
        "capital_flow_feed": capital_events[:80],
        "stats": {
            "high_score": sum(1 for e in capital_events if e["score"] >= 60)
        }
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(capital_events)}개 이벤트 생성 → {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

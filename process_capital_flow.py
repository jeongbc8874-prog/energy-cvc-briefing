"""
process_capital_flow.py
Energy Capital Flow — Capital Flow Processor
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = PROCESSED_DIR / "latest.json"

def calculate_capital_score(article: dict) -> int:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    score = 0
    capital_keywords = ["raises", "raised", "series a", "series b", "series c", "series d", "series e", 
                        "investment round", "strategic investment", "offtake", "ppa", "project finance", "capex"]
    if any(kw in text for kw in capital_keywords):
        score += 40
    if any(x in text for x in ["$100m", "$200m", "$300m", "million", "billion", "억", "조"]):
        score += 25
    return min(100, score)

def extract_company_name(title: str) -> str:
    words = title.split()
    for word in words:
        if word and word[0].isupper() and len(word) > 3 and word.lower() not in ["the", "new", "first", "for", "with"]:
            return word.strip()
    return "Unknown"

def main():
    print(f"\n=== Energy Capital Flow Processor ===\n{TODAY}\n")

    raw_file = RAW_DIR / f"{TODAY}.json"
    if not raw_file.exists():
        print(f"❌ raw 파일 없음: {raw_file}")
        return

    data = json.loads(raw_file.read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    capital_events = []
    for art in articles:
        score = calculate_capital_score(art)
        if score < 35:
            continue

        company = extract_company_name(art.get("title", ""))

        event = {
            "id": hashlib.md5(art.get("title", "").encode()).hexdigest()[:12],
            "event_type": "funding" if "raises" in art.get("title", "").lower() or "series" in art.get("title", "").lower() else "capital_signal",
            "title": art.get("title", ""),
            "date": art.get("published_date", TODAY),
            "score": score,
            "company_name": company,
            "sector": "unknown",
            "source_name": art.get("source_name", ""),
            "source_url": art.get("url", ""),
            "why_important": "자본 흐름 신호 감지"
        }
        capital_events.append(event)

    capital_events.sort(key=lambda x: (-x["score"], x["date"]), reverse=True)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_raw": len(articles),
        "total_capital_events": len(capital_events),
        "capital_flow_feed": capital_events[:50],
        "stats": {
            "high_score": sum(1 for e in capital_events if e["score"] >= 70)
        }
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(capital_events)}개 자본 흐름 이벤트 생성 → {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

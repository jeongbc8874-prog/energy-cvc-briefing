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

CAPITAL_SCORE_RULES = {
    "funding_round": ["raises", "raised", "series a", "series b", "series c", "series d", "series e", "investment round"],
    "strategic_investment": ["strategic investment", "led by", "participated in", "hyperscaler", "utility investment"],
    "offtaker_signal": ["offtake", "ppa", "power purchase agreement", "supply agreement"],
    "project_finance": ["project finance", "capex", "financing", "gigafactory", "terminal"],
    "grant": ["grant", "doe award", "government funding"],
}

def calculate_capital_score(article: dict) -> int:
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    score = 0
    for event_type, keywords in CAPITAL_SCORE_RULES.items():
        if any(kw in text for kw in keywords):
            score += 30 if event_type in ["funding_round", "strategic_investment"] else 20
    if any(x in text for x in ["$100m", "$200m", "$300m", "million", "billion", "억", "조"]):
        score += 25
    return min(100, score)

def extract_company_name(title: str) -> str:
    words = title.split()
    for word in words:
        if word and word[0].isupper() and len(word) > 3 and word.lower() not in ["the", "new", "first", "for"]:
            return word.strip()
    return "Unknown"

def main():
    print(f"\n=== Energy Capital Flow Processor ===\n{TODAY}\n")

    raw_file = RAW_DIR / f"{TODAY}.json"
    if not raw_file.exists():
        print(f"❌ 오늘 raw 파일이 없습니다: {raw_file}")
        return

    data = json.loads(raw_file.read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    print(f"로드된 raw 기사: {len(articles)}개")

    capital_events = []
    for art in articles:
        score = calculate_capital_score(art)
        if score < 30:
            continue

        company = extract_company_name(art["title"])

        event = {
            "id": art.get("id") or hashlib.md5(art["title"].encode()).hexdigest()[:12],
            "event_type": "funding_round" if any(k in art["title"].lower() for k in ["raises", "series"]) else "capital_signal",
            "title": art["title"],
            "date": art.get("published_date", TODAY),
            "score": score,
            "company_name": company,
            "sector": "unknown",
            "amount": None,
            "source_name": art["source_name"],
            "source_url": art.get("url", ""),
            "why_important": "자본 흐름 관련 신호" if score >= 60 else "관련 신호",
            "tags": ["capital_flow"]
        }
        capital_events.append(event)

    capital_events.sort(key=lambda x: (-x["score"], x["date"]), reverse=True)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_raw": len(articles),
        "total_capital_events": len(capital_events),
        "capital_flow_feed": capital_events[:50],
        "top_funding": [e for e in capital_events if "funding" in e.get("event_type", "").lower()][:10],
        "sector_heat": {"ess": 65, "hydrogen": 48, "grid_sw": 72},
        "stats": {
            "high_score_events": sum(1 for e in capital_events if e["score"] >= 70),
            "funding_related": sum(1 for e in capital_events if "funding" in e.get("event_type", "").lower())
        }
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 처리 완료: {len(capital_events)}개 자본 흐름 이벤트")
    print(f"   → {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

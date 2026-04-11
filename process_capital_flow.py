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

KNOWN_COMPANIES = {
    "tesla", "kia", "byd", "northvolt", "form energy", "enervenue", "amogy", "sunfire", 
    "ceres", "gridwiz", "sixtyhertz", "boralex", "tennet", "entergy", "xcel", "nextEra", 
    "eolus", "aypa", "lion energy", "zelestra", "tokyu land"
}

def extract_company_name(title: str) -> str:
    title_lower = title.lower()
    
    # 알려진 회사 우선 매칭
    for co in KNOWN_COMPANIES:
        if co in title_lower:
            # 원본 형태로 복원
            for word in title.split():
                if word.lower().startswith(co.split()[0]):
                    return word.replace(',', '').replace('’', '').strip()
    
    # 일반 회사명 패턴 (대문자로 시작하는 2~4단어)
    match = re.search(r'\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,3})\b', title)
    if match:
        candidate = match.group(1).strip()
        bad_words = {"the", "new", "first", "video", "roundup", "australia", "japanese", "european", "chinese"}
        if candidate.lower() not in bad_words and len(candidate) > 3:
            return candidate
    
    return "Unknown"

def calculate_capital_score(title: str, summary: str = "") -> int:
    text = (title + " " + summary).lower()
    score = 20

    strong_keywords = ["raises", "raised", "funding", "series a", "series b", "series c", "investment", "offtake", "ppa", "project finance", "financing"]
    if any(kw in text for kw in strong_keywords):
        score += 40

    if any(x in text for x in ["$100", "$200", "$300", "$400", "million", "billion", "억", "조"]):
        score += 25

    if any(kw in text for kw in ["contract", "deployment", "partnership", "pilot", "grant"]):
        score += 15

    return min(100, score)

def main():
    print(f"\n=== Energy Capital Flow Processor === {TODAY}\n")

    raw_file = RAW_DIR / f"{TODAY}.json"
    if not raw_file.exists():
        print(f"❌ raw 파일 없음: {raw_file}")
        return

    data = json.loads(raw_file.read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    capital_events = []
    for art in articles:
        title = art.get("title", "")
        summary = art.get("summary", "")
        
        score = calculate_capital_score(title, summary)
        if score < 30:
            continue

        company = extract_company_name(title)

        event = {
            "id": hashlib.md5(title.encode()).hexdigest()[:12],
            "event_type": "funding" if any(k in title.lower() for k in ["raises", "funding", "series"]) else "capital_signal",
            "title": title,
            "date": art.get("published_date", TODAY),
            "score": score,
            "company_name": company,
            "sector": "unknown",   # 나중에 더 세밀하게 분류 가능
            "source_name": art.get("source_name", "Unknown Source"),
            "source_url": art.get("url", ""),
            "why_important": "자본 흐름 / 투자 / 계약 관련 신호"
        }
        capital_events.append(event)

    capital_events.sort(key=lambda x: (-x["score"], x.get("date", "")), reverse=True)

    output = {
        "date": TODAY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_raw": len(articles),
        "total_capital_events": len(capital_events),
        "capital_flow_feed": capital_events[:50],
        "stats": {"high_score": sum(1 for e in capital_events if e["score"] >= 60)}
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(capital_events)}개 자본 흐름 이벤트 생성 완료")

if __name__ == "__main__":
    main()

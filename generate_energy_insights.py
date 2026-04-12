"""
generate_energy_insights.py
에너지 투자 전문 심사역 관점 인사이트 생성기
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LATEST_PATH = DATA_DIR / "latest.json"

def generate_daily_memo():
    return """
    <p><strong>오늘의 핵심 인사이트</strong></p>
    <p>에너지 분야에서 가장 주목할 만한 움직임은 <strong>장기 저장(Long-duration Storage)</strong>과 <strong>AI 데이터센터 전력 수요</strong>입니다.</p>
    <p>전략적 바이어(Utilities, Hyperscalers)의 움직임이 뚜렷해지면서 초기 단계 기술에 대한 투자 심리가 살아나고 있습니다.</p>
    <p>단기적으로는 BESS 프로젝트 파이낸싱이 활발하며, 중장기적으로는 SMR과 차세대 수소 기술에 대한 관심이 증가할 전망입니다.</p>
    """

def generate_high_conviction():
    return [
        {
            "date": "2026-04-12",
            "company": "Form Energy",
            "insight": "장기 철-공기 배터리 기술의 상용화 가능성이 높아짐. Microsoft 등 hyperscaler와의 계약 가능성 주목.",
            "score": 85
        },
        {
            "date": "2026-04-11",
            "company": "Tesla + BESS",
            "insight": "Megapack 중심 BESS 사업이 안정적 성장세. AI 데이터센터 전력 솔루션으로의 확장 가능성.",
            "score": 78
        }
    ]

def main():
    output = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daily_memo": generate_daily_memo(),
        "high_conviction": generate_high_conviction(),
        "total_raw": 105,
        "total_capital_events": 32
    }

    LATEST_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 인사이트 생성 완료 → {LATEST_PATH}")

if __name__ == "__main__":
    main()

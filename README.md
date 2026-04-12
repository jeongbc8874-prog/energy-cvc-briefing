# GRIDEDGE Pipeline — 세팅 가이드

## 구조
```
repo/
├── .github/workflows/weekly_brief.yml   # GitHub Actions 스케줄러
├── pipeline/
│   ├── generate_brief.py                # 메인 파이프라인
│   └── requirements.txt
└── docs/
    ├── index.html                       # 랜딩페이지 (Cloudflare Pages)
    ├── brief_latest.html                # 최신 브리프 (자동 갱신)
    ├── brief_latest.json
    └── briefs/                          # 주차별 아카이브
        └── 2025-W47.json
```

## GitHub Secrets 설정
repo → Settings → Secrets → Actions에 추가:

| Secret 이름        | 값                              | 필수 |
|--------------------|----------------------------------|------|
| ANTHROPIC_API_KEY  | sk-ant-...                       | ✅   |
| NEWSAPI_KEY        | newsapi.org에서 무료 발급        | 선택 |

NEWSAPI_KEY 없으면 더미 데이터로 파이프라인 테스트 가능.

## 로컬 테스트
```bash
cd pipeline
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python generate_brief.py
```

## 자동 실행 스케줄
- 매주 화요일 오전 10:00 KST 자동 실행
- 수동 실행: GitHub → Actions → Weekly Energy Brief Generation → Run workflow

## Cloudflare Pages 연동
- docs/ 폴더를 Cloudflare Pages 빌드 디렉토리로 지정
- GitHub push 시 자동 배포
- brief_latest.html → gridedge.io/brief_latest.html로 접근 가능

## 비용 추정 (월간)
| 항목               | 비용         |
|--------------------|--------------|
| GitHub Actions     | 무료 (2,000분/월) |
| Claude API (주 1회)| ~$0.5–1.5/회 |
| NewsAPI            | 무료 플랜 가능 |
| Cloudflare Pages   | 무료          |
| **합계**           | **$2–6/월**  |

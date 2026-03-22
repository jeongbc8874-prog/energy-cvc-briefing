# ⚡ Energy CVC Daily Briefing

Claude AI가 매일 오전 7시에 자동으로 에너지 투자 브리핑을 생성합니다.

---

## 🗂️ 파일 구조

```
energy-cvc-briefing/
├── index.html                      ← 브리핑 대시보드 (자동 생성됨)
├── generate.js                     ← Claude API 호출 스크립트
├── README.md                       ← 이 파일
└── .github/
    └── workflows/
        └── daily.yml               ← 매일 자동 실행 설정
```

---

## 🚀 최초 설정 가이드 (30분)

### STEP 1 — Anthropic API 키 발급 (5분)

1. https://console.anthropic.com 접속
2. 회원가입 → 로그인
3. 좌측 메뉴 **"API Keys"** 클릭
4. **"Create Key"** 버튼 클릭
5. 키 이름 입력 (예: `energy-cvc-briefing`)
6. 생성된 키 복사해서 안전한 곳에 저장
   - 예시: `sk-ant-api03-xxxxxxxxxxxx`

> ⚠️ API 키는 한 번만 표시됩니다. 반드시 복사해두세요!

---

### STEP 2 — GitHub 저장소 생성 (5분)

1. https://github.com 접속 → 회원가입/로그인
2. 우측 상단 **"+"** → **"New repository"**
3. Repository name: `energy-cvc-briefing`
4. **Private** 선택 (API 키 보안을 위해)
5. **"Create repository"** 클릭

**파일 업로드:**
1. 저장소 페이지에서 **"uploading an existing file"** 클릭
2. 아래 파일들을 드래그 앤 드롭:
   - `generate.js`
   - `README.md`
3. `.github/workflows/daily.yml` 은 별도 업로드:
   - **"Add file"** → **"Create new file"**
   - 파일명: `.github/workflows/daily.yml`
   - 내용 붙여넣기

---

### STEP 3 — Netlify 설정 (10분)

1. https://netlify.com 접속 → 회원가입/로그인
2. **"Add new site"** → **"Import an existing project"**
3. **"GitHub"** 선택 → 저장소 `energy-cvc-briefing` 선택
4. Build settings는 모두 비워두고 **"Deploy site"** 클릭
5. 배포 완료 후 URL 확인 (예: `https://amazing-name-123.netlify.app`)

**Netlify 토큰 발급:**
1. Netlify 우측 상단 아이콘 → **"User settings"**
2. **"Applications"** 탭 → **"New access token"**
3. 이름 입력 후 생성 → 토큰 복사

**Netlify Site ID 확인:**
1. 사이트 대시보드 → **"Site configuration"**
2. **"Site ID"** 복사 (예: `a1b2c3d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

---

### STEP 4 — GitHub Secrets 등록 (5분)

GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions** → **"New repository secret"**

아래 3개를 등록하세요:

| Secret 이름 | 값 |
|------------|-----|
| `ANTHROPIC_API_KEY` | Anthropic에서 발급받은 API 키 |
| `NETLIFY_AUTH_TOKEN` | Netlify에서 발급받은 토큰 |
| `NETLIFY_SITE_ID` | Netlify 사이트 ID |

---

### STEP 5 — 첫 번째 브리핑 수동 실행 (1분)

1. GitHub 저장소 → **"Actions"** 탭
2. **"Daily Energy CVC Briefing"** 클릭
3. **"Run workflow"** → **"Run workflow"** 버튼 클릭
4. 2~3분 후 초록색 체크 표시 확인
5. Netlify URL 접속 → 브리핑 확인! 🎉

---

## 📅 자동 실행 시간

매일 **오전 7:00 (한국시간)** 자동 실행됩니다.
언제든지 GitHub Actions에서 수동 실행도 가능합니다.

---

## 💰 예상 비용

| 항목 | 비용 |
|------|------|
| GitHub | 무료 |
| Netlify | 무료 |
| Anthropic API | 월 $3~10 (하루 5번 API 호출) |
| **합계** | **월 $3~10** |

---

## 🔧 문제 해결

**Actions가 실패하는 경우:**
- GitHub Actions 탭에서 실패한 단계 클릭 → 오류 메시지 확인
- Secrets가 올바르게 등록되었는지 확인

**브리핑이 오래된 경우:**
- Actions 탭 → "Run workflow"로 수동 실행

---

*Made with Claude AI · Anthropic*

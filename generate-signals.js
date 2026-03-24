/**
 * Energy CVC Daily Signal Generator v3
 * - 웹 검색 제거 (rate limit 원인)
 * - 전체 토픽을 2개 요청으로 묶어 처리
 * - 토큰 사용량 대폭 절감
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
if (!CLAUDE_KEY) { console.error("ANTHROPIC_API_KEY 없음"); process.exit(1); }

const TODAY    = new Date().toISOString().slice(0, 10);
const TODAY_KR = new Date().toLocaleDateString("ko-KR", {
  timeZone:"Asia/Seoul", year:"numeric", month:"long", day:"numeric", weekday:"long"
});
const WEEK_AGO = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

// ── Claude API (웹 검색 없음) ──────────────────────────────
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model:      "claude-sonnet-4-20250514",
      max_tokens: 4000,
      system,
      messages:   [{ role: "user", content: user }],
    });
    const req = https.request({
      hostname: "api.anthropic.com",
      path:     "/v1/messages",
      method:   "POST",
      headers: {
        "Content-Type":      "application/json",
        "x-api-key":         CLAUDE_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Length":    Buffer.byteLength(body),
      },
    }, res => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const p = JSON.parse(data);
          if (p.error) { reject(new Error(p.error.message)); return; }
          const text = (p.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
          resolve(text);
        } catch(e) { reject(e); }
      });
    });
    req.on("error", reject);
    req.setTimeout(90000, () => { req.destroy(); reject(new Error("Timeout")); });
    req.write(body);
    req.end();
  });
}

function parseJSON(text) {
  const clean = text.replace(/```json|```/g, "").trim();
  const s = clean.indexOf("["), e = clean.lastIndexOf("]");
  if (s === -1 || e === -1) throw new Error("JSON 없음: " + clean.slice(0, 100));
  try { return JSON.parse(clean.slice(s, e + 1)); }
  catch {
    const slice = clean.slice(s, e + 1);
    const last  = slice.lastIndexOf("},{");
    if (last > 0) {
      try { return JSON.parse(slice.slice(0, last + 1) + "]"); } catch {}
    }
    throw new Error("JSON 파싱 실패");
  }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 요청 1: 국내 + 중국 신호 ──────────────────────────────
async function fetchKrAndCn() {
  console.log("① 국내 + 중국 신호 수집 중...");

  const system = `당신은 에너지 인프라 전문 CVC 펀드의 시니어 심사역입니다.
오늘: ${TODAY_KR}
분석 기준: 최근 트렌드 + 알고 있는 실제 기업 정보 기반
비상장 스타트업 우선. JSON 배열만 반환. 마크다운 없음.`;

  const user = `다음 6개 에너지 섹터의 투자 신호를 각 3건씩, 총 18건 생성해주세요.
각 섹터별 실제 기업과 최신 트렌드를 반영하세요.

섹터:
1. 국내 ESS 스타트업 (스탠다드에너지, 씨에스에너지, 에너테크, 하나기술)
2. 국내 수소 스타트업 (하이리움산업, 에스퓨얼셀, 범한퓨얼셀, 이엠솔루션)
3. 국내 그리드 스타트업 (그리드위즈, 식스티헤르츠, 에너지에이아이)
4. 국내 선박/에너지 스타트업 (빈센, 범한퓨얼셀, 파나시아)
5. 중국 ESS/에너지 스타트업 (CATL 생태계 스타트업, 중국 그리드 스타트업)
6. 중국 수소/그리드 스타트업

JSON 배열 18개 반환:
[{
  "topicId": "kr_ess|kr_h2|kr_grid|kr_marine|cn_ess|cn_grid",
  "category": "섹터명",
  "emoji": "이모지",
  "title": "구체적 헤드라인",
  "company": "기업명",
  "companyType": "unlisted_startup|listed_corp|ecosystem",
  "fundingStage": "Seed|Pre-A|Series-A|Series-B|Series-C|N/A",
  "country": "KR 또는 CN",
  "pubDate": "2026-03 또는 최근",
  "source": "출처",
  "summary": "구체적 내용 2문장 (금액/파트너 포함)",
  "eventType": "Hiring|Pilot|Partnership|Grant|Certification|Expansion|Financing|Offtake|ProjectFinance",
  "signalStage": "Early|Commercial|Strategic",
  "relevance": "High|Medium|Low",
  "signal_type": "Pre-funding|Commercial traction|Technical validation|Market context",
  "next_action": "Investigate|Monitor|Note|Skip",
  "deep_insight": "심사역 딥 인사이트 3문장: TRL 단계, 상업화 경로, 투자 타이밍",
  "cvc_action": "구체적 투자 액션",
  "risk": "핵심 리스크",
  "isRealNews": false
}]

JSON만 반환.`;

  const text  = await callClaude(system, user);
  const items = parseJSON(text);
  return items.map(item => ({
    ...item,
    id:          `${item.topicId}-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
    region:      item.country === "CN" ? "CN" : "KR",
    isKorean:    item.country === "KR",
    isChina:     item.country === "CN",
    generatedAt: TODAY,
  }));
}

// ── 요청 2: 글로벌 신호 ────────────────────────────────────
async function fetchGlobal() {
  console.log("② 글로벌 신호 수집 중...");

  const system = `You are a senior CVC analyst specializing in energy infrastructure.
Today: ${TODAY_KR}
Focus: UNLISTED startups. Use real company knowledge. Return ONLY JSON array.`;

  const user = `Generate 18 investment signals (3 per sector) for these 6 global energy sectors.
Use real companies and latest market trends you know about.

Sectors:
1. Global ESS / Long Duration Storage startups
2. Global Green Hydrogen / Electrolyzer startups
3. Global Grid Software / VPP startups
4. Global Marine Decarbonization startups
5. Global HVDC / Transmission startups
6. Global SMR / Nuclear / DC Power startups

Return JSON array of 18:
[{
  "topicId": "g_ess|g_h2|g_grid|g_marine|g_hvdc|g_smr",
  "category": "sector label",
  "emoji": "emoji",
  "title": "specific headline",
  "company": "company name (prefer unlisted)",
  "companyType": "unlisted_startup|listed_corp|ecosystem",
  "fundingStage": "Seed|Series-A|Series-B|Series-C|Growth|N/A",
  "country": "2-letter code",
  "pubDate": "2026-03 or recent",
  "source": "source name",
  "summary": "2 specific sentences with amounts/partners",
  "eventType": "Hiring|Pilot|Partnership|Grant|Certification|Expansion|Financing|Offtake|ProjectFinance",
  "signalStage": "Early|Commercial|Strategic",
  "relevance": "High|Medium|Low",
  "signal_type": "Pre-funding|Commercial traction|Technical validation|Market context",
  "next_action": "Investigate|Monitor|Note|Skip",
  "deep_insight": "3 sentences: TRL stage, commercialization path, investment timing, moat",
  "cvc_action": "specific CVC action",
  "risk": "key risk",
  "isRealNews": false
}]

Return ONLY JSON.`;

  const text  = await callClaude(system, user);
  const items = parseJSON(text);
  return items.map(item => ({
    ...item,
    id:          `${item.topicId}-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
    region:      "GLOBAL",
    isKorean:    false,
    isChina:     false,
    generatedAt: TODAY,
  }));
}

// ── 요청 3: 딥 브리핑 ─────────────────────────────────────
async function generateBrief(signals) {
  console.log("③ 딥 브리핑 생성 중...");

  const highSignals = signals
    .filter(s => s.relevance === "High")
    .slice(0, 8)
    .map(s => `[${s.country}][${s.category}] ${s.company}: ${s.title}`)
    .join("\n");

  const system = "에너지 CVC 시니어 심사역. 딥 인사이트 내부 브리핑. 한국어. 비상장 스타트업 중심.";
  const user   = `오늘(${TODAY_KR}) CVC 딥 브리핑 5-6문장.

주요 신호:
${highSignals}

작성:
1. 이번 주 가장 중요한 비상장 투자기회 2-3건 (이유 포함)
2. 국내 정책/규제 연계 기회
3. 중국 시장이 국내 스타트업에 주는 시사점
4. 대기업 파트너십에서 읽는 비상장 투자 기회
5. 즉시 액션 + 모니터링 포인트

구체적 회사명·수치 필수. 표면적 요약 금지.`;

  return callClaude(system, user);
}

// ── 메인 ───────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v3`);
  console.log(`날짜: ${TODAY_KR}`);
  console.log(`※ 웹검색 없이 Claude 지식 기반 분석\n`);

  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  let allSignals = [];

  // 요청 1: 국내 + 중국
  try {
    const items = await fetchKrAndCn();
    allSignals.push(...items);
    const kr = items.filter(s => s.isKorean).length;
    const cn = items.filter(s => s.isChina).length;
    console.log(`  ✓ ${items.length}건 (국내 ${kr}, 중국 ${cn})`);
  } catch(e) {
    console.error(`  ✗ 국내/중국 실패: ${e.message}`);
  }

  // 요청 사이 30초 대기 (rate limit 완전 초기화)
  console.log("  ⏱ 30초 대기 (rate limit 초기화)...");
  await delay(30000);

  // 요청 2: 글로벌
  try {
    const items = await fetchGlobal();
    allSignals.push(...items);
    console.log(`  ✓ ${items.length}건 (글로벌)`);
  } catch(e) {
    console.error(`  ✗ 글로벌 실패: ${e.message}`);
  }

  // 비상장 우선 정렬
  allSignals.sort((a, b) => {
    const sa = (a.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[a.relevance]||0);
    const sb = (b.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[b.relevance]||0);
    return sb - sa;
  });

  // 30초 대기 후 브리핑
  console.log("  ⏱ 30초 대기...");
  await delay(30000);

  let brief = "";
  if (allSignals.length > 0) {
    try {
      brief = await generateBrief(allSignals);
      console.log(`  ✓ 브리핑 완료`);
    } catch(e) {
      console.error(`  ✗ 브리핑 실패: ${e.message}`);
    }
  }

  // 통계
  const stats = {
    total:       allSignals.length,
    unlisted:    allSignals.filter(s => s.companyType === "unlisted_startup").length,
    kr:          allSignals.filter(s => s.isKorean).length,
    cn:          allSignals.filter(s => s.isChina).length,
    global:      allSignals.filter(s => !s.isKorean && !s.isChina).length,
    high:        allSignals.filter(s => s.relevance === "High").length,
    investigate: allSignals.filter(s => s.next_action === "Investigate").length,
  };

  const output = {
    date: TODAY, dateKr: TODAY_KR, weekAgo: WEEK_AGO,
    generatedAt: new Date().toISOString(),
    brief, stats, signals: allSignals, errors: [],
  };

  // 저장
  fs.writeFileSync(path.join(dataDir, `${TODAY}.json`), JSON.stringify(output, null, 2), "utf8");
  fs.writeFileSync(path.join(dataDir, "latest.json"),   JSON.stringify(output, null, 2), "utf8");

  // index.json
  const indexPath = path.join(dataDir, "index.json");
  let index = [];
  if (fs.existsSync(indexPath)) {
    try { index = JSON.parse(fs.readFileSync(indexPath, "utf8")); } catch {}
  }
  if (!index.find(d => d.date === TODAY)) {
    index.unshift({ date: TODAY, dateKr: TODAY_KR, stats });
    fs.writeFileSync(indexPath, JSON.stringify(index.slice(0, 90), null, 2), "utf8");
  }

  console.log(`\n✅ 완료!`);
  console.log(`총 ${stats.total}건 | 비상장 ${stats.unlisted} | High ${stats.high}`);
  console.log(`국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}\n`);
}

main().catch(e => { console.error("❌ 오류:", e.message); process.exit(1); });

/**
 * Energy CVC Daily Signal Generator v4
 * 핵심 수정: JSON 파싱 로직 강화
 * - 응답 전체에서 JSON 배열을 더 유연하게 추출
 * - 웹검색 없음 (rate limit 방지)
 * - 요청 2개로 묶어서 처리
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

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Claude API ─────────────────────────────────────────────
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
          const parsed = JSON.parse(data);
          if (parsed.error) { reject(new Error(parsed.error.message)); return; }
          const text = (parsed.content || [])
            .filter(b => b.type === "text")
            .map(b => b.text)
            .join("\n");
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

// ── JSON 파싱 (핵심 개선) ──────────────────────────────────
// Claude가 JSON 앞뒤에 텍스트를 붙여도 올바르게 추출
function extractJSON(text) {
  // 방법 1: ```json ... ``` 블록 추출
  const codeBlock = text.match(/```(?:json)?\s*(\[[\s\S]*?\])\s*```/);
  if (codeBlock) {
    try { return JSON.parse(codeBlock[1]); } catch {}
  }

  // 방법 2: 첫 번째 [ 부터 마지막 ] 까지
  const start = text.indexOf("[");
  const end   = text.lastIndexOf("]");
  if (start !== -1 && end !== -1 && end > start) {
    const slice = text.slice(start, end + 1);
    try { return JSON.parse(slice); } catch {}

    // 방법 3: 불완전한 JSON 복구 (마지막 완전한 객체까지만)
    const objects = [];
    let depth = 0, objStart = -1;
    for (let i = 0; i < slice.length; i++) {
      if (slice[i] === "{") { if (depth === 0) objStart = i; depth++; }
      else if (slice[i] === "}") {
        depth--;
        if (depth === 0 && objStart !== -1) {
          try {
            objects.push(JSON.parse(slice.slice(objStart, i + 1)));
          } catch {}
          objStart = -1;
        }
      }
    }
    if (objects.length > 0) {
      console.log(`  ⚠ JSON 복구: ${objects.length}개 객체 추출`);
      return objects;
    }
  }

  throw new Error("JSON 추출 실패. 응답 앞부분: " + text.slice(0, 200));
}

// ── 국내 + 중국 신호 생성 ─────────────────────────────────
async function fetchKrCn() {
  console.log("① 국내 + 중국 신호 수집 중...");

  const system = `당신은 에너지 인프라 전문 CVC 펀드의 시니어 심사역입니다.
오늘: ${TODAY_KR}
규칙: 반드시 JSON 배열 [ ] 만 출력. 설명 텍스트 절대 금지.`;

  const user = `아래 6개 섹터의 에너지 투자 신호를 각 3건씩 총 18건 생성하세요.

섹터:
1. 국내 ESS 스타트업 (스탠다드에너지, 씨에스에너지, 에너테크, 하나기술, 에이치에너지)
2. 국내 수소 스타트업 (하이리움산업, 에스퓨얼셀, 범한퓨얼셀, 이엠솔루션)
3. 국내 그리드 스타트업 (그리드위즈, 식스티헤르츠, 에너지에이아이, 이노원)
4. 국내 선박 스타트업 (빈센, 범한퓨얼셀, 파나시아, HiNAV)
5. 중국 ESS 스타트업 (CATL 생태계, Pylontech, REPT, BYD 관련 스타트업)
6. 중국 수소/그리드 (SINOHY, Peric, Sungrow, 중국 VPP 스타트업)

출력 형식 — 반드시 아래 JSON 배열만 출력, 다른 텍스트 없이:
[
{"topicId":"kr_ess","category":"국내 ESS 스타트업","emoji":"🇰🇷🔋","title":"제목","company":"기업명","companyType":"unlisted_startup","fundingStage":"Series-A","country":"KR","pubDate":"2026-03","source":"출처","summary":"내용 2문장","eventType":"Financing","signalStage":"Early","relevance":"High","signal_type":"Pre-funding","next_action":"Investigate","deep_insight":"인사이트 3문장","cvc_action":"액션","risk":"리스크","isRealNews":false},
...
]`;

  const text  = await callClaude(system, user);
  console.log(`  응답 길이: ${text.length}자`);
  const items = extractJSON(text);
  console.log(`  ✓ ${items.length}건 파싱 완료`);
  return items.map(item => ({
    ...item,
    id:          `${item.topicId||"kr"}-${Date.now()}-${Math.random().toString(36).slice(2,5)}`,
    region:      item.country === "CN" ? "CN" : "KR",
    isKorean:    item.country === "KR",
    isChina:     item.country === "CN",
    generatedAt: TODAY,
  }));
}

// ── 글로벌 신호 생성 ──────────────────────────────────────
async function fetchGlobal() {
  console.log("② 글로벌 신호 수집 중...");

  const system = `You are a senior CVC analyst specializing in energy infrastructure.
Today: ${TODAY_KR}
Rule: Output ONLY a JSON array [ ]. No explanatory text whatsoever.`;

  const user = `Generate 18 energy investment signals (3 per sector) for these 6 sectors.

Sectors:
1. Global ESS / Long Duration Storage (Form Energy, Ambri, ESS Inc, Invinity, CMBlu)
2. Global Green Hydrogen (Sunfire, Nel, Hysata, Verdagy, Electric Hydrogen)
3. Global Grid Software / VPP (AutoGrid, Voltus, CPower, Leap, Upside Energy)
4. Global Marine Decarbonization (Ceres Power, Ballard, Freudenberg, CMB.TECH)
5. Global HVDC / Offshore Wind Infra (startups in cable accessories, grid interconnection)
6. Global SMR / Nuclear / Advanced Energy (NuScale, Oklo, Kairos, Commonwealth Fusion)

Output format — ONLY the JSON array, nothing else:
[
{"topicId":"g_ess","category":"Global ESS","emoji":"🌍🔋","title":"headline","company":"company","companyType":"unlisted_startup","fundingStage":"Series-B","country":"US","pubDate":"2026-03","source":"source","summary":"2 sentences","eventType":"Financing","signalStage":"Commercial","relevance":"High","signal_type":"Commercial traction","next_action":"Investigate","deep_insight":"3 sentences of insight","cvc_action":"action","risk":"risk","isRealNews":false},
...
]`;

  const text  = await callClaude(system, user);
  console.log(`  응답 길이: ${text.length}자`);
  const items = extractJSON(text);
  console.log(`  ✓ ${items.length}건 파싱 완료`);
  return items.map(item => ({
    ...item,
    id:          `${item.topicId||"g"}-${Date.now()}-${Math.random().toString(36).slice(2,5)}`,
    region:      "GLOBAL",
    isKorean:    false,
    isChina:     false,
    generatedAt: TODAY,
  }));
}

// ── 브리핑 생성 ────────────────────────────────────────────
async function generateBrief(signals) {
  console.log("③ 브리핑 생성 중...");
  const top = signals
    .filter(s => s.relevance === "High")
    .slice(0, 8)
    .map(s => `[${s.country}][${s.category}] ${s.company}: ${s.title}`)
    .join("\n");

  return callClaude(
    "에너지 CVC 시니어 심사역. 딥 인사이트 내부 브리핑. 한국어. 비상장 스타트업 중심.",
    `오늘(${TODAY_KR}) CVC 딥 브리핑 5-6문장.\n\n주요신호:\n${top}\n\n1)비상장 투자기회 2)국내정책 3)중국시사점 4)즉시액션 5)모니터링\n\n구체적 회사명·수치 필수.`
  );
}

// ── 메인 ───────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v4`);
  console.log(`날짜: ${TODAY_KR}\n`);

  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  let allSignals = [];

  // ① 국내 + 중국
  try {
    const items = await fetchKrCn();
    allSignals.push(...items);
    console.log(`  소계: 국내 ${items.filter(s=>s.isKorean).length}건, 중국 ${items.filter(s=>s.isChina).length}건`);
  } catch(e) {
    console.error(`  ✗ 국내/중국 실패: ${e.message}`);
  }

  console.log("  ⏱ 30초 대기...");
  await delay(30000);

  // ② 글로벌
  try {
    const items = await fetchGlobal();
    allSignals.push(...items);
    console.log(`  소계: 글로벌 ${items.length}건`);
  } catch(e) {
    console.error(`  ✗ 글로벌 실패: ${e.message}`);
  }

  // 비상장 우선 정렬
  allSignals.sort((a, b) => {
    const sa = (a.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[a.relevance]||0);
    const sb = (b.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[b.relevance]||0);
    return sb - sa;
  });

  console.log("  ⏱ 30초 대기...");
  await delay(30000);

  // ③ 브리핑
  let brief = "";
  if (allSignals.length > 0) {
    try {
      brief = await generateBrief(allSignals);
      console.log("  ✓ 브리핑 완료");
    } catch(e) {
      console.error(`  ✗ 브리핑 실패: ${e.message}`);
    }
  }

  const stats = {
    total:       allSignals.length,
    unlisted:    allSignals.filter(s => s.companyType==="unlisted_startup").length,
    kr:          allSignals.filter(s => s.isKorean).length,
    cn:          allSignals.filter(s => s.isChina).length,
    global:      allSignals.filter(s => !s.isKorean && !s.isChina).length,
    high:        allSignals.filter(s => s.relevance==="High").length,
    investigate: allSignals.filter(s => s.next_action==="Investigate").length,
  };

  const output = {
    date:TODAY, dateKr:TODAY_KR,
    generatedAt: new Date().toISOString(),
    brief, stats, signals: allSignals, errors: [],
  };

  // 파일 저장
  fs.writeFileSync(path.join(dataDir, `${TODAY}.json`), JSON.stringify(output, null, 2), "utf8");
  fs.writeFileSync(path.join(dataDir, "latest.json"),   JSON.stringify(output, null, 2), "utf8");

  // index.json 업데이트
  const indexPath = path.join(dataDir, "index.json");
  let index = [];
  if (fs.existsSync(indexPath)) {
    try { index = JSON.parse(fs.readFileSync(indexPath, "utf8")); } catch {}
  }
  if (!index.find(d => d.date === TODAY)) {
    index.unshift({ date:TODAY, dateKr:TODAY_KR, stats });
    fs.writeFileSync(indexPath, JSON.stringify(index.slice(0,90), null, 2), "utf8");
  }

  console.log(`\n✅ 완료!`);
  console.log(`총 ${stats.total}건 | 비상장 ${stats.unlisted} | High ${stats.high}`);
  console.log(`국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}\n`);
}

main().catch(e => { console.error("❌ 치명적 오류:", e.message); process.exit(1); });

/**
 * Energy CVC Daily Signal Generator v5
 * 수정: JSON 파싱 완전 강화 - 줄바꿈/공백 처리
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

// ── JSON 파싱 (최강 버전) ──────────────────────────────────
function extractJSON(rawText) {
  // 1. 응답 전체 로그 (디버깅용)
  console.log(`  [디버그] 응답 앞 300자: ${rawText.slice(0, 300)}`);

  // 2. 불필요한 공백/줄바꿈 정리
  const text = rawText.trim();

  // 3. ```json 또는 ``` 코드블록 안의 JSON 추출
  const codeMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (codeMatch) {
    try {
      const result = JSON.parse(codeMatch[1].trim());
      console.log(`  [파싱] 코드블록에서 ${result.length}건 추출`);
      return result;
    } catch(e) { console.log(`  [파싱] 코드블록 파싱 실패: ${e.message}`); }
  }

  // 4. [ 로 시작하는 위치 찾기 (공백/줄바꿈 무시)
  let startIdx = -1;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "[") { startIdx = i; break; }
  }

  if (startIdx === -1) throw new Error("JSON 배열 시작([) 없음");

  // 5. 괄호 매칭으로 완전한 JSON 배열 찾기
  let depth = 0;
  let endIdx = -1;
  for (let i = startIdx; i < text.length; i++) {
    if      (text[i] === "[") depth++;
    else if (text[i] === "]") { depth--; if (depth === 0) { endIdx = i; break; } }
  }

  if (endIdx === -1) {
    // 6. 불완전한 JSON → 개별 객체 추출
    console.log("  [파싱] 불완전한 JSON, 개별 객체 추출 시도...");
    const objects = [];
    let objDepth = 0, objStart = -1;
    for (let i = startIdx; i < text.length; i++) {
      if (text[i] === "{") { if (objDepth === 0) objStart = i; objDepth++; }
      else if (text[i] === "}") {
        objDepth--;
        if (objDepth === 0 && objStart !== -1) {
          try { objects.push(JSON.parse(text.slice(objStart, i + 1))); } catch {}
          objStart = -1;
        }
      }
    }
    if (objects.length > 0) {
      console.log(`  [파싱] 복구 성공: ${objects.length}건`);
      return objects;
    }
    throw new Error("JSON 복구 실패");
  }

  // 7. 완전한 JSON 파싱
  const jsonStr = text.slice(startIdx, endIdx + 1);
  try {
    const result = JSON.parse(jsonStr);
    console.log(`  [파싱] 정상 파싱: ${result.length}건`);
    return result;
  } catch(e) {
    // 8. 마지막 시도: 후행 쉼표 제거 후 파싱
    const fixed = jsonStr
      .replace(/,\s*}/g, "}")   // 객체 내 후행 쉼표
      .replace(/,\s*]/g, "]");  // 배열 내 후행 쉼표
    try {
      const result = JSON.parse(fixed);
      console.log(`  [파싱] 수정 후 파싱: ${result.length}건`);
      return result;
    } catch(e2) {
      throw new Error(`JSON 파싱 최종 실패: ${e2.message}`);
    }
  }
}

// ── 국내 + 중국 신호 ──────────────────────────────────────
async function fetchKrCn() {
  console.log("① 국내 + 중국 신호 수집 중...");
  const system = `에너지 CVC 시니어 심사역. 오늘: ${TODAY_KR}. 반드시 유효한 JSON 배열만 출력.`;
  const user = `6개 섹터 × 3건 = 18건 투자 신호 생성.

섹터1(kr_ess): 국내ESS스타트업 - 스탠다드에너지,씨에스에너지,에너테크,하나기술
섹터2(kr_h2): 국내수소스타트업 - 하이리움산업,에스퓨얼셀,범한퓨얼셀,이엠솔루션
섹터3(kr_grid): 국내그리드스타트업 - 그리드위즈,식스티헤르츠,에너지에이아이
섹터4(kr_marine): 국내선박스타트업 - 빈센,범한퓨얼셀,파나시아
섹터5(cn_ess): 중국ESS스타트업 - Pylontech,REPT,Gotion,EVE Energy 생태계
섹터6(cn_grid): 중국수소/그리드 - SINOHY,Sungrow,Goldwind 생태계스타트업

JSON 배열만 출력 (다른 텍스트 없이):
[{"topicId":"kr_ess","category":"국내 ESS 스타트업","emoji":"🇰🇷🔋","title":"제목","company":"기업명","companyType":"unlisted_startup","fundingStage":"Series-A","country":"KR","pubDate":"2026-03","source":"출처","summary":"내용2문장","eventType":"Financing","signalStage":"Commercial","relevance":"High","signal_type":"Pre-funding","next_action":"Investigate","deep_insight":"인사이트3문장","cvc_action":"액션","risk":"리스크","isRealNews":false},{"topicId":"kr_ess","category":"국내 ESS 스타트업","emoji":"🇰🇷🔋","title":"제목2","company":"기업명2","companyType":"unlisted_startup","fundingStage":"Pre-A","country":"KR","pubDate":"2026-03","source":"출처","summary":"내용","eventType":"Pilot","signalStage":"Early","relevance":"Medium","signal_type":"Technical validation","next_action":"Monitor","deep_insight":"인사이트","cvc_action":"액션","risk":"리스크","isRealNews":false}]

위 예시처럼 18개 객체를 담은 완전한 JSON 배열을 출력하세요.`;

  const text  = await callClaude(system, user);
  console.log(`  응답 길이: ${text.length}자`);
  const items = extractJSON(text);
  return items.map((item, i) => ({
    ...item,
    id:          `${(item.topicId||"kr").replace(/[^a-z_]/g,"")}-${Date.now()}-${i}`,
    region:      (item.country||"KR") === "CN" ? "CN" : "KR",
    isKorean:    (item.country||"KR") !== "CN",
    isChina:     (item.country||"KR") === "CN",
    generatedAt: TODAY,
  }));
}

// ── 글로벌 신호 ───────────────────────────────────────────
async function fetchGlobal() {
  console.log("② 글로벌 신호 수집 중...");
  const system = `Senior energy CVC analyst. Today: ${TODAY_KR}. Output ONLY valid JSON array.`;
  const user = `Generate 18 investment signals (3 per sector).

Sector1(g_ess): Global ESS - Form Energy, Ambri, ESS Inc, Invinity, CMBlu, Hydrostor
Sector2(g_h2): Global Hydrogen - Sunfire, Hysata, Electric Hydrogen, Verdagy, H2Pro
Sector3(g_grid): Global Grid/VPP - AutoGrid, Voltus, Leap, Upside Energy, Sympower
Sector4(g_marine): Marine Decarbonization - Ceres Power, Freudenberg, CMB.TECH, WE Tech
Sector5(g_hvdc): HVDC/Offshore - Nexans, NKT, grid accessories startups
Sector6(g_smr): Advanced Nuclear - Oklo, Kairos, Commonwealth Fusion, TAE Technologies

Output ONLY JSON array (no other text):
[{"topicId":"g_ess","category":"Global ESS","emoji":"🌍🔋","title":"headline","company":"company","companyType":"unlisted_startup","fundingStage":"Series-B","country":"US","pubDate":"2026-03","source":"source","summary":"2 sentences","eventType":"Financing","signalStage":"Commercial","relevance":"High","signal_type":"Commercial traction","next_action":"Investigate","deep_insight":"3 sentences","cvc_action":"action","risk":"risk","isRealNews":false},{"topicId":"g_ess","category":"Global ESS","emoji":"🌍🔋","title":"headline2","company":"company2","companyType":"unlisted_startup","fundingStage":"Series-A","country":"UK","pubDate":"2026-03","source":"source","summary":"summary","eventType":"Pilot","signalStage":"Early","relevance":"Medium","signal_type":"Technical validation","next_action":"Monitor","deep_insight":"insight","cvc_action":"action","risk":"risk","isRealNews":false}]

Return 18 objects total in valid JSON array.`;

  const text  = await callClaude(system, user);
  console.log(`  응답 길이: ${text.length}자`);
  const items = extractJSON(text);
  return items.map((item, i) => ({
    ...item,
    id:          `${(item.topicId||"g").replace(/[^a-z_]/g,"")}-${Date.now()}-${i}`,
    region:      "GLOBAL",
    isKorean:    false,
    isChina:     false,
    generatedAt: TODAY,
  }));
}

// ── 브리핑 ────────────────────────────────────────────────
async function generateBrief(signals) {
  console.log("③ 브리핑 생성 중...");
  const top = signals.filter(s => s.relevance === "High").slice(0, 8)
    .map(s => `[${s.country||""}][${s.category||""}] ${s.company||""}: ${s.title||""}`).join("\n");
  return callClaude(
    "에너지 CVC 시니어 심사역. 딥 인사이트. 한국어.",
    `오늘(${TODAY_KR}) CVC 브리핑 5문장.\n주요신호:\n${top}\n\n비상장투자기회, 국내정책연계, 중국시사점, 즉시액션, 모니터링. 구체적 수치·회사명 필수.`
  );
}

// ── 메인 ───────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v5`);
  console.log(`날짜: ${TODAY_KR}\n`);

  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  let allSignals = [];

  try {
    const items = await fetchKrCn();
    allSignals.push(...items);
    console.log(`  국내 ${items.filter(s=>s.isKorean).length}건, 중국 ${items.filter(s=>s.isChina).length}건`);
  } catch(e) { console.error(`  ✗ 국내/중국: ${e.message}`); }

  console.log("  ⏱ 30초 대기..."); await delay(30000);

  try {
    const items = await fetchGlobal();
    allSignals.push(...items);
    console.log(`  글로벌 ${items.length}건`);
  } catch(e) { console.error(`  ✗ 글로벌: ${e.message}`); }

  // 비상장 우선 정렬
  allSignals.sort((a, b) => {
    const sa = (a.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[a.relevance]||0);
    const sb = (b.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[b.relevance]||0);
    return sb - sa;
  });

  console.log("  ⏱ 30초 대기..."); await delay(30000);

  let brief = "";
  if (allSignals.length > 0) {
    try { brief = await generateBrief(allSignals); console.log("  ✓ 브리핑"); }
    catch(e) { console.error(`  ✗ 브리핑: ${e.message}`); }
  }

  const stats = {
    total:       allSignals.length,
    unlisted:    allSignals.filter(s=>s.companyType==="unlisted_startup").length,
    kr:          allSignals.filter(s=>s.isKorean).length,
    cn:          allSignals.filter(s=>s.isChina).length,
    global:      allSignals.filter(s=>!s.isKorean&&!s.isChina).length,
    high:        allSignals.filter(s=>s.relevance==="High").length,
    investigate: allSignals.filter(s=>s.next_action==="Investigate").length,
  };

  const output = { date:TODAY, dateKr:TODAY_KR, generatedAt:new Date().toISOString(), brief, stats, signals:allSignals, errors:[] };
  fs.writeFileSync(path.join(dataDir,`${TODAY}.json`), JSON.stringify(output,null,2), "utf8");
  fs.writeFileSync(path.join(dataDir,"latest.json"),   JSON.stringify(output,null,2), "utf8");

  const idxPath = path.join(dataDir,"index.json");
  let idx = [];
  if (fs.existsSync(idxPath)) { try { idx = JSON.parse(fs.readFileSync(idxPath,"utf8")); } catch {} }
  if (!idx.find(d=>d.date===TODAY)) {
    idx.unshift({date:TODAY,dateKr:TODAY_KR,stats});
    fs.writeFileSync(idxPath, JSON.stringify(idx.slice(0,90),null,2), "utf8");
  }

  console.log(`\n✅ 완료! 총 ${stats.total}건 | 비상장 ${stats.unlisted} | High ${stats.high}`);
  console.log(`국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}\n`);
}

main().catch(e => { console.error("❌ 오류:", e.message); process.exit(1); });

/**
 * Energy CVC Daily Signal Generator v2
 * Rate limit 해결: 토픽 간 대기 시간 증가 + 프롬프트 최적화
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

// ── 토픽 목록 (프롬프트 최소화) ────────────────────────────
const TOPICS = [
  // 국내
  { id:"kr_ess",      label:"국내 ESS 스타트업",     emoji:"🇰🇷🔋", region:"KR",
    companies:"스탠다드에너지,씨에스에너지,에너테크인터내셔널,하나기술,에이치에너지",
    q:"한국 ESS 배터리 스타트업 투자 계약 펀딩 2025 2026" },
  { id:"kr_h2",       label:"국내 수소 스타트업",     emoji:"🇰🇷💧", region:"KR",
    companies:"하이리움산업,에스퓨얼셀,범한퓨얼셀,이엠솔루션,그린수소시스템",
    q:"한국 수소 연료전지 스타트업 투자 파트너십 2025 2026" },
  { id:"kr_grid",     label:"국내 그리드 스타트업",   emoji:"🇰🇷⚡", region:"KR",
    companies:"그리드위즈,식스티헤르츠,에너지에이아이,이노원",
    q:"그리드위즈 식스티헤르츠 VPP 스마트그리드 투자 2025 2026" },
  { id:"kr_startup",  label:"국내 에너지 스타트업",   emoji:"🇰🇷🚀", region:"KR",
    companies:"빈센,하이리움산업,에너지X,클린일렉스,에스퓨얼셀",
    q:"한국 에너지 스타트업 시리즈 투자 펀딩 2025 2026" },
  // 글로벌
  { id:"g_ess",       label:"Global ESS",            emoji:"🌍🔋", region:"GLOBAL",
    q:"energy storage startup funding investment deal 2025 2026 recent" },
  { id:"g_h2",        label:"Global Hydrogen",       emoji:"🌍💧", region:"GLOBAL",
    q:"green hydrogen electrolyzer fuel cell startup funding deal 2025 2026" },
  { id:"g_grid",      label:"Global Grid/VPP",       emoji:"🌍⚡", region:"GLOBAL",
    q:"virtual power plant VPP grid software startup investment contract 2025 2026" },
  { id:"g_marine",    label:"Global Marine",         emoji:"🌍🚢", region:"GLOBAL",
    q:"marine shipping decarbonization fuel cell ammonia startup deal 2025 2026" },
  { id:"g_hvdc",      label:"Global HVDC",           emoji:"🌍🔌", region:"GLOBAL",
    q:"HVDC offshore wind transmission startup investment 2025 2026" },
  { id:"g_smr",       label:"Global SMR/Nuclear",    emoji:"🌍☢️", region:"GLOBAL",
    q:"small modular reactor SMR nuclear startup investment deal 2025 2026" },
  // 중국
  { id:"cn_ess",      label:"China ESS",             emoji:"🇨🇳🔋", region:"CN",
    q:"China energy storage startup investment deal 2025 2026 recent" },
  { id:"cn_h2",       label:"China Hydrogen",        emoji:"🇨🇳💧", region:"CN",
    q:"China green hydrogen electrolyzer startup investment 2025 2026" },
  { id:"cn_grid",     label:"China Grid/VPP",        emoji:"🇨🇳⚡", region:"CN",
    q:"China virtual power plant VPP grid startup investment policy 2025 2026" },
];

// ── Claude API (간결한 프롬프트) ───────────────────────────
function callClaude(systemMsg, userMsg) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2000,          // 4000 → 2000으로 절반 감소
      system: systemMsg,
      tools: [{ type: "web_search_20250305", name: "web_search" }],
      messages: [{ role: "user", content: userMsg }],
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
    req.setTimeout(60000, () => { req.destroy(); reject(new Error("Timeout")); });
    req.write(body);
    req.end();
  });
}

function parseJSON(text) {
  const clean = text.replace(/```json|```/g, "").trim();
  const s = clean.indexOf("["), e = clean.lastIndexOf("]");
  if (s === -1 || e === -1) throw new Error("JSON 없음");
  try { return JSON.parse(clean.slice(s, e + 1)); }
  catch {
    // 불완전 JSON 복구
    const slice = clean.slice(s, e + 1);
    const lastObj = slice.lastIndexOf("},{");
    if (lastObj > 0) {
      try { return JSON.parse(slice.slice(0, lastObj + 1) + "]"); } catch {}
    }
    throw new Error("JSON 파싱 실패");
  }
}

// ── 간결한 프롬프트 (토큰 절약) ────────────────────────────
function buildPrompt(topic) {
  const isKr = topic.region === "KR";
  const isCn = topic.region === "CN";

  const system = isKr
    ? `에너지 CVC 시니어 심사역. 최근 7일(${WEEK_AGO} 이후) 실제 뉴스만. 비상장 스타트업 우선. JSON 배열만 반환.`
    : `Senior energy CVC analyst. Only news after ${WEEK_AGO}. Prefer unlisted startups. Return ONLY JSON array.`;

  const schema = `[{"title":"","company":"","companyType":"unlisted_startup|listed_corp|ecosystem","fundingStage":"Seed|Pre-A|Series-A|Series-B|N/A","country":"${isKr?"KR":isCn?"CN":"XX"}","pubDate":"","source":"","summary":"","eventType":"Hiring|Pilot|Partnership|Grant|Certification|Expansion|Financing|Offtake|ProjectFinance","relevance":"High|Medium|Low","signal_type":"Pre-funding|Commercial traction|Technical validation|Market context","next_action":"Investigate|Monitor|Note|Skip","deep_insight":"","cvc_action":"","risk":"","isRealNews":true}]`;

  const user = isKr
    ? `검색: "${topic.q}"\n대상기업: ${topic.companies}\n\n최근7일 실제뉴스 기반 투자신호 3건:\n${schema}\n\nJSON만 반환.`
    : `Search: "${topic.q}"${isCn?"\nFocus: Chinese energy market.":""}\n\nReal news last 7 days, 3 investment signals:\n${schema}\n\nReturn ONLY JSON.`;

  return { system, user };
}

// ── 토픽별 수집 ────────────────────────────────────────────
async function fetchTopic(topic) {
  const { system, user } = buildPrompt(topic);
  const text  = await callClaude(system, user);
  const items = parseJSON(text);
  return items.map((item, i) => ({
    ...item,
    id:          `${topic.id}-${i}-${Date.now()}`,
    topicId:     topic.id,
    category:    topic.label,
    emoji:       topic.emoji,
    region:      topic.region,
    isKorean:    topic.region === "KR",
    isChina:     topic.region === "CN",
    generatedAt: TODAY,
  }));
}

// ── 브리핑 (간결) ──────────────────────────────────────────
async function generateBrief(signals) {
  const top = signals
    .filter(s => s.relevance === "High")
    .slice(0, 6)
    .map(s => `[${s.region}][${s.category}] ${s.company}: ${s.title}`)
    .join("\n");

  const system = "에너지 CVC 시니어 심사역. 딥 인사이트 위주 내부 브리핑. 한국어. 비상장 스타트업 중심.";
  const user   = `오늘(${TODAY_KR}) CVC 브리핑 5문장 작성.\n\n주요신호:\n${top}\n\n내용: 1)비상장 투자기회 2)국내정책연계 3)중국시장시사점 4)즉시액션 5)모니터링포인트\n\n구체적 회사명·수치 필수.`;

  return callClaude(system, user);
}

// ── 메인 ───────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v2`);
  console.log(`날짜: ${TODAY_KR} | 범위: ${WEEK_AGO} 이후\n`);

  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  const allSignals = [];
  const errors     = [];

  for (let i = 0; i < TOPICS.length; i++) {
    const topic = TOPICS[i];
    console.log(`→ ${topic.emoji} ${topic.label}...`);

    try {
      const items = await fetchTopic(topic);
      // 비상장 우선 정렬
      items.sort((a, b) => {
        const sa = (a.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[a.relevance]||0);
        const sb = (b.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[b.relevance]||0);
        return sb - sa;
      });
      allSignals.push(...items);
      const u = items.filter(x => x.companyType === "unlisted_startup").length;
      console.log(`  ✓ ${items.length}건 (비상장 ${u}, High ${items.filter(x=>x.relevance==="High").length})`);
    } catch(e) {
      console.error(`  ✗ 실패: ${e.message}`);
      errors.push({ topic: topic.id, error: e.message });
    }

    // ── Rate limit 방지: 토픽 사이 3초 대기 ──────────────
    if (i < TOPICS.length - 1) {
      console.log(`  ⏱ 3초 대기...`);
      await new Promise(r => setTimeout(r, 3000));
    }
  }

  // 브리핑
  let brief = "";
  if (allSignals.length > 0) {
    console.log(`\n② 브리핑 생성 중...`);
    await new Promise(r => setTimeout(r, 3000)); // 브리핑 전도 대기
    try {
      brief = await generateBrief(allSignals);
      console.log(`  ✓ 완료`);
    } catch(e) {
      console.error(`  ✗ 브리핑 실패: ${e.message}`);
    }
  }

  const output = {
    date:        TODAY,
    dateKr:      TODAY_KR,
    weekAgo:     WEEK_AGO,
    generatedAt: new Date().toISOString(),
    brief,
    stats: {
      total:       allSignals.length,
      unlisted:    allSignals.filter(s => s.companyType === "unlisted_startup").length,
      kr:          allSignals.filter(s => s.isKorean).length,
      cn:          allSignals.filter(s => s.isChina).length,
      global:      allSignals.filter(s => !s.isKorean && !s.isChina).length,
      high:        allSignals.filter(s => s.relevance === "High").length,
      investigate: allSignals.filter(s => s.next_action === "Investigate").length,
    },
    signals: allSignals,
    errors,
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
    index.unshift({ date: TODAY, dateKr: TODAY_KR, stats: output.stats });
    index = index.slice(0, 90);
    fs.writeFileSync(indexPath, JSON.stringify(index, null, 2), "utf8");
  }

  console.log(`\n✅ 완료!`);
  console.log(`총 ${allSignals.length}건 | 비상장 ${output.stats.unlisted} | High ${output.stats.high}`);
  console.log(`국내 ${output.stats.kr} | 글로벌 ${output.stats.global} | 중국 ${output.stats.cn}`);
  if (errors.length > 0) console.log(`실패 ${errors.length}건: ${errors.map(e=>e.topic).join(", ")}`);
}

main().catch(e => { console.error("❌ 오류:", e.message); process.exit(1); });

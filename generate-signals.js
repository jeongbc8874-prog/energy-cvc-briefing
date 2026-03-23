/**
 * Energy CVC Daily Signal Generator
 * GitHub Actions에서 매일 실행 → data/YYYY-MM-DD.json 저장
 *
 * 소스 다양화:
 * - 글로벌: TechCrunch, Reuters, Bloomberg, Recharge, BNEF, Wood Mackenzie 등
 * - 국내: 전자신문, 에너지경제, 연합뉴스, 디일렉
 * - 중국: South China Morning Post, Yicai, Xinhua (에너지 섹터)
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
if (!CLAUDE_KEY) { console.error("ANTHROPIC_API_KEY 없음"); process.exit(1); }

const TODAY     = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
const TODAY_KR  = new Date().toLocaleDateString("ko-KR", { timeZone:"Asia/Seoul", year:"numeric", month:"long", day:"numeric", weekday:"long" });
const WEEK_AGO  = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

// ── 검색 토픽 (국내 + 글로벌 + 중국) ─────────────────────
const TOPICS = [
  // ── 국내 비상장 스타트업 ──────────────────────────────
  {
    id: "kr_ess_startup",
    label: "국내 ESS 스타트업",
    emoji: "🇰🇷🔋",
    region: "KR",
    lang: "ko",
    companies: ["스탠다드에너지","씨에스에너지","에너테크인터내셔널","하나기술","에이치에너지","비엠텍"],
    query: `(스탠다드에너지 OR 씨에스에너지 OR 에너테크인터내셔널 OR 하나기술 OR 에이치에너지) (투자 OR 계약 OR 파트너십 OR 시리즈 OR 펀딩 OR 수주) after:${WEEK_AGO} site:etnews.com OR site:enewstoday.co.kr OR site:electimes.com OR site:energy.co.kr`,
  },
  {
    id: "kr_hydrogen_startup",
    label: "국내 수소 스타트업",
    emoji: "🇰🇷💧",
    region: "KR",
    lang: "ko",
    companies: ["하이리움산업","에스퓨얼셀","범한퓨얼셀","이엠솔루션","그린수소시스템","하이드로리서치"],
    query: `(하이리움 OR 에스퓨얼셀 OR 범한퓨얼셀 OR 이엠솔루션 OR 그린수소) (투자 OR 파트너십 OR 계약 OR 펀딩 OR 인증) after:${WEEK_AGO}`,
  },
  {
    id: "kr_grid_startup",
    label: "국내 그리드 스타트업",
    emoji: "🇰🇷⚡",
    region: "KR",
    lang: "ko",
    companies: ["그리드위즈","식스티헤르츠","에너지에이아이","이노원","파워유닛","에너지X"],
    query: `(그리드위즈 OR 식스티헤르츠 OR 에너지에이아이 OR VPP OR 가상발전소) (투자 OR 계약 OR 파트너십 OR 실증 OR 펀딩) after:${WEEK_AGO} site:etnews.com OR site:zdnet.co.kr OR site:bloter.net`,
  },
  {
    id: "kr_marine_startup",
    label: "국내 선박 스타트업",
    emoji: "🇰🇷🚢",
    region: "KR",
    lang: "ko",
    companies: ["빈센","범한퓨얼셀","파나시아","HiNAV","에이치라인해운"],
    query: `(빈센 OR 범한퓨얼셀 OR 파나시아) (선박 OR 연료전지 OR 수소 OR 암모니아) (투자 OR 계약 OR 인증) after:${WEEK_AGO}`,
  },
  // ── 글로벌 ──────────────────────────────────────────
  {
    id: "global_ess",
    label: "Global ESS Startups",
    emoji: "🌍🔋",
    region: "GLOBAL",
    lang: "en",
    query: `energy storage startup funding OR investment OR deal OR partnership after:${WEEK_AGO} site:rechargenews.com OR site:electrek.co OR site:pv-magazine.com OR site:energymonitor.ai OR site:canary.media`,
  },
  {
    id: "global_hydrogen",
    label: "Global Hydrogen Startups",
    emoji: "🌍💧",
    region: "GLOBAL",
    lang: "en",
    query: `green hydrogen startup electrolyzer fuel cell funding OR investment OR partnership after:${WEEK_AGO} site:hydrogeninsight.com OR site:rechargenews.com OR site:spglobal.com`,
  },
  {
    id: "global_grid",
    label: "Global Grid Software",
    emoji: "🌍⚡",
    region: "GLOBAL",
    lang: "en",
    query: `virtual power plant VPP grid software startup investment OR contract OR utility after:${WEEK_AGO} site:utilitydive.com OR site:greentechmedia.com OR site:canary.media`,
  },
  {
    id: "global_marine",
    label: "Global Marine Decarbonization",
    emoji: "🌍🚢",
    region: "GLOBAL",
    lang: "en",
    query: `marine shipping decarbonization startup fuel cell ammonia methanol funding OR deal after:${WEEK_AGO} site:rechargenews.com OR site:tradewindsnews.com OR site:splash247.com`,
  },
  {
    id: "global_hvdc",
    label: "Global HVDC / Transmission",
    emoji: "🌍🔌",
    region: "GLOBAL",
    lang: "en",
    query: `HVDC offshore wind transmission startup investment OR contract after:${WEEK_AGO} site:rechargenews.com OR site:windpowermonthly.com OR site:electrek.co`,
  },
  {
    id: "global_dcpower",
    label: "Global DC Power / AI Infra",
    emoji: "🌍🖥️",
    region: "GLOBAL",
    lang: "en",
    query: `data center power electronics startup hyperscaler investment OR deal OR partnership after:${WEEK_AGO} site:techcrunch.com OR site:datacenterknowledge.com OR site:theregister.com`,
  },
  {
    id: "global_wte",
    label: "Global Waste-to-Energy",
    emoji: "🌍♻️",
    region: "GLOBAL",
    lang: "en",
    query: `waste energy pyrolysis biogas startup investment OR offtake OR deal after:${WEEK_AGO} site:bioenergynews.com OR site:waste-management-world.com OR site:rechargenews.com`,
  },
  {
    id: "global_smr",
    label: "Global SMR / Nuclear",
    emoji: "🌍☢️",
    region: "GLOBAL",
    lang: "en",
    query: `small modular reactor SMR nuclear startup investment OR partnership OR deal after:${WEEK_AGO} site:nuclearenergyinsider.com OR site:world-nuclear-news.org OR site:techcrunch.com`,
  },
  // ── 중국 ──────────────────────────────────────────────
  {
    id: "china_ess",
    label: "China ESS Market",
    emoji: "🇨🇳🔋",
    region: "CN",
    lang: "en",
    query: `China energy storage CATL BYD REPT startup investment OR deal OR partnership after:${WEEK_AGO} site:scmp.com OR site:yicai.com OR site:caixin.com OR site:bloomberg.com`,
  },
  {
    id: "china_hydrogen",
    label: "China Hydrogen",
    emoji: "🇨🇳💧",
    region: "CN",
    lang: "en",
    query: `China green hydrogen electrolyzer startup SINOHY Peric Sunwise investment OR deal after:${WEEK_AGO} site:scmp.com OR site:hydrogeninsight.com OR site:rechargenews.com`,
  },
  {
    id: "china_grid",
    label: "China Grid / VPP",
    emoji: "🇨🇳⚡",
    region: "CN",
    lang: "en",
    query: `China virtual power plant VPP grid startup investment OR policy OR deal after:${WEEK_AGO} site:scmp.com OR site:caixin.com OR site:spglobal.com`,
  },
];

// ── Claude API 호출 ────────────────────────────────────────
function callClaude(system, userMsg, useWebSearch = true) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4000,
      system,
      ...(useWebSearch ? { tools: [{ type: "web_search_20250305", name: "web_search" }] } : {}),
      messages: [{ role: "user", content: userMsg }],
    });

    const req = https.request({
      hostname: "api.anthropic.com",
      path: "/v1/messages",
      method: "POST",
      headers: {
        "Content-Type":    "application/json",
        "x-api-key":       CLAUDE_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Length":  Buffer.byteLength(body),
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
  // 불완전한 JSON 복구 시도
  let slice = clean.slice(s, e + 1);
  try { return JSON.parse(slice); }
  catch {
    const lastComma = slice.lastIndexOf("},{");
    if (lastComma > 0) {
      try { return JSON.parse(slice.slice(0, lastComma + 1) + "]"); } catch {}
    }
    throw new Error("JSON 파싱 실패");
  }
}

// ── 토픽별 신호 수집 ───────────────────────────────────────
async function fetchTopicSignals(topic) {
  const isKr = topic.region === "KR";
  const isCn = topic.region === "CN";

  const system = isKr
    ? `당신은 에너지 인프라 전문 CVC 펀드의 시니어 심사역입니다.
오늘(${TODAY_KR}) 기준 최근 7일(${WEEK_AGO} 이후) 실제 뉴스만 사용합니다.
비상장 스타트업 우선. 대기업은 생태계 맥락으로만.
JSON 배열만 반환. 마크다운 없음.`
    : `You are a senior CVC analyst specializing in energy infrastructure.
Today is ${TODAY_KR}. Use ONLY news from the last 7 days (after ${WEEK_AGO}).
Focus on UNLISTED startups. Corporates are ecosystem context only.
Return ONLY valid JSON array. No markdown.`;

  const companyContext = isKr && topic.companies
    ? `\n대상 비상장 기업: ${topic.companies.join(", ")}\n` : "";

  const prompt = isKr ? `
웹 검색어: "${topic.query}"
${companyContext}
최근 7일 실제 뉴스를 검색하여 투자 신호 4건을 JSON으로 반환:
[{
  "title": "실제 헤드라인",
  "company": "기업명",
  "companyType": "unlisted_startup|listed_corp|ecosystem",
  "fundingStage": "Pre-A|Series-A|Series-B|Series-C|Pre-IPO|N/A",
  "country": "KR",
  "pubDate": "게재일 또는 최근며칠",
  "source": "출처명",
  "summary": "실제 내용 2-3문장 (금액/파트너/날짜 포함)",
  "eventType": "Hiring|Pilot|Partnership|Grant|Certification|Expansion|Financing|Offtake|ProjectFinance",
  "signalStage": "Early|Commercial|Strategic",
  "relevance": "High|Medium|Low",
  "signal_type": "Pre-funding|Commercial traction|Technical validation|Market context",
  "next_action": "Investigate|Monitor|Note|Skip",
  "deep_insight": "에너지 심사역 딥 인사이트 3-4문장: TRL 단계, 상업화 경로, 타이밍 의미, 경쟁 구도, 대기업 연계 의미",
  "cvc_action": "구체적 투자 액션",
  "risk": "핵심 리스크",
  "isRealNews": true
}]
JSON만 반환.`
    : `
Search query: "${topic.query}"
${isCn ? "\nFocus: Chinese energy market, include both Chinese companies and foreign companies active in China.\n" : ""}
Search web for REAL news from last 7 days (after ${WEEK_AGO}), return 4 investment signals as JSON:
[{
  "title": "Real headline from last 7 days",
  "company": "Company name (prefer unlisted startups)",
  "companyType": "unlisted_startup|listed_corp|ecosystem",
  "fundingStage": "Seed|Series-A|Series-B|Series-C|Growth|N/A",
  "country": "${isCn ? "CN" : "2-letter code"}",
  "pubDate": "Publication date or days ago",
  "source": "Source name",
  "summary": "2-3 sentences with date/amount/partner details",
  "eventType": "Hiring|Pilot|Partnership|Grant|Certification|Expansion|Financing|Offtake|ProjectFinance",
  "signalStage": "Early|Commercial|Strategic",
  "relevance": "High|Medium|Low",
  "signal_type": "Pre-funding|Commercial traction|Technical validation|Market context",
  "next_action": "Investigate|Monitor|Note|Skip",
  "deep_insight": "3-4 sentences: TRL stage, commercialization path, timing significance, competitive moat, corporate partnership meaning, risks",
  "cvc_action": "Specific CVC action",
  "risk": "Key risk in one line",
  "isRealNews": true
}]
Return ONLY JSON array.`;

  const text = await callClaude(system, prompt, true);
  const items = parseJSON(text);
  return items.map((item, i) => ({
    ...item,
    id:         `${topic.id}-${i}-${Date.now()}`,
    topicId:    topic.id,
    category:   topic.label,
    emoji:      topic.emoji,
    region:     topic.region,
    isKorean:   topic.region === "KR",
    isChina:    topic.region === "CN",
    generatedAt: TODAY,
  }));
}

// ── 딥 브리핑 생성 ─────────────────────────────────────────
async function generateBrief(signals) {
  const unlisted = signals.filter(s => s.companyType === "unlisted_startup" && s.relevance === "High");
  const krHigh   = signals.filter(s => s.isKorean && s.relevance === "High");
  const glHigh   = signals.filter(s => !s.isKorean && !s.isChina && s.relevance === "High");
  const cnHigh   = signals.filter(s => s.isChina && s.relevance === "High");

  const prompt = `오늘(${TODAY_KR}) 에너지 CVC 일일 딥 브리핑을 작성해주세요.

비상장 스타트업 핵심:
${unlisted.slice(0,5).map(s=>`- [${s.category}] ${s.company} (${s.fundingStage||""}): ${s.deep_insight?.slice(0,120)||s.title}`).join("\n")}

국내 High:
${krHigh.slice(0,4).map(s=>`- ${s.company}: ${s.title}`).join("\n")||"없음"}

글로벌 High:
${glHigh.slice(0,4).map(s=>`- [${s.country}] ${s.company}: ${s.title}`).join("\n")||"없음"}

중국 High:
${cnHigh.slice(0,3).map(s=>`- ${s.company}: ${s.title}`).join("\n")||"없음"}

작성 (6-7문장, 내부 메모 스타일):
1. 이번 주 가장 중요한 비상장 투자 기회 2-3건 (이유 포함)
2. 국내 정책/규제와 연계된 기회
3. 중국 시장 동향이 국내 스타트업에 주는 시사점
4. 대기업 파트너십에서 읽는 비상장 투자 기회
5. 즉시 액션 (이유 포함)
6. 다음 주 모니터링 포인트

에너지 전문 심사역 언어. 표면적 요약 금지. 구체적 수치/회사명 필수.`;

  const text = await callClaude(
    `당신은 에너지 인프라 전문 CVC 펀드 시니어 심사역입니다. 딥 인사이트 위주의 내부 브리핑을 한국어로 작성합니다.`,
    prompt,
    true
  );
  return text.replace(/```/g, "").trim();
}

// ── 메인 실행 ──────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Daily Signal Generator`);
  console.log(`날짜: ${TODAY_KR}`);
  console.log(`검색 범위: ${WEEK_AGO} 이후 (최근 7일)\n`);

  // data 디렉토리 생성
  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  const allSignals = [];
  const errors     = [];

  // 각 토픽 순차 처리
  for (const topic of TOPICS) {
    console.log(`→ ${topic.emoji} ${topic.label}...`);
    try {
      const items = await fetchTopicSignals(topic);
      // 비상장 우선 정렬
      items.sort((a, b) => {
        const sa = (a.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[a.relevance]||0);
        const sb = (b.companyType==="unlisted_startup"?10:0) + ({High:3,Medium:1,Low:0}[b.relevance]||0);
        return sb - sa;
      });
      allSignals.push(...items);
      const u = items.filter(x => x.companyType==="unlisted_startup").length;
      console.log(`  ✓ ${items.length}건 (비상장 ${u}건, High ${items.filter(x=>x.relevance==="High").length}건)`);
    } catch(e) {
      console.error(`  ✗ 실패: ${e.message}`);
      errors.push({ topic: topic.id, error: e.message });
    }
    // API 과부하 방지
    await new Promise(r => setTimeout(r, 1000));
  }

  console.log(`\n② 딥 브리핑 생성 중...`);
  let brief = "";
  try {
    brief = await generateBrief(allSignals);
    console.log(`  ✓ 브리핑 완료`);
  } catch(e) {
    console.error(`  ✗ 브리핑 실패: ${e.message}`);
  }

  // 최종 데이터 구조
  const output = {
    date:        TODAY,
    dateKr:      TODAY_KR,
    weekAgo:     WEEK_AGO,
    generatedAt: new Date().toISOString(),
    brief,
    stats: {
      total:    allSignals.length,
      unlisted: allSignals.filter(s => s.companyType==="unlisted_startup").length,
      kr:       allSignals.filter(s => s.isKorean).length,
      cn:       allSignals.filter(s => s.isChina).length,
      global:   allSignals.filter(s => !s.isKorean && !s.isChina).length,
      high:     allSignals.filter(s => s.relevance==="High").length,
      investigate: allSignals.filter(s => s.next_action==="Investigate").length,
    },
    signals: allSignals,
    errors,
  };

  // 오늘 날짜 파일 저장
  const filePath = path.join(dataDir, `${TODAY}.json`);
  fs.writeFileSync(filePath, JSON.stringify(output, null, 2), "utf8");
  console.log(`\n✅ 저장 완료: data/${TODAY}.json`);
  console.log(`   총 ${allSignals.length}건 | 비상장 ${output.stats.unlisted}건 | High ${output.stats.high}건`);
  console.log(`   국내 ${output.stats.kr}건 | 글로벌 ${output.stats.global}건 | 중국 ${output.stats.cn}건\n`);

  // latest.json도 업데이트 (웹사이트 홈에서 사용)
  fs.writeFileSync(path.join(dataDir, "latest.json"), JSON.stringify(output, null, 2), "utf8");

  // index.json 업데이트 (날짜 목록)
  const indexPath = path.join(dataDir, "index.json");
  let index = [];
  if (fs.existsSync(indexPath)) {
    try { index = JSON.parse(fs.readFileSync(indexPath, "utf8")); } catch {}
  }
  if (!index.find(d => d.date === TODAY)) {
    index.unshift({ date: TODAY, dateKr: TODAY_KR, stats: output.stats });
    index = index.slice(0, 90); // 최근 90일만 유지
    fs.writeFileSync(indexPath, JSON.stringify(index, null, 2), "utf8");
  }

  console.log("🎉 완료!\n");
}

main().catch(e => {
  console.error("❌ 치명적 오류:", e.message);
  process.exit(1);
});

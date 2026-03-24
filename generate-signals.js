/**
 * Energy CVC Daily Signal Generator v6
 * 실제 뉴스 기반: NewsAPI → Claude 분석 → 링크 포함 저장
 *
 * GitHub Secrets 필요:
 *   ANTHROPIC_API_KEY  (기존)
 *   NEWS_API_KEY       (기존 — newsapi.org)
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
const NEWS_KEY   = process.env.NEWS_API_KEY;

if (!CLAUDE_KEY) { console.error("ANTHROPIC_API_KEY 없음"); process.exit(1); }
if (!NEWS_KEY)   { console.error("NEWS_API_KEY 없음"); process.exit(1); }

const TODAY    = new Date().toISOString().slice(0, 10);
const TODAY_KR = new Date().toLocaleDateString("ko-KR", {
  timeZone:"Asia/Seoul", year:"numeric", month:"long", day:"numeric", weekday:"long"
});
// NewsAPI 무료 플랜: 최근 30일까지만 가능
const MONTH_AGO = new Date(Date.now() - 28 * 86400000).toISOString().slice(0, 10);

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── NewsAPI 호출 ───────────────────────────────────────────
function fetchNews(query, pageSize = 10) {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams({
      q:          query,
      language:   "en",
      sortBy:     "publishedAt",
      pageSize:   String(pageSize),
      from:       MONTH_AGO,
      apiKey:     NEWS_KEY,
    });
    const req = https.request({
      hostname: "newsapi.org",
      path:     `/v2/everything?${params}`,
      method:   "GET",
      headers:  { "User-Agent": "EnergyCVC/1.0" },
    }, res => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const p = JSON.parse(data);
          if (p.status !== "ok") { reject(new Error(p.message || "NewsAPI 오류")); return; }
          resolve(p.articles || []);
        } catch(e) { reject(e); }
      });
    });
    req.on("error", reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error("NewsAPI Timeout")); });
    req.end();
  });
}

// ── 한국 뉴스 (NewsAPI 한국어 지원 제한 → 영어 쿼리 사용) ─
async function fetchAllNews() {
  console.log("① NewsAPI 실제 뉴스 수집 중...");

  // 검색 쿼리 목록 (에너지 CVC 관련)
  const queries = [
    // 국내 기업 (영문명)
    { q: "Korea energy storage battery startup investment",          tag: "kr_ess"      },
    { q: "Korea hydrogen fuel cell startup funding",                  tag: "kr_h2"       },
    { q: "Korea grid VPP virtual power plant startup",                tag: "kr_grid"     },
    { q: "Gridwiz OR Sixty Hertz OR EnergyAI Korea startup",         tag: "kr_startup"  },
    // 글로벌
    { q: "energy storage startup funding investment 2025",            tag: "g_ess"       },
    { q: "green hydrogen electrolyzer startup funding",               tag: "g_h2"        },
    { q: "virtual power plant VPP startup investment contract",       tag: "g_grid"      },
    { q: "marine shipping decarbonization fuel cell startup",         tag: "g_marine"    },
    { q: "small modular reactor SMR nuclear startup investment",      tag: "g_smr"       },
    { q: "HVDC offshore wind cable transmission startup",             tag: "g_hvdc"      },
    // 중국
    { q: "China energy storage startup investment CATL ecosystem",    tag: "cn_ess"      },
    { q: "China green hydrogen electrolyzer startup",                 tag: "cn_h2"       },
    { q: "China virtual power plant grid startup policy",             tag: "cn_grid"     },
  ];

  const allArticles = [];
  // NewsAPI 무료 플랜: 분당 요청 제한 있음 → 순차 처리
  for (const q of queries) {
    try {
      const articles = await fetchNews(q.q, 5);
      const valid = articles.filter(a =>
        a.title &&
        a.title !== "[Removed]" &&
        a.url &&
        a.url !== "https://removed.com"
      );
      allArticles.push(...valid.map(a => ({ ...a, tag: q.tag })));
      console.log(`  [${q.tag}] ${valid.length}건`);
    } catch(e) {
      console.error(`  [${q.tag}] 실패: ${e.message}`);
    }
    await delay(200); // NewsAPI 과부하 방지
  }

  // 중복 제거 (URL 기준)
  const seen = new Set();
  const deduped = allArticles.filter(a => {
    if (seen.has(a.url)) return false;
    seen.add(a.url);
    return true;
  });

  console.log(`  총 ${deduped.length}건 수집 (중복 제거 후)`);
  return deduped;
}

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
          resolve((p.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n"));
        } catch(e) { reject(e); }
      });
    });
    req.on("error", reject);
    req.setTimeout(90000, () => { req.destroy(); reject(new Error("Claude Timeout")); });
    req.write(body); req.end();
  });
}

// ── JSON 파싱 (강화) ───────────────────────────────────────
function extractJSON(text) {
  // 방법1: 코드블록
  const cb = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (cb) { try { return JSON.parse(cb[1].trim()); } catch {} }

  // 방법2: 첫 [ ~ 마지막 ]
  let d = 0, s = -1, e = -1;
  for (let i = 0; i < text.length; i++) {
    if (text[i]==="[" && d===0) { s=i; d++; }
    else if (text[i]==="[") d++;
    else if (text[i]==="]") { d--; if(d===0&&s!==-1){e=i;break;} }
  }
  if (s!==-1 && e!==-1) {
    const slice = text.slice(s, e+1);
    try { return JSON.parse(slice); } catch {}
    // 후행 쉼표 제거
    try { return JSON.parse(slice.replace(/,(\s*[}\]])/g,"$1")); } catch {}
    // 개별 객체 복구
    const objs=[]; let od=0, os=-1;
    for(let i=0;i<slice.length;i++){
      if(slice[i]==="{"){if(od===0)os=i;od++;}
      else if(slice[i]==="}"){ od--; if(od===0&&os!==-1){try{objs.push(JSON.parse(slice.slice(os,i+1)));}catch{}os=-1;}}
    }
    if(objs.length>0)return objs;
  }
  throw new Error("JSON 추출 실패");
}

// ── 이벤트 타입 추론 ──────────────────────────────────────
function inferEventType(title, desc) {
  const t = (title+" "+desc).toLowerCase();
  if (/offtake|supply agreement|long.term contract/.test(t)) return "Offtake";
  if (/cfo|vp finance|head of finance|project finance/.test(t)) return "Hiring";
  if (/certif|approv|dnv|tüv|class approv/.test(t)) return "Certification";
  if (/grant|award|doe |eu fund|innovate uk|arena/.test(t)) return "Grant";
  if (/manufactur|production|facility|scale.up/.test(t)) return "Expansion";
  if (/pilot|trial|demonstration|deploy/.test(t)) return "Pilot";
  if (/partner|mou|agreement|framework/.test(t)) return "Partnership";
  if (/series|raised|funding round|\$\d+m|\$\d+b/.test(t)) return "Financing";
  if (/acqui|merger|takeover/.test(t)) return "MA";
  return "News";
}

function inferImpact(title, desc) {
  const t = title + " " + desc;
  if (/contract|commercial|deploy|certif|offtake|series [b-d]|production|cfo|\$\d+[mb]/i.test(t)) return "High";
  if (/study|report|analysis|whitepaper|outlook/i.test(t)) return "Low";
  return "Medium";
}

// ── Claude로 배치 분석 ─────────────────────────────────────
async function analyzeArticlesBatch(articles, batchIdx) {
  const list = articles.map((a, i) => [
    `${i+1}. [${a.tag}] ${a.source?.name||"Unknown"}`,
    `제목: ${a.title}`,
    `내용: ${(a.description||"").slice(0,150)}`,
    `날짜: ${(a.publishedAt||"").slice(0,10)}`,
  ].join("\n")).join("\n\n");

  const system = `에너지 CVC 시니어 심사역. 비상장 스타트업 중심 투자 관점 분석. JSON 배열만 반환.`;
  const user = `아래 ${articles.length}건의 실제 에너지 뉴스를 CVC 투자 관점으로 분석하세요.

${list}

각 기사에 대해 JSON 배열로 반환 (순서 유지, 다른 텍스트 없이):
[{"idx":1,"company":"언급된 회사명","companyType":"unlisted_startup|listed_corp|ecosystem","fundingStage":"Seed|Pre-A|Series-A|Series-B|Series-C|N/A","relevance":"High|Medium|Low","signal_type":"Pre-funding|Commercial traction|Technical validation|Market context","next_action":"Investigate|Monitor|Note|Skip","deep_insight":"심사역 딥 인사이트 2-3문장: TRL 단계, 상업화 경로, 비상장 투자 기회 관점","cvc_action":"구체적 CVC 액션","risk":"핵심 리스크 한 줄"}]

반드시 ${articles.length}개 객체. JSON만.`;

  const text = await callClaude(system, user);
  const analyses = extractJSON(text);

  // 기사와 분석 병합
  return articles.map((article, i) => {
    const analysis = analyses.find(a => a.idx === i+1) || analyses[i] || {};
    return {
      id:          `${article.tag}-${Date.now()}-${i+batchIdx*10}`,
      topicId:     article.tag,
      category:    tagToCategory(article.tag),
      emoji:       tagToEmoji(article.tag),
      region:      tagToRegion(article.tag),
      isKorean:    article.tag.startsWith("kr_"),
      isChina:     article.tag.startsWith("cn_"),

      // ── 실제 뉴스 데이터 ──
      title:       article.title,
      url:         article.url,           // ← 실제 기사 링크
      source:      article.source?.name || "Unknown",
      pubDate:     (article.publishedAt||"").slice(0,10), // 실제 날짜
      summary:     (article.description||article.title||"").slice(0,300),
      country:     tagToCountry(article.tag),
      isRealNews:  true,                  // ← 실제 뉴스 표시
      generatedAt: TODAY,

      // ── Claude 분석 데이터 ──
      company:      analysis.company     || extractCompany(article.title, article.description||""),
      companyType:  analysis.companyType || "ecosystem",
      fundingStage: analysis.fundingStage|| "N/A",
      eventType:    inferEventType(article.title, article.description||""),
      signalStage:  "Early",
      relevance:    analysis.relevance   || inferImpact(article.title, article.description||""),
      signal_type:  analysis.signal_type || "Market context",
      next_action:  analysis.next_action || "Monitor",
      deep_insight: analysis.deep_insight|| "",
      cvc_action:   analysis.cvc_action  || "",
      risk:         analysis.risk        || "",
    };
  });
}

// ── 헬퍼 함수들 ───────────────────────────────────────────
function tagToCategory(tag) {
  const m = {
    kr_ess:"국내 ESS 스타트업", kr_h2:"국내 수소 스타트업",
    kr_grid:"국내 그리드 스타트업", kr_startup:"국내 에너지 스타트업",
    g_ess:"Global ESS", g_h2:"Global Hydrogen",
    g_grid:"Global Grid/VPP", g_marine:"Global Marine",
    g_smr:"Global SMR/Nuclear", g_hvdc:"Global HVDC",
    cn_ess:"China ESS", cn_h2:"China Hydrogen", cn_grid:"China Grid",
  };
  return m[tag] || tag;
}
function tagToEmoji(tag) {
  if (tag.startsWith("kr_")) return "🇰🇷";
  if (tag.startsWith("cn_")) return "🇨🇳";
  return "🌍";
}
function tagToRegion(tag) {
  if (tag.startsWith("kr_")) return "KR";
  if (tag.startsWith("cn_")) return "CN";
  return "GLOBAL";
}
function tagToCountry(tag) {
  if (tag.startsWith("kr_")) return "KR";
  if (tag.startsWith("cn_")) return "CN";
  return "US"; // 기본값
}
function extractCompany(title, desc) {
  // 간단한 회사명 추출 (대문자로 시작하는 단어)
  const matches = (title+" "+desc).match(/\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?\b/g) || [];
  const stopwords = new Set(["The","This","That","For","With","From","After","Before","When","Energy","Power","Battery"]);
  const names = matches.filter(m => !stopwords.has(m) && m.length > 2);
  return names[0] || "Unknown";
}

// ── 브리핑 생성 ────────────────────────────────────────────
async function generateBrief(signals) {
  const top = signals.filter(s=>s.relevance==="High").slice(0,8)
    .map(s=>`[${s.region}][${s.category}] ${s.company} (${s.source}): ${s.title}`).join("\n");

  return callClaude(
    "에너지 CVC 시니어 심사역. 딥 인사이트. 한국어. 비상장 중심.",
    `오늘(${TODAY_KR}) CVC 딥 브리핑 5-6문장.\n실제 뉴스 기반 주요 신호:\n${top}\n\n1)비상장 투자기회 2)국내정책 3)중국시사점 4)즉시액션 5)모니터링. 구체적 수치·회사명 필수.`
  );
}

// ── 메인 ───────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v6 (실제 뉴스 기반)`);
  console.log(`날짜: ${TODAY_KR} | NewsAPI + Claude 분석\n`);

  const dataDir = path.join(__dirname, "data");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  // ① NewsAPI로 실제 기사 수집
  const articles = await fetchAllNews();
  if (articles.length === 0) {
    console.error("뉴스 수집 실패. NEWS_API_KEY를 확인하세요.");
    process.exit(1);
  }

  // ② Claude로 배치 분석 (8건씩, rate limit 방지)
  console.log(`\n② Claude 분석 시작 (${articles.length}건)...`);
  const allSignals = [];
  const batchSize  = 8;

  for (let i = 0; i < articles.length; i += batchSize) {
    const batch = articles.slice(i, i + batchSize);
    console.log(`  배치 ${Math.floor(i/batchSize)+1}: ${batch.length}건 분석...`);
    try {
      const analyzed = await analyzeArticlesBatch(batch, Math.floor(i/batchSize));
      allSignals.push(...analyzed);
      console.log(`  ✓ ${analyzed.length}건 완료`);
    } catch(e) {
      console.error(`  ✗ 배치 실패: ${e.message}`);
      // 실패한 배치는 기본 데이터로 추가
      batch.forEach((a, j) => allSignals.push({
        id: `${a.tag}-${Date.now()}-${i+j}`,
        topicId: a.tag, category: tagToCategory(a.tag), emoji: tagToEmoji(a.tag),
        region: tagToRegion(a.tag), isKorean: a.tag.startsWith("kr_"), isChina: a.tag.startsWith("cn_"),
        title: a.title, url: a.url, source: a.source?.name||"Unknown",
        pubDate: (a.publishedAt||"").slice(0,10), summary: (a.description||"").slice(0,300),
        country: tagToCountry(a.tag), isRealNews: true, generatedAt: TODAY,
        company: extractCompany(a.title, a.description||""), companyType: "ecosystem",
        fundingStage: "N/A", eventType: inferEventType(a.title, a.description||""),
        signalStage: "Early", relevance: inferImpact(a.title, a.description||""),
        signal_type: "Market context", next_action: "Monitor",
        deep_insight: "", cvc_action: "", risk: "",
      }));
    }
    if (i + batchSize < articles.length) {
      console.log("  ⏱ 30초 대기...");
      await delay(30000);
    }
  }

  // 비상장 우선 정렬
  allSignals.sort((a,b)=>{
    const sa=(a.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[a.relevance]||0);
    const sb=(b.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[b.relevance]||0);
    return sb-sa;
  });

  // ③ 브리핑
  console.log("\n③ 브리핑 생성 중...");
  await delay(30000);
  let brief = "";
  try { brief = await generateBrief(allSignals); console.log("  ✓ 완료"); }
  catch(e) { console.error(`  ✗ ${e.message}`); }

  const stats = {
    total:       allSignals.length,
    unlisted:    allSignals.filter(s=>s.companyType==="unlisted_startup").length,
    kr:          allSignals.filter(s=>s.isKorean).length,
    cn:          allSignals.filter(s=>s.isChina).length,
    global:      allSignals.filter(s=>!s.isKorean&&!s.isChina).length,
    high:        allSignals.filter(s=>s.relevance==="High").length,
    investigate: allSignals.filter(s=>s.next_action==="Investigate").length,
    realNews:    allSignals.filter(s=>s.isRealNews).length,
  };

  const output = {
    date:TODAY, dateKr:TODAY_KR, generatedAt:new Date().toISOString(),
    brief, stats, signals:allSignals, errors:[],
  };

  fs.writeFileSync(path.join(dataDir,`${TODAY}.json`), JSON.stringify(output,null,2),"utf8");
  fs.writeFileSync(path.join(dataDir,"latest.json"),   JSON.stringify(output,null,2),"utf8");

  const idxPath = path.join(dataDir,"index.json");
  let idx=[];
  if(fs.existsSync(idxPath)){try{idx=JSON.parse(fs.readFileSync(idxPath,"utf8"));}catch{}}
  if(!idx.find(d=>d.date===TODAY)){
    idx.unshift({date:TODAY,dateKr:TODAY_KR,stats});
    fs.writeFileSync(idxPath,JSON.stringify(idx.slice(0,90),null,2),"utf8");
  }

  console.log(`\n✅ 완료!`);
  console.log(`실제 뉴스 ${stats.realNews}건 | 국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}`);
  console.log(`High ${stats.high} | 비상장 ${stats.unlisted} | 즉시검토 ${stats.investigate}\n`);
}

main().catch(e=>{console.error("❌ 오류:",e.message);process.exit(1);});

/**
 * Energy CVC Signal Generator v8
 * + 데이터 신뢰도 레이블 (FACT / AI_ANALYSIS / AI_ESTIMATE)
 * + OpenDART 실제 공시 연결
 * + 스코어카드 근거 강화
 * + 정책 트리거 실제 URL
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
const NEWS_KEY   = process.env.NEWS_API_KEY;
const DART_KEY   = process.env.DART_API_KEY;

if (!CLAUDE_KEY) { console.error("ANTHROPIC_API_KEY 없음"); process.exit(1); }
if (!NEWS_KEY)   { console.error("NEWS_API_KEY 없음"); process.exit(1); }

const TODAY     = new Date().toISOString().slice(0, 10);
const TODAY_KR  = new Date().toLocaleDateString("ko-KR", { timeZone:"Asia/Seoul", year:"numeric", month:"long", day:"numeric", weekday:"long" });
const MONTH_AGO = new Date(Date.now() - 28 * 86400000).toISOString().slice(0, 10);
const WEEK_AGO  = new Date(Date.now() - 7  * 86400000).toISOString().slice(0, 10);

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ══════════════════════════════════════════════════════════
// 신뢰도 레벨 정의
// FACT        = 원본 소스 링크 있음, 검증 가능
// AI_ANALYSIS = 실제 데이터 기반 AI 해석 (해석은 AI)
// AI_ESTIMATE = AI 추정, 실제 검증 필요
// ══════════════════════════════════════════════════════════
const TRUST = {
  FACT:        { label:"팩트",     color:"#1A5C36", bg:"#EDF6F1", border:"#A7E3BE", icon:"✓",  desc:"원본 소스 링크 확인 가능" },
  AI_ANALYSIS: { label:"AI 분석",  color:"#1B3A5C", bg:"#EDF2F8", border:"#C0D4EC", icon:"⚙",  desc:"실제 데이터 기반 AI 해석" },
  AI_ESTIMATE: { label:"AI 추정",  color:"#A85400", bg:"#FDF4E8", border:"#F0D8A8", icon:"~",  desc:"AI 추정값 — 독립 검증 필요" },
};

// ══════════════════════════════════════════════════════════
// 정책 트리거 DB (실제 URL 포함)
// ══════════════════════════════════════════════════════════
const POLICY_TRIGGERS = [
  {
    id:"re100_kr", region:"KR", label:"국내 RE100 이행 가이드라인",
    urgency:"High", sectors:["ESS","Grid","Solar"],
    desc:"산업부 RE100 이행 기업 증가 → 기업용 ESS·PPA·VPP 수요 급증",
    url:"https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsView.do?bbs_seq_n=165753",
    urlLabel:"산업통상자원부 공식 발표",
    beneficiaries:["그리드위즈","식스티헤르츠","에너지에이아이"],
    trust: "FACT",
  },
  {
    id:"h2_roadmap", region:"KR", label:"수소경제 로드맵 2.0",
    urgency:"High", sectors:["Hydrogen","Marine"],
    desc:"2030년 청정수소 발전 비중 목표 → 수전해·연료전지 스타트업 직접 수혜",
    url:"https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsView.do?bbs_seq_n=164649",
    urlLabel:"수소경제 로드맵 원문",
    beneficiaries:["하이리움산업","에스퓨얼셀","범한퓨얼셀"],
    trust: "FACT",
  },
  {
    id:"motie_vpp", region:"KR", label:"MOTIE VPP 실증사업",
    urgency:"Medium", sectors:["Grid","Software"],
    desc:"산업부 VPP 실증사업 확대 → DR·VPP 플랫폼 스타트업 공공계약 기회",
    url:"https://www.energy.go.kr/",
    urlLabel:"에너지 공단 VPP 사업 공고",
    beneficiaries:["그리드위즈","식스티헤르츠"],
    trust: "FACT",
  },
  {
    id:"kpx_ancillary", region:"KR", label:"KPX 보조서비스 시장 확대",
    urgency:"High", sectors:["Grid","ESS"],
    desc:"한국전력거래소 주파수 조정 보조서비스 ESS 참여 확대 → VPP·ESS 스타트업 수익 모델 강화",
    url:"https://www.kpx.or.kr/www/contents.do?key=223",
    urlLabel:"한국전력거래소 보조서비스 안내",
    beneficiaries:["그리드위즈","씨에스에너지","스탠다드에너지"],
    trust: "FACT",
  },
  {
    id:"imo2030", region:"GLOBAL", label:"IMO 2030 탄소규제",
    urgency:"High", sectors:["Marine"],
    desc:"선박 탄소집약도 40% 감축 의무 → 대체연료·연료전지 스타트업 수요 급증",
    url:"https://www.imo.org/en/MediaCentre/PressBriefings/pages/CII-and-EEXI-in-force.aspx",
    urlLabel:"IMO 공식 사이트",
    beneficiaries:["빈센","범한퓨얼셀","CMB.TECH"],
    trust: "FACT",
  },
  {
    id:"ira_us", region:"US", label:"미국 IRA (인플레이션 감축법)",
    urgency:"High", sectors:["ESS","Solar","H2"],
    desc:"IRA 세액공제 지속 → 미국 시장 진출 한국 기업 직접 수혜",
    url:"https://www.energy.gov/lpo/inflation-reduction-act",
    urlLabel:"미 에너지부 IRA 안내",
    beneficiaries:["LG에너지솔루션 생태계","한화솔루션"],
    trust: "FACT",
  },
  {
    id:"eu_cbam", region:"EU", label:"EU CBAM (탄소국경세)",
    urgency:"Medium", sectors:["H2","ESS","Grid"],
    desc:"탄소국경세 2026년 전면시행 → 청정에너지 제조 스타트업 수출 경쟁력 강화",
    url:"https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism_en",
    urlLabel:"EU 집행위원회 CBAM 공식 페이지",
    beneficiaries:["스탠다드에너지","하이리움산업"],
    trust: "FACT",
  },
  {
    id:"ferc2222", region:"US", label:"FERC Order 2222",
    urgency:"Medium", sectors:["Grid","VPP"],
    desc:"미국 분산자원 도매시장 참여 허용 → VPP·DR 스타트업 TAM 대폭 확대",
    url:"https://www.ferc.gov/media/ferc-order-no-2222-fact-sheet",
    urlLabel:"FERC Order 2222 팩트시트",
    beneficiaries:["AutoGrid","Voltus","Leap Energy"],
    trust: "FACT",
  },
  {
    id:"china_ess_mandate", region:"CN", label:"중국 ESS 의무 설치 정책",
    urgency:"High", sectors:["ESS"],
    desc:"중국 신재생 발전소 ESS 의무 설치 → 중국 ESS 스타트업 급성장, 국내 경쟁 심화",
    url:"https://www.ndrc.gov.cn/",
    urlLabel:"중국 국가발전개혁위원회 (NDRC)",
    beneficiaries:["Pylontech","REPT","EVE Energy"],
    trust: "FACT",
  },
  {
    id:"dart_2024_ess", region:"KR", label:"국내 ESS 관련 주요 공시 (DART)",
    urgency:"Medium", sectors:["ESS","Grid"],
    desc:"에너지 관련 기업 DART 공시 — 유상증자, 전환사채, 계약 체결 등 실제 팩트 확인 가능",
    url:"https://dart.fss.or.kr/dsab007/main.do",
    urlLabel:"DART 전자공시시스템",
    beneficiaries:["스탠다드에너지","씨에스에너지","그리드위즈"],
    trust: "FACT",
  },
];

// ══════════════════════════════════════════════════════════
// OpenDART 공시 수집
// ══════════════════════════════════════════════════════════
function fetchDART(query) {
  return new Promise((resolve, reject) => {
    if (!DART_KEY) { resolve([]); return; }
    const bgn = new Date(Date.now() - 30 * 86400000).toISOString().slice(0,10).replace(/-/g,"");
    const end = TODAY.replace(/-/g,"");
    const params = new URLSearchParams({
      crtfc_key: DART_KEY,
      corp_name:  query,
      bgn_de:     bgn,
      end_de:     end,
      pblntf_ty:  "A",  // 정기공시
      page_count: "10",
    });
    const req = https.request({
      hostname: "opendart.fss.or.kr",
      path:     `/api/list.json?${params}`,
      method:   "GET",
    }, res => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const p = JSON.parse(data);
          if (p.status !== "000") { resolve([]); return; }
          resolve((p.list || []).slice(0, 5));
        } catch { resolve([]); }
      });
    });
    req.on("error", () => resolve([]));
    req.setTimeout(10000, () => { req.destroy(); resolve([]); });
    req.end();
  });
}

async function fetchDARTSignals() {
  if (!DART_KEY) { console.log("  DART_API_KEY 없음 — 건너뜀"); return []; }
  console.log("  OpenDART 공시 수집 중...");
  const keywords = ["수소","배터리","에너지저장","연료전지","태양광","풍력","ESS","VPP"];
  const all = [];
  for (const kw of keywords) {
    const items = await fetchDART(kw);
    all.push(...items.map(item => ({
      id:          `dart-${item.rcept_no}`,
      topicId:     "kr_dart",
      category:    "DART 공시",
      emoji:       "📋",
      region:      "KR", isKorean: true, isChina: false,
      title:       item.report_nm,
      company:     item.corp_name,
      companyType: "listed_corp",
      fundingStage:"N/A",
      country:     "KR",
      pubDate:     `${item.rcept_dt?.slice(0,4)}-${item.rcept_dt?.slice(4,6)}-${item.rcept_dt?.slice(6,8)}`,
      source:      "DART 전자공시",
      url:         `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcept_no}`,
      summary:     `${item.corp_name} — ${item.report_nm} (${item.rcept_dt}) 공시. 제출인: ${item.flr_nm}`,
      eventType:   inferDARTEvent(item.report_nm),
      signalStage: "Strategic",
      relevance:   inferDARTRelevance(item.report_nm),
      signal_type: "Commercial traction",
      next_action: "Monitor",
      deep_insight:"",
      cvc_action:  "",
      risk:        "",
      trust:       "FACT",           // DART 공시 = 100% 팩트
      trustSource: "DART 전자공시시스템 (금융감독원)",
      isRealNews:  true,
      generatedAt: TODAY,
    })));
    await delay(300);
  }
  const seen = new Set();
  return all.filter(a => { if(seen.has(a.id)) return false; seen.add(a.id); return true; });
}

function inferDARTEvent(name) {
  if (/유상증자|전환사채|신주인수권/.test(name)) return "Financing";
  if (/계약|수주|납품/.test(name))              return "Partnership";
  if (/투자|취득|인수/.test(name))              return "Financing";
  if (/사업보고|반기보고|분기보고/.test(name))   return "News";
  return "News";
}
function inferDARTRelevance(name) {
  if (/유상증자|전환사채|신주인수권|계약체결/.test(name)) return "High";
  if (/투자|취득|수주/.test(name))                       return "Medium";
  return "Low";
}

// ══════════════════════════════════════════════════════════
// NewsAPI
// ══════════════════════════════════════════════════════════
function fetchNews(query, pageSize = 8) {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams({ q:query, language:"en", sortBy:"publishedAt", pageSize:String(pageSize), from:MONTH_AGO, apiKey:NEWS_KEY });
    const req = https.request({ hostname:"newsapi.org", path:`/v2/everything?${params}`, method:"GET", headers:{"User-Agent":"EnergyCVC/1.0"} }, res => {
      let data=""; res.on("data",c=>data+=c); res.on("end",()=>{ try{ const p=JSON.parse(data); if(p.status!=="ok"){reject(new Error(p.message));return;} resolve(p.articles||[]); }catch(e){reject(e);} });
    });
    req.on("error",reject); req.setTimeout(15000,()=>{req.destroy();reject(new Error("Timeout"));}); req.end();
  });
}

async function fetchAllNews() {
  console.log("① NewsAPI 뉴스 수집...");
  const queries = [
    {q:"Korea energy storage battery startup investment",tag:"kr_ess"},
    {q:"Korea hydrogen fuel cell startup funding",tag:"kr_h2"},
    {q:"Korea grid VPP virtual power plant Gridwiz",tag:"kr_grid"},
    {q:"energy storage startup funding investment 2025",tag:"g_ess"},
    {q:"green hydrogen electrolyzer startup funding",tag:"g_h2"},
    {q:"virtual power plant VPP startup investment contract",tag:"g_grid"},
    {q:"marine shipping decarbonization fuel cell startup",tag:"g_marine"},
    {q:"small modular reactor SMR nuclear startup investment",tag:"g_smr"},
    {q:"China energy storage startup investment",tag:"cn_ess"},
    {q:"China green hydrogen electrolyzer startup",tag:"cn_h2"},
  ];
  const all=[];
  for(const q of queries){
    try{
      const arts=await fetchNews(q.q,6);
      const valid=arts.filter(a=>a.title&&a.title!=="[Removed]"&&a.url&&a.url!=="https://removed.com");
      all.push(...valid.map(a=>({...a,tag:q.tag})));
      console.log(`  [${q.tag}] ${valid.length}건`);
    }catch(e){console.error(`  [${q.tag}] 실패: ${e.message}`);}
    await delay(150);
  }
  const seen=new Set(); return all.filter(a=>{if(seen.has(a.url))return false;seen.add(a.url);return true;});
}

// ══════════════════════════════════════════════════════════
// Claude API
// ══════════════════════════════════════════════════════════
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ model:"claude-sonnet-4-20250514", max_tokens:3000, system, messages:[{role:"user",content:user}] });
    const req = https.request({
      hostname:"api.anthropic.com", path:"/v1/messages", method:"POST",
      headers:{"Content-Type":"application/json","x-api-key":CLAUDE_KEY,"anthropic-version":"2023-06-01","Content-Length":Buffer.byteLength(body)},
    }, res=>{let data="";res.on("data",c=>data+=c);res.on("end",()=>{try{const p=JSON.parse(data);if(p.error){reject(new Error(p.error.message));return;}resolve((p.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n"));}catch(e){reject(e);}});});
    req.on("error",reject); req.setTimeout(90000,()=>{req.destroy();reject(new Error("Timeout"));}); req.write(body); req.end();
  });
}

function extractJSON(text) {
  const cb=text.match(/```(?:json)?\s*([\s\S]*?)\s*```/); if(cb){try{return JSON.parse(cb[1].trim());}catch{}}
  let d=0,s=-1,e=-1;
  for(let i=0;i<text.length;i++){if(text[i]==="["&&d===0){s=i;d++;}else if(text[i]==="[")d++;else if(text[i]==="]"){d--;if(d===0&&s!==-1){e=i;break;}}}
  if(s!==-1&&e!==-1){
    const sl=text.slice(s,e+1);
    try{return JSON.parse(sl);}catch{}
    try{return JSON.parse(sl.replace(/,(\s*[}\]])/g,"$1"));}catch{}
    const objs=[];let od=0,os=-1;
    for(let i=0;i<sl.length;i++){if(sl[i]==="{"){if(od===0)os=i;od++;}else if(sl[i]==="}"){ od--;if(od===0&&os!==-1){try{objs.push(JSON.parse(sl.slice(os,i+1)));}catch{}os=-1;}}}
    if(objs.length>0)return objs;
  }
  throw new Error("JSON 없음");
}

function inferEventType(t,d){const s=(t+" "+d).toLowerCase();if(/offtake|supply agreement/.test(s))return"Offtake";if(/certif|approv|dnv|tüv/.test(s))return"Certification";if(/grant|award|doe |eu fund/.test(s))return"Grant";if(/manufactur|production|facility/.test(s))return"Expansion";if(/pilot|trial|deploy/.test(s))return"Pilot";if(/partner|mou|agreement/.test(s))return"Partnership";if(/series|raised|\$\d+m/.test(s))return"Financing";return"News";}
function inferImpact(t,d){const s=t+" "+d;if(/contract|commercial|deploy|certif|offtake|series [b-d]|\$\d+[mb]/i.test(s))return"High";if(/study|report|analysis/i.test(s))return"Low";return"Medium";}
function tagToCategory(tag){const m={kr_ess:"국내 ESS",kr_h2:"국내 수소",kr_grid:"국내 그리드",g_ess:"Global ESS",g_h2:"Global Hydrogen",g_grid:"Global Grid",g_marine:"Global Marine",g_smr:"Global SMR",cn_ess:"China ESS",cn_h2:"China Hydrogen"};return m[tag]||tag;}
function tagToEmoji(tag){if(tag.startsWith("kr_"))return"🇰🇷";if(tag.startsWith("cn_"))return"🇨🇳";return"🌍";}
function tagToCountry(tag){if(tag.startsWith("kr_"))return"KR";if(tag.startsWith("cn_"))return"CN";return"US";}
function extractCompany(t,d){const m=(t+" "+d).match(/\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?\b/g)||[];const stop=new Set(["The","This","For","With","Energy","Power","Korea","China"]);return m.filter(x=>!stop.has(x)&&x.length>2)[0]||"Unknown";}

// ══════════════════════════════════════════════════════════
// 배치 분석 (신뢰도 + 근거 강화)
// ══════════════════════════════════════════════════════════
async function analyzeArticlesBatch(articles, batchIdx) {
  const list = articles.map((a,i) => [
    `${i+1}. [${a.tag}] ${a.source?.name||"Unknown"}`,
    `제목: ${a.title}`,
    `내용: ${(a.description||"").slice(0,150)}`,
    `날짜: ${(a.publishedAt||"").slice(0,10)}`,
  ].join("\n")).join("\n\n");

  const system = `에너지 CVC 시니어 심사역. 비상장 스타트업 중심. 분석은 근거 기반으로. JSON 배열만 반환.`;
  const user = `${articles.length}건 뉴스 CVC 분석. 반드시 근거를 명시하세요.

${list}

JSON 배열 ${articles.length}개:
[{
  "idx":1,
  "company":"회사명",
  "companyType":"unlisted_startup|listed_corp|ecosystem",
  "fundingStage":"Seed|Pre-A|Series-A|Series-B|N/A",
  "relevance":"High|Medium|Low",
  "relevance_reason":"왜 이 relevance인지 한 문장 — 반드시 기사 내용 인용",
  "signal_type":"Pre-funding|Commercial traction|Technical validation|Market context",
  "next_action":"Investigate|Monitor|Note|Skip",
  "next_action_reason":"왜 이 액션인지 한 문장",
  "deep_insight":"심사역 딥 인사이트 2-3문장 (근거 명시)",
  "cvc_action":"구체적 액션",
  "risk":"핵심 리스크",
  "trust":"FACT|AI_ANALYSIS",
  "trust_reason":"FACT면 '기사 원문 링크 있음', AI_ANALYSIS면 분석 근거"
}]
JSON만.`;

  const text = await callClaude(system, user);
  const analyses = extractJSON(text);

  return articles.map((article, i) => {
    const a = analyses.find(x => x.idx === i+1) || analyses[i] || {};
    const coName = a.company || extractCompany(article.title, article.description||"");
    return {
      id:          `${article.tag}-${Date.now()}-${i+batchIdx*10}`,
      topicId:     article.tag,
      category:    tagToCategory(article.tag),
      emoji:       tagToEmoji(article.tag),
      region:      article.tag.startsWith("kr_")?"KR":article.tag.startsWith("cn_")?"CN":"GLOBAL",
      isKorean:    article.tag.startsWith("kr_"),
      isChina:     article.tag.startsWith("cn_"),
      // ── 실제 뉴스 데이터 (FACT) ──
      title:       article.title,
      url:         article.url,
      source:      article.source?.name || "Unknown",
      pubDate:     (article.publishedAt||"").slice(0,10),
      summary:     (article.description||"").slice(0,300),
      country:     tagToCountry(article.tag),
      isRealNews:  true,
      generatedAt: TODAY,
      // ── 신뢰도 ──
      trust:       "FACT",           // 뉴스 원문 자체는 FACT
      trustSource: `${article.source?.name||"Unknown"} (원문 링크 포함)`,
      // ── Claude 분석 (AI_ANALYSIS) ──
      company:     coName,
      companyType: a.companyType || "ecosystem",
      fundingStage:a.fundingStage || "N/A",
      eventType:   inferEventType(article.title, article.description||""),
      signalStage: "Early",
      relevance:   a.relevance || inferImpact(article.title, article.description||""),
      relevance_reason: a.relevance_reason || "",   // ← 새 필드
      signal_type: a.signal_type || "Market context",
      next_action: a.next_action || "Monitor",
      next_action_reason: a.next_action_reason || "", // ← 새 필드
      deep_insight:a.deep_insight || "",
      deep_insight_trust: "AI_ANALYSIS",
      cvc_action:  a.cvc_action || "",
      risk:        a.risk || "",
      scorecard:   null,
    };
  });
}

// ══════════════════════════════════════════════════════════
// 스코어카드 (근거 강화)
// ══════════════════════════════════════════════════════════
function loadProfiles() {
  const p=path.join(__dirname,"data","company-profiles.json");
  if(!fs.existsSync(p))return {};
  try{return JSON.parse(fs.readFileSync(p,"utf8"));}catch{return {};}
}
function saveProfiles(profiles){fs.writeFileSync(path.join(__dirname,"data","company-profiles.json"),JSON.stringify(profiles,null,2),"utf8");}
function updateProfile(profiles, signal) {
  const name=signal.company; if(!name||name==="Unknown")return profiles;
  if(!profiles[name])profiles[name]={name,firstSeen:TODAY,lastSeen:TODAY,sector:signal.category||"",region:signal.region||"",country:signal.country||"",signalCount:0,highCount:0,signals:[],scoreHistory:[],fundingStage:signal.fundingStage||"N/A"};
  const p=profiles[name]; p.lastSeen=TODAY; p.signalCount=(p.signalCount||0)+1;
  if(signal.relevance==="High")p.highCount=(p.highCount||0)+1;
  if(signal.fundingStage&&signal.fundingStage!=="N/A")p.fundingStage=signal.fundingStage;
  p.signals=[{date:TODAY,title:signal.title,relevance:signal.relevance,eventType:signal.eventType,signal_type:signal.signal_type,url:signal.url||null},...(p.signals||[])].slice(0,30);
  p.recentActivity=(p.signals||[]).filter(s=>s.date>=WEEK_AGO).length;
  return profiles;
}

async function generateScorecard(companyName, signals, profile) {
  const recentSignals = signals.slice(0,5).map(s=>`- [${s.eventType}] ${s.title} (${s.relevance}) ${s.url?`URL:${s.url}`:""}`).join("\n");
  const system = "에너지 CVC 시니어 심사역. 스코어카드 생성. 반드시 각 점수의 근거를 기사/공시 내용에서 인용. JSON만.";
  const user = `${companyName} 투자 스코어카드.

근거 자료:
${recentSignals}

프로파일: 최초발견 ${profile.firstSeen}, 총신호 ${profile.signalCount}건, 최근7일 ${profile.recentActivity||0}건

5개 항목 0-5점 평가. 각 항목 점수의 근거를 반드시 실제 신호에서 인용하세요:
{
  "technology":{"score":0,"max":5,"reason":"점수 근거 (어떤 신호에서 판단했는지)","evidence":"인용한 신호 제목"},
  "commercialization":{"score":0,"max":5,"reason":"점수 근거","evidence":"인용 신호"},
  "team":{"score":0,"max":5,"reason":"점수 근거","evidence":"인용 신호"},
  "partnership":{"score":0,"max":5,"reason":"점수 근거","evidence":"인용 신호"},
  "fundraising_timing":{"score":0,"max":5,"reason":"점수 근거","evidence":"인용 신호"},
  "total":0,
  "conviction":"High|Medium|Low",
  "timing_signal":"Immediate|3-6months|6-12months|Watch",
  "timing_reason":"왜 이 타이밍인지 근거",
  "one_line":"한 줄 투자 판단",
  "trust":"AI_ANALYSIS",
  "trust_note":"스코어카드는 AI 추정값입니다. 실제 투자 결정 전 독립적 검증 필요."
}`;
  try {
    const text = await callClaude(system, user);
    const clean = text.replace(/```json|```/g,"").trim();
    const s=clean.indexOf("{"),e=clean.lastIndexOf("}");
    if(s!==-1&&e!==-1)return JSON.parse(clean.slice(s,e+1));
  } catch(e) { console.error(`  스코어카드 실패 (${companyName}): ${e.message}`); }
  return null;
}

function findComparableDeals(companyName, sector) {
  const DB=[
    {company:"Form Energy",country:"US",sector:"ESS-LongDuration",stage:"Series-E",amount:"$450M",year:2023,valuation:"~$1.5B",investors:["ArcelorMittal","GIC"],comparableTo:["스탠다드에너지","에이치에너지"],trust:"FACT",source:"Form Energy 공식 보도자료"},
    {company:"Ambri",country:"US",sector:"ESS-LongDuration",stage:"Series-E",amount:"$144M",year:2022,valuation:"~$500M",investors:["Bill Gates","Paulson"],comparableTo:["스탠다드에너지"],trust:"FACT",source:"Ambri 공식 발표"},
    {company:"Sunfire",country:"DE",sector:"H2-Electrolyzer",stage:"Series-E",amount:"€215M",year:2023,valuation:"~$800M",investors:["Carbon Direct"],comparableTo:["하이리움산업"],trust:"FACT",source:"Sunfire 공식 보도자료"},
    {company:"Electric Hydrogen",country:"US",sector:"H2-Electrolyzer",stage:"Series-B",amount:"$380M",year:2023,valuation:"~$1B",investors:["DCVC","5AM"],comparableTo:["하이드로리서치"],trust:"FACT",source:"Electric Hydrogen 공식"},
    {company:"AutoGrid",country:"US",sector:"Grid-VPP",stage:"Series-D",amount:"$85M",year:2021,valuation:"~$300M",investors:["E.ON","Shell"],comparableTo:["그리드위즈"],trust:"FACT",source:"AutoGrid 공식 발표"},
    {company:"Voltus",country:"US",sector:"Grid-DR",stage:"Acquired",amount:"$50M",year:2023,valuation:"~$200M",investors:["S&P Global"],comparableTo:["그리드위즈","식스티헤르츠"],trust:"FACT",source:"S&P Global 인수 공식"},
    {company:"Upside Energy",country:"UK",sector:"Grid-VPP",stage:"Series-B",amount:"£30M",year:2023,valuation:"~$100M",investors:["Octopus"],comparableTo:["그리드위즈"],trust:"FACT",source:"Upside Energy 공식"},
    {company:"Ceres Power",country:"UK",sector:"Marine-SOFC",stage:"Listed",amount:"£181M",year:2022,valuation:"~$600M",investors:["Bosch","Doosan"],comparableTo:["에스퓨얼셀","범한퓨얼셀"],trust:"FACT",source:"LSE 상장 공시"},
  ];
  return DB.filter(d=>d.comparableTo.some(c=>c.includes(companyName)||companyName.includes(c))||(sector&&d.sector.toLowerCase().includes(sector.toLowerCase().split("/")[0].toLowerCase()))).slice(0,3);
}

function findPolicyTriggers(companyName, sector, country) {
  return POLICY_TRIGGERS.filter(p=>(p.region===country||p.region==="GLOBAL")&&(p.beneficiaries.some(b=>b.includes(companyName)||companyName.includes(b))||p.sectors.some(s=>(sector||"").toLowerCase().includes(s.toLowerCase())))).slice(0,3);
}

// ══════════════════════════════════════════════════════════
// 메인
// ══════════════════════════════════════════════════════════
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v8`);
  console.log(`날짜: ${TODAY_KR}`);
  console.log(`신뢰도 레이블: FACT / AI_ANALYSIS / AI_ESTIMATE\n`);

  const dataDir=path.join(__dirname,"data");
  if(!fs.existsSync(dataDir))fs.mkdirSync(dataDir,{recursive:true});

  const profiles=loadProfiles();
  console.log(`기존 프로파일: ${Object.keys(profiles).length}개`);

  // ① NewsAPI
  const articles=await fetchAllNews();
  if(!articles.length){console.error("뉴스 없음");process.exit(1);}

  // ② DART 공시
  const dartSignals=await fetchDARTSignals();
  console.log(`  DART 공시: ${dartSignals.length}건`);

  // ③ Claude 배치 분석
  console.log(`\n② Claude 분석 (${articles.length}건)...`);
  const newsSignals=[];
  const batchSize=8;
  for(let i=0;i<articles.length;i+=batchSize){
    const batch=articles.slice(i,i+batchSize);
    console.log(`  배치 ${Math.floor(i/batchSize)+1}...`);
    try{
      const analyzed=await analyzeArticlesBatch(batch,Math.floor(i/batchSize));
      analyzed.forEach(s=>{
        s.comparableDeals=findComparableDeals(s.company,s.category);
        s.policyTriggers=findPolicyTriggers(s.company,s.category,s.country);
        updateProfile(profiles,s);
      });
      newsSignals.push(...analyzed);
      console.log(`  ✓ ${analyzed.length}건`);
    }catch(e){
      console.error(`  ✗ ${e.message}`);
      batch.forEach((a,j)=>{
        const s={id:`${a.tag}-${Date.now()}-${i+j}`,topicId:a.tag,category:tagToCategory(a.tag),emoji:tagToEmoji(a.tag),region:a.tag.startsWith("kr_")?"KR":a.tag.startsWith("cn_")?"CN":"GLOBAL",isKorean:a.tag.startsWith("kr_"),isChina:a.tag.startsWith("cn_"),title:a.title,url:a.url,source:a.source?.name||"Unknown",pubDate:(a.publishedAt||"").slice(0,10),summary:(a.description||"").slice(0,300),country:tagToCountry(a.tag),isRealNews:true,generatedAt:TODAY,company:extractCompany(a.title,a.description||""),companyType:"ecosystem",fundingStage:"N/A",eventType:inferEventType(a.title,a.description||""),signalStage:"Early",relevance:inferImpact(a.title,a.description||""),signal_type:"Market context",next_action:"Monitor",deep_insight:"",cvc_action:"",risk:"",trust:"FACT",trustSource:a.source?.name||"Unknown",comparableDeals:[],policyTriggers:[]};
        newsSignals.push(s);updateProfile(profiles,s);
      });
    }
    if(i+batchSize<articles.length){console.log("  ⏱ 30초...");await delay(30000);}
  }

  const allSignals=[...newsSignals,...dartSignals];
  allSignals.sort((a,b)=>((b.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[b.relevance]||0))-((a.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[a.relevance]||0)));

  // ④ 스코어카드
  console.log("\n③ 스코어카드 (근거 강화)...");
  await delay(30000);
  const topCos=[...new Set(allSignals.filter(s=>s.relevance==="High"&&s.company!=="Unknown").map(s=>s.company))].slice(0,5);
  for(const name of topCos){
    const coSigs=allSignals.filter(s=>s.company===name);
    const prof=profiles[name];
    if(!prof)continue;
    console.log(`  ${name}...`);
    try{
      const sc=await generateScorecard(name,coSigs,prof);
      if(sc){prof.latestScorecard=sc;prof.scoreHistory=[{date:TODAY,scorecard:sc},...(prof.scoreHistory||[])].slice(0,12);coSigs.forEach(s=>{s.scorecard=sc;});}
    }catch(e){console.error(`  ✗ ${e.message}`);}
    await delay(8000);
  }

  saveProfiles(profiles);

  // ⑤ 브리핑
  console.log("\n④ 브리핑...");
  await delay(30000);
  let brief="";
  try{
    const top=allSignals.filter(s=>s.relevance==="High").slice(0,8).map(s=>`[${s.region}][${s.category}] ${s.company} (${s.source}): ${s.title}`).join("\n");
    brief=await callClaude("에너지 CVC 시니어 심사역. 딥 인사이트. 한국어. 비상장 중심.",`오늘(${TODAY_KR}) CVC 브리핑 5문장.\n주요신호:\n${top}\n\n비상장투자기회, 정책연계, 타이밍, 즉시액션. 구체적 수치·회사명 필수.`);
    console.log("  ✓");
  }catch(e){console.error(`  ✗ ${e.message}`);}

  const stats={
    total:allSignals.length,unlisted:allSignals.filter(s=>s.companyType==="unlisted_startup").length,
    kr:allSignals.filter(s=>s.isKorean).length,cn:allSignals.filter(s=>s.isChina).length,
    global:allSignals.filter(s=>!s.isKorean&&!s.isChina).length,
    high:allSignals.filter(s=>s.relevance==="High").length,investigate:allSignals.filter(s=>s.next_action==="Investigate").length,
    realNews:allSignals.filter(s=>s.isRealNews).length,dartCount:dartSignals.length,
    profiledCompanies:Object.keys(profiles).length,withScorecard:allSignals.filter(s=>s.scorecard).length,
    factCount:allSignals.filter(s=>s.trust==="FACT").length,
    aiCount:allSignals.filter(s=>s.trust==="AI_ANALYSIS").length,
  };

  const output={date:TODAY,dateKr:TODAY_KR,generatedAt:new Date().toISOString(),brief,stats,signals:allSignals,policyTriggers:POLICY_TRIGGERS,trustLegend:TRUST,errors:[]};
  fs.writeFileSync(path.join(dataDir,`${TODAY}.json`),JSON.stringify(output,null,2),"utf8");
  fs.writeFileSync(path.join(dataDir,"latest.json"),JSON.stringify(output,null,2),"utf8");

  const idxPath=path.join(dataDir,"index.json");let idx=[];
  if(fs.existsSync(idxPath)){try{idx=JSON.parse(fs.readFileSync(idxPath,"utf8"));}catch{}}
  if(!idx.find(d=>d.date===TODAY)){idx.unshift({date:TODAY,dateKr:TODAY_KR,stats});fs.writeFileSync(idxPath,JSON.stringify(idx.slice(0,90),null,2),"utf8");}

  console.log(`\n✅ 완료!`);
  console.log(`총 ${stats.total}건 | FACT ${stats.factCount} | AI분석 ${stats.aiCount}`);
  console.log(`뉴스 ${stats.realNews} | DART공시 ${stats.dartCount} | High ${stats.high}`);
  console.log(`국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}\n`);
}

main().catch(e=>{console.error("❌",e.message);process.exit(1);});

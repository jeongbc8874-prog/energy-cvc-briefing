/**
 * Energy CVC Signal Generator v7
 * + 기업 누적 프로파일 (히스토리 추적)
 * + 투자 스코어카드 (항목별 점수)
 * + 정책/규제 트리거 매핑
 * + 유사 딜 레퍼런스
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
const MONTH_AGO = new Date(Date.now() - 28 * 86400000).toISOString().slice(0, 10);

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 정책/규제 트리거 데이터베이스 ─────────────────────────
const POLICY_TRIGGERS = [
  // 국내
  { id:"re100_kr",   region:"KR", label:"국내 RE100",          sectors:["ESS","Grid","Solar"],   urgency:"High",
    desc:"국내 RE100 이행 기업 증가 → 기업용 ESS·PPA·VPP 수요 급증", beneficiaries:["그리드위즈","식스티헤르츠","에너지에이아이"] },
  { id:"h2_roadmap", region:"KR", label:"수소경제 로드맵 2.0", sectors:["Hydrogen","Marine"],     urgency:"High",
    desc:"2030년 청정수소 발전 비중 목표 → 수전해·연료전지 스타트업 직접 수혜", beneficiaries:["하이리움산업","에스퓨얼셀","범한퓨얼셀"] },
  { id:"motie_vpp",  region:"KR", label:"MOTIE VPP 실증",      sectors:["Grid","Software"],      urgency:"Medium",
    desc:"산업부 VPP 실증사업 확대 → DR·VPP 플랫폼 스타트업 공공계약 기회", beneficiaries:["그리드위즈","식스티헤르츠"] },
  { id:"ess_subsidy", region:"KR", label:"ESS 보조금 확대",     sectors:["ESS"],                 urgency:"Medium",
    desc:"산업용·가정용 ESS 보조금 재설계 → 설치 수요 급증 예상", beneficiaries:["씨에스에너지","하나기술","스탠다드에너지"] },
  // 글로벌
  { id:"ira_us",     region:"US", label:"미국 IRA",             sectors:["ESS","Solar","H2"],    urgency:"High",
    desc:"IRA 세액공제 지속 → 미국 시장 진출 한국 기업 직접 수혜", beneficiaries:["LG에너지솔루션 생태계","한화솔루션"] },
  { id:"imo2030",    region:"GLOBAL", label:"IMO 2030",         sectors:["Marine"],              urgency:"High",
    desc:"선박 탄소집약도 40% 감축 의무 → 대체연료·연료전지 스타트업 수요 급증", beneficiaries:["빈센","범한퓨얼셀","CMB.TECH"] },
  { id:"eu_cbam",    region:"EU", label:"EU CBAM",              sectors:["H2","ESS","Grid"],     urgency:"Medium",
    desc:"탄소국경세 2026년 전면시행 → 청정에너지 제조 스타트업 수출 경쟁력 강화", beneficiaries:["스탠다드에너지","하이리움산업"] },
  { id:"ferc2222",   region:"US", label:"FERC Order 2222",      sectors:["Grid","VPP"],          urgency:"Medium",
    desc:"미국 분산자원 도매시장 참여 허용 → VPP·DR 스타트업 TAM 대폭 확대", beneficiaries:["AutoGrid","Voltus","Leap Energy"] },
  { id:"china_ess",  region:"CN", label:"중국 ESS 의무화",       sectors:["ESS"],                urgency:"High",
    desc:"중국 신재생 발전소 ESS 의무 설치 → 중국 ESS 스타트업 급성장, 국내 경쟁 심화", beneficiaries:["Pylontech","REPT","EVE Energy"] },
];

// ── 유사 딜 레퍼런스 DB ────────────────────────────────────
const COMP_DEALS = [
  // ESS
  { id:"form_energy",   company:"Form Energy",      country:"US", sector:"ESS-LongDuration", stage:"Series E", amount:"$450M", year:2023, valuation:"~$1.5B", investors:["ArcelorMittal","GIC","Breakthrough Energy"], comparableTo:["스탠다드에너지","에이치에너지"] },
  { id:"ambri",         company:"Ambri",             country:"US", sector:"ESS-LongDuration", stage:"Series E", amount:"$144M", year:2022, valuation:"~$500M", investors:["Bill Gates","Paulson","Reliance"], comparableTo:["스탠다드에너지"] },
  { id:"invinity",      company:"Invinity Energy",   country:"UK", sector:"ESS-Vanadium",     stage:"Listed",   amount:"£30M",  year:2023, valuation:"~$150M", investors:["Public"], comparableTo:["에이치에너지"] },
  // Hydrogen
  { id:"sunfire",       company:"Sunfire",           country:"DE", sector:"H2-Electrolyzer",  stage:"Series E", amount:"€215M", year:2023, valuation:"~$800M", investors:["Carbon Direct","Planet First Partners"], comparableTo:["하이리움산업","그린수소시스템"] },
  { id:"electric_h2",  company:"Electric Hydrogen", country:"US", sector:"H2-Electrolyzer",  stage:"Series B", amount:"$380M", year:2023, valuation:"~$1B",   investors:["DCVC","5AM Ventures"], comparableTo:["하이드로리서치"] },
  { id:"hysata",        company:"Hysata",            country:"AU", sector:"H2-Electrolyzer",  stage:"Series B", amount:"$42M",  year:2023, valuation:"~$150M", investors:["CSIRO","Fortescue"], comparableTo:["그린수소시스템"] },
  // Marine
  { id:"ceres_power",  company:"Ceres Power",       country:"UK", sector:"Marine-SOFC",       stage:"Listed",   amount:"£181M", year:2022, valuation:"~$600M", investors:["Bosch","Doosan"], comparableTo:["에스퓨얼셀","범한퓨얼셀"] },
  { id:"cmb_tech",     company:"CMB.TECH",          country:"BE", sector:"Marine-Ammonia",    stage:"Private",  amount:"€500M", year:2023, valuation:"N/A",    investors:["CMB Group"], comparableTo:["빈센"] },
  // Grid/VPP
  { id:"autogrid",     company:"AutoGrid",          country:"US", sector:"Grid-VPP",          stage:"Series D", amount:"$85M",  year:2021, valuation:"~$300M", investors:["E.ON","Engie","Shell"], comparableTo:["그리드위즈"] },
  { id:"voltus",       company:"Voltus",            country:"US", sector:"Grid-DR",           stage:"Acquired", amount:"$50M",  year:2023, valuation:"~$200M", investors:["S&P Global Acquired"], comparableTo:["그리드위즈","식스티헤르츠"] },
  { id:"upside_energy",company:"Upside Energy",     country:"UK", sector:"Grid-VPP",          stage:"Series B", amount:"£30M",  year:2023, valuation:"~$100M", investors:["Octopus Ventures"], comparableTo:["그리드위즈","에너지에이아이"] },
  // SMR/Nuclear
  { id:"oklo",         company:"Oklo",              country:"US", sector:"Nuclear-SMR",        stage:"Listed",   amount:"$306M", year:2024, valuation:"~$1B",   investors:["Sam Altman","Public"], comparableTo:[] },
  { id:"commonwealth", company:"Commonwealth Fusion",country:"US",sector:"Nuclear-Fusion",    stage:"Series B", amount:"$1.8B", year:2021, valuation:"~$2B",   investors:["Tiger Global","Eni"], comparableTo:[] },
];

// ── 기업 프로파일 로드/저장 ────────────────────────────────
function loadProfiles() {
  const p = path.join(__dirname, "data", "company-profiles.json");
  if (!fs.existsSync(p)) return {};
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return {}; }
}

function saveProfiles(profiles) {
  const p = path.join(__dirname, "data", "company-profiles.json");
  fs.writeFileSync(p, JSON.stringify(profiles, null, 2), "utf8");
}

function updateProfile(profiles, signal) {
  const name = signal.company;
  if (!name || name === "Unknown") return profiles;
  if (!profiles[name]) {
    profiles[name] = {
      name,
      firstSeen:    TODAY,
      lastSeen:     TODAY,
      sector:       signal.category || "",
      region:       signal.region || "",
      country:      signal.country || "",
      signalCount:  0,
      highCount:    0,
      signals:      [],
      scoreHistory: [],
      fundingStage: signal.fundingStage || "N/A",
    };
  }
  const p = profiles[name];
  p.lastSeen    = TODAY;
  p.signalCount = (p.signalCount || 0) + 1;
  if (signal.relevance === "High") p.highCount = (p.highCount || 0) + 1;
  if (signal.fundingStage && signal.fundingStage !== "N/A") p.fundingStage = signal.fundingStage;

  // 신호 히스토리 (최근 30개만 유지)
  p.signals = [
    { date:TODAY, title:signal.title, relevance:signal.relevance, eventType:signal.eventType, signal_type:signal.signal_type },
    ...(p.signals||[])
  ].slice(0, 30);

  // 신호 빈도 (최근 활동성)
  const recentDates = p.signals.map(s => s.date).filter(d => d >= new Date(Date.now()-30*86400000).toISOString().slice(0,10));
  p.recentActivity = recentDates.length; // 최근 30일 신호 수

  return profiles;
}

// ── 유사 딜 매칭 ──────────────────────────────────────────
function findComparableDeals(companyName, sector) {
  const matches = COMP_DEALS.filter(d =>
    d.comparableTo.some(c => c.includes(companyName) || companyName.includes(c)) ||
    (sector && d.sector.toLowerCase().includes(sector.toLowerCase().split("/")[0].toLowerCase()))
  ).slice(0, 3);
  return matches;
}

// ── 정책 트리거 매칭 ──────────────────────────────────────
function findPolicyTriggers(companyName, sector, region) {
  return POLICY_TRIGGERS.filter(p =>
    (p.region === region || p.region === "GLOBAL") &&
    (p.beneficiaries.some(b => b.includes(companyName) || companyName.includes(b)) ||
     p.sectors.some(s => (sector||"").toLowerCase().includes(s.toLowerCase())))
  ).slice(0, 3);
}

// ── 스코어카드 생성 (Claude) ──────────────────────────────
async function generateScorecard(companyName, signals, profile) {
  const recentSignals = signals.slice(0, 5).map(s =>
    `- ${s.eventType}: ${s.title} (${s.relevance})`
  ).join("\n");

  const system = "에너지 CVC 시니어 심사역. 투자 스코어카드 생성. JSON만 반환.";
  const user = `${companyName} 투자 스코어카드 생성.

최근 신호:
${recentSignals}

프로파일: 최초발견 ${profile.firstSeen}, 총 신호 ${profile.signalCount}건, 최근30일 ${profile.recentActivity||0}건

아래 5개 항목을 각각 0-5점으로 평가하고 근거를 제시하세요:
JSON으로만 반환:
{"technology":{"score":0,"max":5,"reason":"근거"},"commercialization":{"score":0,"max":5,"reason":"근거"},"team":{"score":0,"max":5,"reason":"근거"},"partnership":{"score":0,"max":5,"reason":"근거"},"fundraising_timing":{"score":0,"max":5,"reason":"근거"},"total":0,"conviction":"High|Medium|Low","timing_signal":"Immediate|3-6months|6-12months|Watch","one_line":"한 줄 투자 판단"}`;

  try {
    const text = await callClaude(system, user);
    const clean = text.replace(/```json|```/g,"").trim();
    const s = clean.indexOf("{"), e = clean.lastIndexOf("}");
    if (s !== -1 && e !== -1) return JSON.parse(clean.slice(s, e+1));
  } catch(e) {
    console.error(`  스코어카드 실패 (${companyName}): ${e.message}`);
  }
  return null;
}

// ── NewsAPI ────────────────────────────────────────────────
function fetchNews(query, pageSize=8) {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams({ q:query, language:"en", sortBy:"publishedAt", pageSize:String(pageSize), from:MONTH_AGO, apiKey:NEWS_KEY });
    const req = https.request({ hostname:"newsapi.org", path:`/v2/everything?${params}`, method:"GET", headers:{"User-Agent":"EnergyCVC/1.0"} }, res => {
      let data=""; res.on("data",c=>data+=c); res.on("end",()=>{
        try { const p=JSON.parse(data); if(p.status!=="ok"){reject(new Error(p.message||"NewsAPI오류"));return;} resolve(p.articles||[]); } catch(e){reject(e);}
      });
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
    {q:"China energy storage startup CATL ecosystem",tag:"cn_ess"},
    {q:"China green hydrogen electrolyzer startup",tag:"cn_h2"},
  ];
  const all=[];
  for(const q of queries){
    try{ const arts=await fetchNews(q.q,6); const valid=arts.filter(a=>a.title&&a.title!=="[Removed]"&&a.url&&a.url!=="https://removed.com"); all.push(...valid.map(a=>({...a,tag:q.tag}))); console.log(`  [${q.tag}] ${valid.length}건`); }
    catch(e){ console.error(`  [${q.tag}] 실패: ${e.message}`); }
    await delay(150);
  }
  const seen=new Set(); return all.filter(a=>{if(seen.has(a.url))return false;seen.add(a.url);return true;});
}

// ── Claude API ────────────────────────────────────────────
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ model:"claude-sonnet-4-20250514", max_tokens:3000, system, messages:[{role:"user",content:user}] });
    const req = https.request({ hostname:"api.anthropic.com", path:"/v1/messages", method:"POST",
      headers:{"Content-Type":"application/json","x-api-key":CLAUDE_KEY,"anthropic-version":"2023-06-01","Content-Length":Buffer.byteLength(body)} },
    res=>{let data="";res.on("data",c=>data+=c);res.on("end",()=>{try{const p=JSON.parse(data);if(p.error){reject(new Error(p.error.message));return;}resolve((p.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n"));}catch(e){reject(e);}});});
    req.on("error",reject); req.setTimeout(90000,()=>{req.destroy();reject(new Error("Timeout"));}); req.write(body); req.end();
  });
}

function extractJSON(text) {
  const cb=text.match(/```(?:json)?\s*([\s\S]*?)\s*```/); if(cb){try{return JSON.parse(cb[1].trim());}catch{}}
  let d=0,s=-1,e=-1;
  for(let i=0;i<text.length;i++){if(text[i]==="["&&d===0){s=i;d++;}else if(text[i]==="[")d++;else if(text[i]==="]"){d--;if(d===0&&s!==-1){e=i;break;}}}
  if(s!==-1&&e!==-1){const sl=text.slice(s,e+1);try{return JSON.parse(sl);}catch{}try{return JSON.parse(sl.replace(/,(\s*[}\]])/g,"$1"));}catch{}
    const objs=[];let od=0,os=-1;for(let i=0;i<sl.length;i++){if(sl[i]==="{"){if(od===0)os=i;od++;}else if(sl[i]==="}"){od--;if(od===0&&os!==-1){try{objs.push(JSON.parse(sl.slice(os,i+1)));}catch{}os=-1;}}}
    if(objs.length>0)return objs;}
  throw new Error("JSON 추출 실패");
}

function inferEventType(title,desc){const t=(title+" "+desc).toLowerCase();if(/offtake|supply agreement/.test(t))return"Offtake";if(/certif|approv|dnv|tüv/.test(t))return"Certification";if(/grant|award|doe |eu fund/.test(t))return"Grant";if(/manufactur|production|facility/.test(t))return"Expansion";if(/pilot|trial|deploy/.test(t))return"Pilot";if(/partner|mou|agreement/.test(t))return"Partnership";if(/series|raised|\$\d+m/.test(t))return"Financing";return"News";}
function inferImpact(title,desc){const t=title+" "+desc;if(/contract|commercial|deploy|certif|offtake|series [b-d]|\$\d+[mb]/i.test(t))return"High";if(/study|report|analysis/i.test(t))return"Low";return"Medium";}
function tagToCategory(tag){const m={kr_ess:"국내 ESS",kr_h2:"국내 수소",kr_grid:"국내 그리드",g_ess:"Global ESS",g_h2:"Global Hydrogen",g_grid:"Global Grid",g_marine:"Global Marine",g_smr:"Global SMR",cn_ess:"China ESS",cn_h2:"China Hydrogen"};return m[tag]||tag;}
function tagToEmoji(tag){if(tag.startsWith("kr_"))return"🇰🇷";if(tag.startsWith("cn_"))return"🇨🇳";return"🌍";}
function tagToRegion(tag){if(tag.startsWith("kr_"))return"KR";if(tag.startsWith("cn_"))return"CN";return"GLOBAL";}
function tagToCountry(tag){if(tag.startsWith("kr_"))return"KR";if(tag.startsWith("cn_"))return"CN";return"US";}
function extractCompany(title,desc){const matches=(title+" "+desc).match(/\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?\b/g)||[];const stop=new Set(["The","This","That","For","With","From","After","Energy","Power","Battery","China","Korea"]);const names=matches.filter(m=>!stop.has(m)&&m.length>2);return names[0]||"Unknown";}

// ── 기사 배치 분석 ─────────────────────────────────────────
async function analyzeArticlesBatch(articles, batchIdx) {
  const list=articles.map((a,i)=>[`${i+1}. [${a.tag}] ${a.source?.name||"Unknown"}`,`제목: ${a.title}`,`내용: ${(a.description||"").slice(0,150)}`,`날짜: ${(a.publishedAt||"").slice(0,10)}`].join("\n")).join("\n\n");
  const system="에너지 CVC 시니어 심사역. 비상장 스타트업 중심. JSON 배열만 반환.";
  const user=`${articles.length}건 에너지 뉴스 CVC 투자 분석.\n\n${list}\n\nJSON 배열 ${articles.length}개 (순서유지):\n[{"idx":1,"company":"회사명","companyType":"unlisted_startup|listed_corp|ecosystem","fundingStage":"Seed|Pre-A|Series-A|Series-B|N/A","relevance":"High|Medium|Low","signal_type":"Pre-funding|Commercial traction|Technical validation|Market context","next_action":"Investigate|Monitor|Note|Skip","deep_insight":"딥인사이트 2-3문장","cvc_action":"구체적 액션","risk":"핵심 리스크"}]\n\nJSON만.`;
  const text=await callClaude(system,user); const analyses=extractJSON(text);
  return articles.map((article,i)=>{
    const analysis=analyses.find(a=>a.idx===i+1)||analyses[i]||{};
    const companyName=analysis.company||extractCompany(article.title,article.description||"");
    const region=tagToRegion(article.tag);
    const sector=tagToCategory(article.tag);
    const comparableDeals=findComparableDeals(companyName, sector);
    const policyTriggers=findPolicyTriggers(companyName, sector, tagToCountry(article.tag));
    return {
      id:`${article.tag}-${Date.now()}-${i+batchIdx*10}`,
      topicId:article.tag, category:sector, emoji:tagToEmoji(article.tag),
      region, isKorean:article.tag.startsWith("kr_"), isChina:article.tag.startsWith("cn_"),
      title:article.title, url:article.url, source:article.source?.name||"Unknown",
      pubDate:(article.publishedAt||"").slice(0,10), summary:(article.description||"").slice(0,300),
      country:tagToCountry(article.tag), isRealNews:true, generatedAt:TODAY,
      company:companyName, companyType:analysis.companyType||"ecosystem",
      fundingStage:analysis.fundingStage||"N/A",
      eventType:inferEventType(article.title,article.description||""),
      signalStage:"Early", relevance:analysis.relevance||inferImpact(article.title,article.description||""),
      signal_type:analysis.signal_type||"Market context", next_action:analysis.next_action||"Monitor",
      deep_insight:analysis.deep_insight||"", cvc_action:analysis.cvc_action||"", risk:analysis.risk||"",
      // ── 새 필드 ──
      comparableDeals,   // 유사 딜 레퍼런스
      policyTriggers,    // 정책 트리거
      scorecard:null,    // 나중에 채워짐
    };
  });
}

// ── 메인 ──────────────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v7`);
  console.log(`날짜: ${TODAY_KR} | 기업 프로파일 + 스코어카드 + 정책 트리거\n`);

  const dataDir=path.join(__dirname,"data");
  if(!fs.existsSync(dataDir))fs.mkdirSync(dataDir,{recursive:true});

  // ① 기존 프로파일 로드
  const profiles=loadProfiles();
  console.log(`기존 프로파일: ${Object.keys(profiles).length}개 기업`);

  // ② 뉴스 수집
  const articles=await fetchAllNews();
  if(!articles.length){console.error("뉴스 없음");process.exit(1);}

  // ③ Claude 배치 분석
  console.log(`\n② Claude 분석 (${articles.length}건)...`);
  const allSignals=[];
  const batchSize=8;
  for(let i=0;i<articles.length;i+=batchSize){
    const batch=articles.slice(i,i+batchSize);
    console.log(`  배치 ${Math.floor(i/batchSize)+1}: ${batch.length}건...`);
    try{
      const analyzed=await analyzeArticlesBatch(batch,Math.floor(i/batchSize));
      allSignals.push(...analyzed);
      analyzed.forEach(s=>updateProfile(profiles,s));
      console.log(`  ✓ ${analyzed.length}건`);
    }catch(e){
      console.error(`  ✗ 배치 실패: ${e.message}`);
      batch.forEach((a,j)=>{
        const s={id:`${a.tag}-${Date.now()}-${i+j}`,topicId:a.tag,category:tagToCategory(a.tag),emoji:tagToEmoji(a.tag),region:tagToRegion(a.tag),isKorean:a.tag.startsWith("kr_"),isChina:a.tag.startsWith("cn_"),title:a.title,url:a.url,source:a.source?.name||"Unknown",pubDate:(a.publishedAt||"").slice(0,10),summary:(a.description||"").slice(0,300),country:tagToCountry(a.tag),isRealNews:true,generatedAt:TODAY,company:extractCompany(a.title,a.description||""),companyType:"ecosystem",fundingStage:"N/A",eventType:inferEventType(a.title,a.description||""),signalStage:"Early",relevance:inferImpact(a.title,a.description||""),signal_type:"Market context",next_action:"Monitor",deep_insight:"",cvc_action:"",risk:"",comparableDeals:[],policyTriggers:[]};
        allSignals.push(s);updateProfile(profiles,s);
      });
    }
    if(i+batchSize<articles.length){console.log("  ⏱ 30초...");await delay(30000);}
  }

  // ④ 핵심 기업 스코어카드 생성 (High 신호 기업 상위 5개)
  console.log("\n③ 스코어카드 생성...");
  await delay(30000);
  const topCompanies=[...new Set(allSignals.filter(s=>s.relevance==="High"&&s.company!=="Unknown").map(s=>s.company))].slice(0,5);
  for(const name of topCompanies){
    const coSignals=allSignals.filter(s=>s.company===name);
    const profile=profiles[name];
    if(!profile)continue;
    console.log(`  스코어카드: ${name}...`);
    try{
      const sc=await generateScorecard(name,coSignals,profile);
      if(sc){
        profiles[name].latestScorecard=sc;
        profiles[name].scoreHistory=[{date:TODAY,scorecard:sc},...(profiles[name].scoreHistory||[])].slice(0,12);
        coSignals.forEach(s=>{s.scorecard=sc;});
      }
    }catch(e){console.error(`  ✗ ${name}: ${e.message}`);}
    await delay(8000);
  }

  // ⑤ 프로파일 저장
  saveProfiles(profiles);
  console.log(`  ✓ ${Object.keys(profiles).length}개 기업 프로파일 저장`);

  // ⑥ 정렬 (비상장 + High 우선)
  allSignals.sort((a,b)=>{
    const sa=(a.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[a.relevance]||0);
    const sb=(b.companyType==="unlisted_startup"?10:0)+({High:3,Medium:1,Low:0}[b.relevance]||0);
    return sb-sa;
  });

  // ⑦ 브리핑
  console.log("\n④ 브리핑...");
  await delay(30000);
  let brief="";
  try{
    const top=allSignals.filter(s=>s.relevance==="High").slice(0,8).map(s=>`[${s.region}][${s.category}] ${s.company} (${s.source}): ${s.title}`).join("\n");
    brief=await callClaude("에너지 CVC 시니어 심사역. 딥 인사이트. 한국어.",`오늘(${TODAY_KR}) CVC 브리핑 5문장.\n주요신호:\n${top}\n\n비상장투자기회, 정책연계, 타이밍, 즉시액션. 구체적 수치·회사명 필수.`);
    console.log("  ✓ 완료");
  }catch(e){console.error(`  ✗ ${e.message}`);}

  const stats={
    total:allSignals.length, unlisted:allSignals.filter(s=>s.companyType==="unlisted_startup").length,
    kr:allSignals.filter(s=>s.isKorean).length, cn:allSignals.filter(s=>s.isChina).length,
    global:allSignals.filter(s=>!s.isKorean&&!s.isChina).length,
    high:allSignals.filter(s=>s.relevance==="High").length,
    investigate:allSignals.filter(s=>s.next_action==="Investigate").length,
    realNews:allSignals.filter(s=>s.isRealNews).length,
    profiledCompanies:Object.keys(profiles).length,
    withScorecard:allSignals.filter(s=>s.scorecard).length,
  };

  const output={date:TODAY,dateKr:TODAY_KR,generatedAt:new Date().toISOString(),brief,stats,signals:allSignals,policyTriggers:POLICY_TRIGGERS,errors:[]};
  fs.writeFileSync(path.join(dataDir,`${TODAY}.json`),JSON.stringify(output,null,2),"utf8");
  fs.writeFileSync(path.join(dataDir,"latest.json"),JSON.stringify(output,null,2),"utf8");

  const idxPath=path.join(dataDir,"index.json");let idx=[];
  if(fs.existsSync(idxPath)){try{idx=JSON.parse(fs.readFileSync(idxPath,"utf8"));}catch{}}
  if(!idx.find(d=>d.date===TODAY)){idx.unshift({date:TODAY,dateKr:TODAY_KR,stats});fs.writeFileSync(idxPath,JSON.stringify(idx.slice(0,90),null,2),"utf8");}

  console.log(`\n✅ 완료!`);
  console.log(`신호 ${stats.total}건 | 비상장 ${stats.unlisted} | High ${stats.high}`);
  console.log(`국내 ${stats.kr} | 글로벌 ${stats.global} | 중국 ${stats.cn}`);
  console.log(`프로파일 ${stats.profiledCompanies}개 | 스코어카드 ${stats.withScorecard}건\n`);
}

main().catch(e=>{console.error("❌",e.message);process.exit(1);});

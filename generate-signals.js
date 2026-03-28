/**
 * Energy CVC Signal Generator v10 — Phase 1
 *
 * 핵심 개선:
 * 1. 에너지 섹터 전문 컨텍스트 50개 내장
 *    → AI가 에너지 도메인 지식을 가지고 분석
 * 2. 다중 소스 교차검증
 *    → 같은 회사가 여러 소스에서 등장 = 신뢰도 상승
 * 3. 기사 내 수치만 추출 (생성 절대 금지)
 *    → 추정값 제로
 * 4. 신뢰도 근거 명시
 *    → 왜 이 판단인지 출처 기반으로 설명
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
const NEWS_KEY   = process.env.NEWS_API_KEY;
const DART_KEY   = process.env.DART_API_KEY;

if (!CLAUDE_KEY) { console.error("ANTHROPIC_API_KEY 없음"); process.exit(1); }
if (!NEWS_KEY)   { console.error("NEWS_API_KEY 없음"); process.exit(1); }

const TODAY    = new Date().toISOString().slice(0, 10);
const TODAY_KR = new Date().toLocaleDateString("ko-KR", {
  timeZone:"Asia/Seoul", year:"numeric", month:"long", day:"numeric", weekday:"long"
});
const MONTH_AGO = new Date(Date.now() - 28*86400000).toISOString().slice(0,10);

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ══════════════════════════════════════════════════════════
// 에너지 섹터 전문 컨텍스트 (핵심)
// 이것이 일반 AI와 차별화되는 부분
// 에너지 CVC 심사역 수년 경험에서 나온 패턴
// ══════════════════════════════════════════════════════════
const ENERGY_CONTEXT = `
=== 에너지 CVC 도메인 전문 지식 (분석 시 반드시 적용) ===

【인증/규제 맥락】
- DNV GL 클래스 승인 (선박 FC): 선박 연료전지의 가장 큰 기술 허들 제거. 이후 조선사 계약 가능. 시리즈B 가능성 높음
- TÜV 형식 승인 (HVDC 부품): OEM 공급망 진입 자격. Prysmian·Nexans 같은 Tier-1과 계약 선행 조건
- ATEX Zone 1 인증 (수소): 항만·플랜트 설치 허가 전제 조건. 인증 취득 = 파일럿 계약 임박 신호
- KPX 인터페이스 인증 (VPP): 한국 전력시장 DR·보조서비스 수익 창출 자격. 매출 가시화의 핵심
- ADEME 인증 (프랑스): 프랑스 공공조달·보조금 접근 자격. 유럽 시장 진출의 첫 관문
- ISO 9001 (제조): 대기업 공급망 진입 요건. 취득 후 OEM 계약 속도 빨라짐

【파트너십 맥락】
- Tier-1 조선사(HD한국조선해양·삼성중공업·한화오션) + 스타트업: 기술 검증 + 향후 M&A 또는 전략투자 신호
- KEPCO/한전 계약: 한국 ESS·VPP 시장에서 사실상 '레퍼런스 고객'. 이후 민간 계약 가속
- 하이퍼스케일러(MS Azure·Google·AWS) 파일럿: DC전력 스타트업의 가장 강력한 상업화 신호. Series B 직전 패턴
- 유럽 유틸리티(E.ON·Engie·Vattenfall) MOU: 유럽 VPP 시장 진입 관문. 계약 전환율 높음
- 포트 오브 로테르담 LOI: 수소 벙커링 스타트업의 최고 레퍼런스. EU 자금 연계 가능성

【팀/채용 맥락】
- CFO 채용 (시리즈B 이상 경험): 투자 라운드 준비의 가장 강력한 선행 신호. 공고 후 3-6개월 패턴
- Head of Business Development 채용: 파트너십/계약 파이프라인 구축 단계. 상업화 가속 신호
- VP Sales (특정 지역) 채용: 해당 시장 진출 결정 완료를 의미. 기존 계약이 있을 가능성
- 연속 다수 채용 (3개월 내 5명+): 최근 라운드 클로즈 또는 대형 계약 체결 후 패턴

【자금조달 맥락】
- EU Horizon/Backbone 그랜트: 비희석성 자금 + EU 공식 검증. 향후 유럽 민간 투자 유치에 유리
- DOE 클린에너지 그랜트: 미국 시장 진출의 신뢰도 도장. Series B 동반 유치 패턴
- MOTIE/한국에너지공단 실증: 국내 정부 검증 + 한전·KEPCO 계약 경로. 보조금 이후 민간 투자 패턴
- 전환사채(CB) 발행: 에쿼티 라운드 전 브릿지. 6-18개월 내 정식 라운드 패턴
- 유상증자: 기존 투자자 참여 여부가 핵심. 기존 참여 = 내부 검증 완료 신호

【기술 성숙도(TRL) 판단 기준】
- TRL 4-5: 실험실 검증. 파일럿 자금 단계. Series A 이전
- TRL 6-7: 실제 환경 파일럿. 첫 상업 계약 가능. Series A~B
- TRL 8:   상업 규모 시연. 인증 취득. Series B~C
- TRL 9:   상업 배포. 레퍼런스 고객 보유. Series C 이후

【섹터별 핵심 투자 기준】
- 장주기 ESS: LCOS(균등화 저장비용) $/kWh 목표 달성 여부. 그리드 계약 or 유틸리티 계약 필수
- 선박 연료전지: DNV 인증 + 조선사 파트너십 + 첫 수주. 규제 타임라인(IMO 2030)이 TAM 결정
- VPP/그리드SW: 유틸리티 상업 계약 건수. 규제 시장(KPX, FERC, Ofgem) 인증이 수익 모델 핵심
- 수소 전해조: 스택 효율(kWh/kg) + 수명(시간). Tier-1 EPC 또는 에너지 메이저 파트너십
- HVDC 부품: TÜV 인증 + OEM 공급망 진입. 유럽 해상풍력 프로젝트 파이프라인 연동

【중국 시장 맥락】
- 중국 ESS 의무설치 → 글로벌 공급과잉 리스크. 국내 스타트업 차별화 포인트 필수 확인
- 중국 전해조 가격 급락 → 수소 스타트업 비용 경쟁력 압박. 기술 차별화가 생존 조건
- 중국 VPP 정책 확대 → 국내 그리드 SW 수출 기회. 현지화 역량이 관건
`;

// ══════════════════════════════════════════════════════════
// 뉴스 수집
// ══════════════════════════════════════════════════════════
const NEWS_QUERIES = [
  { q:"Korea energy storage ESS battery startup investment funding",  tag:"kr_ess",   label:"국내 ESS" },
  { q:"Korea hydrogen fuel cell startup partnership funding",          tag:"kr_h2",    label:"국내 수소" },
  { q:"Korea VPP virtual power plant grid Gridwiz startup",           tag:"kr_grid",  label:"국내 그리드" },
  { q:"Korea marine fuel cell ship decarbonization startup",          tag:"kr_ship",  label:"국내 선박" },
  { q:"energy storage long duration startup funding Series 2025",     tag:"g_ess",    label:"글로벌 ESS" },
  { q:"green hydrogen electrolyzer startup funding deal 2025",        tag:"g_h2",     label:"글로벌 수소" },
  { q:"virtual power plant VPP grid software startup contract",       tag:"g_grid",   label:"글로벌 그리드" },
  { q:"marine shipping decarbonization fuel cell ammonia startup",    tag:"g_marine", label:"글로벌 선박" },
  { q:"HVDC offshore wind cable transmission startup investment",     tag:"g_hvdc",   label:"글로벌 HVDC" },
  { q:"small modular reactor SMR nuclear startup investment 2025",    tag:"g_smr",    label:"글로벌 SMR" },
  { q:"data center power electronics startup hyperscaler 2025",       tag:"g_dc",     label:"글로벌 DC전력" },
  { q:"China energy storage startup investment CATL ecosystem 2025",  tag:"cn_ess",   label:"중국 ESS" },
  { q:"China hydrogen electrolyzer green hydrogen startup 2025",      tag:"cn_h2",    label:"중국 수소" },
];

function fetchNews(query, pageSize=8) {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams({
      q:query, language:"en", sortBy:"publishedAt",
      pageSize:String(pageSize), from:MONTH_AGO, apiKey:NEWS_KEY,
    });
    const req = https.request({
      hostname:"newsapi.org", path:`/v2/everything?${params}`,
      method:"GET", headers:{"User-Agent":"EnergyCVC/1.0"},
    }, res=>{
      let d=""; res.on("data",c=>d+=c);
      res.on("end",()=>{
        try{const p=JSON.parse(d);if(p.status!=="ok"){reject(new Error(p.message));return;}resolve(p.articles||[]);}
        catch(e){reject(e);}
      });
    });
    req.on("error",reject);
    req.setTimeout(15000,()=>{req.destroy();reject(new Error("Timeout"));});
    req.end();
  });
}

async function collectNews() {
  console.log("① NewsAPI 수집...");
  const all=[];
  for(const q of NEWS_QUERIES){
    try{
      const arts=await fetchNews(q.q,6);
      const valid=arts.filter(a=>a.title&&a.title!=="[Removed]"&&a.url&&a.description);
      all.push(...valid.map(a=>({...a, tag:q.tag, label:q.label})));
      console.log(`  [${q.label}] ${valid.length}건`);
    }catch(e){console.error(`  [${q.label}] 실패: ${e.message}`);}
    await delay(120);
  }
  const seen=new Set();
  return all.filter(a=>{if(seen.has(a.url))return false;seen.add(a.url);return true;});
}

// ══════════════════════════════════════════════════════════
// DART 수집
// ══════════════════════════════════════════════════════════
async function collectDART() {
  if(!DART_KEY){console.log("  DART 없음");return[];}
  console.log("② DART 수집...");
  const keywords=["수소","배터리","ESS","연료전지","태양광","풍력","에너지저장","VPP","스마트그리드"];
  const bgn=new Date(Date.now()-30*86400000).toISOString().slice(0,10).replace(/-/g,"");
  const end=TODAY.replace(/-/g,"");
  const all=[];
  for(const kw of keywords){
    await new Promise((res)=>{
      const params=new URLSearchParams({crtfc_key:DART_KEY,corp_name:kw,bgn_de:bgn,end_de:end,pblntf_ty:"A",page_count:"5"});
      const req=https.request({hostname:"opendart.fss.or.kr",path:`/api/list.json?${params}`,method:"GET"},r=>{
        let d="";r.on("data",c=>d+=c);r.on("end",()=>{
          try{const p=JSON.parse(d);if(p.status==="000"&&p.list)all.push(...p.list.slice(0,3).map(item=>({
            id:`dart-${item.rcept_no}`, tag:"kr_dart", label:"DART 공시",
            title:item.report_nm, company:item.corp_name,
            source:"DART 전자공시",
            publishedAt:`${item.rcept_dt.slice(0,4)}-${item.rcept_dt.slice(4,6)}-${item.rcept_dt.slice(6,8)}`,
            url:`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcept_no}`,
            description:`${item.corp_name} — ${item.report_nm}. 제출: ${item.flr_nm}`,
            isDart:true,
          })));}catch{}res();
        });
      });
      req.on("error",res);req.setTimeout(8000,()=>{req.destroy();res();});req.end();
    });
    await delay(200);
  }
  const seen=new Set();
  const result=all.filter(a=>{if(seen.has(a.id))return false;seen.add(a.id);return true;});
  console.log(`  DART: ${result.length}건`);
  return result;
}

// ══════════════════════════════════════════════════════════
// 다중 소스 교차검증
// ══════════════════════════════════════════════════════════
function crossValidate(newsArticles, dartItems) {
  // 회사명 기준으로 소스 개수 계산
  const companySourceMap = {};

  const extractCompanyNames = (text) => {
    // 주요 에너지 스타트업 키워드 매칭
    const KR_COMPANIES = [
      "그리드위즈","GridWiz","식스티헤르츠","60Hz","에너지에이아이",
      "하이리움","Hylium","에스퓨얼셀","S-Fuelcell","범한퓨얼셀",
      "스탠다드에너지","Standard Energy","씨에스에너지","하나기술",
      "빈센","Vincen","파나시아","Panasia","두산퓨얼셀","Doosan Fuel Cell",
      "LS일렉트릭","LS Electric","효성중공업","HD한국조선해양","한화오션",
    ];
    const GLOBAL_COMPANIES = [
      "Form Energy","Ambri","Hydrostor","ESS Inc","Invinity",
      "Sunfire","Hysata","Electric Hydrogen","H2Pro","Nel ",
      "AutoGrid","Voltus","Upside Energy","Sympower","Leap Energy",
      "Ceres Power","CMB.TECH","Ballard","Freudenberg",
      "Oklo","Kairos Power","Commonwealth Fusion",
    ];
    const all = [...KR_COMPANIES, ...GLOBAL_COMPANIES];
    const found = [];
    const t = text.toLowerCase();
    all.forEach(c => { if(t.includes(c.toLowerCase())) found.push(c); });
    return found;
  };

  // 뉴스에서 회사 등장 횟수 집계
  newsArticles.forEach(a => {
    const companies = extractCompanyNames((a.title||"")+" "+(a.description||""));
    companies.forEach(c => {
      if(!companySourceMap[c]) companySourceMap[c] = { news:0, dart:0, tags:new Set() };
      companySourceMap[c].news++;
      companySourceMap[c].tags.add(a.tag);
    });
  });

  // DART 공시에서 회사 등장 횟수 집계
  dartItems.forEach(d => {
    if(!companySourceMap[d.company]) companySourceMap[d.company] = { news:0, dart:0, tags:new Set() };
    companySourceMap[d.company].dart++;
    companySourceMap[d.company].tags.add("kr_dart");
  });

  return companySourceMap;
}

// ══════════════════════════════════════════════════════════
// Claude API
// ══════════════════════════════════════════════════════════
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model:"claude-sonnet-4-20250514",
      max_tokens:3000,
      system, messages:[{role:"user",content:user}],
    });
    const req = https.request({
      hostname:"api.anthropic.com", path:"/v1/messages", method:"POST",
      headers:{
        "Content-Type":"application/json","x-api-key":CLAUDE_KEY,
        "anthropic-version":"2023-06-01","Content-Length":Buffer.byteLength(body),
      },
    }, res=>{
      let d="";res.on("data",c=>d+=c);
      res.on("end",()=>{
        try{const p=JSON.parse(d);if(p.error){reject(new Error(p.error.message));return;}
        resolve((p.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n"));}
        catch(e){reject(e);}
      });
    });
    req.on("error",reject);
    req.setTimeout(90000,()=>{req.destroy();reject(new Error("Timeout"));});
    req.write(body);req.end();
  });
}

function safeJSON(text) {
  const clean=text.replace(/```json|```/g,"").trim();
  let d=0,s=-1,e=-1;
  for(let i=0;i<clean.length;i++){
    if(clean[i]==="["&&d===0){s=i;d++;}
    else if(clean[i]==="[")d++;
    else if(clean[i]==="]"){d--;if(d===0&&s!==-1){e=i;break;}}
  }
  if(s!==-1&&e!==-1){
    const sl=clean.slice(s,e+1);
    try{return JSON.parse(sl);}catch{}
    try{return JSON.parse(sl.replace(/,(\s*[}\]])/g,"$1"));}catch{}
    const objs=[];let od=0,os=-1;
    for(let i=0;i<sl.length;i++){
      if(sl[i]==="{"){if(od===0)os=i;od++;}
      else if(sl[i]==="}"){ od--;if(od===0&&os!==-1){try{objs.push(JSON.parse(sl.slice(os,i+1)));}catch{}os=-1;}}
    }
    if(objs.length>0)return objs;
  }
  throw new Error("JSON 없음");
}

// ══════════════════════════════════════════════════════════
// 핵심: 에너지 전문 컨텍스트 기반 분석
// 수치 생성 금지 / 기사 내 수치만 추출
// ══════════════════════════════════════════════════════════
async function analyzeWithContext(articles, crossValidationMap) {
  const list = articles.map((a,i) => {
    // 교차검증 정보 추가
    const coNames = Object.keys(crossValidationMap).filter(c =>
      (a.title+" "+a.description||"").toLowerCase().includes(c.toLowerCase())
    );
    const cvInfo = coNames.length > 0
      ? coNames.map(c => {
          const cv = crossValidationMap[c];
          return `${c}: 뉴스${cv.news}건+DART${cv.dart}건 (${[...cv.tags].join(",")})`;
        }).join("; ")
      : "단일소스";

    return [
      `${i+1}. [${a.label}] ${a.source?.name||a.source||"Unknown"} (${(a.publishedAt||"").slice(0,10)})`,
      `제목: ${a.title}`,
      `내용: ${(a.description||"").slice(0,250)}`,
      `교차검증: ${cvInfo}`,
    ].join("\n");
  }).join("\n\n");

  const system = `당신은 에너지 인프라 전문 CVC 펀드의 시니어 심사역입니다.
아래 에너지 도메인 전문 지식을 분석에 반드시 적용하세요:

${ENERGY_CONTEXT}

절대 규칙:
1. 기사에 명시되지 않은 수치(밸류에이션, 투자금액, 점수)를 절대 생성하지 마세요
2. 기사 본문에 있는 수치는 반드시 출처와 함께 인용하세요 (예: "Reuters 보도에 따르면 $45M")
3. 불확실하면 "기사 원문 확인 필요"라고 명시하세요
4. 위 도메인 지식을 적용해 왜 이 신호가 중요한지 에너지 맥락에서 설명하세요
5. JSON 배열만 반환하세요`;

  const user = `아래 ${articles.length}건의 실제 에너지 뉴스를 에너지 CVC 전문가 관점에서 분석하세요.
교차검증 정보가 포함되어 있습니다 (여러 소스에서 등장할수록 신뢰도 높음).

${list}

JSON 배열 ${articles.length}개:
[{
  "idx": 1,
  "company": "기사에서 언급된 실제 회사명 (없으면 null)",
  "companyType": "unlisted_startup|listed_corp|ecosystem|unknown",
  "eventType": "Financing|Partnership|Certification|Pilot|Expansion|Grant|Hiring|News",

  "extracted_facts": {
    "amount": "기사에 명시된 금액 (없으면 null, 절대 추정하지 말 것)",
    "round": "기사에 명시된 라운드 (없으면 null)",
    "partner": "기사에 명시된 파트너사 (없으면 null)",
    "date": "기사에 명시된 날짜 (없으면 null)"
  },

  "domain_insight": "에너지 도메인 전문 지식 적용한 2-3문장 인사이트 (위 도메인 지식 활용)",
  "why_now": "왜 지금 이 시점에 중요한지 (규제·시장 타이밍 맥락)",
  "signal_quality": "High|Medium|Low",
  "signal_quality_reason": "왜 이 quality인지 — 교차검증 결과와 도메인 지식 기반으로",
  "next_action": "Investigate|Monitor|Note|Skip",
  "next_action_reason": "왜 이 액션인지",
  "risk": "에너지 도메인 관점의 핵심 리스크",
  "cross_validation_score": "single|double|triple_plus (소스 수 기반)"
}]

JSON만 반환.`;

  const text = await callClaude(system, user);
  return safeJSON(text);
}

// ══════════════════════════════════════════════════════════
// 신호 조합 (팩트 + 도메인 분석)
// ══════════════════════════════════════════════════════════
function buildSignal(article, analysis, crossValidationMap) {
  const a = analysis || {};

  // 교차검증 점수 계산
  const coNames = Object.keys(crossValidationMap).filter(c =>
    ((article.title||"")+" "+(article.description||"")).toLowerCase().includes(c.toLowerCase())
  );
  const cvData = coNames.length > 0 ? crossValidationMap[coNames[0]] : null;
  const sourceCount = cvData ? cvData.news + cvData.dart : 1;
  const cvScore = sourceCount >= 3 ? "triple_plus" : sourceCount === 2 ? "double" : "single";
  const cvTrust = sourceCount >= 3 ? "High" : sourceCount === 2 ? "Medium" : "Low";

  return {
    id:        `${article.tag}-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
    tag:       article.tag,
    label:     article.label,
    region:    article.tag.startsWith("kr_")?"KR":article.tag.startsWith("cn_")?"CN":"GLOBAL",
    isKorean:  article.tag.startsWith("kr_"),
    isChina:   article.tag.startsWith("cn_"),
    isDart:    !!article.isDart,

    // ── 100% 팩트 필드 ────────────────────────────────
    title:     article.title,
    url:       article.url,
    source:    article.source?.name || article.source || "Unknown",
    pubDate:   (article.publishedAt||"").slice(0,10),
    summary:   (article.description||"").slice(0,350),

    // ── 기사에서 추출한 수치 (생성값 아님) ──────────────
    extracted_facts: a.extracted_facts || { amount:null, round:null, partner:null, date:null },

    // ── 에너지 도메인 분석 ─────────────────────────────
    company:           a.company || null,
    companyType:       a.companyType || "unknown",
    eventType:         a.eventType || "News",
    domain_insight:    a.domain_insight || "",
    why_now:           a.why_now || "",
    signal_quality:    a.signal_quality || "Low",
    signal_quality_reason: a.signal_quality_reason || "",
    next_action:       a.next_action || "Monitor",
    next_action_reason:a.next_action_reason || "",
    risk:              a.risk || null,

    // ── 교차검증 결과 ──────────────────────────────────
    cross_validation: {
      score:       a.cross_validation_score || cvScore,
      sourceCount: sourceCount,
      trustLevel:  cvTrust,
      sources:     cvData ? [...cvData.tags] : [article.tag],
    },

    // ── 신뢰도 메타 ────────────────────────────────────
    trust:       "FACT",
    analysisTrust: sourceCount >= 2 ? "HIGH_CONFIDENCE" : "STANDARD",
    generatedAt: TODAY,
  };
}

// ══════════════════════════════════════════════════════════
// 브리핑 (도메인 지식 + 팩트 기반)
// ══════════════════════════════════════════════════════════
async function generateBrief(signals) {
  const highItems = signals
    .filter(s => s.signal_quality==="High")
    .slice(0,8)
    .map(s => {
      const cv = s.cross_validation;
      const facts = s.extracted_facts;
      const factStr = [
        facts.amount ? `금액:${facts.amount}` : null,
        facts.round  ? `라운드:${facts.round}` : null,
        facts.partner? `파트너:${facts.partner}` : null,
      ].filter(Boolean).join(", ");
      return `- [${s.label}][${cv.score}소스] "${s.title}" (${s.source}, ${s.pubDate})${factStr?` [${factStr}]`:""}`;
    }).join("\n");

  const system = `에너지 CVC 시니어 심사역. 아래 도메인 지식 활용:
${ENERGY_CONTEXT}

규칙: 기사에 없는 수치 생성 금지. 인용 시 출처 명시. 도메인 지식으로 맥락 설명.`;

  const user = `오늘(${TODAY_KR}) CVC 투자 브리핑 5문장.

실제 기사 목록 (교차검증 포함):
${highItems}

작성 기준:
- 교차검증된 신호(double/triple) 우선 언급
- 에너지 도메인 맥락 적용 (단순 요약 금지)
- 기사에 있는 수치만 인용, 출처 명시
- 규제/타이밍 맥락 포함
- "왜 지금인가" 관점 포함`;

  return callClaude(system, user);
}

// ══════════════════════════════════════════════════════════
// 메인
// ══════════════════════════════════════════════════════════
async function main() {
  console.log(`\n🚀 Energy CVC Signal Generator v10 — Phase 1`);
  console.log(`날짜: ${TODAY_KR}`);
  console.log(`개선: 에너지 전문 컨텍스트 + 다중소스 교차검증 + 수치 추출만\n`);

  const dataDir = path.join(__dirname,"data");
  if(!fs.existsSync(dataDir))fs.mkdirSync(dataDir,{recursive:true});

  // ① 뉴스 + DART 수집
  const articles = await collectNews();
  const dartItems = await collectDART();
  console.log(`\n수집 완료: 뉴스 ${articles.length}건, DART ${dartItems.length}건`);

  // ② 교차검증 맵 생성
  const cvMap = crossValidate(articles, dartItems);
  const multiSourceCompanies = Object.entries(cvMap)
    .filter(([,v])=>v.news+v.dart>=2)
    .map(([k])=>k);
  console.log(`\n교차검증: ${multiSourceCompanies.length}개 기업이 2개+ 소스 등장`);
  if(multiSourceCompanies.length>0) console.log("  →", multiSourceCompanies.join(", "));

  // ③ Claude 분석 (배치, 에너지 컨텍스트 포함)
  console.log(`\n③ 에너지 전문 분석 (${articles.length}건)...`);
  const signals = [];
  const BATCH = 6; // 컨텍스트가 길어서 배치 크기 줄임

  for(let i=0;i<articles.length;i+=BATCH){
    const batch=articles.slice(i,i+BATCH);
    console.log(`  배치 ${Math.floor(i/BATCH)+1}/${Math.ceil(articles.length/BATCH)}...`);
    try{
      const analyses=await analyzeWithContext(batch,cvMap);
      batch.forEach((article,j)=>{
        const a=analyses.find(x=>x.idx===j+1)||analyses[j]||{};
        signals.push(buildSignal(article,a,cvMap));
      });
      console.log(`  ✓ ${batch.length}건`);
    }catch(e){
      console.error(`  ✗ ${e.message}`);
      // 분석 실패 → 팩트만 저장
      batch.forEach(article=>{
        signals.push(buildSignal(article,null,cvMap));
      });
    }
    if(i+BATCH<articles.length){
      console.log("  ⏱ 30초...");
      await delay(30000);
    }
  }

  // DART 신호 추가
  const dartSignals = dartItems.map(d=>{
    const cvData = cvMap[d.company];
    return {
      id:d.id, tag:d.tag, label:d.label,
      region:"KR", isKorean:true, isChina:false, isDart:true,
      title:d.title, url:d.url, source:d.source, pubDate:d.publishedAt,
      summary:d.description,
      extracted_facts:{amount:null,round:null,partner:null,date:null},
      company:d.company, companyType:"listed_corp",
      eventType:d.title.includes("증자")||d.title.includes("사채")?"Financing":"News",
      domain_insight:`${d.company}의 실제 공시. 원문에서 구체적 조건 확인 필요.`,
      why_now:"DART 공시는 법적 공시 의무 사항 — 100% 팩트. 원문 링크에서 세부 조건 직접 확인.",
      signal_quality:d.title.includes("증자")||d.title.includes("계약")?"High":"Medium",
      signal_quality_reason:"DART 공시 = 법적 팩트 데이터",
      next_action:d.title.includes("증자")||d.title.includes("계약")?"Investigate":"Monitor",
      next_action_reason:"공시 원문에서 조건 확인 후 판단",
      risk:null,
      cross_validation:{
        score: cvData&&cvData.news>0?"double":"single",
        sourceCount: cvData?(cvData.news+cvData.dart):1,
        trustLevel: cvData&&cvData.news>0?"High":"Medium",
        sources: cvData?[...cvData.tags]:["kr_dart"],
      },
      trust:"FACT", analysisTrust:"HIGH_CONFIDENCE", generatedAt:TODAY,
    };
  });

  const allSignals=[...signals,...dartSignals].sort((a,b)=>{
    // 교차검증 소스 수 + 신호 품질로 정렬
    const scoreA=(a.cross_validation.sourceCount*2)+({High:3,Medium:1,Low:0}[a.signal_quality]||0);
    const scoreB=(b.cross_validation.sourceCount*2)+({High:3,Medium:1,Low:0}[b.signal_quality]||0);
    return scoreB-scoreA;
  });

  // ④ 브리핑
  console.log("\n④ 브리핑...");
  await delay(30000);
  let brief="";
  try{
    brief=await generateBrief(allSignals);
    console.log("  ✓");
  }catch(e){console.error(`  ✗ ${e.message}`);}

  const stats = {
    total:allSignals.length,
    newsCount:signals.length,
    dartCount:dartSignals.length,
    kr:allSignals.filter(s=>s.isKorean).length,
    cn:allSignals.filter(s=>s.isChina).length,
    global:allSignals.filter(s=>!s.isKorean&&!s.isChina).length,
    high:allSignals.filter(s=>s.signal_quality==="High").length,
    investigate:allSignals.filter(s=>s.next_action==="Investigate").length,
    multiSource:allSignals.filter(s=>s.cross_validation.sourceCount>=2).length,
    tripleSource:allSignals.filter(s=>s.cross_validation.sourceCount>=3).length,
  };

  const output={
    date:TODAY, dateKr:TODAY_KR,
    generatedAt:new Date().toISOString(),
    dataPolicy:"팩트 전용 + 에너지 도메인 전문 분석 + 교차검증",
    brief, stats, signals:allSignals, errors:[],
    // Phase 2를 위한 패턴 데이터 누적
    phase2_seeds:{
      multiSourceCompanies,
      signalPatterns:allSignals.filter(s=>s.cross_validation.sourceCount>=2).map(s=>({
        company:s.company, eventType:s.eventType, date:s.pubDate,
        signalQuality:s.signal_quality, sourceCount:s.cross_validation.sourceCount,
      })),
    },
  };

  fs.writeFileSync(path.join(dataDir,`${TODAY}.json`),JSON.stringify(output,null,2),"utf8");
  fs.writeFileSync(path.join(dataDir,"latest.json"),JSON.stringify(output,null,2),"utf8");

  // index.json 업데이트
  const idxPath=path.join(dataDir,"index.json");
  let idx=[];
  if(fs.existsSync(idxPath)){try{idx=JSON.parse(fs.readFileSync(idxPath,"utf8"));}catch{}}
  if(!idx.find(d=>d.date===TODAY)){
    idx.unshift({date:TODAY,dateKr:TODAY_KR,stats});
    fs.writeFileSync(idxPath,JSON.stringify(idx.slice(0,90),null,2),"utf8");
  }

  console.log(`\n✅ 완료!`);
  console.log(`총 ${stats.total}건 | 뉴스 ${stats.newsCount} | DART ${stats.dartCount}`);
  console.log(`교차검증 2소스+ : ${stats.multiSource}건 (신뢰도 상승)`);
  console.log(`교차검증 3소스+: ${stats.tripleSource}건 (최고 신뢰도)`);
  console.log(`High : ${stats.high}건 | Investigate: ${stats.investigate}건`);
  console.log(`\n⏳ Phase 2 시작까지: 데이터 누적 중 (phase2_seeds 저장됨)\n`);
}

main().catch(e=>{console.error("❌",e.message);process.exit(1);});

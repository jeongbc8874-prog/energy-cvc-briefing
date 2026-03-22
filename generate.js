/**
 * Energy CVC Daily Briefing Generator
 * 매일 새벽 7시 자동 실행 → Claude API로 브리핑 생성 → index.html 업데이트
 *
 * 사용법: node generate.js
 * 환경변수: ANTHROPIC_API_KEY (GitHub Secrets에 저장)
 */

const https = require('https');
const fs = require('fs');

const API_KEY = process.env.ANTHROPIC_API_KEY;
if (!API_KEY) { console.error('❌ ANTHROPIC_API_KEY 환경변수가 없습니다.'); process.exit(1); }

// ─── 날짜 ───────────────────────────────────────────
function korDate() {
  return new Date().toLocaleDateString('ko-KR', {
    year:'numeric', month:'long', day:'numeric', weekday:'long',
    timeZone:'Asia/Seoul'
  });
}
function isoDate() {
  return new Date().toLocaleDateString('ko-KR', {
    year:'numeric', month:'2-digit', day:'2-digit',
    timeZone:'Asia/Seoul'
  }).replace(/\. /g,'-').replace('.','');
}
function timeStr() {
  return new Date().toLocaleTimeString('ko-KR', {
    hour:'2-digit', minute:'2-digit', timeZone:'Asia/Seoul'
  });
}

// ─── Claude API 호출 ────────────────────────────────
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 1500,
      system,
      messages: [{ role:'user', content: user }]
    });

    const options = {
      hostname: 'api.anthropic.com',
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Length': Buffer.byteLength(body)
      }
    };

    const req = https.request(options, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) { reject(new Error(parsed.error.message)); return; }
          resolve(parsed.content?.[0]?.text || '');
        } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ─── 프롬프트 ────────────────────────────────────────
const SYSTEM = `당신은 에너지 분야 CVC 심사역을 위한 AI 딜소싱 에이전트입니다.
오늘(${korDate()}) 기준으로 에너지 투자 시장을 분석합니다.
반드시 순수 JSON만 반환하세요. 마크다운, 코드블록, 설명 없이 JSON만.`;

const PROMPTS = {
  deals: `오늘의 추천 딜 4건을 JSON 배열로 반환하세요.
형식: [{"name":"기업명","score":"9.2","scoreClass":"s-high","colorClass":"","tags":[{"t":"섹터","c":"dt-sector"},{"t":"Series B · $55M","c":"dt-stage"},{"t":"미국","c":"dt-country"}],"desc":"한두줄 설명","signal":"▲ 투자 시그널"}]
scoreClass: s-high(8이상), s-mid(6~8). colorClass: ""(초록),"blue","amber","purple" 중 하나.
에너지 섹터(ESS,수소,태양광,에너지AI,SMR,CCUS) 다양하게 구성하세요.`,

  global: `오늘의 글로벌 에너지 투자 뉴스 5건을 JSON 배열로 반환하세요.
형식: [{"tag":"글로벌","tagC":"nt-g","time":"2시간 전","title":"뉴스 제목","body":"CVC 심사역 관점 시사점 포함 2~3줄"}]
tagC 옵션: nt-g(글로벌초록), nt-b(파랑), nt-o(주황), nt-r(빨강), nt-p(보라)
tag 내용: 글로벌/정책/기술/M&A/시장 중 하나`,

  domestic: `오늘의 국내 에너지 스타트업 펀딩 소식 4건을 JSON 배열로 반환하세요.
형식: [{"amount":"150억","co":"기업명","detail":"Series B · 섹터","desc":"투자 배경과 CVC 시사점 1~2줄"}]
에너지 섹터 기업만, 실제 있을 법한 국내 기업으로 구성하세요.`,

  sector: `에너지 섹터별 이번달 투자 트렌드를 JSON 배열로 반환하세요.
형식: [{"name":"ESS / 배터리","pct":"84","color":"var(--g)","note":"한줄 트렌드 설명"}]
6개 섹터: ESS/배터리(var(--g)), 그린수소(var(--b)), 태양광(var(--o)), 에너지AI(#a78bfa), SMR/원자력(#f472b6), CCUS(#34d399)
pct는 투자 활성도 퍼센트(숫자만).`,

  editorial: `오늘의 에너지 CVC 심사역 관점 에디토리얼을 JSON으로 반환하세요.
형식: {"quote":"핵심 통찰 한 문장 (인용구 스타일)","body":"심층 분석 본문 (400~500자, 문단 나눔. 오늘 심사역이 취해야 할 액션 3가지 포함)"}
오늘 날짜(${korDate()})의 실제 에너지 시장 맥락을 반영하세요.`
};

// ─── HTML 생성 ────────────────────────────────────────
function buildHTML(data) {
  const { deals, global: globalNews, domestic, sector, editorial } = data;

  const dealsHTML = deals.map(d => `
    <div class="deal-row ${d.colorClass||''}">
      <div class="deal-top">
        <div class="deal-name">${d.name}</div>
        <div class="deal-score-wrap">
          <div class="deal-score ${d.scoreClass}">${d.score}</div>
          <div class="deal-score-label">/ 10</div>
        </div>
      </div>
      <div class="deal-tags">${d.tags.map(t=>`<span class="dtag ${t.c}">${t.t}</span>`).join('')}</div>
      <div class="deal-desc">${d.desc}</div>
      <div class="deal-signal">${d.signal}</div>
    </div>`).join('');

  const globalHTML = globalNews.map(n => `
    <div class="news-item">
      <div class="news-meta">
        <span class="ntag ${n.tagC}">${n.tag}</span>
        <span class="ntime">${n.time}</span>
      </div>
      <div class="news-title">${n.title}</div>
      <div class="news-body">${n.body}</div>
    </div>`).join('');

  const domesticHTML = domestic.map(f => `
    <div class="fund-row">
      <div class="fund-amount">${f.amount}</div>
      <div class="fund-info">
        <div class="fund-co">${f.co}</div>
        <div class="fund-detail">${f.detail}</div>
        <div class="fund-desc">${f.desc}</div>
      </div>
    </div>`).join('');

  const sectorHTML = sector.map(s => `
    <div class="s-row">
      <div class="s-top">
        <div class="s-name">${s.name}</div>
        <div class="s-pct">${s.pct}%</div>
      </div>
      <div class="s-bar-bg">
        <div class="s-bar-fill" style="width:${s.pct}%;background:${s.color}"></div>
      </div>
      <div class="s-note">${s.note}</div>
    </div>`).join('');

  const today = korDate();
  const now = timeStr();

  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Energy CVC Daily Briefing — ${isoDate()}</title>
<meta name="description" content="에너지 CVC 심사역을 위한 AI 딜소싱 일간 브리핑">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@300;400;500&family=Playfair+Display:ital,wght@0,700;1,400&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0d11;--surface:#13161e;--surface2:#1a1e29;--border:#222736;--border2:#2a3045;--g:#00d97e;--b:#3b82f6;--o:#f59e0b;--r:#ef4444;--p:#a78bfa;--text:#e8edf5;--text2:#7c8db5;--text3:#404860;}
*{margin:0;padding:0;box-sizing:border-box;}html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--text);font-family:'Noto Sans KR',sans-serif;min-height:100vh;overflow-x:hidden;}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;background-image:linear-gradient(rgba(0,217,126,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,217,126,.025) 1px,transparent 1px);background-size:48px 48px;}
.topbar{position:sticky;top:0;z-index:200;background:rgba(11,13,17,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 28px;height:56px;}
.topbar-logo{font-family:'Bebas Neue',sans-serif;font-size:20px;letter-spacing:.08em;color:var(--g);display:flex;align-items:center;gap:10px;}
.topbar-logo span{color:var(--text2);font-size:14px;letter-spacing:.04em;font-family:'JetBrains Mono',monospace;}
.topbar-right{display:flex;align-items:center;gap:14px;}
.pulse-badge{display:flex;align-items:center;gap:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--g);letter-spacing:.08em;background:rgba(0,217,126,.08);border:1px solid rgba(0,217,126,.18);padding:4px 10px;border-radius:20px;}
.pulse-dot{width:6px;height:6px;border-radius:50%;background:var(--g);animation:blink 2s infinite;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.3;}}
.topbar-date{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);}
.hero{position:relative;z-index:1;background:linear-gradient(135deg,rgba(0,217,126,.06),rgba(59,130,246,.04));border-bottom:1px solid var(--border);padding:36px 28px 28px;overflow:hidden;}
.hero-kicker{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--g);margin-bottom:10px;display:flex;align-items:center;gap:8px;}
.hero-kicker::before{content:'';width:20px;height:1px;background:var(--g);}
.hero-title{font-family:'Playfair Display',serif;font-size:clamp(22px,4vw,38px);line-height:1.2;color:var(--text);margin-bottom:10px;}
.hero-desc{font-size:13px;color:var(--text2);line-height:1.8;max-width:600px;font-weight:300;}
.hero-meta{margin-top:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.hero-chip{font-family:'JetBrains Mono',monospace;font-size:10px;padding:4px 10px;border-radius:4px;letter-spacing:.06em;}
.hc-g{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.2);}
.hc-b{background:rgba(59,130,246,.1);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.hc-o{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
.main{position:relative;z-index:1;max-width:1280px;margin:0 auto;padding:28px;display:grid;grid-template-columns:1fr 340px;gap:20px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;animation:fadeUp .5s ease both;}
@keyframes fadeUp{from{opacity:0;transform:translateY(14px);}to{opacity:1;transform:translateY(0);}}
.card:nth-child(1){animation-delay:.05s;}.card:nth-child(2){animation-delay:.1s;}.card:nth-child(3){animation-delay:.15s;}.card:nth-child(4){animation-delay:.2s;}
.card-head{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.card-title{display:flex;align-items:center;gap:8px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--text2);}
.card-icon{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;}
.ci-g{background:rgba(0,217,126,.15);}.ci-b{background:rgba(59,130,246,.15);}.ci-o{background:rgba(245,158,11,.15);}.ci-p{background:rgba(167,139,250,.15);}
.card-badge{font-family:'JetBrains Mono',monospace;font-size:9px;padding:3px 8px;border-radius:20px;letter-spacing:.06em;}
.cb-g{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.18);}
.cb-b{background:rgba(59,130,246,.1);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.cb-o{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
.cb-p{background:rgba(167,139,250,.1);color:#c4b5fd;border:1px solid rgba(167,139,250,.2);}
.card-body{padding:20px;}
.span-col{grid-column:1 / -1;}.col-left{grid-column:1;}.col-right{grid-column:2;}
.deal-list{display:flex;flex-direction:column;gap:12px;}
.deal-row{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;border-left:3px solid var(--g);transition:transform .2s;}
.deal-row:hover{transform:translateX(3px);}
.deal-row.blue{border-left-color:var(--b);}.deal-row.amber{border-left-color:var(--o);}.deal-row.purple{border-left-color:var(--p);}
.deal-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;}
.deal-name{font-family:'Playfair Display',serif;font-size:17px;line-height:1.2;}
.deal-score-wrap{text-align:right;}
.deal-score{font-family:'Bebas Neue',sans-serif;font-size:26px;line-height:1;}
.deal-score.s-high{color:var(--g);}.deal-score.s-mid{color:var(--o);}
.deal-score-label{font-family:'JetBrains Mono',monospace;font-size:8px;color:var(--text3);}
.deal-tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px;}
.dtag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 7px;border-radius:3px;letter-spacing:.05em;}
.dt-sector{background:rgba(59,130,246,.12);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.dt-stage{background:rgba(255,255,255,.05);color:var(--text2);border:1px solid var(--border2);}
.dt-country{background:rgba(0,217,126,.08);color:var(--g);border:1px solid rgba(0,217,126,.15);}
.deal-desc{font-size:12px;color:var(--text2);line-height:1.65;font-weight:300;}
.deal-signal{margin-top:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--g);letter-spacing:.04em;}
.news-list{display:flex;flex-direction:column;}
.news-item{padding:14px 0;border-bottom:1px solid var(--border);}
.news-item:last-child{border-bottom:none;padding-bottom:0;}
.news-meta{display:flex;align-items:center;gap:6px;margin-bottom:5px;}
.ntag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;letter-spacing:.05em;}
.nt-g{background:rgba(0,217,126,.12);color:var(--g);}.nt-b{background:rgba(59,130,246,.12);color:#7ab3ff;}
.nt-o{background:rgba(245,158,11,.12);color:#fbbf24;}.nt-r{background:rgba(239,68,68,.1);color:#fca5a5;}.nt-p{background:rgba(167,139,250,.12);color:#c4b5fd;}
.ntime{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text3);}
.news-title{font-size:13px;font-weight:500;line-height:1.55;color:var(--text);margin-bottom:3px;}
.news-body{font-size:12px;color:var(--text2);line-height:1.65;font-weight:300;}
.fund-list{display:flex;flex-direction:column;gap:10px;}
.fund-row{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start;}
.fund-amount{font-family:'Bebas Neue',sans-serif;font-size:20px;color:var(--g);line-height:1;white-space:nowrap;min-width:50px;text-align:right;}
.fund-co{font-size:13px;font-weight:500;margin-bottom:2px;}
.fund-detail{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);letter-spacing:.04em;}
.fund-desc{font-size:11.5px;color:var(--text2);margin-top:3px;font-weight:300;line-height:1.5;}
.sector-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;}
.s-row{display:flex;flex-direction:column;gap:5px;}
.s-top{display:flex;justify-content:space-between;align-items:center;}
.s-name{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);}
.s-pct{font-family:'Bebas Neue',sans-serif;font-size:16px;color:var(--text);}
.s-bar-bg{height:4px;background:var(--border2);border-radius:2px;overflow:hidden;}
.s-bar-fill{height:100%;border-radius:2px;transition:width 1.2s cubic-bezier(.4,0,.2,1);}
.s-note{font-size:11px;color:var(--text3);font-weight:300;}
.editorial-wrap{position:relative;background:linear-gradient(135deg,rgba(0,217,126,.04),rgba(59,130,246,.03));border-radius:10px;padding:24px;border:1px solid rgba(0,217,126,.1);}
.editorial-quote{font-family:'Playfair Display',serif;font-style:italic;font-size:clamp(15px,2vw,18px);line-height:1.6;color:var(--text);margin-bottom:18px;padding-bottom:18px;border-bottom:1px solid var(--border);}
.editorial-body{font-size:13.5px;line-height:1.95;color:var(--text2);font-weight:300;white-space:pre-wrap;}
.editorial-byline{margin-top:18px;display:flex;align-items:center;gap:10px;}
.byline-avatar{width:30px;height:30px;border-radius:50%;background:var(--g);display:flex;align-items:center;justify-content:center;font-family:'Bebas Neue',sans-serif;font-size:13px;color:#000;flex-shrink:0;}
.byline-text{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);line-height:1.5;}
.footer{position:relative;z-index:1;border-top:1px solid var(--border);padding:20px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;}
.footer-l{font-family:'Bebas Neue',sans-serif;font-size:16px;letter-spacing:.08em;color:var(--text3);}
.footer-r{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);text-align:right;}
@media(max-width:960px){.main{grid-template-columns:1fr;padding:16px;gap:16px;}.col-left,.col-right,.span-col{grid-column:1;}}
@media(max-width:480px){.topbar{padding:0 16px;}.topbar-date{display:none;}.hero{padding:24px 16px 20px;}}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px;}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-logo">ENERGY CVC <span>/ DAILY BRIEFING</span></div>
  <div class="topbar-right">
    <div class="topbar-date">${today}</div>
    <div class="pulse-badge"><div class="pulse-dot"></div>AI GENERATED</div>
  </div>
</div>
<div class="hero">
  <div class="hero-kicker">TODAY'S INTELLIGENCE · ${today}</div>
  <h1 class="hero-title">${editorial.quote.substring(0,40)}...</h1>
  <p class="hero-desc">Claude AI Agent가 오늘의 글로벌·국내 에너지 투자 동향을 분석했습니다. 딜소싱·뉴스·트렌드 전체를 아래에서 확인하세요.</p>
  <div class="hero-meta">
    <span class="hero-chip hc-g">⚡ 추천 딜 ${deals.length}건</span>
    <span class="hero-chip hc-b">🌐 글로벌 뉴스 ${globalNews.length}건</span>
    <span class="hero-chip hc-o">🇰🇷 국내 펀딩 ${domestic.length}건</span>
  </div>
</div>
<div class="main">
  <div class="card span-col">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-g">🎯</div>오늘의 추천 딜</div>
      <div class="card-badge cb-g">AI SCORED</div>
    </div>
    <div class="card-body"><div class="deal-list">${dealsHTML}</div></div>
  </div>
  <div class="card col-left">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-b">🌐</div>글로벌 에너지 투자 뉴스</div>
      <div class="card-badge cb-b">GLOBAL</div>
    </div>
    <div class="card-body"><div class="news-list">${globalHTML}</div></div>
  </div>
  <div class="card col-right">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-o">🇰🇷</div>국내 펀딩 소식</div>
      <div class="card-badge cb-o">DOMESTIC</div>
    </div>
    <div class="card-body"><div class="fund-list">${domesticHTML}</div></div>
  </div>
  <div class="card span-col">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-p">📊</div>섹터별 투자 트렌드</div>
      <div class="card-badge cb-p">THIS MONTH</div>
    </div>
    <div class="card-body"><div class="sector-grid">${sectorHTML}</div></div>
  </div>
  <div class="card span-col">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-g">✍️</div>심사역 AI 에디토리얼</div>
      <div class="card-badge cb-g">CLAUDE ANALYSIS</div>
    </div>
    <div class="card-body">
      <div class="editorial-wrap">
        <div class="editorial-quote">${editorial.quote}</div>
        <div class="editorial-body">${editorial.body}</div>
        <div class="editorial-byline">
          <div class="byline-avatar">AI</div>
          <div class="byline-text">CLAUDE AI · ENERGY CVC INTELLIGENCE AGENT<br>${today} ${now} 자동 생성</div>
        </div>
      </div>
    </div>
  </div>
</div>
<div class="footer">
  <div class="footer-l">ENERGY · CVC INTELLIGENCE</div>
  <div class="footer-r">Claude AI 분석 엔진<br>${today} ${now} 생성</div>
</div>
</body>
</html>`;
}

// ─── 메인 실행 ────────────────────────────────────────
async function main() {
  console.log(`\n🚀 Energy CVC Briefing 생성 시작 — ${korDate()}\n`);

  try {
    console.log('① 추천 딜 스코어링 중...');
    const dealsRaw = await callClaude(SYSTEM, PROMPTS.deals);
    const deals = JSON.parse(dealsRaw.replace(/```json|```/g,'').trim());

    console.log('② 글로벌 뉴스 수집·분석 중...');
    const globalRaw = await callClaude(SYSTEM, PROMPTS.global);
    const global = JSON.parse(globalRaw.replace(/```json|```/g,'').trim());

    console.log('③ 국내 펀딩 소식 확인 중...');
    const domesticRaw = await callClaude(SYSTEM, PROMPTS.domestic);
    const domestic = JSON.parse(domesticRaw.replace(/```json|```/g,'').trim());

    console.log('④ 섹터 트렌드 분석 중...');
    const sectorRaw = await callClaude(SYSTEM, PROMPTS.sector);
    const sector = JSON.parse(sectorRaw.replace(/```json|```/g,'').trim());

    console.log('⑤ AI 에디토리얼 작성 중...');
    const editorialRaw = await callClaude(SYSTEM, PROMPTS.editorial);
    const editorial = JSON.parse(editorialRaw.replace(/```json|```/g,'').trim());

    console.log('⑥ HTML 생성 중...');
    const html = buildHTML({ deals, global, domestic, sector, editorial });
    fs.writeFileSync('index.html', html, 'utf8');

    console.log('\n✅ 완료! index.html 생성 성공\n');
  } catch(err) {
    console.error('\n❌ 오류 발생:', err.message);
    process.exit(1);
  }
}

main();

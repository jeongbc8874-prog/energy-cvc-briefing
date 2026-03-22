/**
 * Energy CVC Daily Briefing Generator v2
 * 클릭 기능 추가: 딜 상세팝업, AI 심층분석, 뉴스 원문링크, 섹터 리포트
 */

const https = require('https');
const fs = require('fs');

const API_KEY = process.env.ANTHROPIC_API_KEY;
if (!API_KEY) { console.error('❌ ANTHROPIC_API_KEY 없음'); process.exit(1); }

function korDate() {
  return new Date().toLocaleDateString('ko-KR', {
    year:'numeric', month:'long', day:'numeric', weekday:'long', timeZone:'Asia/Seoul'
  });
}
function isoDate() {
  return new Date().toLocaleDateString('ko-KR', {
    year:'numeric', month:'2-digit', day:'2-digit', timeZone:'Asia/Seoul'
  }).replace(/\. /g,'-').replace('.','');
}
function timeStr() {
  return new Date().toLocaleTimeString('ko-KR', {
    hour:'2-digit', minute:'2-digit', timeZone:'Asia/Seoul'
  });
}

function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2000,
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

const SYSTEM = `당신은 에너지 분야 CVC 심사역을 위한 AI 딜소싱 에이전트입니다.
오늘(${korDate()}) 기준으로 에너지 투자 시장을 분석합니다.
반드시 순수 JSON만 반환하세요. 마크다운, 코드블록, 설명 없이 JSON만.`;

const PROMPTS = {
  deals: `오늘의 추천 딜 4건을 JSON 배열로 반환하세요.
형식: [{"name":"기업명","score":"9.2","scoreClass":"s-high","colorClass":"","tags":[{"t":"섹터","c":"dt-sector"},{"t":"Series B · $55M","c":"dt-stage"},{"t":"미국","c":"dt-country"}],"desc":"한두줄 설명","signal":"▲ 투자 시그널","detail":{"tech":"기술 검증 내용 2~3줄","valuation":"밸류에이션 분석 2~3줄 (최근 라운드, 멀티플, 적정성)","risks":["리스크1","리스크2","리스크3"],"action":"심사역 즉시 액션 아이템 1~2줄","newsUrl":"관련 최신 뉴스 검색용 키워드 (영문)"}}]
scoreClass: s-high(8이상), s-mid(6~8). colorClass: ""(초록),"blue","amber","purple".
에너지 섹터(ESS,수소,태양광,에너지AI,SMR,CCUS) 다양하게.`,

  global: `오늘의 글로벌 에너지 투자 뉴스 5건을 JSON 배열로 반환하세요.
형식: [{"tag":"글로벌","tagC":"nt-g","time":"2시간 전","title":"뉴스 제목","body":"CVC 심사역 관점 시사점 2~3줄","url":"https://google.com/search?q=관련+영문+검색어"}]
tagC: nt-g(초록), nt-b(파랑), nt-o(주황), nt-r(빨강), nt-p(보라)
url은 실제 검색 가능한 Google 검색 URL로`,

  domestic: `오늘의 국내 에너지 스타트업 펀딩 소식 4건을 JSON 배열로 반환하세요.
형식: [{"amount":"150억","co":"기업명","detail":"Series B · 섹터","desc":"투자 배경과 CVC 시사점 1~2줄","url":"https://google.com/search?q=기업명+투자+펀딩"}]`,

  sector: `에너지 섹터별 이번달 투자 트렌드를 JSON 배열로 반환하세요.
형식: [{"name":"ESS / 배터리","pct":"84","color":"var(--g)","note":"한줄 트렌드","report":{"summary":"섹터 현황 요약 2~3줄","topDeals":"주목할 딜 2~3개 언급","outlook":"6개월 전망 2줄","risk":"주요 리스크 1~2줄"}}]
6개 섹터: ESS/배터리(var(--g)), 그린수소(var(--b)), 태양광(var(--o)), 에너지AI(#a78bfa), SMR/원자력(#f472b6), CCUS(#34d399)`,

  editorial: `오늘의 에너지 CVC 심사역 관점 에디토리얼을 JSON으로 반환하세요.
형식: {"quote":"핵심 통찰 한 문장","body":"심층 분석 본문 (400~500자, 문단 나눔, 오늘 취해야 할 액션 3가지 포함)"}
오늘 날짜(${korDate()})의 실제 에너지 시장 맥락 반영.`
};

function buildHTML(data) {
  const { deals, global: globalNews, domestic, sector, editorial } = data;
  const today = korDate();
  const now = timeStr();

  const dealsJSON = JSON.stringify(deals).replace(/`/g,'\\`').replace(/\$/g,'\\$');
  const sectorJSON = JSON.stringify(sector).replace(/`/g,'\\`').replace(/\$/g,'\\$');

  const dealsHTML = deals.map((d,i) => `
    <div class="deal-row ${d.colorClass||''}" onclick="openDeal(${i})" style="cursor:pointer">
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
      <div class="deal-click-hint">🔍 클릭하여 상세 분석 보기</div>
    </div>`).join('');

  const globalHTML = globalNews.map(n => `
    <div class="news-item" onclick="window.open('${n.url}','_blank')" style="cursor:pointer">
      <div class="news-meta">
        <span class="ntag ${n.tagC}">${n.tag}</span>
        <span class="ntime">${n.time}</span>
        <span class="news-link-hint">↗ 원문</span>
      </div>
      <div class="news-title">${n.title}</div>
      <div class="news-body">${n.body}</div>
    </div>`).join('');

  const domesticHTML = domestic.map(f => `
    <div class="fund-row" onclick="window.open('${f.url}','_blank')" style="cursor:pointer">
      <div class="fund-amount">${f.amount}</div>
      <div class="fund-info">
        <div class="fund-co">${f.co} <span class="news-link-hint">↗</span></div>
        <div class="fund-detail">${f.detail}</div>
        <div class="fund-desc">${f.desc}</div>
      </div>
    </div>`).join('');

  const sectorHTML = sector.map((s,i) => `
    <div class="s-row" onclick="openSector(${i})" style="cursor:pointer">
      <div class="s-top">
        <div class="s-name">${s.name}</div>
        <div class="s-pct">${s.pct}%</div>
      </div>
      <div class="s-bar-bg">
        <div class="s-bar-fill" style="width:${s.pct}%;background:${s.color}"></div>
      </div>
      <div class="s-note">${s.note} <span class="news-link-hint">📊 리포트</span></div>
    </div>`).join('');

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
.deal-row{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;border-left:3px solid var(--g);transition:all .2s;}
.deal-row:hover{border-color:rgba(0,217,126,.4);transform:translateX(3px);background:#1e2535;}
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
.deal-click-hint{margin-top:8px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);letter-spacing:.04em;opacity:.6;}
.deal-row:hover .deal-click-hint{opacity:1;color:var(--g);}
.news-list{display:flex;flex-direction:column;}
.news-item{padding:14px 0;border-bottom:1px solid var(--border);transition:background .15s;border-radius:6px;padding:12px 8px;}
.news-item:hover{background:var(--surface2);}
.news-item:last-child{border-bottom:none;}
.news-meta{display:flex;align-items:center;gap:6px;margin-bottom:5px;}
.ntag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;letter-spacing:.05em;}
.nt-g{background:rgba(0,217,126,.12);color:var(--g);}.nt-b{background:rgba(59,130,246,.12);color:#7ab3ff;}
.nt-o{background:rgba(245,158,11,.12);color:#fbbf24;}.nt-r{background:rgba(239,68,68,.1);color:#fca5a5;}.nt-p{background:rgba(167,139,250,.12);color:#c4b5fd;}
.ntime{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text3);}
.news-link-hint{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--b);margin-left:auto;}
.news-title{font-size:13px;font-weight:500;line-height:1.55;color:var(--text);margin-bottom:3px;}
.news-body{font-size:12px;color:var(--text2);line-height:1.65;font-weight:300;}
.fund-list{display:flex;flex-direction:column;gap:10px;}
.fund-row{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:flex;gap:12px;align-items:flex-start;transition:all .2s;}
.fund-row:hover{border-color:rgba(245,158,11,.3);background:#1e2030;}
.fund-amount{font-family:'Bebas Neue',sans-serif;font-size:20px;color:var(--g);line-height:1;white-space:nowrap;min-width:50px;text-align:right;}
.fund-co{font-size:13px;font-weight:500;margin-bottom:2px;}
.fund-detail{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text3);letter-spacing:.04em;}
.fund-desc{font-size:11.5px;color:var(--text2);margin-top:3px;font-weight:300;line-height:1.5;}
.sector-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;}
.s-row{display:flex;flex-direction:column;gap:5px;padding:10px;border-radius:8px;transition:background .15s;}
.s-row:hover{background:var(--surface2);}
.s-top{display:flex;justify-content:space-between;align-items:center;}
.s-name{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);}
.s-pct{font-family:'Bebas Neue',sans-serif;font-size:16px;color:var(--text);}
.s-bar-bg{height:4px;background:var(--border2);border-radius:2px;overflow:hidden;}
.s-bar-fill{height:100%;border-radius:2px;}
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

/* ── MODAL ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px);animation:fadeIn .2s ease;}
@keyframes fadeIn{from{opacity:0;}to{opacity:1;}}
.modal{background:var(--surface);border:1px solid var(--border2);border-radius:16px;width:100%;max-width:640px;max-height:85vh;overflow-y:auto;animation:slideUp .25s ease;}
@keyframes slideUp{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}
.modal-head{padding:20px 24px;border-bottom:1px solid var(--border);display:flex;align-items:flex-start;justify-content:space-between;position:sticky;top:0;background:var(--surface);z-index:1;}
.modal-title{font-family:'Playfair Display',serif;font-size:22px;color:var(--text);}
.modal-close{background:var(--surface2);border:1px solid var(--border);color:var(--text2);width:32px;height:32px;border-radius:50%;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s;}
.modal-close:hover{background:var(--r);color:#fff;border-color:var(--r);}
.modal-body{padding:24px;}
.modal-section{margin-bottom:20px;}
.modal-section-title{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--g);margin-bottom:10px;display:flex;align-items:center;gap:8px;}
.modal-section-title::after{content:'';flex:1;height:1px;background:var(--border);}
.modal-text{font-size:13.5px;color:var(--text2);line-height:1.8;font-weight:300;}
.risk-list{display:flex;flex-direction:column;gap:8px;}
.risk-item{display:flex;align-items:flex-start;gap:10px;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.15);border-radius:8px;padding:10px 12px;}
.risk-num{font-family:'Bebas Neue',sans-serif;font-size:18px;color:var(--r);line-height:1;flex-shrink:0;}
.risk-text{font-size:13px;color:var(--text2);line-height:1.6;}
.action-box{background:rgba(0,217,126,.06);border:1px solid rgba(0,217,126,.2);border-radius:8px;padding:14px 16px;}
.action-text{font-size:13.5px;color:var(--text);line-height:1.7;}
.ai-analysis-area{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;min-height:80px;}
.ai-analysis-content{font-size:13px;color:var(--text2);line-height:1.8;white-space:pre-wrap;}
.ai-btn{width:100%;padding:12px;background:var(--g);color:#000;border:none;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700;letter-spacing:.06em;cursor:pointer;transition:all .2s;margin-top:12px;}
.ai-btn:hover{background:#00f090;transform:translateY(-1px);}
.ai-btn:disabled{opacity:.5;cursor:not-allowed;transform:none;}
.dots span{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--g);margin:0 2px;animation:dotB 1.2s infinite;}
.dots span:nth-child(2){animation-delay:.2s;}.dots span:nth-child(3){animation-delay:.4s;}
@keyframes dotB{0%,80%,100%{transform:translateY(0);opacity:.4;}40%{transform:translateY(-5px);opacity:1;}}

/* SECTOR MODAL */
.sector-modal-bar{height:6px;border-radius:3px;margin:8px 0;}
.sector-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}
.sector-stat{background:var(--surface2);border-radius:8px;padding:12px;border:1px solid var(--border);}
.sector-stat-label{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;}
.sector-stat-value{font-size:13px;color:var(--text);line-height:1.6;}

@media(max-width:960px){.main{grid-template-columns:1fr;padding:16px;gap:16px;}.col-left,.col-right,.span-col{grid-column:1;}}
@media(max-width:480px){.topbar{padding:0 16px;}.topbar-date{display:none;}.hero{padding:24px 16px 20px;}.modal{max-height:92vh;}}
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
  <h1 class="hero-title">${editorial.quote.substring(0,45)}...</h1>
  <p class="hero-desc">Claude AI Agent가 오늘의 글로벌·국내 에너지 투자 동향을 분석했습니다. 각 항목을 클릭하면 상세 내용을 확인할 수 있습니다.</p>
  <div class="hero-meta">
    <span class="hero-chip hc-g">⚡ 추천 딜 ${deals.length}건 (클릭 가능)</span>
    <span class="hero-chip hc-b">🌐 뉴스 ${globalNews.length}건 (원문 링크)</span>
    <span class="hero-chip hc-o">📊 섹터 리포트 (클릭 가능)</span>
  </div>
</div>
<div class="main">
  <div class="card span-col">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-g">🎯</div>오늘의 추천 딜 — 클릭하여 상세 분석</div>
      <div class="card-badge cb-g">AI SCORED</div>
    </div>
    <div class="card-body"><div class="deal-list">${dealsHTML}</div></div>
  </div>
  <div class="card col-left">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-b">🌐</div>글로벌 에너지 투자 뉴스 — 클릭시 원문</div>
      <div class="card-badge cb-b">GLOBAL</div>
    </div>
    <div class="card-body"><div class="news-list">${globalHTML}</div></div>
  </div>
  <div class="card col-right">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-o">🇰🇷</div>국내 펀딩 소식 — 클릭시 검색</div>
      <div class="card-badge cb-o">DOMESTIC</div>
    </div>
    <div class="card-body"><div class="fund-list">${domesticHTML}</div></div>
  </div>
  <div class="card span-col">
    <div class="card-head">
      <div class="card-title"><div class="card-icon ci-p">📊</div>섹터별 투자 트렌드 — 클릭하여 리포트</div>
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

<!-- MODAL -->
<div id="modal" style="display:none"></div>

<script>
const DEALS = ${dealsJSON};
const SECTORS = ${sectorJSON};
const API_SYSTEM = "당신은 에너지 CVC 심사역 AI입니다. 요청한 기업에 대해 투자 관점의 심층 분석을 한국어로 제공하세요. 기술 차별성, 시장 포지셔닝, 경쟁사 비교, 밸류에이션 적정성, 투자 타이밍을 포함하세요.";

function closeModal() {
  document.getElementById('modal').style.display = 'none';
  document.body.style.overflow = '';
}

function showModal(html) {
  const m = document.getElementById('modal');
  m.innerHTML = \`<div class="modal-overlay" onclick="closeModal()"><div class="modal" onclick="event.stopPropagation()">\${html}</div></div>\`;
  m.style.display = 'block';
  document.body.style.overflow = 'hidden';
}

// ── 딜 상세 팝업 ──
function openDeal(i) {
  const d = DEALS[i];
  const risksHTML = d.detail.risks.map((r,n) => \`
    <div class="risk-item">
      <div class="risk-num">\${n+1}</div>
      <div class="risk-text">\${r}</div>
    </div>\`).join('');

  showModal(\`
    <div class="modal-head">
      <div>
        <div class="modal-title">\${d.name}</div>
        <div style="display:flex;gap:6px;margin-top:6px">
          \${d.tags.map(t=>\`<span class="dtag \${t.c}">\${t.t}</span>\`).join('')}
        </div>
      </div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div class="modal-section">
        <div class="modal-section-title">🔬 기술 검증</div>
        <div class="modal-text">\${d.detail.tech}</div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">💰 밸류에이션 분석</div>
        <div class="modal-text">\${d.detail.valuation}</div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">⚠️ 리스크 요인</div>
        <div class="risk-list">\${risksHTML}</div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">✅ 즉시 액션 아이템</div>
        <div class="action-box"><div class="action-text">\${d.detail.action}</div></div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">🤖 Claude AI 심층 분석</div>
        <div class="ai-analysis-area">
          <div class="ai-analysis-content" id="ai-content-\${i}">버튼을 눌러 실시간 AI 심층 분석을 받아보세요.</div>
        </div>
        <button class="ai-btn" id="ai-btn-\${i}" onclick="runAI(\${i})">
          🔍 AI 심층 분석 실행 (Claude 실시간)
        </button>
      </div>
    </div>\`);
}

// ── AI 실시간 심층 분석 ──
async function runAI(i) {
  const d = DEALS[i];
  const btn = document.getElementById(\`ai-btn-\${i}\`);
  const content = document.getElementById(\`ai-content-\${i}\`);
  btn.disabled = true;
  btn.innerHTML = '<div class="dots"><span></span><span></span><span></span></div> 분석 중...';
  content.textContent = '';

  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        system: API_SYSTEM,
        messages: [{ role: 'user', content: \`\${d.name} (\${d.tags.map(t=>t.t).join(', ')}) 기업에 대한 CVC 투자 관점 심층 분석을 해주세요. 현재 스코어 \${d.score}/10. \${d.desc}\` }]
      })
    });
    const data = await res.json();
    const text = data.content?.[0]?.text || '분석을 가져올 수 없습니다.';
    // typewriter
    content.textContent = '';
    for(let j=0; j<text.length; j++) {
      content.textContent += text[j];
      await new Promise(r=>setTimeout(r,8));
    }
    btn.style.display = 'none';
  } catch(e) {
    content.textContent = 'API 연결 오류: ' + e.message;
    btn.disabled = false;
    btn.textContent = '다시 시도';
  }
}

// ── 섹터 리포트 팝업 ──
function openSector(i) {
  const s = SECTORS[i];
  const r = s.report;
  showModal(\`
    <div class="modal-head">
      <div>
        <div class="modal-title">\${s.name}</div>
        <div style="font-family:JetBrains Mono,monospace;font-size:11px;color:var(--text3);margin-top:4px">이번달 투자 활성도 \${s.pct}%</div>
      </div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div class="sector-modal-bar" style="background:\${s.color};width:\${s.pct}%"></div>
      <div class="modal-section">
        <div class="modal-section-title">📊 섹터 현황</div>
        <div class="modal-text">\${r.summary}</div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">🎯 주목할 딜</div>
        <div class="modal-text">\${r.topDeals}</div>
      </div>
      <div class="sector-stat-grid">
        <div class="sector-stat">
          <div class="sector-stat-label">📈 6개월 전망</div>
          <div class="sector-stat-value">\${r.outlook}</div>
        </div>
        <div class="sector-stat">
          <div class="sector-stat-label">⚠️ 주요 리스크</div>
          <div class="sector-stat-value">\${r.risk}</div>
        </div>
      </div>
    </div>\`);
}

// ESC 키로 모달 닫기
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeModal(); });
</script>
</body>
</html>`;
}

async function main() {
  console.log(`\n🚀 Energy CVC Briefing v2 생성 — ${korDate()}\n`);
  try {
    console.log('① 추천 딜 스코어링...');
    const deals = JSON.parse((await callClaude(SYSTEM, PROMPTS.deals)).replace(/```json|```/g,'').trim());
    console.log('② 글로벌 뉴스...');
    const global = JSON.parse((await callClaude(SYSTEM, PROMPTS.global)).replace(/```json|```/g,'').trim());
    console.log('③ 국내 펀딩...');
    const domestic = JSON.parse((await callClaude(SYSTEM, PROMPTS.domestic)).replace(/```json|```/g,'').trim());
    console.log('④ 섹터 트렌드...');
    const sector = JSON.parse((await callClaude(SYSTEM, PROMPTS.sector)).replace(/```json|```/g,'').trim());
    console.log('⑤ 에디토리얼...');
    const editorial = JSON.parse((await callClaude(SYSTEM, PROMPTS.editorial)).replace(/```json|```/g,'').trim());
    console.log('⑥ HTML 생성...');
    fs.writeFileSync('index.html', buildHTML({ deals, global, domestic, sector, editorial }), 'utf8');
    console.log('\n✅ 완료!\n');
  } catch(err) {
    console.error('\n❌ 오류:', err.message);
    process.exit(1);
  }
}

main();

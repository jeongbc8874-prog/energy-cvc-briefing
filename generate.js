/**
 * Energy CVC Daily Briefing Generator v3
 * JSON 파싱 안정화 버전
 */

const https = require('https');
const fs = require('fs');

const API_KEY = process.env.ANTHROPIC_API_KEY;
if (!API_KEY) { console.error('ANTHROPIC_API_KEY 없음'); process.exit(1); }

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

function safeParseJSON(text) {
  let clean = text.replace(/```json/gi,'').replace(/```/g,'').trim();

  // 문자열 값 안의 줄바꿈 제거 (JSON 파싱 실패 주원인)
  // 따옴표 안의 내용에서 줄바꿈을 공백으로 치환
  clean = clean.replace(/"([^"]*)"/g, function(match, inner) {
    return '"' + inner.replace(/\n/g,' ').replace(/\r/g,'').replace(/[\r\n]/g,' ') + '"';
  });

  // 배열 또는 객체만 추출
  const arrStart = clean.indexOf('[');
  const objStart = clean.indexOf('{');
  if (arrStart !== -1 && (objStart === -1 || arrStart < objStart)) {
    const arrEnd = clean.lastIndexOf(']');
    if (arrEnd > arrStart) clean = clean.substring(arrStart, arrEnd + 1);
  } else if (objStart !== -1) {
    const objEnd = clean.lastIndexOf('}');
    if (objEnd > objStart) clean = clean.substring(objStart, objEnd + 1);
  }

  try {
    return JSON.parse(clean);
  } catch(e) {
    // 마지막 불완전 항목 제거 후 재시도
    if (clean.startsWith('[')) {
      const lastGood = clean.lastIndexOf('},{');
      if (lastGood > 0) {
        try { return JSON.parse(clean.substring(0, lastGood+1) + ']'); } catch(e2) {}
      }
    }
    console.error('JSON 파싱 실패:', e.message);
    console.error('원본 앞부분:', clean.substring(0, 400));
    throw e;
  }
}

const SYSTEM = `You are an AI agent for Korean energy CVC investors.
Today is ${korDate()}.
CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no explanations.
All text values must be single-line strings with NO line breaks inside strings.
Use Korean text for descriptions.`;

const PROMPTS = {
  deals: `Return a JSON array of 4 recommended energy startup deals.
Schema for each item:
{"name":"Company Name","score":"9.2","scoreClass":"s-high","colorClass":"","tags":[{"t":"ESS","c":"dt-sector"},{"t":"Series B $55M","c":"dt-stage"},{"t":"USA","c":"dt-country"}],"desc":"One sentence description in Korean","signal":"Korean signal text","detail":{"tech":"Korean tech validation 1-2 sentences","valuation":"Korean valuation analysis 1-2 sentences","risks":["Korean risk 1","Korean risk 2","Korean risk 3"],"action":"Korean action item"}}
scoreClass: s-high(8+) or s-mid(6-8). colorClass: empty string or blue or amber or purple.
Cover diverse sectors: ESS, hydrogen, solar, energy AI, SMR, CCUS.
Return ONLY the JSON array.`,

  global: `Return a JSON array of 5 global energy investment news items.
Schema: {"tag":"글로벌","tagC":"nt-g","time":"2시간 전","title":"Korean news title","body":"Korean 1-2 sentence insight for CVC investors","url":"https://www.google.com/search?q=energy+investment+news"}
tagC options: nt-g nt-b nt-o nt-r nt-p
Return ONLY the JSON array.`,

  domestic: `Return a JSON array of 4 Korean domestic energy startup funding news.
Schema: {"amount":"150억","co":"Company name","detail":"Series B ESS","desc":"Korean 1-2 sentence insight","url":"https://www.google.com/search?q=Korean+energy+startup+funding"}
Return ONLY the JSON array.`,

  sector: `Return a JSON array of 6 energy sector investment trends.
Schema: {"name":"ESS / 배터리","pct":"84","color":"var(--g)","note":"Korean one sentence trend","report":{"summary":"Korean 2-3 sentence sector overview","topDeals":"Korean mention of 2-3 notable deals","outlook":"Korean 2 sentence 6-month outlook","risk":"Korean 1-2 sentence risk"}}
Use exactly these 6 sectors with these colors:
ESS/배터리 var(--g), 그린수소 var(--b), 태양광 var(--o), 에너지AI #a78bfa, SMR/원자력 #f472b6, CCUS #34d399
Return ONLY the JSON array.`,

  editorial: `Return a JSON object with today's editorial for Korean energy CVC investors.
Schema: {"quote":"Korean one sentence key insight","body":"Korean 400-500 char editorial with 3 action items for investors today"}
Return ONLY the JSON object.`
};

function buildHTML(data) {
  const { deals, global: globalNews, domestic, sector, editorial } = data;
  const today = korDate();
  const now = timeStr();

  const dealsJSON = JSON.stringify(deals).replace(/\\/g,'\\\\').replace(/`/g,'\\`');
  const sectorJSON = JSON.stringify(sector).replace(/\\/g,'\\\\').replace(/`/g,'\\`');

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
      <div class="deal-hint">🔍 클릭하여 상세 분석</div>
    </div>`).join('');

  const globalHTML = globalNews.map(n => `
    <div class="news-item" onclick="window.open('${n.url}','_blank')" style="cursor:pointer">
      <div class="news-meta">
        <span class="ntag ${n.tagC}">${n.tag}</span>
        <span class="ntime">${n.time}</span>
        <span class="nlink">↗ 원문</span>
      </div>
      <div class="news-title">${n.title}</div>
      <div class="news-body">${n.body}</div>
    </div>`).join('');

  const domesticHTML = domestic.map(f => `
    <div class="fund-row" onclick="window.open('${f.url}','_blank')" style="cursor:pointer">
      <div class="fund-amount">${f.amount}</div>
      <div class="fund-info">
        <div class="fund-co">${f.co} <span class="nlink">↗</span></div>
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
      <div class="s-bar-bg"><div class="s-bar-fill" style="width:${s.pct}%;background:${s.color}"></div></div>
      <div class="s-note">${s.note} <span class="nlink">📊 리포트</span></div>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>Energy CVC Daily Briefing — ${isoDate()}</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@300;400;500&family=Playfair+Display:ital,wght@0,700;1,400&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0d11;--sf:#13161e;--sf2:#1a1e29;--bd:#222736;--bd2:#2a3045;--g:#00d97e;--b:#3b82f6;--o:#f59e0b;--r:#ef4444;--p:#a78bfa;--tx:#e8edf5;--tx2:#7c8db5;--tx3:#404860;}
*{margin:0;padding:0;box-sizing:border-box;}html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--tx);font-family:'Noto Sans KR',sans-serif;min-height:100vh;overflow-x:hidden;}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;background-image:linear-gradient(rgba(0,217,126,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,217,126,.025) 1px,transparent 1px);background-size:48px 48px;}
.tb{position:sticky;top:0;z-index:200;background:rgba(11,13,17,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;padding:0 28px;height:56px;}
.tb-logo{font-family:'Bebas Neue',sans-serif;font-size:20px;letter-spacing:.08em;color:var(--g);display:flex;align-items:center;gap:10px;}
.tb-logo span{color:var(--tx2);font-size:14px;font-family:'JetBrains Mono',monospace;}
.tb-r{display:flex;align-items:center;gap:14px;}
.pb{display:flex;align-items:center;gap:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--g);background:rgba(0,217,126,.08);border:1px solid rgba(0,217,126,.18);padding:4px 10px;border-radius:20px;}
.pd{width:6px;height:6px;border-radius:50%;background:var(--g);animation:bk 2s infinite;}
@keyframes bk{0%,100%{opacity:1;}50%{opacity:.3;}}
.tb-d{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);}
.hero{position:relative;z-index:1;background:linear-gradient(135deg,rgba(0,217,126,.06),rgba(59,130,246,.04));border-bottom:1px solid var(--bd);padding:36px 28px 28px;}
.hk{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--g);margin-bottom:10px;display:flex;align-items:center;gap:8px;}
.hk::before{content:'';width:20px;height:1px;background:var(--g);}
.ht{font-family:'Playfair Display',serif;font-size:clamp(22px,4vw,38px);line-height:1.2;color:var(--tx);margin-bottom:10px;}
.hd{font-size:13px;color:var(--tx2);line-height:1.8;max-width:600px;font-weight:300;}
.hm{margin-top:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.hc{font-family:'JetBrains Mono',monospace;font-size:10px;padding:4px 10px;border-radius:4px;}
.hc-g{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.2);}
.hc-b{background:rgba(59,130,246,.1);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.hc-o{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
.main{position:relative;z-index:1;max-width:1280px;margin:0 auto;padding:28px;display:grid;grid-template-columns:1fr 340px;gap:20px;}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:12px;overflow:hidden;animation:fu .5s ease both;}
@keyframes fu{from{opacity:0;transform:translateY(14px);}to{opacity:1;transform:translateY(0);}}
.card:nth-child(1){animation-delay:.05s;}.card:nth-child(2){animation-delay:.1s;}.card:nth-child(3){animation-delay:.15s;}.card:nth-child(4){animation-delay:.2s;}
.ch{padding:14px 20px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;}
.ct{display:flex;align-items:center;gap:8px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--tx2);}
.ci{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;}
.ci-g{background:rgba(0,217,126,.15);}.ci-b{background:rgba(59,130,246,.15);}.ci-o{background:rgba(245,158,11,.15);}.ci-p{background:rgba(167,139,250,.15);}
.cb{font-family:'JetBrains Mono',monospace;font-size:9px;padding:3px 8px;border-radius:20px;}
.cb-g{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.18);}
.cb-b{background:rgba(59,130,246,.1);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.cb-o{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
.cb-p{background:rgba(167,139,250,.1);color:#c4b5fd;border:1px solid rgba(167,139,250,.2);}
.cb-{padding:20px;}
.sc{grid-column:1/-1;}.cl{grid-column:1;}.cr{grid-column:2;}
.dl{display:flex;flex-direction:column;gap:12px;}
.deal-row{background:var(--sf2);border:1px solid var(--bd);border-radius:10px;padding:16px;border-left:3px solid var(--g);transition:all .2s;}
.deal-row:hover{border-color:rgba(0,217,126,.5);transform:translateX(3px);background:#1e2535;}
.deal-row.blue{border-left-color:var(--b);}.deal-row.amber{border-left-color:var(--o);}.deal-row.purple{border-left-color:var(--p);}
.deal-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;}
.deal-name{font-family:'Playfair Display',serif;font-size:17px;}
.deal-score{font-family:'Bebas Neue',sans-serif;font-size:26px;line-height:1;}
.deal-score.s-high{color:var(--g);}.deal-score.s-mid{color:var(--o);}
.deal-score-label{font-family:'JetBrains Mono',monospace;font-size:8px;color:var(--tx3);text-align:right;}
.deal-tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px;}
.dtag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 7px;border-radius:3px;}
.dt-sector{background:rgba(59,130,246,.12);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.dt-stage{background:rgba(255,255,255,.05);color:var(--tx2);border:1px solid var(--bd2);}
.dt-country{background:rgba(0,217,126,.08);color:var(--g);border:1px solid rgba(0,217,126,.15);}
.deal-desc{font-size:12px;color:var(--tx2);line-height:1.65;font-weight:300;}
.deal-signal{margin-top:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--g);}
.deal-hint{margin-top:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);}
.deal-row:hover .deal-hint{color:var(--g);}
.nl{display:flex;flex-direction:column;}
.news-item{padding:12px 8px;border-bottom:1px solid var(--bd);border-radius:6px;transition:background .15s;}
.news-item:hover{background:var(--sf2);}
.news-item:last-child{border-bottom:none;}
.news-meta{display:flex;align-items:center;gap:6px;margin-bottom:5px;}
.ntag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;}
.nt-g{background:rgba(0,217,126,.12);color:var(--g);}.nt-b{background:rgba(59,130,246,.12);color:#7ab3ff;}
.nt-o{background:rgba(245,158,11,.12);color:#fbbf24;}.nt-r{background:rgba(239,68,68,.1);color:#fca5a5;}.nt-p{background:rgba(167,139,250,.12);color:#c4b5fd;}
.ntime{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--tx3);}
.nlink{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--b);margin-left:auto;}
.news-title{font-size:13px;font-weight:500;line-height:1.55;color:var(--tx);margin-bottom:3px;}
.news-body{font-size:12px;color:var(--tx2);line-height:1.65;font-weight:300;}
.fl{display:flex;flex-direction:column;gap:10px;}
.fund-row{background:var(--sf2);border:1px solid var(--bd);border-radius:8px;padding:12px 14px;display:flex;gap:12px;transition:all .2s;}
.fund-row:hover{border-color:rgba(245,158,11,.3);}
.fund-amount{font-family:'Bebas Neue',sans-serif;font-size:20px;color:var(--g);line-height:1;white-space:nowrap;min-width:50px;text-align:right;}
.fund-co{font-size:13px;font-weight:500;margin-bottom:2px;}
.fund-detail{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);}
.fund-desc{font-size:11.5px;color:var(--tx2);margin-top:3px;font-weight:300;line-height:1.5;}
.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;}
.s-row{display:flex;flex-direction:column;gap:5px;padding:10px;border-radius:8px;transition:background .15s;}
.s-row:hover{background:var(--sf2);}
.s-top{display:flex;justify-content:space-between;align-items:center;}
.s-name{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--tx2);}
.s-pct{font-family:'Bebas Neue',sans-serif;font-size:16px;color:var(--tx);}
.s-bar-bg{height:4px;background:var(--bd2);border-radius:2px;overflow:hidden;}
.s-bar-fill{height:100%;border-radius:2px;}
.s-note{font-size:11px;color:var(--tx3);font-weight:300;}
.ew{background:linear-gradient(135deg,rgba(0,217,126,.04),rgba(59,130,246,.03));border-radius:10px;padding:24px;border:1px solid rgba(0,217,126,.1);}
.eq{font-family:'Playfair Display',serif;font-style:italic;font-size:clamp(15px,2vw,18px);line-height:1.6;color:var(--tx);margin-bottom:18px;padding-bottom:18px;border-bottom:1px solid var(--bd);}
.eb{font-size:13.5px;line-height:1.95;color:var(--tx2);font-weight:300;white-space:pre-wrap;}
.ebl{margin-top:18px;display:flex;align-items:center;gap:10px;}
.ea{width:30px;height:30px;border-radius:50%;background:var(--g);display:flex;align-items:center;justify-content:center;font-family:'Bebas Neue',sans-serif;font-size:13px;color:#000;flex-shrink:0;}
.et{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);line-height:1.5;}
.ft{position:relative;z-index:1;border-top:1px solid var(--bd);padding:20px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;}
.fl2{font-family:'Bebas Neue',sans-serif;font-size:16px;letter-spacing:.08em;color:var(--tx3);}
.fr{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);text-align:right;}
/* MODAL */
.mo{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px);animation:fi .2s ease;}
@keyframes fi{from{opacity:0;}to{opacity:1;}}
.mb{background:var(--sf);border:1px solid var(--bd2);border-radius:16px;width:100%;max-width:640px;max-height:85vh;overflow-y:auto;animation:su .25s ease;}
@keyframes su{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}
.mh{padding:20px 24px;border-bottom:1px solid var(--bd);display:flex;align-items:flex-start;justify-content:space-between;position:sticky;top:0;background:var(--sf);z-index:1;}
.mt{font-family:'Playfair Display',serif;font-size:22px;color:var(--tx);}
.mc{background:var(--sf2);border:1px solid var(--bd);color:var(--tx2);width:32px;height:32px;border-radius:50%;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s;}
.mc:hover{background:var(--r);color:#fff;border-color:var(--r);}
.mbd{padding:24px;}
.ms{margin-bottom:20px;}
.mst{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--g);margin-bottom:10px;display:flex;align-items:center;gap:8px;}
.mst::after{content:'';flex:1;height:1px;background:var(--bd);}
.mtx{font-size:13.5px;color:var(--tx2);line-height:1.8;font-weight:300;}
.rl{display:flex;flex-direction:column;gap:8px;}
.ri{display:flex;align-items:flex-start;gap:10px;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.15);border-radius:8px;padding:10px 12px;}
.rn{font-family:'Bebas Neue',sans-serif;font-size:18px;color:var(--r);line-height:1;flex-shrink:0;}
.rt{font-size:13px;color:var(--tx2);line-height:1.6;}
.ab{background:rgba(0,217,126,.06);border:1px solid rgba(0,217,126,.2);border-radius:8px;padding:14px 16px;}
.at{font-size:13.5px;color:var(--tx);line-height:1.7;}
.aa{background:var(--sf2);border:1px solid var(--bd);border-radius:10px;padding:16px;min-height:80px;}
.ac{font-size:13px;color:var(--tx2);line-height:1.8;white-space:pre-wrap;}
.ai-btn{width:100%;padding:12px;background:var(--g);color:#000;border:none;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700;cursor:pointer;transition:all .2s;margin-top:12px;}
.ai-btn:hover{background:#00f090;transform:translateY(-1px);}
.ai-btn:disabled{opacity:.5;cursor:not-allowed;transform:none;}
.dots span{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--g);margin:0 2px;animation:db 1.2s infinite;}
.dots span:nth-child(2){animation-delay:.2s;}.dots span:nth-child(3){animation-delay:.4s;}
@keyframes db{0%,80%,100%{transform:translateY(0);opacity:.4;}40%{transform:translateY(-5px);opacity:1;}}
.smb{height:6px;border-radius:3px;margin:8px 0;}
.ssg{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}
.ss{background:var(--sf2);border-radius:8px;padding:12px;border:1px solid var(--bd);}
.ssl{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--tx3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;}
.ssv{font-size:13px;color:var(--tx);line-height:1.6;}
.card-body{padding:20px;}
@media(max-width:960px){.main{grid-template-columns:1fr;padding:16px;gap:16px;}.cl,.cr,.sc{grid-column:1;}}
@media(max-width:480px){.tb{padding:0 16px;}.tb-d{display:none;}.hero{padding:24px 16px 20px;}.mb{max-height:92vh;}}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:3px;}
</style>
</head>
<body>
<div class="tb">
  <div class="tb-logo">ENERGY CVC <span>/ DAILY BRIEFING</span></div>
  <div class="tb-r">
    <div class="tb-d">${today}</div>
    <div class="pb"><div class="pd"></div>AI GENERATED</div>
  </div>
</div>
<div class="hero">
  <div class="hk">TODAY'S INTELLIGENCE · ${today}</div>
  <h1 class="ht">${editorial.quote.substring(0,45)}...</h1>
  <p class="hd">Claude AI Agent가 오늘의 에너지 투자 동향을 분석했습니다. 각 항목을 클릭하면 상세 내용을 볼 수 있습니다.</p>
  <div class="hm">
    <span class="hc hc-g">⚡ 추천 딜 ${deals.length}건</span>
    <span class="hc hc-b">🌐 뉴스 ${globalNews.length}건</span>
    <span class="hc hc-o">📊 섹터 리포트</span>
  </div>
</div>
<div class="main">
  <div class="card sc">
    <div class="ch"><div class="ct"><div class="ci ci-g">🎯</div>오늘의 추천 딜</div><div class="cb cb-g">AI SCORED · 클릭가능</div></div>
    <div class="card-body"><div class="dl">${dealsHTML}</div></div>
  </div>
  <div class="card cl">
    <div class="ch"><div class="ct"><div class="ci ci-b">🌐</div>글로벌 투자 뉴스</div><div class="cb cb-b">클릭시 원문</div></div>
    <div class="card-body"><div class="nl">${globalHTML}</div></div>
  </div>
  <div class="card cr">
    <div class="ch"><div class="ct"><div class="ci ci-o">🇰🇷</div>국내 펀딩 소식</div><div class="cb cb-o">클릭시 검색</div></div>
    <div class="card-body"><div class="fl">${domesticHTML}</div></div>
  </div>
  <div class="card sc">
    <div class="ch"><div class="ct"><div class="ci ci-p">📊</div>섹터별 투자 트렌드</div><div class="cb cb-p">클릭시 리포트</div></div>
    <div class="card-body"><div class="sg">${sectorHTML}</div></div>
  </div>
  <div class="card sc">
    <div class="ch"><div class="ct"><div class="ci ci-g">✍️</div>심사역 AI 에디토리얼</div><div class="cb cb-g">CLAUDE ANALYSIS</div></div>
    <div class="card-body">
      <div class="ew">
        <div class="eq">${editorial.quote}</div>
        <div class="eb">${editorial.body}</div>
        <div class="ebl"><div class="ea">AI</div><div class="et">CLAUDE AI · ENERGY CVC INTELLIGENCE AGENT<br>${today} ${now} 자동 생성</div></div>
      </div>
    </div>
  </div>
</div>
<div class="ft">
  <div class="fl2">ENERGY · CVC INTELLIGENCE</div>
  <div class="fr">Claude AI 분석 엔진<br>${today} ${now} 생성</div>
</div>
<div id="modal" style="display:none"></div>
<script>
const DEALS = ${dealsJSON};
const SECTORS = ${sectorJSON};

function closeModal(){document.getElementById('modal').style.display='none';document.body.style.overflow='';}
function showModal(html){const m=document.getElementById('modal');m.innerHTML='<div class="mo" onclick="closeModal()"><div class="mb" onclick="event.stopPropagation()">'+html+'</div></div>';m.style.display='block';document.body.style.overflow='hidden';}

function openDeal(i){
  const d=DEALS[i];
  const risks=d.detail.risks.map((r,n)=>'<div class="ri"><div class="rn">'+(n+1)+'</div><div class="rt">'+r+'</div></div>').join('');
  const tags=d.tags.map(t=>'<span class="dtag '+t.c+'">'+t.t+'</span>').join('');
  showModal('<div class="mh"><div><div class="mt">'+d.name+'</div><div style="display:flex;gap:6px;margin-top:6px">'+tags+'</div></div><button class="mc" onclick="closeModal()">✕</button></div><div class="mbd"><div class="ms"><div class="mst">🔬 기술 검증</div><div class="mtx">'+d.detail.tech+'</div></div><div class="ms"><div class="mst">💰 밸류에이션</div><div class="mtx">'+d.detail.valuation+'</div></div><div class="ms"><div class="mst">⚠️ 리스크</div><div class="rl">'+risks+'</div></div><div class="ms"><div class="mst">✅ 액션 아이템</div><div class="ab"><div class="at">'+d.detail.action+'</div></div></div><div class="ms"><div class="mst">🤖 AI 심층 분석</div><div class="aa"><div class="ac" id="ac'+i+'">버튼을 눌러 실시간 AI 심층 분석을 받아보세요.</div></div><button class="ai-btn" id="ab'+i+'" onclick="runAI('+i+')">🔍 AI 심층 분석 실행</button></div></div>');
}

async function runAI(i){
  const d=DEALS[i];
  const btn=document.getElementById('ab'+i);
  const content=document.getElementById('ac'+i);
  btn.disabled=true;
  btn.innerHTML='<div class="dots"><span></span><span></span><span></span></div> 분석 중...';
  content.textContent='';
  try{
    const res=await fetch('https://api.anthropic.com/v1/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:800,system:'당신은 에너지 CVC 심사역 AI입니다. 투자 관점의 심층 분석을 한국어로 제공하세요.',messages:[{role:'user',content:d.name+' ('+d.tags.map(t=>t.t).join(', ')+') 기업 CVC 투자 심층 분석. 스코어 '+d.score+'/10. '+d.desc}]})});
    const data=await res.json();
    const text=data.content?.[0]?.text||'분석을 가져올 수 없습니다.';
    content.textContent='';
    for(let j=0;j<text.length;j++){content.textContent+=text[j];await new Promise(r=>setTimeout(r,8));}
    btn.style.display='none';
  }catch(e){content.textContent='오류: '+e.message;btn.disabled=false;btn.textContent='다시 시도';}
}

function openSector(i){
  const s=SECTORS[i];const r=s.report;
  showModal('<div class="mh"><div><div class="mt">'+s.name+'</div><div style="font-family:JetBrains Mono,monospace;font-size:11px;color:var(--tx3);margin-top:4px">이번달 투자 활성도 '+s.pct+'%</div></div><button class="mc" onclick="closeModal()">✕</button></div><div class="mbd"><div class="smb" style="background:'+s.color+';width:'+s.pct+'%"></div><div class="ms"><div class="mst">📊 섹터 현황</div><div class="mtx">'+r.summary+'</div></div><div class="ms"><div class="mst">🎯 주목할 딜</div><div class="mtx">'+r.topDeals+'</div></div><div class="ssg"><div class="ss"><div class="ssl">📈 6개월 전망</div><div class="ssv">'+r.outlook+'</div></div><div class="ss"><div class="ssl">⚠️ 리스크</div><div class="ssv">'+r.risk+'</div></div></div></div>');
}

document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
</script>
</body>
</html>`;
}

async function main() {
  console.log('\n🚀 Energy CVC Briefing v3 — ' + korDate() + '\n');
  try {
    console.log('① 딜 스코어링...');
    const deals = safeParseJSON(await callClaude(SYSTEM, PROMPTS.deals));
    console.log('② 글로벌 뉴스...');
    const global = safeParseJSON(await callClaude(SYSTEM, PROMPTS.global));
    console.log('③ 국내 펀딩...');
    const domestic = safeParseJSON(await callClaude(SYSTEM, PROMPTS.domestic));
    console.log('④ 섹터 트렌드...');
    const sector = safeParseJSON(await callClaude(SYSTEM, PROMPTS.sector));
    console.log('⑤ 에디토리얼...');
    const editorial = safeParseJSON(await callClaude(SYSTEM, PROMPTS.editorial));
    console.log('⑥ HTML 생성...');
    fs.writeFileSync('index.html', buildHTML({ deals, global, domestic, sector, editorial }), 'utf8');
    console.log('\n✅ 완료!\n');
  } catch(err) {
    console.error('\n❌ 오류:', err.message);
    process.exit(1);
  }
}

main();

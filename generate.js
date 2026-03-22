/**
 * Energy CVC Daily Briefing Generator v5
 * 실제 데이터: OpenDART + RSS + SEC EDGAR + NewsAPI
 */

const https = require('https');
const http = require('http');
const fs = require('fs');

const CLAUDE_KEY = process.env.ANTHROPIC_API_KEY;
const NEWS_KEY = process.env.NEWS_API_KEY;
const DART_KEY = process.env.DART_API_KEY;

if (!CLAUDE_KEY) { console.error('ANTHROPIC_API_KEY 없음'); process.exit(1); }

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
function timeAgo(dateStr) {
  if (!dateStr) return '최근';
  const diff = Math.floor((Date.now() - new Date(dateStr)) / 60000);
  if (diff < 60) return diff + '분 전';
  if (diff < 1440) return Math.floor(diff/60) + '시간 전';
  return Math.floor(diff/1440) + '일 전';
}

// ── HTTP GET ──────────────────────────────────────────
function httpGet(url, isHttp) {
  return new Promise((resolve, reject) => {
    const lib = isHttp ? http : https;
    const req = lib.get(url, { headers: { 'User-Agent': 'EnergyCVC/1.0' } }, res => {
      // 리다이렉트 처리
      if (res.statusCode === 301 || res.statusCode === 302) {
        return httpGet(res.headers.location).then(resolve).catch(reject);
      }
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.setTimeout(12000, () => { req.destroy(); reject(new Error('Timeout: ' + url.substring(0,50))); });
  });
}

async function httpGetJSON(url) {
  const text = await httpGet(url);
  return JSON.parse(text);
}

// ── Claude API ────────────────────────────────────────
function callClaude(system, user) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 4000,
      system,
      messages: [{ role:'user', content: user }]
    });
    const options = {
      hostname: 'api.anthropic.com',
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': CLAUDE_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Length': Buffer.byteLength(body)
      }
    };
    const req = https.request(options, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const p = JSON.parse(data);
          if (p.error) { reject(new Error(p.error.message)); return; }
          resolve(p.content?.[0]?.text || '');
        } catch(e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ── JSON 파싱 ─────────────────────────────────────────
function safeJSON(text) {
  let c = text.replace(/```json/gi,'').replace(/```/g,'').trim();
  c = c.replace(/"([^"]*)"/g, (m, inner) =>
    '"' + inner.replace(/[\r\n]+/g,' ').replace(/\t/g,' ') + '"'
  );
  const as = c.indexOf('['), os = c.indexOf('{');
  if (as !== -1 && (os === -1 || as < os)) {
    const ae = c.lastIndexOf(']');
    if (ae > as) c = c.substring(as, ae+1);
  } else if (os !== -1) {
    const oe = c.lastIndexOf('}');
    if (oe > os) c = c.substring(os, oe+1);
  }
  try { return JSON.parse(c); }
  catch(e) {
    if (c.startsWith('[')) {
      const lg = c.lastIndexOf('},{');
      if (lg > 0) try { return JSON.parse(c.substring(0,lg+1)+']'); } catch(e2){}
    }
    throw new Error('JSON 파싱 실패: ' + e.message + '\n' + c.substring(0,300));
  }
}

// ══════════════════════════════════════════════════════
// ① OpenDART — 국내 에너지 기업 공시
// ══════════════════════════════════════════════════════
async function fetchDartFunding() {
  if (!DART_KEY) { console.log('  DART_API_KEY 없음, 스킵'); return []; }
  try {
    // 최근 30일 투자유치/CB/BW 공시 검색
    const today = new Date();
    const bgn = new Date(today - 30*24*60*60*1000).toISOString().slice(0,10).replace(/-/g,'');
    const end = today.toISOString().slice(0,10).replace(/-/g,'');

    // 에너지 관련 키워드로 공시 검색
    const keywords = ['에너지', '수소', '배터리', 'ESS', '태양광'];
    const results = [];

    for (const kw of keywords.slice(0,3)) {
      try {
        const url = `https://opendart.fss.or.kr/api/list.json?crtfc_key=${DART_KEY}&bgn_de=${bgn}&end_de=${end}&pblntf_ty=A&page_count=5&corp_name=${encodeURIComponent(kw)}`;
        const data = await httpGetJSON(url);
        if (data.list && data.list.length > 0) {
          for (const item of data.list.slice(0,2)) {
            results.push({
              corp: item.corp_name || '',
              title: item.report_nm || '',
              date: item.rcept_dt || '',
              url: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcept_no}`
            });
          }
        }
      } catch(e) { console.log('  DART 키워드 실패 (' + kw + '):', e.message); }
    }

    // 중복 제거
    const seen = new Set();
    return results.filter(r => {
      if (seen.has(r.corp)) return false;
      seen.add(r.corp);
      return true;
    }).slice(0, 5);
  } catch(e) {
    console.log('  DART 수집 실패:', e.message);
    return [];
  }
}

// ══════════════════════════════════════════════════════
// ② RSS 피드 — 글로벌 에너지 뉴스
// ══════════════════════════════════════════════════════
async function fetchRSSNews() {
  const feeds = [
    { url: 'https://techcrunch.com/tag/energy/feed/', source: 'TechCrunch' },
    { url: 'https://feeds.feedburner.com/entrepreneur/latest', source: 'Entrepreneur' },
    { url: 'https://cleantechnica.com/feed/', source: 'CleanTechnica' },
    { url: 'https://electrek.co/feed/', source: 'Electrek' },
    { url: 'https://www.greenbiz.com/rss.xml', source: 'GreenBiz' }
  ];

  const results = [];
  for (const feed of feeds) {
    try {
      const xml = await httpGet(feed.url);
      // RSS XML 파싱 (간단한 정규식)
      const items = xml.match(/<item>([\s\S]*?)<\/item>/g) || [];
      for (const item of items.slice(0,2)) {
        const title = (item.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/) ||
                       item.match(/<title>(.*?)<\/title>/) || [])[1] || '';
        const link = (item.match(/<link>(.*?)<\/link>/) ||
                      item.match(/<link\s[^>]*href="([^"]*)"/) || [])[1] || '';
        const pubDate = (item.match(/<pubDate>(.*?)<\/pubDate>/) || [])[1] || '';
        const desc = (item.match(/<description><!\[CDATA\[(.*?)\]\]><\/description>/) ||
                      item.match(/<description>(.*?)<\/description>/) || [])[1] || '';

        if (title && link) {
          results.push({
            title: title.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').trim(),
            url: link.trim(),
            publishedAt: pubDate,
            source: feed.source,
            desc: desc.replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').trim().substring(0,200)
          });
        }
      }
    } catch(e) { console.log('  RSS 실패 (' + feed.source + '):', e.message); }
  }
  return results.slice(0, 6);
}

// ══════════════════════════════════════════════════════
// ③ NewsAPI — 에너지 투자 뉴스
// ══════════════════════════════════════════════════════
async function fetchNewsAPI() {
  if (!NEWS_KEY) return [];
  try {
    const url = `https://newsapi.org/v2/everything?q=energy+startup+investment+funding&language=en&sortBy=publishedAt&pageSize=5&apiKey=${NEWS_KEY}`;
    const data = await httpGetJSON(url);
    return (data.articles || []).map(a => ({
      title: a.title || '',
      url: a.url || '',
      publishedAt: a.publishedAt || '',
      source: a.source?.name || 'NewsAPI',
      desc: (a.description || '').substring(0, 200)
    }));
  } catch(e) {
    console.log('  NewsAPI 실패:', e.message);
    return [];
  }
}

// ══════════════════════════════════════════════════════
// ④ SEC EDGAR — 미국 에너지 기업 공시
// ══════════════════════════════════════════════════════
async function fetchSECFilings() {
  try {
    // SEC EDGAR 풀텍스트 검색 - 에너지 스타트업 S-1, 8-K
    const url = 'https://efts.sec.gov/LATEST/search-index?q=%22energy+storage%22+%22funding%22&dateRange=custom&startdt=' +
      new Date(Date.now() - 14*24*60*60*1000).toISOString().slice(0,10) +
      '&enddt=' + new Date().toISOString().slice(0,10) +
      '&forms=8-K&hits.hits._source=period_of_report,entity_name,file_date,form_type&hits.hits.total=true';

    const data = await httpGetJSON(url);
    const hits = data.hits?.hits || [];
    return hits.slice(0,3).map(h => ({
      company: h._source?.entity_name || '',
      form: h._source?.form_type || '8-K',
      date: h._source?.file_date || '',
      url: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(h._source?.entity_name||'')}&type=8-K&dateb=&owner=include&count=5`
    }));
  } catch(e) {
    console.log('  SEC EDGAR 실패:', e.message);
    return [];
  }
}

// ══════════════════════════════════════════════════════
// Claude 분석 프롬프트
// ══════════════════════════════════════════════════════
const SYS = `You are an AI agent for Korean energy CVC investors. Today is ${korDate()}.
Return ONLY valid JSON. No markdown. Keep ALL strings under 50 chars except aiAnalysis (200 chars max).`;

function buildDartPrompt(dartItems) {
  const text = dartItems.map((d,i) =>
    `${i+1}. [${d.corp}] ${d.title} (${d.date}) URL: ${d.url}`
  ).join('\n');

  return `Analyze these REAL Korean company disclosures from OpenDART (금융감독원) for energy CVC investors.
Return JSON array of ${Math.min(dartItems.length, 4)} items.
Schema: [{"amount":"미공개","co":"기업명","detail":"공시 유형","desc":"Korean CVC insight 1-2 sentences","url":"EXACT_URL_FROM_DATA","isReal":true}]
CRITICAL: Use EXACT company names and URLs from the data. Keep desc under 50 chars.

Disclosures:
${text}

Return ONLY JSON array.`;
}

function buildNewsPrompt(articles) {
  const text = articles.map((a,i) =>
    `${i+1}. [${a.source}] ${a.title}\n   URL: ${a.url}\n   Date: ${a.publishedAt}`
  ).join('\n\n');

  return `Analyze these REAL energy news articles for Korean CVC investors.
Return JSON array of ${Math.min(articles.length, 5)} items.
Schema: [{"tag":"글로벌","tagC":"nt-g","time":"X시간 전","title":"Korean title (under 35chars)","body":"Korean CVC insight under 45chars","url":"EXACT_ORIGINAL_URL","source":"SOURCE_NAME"}]
tagC: nt-g(funding/green), nt-b(tech/blue), nt-o(policy/orange), nt-r(MA/red), nt-p(market/purple)
CRITICAL: Use EXACT URLs. Calculate time from: ${new Date().toISOString()}

Articles:
${text}

Return ONLY JSON array.`;
}

const PROMPTS = {
  deals: `Return JSON array of 4 energy startup deals based on TODAY's real market context (${korDate()}).
Schema: [{"name":"Co","score":"9.1","scoreClass":"s-high","colorClass":"","tags":[{"t":"ESS","c":"dt-sector"},{"t":"Series B $45M","c":"dt-stage"},{"t":"USA","c":"dt-country"}],"desc":"Korean desc","signal":"Korean signal","detail":{"tech":"Korean tech","valuation":"Korean valuation","risks":["r1","r2","r3"],"action":"Korean action","aiAnalysis":"Korean 3-4 sentence CVC analysis with recommendation"}}]
scoreClass: s-high(8+) or s-mid. colorClass: empty/blue/amber/purple. Return ONLY JSON array.`,

  sector: `Return JSON array of 6 energy sector trends for ${korDate()}. Keep ALL strings under 40 chars.
Schema: [{"name":"ESS / 배터리","pct":"84","color":"var(--g)","note":"Korean note","report":{"summary":"Korean summary","topDeals":"Korean deals","outlook":"Korean outlook","risk":"Korean risk"}}]
6 sectors: ESS/배터리 var(--g), 그린수소 var(--b), 태양광 var(--o), 에너지AI #a78bfa, SMR/원자력 #f472b6, CCUS #34d399
Return ONLY JSON array.`,

  editorial: `Return JSON for today's editorial (${korDate()}). Schema: {"quote":"Korean insight sentence","body":"Korean 400char editorial with 3 action items"}
Return ONLY JSON object.`
};

// ══════════════════════════════════════════════════════
// HTML 생성
// ══════════════════════════════════════════════════════
function buildHTML(data) {
  const { deals, news, domestic, sector, editorial, dataSources } = data;
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

  const newsHTML = news.map(n => `
    <div class="news-item" onclick="window.open('${n.url}','_blank')" style="cursor:pointer">
      <div class="news-meta">
        <span class="ntag ${n.tagC}">${n.tag}</span>
        <span class="ntime">${n.time} · ${n.source||''}</span>
        <span class="nlink">↗ 원문</span>
      </div>
      <div class="news-title">${n.title}</div>
      <div class="news-body">${n.body}</div>
    </div>`).join('');

  const domesticHTML = domestic.length > 0 ? domestic.map(f => `
    <div class="fund-row" onclick="window.open('${f.url}','_blank')" style="cursor:pointer">
      <div class="fund-amount">${f.amount}</div>
      <div class="fund-info">
        <div class="fund-co">${f.co} ${f.isReal ? '<span class="real-tag">DART</span>' : ''} <span class="nlink">↗</span></div>
        <div class="fund-detail">${f.detail}</div>
        <div class="fund-desc">${f.desc}</div>
      </div>
    </div>`).join('') : '<div style="color:var(--tx3);font-size:13px;padding:10px">오늘 국내 에너지 공시 없음</div>';

  const sectorHTML = sector.map((s,i) => `
    <div class="s-row" onclick="openSector(${i})" style="cursor:pointer">
      <div class="s-top">
        <div class="s-name">${s.name}</div>
        <div class="s-pct">${s.pct}%</div>
      </div>
      <div class="s-bar-bg"><div class="s-bar-fill" style="width:${s.pct}%;background:${s.color}"></div></div>
      <div class="s-note">${s.note} <span class="nlink">📊</span></div>
    </div>`).join('');

  const sourcesBadges = dataSources.map(s =>
    `<span class="src-badge">${s}</span>`
  ).join('');

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
.tb-r{display:flex;align-items:center;gap:10px;}
.pb{display:flex;align-items:center;gap:6px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--g);background:rgba(0,217,126,.08);border:1px solid rgba(0,217,126,.18);padding:4px 10px;border-radius:20px;}
.pd{width:6px;height:6px;border-radius:50%;background:var(--g);animation:bk 2s infinite;}
@keyframes bk{0%,100%{opacity:1;}50%{opacity:.3;}}
.tb-d{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--tx3);}
.hero{position:relative;z-index:1;background:linear-gradient(135deg,rgba(0,217,126,.06),rgba(59,130,246,.04));border-bottom:1px solid var(--bd);padding:36px 28px 28px;}
.hk{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--g);margin-bottom:10px;display:flex;align-items:center;gap:8px;}
.hk::before{content:'';width:20px;height:1px;background:var(--g);}
.ht{font-family:'Playfair Display',serif;font-size:clamp(22px,4vw,38px);line-height:1.2;color:var(--tx);margin-bottom:10px;}
.hd{font-size:13px;color:var(--tx2);line-height:1.8;max-width:600px;font-weight:300;}
.hm{margin-top:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.hc{font-family:'JetBrains Mono',monospace;font-size:10px;padding:4px 10px;border-radius:4px;}
.hc-g{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.2);}
.hc-b{background:rgba(59,130,246,.1);color:#7ab3ff;border:1px solid rgba(59,130,246,.2);}
.hc-o{background:rgba(245,158,11,.1);color:#fbbf24;border:1px solid rgba(245,158,11,.2);}
.src-badge{font-family:'JetBrains Mono',monospace;font-size:9px;padding:3px 7px;border-radius:3px;background:rgba(255,255,255,.06);color:var(--tx3);border:1px solid var(--bd2);}
.real-tag{font-family:'JetBrains Mono',monospace;font-size:8px;padding:1px 5px;border-radius:3px;background:rgba(0,217,126,.15);color:var(--g);border:1px solid rgba(0,217,126,.3);margin-left:4px;}
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
.cb-r{background:rgba(239,68,68,.1);color:#fca5a5;border:1px solid rgba(239,68,68,.2);}
.cb-dart{background:rgba(0,217,126,.1);color:var(--g);border:1px solid rgba(0,217,126,.3);}
.card-body{padding:20px;}
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
.news-meta{display:flex;align-items:center;gap:6px;margin-bottom:5px;flex-wrap:wrap;}
.ntag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;}
.nt-g{background:rgba(0,217,126,.12);color:var(--g);}.nt-b{background:rgba(59,130,246,.12);color:#7ab3ff;}
.nt-o{background:rgba(245,158,11,.12);color:#fbbf24;}.nt-r{background:rgba(239,68,68,.1);color:#fca5a5;}.nt-p{background:rgba(167,139,250,.12);color:#c4b5fd;}
.ntime{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--tx3);}
.nlink{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--b);margin-left:auto;}
.news-title{font-size:13px;font-weight:500;line-height:1.55;color:var(--tx);margin-bottom:3px;}
.news-body{font-size:12px;color:var(--tx2);line-height:1.65;font-weight:300;}
.fl{display:flex;flex-direction:column;gap:10px;}
.fund-row{background:var(--sf2);border:1px solid var(--bd);border-radius:8px;padding:12px 14px;display:flex;gap:12px;transition:all .2s;}
.fund-row:hover{border-color:rgba(0,217,126,.3);}
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
.aa{background:var(--sf2);border:1px solid var(--bd);border-radius:10px;padding:16px;}
.ac{font-size:13px;color:var(--tx2);line-height:1.8;}
.smb{height:6px;border-radius:3px;margin:8px 0;}
.ssg{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;}
.ss{background:var(--sf2);border-radius:8px;padding:12px;border:1px solid var(--bd);}
.ssl{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--tx3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;}
.ssv{font-size:13px;color:var(--tx);line-height:1.6;}
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
    <div class="pb"><div class="pd"></div>LIVE</div>
  </div>
</div>
<div class="hero">
  <div class="hk">TODAY'S INTELLIGENCE · ${today}</div>
  <h1 class="ht">${editorial.quote.substring(0,45)}...</h1>
  <p class="hd">실제 데이터 기반 브리핑. 뉴스 클릭 시 원문으로 이동, 국내 공시는 DART 원문 연결.</p>
  <div class="hm">
    <span class="hc hc-g">⚡ 추천 딜 ${deals.length}건</span>
    <span class="hc hc-b">📡 실시간 뉴스 ${news.length}건</span>
    <span class="hc hc-o">🇰🇷 국내 공시 ${domestic.length}건</span>
    ${sourcesBadges}
  </div>
</div>
<div class="main">
  <div class="card sc">
    <div class="ch"><div class="ct"><div class="ci ci-g">🎯</div>오늘의 추천 딜</div><div class="cb cb-g">AI SCORED · 클릭가능</div></div>
    <div class="card-body"><div class="dl">${dealsHTML}</div></div>
  </div>
  <div class="card cl">
    <div class="ch"><div class="ct"><div class="ci ci-b">📡</div>글로벌 실시간 뉴스</div><div class="cb cb-b">LIVE · 원문링크</div></div>
    <div class="card-body"><div class="nl">${newsHTML}</div></div>
  </div>
  <div class="card cr">
    <div class="ch"><div class="ct"><div class="ci ci-o">🇰🇷</div>국내 에너지 공시</div><div class="cb cb-dart">OpenDART 실제</div></div>
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
        <div class="ebl">
          <div class="ea">AI</div>
          <div class="et">CLAUDE AI + OpenDART + RSS · ${today} ${now} 자동 생성</div>
        </div>
      </div>
    </div>
  </div>
</div>
<div class="ft">
  <div class="fl2">ENERGY · CVC INTELLIGENCE</div>
  <div class="fr">OpenDART + RSS + NewsAPI + Claude AI<br>${today} ${now} 생성</div>
</div>
<div id="modal" style="display:none"></div>
<script>
const DEALS=${dealsJSON};
const SECTORS=${sectorJSON};
function closeModal(){document.getElementById('modal').style.display='none';document.body.style.overflow='';}
function showModal(h){const m=document.getElementById('modal');m.innerHTML='<div class="mo" onclick="closeModal()"><div class="mb" onclick="event.stopPropagation()">'+h+'</div></div>';m.style.display='block';document.body.style.overflow='hidden';}
function openDeal(i){
  const d=DEALS[i];
  const risks=d.detail.risks.map((r,n)=>'<div class="ri"><div class="rn">'+(n+1)+'</div><div class="rt">'+r+'</div></div>').join('');
  const tags=d.tags.map(t=>'<span class="dtag '+t.c+'">'+t.t+'</span>').join('');
  showModal('<div class="mh"><div><div class="mt">'+d.name+'</div><div style="display:flex;gap:6px;margin-top:6px">'+tags+'</div></div><button class="mc" onclick="closeModal()">✕</button></div><div class="mbd"><div class="ms"><div class="mst">🔬 기술 검증</div><div class="mtx">'+d.detail.tech+'</div></div><div class="ms"><div class="mst">💰 밸류에이션</div><div class="mtx">'+d.detail.valuation+'</div></div><div class="ms"><div class="mst">⚠️ 리스크</div><div class="rl">'+risks+'</div></div><div class="ms"><div class="mst">✅ 액션 아이템</div><div class="ab"><div class="at">'+d.detail.action+'</div></div></div><div class="ms"><div class="mst">🤖 AI 심층 분석</div><div class="aa"><div class="ac">'+(d.detail.aiAnalysis||'분석 없음')+'</div></div></div></div>');
}
function openSector(i){
  const s=SECTORS[i];const r=s.report;
  showModal('<div class="mh"><div><div class="mt">'+s.name+'</div><div style="font-family:JetBrains Mono,monospace;font-size:11px;color:var(--tx3);margin-top:4px">이번달 활성도 '+s.pct+'%</div></div><button class="mc" onclick="closeModal()">✕</button></div><div class="mbd"><div class="smb" style="background:'+s.color+';width:'+s.pct+'%"></div><div class="ms"><div class="mst">📊 섹터 현황</div><div class="mtx">'+r.summary+'</div></div><div class="ms"><div class="mst">🎯 주목할 딜</div><div class="mtx">'+r.topDeals+'</div></div><div class="ssg"><div class="ss"><div class="ssl">📈 6개월 전망</div><div class="ssv">'+r.outlook+'</div></div><div class="ss"><div class="ssl">⚠️ 리스크</div><div class="ssv">'+r.risk+'</div></div></div></div>');
}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
</script>
</body>
</html>`;
}

// ══════════════════════════════════════════════════════
// 메인 실행
// ══════════════════════════════════════════════════════
async function main() {
  console.log('\n🚀 Energy CVC Briefing v5 (실제 데이터) — ' + korDate() + '\n');
  const dataSources = [];

  try {
    // ① 실제 데이터 수집 (병렬)
    console.log('① 실제 데이터 수집 중...');
    const [dartItems, rssArticles, newsAPIArticles, secFilings] = await Promise.all([
      fetchDartFunding(),
      fetchRSSNews(),
      fetchNewsAPI(),
      fetchSECFilings()
    ]);

    console.log('  OpenDART 공시:', dartItems.length + '건');
    console.log('  RSS 뉴스:', rssArticles.length + '건');
    console.log('  NewsAPI:', newsAPIArticles.length + '건');
    console.log('  SEC 공시:', secFilings.length + '건');

    // 데이터 소스 배지
    if (dartItems.length > 0) dataSources.push('OpenDART');
    if (rssArticles.length > 0) dataSources.push('RSS');
    if (newsAPIArticles.length > 0) dataSources.push('NewsAPI');
    if (secFilings.length > 0) dataSources.push('SEC EDGAR');

    // ② 뉴스 합치기 (RSS + NewsAPI)
    const allArticles = [...rssArticles, ...newsAPIArticles].slice(0, 6);

    // ③ Claude AI 분석
    console.log('\n② Claude AI 분석 중...');

    console.log('  뉴스 분석...');
    const news = allArticles.length > 0
      ? safeJSON(await callClaude('You are an energy CVC analyst. Return ONLY valid JSON. No markdown.', buildNewsPrompt(allArticles)))
      : [];

    console.log('  국내 공시 분석...');
    const domestic = dartItems.length > 0
      ? safeJSON(await callClaude('You are an energy CVC analyst. Return ONLY valid JSON. No markdown.', buildDartPrompt(dartItems)))
      : [];

    console.log('  딜 스코어링...');
    const deals = safeJSON(await callClaude(SYS, PROMPTS.deals));

    console.log('  섹터 트렌드...');
    const sector = safeJSON(await callClaude(SYS, PROMPTS.sector));

    console.log('  에디토리얼...');
    const editorial = safeJSON(await callClaude(SYS, PROMPTS.editorial));

    // ④ HTML 생성
    console.log('\n③ HTML 생성...');
    fs.writeFileSync('index.html', buildHTML({
      deals, news, domestic, sector, editorial, dataSources
    }), 'utf8');

    console.log('\n✅ 완료!');
    console.log('  뉴스: ' + news.length + '건 (실제)');
    console.log('  국내 공시: ' + domestic.length + '건 (DART 실제)');
    console.log('  데이터 소스:', dataSources.join(', ') || 'Claude AI');
    console.log('');

  } catch(err) {
    console.error('\n❌ 오류:', err.message);
    process.exit(1);
  }
}

main();

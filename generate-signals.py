"""
Energy CVC Signal Generator
GitHub Actions에서 매일 실행 → data/latest.json 저장

필요한 패키지: feedparser (pip install feedparser)
stdlib만 사용 (requests 불필요)
"""

import re
import json
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    print("⚠ feedparser 없음 — 시뮬레이션 모드로 실행")

import os
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

TODAY    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
TODAY_KR = datetime.now(timezone.utc).strftime("%Y년 %m월 %d일")

# ══════════════════════════════════════════════════════════
# 1. RSS 소스 목록
# ══════════════════════════════════════════════════════════

RSS_SOURCES = [
    {"id":"utilitydive",      "name":"Utility Dive",       "url":"https://www.utilitydive.com/feeds/news/",        "segments":["grid_sw","ess","dc_power"]},
    {"id":"pvmagazine",       "name":"PV Magazine",         "url":"https://www.pv-magazine.com/feed/",              "segments":["ess","hydrogen","forecasting"]},
    {"id":"rechargenews",     "name":"Recharge News",       "url":"https://www.rechargenews.com/feed",              "segments":["ess","marine_fc","hvdc"]},
    {"id":"hydrogeninsight",  "name":"Hydrogen Insight",    "url":"https://www.hydrogeninsight.com/feed",           "segments":["hydrogen","marine_fc"]},
    {"id":"energystoragenews","name":"Energy Storage News", "url":"https://www.energy-storage.news/feed/",          "segments":["ess"]},
    {"id":"offshorewind",     "name":"Offshore Wind Biz",   "url":"https://www.offshorewind.biz/feed/",             "segments":["hvdc","ess"]},
]

# ══════════════════════════════════════════════════════════
# 2. 추적 기업 목록 (alias = 키워드 매칭)
# ══════════════════════════════════════════════════════════

COMPANIES = [
    {"id":"c_gridwiz",    "name":"그리드위즈",     "aliases":["gridwiz","grid wiz"],          "sector":"grid_sw",  "country":"KR","stage":"commercial","type":"Strategic/CVC"},
    {"id":"c_sixtyhertz", "name":"식스티헤르츠",   "aliases":["sixty hertz","60hz","sixtyhertz"],"sector":"grid_sw","country":"KR","stage":"commercial","type":"VC"},
    {"id":"c_vincen",     "name":"빈센",           "aliases":["vincen","vinsen"],             "sector":"marine_fc","country":"KR","stage":"pilot",     "type":"Strategic/CVC"},
    {"id":"c_standard_e", "name":"스탠다드에너지", "aliases":["standard energy"],             "sector":"ess",      "country":"KR","stage":"pilot",     "type":"Strategic/CVC"},
    {"id":"c_hylium",     "name":"하이리움산업",   "aliases":["hylium","하이리움"],           "sector":"hydrogen", "country":"KR","stage":"demo",      "type":"Strategic/CVC"},
    {"id":"c_cs_energy",  "name":"씨에스에너지",   "aliases":["cs energy","씨에스에너지"],    "sector":"ess",      "country":"KR","stage":"commercial","type":"Strategic/CVC"},
    {"id":"c_form_energy","name":"Form Energy",    "aliases":["form energy","formenergy"],    "sector":"ess",      "country":"US","stage":"commercial","type":"Infrastructure/PF"},
    {"id":"c_autogrid",   "name":"AutoGrid",       "aliases":["autogrid","auto grid"],        "sector":"grid_sw",  "country":"US","stage":"scaling",   "type":"Growth"},
    {"id":"c_sunfire",    "name":"Sunfire",         "aliases":["sunfire"],                    "sector":"hydrogen", "country":"DE","stage":"commercial","type":"Infrastructure/PF"},
    {"id":"c_amogy",      "name":"Amogy",           "aliases":["amogy"],                      "sector":"marine_fc","country":"US","stage":"pilot",     "type":"Strategic/CVC"},
    {"id":"c_hysata",     "name":"Hysata",          "aliases":["hysata"],                     "sector":"hydrogen", "country":"AU","stage":"pilot",     "type":"Strategic/CVC"},
    {"id":"c_ceres",      "name":"Ceres Power",     "aliases":["ceres power","ceres"],        "sector":"marine_fc","country":"UK","stage":"commercial","type":"Strategic/CVC"},
    {"id":"c_invinity",   "name":"Invinity Energy", "aliases":["invinity"],                   "sector":"ess",      "country":"UK","stage":"commercial","type":"Growth"},
]

# ══════════════════════════════════════════════════════════
# 3. 이벤트 분류 규칙 (Tier 1~4, 룰 기반)
# ══════════════════════════════════════════════════════════

EVENT_RULES = [
    # Tier 1 — 구체적 상업/기술 액션
    {"kws":["class approval","dnv gl","dnv certified","kpx certified","atex certified"],    "type":"Certification","impact":"Commercial",    "score":85,"tier":1},
    {"kws":["commercial contract","offtake agreement","supply agreement","signed contract"],"type":"Contract",     "impact":"Commercial",    "score":90,"tier":1},
    {"kws":["commissioned","operational","goes live","first delivery","deployed at"],      "type":"Deployment",   "impact":"Commercial",    "score":85,"tier":1},
    # Tier 2 — 검증된 진전
    {"kws":["utility pilot","hyperscaler pilot","shipyard pilot","kepco pilot"],           "type":"Pilot",        "impact":"Technical",     "score":78,"tier":2},
    {"kws":["pilot project","pilot program","field trial","demonstration project"],        "type":"Pilot",        "impact":"Technical",     "score":60,"tier":2},
    {"kws":["series a","series b","series c","series d","raised $","raised €","funding round"],"type":"Financing","impact":"Financing",   "score":80,"tier":2},
    {"kws":["cfo","chief financial officer","vp finance","head of finance"],               "type":"Hiring",       "impact":"Funding Signal","score":75,"tier":2},
    {"kws":["vp sales","vp business development","head of business development"],          "type":"Hiring",       "impact":"Commercial",    "score":65,"tier":2},
    # Tier 3 — 방향성 신호
    {"kws":["strategic partnership","mou signed","joint development","framework agreement"],"type":"Partnership", "impact":"Commercial",    "score":55,"tier":3},
    {"kws":["partnership","mou","collaboration","memorandum"],                             "type":"Partnership",  "impact":"Commercial",    "score":35,"tier":3},
    {"kws":["doe grant","eu grant","government grant","awarded grant","horizon grant"],    "type":"Grant",        "impact":"Policy",        "score":45,"tier":3},
    {"kws":["gigafactory","manufacturing plant","scale-up","opens facility"],              "type":"Expansion",    "impact":"Commercial",    "score":70,"tier":3},
    # Tier 4 — 네거티브 (항상 포함)
    {"kws":["delay","postponed","behind schedule","timeline slips"],                       "type":"Negative",     "impact":"Risk",          "score":0, "tier":4},
    {"kws":["funding shortfall","cost overrun","supply chain issue","struggles to raise"], "type":"Negative",     "impact":"Risk",          "score":0, "tier":4},
]

SEGMENT_KWS = {
    "ess":         ["battery","energy storage","ess","vanadium","iron-air","flow battery"],
    "marine_fc":   ["marine","vessel","ship","fuel cell","dnv","amogy"],
    "grid_sw":     ["vpp","virtual power","demand response","grid software","kepco"],
    "hvdc":        ["hvdc","transmission","cable","offshore wind"],
    "hydrogen":    ["hydrogen","electrolyzer","h2","liquid hydrogen","green hydrogen"],
    "dc_power":    ["data center","hyperscaler","azure","aws","power electronics"],
    "forecasting": ["forecast","prediction","renewable forecast"],
}

# ══════════════════════════════════════════════════════════
# 4. 시그널 스코어 수정자
# ══════════════════════════════════════════════════════════

SCORE_MODS = [
    # 가산
    {"pattern": r"kepco|microsoft|google|amazon|engie|e\.on|hyundai|samsung|hanwha|shell", "delta":+15, "reason":"Named strategic buyer"},
    {"pattern": r"\$[\d,]+[mb]|€[\d,]+[mb]|£[\d,]+[mb]|[\d,]+mwh|[\d,]+gw\b",           "delta":+12, "reason":"Concrete figure"},
    {"pattern": r"q[1-4] 20[2-9]\d|by 202\d|within \d+ month",                           "delta":+8,  "reason":"Concrete timeframe"},
    {"pattern": r"south korea|germany|singapore|rotterdam|busan|incheon",                  "delta":+5,  "reason":"Specific geography"},
    # 감산 (노이즈)
    {"pattern": r"proud to announce|excited to share|pleased to announce",                 "delta":-40, "reason":"Generic PR"},
    {"pattern": r"exploring|in discussions|looking to partner|potential.*partner",         "delta":-45, "reason":"Vague language"},
    {"pattern": r"wins award|recognized as|named.*leader|gartner|frost.*sullivan",         "delta":-35, "reason":"Vanity award"},
    {"pattern": r"keynote|speaks at|panel discussion|webinar|attends.*conference",         "delta":-30, "reason":"Conference only"},
    {"pattern": r"publishes report|whitepaper|new study|research finds",                   "delta":-25, "reason":"Report only"},
    {"pattern": r"rebrands|new logo|launches website|new website",                         "delta":-50, "reason":"Rebranding"},
]

# ══════════════════════════════════════════════════════════
# STEP 1: RSS 수집
# ══════════════════════════════════════════════════════════

def fetch_sources():
    """
    Fetch RSS feeds. Returns (raw_items, source_log).
    source_log records per-source status for the reliability layer.
    """
    print("① RSS 수집 중...")
    raw        = []
    source_log = []   # per-source status — written to JSON for UI transparency

    if not HAS_FEEDPARSER:
        print("  feedparser 없음 — 빈 결과 반환")
        for s in RSS_SOURCES:
            source_log.append({"id":s["id"],"name":s["name"],"url":s["url"],
                "status":"failed","error":"feedparser not installed",
                "items":0,"fetched_at":datetime.now(timezone.utc).isoformat()})
        return raw, source_log

    for s in RSS_SOURCES:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            import socket
            socket.setdefaulttimeout(15)
            feed   = feedparser.parse(s["url"])
            count  = 0
            errors = []

            # feedparser returns status if HTTP was involved
            http_status = getattr(feed, "status", None)
            if http_status and http_status >= 400:
                raise Exception(f"HTTP {http_status}")

            for entry in feed.entries[:20]:
                title   = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")[:500]
                link    = getattr(entry, "link", "")
                date    = _parse_date(entry)
                if not title or title == "[Removed]":
                    continue
                raw.append({
                    "source_id":       s["id"],
                    "source_name":     s["name"],
                    "source_url":      link,
                    "source_segments": s["segments"],
                    "title":           title,
                    "summary":         summary,
                    "published_date":  date,
                    "raw_text":        (title + " " + summary).lower(),
                })
                count += 1

            status = "success" if count > 0 else "partial"
            if count == 0:
                errors.append("Feed returned 0 usable items")
            print(f"  ✓ {s['name']}: {count}건")
            source_log.append({
                "id":s["id"],"name":s["name"],"url":s["url"],
                "status":status,"error":errors[0] if errors else None,
                "items":count,"fetched_at":fetched_at,
            })
        except Exception as ex:
            print(f"  ✗ {s['name']}: {ex}")
            source_log.append({
                "id":s["id"],"name":s["name"],"url":s["url"],
                "status":"failed","error":str(ex),
                "items":0,"fetched_at":fetched_at,
            })

    ok      = sum(1 for s in source_log if s["status"]=="success")
    partial = sum(1 for s in source_log if s["status"]=="partial")
    failed  = sum(1 for s in source_log if s["status"]=="failed")
    print(f"  총 {len(raw)}건 수집 | 소스: {ok}성공 / {partial}부분 / {failed}실패\n")
    return raw, source_log

def _parse_date(entry):
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
    except Exception:
        pass
    return TODAY

# ══════════════════════════════════════════════════════════
# STEP 2: 분류 + 스코어링
# ══════════════════════════════════════════════════════════

def classify(raw_text):
    for rule in EVENT_RULES:
        for kw in rule["kws"]:
            if kw in raw_text:
                return {"type": rule["type"], "impact": rule["impact"],
                        "base_score": rule["score"], "tier": rule["tier"], "matched": kw}
    return {"type":"News", "impact":"Informational", "base_score":15, "tier":5, "matched":None}

def infer_segment(raw_text, source_segments):
    for seg, kws in SEGMENT_KWS.items():
        if any(kw in raw_text for kw in kws):
            return seg
    return source_segments[0] if source_segments else "unknown"

def score(raw_text, base, is_matched):
    s = base + (10 if is_matched else 0)
    applied = []
    for mod in SCORE_MODS:
        if re.search(mod["pattern"], raw_text, re.I):
            s += mod["delta"]
            applied.append({"delta": mod["delta"], "reason": mod["reason"]})
    final = max(0, min(100, round(s)))
    return {
        "signal_strength": final,
        "signal_tier": "high" if final >= 60 else "medium" if final >= 35 else "low",
        "score_breakdown": applied,
        "is_noise": final < 30,
    }

def match_company(raw_text):
    for co in COMPANIES:
        for alias in co["aliases"]:
            if alias.lower() in raw_text:
                return co["id"], co["name"]
    return None, None

def make_id(source_id, title, date):
    key = f"{source_id}:{title}:{date}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]

# ══════════════════════════════════════════════════════════
# STEP 3: 정규화 + 필터
# ══════════════════════════════════════════════════════════

def normalize(raw_items):
    print("② 분류 + 필터링 중...")
    kept, filtered = [], []

    for item in raw_items:
        clf         = classify(item["raw_text"])
        segment     = infer_segment(item["raw_text"], item["source_segments"])
        co_id, co_nm= match_company(item["raw_text"])
        strength    = score(item["raw_text"], clf["base_score"], co_id is not None)
        is_negative = clf["type"] == "Negative"

        event = {
            "id":             make_id(item["source_id"], item["title"], item["published_date"]),
            "title":          item["title"],
            "summary":        item["summary"],
            "event_date":     item["published_date"],
            "source_name":    item["source_name"],
            "source_url":     item["source_url"],
            "event_type":     clf["type"],
            "impact_type":    clf["impact"],
            "matched_rule":   clf["matched"],
            "signal_stage":   "commercial" if clf["type"] in ("Contract","Certification","Deployment") else
                              "early"      if clf["type"] in ("Pilot","Milestone") else "strategic",
            "signal_strength":strength["signal_strength"],
            "signal_tier":    strength["signal_tier"],
            "score_breakdown":strength["score_breakdown"],
            "segment":        segment,
            "company_id":     co_id,
            "company_name":   co_nm or "Unassigned",
            "is_negative":    is_negative,
            "is_noise":       strength["is_noise"] and not is_negative,
        }

        if not strength["is_noise"] or is_negative:
            kept.append(event)
        else:
            penalty = next((m["reason"] for m in strength["score_breakdown"] if m["delta"] < 0), "score < 30")
            filtered.append({**event, "drop_reason": penalty})

    kept.sort(key=lambda e: (-(e["signal_strength"]), e["event_date"]))
    print(f"  유지: {len(kept)}건 | 필터: {len(filtered)}건\n")
    return kept, filtered

# ══════════════════════════════════════════════════════════
# STEP 4: 인사이트 생성 (이벤트만 사용, 수치 생성 금지)
# ══════════════════════════════════════════════════════════

def build_insight(co, events):
    if not events:
        return {
            "observed_facts":  [],
            "matched_pattern": "Insufficient signal. Primary research required.",
            "may_indicate":    ["No pattern without events"],
            "missing":         ["No public events ingested"],
            "confidence":      "Low",
            "next_check":      "Direct outreach recommended.",
        }

    types    = [e["event_type"] for e in events]
    has_cert = "Certification" in types
    has_ctr  = "Contract" in types or "Deployment" in types
    has_hire = "Hiring" in types
    has_plt  = "Pilot" in types
    has_fin  = "Financing" in types
    has_neg  = any(e["is_negative"] for e in events)
    has_grnt = "Grant" in types
    high_ct  = sum(1 for e in events if e["signal_tier"] == "high")

    # 사실만 추출 (이벤트에서)
    facts = [
        f"[{e['event_type']}] {e['title']} — {e['source_name']} ({e['event_date']})"
        for e in events if e["signal_strength"] >= 40
    ][:5]

    # 패턴 매칭
    if has_cert and has_ctr and has_hire:
        pattern  = f"{co['name']}는 규제 인증 + 유틸리티 계약 + 재무 담당자 채용이 동시에 관찰됩니다. 국내 그리드SW/ESS 사례에서 이 조합은 통상 6-12개월 내 시리즈C 라운드 준비의 선행 신호입니다."
        indicate = ["6-12개월 내 Series C 프로세스 가능성","전략투자자(유틸리티/OEM) 앵커 포지션 가능성","해외 BD 채용 공고 모니터링 필요"]
        pid, confidence = "series_c_prep", "Medium-High"
    elif has_cert and has_ctr:
        pattern  = f"{co['name']}는 제3자 인증과 첫 상업 계약을 동시에 확보했습니다. 공급망 진입의 가장 어려운 허들을 넘은 상태입니다. 수익 가시성이 생기기 시작했으나 규모와 독점 여부는 미확인입니다."
        indicate = ["2번째 OEM 고객 확보 병행 가능성","EPC/OEM의 M&A 관심 가능성","계약 램프업 지연 시 브릿지 가능성"]
        pid, confidence = "supply_entry", "Medium"
    elif has_plt and (has_fin or has_ctr):
        pattern  = f"{co['name']}는 파일럿 완료와 전략적 파트너십/파이낸싱이 확인됩니다. 다만 인증 허들 미통과 상태로 모든 상업 신호는 조건부입니다."
        indicate = ["인증 신청 진행 중 가능성","파트너십이 LOI→계약 전환 임박 가능성","인증 완료 전까지 펀딩 브릿지 의존 가능성"]
        pid, confidence = "cert_gate", "Medium-Low"
    elif has_grnt and not has_ctr:
        pattern  = f"{co['name']}의 가장 강한 공개 신호는 정부 그랜트입니다. 그랜트는 기술 방향성을 검증하지만 시장 수요를 확인하지 않습니다. 오프테이커나 전략 구매자 없이는 투자 논거 진전이 어렵습니다."
        indicate = ["TRL 4-6 단계: 정부 검증 단계","상업 파이프라인 미공개 또는 초기 단계"]
        pid, confidence = "grant_only", "Low"
    elif has_fin and has_ctr:
        pattern  = f"{co['name']}는 전략 투자 유치와 상업 계약이 동시 확인됩니다. 외부 자본 검증과 초기 매출 가시성이 함께 나타나는 가장 강한 신호 조합입니다."
        indicate = ["12-18개월 내 매출 램프업 예상","전략투자자의 우선협상권 또는 M&A 옵션 가능성","계약 KPI 달성 시 높은 밸류에이션 후속 라운드 가능"]
        pid, confidence = "strategic_capital", "High"
    elif has_neg:
        pattern  = f"{co['name']}의 최근 신호에서 부정적 이벤트가 감지됩니다. 긍정 신호는 이 리스크 맥락에서 재평가가 필요합니다."
        indicate = ["타임라인 연장 가능성","브릿지 파이낸싱 또는 다운라운드 가능성"]
        pid, confidence = "negative", "Low"
    else:
        pattern  = f"{co['name']}는 현재 {len(events)}건의 이벤트가 집계됩니다. 패턴 확인에 충분한 신호 밀도가 아닙니다. 1차 리서치를 권장합니다."
        indicate = ["초기 단계 또는 공개 정보 제한적","주요 활동이 공개 소스에 아직 미반영 가능성"]
        pid, confidence = "low_density", "Low"

    # 미싱 에비던스
    missing = []
    sector  = co.get("sector","")
    if not has_ctr:
        missing.append("상업 계약 없음 — 모든 수익 가설은 미검증 상태")
    if not has_cert and sector in ("marine_fc","ess","hvdc"):
        missing.append("제3자 인증 없음 — 대부분의 규제 에너지 섹터에서 조달 전제 조건")
    if high_ct == 0:
        missing.append("High 신호 없음 — 현재 이벤트는 방향성만 제공, 확증 아님")
    if co.get("country") == "KR" and not any(
        re.search(r"us|eu|europe|japan|singapore|global|overseas", (e["title"]+" "+e["summary"]).lower())
        for e in events
    ):
        missing.append("해외 레퍼런스 없음 — 글로벌 확장 논거 미검증")
    if has_grnt and not has_ctr:
        missing.append("그랜트 있음 + 오프테이커 없음 — 그랜트 단독 신호는 약함")

    next_map = {
        "series_c_prep":    "해외 VP Sales 채용 공고 또는 2번째 KEPCO급 계약 ACV 모니터링",
        "supply_entry":     "계약 범위(단건 vs. 프레임워크) 확인 및 2번째 OEM RFP 진행 여부",
        "cert_gate":        "인증 신청 공식 제출 여부 확인. 제출됐다면 예상 일정",
        "grant_only":       "그랜트가 상업 공동자금 파트너를 요구하는지 확인 → 구매자 표면화",
        "strategic_capital":"전략투자자의 섹터 포지션 파악. 동 섹터 M&A 이력 확인",
        "negative":         "부정 신호가 프로젝트 레벨(격리) vs. 구조적(시장/기술) 여부 판단",
        "low_density":      "직접 접촉 또는 채널 체크 권장",
    }

    return {
        "observed_facts":  facts,
        "matched_pattern": pattern,
        "pattern_id":      pid,
        "may_indicate":    indicate,
        "missing":         missing,
        "confidence":      confidence,
        "next_check":      next_map.get(pid, "최근 이벤트 검토 후 1차 소스 교차 확인"),
        "event_count":     len(events),
        "high_signal":     high_ct,
        "note":            "기존 이벤트에서만 생성됨. 수치/사실 생성 없음.",
    }

# ══════════════════════════════════════════════════════════
# STEP 5: 브리핑 (Claude API — 없으면 룰 기반 대체)
# ══════════════════════════════════════════════════════════

def call_claude(prompt):
    if not ANTHROPIC_KEY:
        return None
    import json as _json
    body = _json.dumps({
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 800,
        "messages":   [{"role":"user","content":prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = _json.loads(r.read())
            return data["content"][0]["text"]
    except Exception as e:
        print(f"  Claude API 실패: {e}")
        return None

def generate_brief(events):
    print("③ 브리핑 생성 중...")
    high = [e for e in events if e["signal_tier"] == "high"][:8]

    if ANTHROPIC_KEY and high:
        lines = "\n".join(
            f"- [{e['event_type']}] {e['company_name']} ({e['source_name']}): {e['title']}"
            for e in high
        )
        prompt = f"""오늘({TODAY_KR}) 에너지 CVC 투자 브리핑을 4-5문장으로 작성해주세요.

실제 수집된 High 신호:
{lines}

원칙:
- 기사에 없는 수치 생성 금지
- 투자 심사역 내부 메모 톤
- 왜 지금인지, 어떤 패턴인지 중심으로
- 구체적 회사명·언론사 인용"""
        result = call_claude(prompt)
        if result:
            print("  ✓ Claude 브리핑 완료")
            return result.strip()

    # 대체: 룰 기반 브리핑
    if not high:
        return f"{TODAY_KR} 기준 High 신호 없음. 데이터 수집 확인 필요."

    lines = [f"[{e['event_type']}] {e['company_name']}: {e['title']} ({e['source_name']})" for e in high[:3]]
    return (
        f"{TODAY_KR} 주요 신호 {len(high)}건 수집됨. "
        f"상위 신호: {'; '.join(lines[:2])}. "
        f"High 신호 기업: {', '.join(set(e['company_name'] for e in high if e['company_id']))}. "
        f"전체 {len(events)}건 중 노이즈 필터 후 유지."
    )

# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    print(f"\n{'═'*50}")
    print(f"Energy CVC Signal Generator")
    print(f"날짜: {TODAY_KR}")
    print(f"{'═'*50}\n")

    Path("data").mkdir(exist_ok=True)

    # 1. 수집
    raw, source_log = fetch_sources()

    # 2. 분류 + 필터
    kept, filtered = normalize(raw)

    # 3. 기업별 인사이트
    print("③ 기업별 인사이트 생성 중...")
    company_events = {}
    for e in kept:
        if e["company_id"]:
            company_events.setdefault(e["company_id"], []).append(e)

    company_insights = {}
    for co in COMPANIES:
        evs = company_events.get(co["id"], [])
        if evs:
            company_insights[co["id"]] = {
                **co,
                "events": evs,
                "insight": build_insight(co, evs),
                "signal_count": len(evs),
                "high_count": sum(1 for e in evs if e["signal_tier"] == "high"),
            }
    print(f"  인사이트 생성: {len(company_insights)}개 기업\n")

    # 4. 브리핑
    brief = generate_brief(kept)

    # 5. 통계
    stats = {
        "total":       len(kept),
        "high":        sum(1 for e in kept if e["signal_tier"] == "high"),
        "medium":      sum(1 for e in kept if e["signal_tier"] == "medium"),
        "negative":    sum(1 for e in kept if e["is_negative"]),
        "matched":     sum(1 for e in kept if e["company_id"]),
        "filtered_out":len(filtered),
        "companies_with_signals": len(company_insights),
        "by_segment":  {},
        "by_type":     {},
    }
    for e in kept:
        stats["by_segment"][e["segment"]] = stats["by_segment"].get(e["segment"], 0) + 1
        stats["by_type"][e["event_type"]]  = stats["by_type"].get(e["event_type"], 0)  + 1

    # 6. 저장
    output = {
        "date":         TODAY,
        "dateKr":       TODAY_KR,
        "generatedAt":  datetime.now(timezone.utc).isoformat(),
        "brief":        brief,
        "stats":        stats,
        "signals":      kept,
        "filteredOut":  filtered[:20],  # 최근 20개만
        "companies":    company_insights,
        "sources":      [s["name"] for s in RSS_SOURCES],
        "source_log":   source_log,
        "reliability": {
            "sources_total":   len(source_log),
            "sources_ok":      sum(1 for s in source_log if s["status"]=="success"),
            "sources_partial": sum(1 for s in source_log if s["status"]=="partial"),
            "sources_failed":  sum(1 for s in source_log if s["status"]=="failed"),
            "new_events":      len(kept),
            "filtered_out":    len(filtered),
        },
    }

    # latest.json (웹사이트 홈)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 날짜별 아카이브
    with open(f"data/{TODAY}.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # index.json (날짜 목록)
    index_path = Path("data/index.json")
    index = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
        except Exception:
            pass
    if not any(d["date"] == TODAY for d in index):
        index.insert(0, {"date": TODAY, "dateKr": TODAY_KR, "stats": stats})
        index = index[:90]
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    print("✅ 완료!")
    print(f"  신호: {stats['total']}건 | High: {stats['high']} | 필터: {stats['filtered_out']}")
    print(f"  기업 인사이트: {stats['companies_with_signals']}개")
    print(f"  저장: data/latest.json, data/{TODAY}.json\n")

if __name__ == "__main__":
    main()

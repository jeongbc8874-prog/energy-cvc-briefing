#!/usr/bin/env python3
"""
build_company_profile.py  —  Phase 2: Company-Centric Data Model  v2.0
══════════════════════════════════════════════════════════════════════════

입력:  data/latest.json            (generate-signals.py 출력)
       └─ companies{}              {co_id: enrich_company() 출력}
       └─ scorecards{}             {co_id: build_company_scorecard() 출력}
       └─ signals[]                전체 RSS signal 이벤트

입력:  data/company_profiles.json  (전날 누적 프로필, 없으면 신규)

출력:  data/company_profiles.json  (갱신)
       data/archive/profiles_YYYY-MM-DD.json

실행 순서 (daily.yml):
  1. python collect_energy_signals.py   (선택)
  2. python generate-signals.py
  3. python build_company_profile.py    ← 이 파일
  4. git add data/ && git commit && git push

구조 확인 (enrich_company() 반환값 키):
  id, name, sector, country, hq, founded, description, tags,
  known_investors, investor_type, aliases, stage (원본), watchlist_default
  + events[]           : 최대 10개 signal 이벤트
  + insight{}          : build_insight() 출력
  + signal_count, high_count, neg_count, reinforcing, type_counts
  + stage_label        : STAGE_LADDER 추론 결과
  + stage_color, stage_desc
  + pattern{}          : detect_pattern() 출력
  + ttr, ttr_color     : TTR_RULES 추론 결과
  + gaps[]             : [{rule_id, label, severity, memo}]  ← 주의: list
  + critical_gaps (int): gaps 중 severity=="critical" 개수  ← 주의: int
  + high_gaps (int)
  + buyer_activity{}   : {buyer_id: {name, type, count, events[]}}
  + linked_projects[]
  + sector_rulebook{}

데이터 정합성 원칙:
  - 수치(금액)는 소스 명시된 것만 기록. 없으면 "not disclosed".
  - signals[]는 signal id 기준 dedup 누적.
  - critical_gaps[].first_seen 절대 갱신 금지 (최초 감지일 보존).
  - 오늘 signals 없는 회사도 이전 프로필 그대로 보존.
  - funding_history verified=false 기본값. 원문 확인 후 analyst가 true로.
══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── rapidfuzz 선택적 import (없으면 difflib fallback) ─────────────
try:
    from rapidfuzz import fuzz as _fuzz
    def _token_ratio(a: str, b: str) -> float:
        return _fuzz.token_sort_ratio(a, b)
    _FUZZY_ENGINE = "rapidfuzz"
except ImportError:
    def _token_ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    _FUZZY_ENGINE = "difflib"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("profile")

TODAY   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).isoformat()

DATA    = Path("data")
LATEST  = DATA / "latest.json"
DEST    = DATA / "company_profiles.json"
ARCHIVE = DATA / "archive"

FUZZY_THRESHOLD = 85   # 이 점수 이상이면 같은 회사로 간주


# ══════════════════════════════════════════════════════════════════════════
# 1. 회사 이름 정규화 + Fuzzy Matching
#
# 구조:
#   co_intel 키는 이미 generate-signals.py가 매핑한 company_id.
#   하지만 signals[]의 company_name은 자유 텍스트이므로
#   프로필 보강 시 추가 매핑이 필요할 수 있음.
#
# resolve_company_id() 우선순위:
#   1. 정확한 alias 일치 (_ALIAS_TO_ID 테이블)
#   2. Fuzzy match vs. 등록된 모든 alias (threshold 85)
#   3. None (레지스트리 미등록 → 무시)
# ══════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    """소문자 + 특수문자 제거 + 연속 공백 단일화."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[,.\-_/()\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 법인 접미사 제거 (Inc, LLC, Ltd, GmbH, Co. 등)
    s = re.sub(r"\b(inc|llc|ltd|gmbh|co|corp|sa|bv|plc|ag|sas|oy|ab)\b\.?$", "", s).strip()
    return s


# ── 정확한 alias → company_id 매핑 테이블 ─────────────────────────
# generate-signals.py COMPANIES 레지스트리와 동기화.
# 새 회사를 COMPANIES에 추가하면 여기도 추가.
_ALIAS_TO_ID: dict[str, str] = {

    # ── Korean portfolio ───────────────────────────────────────────
    "gridwiz":                      "c_gridwiz",
    "grid wiz":                     "c_gridwiz",
    "그리드위즈":                    "c_gridwiz",
    "gridwiz inc":                  "c_gridwiz",
    "sixty hertz":                  "c_sixtyhertz",
    "60hz":                         "c_sixtyhertz",
    "sixtyhertz":                   "c_sixtyhertz",
    "식스티헤르츠":                  "c_sixtyhertz",
    "vincen":                       "c_vincen",
    "vinsen":                       "c_vincen",
    "빈센":                          "c_vincen",
    "vincen corp":                  "c_vincen",
    "standard energy":              "c_standard_e",
    "스탠다드에너지":                "c_standard_e",
    "standard energy inc":          "c_standard_e",
    "hylium":                       "c_hylium",
    "하이리움":                      "c_hylium",
    "하이리움산업":                  "c_hylium",
    "hylium industries":            "c_hylium",
    "cs energy":                    "c_cs_energy",
    "씨에스에너지":                  "c_cs_energy",
    "cs energy korea":              "c_cs_energy",

    # ── Global benchmarks ─────────────────────────────────────────
    "form energy":                  "c_form_energy",
    "formenergy":                   "c_form_energy",
    "form energy inc":              "c_form_energy",
    "autogrid":                     "c_autogrid",
    "auto grid":                    "c_autogrid",
    "autogrid systems":             "c_autogrid",
    "sunfire":                      "c_sunfire",
    "sunfire gmbh":                 "c_sunfire",
    "amogy":                        "c_amogy",
    "amogy inc":                    "c_amogy",
    "hysata":                       "c_hysata",
    "hysata pty":                   "c_hysata",
    "ceres power":                  "c_ceres",
    "ceres":                        "c_ceres",
    "invinity":                     "c_invinity",
    "invinity energy":              "c_invinity",
    "invinity energy systems":      "c_invinity",

    # ── 에너지 스타트업 (레지스트리 미등록 — 추후 COMPANIES에 추가 가능) ──
    # 아래는 fuzzy match용 보조 테이블. company_id가 없으면 None 반환.
    # 실제 추가 시 generate-signals.py COMPANIES에 먼저 등록 필요.

    # LDES / Battery
    "ambri":                        None,   # 미등록
    "eos energy":                   None,
    "eos energy enterprises":       None,
    "hydrostor":                    None,
    "energy vault":                 None,
    "enervenue":                    None,   # 미등록 — 예시 출력 참고
    "enervenue inc":                None,
    "form factor energy":           None,   # Form Energy 혼동 방지
    "iron air battery":             "c_form_energy",  # 기술 명칭 매핑
    "iron-air":                     "c_form_energy",

    # Green Hydrogen / Electrolyzer
    "electric hydrogen":            None,
    "verdagy":                      None,
    "ohmium":                       None,
    "ohmium international":         None,
    "plug power":                   None,
    "bloom energy":                 None,
    "electrochaea":                 None,
    "h2pro":                        None,
    "enapter":                      None,
    "hysata capillary":             "c_hysata",

    # Grid Software / VPP
    "fluence":                      None,
    "fluence energy":               None,
    "stem":                         None,
    "stem inc":                     None,
    "voltus":                       None,
    "leap energy":                  None,
    "virtual peaker":               None,
    "enbala":                       None,

    # Advanced Nuclear
    "kairos power":                 None,
    "terrapower":                   None,
    "x-energy":                     None,
    "nuscale":                      None,
    "nuscale power":                None,
    "oklo":                         None,
    "terrestrial energy":           None,

    # Geothermal
    "fervo energy":                 None,
    "fervo":                        None,
    "sage geosystems":              None,
    "gradient geothermal":          None,
    "eavor":                        None,

    # Offshore Wind
    "orsted":                       None,
    "vestas":                       None,
    "siemens gamesa":               None,
    "equinor renewables":           None,

    # Marine FC
    "toyota fuel cell":             None,
    "ballard power":                None,
    "ballard power systems":        None,
    "fuelcell energy":              None,
}

# 정규화된 alias → (canonical_alias, company_id) 역인덱스
_NORM_INDEX: dict[str, tuple[str, Optional[str]]] = {
    _norm(alias): (alias, cid)
    for alias, cid in _ALIAS_TO_ID.items()
}

# Fuzzy 비교용 정규화된 alias 리스트 (None 제외 — 실제 등록 회사만)
_REGISTERED_NORMS: list[tuple[str, str]] = [   # [(norm_alias, company_id)]
    (_norm(alias), cid)
    for alias, cid in _ALIAS_TO_ID.items()
    if cid is not None
]


def resolve_company_id(name: str) -> Optional[str]:
    """
    회사명 → company_id.

    우선순위:
      1. 정확한 alias 일치 (정규화 후)
      2. Fuzzy token sort ratio ≥ FUZZY_THRESHOLD vs. 등록 aliases
      3. None

    Note:
      co_intel 딕셔너리는 이미 company_id를 키로 갖고 있으므로
      이 함수는 co_intel 외부(signals.company_name 등)에서만 사용.
    """
    if not name or not name.strip():
        return None

    normed = _norm(name)

    # 1. 정확한 일치
    if normed in _NORM_INDEX:
        return _NORM_INDEX[normed][1]

    # 2. Fuzzy match
    best_score  = 0.0
    best_cid: Optional[str] = None
    for norm_alias, cid in _REGISTERED_NORMS:
        score = _token_ratio(normed, norm_alias)
        if score > best_score:
            best_score = score
            best_cid   = cid

    if best_score >= FUZZY_THRESHOLD:
        log.debug(
            f"Fuzzy match: '{name}' → {best_cid} "
            f"(score={best_score:.0f}, engine={_FUZZY_ENGINE})"
        )
        return best_cid

    return None


def _validate_co(co: dict) -> bool:
    """enrich_company() 출력의 필수 키 존재 여부 확인."""
    required = {"id", "name", "sector", "stage_label", "gaps", "ttr", "events"}
    missing  = required - set(co.keys())
    if missing:
        log.warning(f"  co '{co.get('id','?')}' 필수 키 누락: {missing}")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# 2. Funding 추출기
# ══════════════════════════════════════════════════════════════════════════

_AMOUNT_RE = re.compile(
    r"(\$|€|£|₩)\s*([\d,]+(?:\.\d+)?)\s*"
    r"(billion|million|B(?=\b|\s)|M(?=\b|\s)|억)",
    re.I,
)
_ROUND_MAP: list[tuple[str, str]] = [
    ("series e",        "Series E"),
    ("series d",        "Series D"),
    ("series c",        "Series C"),
    ("series b",        "Series B"),
    ("series a",        "Series A"),
    ("pre-series a",    "Pre-Series A"),
    ("seed round",      "Seed"),
    ("pre-seed",        "Pre-Seed"),
    ("bridge round",    "Bridge"),
    ("convertible note","Convertible Note"),
    ("ipo",             "IPO"),
    ("spac",            "SPAC"),
    ("debt financing",  "Debt"),
]
_LED_RE = re.compile(
    r"(?:led by|lead investor[:\s]+)([\w\s&\-']+?)(?:\s+and\b|\s+with\b|\s*[,.]|$)",
    re.I,
)


def _parse_amount(text: str) -> str:
    m = _AMOUNT_RE.search(text)
    if not m:
        return "not disclosed"
    sym, raw, unit = m.group(1), m.group(2).replace(",", ""), m.group(3).upper()
    try:
        v = float(raw)
    except ValueError:
        return m.group(0).strip()
    if unit in ("BILLION", "B"):
        return f"{sym}{v * 1000:.0f}M"
    if unit == "억":
        return f"₩{v:.0f}억"
    return f"{sym}{v:.0f}M"


def _parse_round(text: str) -> str:
    t = text.lower()
    for kw, label in _ROUND_MAP:
        if kw in t:
            return label
    return "Unknown Round" if _AMOUNT_RE.search(text) else ""


def _parse_lead(text: str) -> str:
    m = _LED_RE.search(text)
    if m:
        cand = m.group(1).strip().rstrip(".,")
        if 1 <= len(cand.split()) <= 6:
            return cand
    return "not disclosed"


def extract_funding_events(signals: list[dict]) -> list[dict]:
    """
    Financing 이벤트 → funding_history 항목.
    (date[:7] + round) 기준 dedup.
    금액 없으면 "not disclosed" — 추정하지 않음.
    """
    out:  list[dict] = []
    seen: set[str]   = set()

    for ev in signals:
        if ev.get("event_type") not in ("Financing", "funding"):
            continue
        date = ev.get("event_date") or ev.get("published_date", "")
        text = (ev.get("title", "") + " " +
                (ev.get("summary") or ev.get("raw_summary", "")))
        rnd  = _parse_round(text)
        if not rnd:
            continue
        key = f"{date[:7]}:{rnd}"
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date":          date,
            "round":         rnd,
            "amount":        _parse_amount(text),
            "lead_investors":[_parse_lead(text)],
            "source":        ev.get("source_name", ""),
            "source_url":    ev.get("source_url", ""),
            "signal_id":     ev.get("id", ""),
            "verified":      False,
            "_note":         (
                "RSS 자동 추출. 금액은 회사 공식 보도자료 또는 "
                "DART/SEC 공시로 반드시 검증 필요."
            ),
        })

    return sorted(out, key=lambda x: x["date"], reverse=True)


# ══════════════════════════════════════════════════════════════════════════
# 3. Gap 병합
#
# 입력: today_raw_gaps = co["gaps"]  (enrich_company() 출력 — list of dict)
#       주의: co["critical_gaps"]는 int(개수)이므로 사용하지 않음.
# ══════════════════════════════════════════════════════════════════════════

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def merge_gaps(
    today_raw_gaps: list[dict],   # [{rule_id, label, severity, memo}]
    prev_gaps:      list[dict],   # 전날 critical_gaps (status 포함)
) -> list[dict]:
    """
    오늘 gaps + 이전 gaps 병합.
      new:        오늘 새로 나타난 gap
      persisting: 이전에도 있었고 오늘도 있는 gap (first_seen 보존)
      resolved:   이전엔 있었는데 오늘 사라진 gap
    """
    prev_active: dict[str, dict] = {
        g["rule_id"]: g
        for g in prev_gaps
        if g.get("status") != "resolved"
    }
    today_ids: set[str] = {g["rule_id"] for g in today_raw_gaps}
    merged: list[dict]  = []

    # 오늘 gaps 처리
    for g in today_raw_gaps:
        rid  = g["rule_id"]
        prev = prev_active.get(rid, {})
        merged.append({
            "rule_id":    rid,
            "gap_type":   g.get("label", rid),
            "severity":   g["severity"],
            "memo":       g["memo"],
            "status":     "persisting" if rid in prev_active else "new",
            "first_seen": prev.get("first_seen", TODAY),   # 최초 감지일 절대 갱신 금지
            "last_seen":  TODAY,
        })

    # resolved: 이전엔 있었지만 오늘 사라진 gap
    for rid, g in prev_active.items():
        if rid not in today_ids:
            merged.append({
                **g,
                "status":      "resolved",
                "last_seen":   g.get("last_seen", TODAY),
                "resolved_on": TODAY,
            })

    merged.sort(key=lambda x: _SEV_ORDER.get(x.get("severity", "low"), 9))
    return merged


# ══════════════════════════════════════════════════════════════════════════
# 4. Buyer Activity 포맷터
# ══════════════════════════════════════════════════════════════════════════

def format_buyer_activity(buyer_dict: dict) -> list[dict]:
    """
    {buyer_id: {name, type, count, events[]}} → 배열.
    signal_strength 내림차순.
    """
    out: list[dict] = []
    for bid, b in buyer_dict.items():
        evts = sorted(
            b.get("events", []),
            key=lambda e: e.get("date", ""),
            reverse=True,
        )
        if not evts:
            continue
        latest = evts[0]
        out.append({
            "buyer_id":         bid,
            "buyer":            b.get("name", ""),
            "type":             b.get("type", ""),
            "interaction_count":b.get("count", 0),
            "latest_date":      latest.get("date", ""),
            "signal_strength":  latest.get("score", 0),
            "recent_signals":   evts[:3],
        })
    return sorted(out, key=lambda x: -x["signal_strength"])


# ══════════════════════════════════════════════════════════════════════════
# 5. Signal Events 병합 (id dedup, 최신순 30개)
# ══════════════════════════════════════════════════════════════════════════

def merge_signal_events(today_evs: list[dict], prev_evs: list[dict]) -> list[dict]:
    prev_ids: set[str] = {e.get("id", "") for e in prev_evs}
    new = [
        {
            "id":              ev.get("id", ""),
            "date":            ev.get("event_date") or ev.get("published_date", ""),
            "title":           ev.get("title", ""),
            "event_type":      ev.get("event_type", ""),
            "signal_tier":     ev.get("signal_tier", "low"),
            "signal_strength": ev.get("signal_strength", 0),
            "source_name":     ev.get("source_name", ""),
            "source_url":      ev.get("source_url", ""),
            "is_negative":     ev.get("is_negative", False),
            "neg_subtype":     ev.get("neg_subtype"),
            "observed_fact":   (
                ev.get("evidence", {}).get("observed_fact")
                or ev.get("title", "")
            ),
        }
        for ev in today_evs
        if ev.get("id", "") not in prev_ids
    ]
    combined = new + prev_evs
    combined.sort(key=lambda e: e.get("date", ""), reverse=True)
    return combined[:30]


# ══════════════════════════════════════════════════════════════════════════
# 6. Next Step 추론
# ══════════════════════════════════════════════════════════════════════════

_STAGE_NEXT: dict[str, dict] = {
    "Lab":              {"next": "Pilot",
                         "gate": "Named third-party pilot or government grant award"},
    "Pilot":            {"next": "Demo / First Commercial",
                         "gate": "Third-party certification (DNV GL / KPX / UL / TÜV)"},
    "Demo":             {"next": "First Commercial",
                         "gate": "Named commercial contract with binding terms"},
    "First Commercial": {"next": "Scaling",
                         "gate": "2+ named customers or project-finance structure"},
    "Scaling":          {"next": "PF-Ready / Exit",
                         "gate": "Project-finance close or strategic M&A"},
    "PF-Ready":         {"next": "Exit / IPO",
                         "gate": "Strategic acquisition or public listing"},
}
_SECTOR_GATE: dict[str, str] = {
    "marine_fc":        "DNV GL or ClassNK Type Approval Certificate",
    "ess":              "UL 9540 / IEC 62619 + grid interconnection agreement",
    "grid_sw":          "KPX / FERC / ENTSO-E market certification + named contract",
    "hydrogen":         "Named industrial offtaker at contracted price (not MOU)",
    "hvdc":             "TÜV / DNV component qualification + OEM supply agreement",
    "dc_power":         "Hyperscaler framework PPA",
    "advanced_nuclear": "NRC license approval",
    "offshore_wind":    "CfD or PPA award + grid connection agreement",
    "geothermal":       "EGS thermal confirmation + grid connection permit",
    "long_duration_storage": "UL 9540 + independent LCOS validation + offtake agreement",
}


def build_next_step(stage: str, sector: str, active_gaps: list[dict]) -> dict:
    path = _STAGE_NEXT.get(stage, _STAGE_NEXT["Lab"]).copy()
    path["current_stage"] = stage
    path["sector_gate"]   = _SECTOR_GATE.get(sector, "Sector-specific gate — see rulebook")
    path["top_blockers"]  = [
        {"gap_type": g["gap_type"], "severity": g["severity"]}
        for g in active_gaps
        if g.get("severity") in ("critical", "high")
        and g.get("status") != "resolved"
    ][:3]
    return path


# ══════════════════════════════════════════════════════════════════════════
# 7. 핵심 빌더
# ══════════════════════════════════════════════════════════════════════════

def build_profile(
    co:        dict,              # enrich_company() 출력 (오늘)
    prev:      dict,              # 전날 CompanyProfile (없으면 {})
    scorecard: dict,              # build_company_scorecard() 출력 (없으면 {})
) -> Optional[dict]:
    """
    요청 스키마를 충족하는 CompanyProfile 생성.
    필수 키 누락 시 None 반환.
    """
    if not _validate_co(co):
        return None

    cid   = co["id"]
    stage = co.get("stage_label", "Lab")

    # ── signals 누적 ──────────────────────────────────────────────
    today_evs  = co.get("events", [])              # max 10 (enrich_company 제한)
    today_ids  = {e["id"] for e in today_evs if "id" in e}
    prev_ids   = set(prev.get("signals", []))
    all_ids    = sorted(prev_ids | today_ids)      # 전체 누적 (날짜 무관)

    # ── signal_events 병합 ────────────────────────────────────────
    signal_events = merge_signal_events(today_evs, prev.get("signal_events", []))

    # ── funding_history ───────────────────────────────────────────
    today_funding = extract_funding_events(today_evs)
    prev_funding  = prev.get("funding_history", [])
    seen_fkeys    = {f"{f['date'][:7]}:{f['round']}" for f in prev_funding}
    merged_funding = list(prev_funding)
    for f in today_funding:
        k = f"{f['date'][:7]}:{f['round']}"
        if k not in seen_fkeys:
            merged_funding.append(f)
            seen_fkeys.add(k)
    merged_funding.sort(key=lambda x: x.get("date", ""), reverse=True)

    # ── critical_gaps (list) ──────────────────────────────────────
    # 주의: co["gaps"]는 list, co["critical_gaps"]는 int
    today_raw_gaps = co.get("gaps", [])
    prev_gaps_list = prev.get("critical_gaps", [])
    critical_gaps  = merge_gaps(today_raw_gaps, prev_gaps_list)
    active_gaps    = [g for g in critical_gaps if g.get("status") != "resolved"]
    missing_ev     = [g["gap_type"] for g in active_gaps]

    # ── buyer_activity ─────────────────────────────────────────────
    buyer_activity = format_buyer_activity(co.get("buyer_activity", {}))

    # ── investment score ───────────────────────────────────────────
    inv_score: dict = {}
    if scorecard:
        inv_score = {
            "total_score":    scorecard.get("total_score", 0),
            "max_possible":   scorecard.get("max_possible", 10),
            "interpretation": scorecard.get("interpretation", "Insufficient"),
            "rationale":      scorecard.get("rationale", ""),
            "as_of":          TODAY,
        }

    # ── ttr slug ──────────────────────────────────────────────────
    ttr_raw  = co.get("ttr", "Long-term")
    ttr_slug = ttr_raw.lower().replace("-", "_").replace(" ", "_")
    # e.g. "Near-term" → "near_term"

    return {
        # ══ 요청 스키마 필수 필드 ════════════════════════════════════
        "company_id":       cid,
        "name":             co.get("name", ""),
        "sector":           co.get("sector", ""),
        "stage":            stage.lower().replace(" ", "_"),
        "stage_label":      stage,
        "country":          co.get("country", ""),
        "description":      co.get("description", ""),
        "funding_history":  merged_funding,
        "signals":          all_ids,
        "critical_gaps":    critical_gaps,         # list (with status/first_seen)
        "buyer_activity":   buyer_activity,
        "missing_evidence": missing_ev,
        "ttr":              ttr_slug,
        "last_updated":     TODAY,
        # ══ 확장 필드 (Investment Memo Generator용) ══════════════════
        "hq":               co.get("hq", ""),
        "founded":          co.get("founded"),
        "tags":             co.get("tags", []),
        "known_investors":  co.get("known_investors", []),
        "investor_type":    co.get("investor_type", ""),
        "signal_count":     len(all_ids),
        "signal_events":    signal_events,
        "high_count":       co.get("high_count", 0),
        "neg_count":        co.get("neg_count", 0),
        "type_counts":      co.get("type_counts", {}),
        "pattern":          co.get("pattern", {}),
        "stage_color":      co.get("stage_color", "#6E6E6E"),
        "stage_desc":       co.get("stage_desc", ""),
        "ttr_color":        co.get("ttr_color", "#6E6E6E"),
        "investment_score": inv_score,
        "next_step":        build_next_step(stage, co.get("sector", ""), active_gaps),
        "sector_rulebook":  co.get("sector_rulebook", {}),
        "insight":          co.get("insight", {}),
        "first_seen":       prev.get("first_seen", TODAY),
        "_data_integrity": (
            "수치(금액, 용량, 일정)는 출처 명시된 것만 기록. "
            "'not disclosed'는 공개 정보 없음을 의미. "
            "외부 인용 전 반드시 원문(보도자료/DART/SEC 공시) 검증 필요."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# 8. 포트폴리오 요약
# ══════════════════════════════════════════════════════════════════════════

def portfolio_summary(profiles: dict[str, dict]) -> dict:
    cos = list(profiles.values())
    stage_dist:  dict[str, int] = {}
    sector_dist: dict[str, int] = {}
    ttr_dist:    dict[str, int] = {}
    for c in cos:
        sl = c.get("stage_label", "Lab");   stage_dist[sl]  = stage_dist.get(sl, 0) + 1
        sc = c.get("sector", "other");      sector_dist[sc] = sector_dist.get(sc, 0) + 1
        tt = c.get("ttr", "long_term");     ttr_dist[tt]    = ttr_dist.get(tt, 0) + 1

    total_crit = sum(
        sum(1 for g in c.get("critical_gaps", [])
            if g.get("severity") == "critical" and g.get("status") != "resolved")
        for c in cos
    )
    high_cos = sorted(
        [c for c in cos if c.get("high_count", 0) >= 1],
        key=lambda c: -(c.get("high_count", 0) * 3
                        + c.get("investment_score", {}).get("total_score", 0)),
    )[:5]
    concern = [
        {"company_id": c["company_id"], "name": c["name"],
         "score": c.get("investment_score", {}).get("total_score", 0),
         "neg_count": c.get("neg_count", 0)}
        for c in cos
        if (c.get("investment_score", {}).get("total_score", 0) < 0
            or c.get("neg_count", 0) >= 2)
    ]
    return {
        "as_of":               TODAY,
        "total_companies":     len(cos),
        "stage_distribution":  stage_dist,
        "sector_distribution": sector_dist,
        "ttr_distribution":    ttr_dist,
        "total_critical_gaps": total_crit,
        "fuzzy_engine":        _FUZZY_ENGINE,
        "high_signal_companies": [
            {"company_id": c["company_id"], "name": c["name"],
             "high_count": c["high_count"], "stage": c["stage_label"],
             "score": c.get("investment_score", {}).get("total_score", 0)}
            for c in high_cos
        ],
        "concern_companies": concern,
    }


# ══════════════════════════════════════════════════════════════════════════
# 9. 예시 출력 (Form Energy & EnerVenue)
#    main() 실행 후 콘솔에 두 회사 프로필 요약 출력.
# ══════════════════════════════════════════════════════════════════════════

def _print_profile_summary(label: str, profile: Optional[dict]) -> None:
    """프로필 핵심 필드를 포맷해서 출력."""
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")

    if profile is None:
        print("  ⚠ 레지스트리 미등록 — company_profiles.json에 없음")
        print(f"  → generate-signals.py의 COMPANIES 배열에 먼저 추가 필요")
        print(f"  → _ALIAS_TO_ID 테이블에 company_id 매핑도 추가 필요")
        return

    cid  = profile.get("company_id", "?")
    name = profile.get("name", "?")
    print(f"  company_id   : {cid}")
    print(f"  name         : {name}")
    print(f"  sector       : {profile.get('sector','?')}")
    print(f"  stage_label  : {profile.get('stage_label','?')}")
    print(f"  ttr          : {profile.get('ttr','?')}")
    print(f"  signal_count : {profile.get('signal_count',0)}")
    print(f"  high_count   : {profile.get('high_count',0)}")
    print(f"  neg_count    : {profile.get('neg_count',0)}")
    print(f"  first_seen   : {profile.get('first_seen','?')}")
    print(f"  last_updated : {profile.get('last_updated','?')}")

    score_d = profile.get("investment_score", {})
    if score_d:
        print(f"  inv_score    : {score_d.get('total_score','?')} / {score_d.get('max_possible','?')}"
              f"  ({score_d.get('interpretation','?')})")

    gaps   = profile.get("critical_gaps", [])
    active = [g for g in gaps if g.get("status") != "resolved"]
    print(f"\n  critical_gaps ({len(active)} active, {len(gaps)-len(active)} resolved):")
    for g in gaps[:5]:
        icon = "●" if g["status"] != "resolved" else "✓"
        days = ""
        if g["status"] == "persisting":
            try:
                d0 = datetime.fromisoformat(g["first_seen"])
                days = f"  ({(datetime.now(timezone.utc)-d0.replace(tzinfo=timezone.utc)).days}d open)"
            except Exception:
                pass
        print(f"    {icon} [{g['severity']:<8}] {g['gap_type']:<40} "
              f"status={g['status']}{days}")

    buyers = profile.get("buyer_activity", [])
    if buyers:
        print(f"\n  buyer_activity ({len(buyers)}):")
        for b in buyers[:3]:
            print(f"    · {b['buyer']:<20} type={b['type']:<12} "
                  f"strength={b['signal_strength']:<3} "
                  f"interactions={b['interaction_count']}")

    funding = profile.get("funding_history", [])
    if funding:
        print(f"\n  funding_history ({len(funding)}):")
        for f in funding[:3]:
            ver = "✓ verified" if f.get("verified") else "⚠ unverified"
            print(f"    · {f['date'][:7]}  {f['round']:<20} "
                  f"{f['amount']:<12} {ver}")

    ns = profile.get("next_step", {})
    if ns:
        print(f"\n  next_step:")
        print(f"    current  : {ns.get('current_stage','?')}")
        print(f"    next     : {ns.get('next','?')}")
        print(f"    gate     : {ns.get('gate','?')}")
        print(f"    blockers : {[b['gap_type'] for b in ns.get('top_blockers',[])]}")

    missing = profile.get("missing_evidence", [])
    if missing:
        print(f"\n  missing_evidence:")
        for m in missing:
            print(f"    ✗ {m}")

    print()


# ══════════════════════════════════════════════════════════════════════════
# 10. MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    log.info(f"build_company_profile.py v2.0  —  {TODAY}")
    log.info(f"Fuzzy engine: {_FUZZY_ENGINE} (threshold={FUZZY_THRESHOLD})")

    if not LATEST.exists():
        log.error(f"{LATEST} 없음. generate-signals.py를 먼저 실행하세요.")
        return

    # ── 입력 로드 ────────────────────────────────────────────────
    latest     = json.loads(LATEST.read_text("utf-8"))
    co_intel   = latest.get("companies", {})    # {co_id: enrich_company() 출력}
    scorecards = latest.get("scorecards", {})   # {co_id: scorecard}
    log.info(f"latest.json: 회사 {len(co_intel)}개, 스코어카드 {len(scorecards)}개")

    # ── 이전 프로필 로드 ─────────────────────────────────────────
    prev_profiles: dict[str, dict] = {}
    if DEST.exists():
        try:
            saved = json.loads(DEST.read_text("utf-8"))
            prev_profiles = saved.get("companies", {})
            log.info(f"이전 프로필: {len(prev_profiles)}개")
        except Exception as ex:
            log.warning(f"이전 프로필 로드 실패 ({ex}) → 신규 시작")

    # ── 프로필 빌드 ──────────────────────────────────────────────
    new_profiles: dict[str, dict] = {}

    for cid, co in co_intel.items():
        try:
            profile = build_profile(
                co        = co,
                prev      = prev_profiles.get(cid, {}),
                scorecard = scorecards.get(cid, {}),
            )
            if profile is None:
                log.warning(f"  ✗ {cid}: build_profile 실패 (필수 키 누락)")
                continue

            new_profiles[cid] = profile

            score  = profile.get("investment_score", {}).get("total_score", "—")
            n_act  = sum(1 for g in profile["critical_gaps"] if g.get("status") != "resolved")
            n_res  = sum(1 for g in profile["critical_gaps"] if g.get("status") == "resolved")
            log.info(
                f"  ✓ {co.get('name','?'):<20} "
                f"stage={profile['stage_label']:<16} "
                f"signals={profile['signal_count']:<3} "
                f"gaps(active={n_act},res={n_res}) "
                f"score={score}"
            )
        except Exception as ex:
            log.error(f"  ✗ {cid} 빌드 실패: {ex}")

    # ── 오늘 signals 없는 회사 → 이전 프로필 보존 ────────────────
    retained = 0
    for cid, prev in prev_profiles.items():
        if cid not in new_profiles:
            new_profiles[cid] = prev
            retained += 1
            log.info(
                f"  · {prev.get('name','?'):<20} "
                f"오늘 signal 없음 → 이전 프로필 유지 "
                f"(last_updated={prev.get('last_updated','?')})"
            )
    if retained:
        log.info(f"  → {retained}개 회사 이전 프로필 보존됨")

    # ── 저장 ─────────────────────────────────────────────────────
    summary = portfolio_summary(new_profiles)
    output  = {
        "date":              TODAY,
        "generated_at":      NOW_ISO,
        "company_count":     len(new_profiles),
        "portfolio_summary": summary,
        "companies":         new_profiles,
    }

    DATA.mkdir(exist_ok=True)
    DEST.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    log.info(f"\n저장: {DEST}  ({len(new_profiles)}개 회사)")

    ARCHIVE.mkdir(exist_ok=True)
    arc = ARCHIVE / f"profiles_{TODAY}.json"
    arc.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")
    log.info(f"아카이브: {arc}")

    # ── 포트폴리오 요약 ───────────────────────────────────────────
    s = summary
    print(f"\n{'═'*60}")
    print(f"  Phase 2 Company Profiles  —  {TODAY}")
    print(f"  {s['total_companies']}개 회사  |  Critical gaps: {s['total_critical_gaps']}")
    print(f"  Stage: {s['stage_distribution']}")
    print(f"  TTR:   {s['ttr_distribution']}")
    if s["high_signal_companies"]:
        top = s["high_signal_companies"][0]
        print(f"  Top:   {top['name']} (HIGH×{top['high_count']}, score={top['score']})")
    if s["concern_companies"]:
        print(f"  ⚠ Concern: {[c['name'] for c in s['concern_companies']]}")

    # ── Form Energy 프로필 출력 ───────────────────────────────────
    _print_profile_summary(
        "Form Energy  (c_form_energy)  — 등록 회사 예시",
        new_profiles.get("c_form_energy"),
    )

    # ── EnerVenue 프로필 출력 (미등록 예시) ──────────────────────
    # EnerVenue는 현재 generate-signals.py COMPANIES에 없으므로
    # co_intel에 포함되지 않음 → None 출력으로 미등록 안내
    enervenue_id = resolve_company_id("EnerVenue")
    _print_profile_summary(
        "EnerVenue  — 미등록 회사 예시 (fuzzy match 결과 포함)",
        new_profiles.get(enervenue_id) if enervenue_id else None,
    )
    log.info(
        f"EnerVenue fuzzy match 결과: '{enervenue_id}' "
        f"(None = 레지스트리 미등록)"
    )
    print("  EnerVenue를 등록하려면:")
    print("  1. generate-signals.py COMPANIES 배열에 추가")
    print("     {'id':'c_enervenue', 'name':'EnerVenue', "
          "'aliases':['enervenue'], 'sector':'ess', ...}")
    print("  2. _ALIAS_TO_ID['enervenue'] = 'c_enervenue'  로 변경")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

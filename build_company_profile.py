#!/usr/bin/env python3
"""
build_company_profile.py  —  Phase 2: Company Intelligence Accumulator  v3.0
══════════════════════════════════════════════════════════════════════════════

입력:
  data/latest.json            generate-signals.py 출력
    .companies{}              {co_id: enrich_company() 출력}
    .scorecards{}             {co_id: scorecard}
    .signals[]                전체 RSS signals
  data/company_profiles.json  전날 누적 프로필

출력:
  data/company_profiles.json  갱신된 누적 프로필
  data/archive/profiles_YYYY-MM-DD.json

핵심 설계:
  1. 누적 우선  — 오늘 signal 없어도 이전 데이터 100% 보존
  2. Gap 고도화 — 7일+ persisting → severity 자동 상향 / 30일+ → long_term_risk 태그
  3. Stage 동적  — 누적 signal 이벤트 타입으로 stage 재추론 (오늘 신호가 없어도)
  4. Funding/Buyer — 전 기간 이벤트에서 추출 + 누적
  5. 정합성     — 수치는 소스 명시된 것만. 없으면 "not disclosed".

enrich_company() 반환 키 (generate-signals.py 실측):
  events[]        최대 10개 오늘 이벤트
  gaps[]          [{rule_id, label, severity, memo}]   ← list
  critical_gaps   int (개수)                           ← 사용 안 함
  buyer_activity  {buyer_id: {name,type,count,events[]}}
  stage_label     STAGE_LADDER 추론 (오늘 이벤트 기준)
  ttr, ttr_color
  pattern{}
  high_count, neg_count, signal_count, type_counts
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── rapidfuzz optional ────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as _rf
    def _ratio(a: str, b: str) -> float:
        return _rf.token_sort_ratio(a, b)
    FUZZY_ENGINE = "rapidfuzz"
except ImportError:
    def _ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    FUZZY_ENGINE = "difflib"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("profile")

TODAY    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO  = datetime.now(timezone.utc).isoformat()
DATA     = Path("data")
LATEST   = DATA / "latest.json"
DEST     = DATA / "company_profiles.json"
ARCHIVE  = DATA / "archive"

FUZZY_THRESHOLD = 85

# Gap 고도화 임계값
GAP_ESCALATE_DAYS  = 7    # 7일+  persisting → severity 한 단계 상향
GAP_CRITICAL_DAYS  = 14   # 14일+ persisting → severity 강제 critical
GAP_LONGTERM_DAYS  = 30   # 30일+ → long_term_risk 태그


# ══════════════════════════════════════════════════════════════════
# 1. 이름 정규화 + Fuzzy Matching
# ══════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[,.\-_/()\[\]]", " ", s)
    s = re.sub(r"\b(inc|llc|ltd|gmbh|co|corp|sa|bv|plc|ag|oy|ab|pty)\b\.?$", "", s)
    return re.sub(r"\s+", " ", s).strip()


_ALIAS_TO_ID: dict[str, Optional[str]] = {
    # ── Korean ──────────────────────────────────────────────────
    "gridwiz": "c_gridwiz", "grid wiz": "c_gridwiz",
    "그리드위즈": "c_gridwiz", "gridwiz inc": "c_gridwiz",
    "sixty hertz": "c_sixtyhertz", "60hz": "c_sixtyhertz",
    "sixtyhertz": "c_sixtyhertz", "식스티헤르츠": "c_sixtyhertz",
    "vincen": "c_vincen", "빈센": "c_vincen", "vinsen": "c_vincen",
    "standard energy": "c_standard_e", "스탠다드에너지": "c_standard_e",
    "hylium": "c_hylium", "하이리움": "c_hylium", "하이리움산업": "c_hylium",
    "cs energy": "c_cs_energy", "씨에스에너지": "c_cs_energy",
    # ── Global registered ───────────────────────────────────────
    "form energy": "c_form_energy", "formenergy": "c_form_energy",
    "form energy inc": "c_form_energy", "iron-air": "c_form_energy",
    "iron air battery": "c_form_energy",
    "autogrid": "c_autogrid", "auto grid": "c_autogrid",
    "autogrid systems": "c_autogrid",
    "sunfire": "c_sunfire", "sunfire gmbh": "c_sunfire",
    "amogy": "c_amogy", "amogy inc": "c_amogy",
    "hysata": "c_hysata", "hysata pty": "c_hysata",
    "ceres power": "c_ceres", "ceres": "c_ceres",
    "invinity": "c_invinity", "invinity energy": "c_invinity",
    "invinity energy systems": "c_invinity",
    # ── Unregistered (None = fuzzy용 보조, 매핑 안 됨) ──────────
    "enervenue": None, "enervenue inc": None,
    "ambri": None, "eos energy": None, "hydrostor": None,
    "energy vault": None, "form factor energy": None,
    "electric hydrogen": None, "verdagy": None, "ohmium": None,
    "plug power": None, "bloom energy": None, "electrochaea": None,
    "fluence": None, "fluence energy": None, "stem inc": None,
    "voltus": None, "leap energy": None,
    "kairos power": None, "terrapower": None, "x-energy": None,
    "nuscale": None, "oklo": None,
    "fervo energy": None, "fervo": None, "sage geosystems": None,
    "orsted": None, "vestas": None, "siemens gamesa": None,
    "ballard power": None, "fuelcell energy": None,
}

_NORM_IDX: dict[str, tuple[str, Optional[str]]] = {
    _norm(k): (k, v) for k, v in _ALIAS_TO_ID.items()
}
_REG_NORMS: list[tuple[str, str]] = [
    (_norm(k), v) for k, v in _ALIAS_TO_ID.items() if v
]


def resolve_id(name: str) -> Optional[str]:
    if not name:
        return None
    n = _norm(name)
    if n in _NORM_IDX:
        return _NORM_IDX[n][1]
    best, best_cid = 0.0, None
    for alias_n, cid in _REG_NORMS:
        s = _ratio(n, alias_n)
        if s > best:
            best, best_cid = s, cid
    return best_cid if best >= FUZZY_THRESHOLD else None


def _validate(co: dict) -> bool:
    missing = {"id", "name", "sector", "stage_label", "gaps", "ttr", "events"} - co.keys()
    if missing:
        log.warning(f"  {co.get('id','?')} 필수 키 누락: {missing}")
    return not missing


# ══════════════════════════════════════════════════════════════════
# 2. 날짜 유틸
# ══════════════════════════════════════════════════════════════════

def _days_since(date_str: str) -> int:
    try:
        d = datetime.fromisoformat(date_str)
        return (datetime.now(timezone.utc) - d.replace(tzinfo=timezone.utc)).days
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════
# 3. Gap 고도화 병합
#    - first_seen 절대 보존
#    - 7일+ persisting → severity 한 단계 상향
#    - 30일+ → long_term_risk: true 태그
#    - resolved: 오늘 없어진 gap
# ══════════════════════════════════════════════════════════════════

_SEV_UP  = {"medium": "high", "high": "critical", "critical": "critical"}
_SEV_ORD = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _escalate_gap(gap: dict) -> dict:
    """
    days_open 기반 severity 자동 상향 규칙:
      7일+  → severity 한 단계 상향 (medium→high, high→critical)
      14일+ → severity 강제 critical (rule ID 무관)
      30일+ → long_term_risk: true 태그
    original_severity는 최초 감지 시 severity를 보존 (상향 이전 값).
    """
    g = dict(gap)
    days = _days_since(g.get("first_seen", TODAY))
    g["days_open"] = days

    # 최초 severity 보존 (한 번만 기록, 이후 덮어쓰지 않음)
    g["original_severity"] = g.get("original_severity", g["severity"])
    original_sev = g["original_severity"]

    if days >= GAP_CRITICAL_DAYS:
        # 14일+ → 무조건 critical
        g["severity"]  = "critical"
        g["escalated"] = True
        g["escalation_reason"] = f"{days}d persisting → forced critical (≥{GAP_CRITICAL_DAYS}d)"
    elif days >= GAP_ESCALATE_DAYS and g["severity"] != "critical":
        # 7일+ → 한 단계 상향
        g["severity"]  = _SEV_UP.get(original_sev, original_sev)
        g["escalated"] = True
        g["escalation_reason"] = f"{days}d persisting → {g['severity']} (≥{GAP_ESCALATE_DAYS}d)"
    else:
        g["escalated"] = False
        g["escalation_reason"] = None

    g["long_term_risk"] = days >= GAP_LONGTERM_DAYS
    return g


def merge_gaps(today_raw: list[dict], prev_gaps: list[dict]) -> list[dict]:
    """
    today_raw : enrich_company()의 gaps[] — [{rule_id, label, severity, memo}]
    prev_gaps : 전날 critical_gaps[] (status/first_seen 포함)
    """
    prev_active = {
        g["rule_id"]: g for g in prev_gaps if g.get("status") != "resolved"
    }
    today_ids = {g["rule_id"] for g in today_raw}
    merged: list[dict] = []

    for g in today_raw:
        rid  = g["rule_id"]
        prev = prev_active.get(rid, {})
        entry = {
            "rule_id":           rid,
            "gap_type":          g.get("label", rid),
            "severity":          g["severity"],
            "original_severity": prev.get("original_severity", g["severity"]),
            "memo":              g["memo"],
            "status":            "persisting" if rid in prev_active else "new",
            "first_seen":        prev.get("first_seen", TODAY),  # 절대 갱신 금지
            "last_seen":         TODAY,
        }
        merged.append(_escalate_gap(entry))

    # resolved
    for rid, g in prev_active.items():
        if rid not in today_ids:
            entry = {**g, "status": "resolved", "resolved_on": TODAY}
            merged.append(entry)

    merged.sort(key=lambda x: _SEV_ORD.get(x.get("severity", "low"), 9))
    return merged


# ══════════════════════════════════════════════════════════════════
# 4. Stage 동적 재추론
#    오늘 enrich_company() 결과 + 누적 signal_events 전체 타입으로
#    stage를 재추론. 오늘 signal이 없어도 이전 데이터로 유지.
# ══════════════════════════════════════════════════════════════════

_STAGE_LADDER = [
    ("PF-Ready",         "#0F4C75", {"Contract", "Deployment"},
     "Multiple commercial deployments or project-financed asset."),
    ("Scaling",          "#0A6640", {"Contract", "Deployment"},
     "Commercial contracts in place. Revenue visible. Second buyer emerging."),
    ("First Commercial", "#1A56DB", {"Contract", "Deployment"},
     "First binding commercial agreement or live deployment confirmed."),
    ("Demo",             "#5B21B6", {"Certification"},
     "Technical gate cleared. Commercial conversion not yet confirmed."),
    ("Pilot",            "#7D4E00", {"Pilot", "Partnership"},
     "Third-party validation in progress. No commercial gate cleared."),
    ("Lab",              "#6E6E6E", set(),
     "Limited public signal. Primary research required."),
]

_TTR_RULES = [
    ("near_term",   "#C0392B",
     lambda sl, ph, hc: sl in ("PF-Ready", "Scaling")
         or (sl == "First Commercial" and ph in ("series_c_prep", "commercial_breakout") and hc >= 2)),
    ("mid_term",    "#7D4E00",
     lambda sl, ph, hc: sl in ("First Commercial", "Demo", "Pilot")
         and ph not in ("grant_dependent", "low_density", "negative_flags")),
    ("long_term",   "#6E6E6E", lambda sl, ph, hc: True),
]

_PATTERN_RULES = [
    ("series_c_prep",      lambda t, h, n: "Certification" in t and ("Contract" in t or "Pilot" in t) and "Hiring" in t and h >= 2 and n == 0),
    ("commercial_breakout",lambda t, h, n: ("Contract" in t or "Deployment" in t) and h >= 2 and n == 0),
    ("cert_gate",          lambda t, h, n: "Certification" in t and "Contract" not in t and "Deployment" not in t and n == 0),
    ("strategic_momentum", lambda t, h, n: "Partnership" in t and ("Pilot" in t or "Financing" in t) and n == 0),
    ("fundraise_signal",   lambda t, h, n: "Hiring" in t and "Financing" not in t and n == 0),
    ("grant_dependent",    lambda t, h, n: "Grant" in t and "Contract" not in t and "Pilot" not in t and "Certification" not in t),
    ("negative_flags",     lambda t, h, n: n >= 1),
    ("low_density",        lambda t, h, n: True),
]


def _infer_stage_from_events(all_events: list[dict]) -> tuple[str, str]:
    """
    누적 이벤트 전체 타입 + high signal 개수로 stage/color 추론.

    추가 규칙 (high signal 자동 승급):
      high >= 3  AND  현재 stage가 Lab  → 최소 Pilot으로 승급
      high >= 5  AND  현재 stage가 Pilot → 최소 Demo으로 승급
    이 규칙은 type-based 추론 결과에 추가로 적용되며,
    이미 더 높은 stage가 추론된 경우에는 적용하지 않음.
    """
    types      = {e.get("event_type", "") for e in all_events}
    high_count = sum(1 for e in all_events if e.get("signal_tier") == "high")

    # 1단계: event type 기반 STAGE_LADDER 추론
    inferred_label  = "Lab"
    inferred_color  = "#6E6E6E"
    for label, color, req, _ in _STAGE_LADDER:
        if req and not (req & types):
            continue
        inferred_label = label
        inferred_color = color
        break

    # 2단계: high signal 개수 기반 자동 승급
    _rank = {"Lab":0,"Pilot":1,"Demo":2,"First Commercial":3,"Scaling":4,"PF-Ready":5}
    _by_rank = {v:k for k,v in _rank.items()}
    _colors  = {"Lab":"#6E6E6E","Pilot":"#7D4E00","Demo":"#5B21B6",
                "First Commercial":"#1A56DB","Scaling":"#0A6640","PF-Ready":"#0F4C75"}

    current_rank = _rank.get(inferred_label, 0)
    min_rank     = current_rank

    if high_count >= 3:
        min_rank = max(min_rank, _rank["Pilot"])    # Lab → 최소 Pilot
    if high_count >= 5:
        min_rank = max(min_rank, _rank["Demo"])     # Pilot → 최소 Demo

    if min_rank > current_rank:
        inferred_label = _by_rank[min_rank]
        inferred_color = _colors[inferred_label]

    return inferred_label, inferred_color


def _infer_pattern(all_events: list[dict]) -> str:
    types = {e.get("event_type", "") for e in all_events}
    high  = sum(1 for e in all_events if e.get("signal_tier") == "high")
    neg   = sum(1 for e in all_events if e.get("is_negative"))
    for pid, fn in _PATTERN_RULES:
        if fn(types, high, neg):
            return pid
    return "low_density"


def _infer_ttr(
    stage:       str,
    pattern:     str,
    high_count:  int,
    active_gaps: list[dict] | None = None,
    first_seen:  str               = "",
) -> tuple[str, str]:
    """
    TTR을 stage + pattern + high_count + gap 압박 + 누적 기간으로 종합 계산.

    기본 규칙 (_TTR_RULES):
      near_term : PF-Ready / Scaling,
                  또는 First Commercial + 강한 패턴 + high >= 2
      mid_term  : First Commercial / Demo / Pilot + 긍정적 패턴
      long_term : 나머지

    패널티 조정:
      active critical gap >= 2   → TTR 한 단계 하향 (near→mid, mid→long)
      long_term_risk gap 존재     → TTR 한 단계 하향
      누적 기간 < 14일            → long_term 강제 (데이터 부족)
    """
    gaps = active_gaps or []

    # 기본 TTR
    base_ttr = "long_term"
    for slug, color, fn in _TTR_RULES:
        if fn(stage, pattern, high_count):
            base_ttr = slug
            break

    # 패널티 계산
    penalty = 0
    crit_gaps    = sum(1 for g in gaps if g.get("severity") == "critical" and g.get("status") != "resolved")
    has_ltr      = any(g.get("long_term_risk") for g in gaps if g.get("status") != "resolved")
    tracking_days = _days_since(first_seen) if first_seen else 0

    if tracking_days < 14:
        return "long_term", "#6E6E6E"   # 데이터 부족 → 판단 유보

    if crit_gaps >= 2:
        penalty += 1
    if has_ltr:
        penalty += 1

    _ttr_order  = ["near_term", "mid_term", "long_term"]
    _ttr_colors = {"near_term": "#C0392B", "mid_term": "#7D4E00", "long_term": "#6E6E6E"}

    idx = _ttr_order.index(base_ttr) if base_ttr in _ttr_order else 2
    idx = min(idx + penalty, len(_ttr_order) - 1)

    final = _ttr_order[idx]
    return final, _ttr_colors[final]


# ══════════════════════════════════════════════════════════════════
# 5. Signal Events 누적 (id dedup, 최신순 50개)
# ══════════════════════════════════════════════════════════════════

def _to_event_row(ev: dict) -> dict:
    return {
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
        "observed_fact":   (ev.get("evidence", {}) or {}).get("observed_fact") or ev.get("title", ""),
    }


def merge_events(today_evs: list[dict], prev_evs: list[dict]) -> list[dict]:
    prev_ids = {e.get("id", "") for e in prev_evs}
    new_rows = [_to_event_row(e) for e in today_evs if e.get("id", "") not in prev_ids]
    combined = new_rows + prev_evs
    combined.sort(key=lambda e: e.get("date", ""), reverse=True)
    return combined[:50]


# ══════════════════════════════════════════════════════════════════
# 6. Funding 추출 (적극적 패턴 매칭)
# ══════════════════════════════════════════════════════════════════

_AMT_RE = re.compile(
    r"(\$|€|£|₩)\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B(?=\b)|M(?=\b)|억)",
    re.I,
)
_ROUND_MAP = [
    ("series e","Series E"),("series d","Series D"),("series c","Series C"),
    ("series b","Series B"),("series a","Series A"),("pre-series a","Pre-Series A"),
    ("seed round","Seed"),("pre-seed","Pre-Seed"),("bridge round","Bridge"),
    ("convertible note","Convertible Note"),("ipo","IPO"),("spac","SPAC"),
    ("debt financing","Debt"),("strategic investment","Strategic"),
]
_LED_RE = re.compile(
    r"(?:led by|lead investor[:\s]+)([\w\s&\-']+?)(?:\s+and\b|\s*[,.]|$)", re.I
)


def _amt(text: str) -> str:
    m = _AMT_RE.search(text)
    if not m:
        return "not disclosed"
    sym, raw, unit = m.group(1), m.group(2).replace(",", ""), m.group(3).upper()
    try:
        v = float(raw)
        if unit in ("BILLION", "B"):
            return f"{sym}{v*1000:.0f}M"
        if unit == "억":
            return f"₩{v:.0f}억"
        return f"{sym}{v:.0f}M"
    except ValueError:
        return m.group(0).strip()


def _round(text: str) -> str:
    t = text.lower()
    for kw, label in _ROUND_MAP:
        if kw in t:
            return label
    return "Unknown Round" if _AMT_RE.search(text) else ""


def _lead(text: str) -> str:
    m = _LED_RE.search(text)
    if m:
        c = m.group(1).strip().rstrip(".,")
        if 1 <= len(c.split()) <= 6:
            return c
    return "not disclosed"


def extract_funding(events: list[dict]) -> list[dict]:
    """전체 이벤트(오늘 + 누적)에서 Financing 항목 추출."""
    out: list[dict] = []
    seen: set[str]  = set()
    for ev in events:
        if ev.get("event_type") not in ("Financing", "funding"):
            continue
        date = ev.get("date") or ev.get("event_date") or ev.get("published_date", "")
        text = ev.get("title", "") + " " + (ev.get("observed_fact") or "")
        rnd  = _round(text)
        if not rnd:
            continue
        key = f"{date[:7]}:{rnd}"
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date":          date,
            "round":         rnd,
            "amount":        _amt(text),
            "lead_investors":[_lead(text)],
            "source":        ev.get("source_name", ""),
            "source_url":    ev.get("source_url", ""),
            "signal_id":     ev.get("id", ""),
            "verified":      False,
            "_note":         "RSS 자동 추출. 원문(보도자료/DART/SEC) 검증 필요.",
        })
    return sorted(out, key=lambda x: x["date"], reverse=True)


def merge_funding(new: list[dict], prev: list[dict]) -> list[dict]:
    seen = {f"{f['date'][:7]}:{f['round']}" for f in prev}
    merged = list(prev)
    for f in new:
        k = f"{f['date'][:7]}:{f['round']}"
        if k not in seen:
            merged.append(f)
            seen.add(k)
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)
    return merged


# ══════════════════════════════════════════════════════════════════
# 7. Buyer Activity 누적
#    오늘 buyer_activity dict + 이전 누적 배열 병합
# ══════════════════════════════════════════════════════════════════

def merge_buyer_activity(today_dict: dict, prev_list: list[dict]) -> list[dict]:
    """
    today_dict: {buyer_id: {name, type, count, events[]}}  ← enrich_company()
    prev_list:  이전 buyer_activity 배열
    """
    merged: dict[str, dict] = {}

    # 이전 데이터 로드
    for b in prev_list:
        bid = b.get("buyer_id", b.get("buyer", ""))
        if bid:
            merged[bid] = dict(b)

    # 오늘 데이터 병합
    for bid, b in today_dict.items():
        today_evts = sorted(b.get("events", []), key=lambda e: e.get("date", ""), reverse=True)
        if bid in merged:
            # 기존 이벤트 dedup 병합
            prev_titles = {e.get("title", "") for e in merged[bid].get("recent_signals", [])}
            new_evts = [e for e in today_evts if e.get("title", "") not in prev_titles]
            merged[bid]["recent_signals"] = (new_evts + merged[bid].get("recent_signals", []))[:5]
            merged[bid]["interaction_count"] = merged[bid].get("interaction_count", 0) + b.get("count", 0)
            if today_evts:
                latest = today_evts[0]
                if latest.get("score", 0) >= merged[bid].get("signal_strength", 0):
                    merged[bid]["latest_date"]     = latest.get("date", "")
                    merged[bid]["signal_strength"]  = latest.get("score", 0)
                    merged[bid]["interaction_type"] = latest.get("event_type", "")
        else:
            if not today_evts:
                continue
            latest = today_evts[0]
            merged[bid] = {
                "buyer_id":         bid,
                "buyer":            b.get("name", ""),
                "type":             b.get("type", ""),
                "interaction_count":b.get("count", 0),
                "latest_date":      latest.get("date", ""),
                "signal_strength":  latest.get("score", 0),
                "interaction_type": latest.get("event_type", ""),
                "recent_signals":   today_evts[:3],
                "first_seen":       TODAY,
            }

    result = sorted(merged.values(), key=lambda x: -x.get("signal_strength", 0))
    return result


# ══════════════════════════════════════════════════════════════════
# 8. 누적 통계 계산
# ══════════════════════════════════════════════════════════════════

def _calc_cumulative_stats(all_events: list[dict]) -> dict:
    total      = len(all_events)
    high       = sum(1 for e in all_events if e.get("signal_tier") == "high")
    neg        = sum(1 for e in all_events if e.get("is_negative"))
    type_counts: dict[str, int] = {}
    for e in all_events:
        t = e.get("event_type", "other")
        type_counts[t] = type_counts.get(t, 0) + 1

    # 최근 30일 신호 수
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    recent = sum(1 for e in all_events if e.get("date", "") >= cutoff)

    # signal velocity: 주당 평균
    if all_events:
        oldest = min(e.get("date", TODAY) for e in all_events)
        try:
            d0    = datetime.fromisoformat(oldest)
            weeks = max(1, (datetime.now(timezone.utc) - d0.replace(tzinfo=timezone.utc)).days / 7)
            velocity = round(total / weeks, 1)
        except Exception:
            velocity = 0.0
    else:
        velocity = 0.0

    return {
        "total":           total,
        "high":            high,
        "negative":        neg,
        "recent_30d":      recent,
        "velocity_per_week": velocity,
        "type_counts":     type_counts,
    }


# ══════════════════════════════════════════════════════════════════
# 9. Next Step 추론
# ══════════════════════════════════════════════════════════════════

_STAGE_NEXT = {
    "Lab":              {"next": "Pilot",                  "gate": "Named third-party pilot or government grant award"},
    "Pilot":            {"next": "Demo / First Commercial","gate": "Third-party certification (DNV GL / KPX / UL / TÜV)"},
    "Demo":             {"next": "First Commercial",       "gate": "Named commercial contract with binding terms"},
    "First Commercial": {"next": "Scaling",                "gate": "2+ named customers or project-finance structure"},
    "Scaling":          {"next": "PF-Ready / Exit",        "gate": "Project-finance close or strategic M&A"},
    "PF-Ready":         {"next": "Exit / IPO",             "gate": "Strategic acquisition or public listing"},
}
_SECTOR_GATE = {
    "marine_fc": "DNV GL or ClassNK Type Approval Certificate",
    "ess":       "UL 9540 / IEC 62619 + grid interconnection agreement",
    "grid_sw":   "KPX / FERC / ENTSO-E market certification + named contract",
    "hydrogen":  "Named industrial offtaker at contracted price (not MOU)",
    "hvdc":      "TÜV / DNV component qualification + OEM supply agreement",
    "dc_power":  "Hyperscaler framework PPA",
    "advanced_nuclear": "NRC license approval",
    "offshore_wind":    "CfD or PPA award + grid connection agreement",
    "geothermal":       "EGS thermal confirmation + grid connection permit",
}


def build_next_step(stage: str, sector: str, active_gaps: list[dict]) -> dict:
    """
    top_blockers 선택 기준 (severity + persisting 기간 복합 점수):
      score = sev_weight + persistence_bonus + ltr_bonus
      sev_weight      : critical=100, high=50, medium=20
      persistence_bonus: days_open * 0.5  (오래된 gap일수록 우선)
      ltr_bonus       : long_term_risk이면 +30
    상위 3개만 포함.
    """
    def _blocker_score(g: dict) -> float:
        sev_w = {"critical": 100, "high": 50, "medium": 20}.get(g.get("severity", "low"), 0)
        days  = g.get("days_open", 0)
        ltr   = 30 if g.get("long_term_risk") else 0
        return sev_w + days * 0.5 + ltr

    path = _STAGE_NEXT.get(stage, _STAGE_NEXT["Lab"]).copy()
    path["current_stage"] = stage
    path["sector_gate"]   = _SECTOR_GATE.get(sector, "Sector-specific gate — see rulebook")

    candidates = [
        g for g in active_gaps
        if g.get("severity") in ("critical", "high", "medium")
        and g.get("status") != "resolved"
    ]
    candidates.sort(key=_blocker_score, reverse=True)

    path["top_blockers"] = [
        {
            "gap_type":        g["gap_type"],
            "severity":        g["severity"],
            "original_severity": g.get("original_severity", g["severity"]),
            "days_open":       g.get("days_open", 0),
            "long_term_risk":  g.get("long_term_risk", False),
            "escalated":       g.get("escalated", False),
            "escalation_reason": g.get("escalation_reason"),
            "blocker_score":   round(_blocker_score(g), 1),
        }
        for g in candidates[:3]
    ]
    return path


# ══════════════════════════════════════════════════════════════════
# 10. 핵심 빌더
# ══════════════════════════════════════════════════════════════════

def build_profile(co: dict, prev: dict, scorecard: dict) -> Optional[dict]:
    """
    co        : enrich_company() 출력 (오늘)
    prev      : 전날 CompanyProfile (없으면 {})
    scorecard : build_company_scorecard() 출력 (없으면 {})
    """
    if not _validate(co):
        return None

    cid    = co["id"]
    sector = co.get("sector", "")

    # ── 1. Signal Events 누적 ──────────────────────────────────
    today_evs     = co.get("events", [])
    prev_evs      = prev.get("signal_events", [])
    all_evs       = merge_events(today_evs, prev_evs)

    # signal id 누적 (전체)
    today_ids = {e["id"] for e in today_evs if "id" in e}
    prev_ids  = set(prev.get("signals", []))
    all_ids   = sorted(prev_ids | today_ids)

    # ── 2. 누적 통계 ──────────────────────────────────────────
    stats = _calc_cumulative_stats(all_evs)

    # ── 3. Stage 동적 재추론 (누적 이벤트 + high signal 승급) ──
    cum_stage, cum_stage_color = _infer_stage_from_events(all_evs)
    cum_pattern_id = _infer_pattern(all_evs)

    # 오늘 enrich_company()의 stage_label도 참고 (더 높으면 채택)
    today_stage = co.get("stage_label", "Lab")
    _rank = {"Lab":0,"Pilot":1,"Demo":2,"First Commercial":3,"Scaling":4,"PF-Ready":5}
    if _rank.get(today_stage, 0) > _rank.get(cum_stage, 0):
        cum_stage, cum_stage_color = today_stage, co.get("stage_color", cum_stage_color)

    # stage 변화 이력
    stage_history = list(prev.get("stage_history", []))
    last_stage = stage_history[-1]["stage"] if stage_history else None
    if cum_stage != last_stage:
        stage_history.append({
            "stage":       cum_stage,
            "date":        TODAY,
            "from_stage":  last_stage or "unknown",
            "auto":        True,
            "trigger":     f"high_signals={stats['high']}, types={list({e.get('event_type','') for e in all_evs[:5]})}",
        })

    # ── 4. Gaps 고도화 병합 ───────────────────────────────────
    today_raw_gaps = co.get("gaps", [])
    prev_gaps      = prev.get("critical_gaps", [])
    critical_gaps  = merge_gaps(today_raw_gaps, prev_gaps)
    active_gaps    = [g for g in critical_gaps if g.get("status") != "resolved"]
    missing_ev     = [g["gap_type"] for g in active_gaps]

    # gap 요약
    gap_summary = {
        "total_active":    len(active_gaps),
        "critical":        sum(1 for g in active_gaps if g.get("severity") == "critical"),
        "high":            sum(1 for g in active_gaps if g.get("severity") == "high"),
        "escalated":       sum(1 for g in active_gaps if g.get("escalated")),
        "long_term_risks": sum(1 for g in active_gaps if g.get("long_term_risk")),
        "forced_critical": sum(1 for g in active_gaps
                               if g.get("days_open", 0) >= GAP_CRITICAL_DAYS
                               and g.get("original_severity") != "critical"),
    }

    # ── 5b. TTR — gap 압박 + 누적 기간 반영 ─────────────────
    cum_ttr, cum_ttr_color = _infer_ttr(
        stage       = cum_stage,
        pattern     = cum_pattern_id,
        high_count  = stats["high"],
        active_gaps = active_gaps,
        first_seen  = prev.get("first_seen", TODAY),
    )

    # ── 5. Buyer Activity 누적 ────────────────────────────────
    buyer_activity = merge_buyer_activity(
        co.get("buyer_activity", {}),
        prev.get("buyer_activity", []),
    )

    # ── 6. Funding History 누적 (누적 이벤트 전체에서 추출) ───
    new_funding = extract_funding(all_evs)
    funding_history = merge_funding(new_funding, prev.get("funding_history", []))

    # ── 7. Investment Score ───────────────────────────────────
    inv_score: dict = {}
    if scorecard:
        inv_score = {
            "total_score":    scorecard.get("total_score", 0),
            "max_possible":   scorecard.get("max_possible", 10),
            "interpretation": scorecard.get("interpretation", "Insufficient"),
            "rationale":      scorecard.get("rationale", ""),
            "as_of":          TODAY,
        }

    # ── 8. Insufficient Signal 명확 표시 ─────────────────────
    has_signal = stats["total"] > 0
    signal_quality = (
        "strong"       if stats["high"] >= 3 else
        "building"     if stats["high"] >= 1 else
        "early"        if stats["total"] >= 3 else
        "insufficient"
    )

    return {
        # ── 기본 정보 ──────────────────────────────────────────
        "company_id":    cid,
        "name":          co.get("name", ""),
        "sector":        sector,
        "stage":         cum_stage.lower().replace(" ", "_"),
        "stage_label":   cum_stage,
        "stage_color":   cum_stage_color,
        "stage_desc":    co.get("stage_desc", ""),
        "stage_history": stage_history,
        "country":       co.get("country", ""),
        "hq":            co.get("hq", ""),
        "founded":       co.get("founded"),
        "description":   co.get("description", ""),
        "tags":          co.get("tags", []),
        "known_investors":co.get("known_investors", []),
        "investor_type": co.get("investor_type", ""),
        # ── 누적 Signals ───────────────────────────────────────
        "signals":       all_ids,
        "signal_count":  len(all_ids),
        "signal_events": all_evs,
        "signal_stats":  stats,
        "signal_quality":signal_quality,
        "has_signal":    has_signal,
        # ── Gap 고도화 ─────────────────────────────────────────
        "critical_gaps": critical_gaps,
        "gap_summary":   gap_summary,
        "missing_evidence": missing_ev,
        # ── Buyer + Funding ────────────────────────────────────
        "buyer_activity":   buyer_activity,
        "funding_history":  funding_history,
        # ── Stage + TTR (동적) ─────────────────────────────────
        "ttr":           cum_ttr,
        "ttr_color":     cum_ttr_color,
        "pattern_id":    cum_pattern_id,
        "pattern":       co.get("pattern", {}),
        # ── Investment Score ───────────────────────────────────
        "investment_score": inv_score,
        # ── Next Step ──────────────────────────────────────────
        "next_step":     build_next_step(cum_stage, sector, active_gaps),
        # ── Sector Rulebook ────────────────────────────────────
        "sector_rulebook": co.get("sector_rulebook", {}),
        # ── 메타 ──────────────────────────────────────────────
        "last_updated":  TODAY,
        "first_seen":    prev.get("first_seen", TODAY),
        "_data_integrity": (
            "수치(금액, 용량, 일정)는 출처 명시된 것만 기록. "
            "'not disclosed'는 공개 정보 없음. "
            "외부 인용 전 원문(보도자료/DART/SEC) 검증 필요."
        ),
    }


# ══════════════════════════════════════════════════════════════════
# 11. 포트폴리오 요약
# ══════════════════════════════════════════════════════════════════

def portfolio_summary(profiles: dict[str, dict]) -> dict:
    cos = list(profiles.values())
    stage_dist:  dict[str, int] = {}
    sector_dist: dict[str, int] = {}
    ttr_dist:    dict[str, int] = {}
    quality_dist:dict[str, int] = {}

    for c in cos:
        sl = c.get("stage_label", "Lab")
        stage_dist[sl]  = stage_dist.get(sl, 0) + 1
        sc = c.get("sector", "other")
        sector_dist[sc] = sector_dist.get(sc, 0) + 1
        tt = c.get("ttr", "long_term")
        ttr_dist[tt]    = ttr_dist.get(tt, 0) + 1
        sq = c.get("signal_quality", "insufficient")
        quality_dist[sq]= quality_dist.get(sq, 0) + 1

    total_crit = sum(c.get("gap_summary", {}).get("critical", 0) for c in cos)
    ltr_count  = sum(c.get("gap_summary", {}).get("long_term_risks", 0) for c in cos)

    high_cos = sorted(
        [c for c in cos if c.get("signal_stats", {}).get("high", 0) >= 1],
        key=lambda c: -(c.get("signal_stats", {}).get("high", 0) * 3
                        + c.get("investment_score", {}).get("total_score", 0)),
    )[:5]

    concern = [
        {"company_id": c["company_id"], "name": c["name"],
         "score": c.get("investment_score", {}).get("total_score", 0),
         "neg_count": c.get("signal_stats", {}).get("negative", 0)}
        for c in cos
        if (c.get("investment_score", {}).get("total_score", 0) < 0
            or c.get("signal_stats", {}).get("negative", 0) >= 2)
    ]

    escalated = [
        {"company_id": c["company_id"], "name": c["name"],
         "escalated_gaps": c.get("gap_summary", {}).get("escalated", 0)}
        for c in cos if c.get("gap_summary", {}).get("escalated", 0) > 0
    ]

    return {
        "as_of":               TODAY,
        "total_companies":     len(cos),
        "stage_distribution":  stage_dist,
        "sector_distribution": sector_dist,
        "ttr_distribution":    ttr_dist,
        "signal_quality":      quality_dist,
        "total_critical_gaps": total_crit,
        "long_term_risks":     ltr_count,
        "escalated_gaps":      len(escalated),
        "fuzzy_engine":        FUZZY_ENGINE,
        "high_signal_companies": [
            {"company_id": c["company_id"], "name": c["name"],
             "high_count": c.get("signal_stats", {}).get("high", 0),
             "stage": c["stage_label"],
             "score": c.get("investment_score", {}).get("total_score", 0),
             "ttr": c.get("ttr", "long_term")}
            for c in high_cos
        ],
        "concern_companies":   concern,
        "escalated_companies": escalated,
    }


# ══════════════════════════════════════════════════════════════════
# 12. 프로필 출력 (디버그)
# ══════════════════════════════════════════════════════════════════

def _print_profile(label: str, p: Optional[dict]) -> None:
    print(f"\n{'─'*62}")
    print(f"  {label}")
    print(f"{'─'*62}")
    if not p:
        print("  ⚠ 미등록 — generate-signals.py COMPANIES에 추가 필요")
        return

    ss = p.get("signal_stats", {})
    sc = p.get("investment_score", {})
    gs = p.get("gap_summary", {})

    print(f"  company_id    : {p['company_id']}")
    print(f"  stage_label   : {p['stage_label']}")
    print(f"  ttr           : {p.get('ttr','?')}")
    print(f"  signal_quality: {p.get('signal_quality','?')}")
    print(f"  signals total : {ss.get('total',0)}  (high={ss.get('high',0)}, neg={ss.get('negative',0)}, 30d={ss.get('recent_30d',0)})")
    print(f"  velocity      : {ss.get('velocity_per_week',0)} signals/week")
    if sc:
        print(f"  inv_score     : {sc.get('total_score','?')}/{sc.get('max_possible','?')} ({sc.get('interpretation','?')})")
    print(f"\n  gaps  active={gs.get('total_active',0)}  critical={gs.get('critical',0)}  escalated={gs.get('escalated',0)}  long_term={gs.get('long_term_risks',0)}")
    for g in p.get("critical_gaps", [])[:5]:
        if g.get("status") == "resolved":
            continue
        ltr = " [LONG-TERM RISK]" if g.get("long_term_risk") else ""
        esc = " ↑escalated"       if g.get("escalated")      else ""
        print(f"    {'●' if g['status']!='resolved' else '✓'} [{g['severity']:<8}] {g['gap_type']:<38} {g['status']} {g.get('days_open',0)}d{esc}{ltr}")

    buyers = p.get("buyer_activity", [])
    if buyers:
        print(f"\n  buyer_activity ({len(buyers)}):")
        for b in buyers[:3]:
            print(f"    · {b['buyer']:<20} {b['type']:<12} strength={b.get('signal_strength',0):<3} interactions={b.get('interaction_count',0)}")

    funding = p.get("funding_history", [])
    if funding:
        print(f"\n  funding_history ({len(funding)}):")
        for f in funding[:3]:
            ver = "✓" if f.get("verified") else "⚠"
            print(f"    {ver} {f['date'][:7]}  {f['round']:<22} {f['amount']}")

    ns = p.get("next_step", {})
    if ns:
        print(f"\n  next_step: {ns.get('current_stage','?')} → {ns.get('next','?')}")
        print(f"    gate    : {ns.get('gate','?')}")
        for b in ns.get("top_blockers", []):
            ltr = " [LTR]" if b.get("long_term_risk") else ""
            print(f"    blocker : {b['gap_type']} ({b['severity']}, {b.get('days_open',0)}d){ltr}")

    sh = p.get("stage_history", [])
    if len(sh) > 1:
        print(f"\n  stage_history: {' → '.join(h['stage'] for h in sh)}")


# ══════════════════════════════════════════════════════════════════
# 13. MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    log.info(f"build_company_profile.py v3.0  —  {TODAY}")
    log.info(f"Fuzzy: {FUZZY_ENGINE}  gap_escalate={GAP_ESCALATE_DAYS}d  long_term={GAP_LONGTERM_DAYS}d")

    if not LATEST.exists():
        log.error(f"{LATEST} 없음. generate-signals.py를 먼저 실행하세요.")
        return

    latest     = json.loads(LATEST.read_text("utf-8"))
    co_intel   = latest.get("companies", {})
    scorecards = latest.get("scorecards", {})
    log.info(f"latest.json: 회사 {len(co_intel)}개")

    prev_profiles: dict[str, dict] = {}
    if DEST.exists():
        try:
            saved = json.loads(DEST.read_text("utf-8"))
            prev_profiles = saved.get("companies", {})
            log.info(f"이전 프로필: {len(prev_profiles)}개 로드")
        except Exception as ex:
            log.warning(f"이전 프로필 로드 실패 ({ex}) → 신규 시작")

    new_profiles: dict[str, dict] = {}

    for cid, co in co_intel.items():
        try:
            p = build_profile(co, prev_profiles.get(cid, {}), scorecards.get(cid, {}))
            if p is None:
                continue
            new_profiles[cid] = p
            ss  = p.get("signal_stats", {})
            gs  = p.get("gap_summary", {})
            log.info(
                f"  ✓ {co.get('name','?'):<20} "
                f"stage={p['stage_label']:<16} "
                f"sig={ss.get('total',0):<3}(+{ss.get('recent_30d',0)}30d) "
                f"gaps(act={gs.get('total_active',0)},esc={gs.get('escalated',0)},ltr={gs.get('long_term_risks',0)}) "
                f"score={p.get('investment_score',{}).get('total_score','—')}"
            )
        except Exception as ex:
            log.error(f"  ✗ {cid}: {ex}")

    # 오늘 signals 없는 회사 → 이전 프로필 보존
    retained = 0
    for cid, prev in prev_profiles.items():
        if cid not in new_profiles:
            new_profiles[cid] = prev
            retained += 1
    if retained:
        log.info(f"  → {retained}개 이전 프로필 보존 (오늘 signal 없음)")

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
    log.info(f"\n저장: {DEST}  ({len(new_profiles)}개)")

    ARCHIVE.mkdir(exist_ok=True)
    arc = ARCHIVE / f"profiles_{TODAY}.json"
    arc.write_text(json.dumps(output, ensure_ascii=False, indent=2), "utf-8")

    s = summary
    print(f"\n{'═'*62}")
    print(f"  Phase 2 v3.0  —  {TODAY}")
    print(f"  {s['total_companies']}개  |  critical gaps: {s['total_critical_gaps']}  |  LTR: {s['long_term_risks']}  |  escalated: {s['escalated_gaps']}")
    print(f"  Stage:   {s['stage_distribution']}")
    print(f"  Quality: {s['signal_quality']}")
    if s["high_signal_companies"]:
        top = s["high_signal_companies"][0]
        print(f"  Top:     {top['name']} (high×{top['high_count']}, score={top['score']}, {top['ttr']})")
    if s.get("escalated_companies"):
        print(f"  ↑ Escalated: {[c['name'] for c in s['escalated_companies']]}")

    # 주요 회사 프로필 출력
    _print_profile("그리드위즈  (c_gridwiz)",        new_profiles.get("c_gridwiz"))
    _print_profile("식스티헤르츠  (c_sixtyhertz)",   new_profiles.get("c_sixtyhertz"))
    _print_profile("Form Energy  (c_form_energy)",   new_profiles.get("c_form_energy"))
    _print_profile("EnerVenue  — 미등록 예시",        new_profiles.get("c_enervenue"))
    print(f"\n{'═'*62}\n")


if __name__ == "__main__":
    main()

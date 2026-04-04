#!/usr/bin/env python3
"""
build_company_profile.py  —  Phase 2: Company-Centric Data Model
══════════════════════════════════════════════════════════════════════

Phase 1 (collect + generate-signals.py)
  → 단방향 일일 signals 목록

Phase 2 (이 파일)
  → 회사 중심 누적 프로필 (시계열 누적, gap 추적, 메모 구조화)

아키텍처:
  입력: data/latest.json  (generate-signals.py 출력)
  입력: data/company_profiles.json  (전날 프로필, 없으면 신규 생성)
  출력: data/company_profiles.json  (누적 갱신)
  출력: data/company_profiles_{DATE}.json  (일별 스냅샷)

실행 순서 (daily.yml):
  1. python collect_energy_signals.py
  2. python generate-signals.py
  3. python build_company_profile.py    ← 이 파일

데이터 정합성 원칙:
  - 수치(funding amount, capacity)는 소스 명시된 것만 기록
  - 없는 데이터는 null / "not disclosed" — 절대 추정하지 않음
  - 기존 프로필의 analyst 입력(notes, overrides)은 덮어쓰지 않음
  - signals 배열은 중복 없이 누적 (signal_id 기준 dedup)

출력 스키마:
  company_profiles.json → { "date": ..., "companies": { id: CompanyProfile } }

CompanyProfile (요청 스키마 + 확장):
  company_id, name, sector, stage, stage_label, country,
  description, tags, known_investors,
  funding_history[],        ← signals에서 추출 + 정적 레지스트리 병합
  signals[],                ← 누적 (signal_id 배열)
  signal_events[],          ← 최근 30개 이벤트 상세
  critical_gaps[],          ← MISSING_RULES 기반 현재 gap 상태
  buyer_activity[],         ← 매핑된 strategic buyer 활동
  missing_evidence[],       ← gap label 배열 (UI용)
  investment_score{},       ← scorecard 요약
  stage_history[],          ← stage 변화 이력 (날짜 추적)
  pattern{},                ← 최신 패턴 감지 결과
  commercialization_path{}, ← 다음 단계 + 핵심 미싱
  ttr, ttr_color,
  last_updated, first_seen,
  analyst_overrides{}       ← 수동 입력 필드 (pipeline이 덮어쓰지 않음)
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("build_company_profile")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

TODAY    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO  = datetime.now(timezone.utc).isoformat()

DATA_DIR         = Path("data")
LATEST_PATH      = DATA_DIR / "latest.json"
PROFILES_PATH    = DATA_DIR / "company_profiles.json"
ARCHIVE_DIR      = DATA_DIR / "profile_archive"


# ════════════════════════════════════════════════════════════════════
# 1. FUNDING EXTRACTOR
#    signals에서 financing 이벤트를 추출 → funding_history 항목 생성
#    수치가 없으면 amount = "not disclosed" (추정 금지)
# ════════════════════════════════════════════════════════════════════

# 라운드 단계 키워드
_ROUND_KWS: list[tuple[str, str]] = [
    ("series e", "Series E"),
    ("series d", "Series D"),
    ("series c", "Series C"),
    ("series b", "Series B"),
    ("series a", "Series A"),
    ("seed round", "Seed"),
    ("pre-seed", "Pre-Seed"),
    ("pre-series a", "Pre-Series A"),
    ("convertible note", "Convertible Note"),
    ("bridge round", "Bridge"),
    ("ipo", "IPO"),
    ("spac", "SPAC"),
    ("debt financing", "Debt"),
]

# 금액 추출 패턴
_AMOUNT_PATTERNS: list[str] = [
    r"\$\s*([\d,]+(?:\.\d+)?)\s*[Bb]illion",   # $1.2 Billion
    r"\$\s*([\d,]+(?:\.\d+)?)\s*[Mm]illion",   # $150 Million
    r"\$\s*([\d,]+(?:\.\d+)?)[Bb]\b",           # $1.2B
    r"\$\s*([\d,]+(?:\.\d+)?)[Mm]\b",           # $150M
    r"€\s*([\d,]+(?:\.\d+)?)\s*[Mm]illion",
    r"€\s*([\d,]+(?:\.\d+)?)[Mm]\b",
    r"£\s*([\d,]+(?:\.\d+)?)\s*[Mm]illion",
    r"₩\s*([\d,]+)억",
]


def _extract_amount(text: str) -> tuple[str, str]:
    """
    텍스트에서 금액과 통화 추출.
    Returns (amount_str, currency). 없으면 ("not disclosed", "").
    """
    t = text.lower()
    for pattern in _AMOUNT_PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            raw = m.group(0).strip()
            # 단위 정규화
            n = m.group(1).replace(",", "")
            try:
                val = float(n)
            except ValueError:
                return raw, "USD"
            if "billion" in t[max(0, m.start()-5):m.end()+10].lower() or raw.upper().endswith("B"):
                currency = "EUR" if "€" in raw else "GBP" if "£" in raw else "USD"
                return f"${val*1000:.0f}M" if currency == "USD" else f"{val*1000:.0f}M {currency}", currency
            if "₩" in raw:
                return raw, "KRW"
            currency = "EUR" if "€" in raw else "GBP" if "£" in raw else "USD"
            return f"{val:.0f}M", currency
    return "not disclosed", ""


def _extract_round(text: str) -> str:
    t = text.lower()
    for kw, label in _ROUND_KWS:
        if kw in t:
            return label
    if any(w in t for w in ["raises", "funding", "raised", "investment"]):
        return "Unknown Round"
    return ""


def _extract_lead_investor(text: str) -> str:
    """
    "led by X", "X led the round" 같은 패턴에서 리드 투자자 추출.
    없으면 "not disclosed".
    """
    patterns = [
        r"led by ([\w\s&,]+?)(?:\s+and|\s+with|\s*,|\.|$)",
        r"([\w\s&]+?) led the (?:round|raise|investment)",
        r"lead investor[:\s]+([\w\s&]+?)(?:\s+and|\s*,|\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            candidate = m.group(1).strip().rstrip(".,")
            if 2 <= len(candidate.split()) <= 5:
                return candidate
    return "not disclosed"


def extract_funding_events(signals: list[dict]) -> list[dict]:
    """
    Financing 이벤트 signals에서 funding_history 항목 추출.
    수치가 없으면 명시적으로 "not disclosed" 표기.
    """
    events = []
    seen   = set()

    for ev in signals:
        if ev.get("event_type") not in ("Financing", "funding"):
            continue
        title   = ev.get("title", "")
        summary = ev.get("summary", "") or ev.get("raw_summary", "")
        full    = f"{title} {summary}"
        date    = ev.get("event_date") or ev.get("published_date", "")
        key     = f"{date}:{title[:40]}"
        if key in seen:
            continue
        seen.add(key)

        amount, currency = _extract_amount(full)
        round_stage      = _extract_round(full)
        lead             = _extract_lead_investor(full)

        events.append({
            "date":          date,
            "round":         round_stage or "Unknown Round",
            "amount":        amount,
            "currency":      currency or "USD",
            "lead_investor": lead,
            "source":        ev.get("source_name", ""),
            "source_url":    ev.get("source_url", ""),
            "signal_id":     ev.get("id", ""),
            "verified":      False,   # analyst must verify against primary source
            "notes":         "Extracted from RSS. Verify amount against company press release.",
        })

    return sorted(events, key=lambda x: x["date"], reverse=True)


# ════════════════════════════════════════════════════════════════════
# 2. GAP TRACKER
#    오늘 gaps + 과거 gaps 비교 → 해결/신규/지속 구분
# ════════════════════════════════════════════════════════════════════

_GAP_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_gap_history(today_gaps: list[dict], prev_gaps: list[dict]) -> list[dict]:
    """
    오늘 gaps와 이전 gaps를 비교.
    각 gap에 status: "new" | "persisting" | "resolved" 추가.
    """
    prev_ids = {g["rule_id"] for g in prev_gaps}
    today_ids = {g["rule_id"] for g in today_gaps}

    enriched: list[dict] = []

    for gap in today_gaps:
        rid = gap["rule_id"]
        prev = next((g for g in prev_gaps if g["rule_id"] == rid), None)
        enriched.append({
            **gap,
            "status":    "persisting" if rid in prev_ids else "new",
            "first_seen": prev.get("first_seen", TODAY) if prev else TODAY,
            "last_seen":  TODAY,
            "days_open":  _days_since(prev.get("first_seen", TODAY)) if prev else 0,
        })

    # Resolved gaps
    for gap in prev_gaps:
        if gap["rule_id"] not in today_ids:
            enriched.append({
                **gap,
                "status":    "resolved",
                "first_seen": gap.get("first_seen", "unknown"),
                "last_seen":  gap.get("last_seen", "unknown"),
                "resolved_on": TODAY,
            })

    enriched.sort(key=lambda g: _GAP_SEVERITY_ORDER.get(g.get("severity", "low"), 9))
    return enriched


def _days_since(date_str: str) -> int:
    try:
        d = datetime.fromisoformat(date_str)
        return (datetime.now(timezone.utc) - d.replace(tzinfo=timezone.utc)).days
    except Exception:
        return 0


# ════════════════════════════════════════════════════════════════════
# 3. STAGE HISTORY TRACKER
#    stage 변화를 날짜와 함께 누적
# ════════════════════════════════════════════════════════════════════

def update_stage_history(
    new_stage: str,
    prev_history: list[dict],
    prev_stage: str,
) -> list[dict]:
    """
    stage가 바뀌었으면 이력 추가. 동일하면 그대로.
    """
    history = list(prev_history)   # 복사
    current_stage = history[-1]["stage"] if history else None

    if new_stage and new_stage != current_stage:
        history.append({
            "stage":        new_stage,
            "date":         TODAY,
            "from_stage":   prev_stage or current_stage or "unknown",
            "auto_detected": True,
            "source":       "generate-signals.py STAGE_LADDER",
        })

    return history


# ════════════════════════════════════════════════════════════════════
# 4. COMMERCIALIZATION PATH
#    현재 stage 기반으로 "다음 단계 + 핵심 미싱" 도출
# ════════════════════════════════════════════════════════════════════

_STAGE_NEXT: dict[str, dict] = {
    "Lab": {
        "next_stage":    "Pilot",
        "required_gate": "Named third-party pilot commitment or government grant award",
        "key_watch":     "Who is the first named technical partner?",
        "typical_catalyst": "Government grant → named co-development partner",
    },
    "Pilot": {
        "next_stage":    "Demo",
        "required_gate": "Third-party certification (DNV GL / KPX / UL / TÜV) or major public pilot result",
        "key_watch":     "Pilot KPI outcome + certification application status",
        "typical_catalyst": "Certification award → first supply MOU with named buyer",
    },
    "Demo": {
        "next_stage":    "First Commercial",
        "required_gate": "Named commercial contract or deployment at reference site",
        "key_watch":     "First binding contract ACV and counterparty type",
        "typical_catalyst": "Contract announcement → Series C financing",
    },
    "First Commercial": {
        "next_stage":    "Scaling",
        "required_gate": "2+ named customers, ARR visibility, or project-finance structure",
        "key_watch":     "Second buyer + international expansion",
        "typical_catalyst": "Second major contract → Series D / infrastructure fund entry",
    },
    "Scaling": {
        "next_stage":    "PF-Ready / Exit",
        "required_gate": "Project-finance bankable structure or strategic M&A interest",
        "key_watch":     "Buyer diversification + offtake concentration risk",
        "typical_catalyst": "Project finance close / strategic acquisition",
    },
}

_SECTOR_GATES: dict[str, str] = {
    "marine_fc":          "DNV GL or ClassNK Type Approval Certificate",
    "ess":                "UL 9540 / IEC 62619 + grid interconnection agreement",
    "long_duration_storage": "Independent LCOS validation + grid interconnection",
    "grid_sw":            "KPX / FERC / ENTSO-E market certification",
    "hydrogen":           "Named industrial offtaker at contracted price",
    "hvdc":               "TÜV / DNV component qualification",
    "advanced_nuclear":   "NRC license approval",
    "offshore_wind":      "CfD / PPA award + grid connection agreement",
    "data_center_power":  "Hyperscaler framework PPA",
    "geothermal":         "EGS thermal confirmation + grid connection permit",
}


def build_commercialization_path(co_enriched: dict) -> dict:
    stage     = co_enriched.get("stage_label", "Lab")
    sector    = co_enriched.get("sector", "")
    gaps      = co_enriched.get("gaps", [])
    scorecard = co_enriched.get("scorecard", {})

    path = _STAGE_NEXT.get(stage, _STAGE_NEXT["Lab"]).copy()
    path["current_stage"]  = stage
    path["sector_gate"]    = _SECTOR_GATES.get(sector, "Sector-specific gate — see sector rulebook")
    path["score"]          = scorecard.get("total_score", 0)
    path["interpretation"] = scorecard.get("interpretation", "Insufficient")

    # Top 2 critical/high gaps as blockers
    blockers = [g for g in gaps if g.get("severity") in ("critical", "high")][:2]
    path["current_blockers"] = [
        {"gap": b["label"], "severity": b["severity"], "memo": b["memo"]}
        for b in blockers
    ]

    return path


# ════════════════════════════════════════════════════════════════════
# 5. BUYER ACTIVITY FORMATTER
#    enrich_company() buyer_activity dict → 요청 스키마 배열
# ════════════════════════════════════════════════════════════════════

def format_buyer_activity(buyer_act_dict: dict) -> list[dict]:
    """
    enrich_company()가 생성하는 buyer_activity 딕셔너리를
    요청 스키마의 buyer_activity 배열로 변환.
    """
    result = []
    for bid, b in buyer_act_dict.items():
        evts = sorted(b.get("events", []), key=lambda e: e.get("date", ""), reverse=True)
        if not evts:
            continue
        latest = evts[0]
        result.append({
            "buyer_id":       bid,
            "buyer":          b.get("name", ""),
            "type":           b.get("type", ""),
            "interaction_count": b.get("count", 0),
            "latest_date":    latest.get("date", ""),
            "latest_event":   latest.get("event_type", ""),
            "signal_strength": latest.get("score", 0),
            "events":         evts[:3],   # 최근 3개만 상세 보존
        })
    result.sort(key=lambda x: x.get("signal_strength", 0), reverse=True)
    return result


# ════════════════════════════════════════════════════════════════════
# 6. CORE BUILDER
#    enrich_company() 출력 + 이전 프로필 → 갱신된 CompanyProfile
# ════════════════════════════════════════════════════════════════════

def build_profile(
    co_enriched: dict,
    prev_profile: dict | None,
    scorecard: dict | None,
) -> dict:
    """
    하나의 enriched company dict에서 CompanyProfile 생성/갱신.

    Args:
        co_enriched:  generate-signals.py enrich_company() 출력
        prev_profile: 전날 저장된 CompanyProfile (없으면 None)
        scorecard:    build_company_scorecard() 출력

    Returns:
        갱신된 CompanyProfile dict
    """
    prev = prev_profile or {}

    cid    = co_enriched["id"]
    name   = co_enriched.get("name", "")
    sector = co_enriched.get("sector", "")
    stage  = co_enriched.get("stage_label", "Lab")

    # ── Signal 누적 ──────────────────────────────────────────────────
    today_evs   = co_enriched.get("events", [])
    today_ids   = {e["id"] for e in today_evs if "id" in e}
    prev_ids    = set(prev.get("signals", []))
    all_sig_ids = sorted(prev_ids | today_ids)

    # signal_events: 최근 30개 이벤트 상세 (중복 제거 후 날짜 역순)
    prev_evs     = prev.get("signal_events", [])
    prev_ev_ids  = {e.get("id", "") for e in prev_evs}
    new_evs_full = [
        {
            "id":          e.get("id", ""),
            "date":        e.get("event_date", e.get("published_date", "")),
            "title":       e.get("title", ""),
            "event_type":  e.get("event_type", ""),
            "signal_tier": e.get("signal_tier", ""),
            "signal_strength": e.get("signal_strength", 0),
            "source_name": e.get("source_name", ""),
            "source_url":  e.get("source_url", ""),
            "is_negative": e.get("is_negative", False),
            "neg_subtype": e.get("neg_subtype"),
            "observed_fact": e.get("evidence", {}).get("observed_fact", e.get("title", "")),
            "why_it_matters": e.get("evidence", {}).get("why_it_matters", ""),
        }
        for e in today_evs if e.get("id", "") not in prev_ev_ids
    ]
    combined_evs = new_evs_full + prev_evs
    combined_evs.sort(key=lambda e: e.get("date", ""), reverse=True)
    signal_events = combined_evs[:30]

    # ── Funding history 누적 ────────────────────────────────────────
    today_funding  = extract_funding_events(today_evs)
    prev_funding   = prev.get("funding_history", [])
    # 정적 레지스트리 funding (COMPANIES 내 known_investors 등은 별도 — 여기서는 signal 기반만)
    merged_funding = _merge_funding(today_funding, prev_funding)

    # ── Gaps ─────────────────────────────────────────────────────────
    today_gaps = co_enriched.get("gaps", [])
    prev_gaps  = [g for g in prev.get("critical_gaps", []) if g.get("status") != "resolved"]
    gap_history = build_gap_history(today_gaps, prev_gaps)

    # missing_evidence (UI용 간결한 레이블 배열)
    missing_ev = [g["label"] for g in gap_history if g.get("status") != "resolved"]

    # ── Stage history ─────────────────────────────────────────────────
    prev_stage_hist  = prev.get("stage_history", [])
    prev_stage       = prev.get("stage_label", "")
    stage_history    = update_stage_history(stage, prev_stage_hist, prev_stage)

    # ── Buyer activity ────────────────────────────────────────────────
    buyer_act_raw  = co_enriched.get("buyer_activity", {})
    buyer_activity = format_buyer_activity(buyer_act_raw)

    # ── Commercialization path ────────────────────────────────────────
    co_for_path = dict(co_enriched)
    co_for_path["scorecard"] = scorecard or {}
    comm_path = build_commercialization_path(co_for_path)

    # ── Investment score summary ──────────────────────────────────────
    inv_score_summary: dict = {}
    if scorecard:
        inv_score_summary = {
            "total_score":     scorecard.get("total_score", 0),
            "max_possible":    scorecard.get("max_possible", 10),
            "interpretation":  scorecard.get("interpretation", "Insufficient"),
            "rationale":       scorecard.get("rationale", ""),
            "as_of":           TODAY,
        }

    # ── analyst_overrides 보존 (pipeline이 절대 덮어쓰지 않음) ───────
    analyst_overrides = prev.get("analyst_overrides", {
        "stage_override":    None,   # 수동 stage 설정 시 사용
        "ttr_override":      None,
        "thesis_note":       None,   # 투자 테제 요약 (analyst 작성)
        "watch_flag":        None,   # "high" | "medium" | "pass" | null
        "last_reviewed":     None,
        "reviewed_by":       None,
    })

    return {
        # ── 기본 정보 ─────────────────────────────────────────────────
        "company_id":    cid,
        "name":          name,
        "sector":        sector,
        "stage":         stage,
        "stage_label":   stage,
        "country":       co_enriched.get("country", ""),
        "description":   co_enriched.get("description", ""),
        "founded":       co_enriched.get("founded"),
        "hq":            co_enriched.get("hq", ""),
        "tags":          co_enriched.get("tags", []),
        "known_investors": co_enriched.get("known_investors", []),
        "investor_type": co_enriched.get("investor_type", ""),

        # ── Signal 누적 ───────────────────────────────────────────────
        "signals":       all_sig_ids,
        "signal_count":  len(all_sig_ids),
        "signal_events": signal_events,
        "high_count":    co_enriched.get("high_count", 0),
        "neg_count":     co_enriched.get("neg_count", 0),
        "type_counts":   co_enriched.get("type_counts", {}),

        # ── Funding history ───────────────────────────────────────────
        "funding_history": merged_funding,

        # ── Gap tracking ──────────────────────────────────────────────
        "critical_gaps":   gap_history,
        "missing_evidence": missing_ev,
        "gap_count":       len([g for g in gap_history if g.get("status") != "resolved"]),
        "critical_gap_count": len([g for g in gap_history
                                   if g.get("severity") == "critical"
                                   and g.get("status") != "resolved"]),

        # ── Buyer activity ────────────────────────────────────────────
        "buyer_activity": buyer_activity,

        # ── Stage ─────────────────────────────────────────────────────
        "stage_history":  stage_history,
        "stage_color":    co_enriched.get("stage_color", "#6E6E6E"),
        "stage_desc":     co_enriched.get("stage_desc", ""),

        # ── Pattern ───────────────────────────────────────────────────
        "pattern":        co_enriched.get("pattern", {}),

        # ── TTR ───────────────────────────────────────────────────────
        "ttr":            co_enriched.get("ttr", "Long-term"),
        "ttr_color":      co_enriched.get("ttr_color", "#6E6E6E"),

        # ── Investment scoring ────────────────────────────────────────
        "investment_score": inv_score_summary,

        # ── Commercialization path ────────────────────────────────────
        "commercialization_path": comm_path,

        # ── Sector rulebook ───────────────────────────────────────────
        "sector_rulebook": co_enriched.get("sector_rulebook", {}),

        # ── Analyst 입력 (보존) ───────────────────────────────────────
        "analyst_overrides": analyst_overrides,

        # ── 메타 ──────────────────────────────────────────────────────
        "last_updated":  TODAY,
        "first_seen":    prev.get("first_seen", TODAY),
        "data_note":     (
            "All numerical values must have source citations. "
            "Fields without sources are marked 'not disclosed'. "
            "Do not cite unverified figures externally."
        ),
    }


def _merge_funding(new_events: list[dict], prev_events: list[dict]) -> list[dict]:
    """새 funding 이벤트를 이전 이력과 병합. (날짜+라운드) 기준 dedup."""
    seen = {f"{e['date']}:{e['round']}" for e in prev_events}
    merged = list(prev_events)
    for ev in new_events:
        key = f"{ev['date']}:{ev['round']}"
        if key not in seen:
            merged.append(ev)
            seen.add(key)
    merged.sort(key=lambda e: e.get("date", ""), reverse=True)
    return merged


# ════════════════════════════════════════════════════════════════════
# 7. PORTFOLIO SUMMARY
#    전체 포트폴리오 요약 (fund-level 대시보드용)
# ════════════════════════════════════════════════════════════════════

def build_portfolio_summary(profiles: dict[str, dict]) -> dict:
    """
    company_profiles 전체에서 포트폴리오 수준 요약 생성.
    """
    cos = list(profiles.values())

    stage_dist: dict[str, int] = {}
    sector_dist: dict[str, int] = {}
    ttr_dist: dict[str, int] = {}

    high_signal_cos  = []
    concern_cos      = []
    stage_changed    = []

    for co in cos:
        # 분포
        sl = co.get("stage_label", "Lab")
        stage_dist[sl] = stage_dist.get(sl, 0) + 1
        sec = co.get("sector", "other")
        sector_dist[sec] = sector_dist.get(sec, 0) + 1
        ttr = co.get("ttr", "Long-term")
        ttr_dist[ttr] = ttr_dist.get(ttr, 0) + 1

        # High signal companies
        if co.get("high_count", 0) >= 2:
            high_signal_cos.append({
                "company_id":  co["company_id"],
                "name":        co["name"],
                "high_count":  co["high_count"],
                "stage":       co["stage_label"],
                "score":       co.get("investment_score", {}).get("total_score", 0),
            })

        # Concern companies (net negative score or neg signals)
        score = co.get("investment_score", {}).get("total_score", 0)
        if score < 0 or co.get("neg_count", 0) >= 2:
            concern_cos.append({
                "company_id": co["company_id"],
                "name":       co["name"],
                "score":      score,
                "neg_count":  co.get("neg_count", 0),
            })

        # Stage changes today
        sh = co.get("stage_history", [])
        if sh and sh[-1].get("date") == TODAY and len(sh) > 1:
            stage_changed.append({
                "company_id": co["company_id"],
                "name":       co["name"],
                "from":       sh[-1].get("from_stage", "?"),
                "to":         sh[-1].get("stage", "?"),
            })

    high_signal_cos.sort(key=lambda x: -x["high_count"])
    concern_cos.sort(key=lambda x: x["score"])

    return {
        "as_of":              TODAY,
        "total_companies":    len(cos),
        "stage_distribution": stage_dist,
        "sector_distribution":sector_dist,
        "ttr_distribution":   ttr_dist,
        "high_signal_companies": high_signal_cos[:5],
        "concern_companies":     concern_cos[:3],
        "stage_changes_today":   stage_changed,
        "total_critical_gaps":   sum(co.get("critical_gap_count", 0) for co in cos),
        "companies_with_buyers": sum(1 for co in cos if co.get("buyer_activity")),
    }


# ════════════════════════════════════════════════════════════════════
# 8. MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    log.info(f"build_company_profile.py — {TODAY}")

    # ── 입력 로드 ─────────────────────────────────────────────────
    if not LATEST_PATH.exists():
        log.error(f"latest.json not found at {LATEST_PATH}. Run generate-signals.py first.")
        return

    latest = json.loads(LATEST_PATH.read_text())
    co_intel: dict = latest.get("companies", {})
    scorecards: dict = latest.get("scorecards", {})

    if not co_intel:
        log.warning("No company data in latest.json. Check signal coverage.")
        return

    # ── 이전 프로필 로드 ──────────────────────────────────────────
    prev_profiles: dict[str, dict] = {}
    if PROFILES_PATH.exists():
        try:
            saved = json.loads(PROFILES_PATH.read_text())
            prev_profiles = saved.get("companies", {})
            log.info(f"Loaded {len(prev_profiles)} previous profiles")
        except Exception as ex:
            log.warning(f"Could not load previous profiles: {ex} — starting fresh")

    # ── 프로필 빌드 ───────────────────────────────────────────────
    new_profiles: dict[str, dict] = {}

    for cid, co_enriched in co_intel.items():
        try:
            prev = prev_profiles.get(cid)
            sc   = scorecards.get(cid)
            profile = build_profile(co_enriched, prev, sc)
            new_profiles[cid] = profile
            log.info(
                f"  {co_enriched.get('name','?'):<20} "
                f"stage={profile['stage_label']:<16} "
                f"signals={profile['signal_count']:<4} "
                f"gaps={profile['gap_count']:<3} "
                f"score={profile.get('investment_score',{}).get('total_score','?')}"
            )
        except Exception as ex:
            log.error(f"  Failed to build profile for {cid}: {ex}")

    # analyst_overrides 보존: 오늘 signals가 없는 회사도 이전 프로필 유지
    for cid, prev in prev_profiles.items():
        if cid not in new_profiles:
            # 오늘 signals 없음 — 이전 프로필 그대로 보존 (last_updated는 갱신 안 함)
            new_profiles[cid] = prev
            log.info(f"  {prev.get('name','?'):<20} → no signals today, previous profile retained")

    # ── 포트폴리오 요약 ───────────────────────────────────────────
    summary = build_portfolio_summary(new_profiles)

    # ── 저장 ──────────────────────────────────────────────────────
    output = {
        "date":              TODAY,
        "generated_at":      NOW_ISO,
        "company_count":     len(new_profiles),
        "portfolio_summary": summary,
        "companies":         new_profiles,
    }

    PROFILES_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    log.info(f"\nSaved {PROFILES_PATH} ({len(new_profiles)} companies)")

    # 일별 아카이브
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_path = ARCHIVE_DIR / f"company_profiles_{TODAY}.json"
    archive_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    log.info(f"Archived → {archive_path}")

    # 요약 출력
    print(f"\n{'═'*60}")
    print(f"  Company Profiles  —  {TODAY}")
    print(f"  {len(new_profiles)} companies | {summary['total_critical_gaps']} critical gaps")
    print(f"  Stage dist: {summary['stage_distribution']}")
    if summary["stage_changes_today"]:
        print(f"  Stage changes today: {summary['stage_changes_today']}")
    if summary["high_signal_companies"]:
        top = summary["high_signal_companies"][0]
        print(f"  Top signal: {top['name']} (HIGH ×{top['high_count']}, score {top['score']})")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

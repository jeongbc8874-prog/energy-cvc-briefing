"""
build_company_profile.py  v8.0
Energy CVC Intelligence Platform — Dynamic Company Registry

━━━ v7.0 대비 핵심 변경 ━━━

[구조 변경]
  이전: COMPANIES 13개 고정 리스트만 처리
  이후: signals에 등장하는 모든 회사를 자동 감지 + 프로필 누적

[파일 구조]
  data/latest.json          ← generate-signals.py 출력 (읽기)
  data/company_profiles.json ← 누적 회사 DB (읽기/쓰기)
  data/latest.json.companies ← 오늘 스냅샷으로 덮어쓰기

[흐름]
  1. company_profiles.json 로드 (없으면 기존 13개로 초기화)
  2. latest.json의 signals 전체 스캔
     - company_id 있는 것 → 기존 프로필 업데이트
     - company_name이 'Unassigned'가 아닌 것 → fuzzy match → 없으면 신규 등록
     - NER 패턴으로 제목/요약에서 추가 회사 추출
  3. 모든 회사 Gap escalation + Stage 승급
  4. company_profiles.json 저장
  5. latest.json의 companies 섹션 업데이트

실행:
  python build_company_profile.py
  BASE_DIR=data python build_company_profile.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from company_resolver import CompanyResolver, SEED_COMPANIES, normalize_name, is_buyer

# ─────────────────────────────────────────────────────────────────────────
# 경로
# ─────────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(os.environ.get("BASE_DIR", "data"))
LATEST_PATH   = BASE_DIR / "latest.json"
PROFILES_PATH = BASE_DIR / "company_profiles.json"
TODAY         = date.today().isoformat()

# ─────────────────────────────────────────────────────────────────────────
# Stage 정의
# ─────────────────────────────────────────────────────────────────────────
STAGE_ORDER = ["Lab", "Pilot", "Demo", "First Commercial", "Scaling", "PF-Ready"]
STAGE_IDX   = {s: i for i, s in enumerate(STAGE_ORDER)}

STAGE_THRESHOLDS: dict[str, float] = {
    "Lab":              0.0,
    "Pilot":            2.0,
    "Demo":             5.0,
    "First Commercial": 8.0,
    "Scaling":         16.0,
    "PF-Ready":        24.0,
}

EVENT_WEIGHT: dict[str, float] = {
    "Contract":     3.0,
    "Deployment":   3.0,
    "Certification":2.5,
    "Pilot":        2.0,
    "Financing":    1.5,
    "Partnership":  1.5,
    "Grant":        1.0,
    "Hiring":       0.5,
    "Milestone":    0.5,
    "Expansion":    1.0,
    "Negative":     0.0,
}

CD_HARD_RULE: dict[int, str] = {
    1: "First Commercial",
    3: "Scaling",
    5: "PF-Ready",
}

# ─────────────────────────────────────────────────────────────────────────
# Gap Escalation 래더 (누적 적용)
# ─────────────────────────────────────────────────────────────────────────
ESCALATION_LADDER = [
    (7,  {"severity_bump": 1, "force_critical": False,
          "tags": [],                               "memo_flag": "[7d+ 미해결]"}),
    (14, {"severity_bump": 0, "force_critical": True,
          "tags": [],                               "memo_flag": "[14d+ → CRITICAL]"}),
    (21, {"severity_bump": 0, "force_critical": True,
          "tags": ["STRUCTURAL_RISK"],              "memo_flag": "[21d+ 구조적 리스크]"}),
    (30, {"severity_bump": 0, "force_critical": True,
          "tags": ["STRUCTURAL_RISK","LONG_TERM_RISK"], "memo_flag": "[30d+ 장기 블로커]"}),
]

SEVERITY_ORDER = ["low", "medium", "high", "critical"]
SEVERITY_IDX   = {s: i for i, s in enumerate(SEVERITY_ORDER)}

BLOCKER_SEV        = {"low": 1, "medium": 2, "high": 4, "critical": 8}
BLOCKER_TIER_BONUS = {7: 1, 14: 3, 21: 6, 30: 12}
RESOLVED_DAYS      = 3

# ─────────────────────────────────────────────────────────────────────────

# SEED_COMPANIES, normalize_name, is_buyer 등은 company_resolver.py에서 import됨

# ═════════════════════════════════════════════════════════════════════════
# 유틸 함수
# ═════════════════════════════════════════════════════════════════════════

def days_since(iso: str) -> int:
    try:
        return max(0, (date.today() - date.fromisoformat(iso)).days)
    except Exception:
        return 0

def bump_severity(current: str, n: int) -> str:
    idx = SEVERITY_IDX.get(current, 0)
    return SEVERITY_ORDER[min(idx + n, len(SEVERITY_ORDER) - 1)]

def floor_severity(current: str, floor: str) -> str:
    return floor if SEVERITY_IDX.get(current, 0) < SEVERITY_IDX.get(floor, 0) else current



# normalize_name, fuzzy_match_company, is_buyer 등은 company_resolver.py에서 import됨

# ═════════════════════════════════════════════════════════════════════════
# Company Profiles DB
# ═════════════════════════════════════════════════════════════════════════

def load_profiles() -> dict[str, dict]:
    """
    company_profiles.json 로드.
    없으면 SEED_COMPANIES 13개로 초기화.
    이전 버전 스키마(값이 dict 아닌 경우) 자동 필터링.
    """
    if PROFILES_PATH.exists():
        try:
            raw = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            # 값이 dict인 항목만 유지 (이전 버전 호환)
            data = {k: v for k, v in raw.items() if isinstance(v, dict)}
            skipped = len(raw) - len(data)
            if skipped:
                print(f"[PROFILES] 경고: {skipped}개 항목이 잘못된 형식 → 제외")
            print(f"[PROFILES] 로드: {PROFILES_PATH} ({len(data)}개 회사)")
            # 시드 회사 중 누락된 것 보충
            for seed in SEED_COMPANIES:
                cid = seed.get("company_id") or seed.get("id")
                if cid not in data:
                    data[cid] = _make_profile_from_seed(seed)
                    print(f"[PROFILES] 시드 보충: {cid}")
            return data
        except Exception as e:
            print(f"[PROFILES] 로드 실패({e}) — 시드 데이터로 초기화")

    print("[PROFILES] 신규 생성 — 시드 13개로 초기화")
    profiles: dict[str, dict] = {}
    for seed in SEED_COMPANIES:
        cid = seed.get("company_id") or seed.get("id")
        profiles[cid] = _make_profile_from_seed(seed)
    return profiles


def _make_profile_from_seed(seed: dict) -> dict:
    return {
        "company_id":     seed.get("company_id") or seed.get("id"),
        "name":           seed["name"],
        "sector":         seed.get("sector", ""),
        "country":        seed.get("country", ""),
        "hq":             seed.get("hq", ""),
        "founded":        seed.get("founded"),
        "description":    seed.get("description", ""),
        "source":         seed.get("source", "registered"),
        "registered_date":TODAY,
        "aliases":        seed.get("aliases", [seed["name"].lower()]),
        # Stage
        "stage":          seed.get("stage", "Lab"),
        "stage_label":    seed.get("stage", "Lab"),
        "stage_score":    0.0,
        "stage_reason":   "",
        # Gap log (통합)
        "gap_log":        {},
        # 오늘 계산 필드
        "active_gaps":    [],
        "structural_tags":[],
        "blocker_score":  0,
        "critical_gaps":  0,
        # 이벤트 이력
        "all_events":     [],
        "signal_count":   0,
        "last_signal_date":"",
        # 메타
        "profile_date":   TODAY,
        "profile_version":"8.0",
    }


def _make_auto_profile(name: str, sector: str = "") -> dict:
    """signals에서 새로 발견된 회사 자동 등록"""
    cid = normalize_name(name)
    print(f"  [NEW COMPANY] '{name}' → company_id='{cid}'  source=auto")
    return {
        "company_id":     cid,
        "name":           name,
        "sector":         sector,
        "country":        "",
        "hq":             "",
        "founded":        None,
        "description":    "Auto-registered from signal. Analyst review recommended.",
        "source":         "auto",
        "registered_date":TODAY,
        "aliases":        [name.lower(), normalize_name(name)],
        "stage":          "Lab",
        "stage_label":    "Lab",
        "stage_score":    0.0,
        "stage_reason":   "",
        "gap_log":        {},
        "active_gaps":    [],
        "structural_tags":[],
        "blocker_score":  0,
        "critical_gaps":  0,
        "all_events":     [],
        "signal_count":   0,
        "last_signal_date":"",
        "profile_date":   TODAY,
        "profile_version":"8.0",
    }


def save_profiles(profiles: dict[str, dict]) -> None:
    PROFILES_PATH.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[PROFILES] 저장: {PROFILES_PATH} ({len(profiles)}개 회사)")


# ═════════════════════════════════════════════════════════════════════════
# Signal 스캔 → 회사 감지 + 이벤트 누적
# ═════════════════════════════════════════════════════════════════════════

def resolve_and_register(
    company_name: str,
    company_id_hint: Optional[str],
    sector: str,
    profiles: dict[str, dict],
    _res: "CompanyResolver | None" = None,
) -> Optional[str]:
    """
    회사명 → company_id. company_resolver 우선, 없으면 profiles dict fallback.
    Returns company_id or None.
    """
    if not company_name or company_name.lower() in ("unassigned", "", "none"):
        return None
    if is_buyer(company_name):
        return None

    # generate-signals.py가 이미 매칭한 ID
    if company_id_hint and company_id_hint in profiles:
        return company_id_hint

    # company_resolver 사용 (SEED + auto 통합 탐색 + 신규 등록)
    if _res is not None:
        cid, _, _ = _res.resolve(company_name, sector)
        if cid:
            # 새로 등록된 경우 profiles에도 반영
            if cid not in profiles:
                new_prof = _make_auto_profile(company_name, sector)
                new_prof["company_id"] = cid
                profiles[cid] = new_prof
            return cid

    # fallback: profiles dict에서 직접 탐색 (resolver 없을 때)
    norm = normalize_name(company_name)
    for cid, prof in profiles.items():
        if not isinstance(prof, dict): continue
        if normalize_name(prof.get("name","")) == norm: return cid
        if company_name.lower() in [a.lower() for a in prof.get("aliases", [])]: return cid

    # 완전 신규 등록
    new_prof = _make_auto_profile(company_name, sector)
    new_id   = new_prof["company_id"]
    if new_id in profiles and profiles[new_id].get("name","").lower() != company_name.lower():
        new_id += "_2"
        new_prof["company_id"] = new_id
    profiles[new_id] = new_prof
    return new_id


def scan_signals(signals: list[dict], profiles: dict[str, dict], _resolver=None) -> dict[str, list[dict]]:
    """
    signals 전체 스캔:
    1. company_id/company_name 필드로 회사 감지
    2. NER로 제목에서 추가 회사 감지
    Returns {company_id: [event, ...]}
    """
    company_events: dict[str, list[dict]] = {}
    new_company_count = 0

    for sig in signals:
        # ── 1. generate-signals.py 매칭 결과 활용 ─────────────────
        co_id   = sig.get("company_id")
        co_name = sig.get("company_name", "")
        sector  = sig.get("segment", "")

        resolved = resolve_and_register(co_name, co_id, sector, profiles, _resolver)
        if resolved:
            if resolved not in profiles:
                new_company_count += 1
            company_events.setdefault(resolved, []).append(sig)

        # ── 2. NER: 제목+요약에서 추가 회사 추출 ──────────────────
        text = sig.get("title", "") + " " + sig.get("summary", "")
        for match in NER_RE.finditer(text):
            found_name = match.group().strip()
            if found_name.lower() == co_name.lower():
                continue  # 이미 처리됨
            if is_buyer_skip(found_name):
                continue
            extra_id = resolve_and_register(found_name, None, sector, profiles, _resolver)
            if extra_id and extra_id != resolved:
                company_events.setdefault(extra_id, []).append(sig)

    # 이벤트 중복 제거 (같은 sig가 NER로 두 번 들어올 수 있음)
    for cid in company_events:
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for ev in company_events[cid]:
            eid = ev.get("id", ev.get("title",""))
            if eid not in seen_ids:
                seen_ids.add(eid)
                deduped.append(ev)
        company_events[cid] = deduped

    if new_company_count:
        print(f"  [SCAN] 신규 회사 {new_company_count}개 자동 등록")

    return company_events


def merge_events_to_profile(profile: dict, new_events: list[dict]) -> dict:
    """
    profile의 all_events에 new_events를 중복 없이 추가.
    all_events는 최대 200개 유지 (날짜 내림차순).
    """
    existing_ids = {ev.get("id", "") for ev in profile.get("all_events", [])}
    added = 0
    for ev in new_events:
        eid = ev.get("id", ev.get("title", ""))
        if eid and eid not in existing_ids:
            profile.setdefault("all_events", []).append(ev)
            existing_ids.add(eid)
            added += 1

    # 날짜 내림차순 정렬, 최대 200개
    profile["all_events"] = sorted(
        profile.get("all_events", []),
        key=lambda e: e.get("event_date", e.get("published_date", "")),
        reverse=True,
    )[:200]

    if added:
        profile["signal_count"] = len(profile.get("all_events", []))
        dates = [
            e.get("event_date", e.get("published_date", ""))
            for e in profile.get("all_events", [])
            if e.get("event_date") or e.get("published_date")
        ]
        profile["last_signal_date"] = max(dates) if dates else ""

    return profile


# ═════════════════════════════════════════════════════════════════════════
# Gap escalation
# ═════════════════════════════════════════════════════════════════════════

def update_gap_log(profile: dict, raw_gaps: list[dict]) -> None:
    """gap_log를 오늘 gaps 기준으로 업데이트 (in-place)."""
    gap_log   = profile.setdefault("gap_log", {})
    today_ids = {g["rule_id"] for g in raw_gaps if "rule_id" in g}

    for gap in raw_gaps:
        rid = gap.get("rule_id")
        if not rid:
            continue
        if rid not in gap_log:
            first_seen = gap.get("first_seen") or TODAY
            gap_log[rid] = {
                "first_seen":    first_seen,
                "last_seen":     TODAY,
                "absent_streak": 0,
                "resolved":      False,
                "resolved_date": None,
            }
            age = days_since(first_seen)
            print(f"  [GAP NEW]    {profile['company_id']:20s} rule={rid:22s} age={age}d")
        else:
            entry = gap_log[rid]
            if entry.get("resolved"):
                entry["resolved"] = False
                entry["resolved_date"] = None
                print(f"  [GAP REOPEN] {profile['company_id']:20s} rule={rid:22s}")
            entry["last_seen"]     = TODAY
            entry["absent_streak"] = 0

    for rid, entry in gap_log.items():
        if rid in today_ids or entry.get("resolved"):
            continue
        entry["absent_streak"] = entry.get("absent_streak", 0) + 1
        streak = entry["absent_streak"]
        if streak >= RESOLVED_DAYS:
            entry["resolved"]      = True
            entry["resolved_date"] = TODAY
            print(f"  [GAP RESOLVED] {profile['company_id']:20s} rule={rid:22s} (absent {streak}d)")


def escalate_gap(gap: dict, first_seen: str, company_id: str) -> dict:
    """모든 matching tier 누적 적용. Returns new dict."""
    gap  = dict(gap)
    days = days_since(first_seen)

    orig_sev  = gap.get("severity", "medium")
    cur_sev   = orig_sev
    all_tags  = list(gap.get("tags", []))
    memo_flags: list[str] = []
    top_tier: Optional[int] = None

    for threshold, rule in ESCALATION_LADDER:
        if days < threshold:
            break
        top_tier = threshold
        if rule["severity_bump"]:
            cur_sev = bump_severity(cur_sev, rule["severity_bump"])
        if rule["force_critical"]:
            cur_sev = floor_severity(cur_sev, "critical")
        for tag in rule["tags"]:
            if tag not in all_tags:
                all_tags.append(tag)
        if rule["memo_flag"] not in memo_flags:
            memo_flags.append(rule["memo_flag"])

    gap["severity"]        = cur_sev
    gap["tags"]            = all_tags
    gap["escalation_days"] = days
    gap["escalation_tier"] = top_tier
    gap["first_seen"]      = first_seen

    if memo_flags:
        base = (gap.get("memo") or "").rstrip()
        gap["memo"] = base + ("  " if base else "") + "  ".join(memo_flags)

    if top_tier is not None and (cur_sev != orig_sev or all_tags):
        print(
            f"  [ESCALATED]  {company_id:20s} rule={gap.get('rule_id','?'):20s} "
            f"days={days:2d}d tier={top_tier:2d} sev:{orig_sev}→{cur_sev} tags={all_tags or '—'}"
        )
    return gap


# ═════════════════════════════════════════════════════════════════════════
# Stage 승급
# ═════════════════════════════════════════════════════════════════════════

def compute_stage(
    company_id: str,
    current_stage: str,
    events: list[dict],
) -> tuple[str, float, str]:
    score    = 0.0
    cd_count = 0
    type_tally: dict[str, int] = {}

    for ev in events:
        tier   = ev.get("signal_tier", "low")
        mult   = 1.0 if tier == "high" else 0.6 if tier == "medium" else 0.3
        etype  = ev.get("event_type", "")
        weight = EVENT_WEIGHT.get(etype, 0.3)
        score += weight * mult
        type_tally[etype] = type_tally.get(etype, 0) + 1
        if etype in ("Contract", "Deployment") and not ev.get("is_negative", False):
            cd_count += 1

    # 점수 기반 stage
    score_stage = "Lab"
    for stage in STAGE_ORDER:
        if score >= STAGE_THRESHOLDS[stage]:
            score_stage = stage

    # hard rule
    hard_floor, hard_reason = "Lab", ""
    for min_cd, floor_stage in sorted(CD_HARD_RULE.items(), reverse=True):
        if cd_count >= min_cd:
            hard_floor  = floor_stage
            hard_reason = f"hard-rule:{cd_count}×CD≥{min_cd}→≥{floor_stage}"
            break

    new_stage = max(
        [score_stage, hard_floor, current_stage],
        key=lambda s: STAGE_IDX.get(s, 0),
    )

    reason = (
        f"score={score:.1f} cd={cd_count} types={type_tally} "
        f"score_stage={score_stage} hard_floor={hard_floor} prev={current_stage} {hard_reason}"
    ).strip()

    if new_stage != current_stage:
        print(
            f"  [STAGE ▲]    {company_id:20s}  {current_stage} → {new_stage}  "
            f"(score={score:.1f} cd={cd_count})"
        )
    else:
        next_idx  = min(STAGE_IDX.get(current_stage, 0) + 1, len(STAGE_ORDER) - 1)
        next_stage = STAGE_ORDER[next_idx]
        need       = STAGE_THRESHOLDS.get(next_stage, 999)
        print(
            f"  [STAGE —]    {company_id:20s}  {current_stage:18s} "
            f"score={score:.1f} need {need:.1f}→{next_stage}"
        )
    return new_stage, round(score, 2), reason


def compute_blocker_score(gaps: list[dict]) -> int:
    total = 0
    for g in gaps:
        sev  = g.get("severity", "low")
        tier = g.get("escalation_tier")
        total += BLOCKER_SEV.get(sev, 1) + BLOCKER_TIER_BONUS.get(tier, 0)
    return total


# ═════════════════════════════════════════════════════════════════════════
# 핵심: 회사 1개 처리
# ═════════════════════════════════════════════════════════════════════════

def process_company(
    profile:    dict,
    events:     list[dict],  # 오늘 latest.json의 이벤트들
    raw_gaps:   list[dict],  # generate-signals.py의 gap 리스트
) -> dict:
    """
    gap_log 업데이트 → escalation → stage 승급 → blocker_score
    Returns updated profile (in-place도 적용됨)
    """
    company_id    = profile["company_id"]
    current_stage = profile.get("stage_label") or profile.get("stage", "Lab")

    # 1. 이벤트 누적
    profile = merge_events_to_profile(profile, events)
    all_events = profile.get("all_events", [])

    # 2. Gap log 업데이트
    update_gap_log(profile, raw_gaps)

    # 3. Gap escalation
    gap_log       = profile.get("gap_log", {})
    enriched_gaps = []
    for gap in raw_gaps:
        rid   = gap.get("rule_id")
        entry = gap_log.get(rid)
        fs    = (
            entry["first_seen"]
            if entry and not entry.get("resolved")
            else gap.get("first_seen") or TODAY
        )
        enriched_gaps.append(escalate_gap(gap, fs, company_id))

    enriched_gaps.sort(key=lambda g: (
        -SEVERITY_IDX.get(g.get("severity", "low"), 0),
        -(g.get("escalation_days") or 0),
    ))

    # 4. Stage 승급
    new_stage, stage_score, stage_reason = compute_stage(
        company_id, current_stage, all_events
    )

    # 5. 집계
    critical_cnt    = sum(1 for g in enriched_gaps if g.get("severity") == "critical")
    structural_tags = sorted({tag for g in enriched_gaps for tag in g.get("tags", [])})
    blocker_score   = compute_blocker_score(enriched_gaps)

    # 6. 프로필 갱신
    profile["stage"]          = new_stage
    profile["stage_label"]    = new_stage
    profile["stage_previous"] = current_stage
    profile["stage_score"]    = stage_score
    profile["stage_reason"]   = stage_reason
    profile["active_gaps"]    = enriched_gaps
    profile["structural_tags"]= structural_tags
    profile["blocker_score"]  = blocker_score
    profile["critical_gaps"]  = critical_cnt
    profile["profile_date"]   = TODAY
    profile["profile_version"]= "8.0"

    return profile


# ═════════════════════════════════════════════════════════════════════════
# 메인 파이프라인
# ═════════════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{'═'*64}")
    print(f"  build_company_profile.py  v8.0   {TODAY}")
    print(f"{'═'*64}\n")

    # ── latest.json 로드 ──────────────────────────────────────────
    if not LATEST_PATH.exists():
        print(f"[ERROR] {LATEST_PATH} 없음 — generate-signals.py를 먼저 실행하세요")
        sys.exit(1)

    try:
        payload = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] latest.json 파싱 실패: {e}")
        sys.exit(1)

    signals: list[dict] = payload.get("signals", [])
    print(f"[LOAD] {LATEST_PATH}  signals={len(signals)}개\n")

    # ── company_profiles.json 로드 ────────────────────────────────
    profiles = load_profiles()
    before_count = len(profiles)
    print()

    # ── signals 스캔 → 회사 감지 + 이벤트 분류 ───────────────────
    print("[SCAN] signals 스캔 — 회사 감지 + 이벤트 분류")
    # resolver에 기존 auto 회사 로드
    _resolver = CompanyResolver()
    _resolver.load_auto_from_profiles(profiles)
    company_events = scan_signals(signals, profiles, _resolver)
    after_count    = len(profiles)
    new_discovered = after_count - before_count
    print(
        f"  기존={before_count}개  신규발견={new_discovered}개  "
        f"총={after_count}개  이벤트있는회사={len(company_events)}개\n"
    )

    # ── 기존 latest.json의 companies에서 gaps 추출 ────────────────
    # generate-signals.py가 enrich_company에서 계산한 gaps를 재활용
    existing_companies: dict = payload.get("companies", {})

    # ── 각 회사 처리 ──────────────────────────────────────────────
    print("[PROCESS] Gap escalation + Stage 승급")
    print("─" * 64)

    summary_rows: list[dict] = []
    processed_companies: dict[str, dict] = {}

    # 오늘 이벤트 있는 회사 먼저
    process_order = list(company_events.keys())
    # 이벤트 없어도 gap_log 있는 기존 회사도 처리 (escalation 누적)
    for cid in profiles:
        if cid not in process_order:
            process_order.append(cid)

    for company_id in process_order:
        profile = profiles.get(company_id)
        if not isinstance(profile, dict):
            continue

        try:
            pname = profile.get("name") or company_id
            print(f"\n\u250c {pname} ({company_id})")

            # 오늘 이벤트
            events_today = company_events.get(company_id, [])
            if not isinstance(events_today, list):
                events_today = []

            # gaps: generate-signals.py 계산값 or 빈 리스트
            # existing_co / raw_gaps 타입 방어 (이전 버전 호환)
            existing_co = existing_companies.get(company_id, {})
            if not isinstance(existing_co, dict):
                existing_co = {}
            raw_gaps = [g for g in (existing_co.get("gaps") or []) if isinstance(g, dict)]

            updated = process_company(profile, events_today, raw_gaps)
            profiles[company_id] = updated

            # latest.json용 enriched company dict 생성
            enriched = {**existing_co, **{
                "id":              company_id,
                "name":            updated.get("name", company_id),
                "sector":          updated.get("sector", ""),
                "stage_label":     updated.get("stage_label", "Lab"),
                "stage_previous":  updated.get("stage_previous", ""),
                "stage_score":     updated.get("stage_score", 0.0),
                "gaps":            updated.get("active_gaps", []),
                "blocker_score":   updated.get("blocker_score", 0),
                "critical_gaps":   updated.get("critical_gaps", 0),
                "structural_tags": updated.get("structural_tags", []),
                "signal_count":    updated.get("signal_count", 0),
                "last_signal_date":updated.get("last_signal_date", ""),
                "source":          updated.get("source", "auto"),
                "profile_version": "8.0",
            }}
            processed_companies[company_id] = enriched

            summary_rows.append({
                "id":      company_id,
                "name":    updated.get("name", company_id),
                "source":  updated.get("source", "auto"),
                "stage":   updated.get("stage_label", "Lab"),
                "prev":    updated.get("stage_previous", ""),
                "up":      updated.get("stage_label") != updated.get("stage_previous",
                           updated.get("stage_label")),
                "blocker": updated.get("blocker_score", 0),
                "crit":    updated.get("critical_gaps", 0),
                "tags":    updated.get("structural_tags", []),
                "events":  len(events_today),
            })

        except Exception as exc:
            import traceback
            print(f"  [ERROR] {company_id}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            # 에러 나도 빈 결과로 계속 진행 (파이프라인 전체 중단 방지)
            processed_companies[company_id] = {
                "id":            company_id,
                "name":          profile.get("name", company_id),
                "stage_label":   profile.get("stage_label", "Lab"),
                "source":        profile.get("source", "auto"),
                "profile_version":"8.0",
                "error":         str(exc),
            }

    # ── latest.json 업데이트 ─────────────────────────────────────
    payload["companies"]          = processed_companies
    payload["profile_built_at"]   = datetime.now(timezone.utc).isoformat()
    payload["profile_version"]    = "8.0"
    payload["company_count_total"]= len(profiles)
    payload["company_count_auto"] = sum(
        1 for p in profiles.values() if p.get("source") == "auto"
    )

    LATEST_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[SAVE] {LATEST_PATH} 업데이트 완료")

    # ── company_profiles.json 저장 ────────────────────────────────
    save_profiles(profiles)

    # ── 요약 테이블 ───────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print(
        f"  {'회사':22s} {'src':4s} {'stage':22s} {'blocker':>8} {'crit':>5}  struct_tags"
    )
    print("  " + "─" * 68)

    # 등록 회사 먼저, 신규 나중
    reg  = [r for r in summary_rows if r["source"] == "registered"]
    auto = [r for r in summary_rows if r["source"] != "registered"]

    for r in sorted(reg, key=lambda x: -x["blocker"]):
        _print_summary_row(r)
    if auto:
        print("  ── 자동 등록 회사 ──────────────────────────────────────────")
        for r in sorted(auto, key=lambda x: -x["events"]):
            _print_summary_row(r)

    print("  " + "─" * 68)
    promotions  = sum(1 for r in summary_rows if r["up"])
    high_risk   = sum(1 for r in summary_rows if r["blocker"] >= 20)
    struct_risk = sum(1 for r in summary_rows if "STRUCTURAL_RISK" in r["tags"])

    print(
        f"  전체={len(summary_rows)}  "
        f"(등록={len(reg)} 자동={len(auto)})  "
        f"승급={promotions}  "
        f"high-risk(≥20)={high_risk}  "
        f"STRUCTURAL_RISK={struct_risk}"
    )
    print(f"{'═'*72}\n")


def _print_summary_row(r: dict) -> None:
    arrow = f"{r['prev']}→{r['stage']}" if r["up"] else r["stage"]
    tags  = ", ".join(r["tags"]) if r["tags"] else "—"
    evs   = f"(+{r['events']})" if r["events"] else ""
    print(
        f"  {r['name']:22s} {r['source']:4s} {arrow:22s} "
        f"{r['blocker']:>8d} {r['crit']:>5d}  {tags} {evs}"
    )


if __name__ == "__main__":
    main()

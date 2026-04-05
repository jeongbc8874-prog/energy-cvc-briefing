"""
build_company_profile.py  v7.0
Energy CVC Intelligence Platform — Gap Escalation + Stage Promotion Engine

동작 방식:
  1. data/latest.json (generate-signals.py 출력) 읽기
  2. data/gap_log.json (누적 이력) 읽기 — 없으면 신규 생성
  3. 각 회사별:
     - Gap escalation (7/14/21/30일 누적 기준)
     - Stage 승급 (event_type 가중치 기반)
     - blocker_score 계산
  4. data/latest.json의 companies 섹션을 in-place 업데이트
  5. data/gap_log.json 저장

실행:
  python build_company_profile.py
  BASE_DIR=data python build_company_profile.py
"""

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# ── 경로 ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(os.environ.get("BASE_DIR", "data"))
LATEST_PATH = BASE_DIR / "latest.json"
GAP_LOG     = BASE_DIR / "gap_log.json"
TODAY       = date.today().isoformat()

# ── Stage 정의 (낮은 인덱스 = 낮은 단계) ──────────────────────────────────
STAGE_ORDER = ["Lab", "Pilot", "Demo", "First Commercial", "Scaling", "PF-Ready"]
STAGE_IDX   = {s: i for i, s in enumerate(STAGE_ORDER)}

# ── Event type 가중치 (stage 승급 점수용) ────────────────────────────────
EVENT_WEIGHT = {
    "Contract":     3.0,
    "Deployment":   3.0,
    "Certification":2.5,
    "Pilot":        2.0,
    "Partnership":  1.5,
    "Financing":    1.5,
    "Grant":        1.0,
    "Hiring":       0.5,
    "Milestone":    0.5,
}

# Stage별 필요 누적 점수
STAGE_SCORE_THRESHOLD = {
    "Lab":             0.0,
    "Pilot":           2.0,   # Pilot 1개 이상
    "Demo":            5.0,   # Pilot + Certification 등
    "First Commercial":8.0,   # Contract 또는 Deployment 포함
    "Scaling":        16.0,   # Contract/Deployment 복수
    "PF-Ready":       24.0,
}

# Hard rule: Contract/Deployment 개수 → 최소 보장 stage
CD_HARD_RULE = {
    1: "First Commercial",
    3: "Scaling",
    5: "PF-Ready",
}

# ── Gap Escalation 누적 래더 ─────────────────────────────────────────────
# days >= threshold 인 모든 tier 누적 적용
ESCALATION_LADDER = [
    (7,  {
        "severity_bump": 1,       # severity +1 단계
        "force_critical": False,
        "tags": [],
        "memo_flag": "[7d+ 미해결]",
    }),
    (14, {
        "severity_bump": 0,
        "force_critical": True,   # critical 강제
        "tags": [],
        "memo_flag": "[14d+ → CRITICAL 강제]",
    }),
    (21, {
        "severity_bump": 0,
        "force_critical": True,
        "tags": ["STRUCTURAL_RISK"],
        "memo_flag": "[21d+ 구조적 리스크]",
    }),
    (30, {
        "severity_bump": 0,
        "force_critical": True,
        "tags": ["STRUCTURAL_RISK", "LONG_TERM_RISK"],
        "memo_flag": "[30d+ 장기 미해결 — 투자 블로커]",
    }),
]

SEVERITY_ORDER = ["low", "medium", "high", "critical"]
SEVERITY_IDX   = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# blocker_score 가중치
BLOCKER_SEV = {"low": 1, "medium": 2, "high": 4, "critical": 8}
BLOCKER_TIER_BONUS = {7: 1, 14: 3, 21: 6, 30: 12}

# resolved: 3일 연속 absent
RESOLVED_DAYS = 3


# ═════════════════════════════════════════════════════════════════════════
# 유틸
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
    if SEVERITY_IDX.get(current, 0) < SEVERITY_IDX.get(floor, 0):
        return floor
    return current


# ═════════════════════════════════════════════════════════════════════════
# Gap Log (persistent)
# ═════════════════════════════════════════════════════════════════════════

def load_gap_log() -> dict:
    if GAP_LOG.exists():
        try:
            data = json.loads(GAP_LOG.read_text())
            print(f"[GAP_LOG] 로드: {GAP_LOG} ({len(data)} 회사)")
            return data
        except Exception as e:
            print(f"[GAP_LOG] 로드 실패 ({e}) — 새로 시작")
    else:
        print("[GAP_LOG] 파일 없음 — 새로 생성")
    return {}


def save_gap_log(log: dict) -> None:
    GAP_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"[GAP_LOG] 저장 완료: {GAP_LOG}")


def update_gap_log(log: dict, company_id: str, today_gaps: list[dict]) -> None:
    """
    오늘 감지된 gaps으로 gap_log 업데이트.
    - 오늘 있는 rule_id: first_seen 보존, absent_streak=0
    - 오늘 없는 rule_id: absent_streak+1, 3일 이상이면 resolved
    - first_seen 우선순위: ① 기존 log ② gap의 first_seen 필드 ③ 오늘
    """
    company_log = log.setdefault(company_id, {})
    today_ids   = {g["rule_id"] for g in today_gaps if "rule_id" in g}

    # 오늘 있는 gaps
    for gap in today_gaps:
        rid = gap.get("rule_id")
        if not rid:
            continue
        existing = company_log.get(rid)
        if existing is None:
            first_seen = gap.get("first_seen") or TODAY
            company_log[rid] = {
                "first_seen":    first_seen,
                "last_seen":     TODAY,
                "absent_streak": 0,
                "resolved":      False,
                "resolved_date": None,
            }
            age = days_since(first_seen)
            print(f"  [GAP NEW]      {company_id:18s} rule={rid:20s} first_seen={first_seen} (age={age}d)")
        else:
            if existing.get("resolved"):
                # 재오픈
                existing["resolved"]      = False
                existing["resolved_date"] = None
                print(f"  [GAP REOPEN]   {company_id:18s} rule={rid:20s}")
            existing["last_seen"]     = TODAY
            existing["absent_streak"] = 0

    # 오늘 없는 gaps
    for rid, entry in company_log.items():
        if rid in today_ids or entry.get("resolved"):
            continue
        entry["absent_streak"] = entry.get("absent_streak", 0) + 1
        streak = entry["absent_streak"]
        if streak >= RESOLVED_DAYS:
            entry["resolved"]      = True
            entry["resolved_date"] = TODAY
            print(f"  [GAP RESOLVED] {company_id:18s} rule={rid:20s} (absent {streak}일 >= {RESOLVED_DAYS}일 → resolved)")
        else:
            print(f"  [GAP ABSENT]   {company_id:18s} rule={rid:20s} (absent_streak={streak}/{RESOLVED_DAYS})")


# ═════════════════════════════════════════════════════════════════════════
# Gap Escalation
# ═════════════════════════════════════════════════════════════════════════

def escalate_gap(gap: dict, first_seen: str, company_id: str) -> dict:
    """
    모든 matching tier를 누적 적용.
    - severity: 7d+이면 +1, 14d+이면 critical 강제
    - tags: STRUCTURAL_RISK(21d+), LONG_TERM_RISK(30d+) 누적
    - memo: 각 tier memo_flag 순차 추가
    Returns new dict (원본 불변).
    """
    gap  = dict(gap)
    days = days_since(first_seen)

    orig_sev    = gap.get("severity", "medium")
    current_sev = orig_sev
    all_tags    = list(gap.get("tags", []))
    memo_flags  = []
    top_tier    = None

    for threshold, rule in ESCALATION_LADDER:
        if days < threshold:
            break
        top_tier = threshold
        if rule["severity_bump"]:
            current_sev = bump_severity(current_sev, rule["severity_bump"])
        if rule["force_critical"]:
            current_sev = floor_severity(current_sev, "critical")
        for tag in rule["tags"]:
            if tag not in all_tags:
                all_tags.append(tag)
        if rule["memo_flag"] not in memo_flags:
            memo_flags.append(rule["memo_flag"])

    gap["severity"]        = current_sev
    gap["tags"]            = all_tags
    gap["escalation_days"] = days
    gap["escalation_tier"] = top_tier
    gap["first_seen"]      = first_seen

    if memo_flags:
        base = (gap.get("memo") or "").rstrip()
        gap["memo"] = base + ("  " if base else "") + "  ".join(memo_flags)

    # 콘솔 로그
    if top_tier is not None:
        changed = (current_sev != orig_sev) or bool(all_tags)
        verb    = "ESCALATED" if changed else "escalation"
        print(
            f"  [{verb:10s}] {company_id:18s} rule={gap.get('rule_id','?'):20s} "
            f"days={days:2d}d  tier={top_tier:2d}  "
            f"sev: {orig_sev}→{current_sev}  tags={all_tags or '—'}"
        )
    else:
        if days > 0:
            print(
                f"  [no-esc      ] {company_id:18s} rule={gap.get('rule_id','?'):20s} "
                f"days={days:2d}d (<7d threshold)"
            )

    return gap


# ═════════════════════════════════════════════════════════════════════════
# Stage Promotion
# ═════════════════════════════════════════════════════════════════════════

def compute_stage(company_id: str, current_stage: str, events: list[dict]) -> tuple[str, float, str]:
    """
    high-confidence 이벤트의 가중치 합산으로 stage 결정.
    hard rule: Contract/Deployment 개수 → 최소 보장 stage.
    절대 강등하지 않음 (no demotion).
    Returns (new_stage, score, reason).
    """
    score    = 0.0
    cd_count = 0
    type_tally: dict[str, int] = {}

    for ev in events:
        # high 또는 medium confidence 모두 반영 (low는 0.3배)
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
        if score >= STAGE_SCORE_THRESHOLD[stage]:
            score_stage = stage

    # hard rule (Contract/Deployment 개수)
    hard_floor  = "Lab"
    hard_reason = ""
    for min_cd, floor_stage in sorted(CD_HARD_RULE.items(), reverse=True):
        if cd_count >= min_cd:
            hard_floor  = floor_stage
            hard_reason = f"hard-rule: {cd_count}×CD≥{min_cd}→≥{floor_stage}"
            break

    # 최종: score_stage, hard_floor, current_stage 중 최대 (강등 없음)
    new_stage = max(
        [score_stage, hard_floor, current_stage],
        key=lambda s: STAGE_IDX.get(s, 0),
    )

    reason = (
        f"score={score:.1f}  cd={cd_count}  types={type_tally}  "
        f"score_stage={score_stage}  hard_floor={hard_floor}  prev={current_stage}  {hard_reason}"
    ).strip()

    if new_stage != current_stage:
        print(
            f"  [STAGE UP ▲  ] {company_id:18s}  "
            f"{current_stage} → {new_stage}  (score={score:.1f}  cd={cd_count})"
        )
    else:
        # 다음 stage까지 필요 점수 표시
        cur_idx  = STAGE_IDX.get(current_stage, 0)
        next_s   = STAGE_ORDER[min(cur_idx + 1, len(STAGE_ORDER) - 1)]
        need     = STAGE_SCORE_THRESHOLD.get(next_s, 999)
        print(
            f"  [STAGE HOLD  ] {company_id:18s}  {current_stage:18s}  "
            f"score={score:.1f}  need {need:.1f} for {next_s}  cd={cd_count}"
        )

    return new_stage, round(score, 2), reason


# ═════════════════════════════════════════════════════════════════════════
# blocker_score
# ═════════════════════════════════════════════════════════════════════════

def compute_blocker_score(gaps: list[dict]) -> int:
    total = 0
    for g in gaps:
        sev   = g.get("severity", "low")
        tier  = g.get("escalation_tier")
        total += BLOCKER_SEV.get(sev, 1) + BLOCKER_TIER_BONUS.get(tier, 0)
    return total


# ═════════════════════════════════════════════════════════════════════════
# 핵심 처리: 회사 1개
# ═════════════════════════════════════════════════════════════════════════

def process_company(
    company_id:  str,
    co_data:     dict,
    gap_log:     dict,
) -> dict:
    """
    co_data: generate-signals.py가 생성한 enriched company dict
    gap_log: 전체 gap 이력 dict (mutated in-place)
    Returns: 업데이트된 co_data
    """
    print(f"\n┌── {company_id} ──────────────────────────────────")

    events      = co_data.get("events", [])
    raw_gaps    = co_data.get("gaps",   [])
    cur_stage   = co_data.get("stage_label") or co_data.get("stage", "Lab")

    # ── 1. Gap log 업데이트 ────────────────────────────────────────────
    print(f"│ [1/4] Gap log 업데이트 (오늘 gaps={len(raw_gaps)})")
    update_gap_log(gap_log, company_id, raw_gaps)

    # ── 2. Gap escalation ─────────────────────────────────────────────
    print(f"│ [2/4] Gap escalation")
    company_log    = gap_log.get(company_id, {})
    enriched_gaps  = []

    for gap in raw_gaps:
        rid   = gap.get("rule_id")
        entry = company_log.get(rid) if rid else None
        fs    = (
            entry["first_seen"]
            if entry and not entry.get("resolved")
            else gap.get("first_seen") or TODAY
        )
        enriched_gaps.append(escalate_gap(gap, fs, company_id))

    # critical 먼저, 그 다음 escalation_days 내림차순
    enriched_gaps.sort(key=lambda g: (
        -SEVERITY_IDX.get(g.get("severity", "low"), 0),
        -(g.get("escalation_days") or 0),
    ))

    # ── 3. Stage 승급 ─────────────────────────────────────────────────
    print(f"│ [3/4] Stage 승급 (current={cur_stage}  events={len(events)})")
    new_stage, stage_score, stage_reason = compute_stage(company_id, cur_stage, events)

    # ── 4. blocker_score + structural_tags ────────────────────────────
    print(f"│ [4/4] Risk 집계")
    critical_cnt   = sum(1 for g in enriched_gaps if g.get("severity") == "critical")
    structural_tags = sorted({
        tag
        for g in enriched_gaps
        for tag in g.get("tags", [])
    })
    blocker_score  = compute_blocker_score(enriched_gaps)

    print(
        f"│      blocker={blocker_score}  critical_gaps={critical_cnt}  "
        f"struct_tags={structural_tags or 'none'}"
    )

    # ── co_data 업데이트 ──────────────────────────────────────────────
    co_data["gaps"]             = enriched_gaps
    co_data["stage_label"]      = new_stage
    co_data["stage_previous"]   = cur_stage
    co_data["stage_score"]      = stage_score
    co_data["stage_reason"]     = stage_reason
    co_data["blocker_score"]    = blocker_score
    co_data["critical_gaps"]    = critical_cnt
    co_data["structural_tags"]  = structural_tags
    co_data["profile_date"]     = TODAY
    co_data["profile_version"]  = "7.0"

    print(
        f"└── DONE: stage={new_stage} (prev={cur_stage})  "
        f"blocker={blocker_score}  crit={critical_cnt}  tags={structural_tags or 'none'}"
    )
    return co_data


# ═════════════════════════════════════════════════════════════════════════
# 메인 파이프라인
# ═════════════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{'═'*62}")
    print(f"  build_company_profile.py  v7.0   {TODAY}")
    print(f"{'═'*62}\n")

    # ── latest.json 로드 ──────────────────────────────────────────────
    if not LATEST_PATH.exists():
        print(f"[ERROR] {LATEST_PATH} 없음 — generate-signals.py를 먼저 실행하세요.")
        sys.exit(1)

    try:
        payload = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] latest.json 파싱 실패: {e}")
        sys.exit(1)

    companies: dict = payload.get("companies", {})
    if not companies:
        print("[WARN] companies 섹션이 비어있음 — 처리할 항목 없음")
        sys.exit(0)

    print(f"[LOAD] {LATEST_PATH}  →  {len(companies)} 회사\n")

    # ── gap_log 로드 ──────────────────────────────────────────────────
    gap_log = load_gap_log()
    print()

    # ── 회사별 처리 ───────────────────────────────────────────────────
    summary_rows = []

    for company_id, co_data in companies.items():
        updated = process_company(company_id, co_data, gap_log)
        companies[company_id] = updated
        summary_rows.append({
            "id":      company_id,
            "name":    co_data.get("name", company_id),
            "stage":   updated["stage_label"],
            "prev":    updated.get("stage_previous", "—"),
            "up":      updated["stage_label"] != updated.get("stage_previous", updated["stage_label"]),
            "blocker": updated["blocker_score"],
            "crit":    updated["critical_gaps"],
            "tags":    updated["structural_tags"],
        })

    # ── latest.json 덮어쓰기 ─────────────────────────────────────────
    payload["companies"]         = companies
    payload["profile_built_at"]  = datetime.now(timezone.utc).isoformat()
    payload["profile_version"]   = "7.0"

    LATEST_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[SAVE] {LATEST_PATH} 업데이트 완료")

    # ── gap_log 저장 ──────────────────────────────────────────────────
    save_gap_log(gap_log)

    # ── 요약 테이블 ───────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print(f"  {'회사':20s} {'stage (prev→new)':22s} {'blocker':>8} {'crit':>6}  struct_tags")
    print(f"  {'─'*68}")
    for r in summary_rows:
        arrow = f"{r['prev']}→{r['stage']}" if r["up"] else r["stage"]
        tags  = ", ".join(r["tags"]) if r["tags"] else "—"
        print(f"  {r['name']:20s} {arrow:22s} {r['blocker']:>8d} {r['crit']:>6d}  {tags}")
    print(f"  {'─'*68}")

    promotions  = sum(1 for r in summary_rows if r["up"])
    high_risk   = sum(1 for r in summary_rows if r["blocker"] >= 20)
    struct_risk = sum(1 for r in summary_rows if "STRUCTURAL_RISK" in r["tags"])

    print(
        f"  처리={len(summary_rows)}  승급={promotions}  "
        f"high-risk(≥20)={high_risk}  STRUCTURAL_RISK={struct_risk}"
    )
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    main()

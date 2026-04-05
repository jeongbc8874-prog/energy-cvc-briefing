"""
build_company_profile.py  v6.0
Energy CVC Intelligence Platform — Phase 2 (Production-grade)

━━━ v5.0 대비 핵심 버그 수정 ━━━

[BUG 1] escalate_gap: highest 단일 적용 → 모든 threshold 누적 적용으로 변경
  - 34일 경과 시 21d(STRUCTURAL_RISK) + 30d(LONG_TERM_RISK) 동시 부착
  - 7d 이상: severity +1  /  14d 이상: severity forced critical (누적)
  - memo_flag도 해당되는 모든 tier 문구 순차 추가

[BUG 2] escalate_gap threshold: highest만 보던 것 → sorted ladder 전체 순회로 변경

[BUG 3] gap_log first_seen 소실 문제
  - gap_log.json 없는 첫 실행 시 모든 first_seen = today → escalation 0d → 미적용
  - 해결: gaps 파일 자체에 first_seen 필드 포함 가능
  - GapLog.update()에서 우선순위: ① 기존 gap_log entry ② gap 파일 first_seen ③ today

[BUG 4] stage threshold: cumulative while loop 오류
  - "steps_needed = new_idx+1" 방식 → 직관적인 절대 score threshold 맵으로 교체
  - Stage: Lab(0) → Demo(5.0) → Pilot(12.0) → First Commercial(22.0) → Scale(35.0)
  - hard rule: Contract/Deployment ≥ 2개 → 최소 Pilot 보장

━━━ 추가 개선 ━━━
  • blocker_score: 장기 미해결 gap에 escalation_tier 기반 추가 가중
  • absent_streak: 3일 연속 absent만 resolved (유지)
  • structural_tags: 회사 레벨에서 모든 gap의 태그 집합
  • Funding / Buyer Activity 추출 (유지)
  • 콘솔 로그: 각 단계별 상세 진단 출력
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("build_company_profile")

# ─────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────
TODAY = date.today()

# ── Stage ladder ──────────────────────────────────────────
STAGES = ["Lab", "Demo", "Pilot", "First Commercial", "Scale"]
STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}

# Absolute weighted-score thresholds to reach each stage
# (score = sum of EVENT_WEIGHTS for all high-confidence signals)
STAGE_THRESHOLDS: dict[str, float] = {
    "Lab":             0.0,
    "Demo":            5.0,
    "Pilot":          12.0,
    "First Commercial": 22.0,
    "Scale":          35.0,
}

# Hard rule: Contract OR Deployment ≥ N → minimum stage enforced
CONTRACT_DEPLOY_HARD_RULE: dict[int, str] = {
    2: "Pilot",            # ≥2 → at least Pilot
    4: "First Commercial", # ≥4 → at least First Commercial
}

# Event-type weights (applied only to high-confidence signals)
EVENT_WEIGHTS: dict[str, float] = {
    "Contract":         3.0,
    "Deployment":       3.0,
    "Certification":    2.5,
    "Pilot":            2.0,
    "Partnership":      1.5,
    "Grant":            1.5,
    "Funding":          1.5,
    "Product_Launch":   1.5,
    "Patent":           1.0,
    "Publication":      0.5,
    "Conference":       0.5,
    "Hiring":           0.5,
}

# ── Severity ──────────────────────────────────────────────
SEVERITY_ORDER = ["low", "medium", "high", "critical"]
SEVERITY_INDEX = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# ── Gap escalation ladder (cumulative — ALL matching tiers applied) ──
# Each tier applies its rule IN ADDITION to all lower tiers.
ESCALATION_LADDER: list[tuple[int, dict]] = [
    (7,  {
        "severity_bump": 1,        # +1 step (low→medium, medium→high, high→critical)
        "force_severity": None,
        "tags": [],
        "memo_flag": "[7d+ PERSISTING]",
    }),
    (14, {
        "severity_bump": 0,
        "force_severity": "critical",
        "tags": [],
        "memo_flag": "[14d+ UNRESOLVED → CRITICAL]",
    }),
    (21, {
        "severity_bump": 0,
        "force_severity": "critical",
        "tags": ["STRUCTURAL_RISK"],
        "memo_flag": "[21d+ Long-term structural issue]",
    }),
    (30, {
        "severity_bump": 0,
        "force_severity": "critical",
        "tags": ["STRUCTURAL_RISK", "LONG_TERM_RISK"],
        "memo_flag": "[30d+ LONG-TERM RISK — escalated to blocker]",
    }),
]

# blocker_score weights
BLOCKER_SEVERITY_WEIGHT = {
    "low":      1,
    "medium":   2,
    "high":     4,
    "critical": 8,
}
BLOCKER_TIER_BONUS = {
    7:  1,
    14: 3,
    21: 6,
    30: 12,
}

# Resolved only after N consecutive absent days
RESOLVED_CONSECUTIVE_DAYS = 3

# ─────────────────────────────────────────────────────────
# Paths  (override via env-var in CI)
# ─────────────────────────────────────────────────────────
BASE_DIR     = Path(os.environ.get("BASE_DIR", "data"))
SIGNALS_DIR  = BASE_DIR / "signals"
GAPS_DIR     = BASE_DIR / "gaps"
PROFILES_DIR = BASE_DIR / "profiles"
GAP_LOG_PATH = BASE_DIR / "gap_log.json"

PROFILES_DIR.mkdir(parents=True, exist_ok=True)


# ═════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════

def _date_str(d: date) -> str:
    return d.isoformat()


def _days_since(iso_date: str) -> int:
    """Inclusive calendar days from iso_date to TODAY. Returns 0 on error."""
    try:
        return max(0, (TODAY - date.fromisoformat(iso_date)).days)
    except (ValueError, TypeError):
        return 0


def _bump_severity(current: str, bump: int) -> str:
    idx = SEVERITY_INDEX.get(current, 0)
    return SEVERITY_ORDER[min(idx + bump, len(SEVERITY_ORDER) - 1)]


def _min_severity(current: str, floor: str) -> str:
    """Ensure severity is at least `floor`."""
    if SEVERITY_INDEX.get(current, 0) < SEVERITY_INDEX.get(floor, 0):
        return floor
    return current


# ═════════════════════════════════════════════════════════
# GapLog — persistent history across daily runs
# ═════════════════════════════════════════════════════════

class GapLog:
    """
    gap_log.json schema:
    {
      "<company_id>": {
        "<rule_id>": {
          "first_seen":    "YYYY-MM-DD",   ← never overwritten once set
          "last_seen":     "YYYY-MM-DD",
          "absent_streak": int,
          "resolved":      bool,
          "resolved_date": "YYYY-MM-DD" | null
        }
      }
    }

    first_seen priority on initial creation:
      1. Existing gap_log entry (preserved across runs)
      2. gap["first_seen"] field in today's gaps file  ← allows backfill
      3. TODAY  (genuinely new gap)
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict[str, dict]] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
                log.info(
                    "  [GAP_LOG] Loaded %s — %d companies tracked",
                    path, len(self.data)
                )
            except json.JSONDecodeError:
                log.warning("  [GAP_LOG] Corrupt gap_log.json — starting fresh")
        else:
            log.info("  [GAP_LOG] No existing gap_log.json — will create fresh")

    # ── daily update ─────────────────────────────────────

    def update(self, company_id: str, today_gaps: list[dict]) -> None:
        """
        Call once per company per run with today's raw gap list.
        Mutates self.data in place.
        """
        company_log = self.data.setdefault(company_id, {})
        today_str   = _date_str(TODAY)
        today_ids   = {g["rule_id"] for g in today_gaps if "rule_id" in g}

        # ── gaps present today ────────────────────────────
        for gap in today_gaps:
            rid = gap.get("rule_id")
            if not rid:
                continue

            existing = company_log.get(rid)
            if existing is None:
                # New gap — use backfill first_seen if provided in gaps file
                backfill_fs = gap.get("first_seen") or today_str
                company_log[rid] = {
                    "first_seen":    backfill_fs,
                    "last_seen":     today_str,
                    "absent_streak": 0,
                    "resolved":      False,
                    "resolved_date": None,
                }
                age = _days_since(backfill_fs)
                log.info(
                    "  [GAP NEW]     company=%-20s rule=%-20s first_seen=%s (age=%dd)",
                    company_id, rid, backfill_fs, age
                )
            else:
                existing["last_seen"]     = today_str
                existing["absent_streak"] = 0
                if existing.get("resolved"):
                    existing["resolved"]      = False
                    existing["resolved_date"] = None
                    log.info(
                        "  [GAP REOPEN]  company=%-20s rule=%-20s (was resolved, now active again)",
                        company_id, rid
                    )

        # ── gaps absent today ─────────────────────────────
        for rid, entry in company_log.items():
            if rid in today_ids or entry.get("resolved"):
                continue
            entry["absent_streak"] = entry.get("absent_streak", 0) + 1
            streak = entry["absent_streak"]
            if streak >= RESOLVED_CONSECUTIVE_DAYS:
                entry["resolved"]      = True
                entry["resolved_date"] = today_str
                log.info(
                    "  [GAP RESOLVED] company=%-20s rule=%-20s (absent %dd ≥ %d → resolved)",
                    company_id, rid, streak, RESOLVED_CONSECUTIVE_DAYS
                )
            else:
                log.info(
                    "  [GAP ABSENT]   company=%-20s rule=%-20s (absent_streak=%d/%d)",
                    company_id, rid, streak, RESOLVED_CONSECUTIVE_DAYS
                )

    # ── accessors ────────────────────────────────────────

    def get_entry(self, company_id: str, rule_id: str) -> dict | None:
        return self.data.get(company_id, {}).get(rule_id)

    def active_entries(self, company_id: str) -> dict[str, dict]:
        return {
            rid: e
            for rid, e in self.data.get(company_id, {}).items()
            if not e.get("resolved")
        }

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, default=str))
        log.info("  [GAP_LOG] Saved → %s", self.path)


# ═════════════════════════════════════════════════════════
# Gap Escalation Engine
# ═════════════════════════════════════════════════════════

def escalate_gap(gap: dict, first_seen: str, company_id: str) -> dict:
    """
    Apply the FULL escalation ladder (all matching tiers, cumulative).
    Returns a new dict — original is not mutated.

    Escalation rules:
      ≥7d   : severity +1 step
      ≥14d  : severity forced to critical; memo += [14d+ UNRESOLVED → CRITICAL]
      ≥21d  : STRUCTURAL_RISK tag; memo += [21d+ Long-term structural issue]
      ≥30d  : LONG_TERM_RISK tag; memo += [30d+ LONG-TERM RISK]; blocker bonus ×2
    All tag/memo additions are cumulative across tiers.
    """
    gap = dict(gap)  # shallow copy
    days = _days_since(first_seen)

    original_severity = gap.get("severity", "medium")
    current_severity  = original_severity
    accumulated_tags  = list(gap.get("tags", []))
    memo_flags: list[str] = []
    highest_tier: int | None = None

    for threshold, rule in ESCALATION_LADDER:
        if days < threshold:
            break
        highest_tier = threshold

        # severity
        if rule["severity_bump"]:
            current_severity = _bump_severity(current_severity, rule["severity_bump"])
        if rule["force_severity"]:
            current_severity = _min_severity(current_severity, rule["force_severity"])

        # tags (accumulate, no duplicates)
        for tag in rule["tags"]:
            if tag not in accumulated_tags:
                accumulated_tags.append(tag)

        # memo flag
        if rule["memo_flag"] and rule["memo_flag"] not in memo_flags:
            memo_flags.append(rule["memo_flag"])

    # Apply to gap
    gap["severity"]        = current_severity
    gap["tags"]            = accumulated_tags
    gap["escalation_days"] = days
    gap["escalation_tier"] = highest_tier
    gap["first_seen"]      = first_seen

    if memo_flags:
        gap["memo"] = (gap.get("memo") or "").rstrip() + "  " + "  ".join(memo_flags)

    # Console log
    if highest_tier is not None:
        severity_changed = (current_severity != original_severity)
        tag_str = str(accumulated_tags) if accumulated_tags else "—"
        if severity_changed or accumulated_tags:
            log.info(
                "  [ESCALATED]   company=%-20s rule=%-20s "
                "days=%2dd  tier=%2d  %s→%s  tags=%s",
                company_id,
                gap.get("rule_id", "?"),
                days,
                highest_tier,
                original_severity,
                current_severity,
                tag_str,
            )
        else:
            log.info(
                "  [ESCALATION]  company=%-20s rule=%-20s "
                "days=%2dd  tier=%2d  severity=%s (no change)",
                company_id,
                gap.get("rule_id", "?"),
                days,
                highest_tier,
                current_severity,
            )
    else:
        log.info(
            "  [NO ESCALATION] company=%-20s rule=%-20s days=%2dd (<7d threshold)",
            company_id, gap.get("rule_id", "?"), days
        )

    return gap


# ═════════════════════════════════════════════════════════
# Stage Promotion Engine
# ═════════════════════════════════════════════════════════

def compute_stage(
    company_id: str,
    current_stage: str,
    signals: list[dict],
) -> tuple[str, float, str]:
    """
    Compute the promoted stage using:
      1. Weighted score of high-confidence signals vs STAGE_THRESHOLDS
      2. Hard rule: Contract/Deployment count → minimum stage floor

    Returns: (new_stage, weighted_score, reason_string)
    """
    score      = 0.0
    high_count = 0
    cd_count   = 0
    type_tally: dict[str, int] = {}

    for sig in signals:
        if sig.get("confidence") != "high":
            continue
        etype  = sig.get("event_type", "Unknown")
        weight = EVENT_WEIGHTS.get(etype, 0.5)
        score += weight
        high_count += 1
        type_tally[etype] = type_tally.get(etype, 0) + 1
        if etype in ("Contract", "Deployment"):
            cd_count += 1

    # ── Score-based stage ─────────────────────────────────
    score_stage = "Lab"
    for stage in STAGES:
        if score >= STAGE_THRESHOLDS[stage]:
            score_stage = stage
        else:
            break

    # ── Hard rule floor ───────────────────────────────────
    hard_floor   = current_stage  # never demote
    hard_reason  = ""
    for min_cd, floor_stage in sorted(CONTRACT_DEPLOY_HARD_RULE.items(), reverse=True):
        if cd_count >= min_cd:
            hard_floor  = floor_stage
            hard_reason = f"[hard-rule: {cd_count}× contract/deploy ≥{min_cd} → ≥{floor_stage}]"
            break

    # Final: highest of score_stage, hard_floor, current_stage (no demotion)
    candidates  = [score_stage, hard_floor, current_stage]
    new_stage   = max(candidates, key=lambda s: STAGE_INDEX.get(s, 0))

    reason = (
        f"score={score:.1f}  high_signals={high_count}  cd_signals={cd_count}  "
        f"types={type_tally}  "
        f"score_stage={score_stage}  hard_floor={hard_floor}  "
        f"prev={current_stage}  {hard_reason}"
    ).strip()

    # Console log
    if new_stage != current_stage:
        log.info(
            "  [STAGE UP]    company=%-20s %s → %s  (score=%.1f  cd=%d)",
            company_id, current_stage, new_stage, score, cd_count
        )
        log.info("  [STAGE UP]    reason: %s", reason)
    else:
        log.info(
            "  [STAGE HOLD]  company=%-20s %s  (score=%.1f  cd=%d  need=%.1f for next)",
            company_id,
            current_stage,
            score,
            cd_count,
            STAGE_THRESHOLDS.get(STAGES[min(STAGE_INDEX[current_stage]+1, len(STAGES)-1)], 999),
        )

    return new_stage, score, reason


# ═════════════════════════════════════════════════════════
# Funding History & Buyer Activity
# ═════════════════════════════════════════════════════════

def extract_funding_history(signals: list[dict]) -> list[dict]:
    rounds = []
    for sig in signals:
        if sig.get("event_type") != "Funding":
            continue
        rounds.append({
            "date":       sig.get("signal_date") or sig.get("date", ""),
            "amount_usd": sig.get("amount_usd"),        # None = unverified
            "round_type": sig.get("round_type", "Unknown"),
            "investors":  sig.get("investors", []),
            "source":     sig.get("source_name", ""),
            "source_url": sig.get("source_url", ""),
            "verified":   sig.get("verified", False),
        })
    rounds.sort(key=lambda r: r["date"], reverse=True)
    return rounds


def extract_buyer_activity(signals: list[dict]) -> list[dict]:
    activities = []
    for sig in signals:
        if sig.get("event_type") not in ("Contract", "Deployment", "Partnership"):
            continue
        activities.append({
            "date":         sig.get("signal_date") or sig.get("date", ""),
            "event_type":   sig.get("event_type"),
            "counterparty": sig.get("counterparty") or sig.get("entity_name", "Unknown"),
            "sector":       sig.get("sector", ""),
            "geography":    sig.get("geography", ""),
            "source":       sig.get("source_name", ""),
            "source_url":   sig.get("source_url", ""),
            "confidence":   sig.get("confidence", "medium"),
        })
    activities.sort(key=lambda a: a["date"], reverse=True)
    return activities


# ═════════════════════════════════════════════════════════
# blocker_score
# ═════════════════════════════════════════════════════════

def compute_blocker_score(enriched_gaps: list[dict]) -> int:
    """
    Weighted score reflecting investment risk from unresolved gaps.

    Per gap:
      base   = BLOCKER_SEVERITY_WEIGHT[severity]
      bonus  = BLOCKER_TIER_BONUS[escalation_tier]  (if escalated)
      total += base + bonus
    """
    total = 0
    for gap in enriched_gaps:
        sev   = gap.get("severity", "low")
        tier  = gap.get("escalation_tier")
        base  = BLOCKER_SEVERITY_WEIGHT.get(sev, 1)
        bonus = BLOCKER_TIER_BONUS.get(tier, 0) if tier else 0
        total += base + bonus
    return total


# ═════════════════════════════════════════════════════════
# Core Profile Builder
# ═════════════════════════════════════════════════════════

def build_profile(
    company_id: str,
    raw_meta:   dict,
    signals:    list[dict],
    raw_gaps:   list[dict],
    gap_log:    GapLog,
) -> dict:
    log.info("")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("  COMPANY: %s", company_id)
    log.info("  signals=%d  raw_gaps=%d", len(signals), len(raw_gaps))
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── 1. Update gap log ─────────────────────────────────
    log.info("  ── [1/5] Updating GapLog ──")
    gap_log.update(company_id, raw_gaps)

    # ── 2. Stage promotion ────────────────────────────────
    log.info("  ── [2/5] Stage Promotion ──")
    current_stage               = raw_meta.get("stage", "Lab")
    new_stage, score, stage_rsn = compute_stage(company_id, current_stage, signals)

    # ── 3. Gap escalation ─────────────────────────────────
    log.info("  ── [3/5] Gap Escalation ──")
    active_entries = gap_log.active_entries(company_id)
    enriched_gaps: list[dict] = []

    for gap in raw_gaps:
        rid   = gap.get("rule_id")
        entry = active_entries.get(rid) if rid else None
        fs    = entry["first_seen"] if entry else (gap.get("first_seen") or _date_str(TODAY))
        enriched_gaps.append(escalate_gap(gap, fs, company_id))

    # Sort: critical first, then by escalation_days desc
    enriched_gaps.sort(key=lambda g: (
        -SEVERITY_INDEX.get(g.get("severity", "low"), 0),
        -(g.get("escalation_days") or 0),
    ))

    # ── 4. Aggregate risk metrics ─────────────────────────
    log.info("  ── [4/5] Risk Aggregation ──")
    critical_count  = sum(1 for g in enriched_gaps if g.get("severity") == "critical")
    structural_tags = sorted({
        tag
        for g in enriched_gaps
        for tag in g.get("tags", [])
    })
    blocker_score = compute_blocker_score(enriched_gaps)

    log.info(
        "  [RISK]  blocker_score=%-4d  critical_gaps=%d  structural_tags=%s",
        blocker_score, critical_count, structural_tags or "none"
    )

    # ── 5. Funding + Buyer Activity ───────────────────────
    log.info("  ── [5/5] Enrichment (Funding / Buyer) ──")
    funding_history = extract_funding_history(signals)
    buyer_activity  = extract_buyer_activity(signals)
    log.info(
        "  [ENRICH] funding_rounds=%d  buyer_events=%d",
        len(funding_history), len(buyer_activity)
    )

    # ── Assemble profile ──────────────────────────────────
    profile = {
        # Identity
        "company_id":   company_id,
        "name":         raw_meta.get("name", company_id),
        "sector":       raw_meta.get("sector", ""),
        "sub_sector":   raw_meta.get("sub_sector", ""),
        "hq":           raw_meta.get("hq", ""),
        "founded":      raw_meta.get("founded"),
        "website":      raw_meta.get("website", ""),

        # Stage
        "stage":          new_stage,
        "stage_previous": current_stage,
        "stage_score":    round(score, 2),
        "stage_reason":   stage_rsn,

        # Signals
        "signal_count":     len(signals),
        "high_signals":     sum(1 for s in signals if s.get("confidence") == "high"),
        "last_signal_date": max(
            (s.get("signal_date", "") for s in signals), default=""
        ),

        # Gaps
        "active_gap_count":   len(enriched_gaps),
        "critical_gap_count": critical_count,
        "blocker_score":      blocker_score,
        "structural_tags":    structural_tags,
        "gaps":               enriched_gaps,

        # Enrichment
        "funding_history": funding_history,
        "buyer_activity":  buyer_activity,

        # Meta
        "profile_date":    _date_str(TODAY),
        "profile_version": "6.0",
    }

    log.info(
        "  [DONE]  stage=%s (prev=%s)  gaps=%d(crit=%d)  "
        "blocker=%d  struct_tags=%s",
        new_stage, current_stage,
        len(enriched_gaps), critical_count,
        blocker_score,
        structural_tags or "none",
    )
    return profile


# ═════════════════════════════════════════════════════════
# File I/O
# ═════════════════════════════════════════════════════════

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        log.error("JSON parse error in %s: %s", path, exc)
        return None


def save_profile(profile: dict) -> None:
    path = PROFILES_DIR / f"{profile['company_id']}.json"
    path.write_text(json.dumps(profile, indent=2, default=str))
    log.info("  Profile saved → %s", path)


# ═════════════════════════════════════════════════════════
# Pipeline entry point
# ═════════════════════════════════════════════════════════

def run_pipeline(company_ids: list[str] | None = None) -> None:
    """
    Daily pipeline entry point.

    Directory layout expected:
      data/signals/<company_id>.json   → list of signal dicts
      data/gaps/<company_id>_gaps.json → list of gap dicts (may include first_seen)
      data/profiles/<company_id>_meta.json → {stage, name, sector, ...}
      data/gap_log.json                → auto-managed

    CLI usage:
      python build_company_profile.py                        # all companies
      python build_company_profile.py form_energy amogy      # specific
    """
    log.info("═══ build_company_profile.py v6.0 ═══  date=%s", _date_str(TODAY))

    gap_log = GapLog(GAP_LOG_PATH)

    if company_ids is None:
        company_ids = sorted(p.stem for p in SIGNALS_DIR.glob("*.json"))

    if not company_ids:
        log.warning("No company signal files found in %s", SIGNALS_DIR)
        return

    log.info("Pipeline start — %d companies: %s", len(company_ids), company_ids)

    summary_rows: list[dict] = []
    processed = 0

    for cid in company_ids:
        signals  = load_json(SIGNALS_DIR  / f"{cid}.json")          or []
        raw_gaps = load_json(GAPS_DIR     / f"{cid}_gaps.json")      or []
        raw_meta = load_json(PROFILES_DIR / f"{cid}_meta.json")      or {"stage": "Lab"}

        if not signals and not raw_gaps:
            log.warning("  SKIP %s — no data files", cid)
            continue

        profile = build_profile(cid, raw_meta, signals, raw_gaps, gap_log)
        save_profile(profile)
        processed += 1

        summary_rows.append({
            "company":       cid,
            "stage":         profile["stage"],
            "prev_stage":    profile["stage_previous"],
            "promoted":      profile["stage"] != profile["stage_previous"],
            "blocker":       profile["blocker_score"],
            "critical_gaps": profile["critical_gap_count"],
            "struct_tags":   profile["structural_tags"],
        })

    gap_log.save()

    # ── Summary table ──────────────────────────────────────
    log.info("")
    log.info("═══ PIPELINE SUMMARY ═════════════════════════════════════════════")
    log.info(
        "  %-20s %-18s %-8s %-8s %-20s",
        "company", "stage (prev→new)", "blocker", "crit_g", "struct_tags"
    )
    log.info("  " + "─" * 78)
    for row in summary_rows:
        arrow = f"{row['prev_stage']}→{row['stage']}" if row["promoted"] else row["stage"]
        log.info(
            "  %-20s %-18s %-8d %-8d %s",
            row["company"],
            arrow,
            row["blocker"],
            row["critical_gaps"],
            ", ".join(row["struct_tags"]) or "—",
        )
    promotions = [r for r in summary_rows if r["promoted"]]
    log.info("  " + "─" * 78)
    log.info(
        "  Processed: %d/%d  |  Promotions: %d  |  High-risk (blocker≥20): %d",
        processed, len(company_ids),
        len(promotions),
        sum(1 for r in summary_rows if r["blocker"] >= 20),
    )
    log.info("═══════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    target = sys.argv[1:] or None
    run_pipeline(target)

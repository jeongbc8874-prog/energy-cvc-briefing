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
    # ── 안정적 무료 피드 ────────────────────────────────────
    {"id":"utilitydive",      "name":"Utility Dive",        "url":"https://www.utilitydive.com/feeds/news/",        "segments":["grid_sw","ess","dc_power"]},
    {"id":"pvmagazine",       "name":"PV Magazine",          "url":"https://www.pv-magazine.com/feed/",              "segments":["ess","hydrogen","forecasting"]},
    {"id":"energystoragenews","name":"Energy Storage News",  "url":"https://www.energy-storage.news/feed/",          "segments":["ess"]},
    {"id":"offshorewind",     "name":"Offshore Wind Biz",    "url":"https://www.offshorewind.biz/feed/",             "segments":["hvdc","ess"]},
    # ── 교체: Recharge News → Electrek (무료, 안정적) ───────
    # Recharge News = Informa/Riviera 계열, RSS 차단됨
    {"id":"electrek",         "name":"Electrek",             "url":"https://electrek.co/feed/",                      "segments":["ess","dc_power","forecasting"]},
    # ── 교체: Hydrogen Insight → H2 View (무료 수소 전문) ───
    # Hydrogen Insight = 유료 paywall, RSS 접근 차단됨
    {"id":"h2view",           "name":"H2 View",              "url":"https://www.h2-view.com/feed/",                  "segments":["hydrogen","marine_fc"]},
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
    # Tier 4 — 네거티브 (항상 포함, 노이즈 필터 면제)
    {"kws":["delay","postponed","behind schedule","timeline slips","pushed back"],
     "type":"Negative","neg_subtype":"delay",        "impact":"Risk","score":0,"tier":4},
    {"kws":["funding shortfall","struggles to raise","runway concerns","bridge financing"],
     "type":"Negative","neg_subtype":"funding_risk",  "impact":"Risk","score":0,"tier":4},
    {"kws":["cost overrun","over budget","capex increase","higher than expected cost"],
     "type":"Negative","neg_subtype":"cost_overrun",  "impact":"Risk","score":0,"tier":4},
    {"kws":["supply chain issue","component shortage","material shortage","delivery delay"],
     "type":"Negative","neg_subtype":"supply_chain",  "impact":"Risk","score":0,"tier":4},
    {"kws":["hiring freeze","layoffs","redundancies","headcount reduction","staff cuts"],
     "type":"Negative","neg_subtype":"hiring_freeze", "impact":"Risk","score":0,"tier":4},
    {"kws":["project cancelled","contract cancelled","terminated","deal collapsed"],
     "type":"Negative","neg_subtype":"cancellation",  "impact":"Risk","score":0,"tier":4},
    {"kws":["competitor wins","competitor awarded","rival secures","loses contract to"],
     "type":"Negative","neg_subtype":"competitor_win","impact":"Risk","score":0,"tier":4},
    {"kws":["subsidy ends","grant expires","government support withdrawn","policy reversal"],
     "type":"Negative","neg_subtype":"subsidy_risk",  "impact":"Risk","score":0,"tier":4},
]

SEGMENT_KWS = {
    "ess":         ["battery","energy storage","ess","vanadium","iron-air","flow battery","long duration","long-duration"],
    "marine_fc":   ["marine","vessel","ship","fuel cell","dnv","amogy","shipping","seafarer"],
    "grid_sw":     ["vpp","virtual power","demand response","grid software","kepco","ancillary service","frequency regulation"],
    "hvdc":        ["hvdc","transmission","cable","offshore wind","interconnect","subsea cable"],
    "hydrogen":    ["hydrogen","electrolyzer","h2","liquid hydrogen","green hydrogen","electrolysis","fuel cell","pem","soec"],
    "dc_power":    ["data center","hyperscaler","azure","aws","google cloud","power electronics","ups","cooling"],
    "forecasting": ["forecast","prediction","renewable forecast","grid forecast","ai grid"],
}

# ══════════════════════════════════════════════════════════
# 4. SIGNAL SCORING RULEBOOK
# ══════════════════════════════════════════════════════════
# Design principle: every point is explained.
# Each rule has: id, pattern, delta, reason, group (boost/noise/veto)
#
# Score bands:
#   >= 60  → HIGH   (shown by default)
#   35-59  → MEDIUM (shown when filter is "medium")
#   < 35   → LOW    (kept in DB, hidden from main feed)
#   < 20   → NOISE  (dropped entirely, logged in filteredOut)
#
# Negative signals are ALWAYS kept regardless of score.
# ══════════════════════════════════════════════════════════

SCORE_THRESHOLD_HIGH   = 60   # shown in default feed view
SCORE_THRESHOLD_MEDIUM = 35   # shown when user selects "Medium"
SCORE_THRESHOLD_KEEP   = 20   # kept in DB (not shown in feed)
# Below KEEP → dropped to filteredOut log

SCORE_RULES = [
    # ── BOOST: Named buyers (+points) ────────────────────────────────
    # Principle: a named strategic buyer materially de-risks commercial assumptions
    {"id":"buyer_top",    "pattern": r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\be\.on\b",
     "delta":+18, "group":"boost", "reason":"Tier-1 strategic buyer named (utility/hyperscaler)"},
    {"id":"buyer_mid",    "pattern": r"\bhyundai\b|\bsamsung\b|\bhanwha\b|\bshell\b|\bbp\b|\bvattenfal\b|\bsiemens\b|\babb\b",
     "delta":+12, "group":"boost", "reason":"Major industrial/OEM buyer named"},
    {"id":"buyer_kr",     "pattern": r"\bls electric\b|\bls일렉트릭\b|\bsk e&s\b|\bsk에코\b|\bposco\b|\bhyundai\b",
     "delta":+10, "group":"boost", "reason":"Korean strategic buyer named"},

    # ── BOOST: Concrete evidence ──────────────────────────────────────
    {"id":"figure_money", "pattern": r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]",
     "delta":+15, "group":"boost", "reason":"Specific funding amount in text"},
    {"id":"figure_mw",    "pattern": r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b",
     "delta":+10, "group":"boost", "reason":"Specific capacity figure in text"},
    {"id":"timeframe",    "pattern": r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month|by end of 20[2-9]",
     "delta":+8,  "group":"boost", "reason":"Concrete timeframe stated"},
    {"id":"geography",    "pattern": r"\bbusan\b|\bincheon\b|\bulsan\b|\broterdam\b|\bsingapore\b|\bhamburg\b|\baberdeen\b",
     "delta":+5,  "group":"boost", "reason":"Specific project location named"},
    {"id":"company_match","pattern": None,  # applied programmatically when company is matched
     "delta":+10, "group":"boost", "reason":"Event matched to tracked company"},

    # ── NOISE: Vague language ─────────────────────────────────────────
    # These phrases signal intent without commitment — actionability is near zero
    {"id":"n_vague_explore","pattern": r"\bexploring\b.*\bpartner|\blooking to\b.*\bpartner|\bin (early )?discussions\b|\bpotential (partner|collaborat|agreement)\b",
     "delta":-35, "group":"noise", "reason":"Vague exploratory language — no binding commitment"},
    {"id":"n_vague_aims",   "pattern": r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bexpects to\b|\bintends to\b",
     "delta":-20, "group":"noise", "reason":"Forward-looking intent without confirmed action"},
    {"id":"n_could_may",    "pattern": r"\bcould (become|reach|achieve|unlock)\b|\bmay (become|reach|achieve)\b|\bhas the potential\b",
     "delta":-25, "group":"noise", "reason":"Speculative language — unconfirmed outcome"},

    # ── NOISE: Generic PR / Marketing ────────────────────────────────
    # These phrases appear in press releases, not operational updates
    {"id":"n_proud",        "pattern": r"\bproud to (announce|partner|share|present)\b|\bexcited to (announce|share|partner)\b|\bpleased to announce\b|\bthrilled to\b",
     "delta":-40, "group":"noise", "reason":"Generic PR announcement language"},
    {"id":"n_vision",       "pattern": r"\bunveils? (vision|strategy|roadmap|plan)\b|\bsets? out (vision|strategy)\b|\bstrategic vision\b",
     "delta":-30, "group":"noise", "reason":"Vision/strategy announcement without concrete action"},
    {"id":"n_rebrand",      "pattern": r"\brebrands?\b|\bnew (logo|brand|name|website|identity)\b|\blaunch(es|ing)? (website|platform)\b",
     "delta":-55, "group":"noise", "reason":"Rebranding/marketing — zero commercial signal"},

    # ── NOISE: Vanity recognition ─────────────────────────────────────
    {"id":"n_award",        "pattern": r"\bwins? (award|prize)\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b|\bgartner\b|\bfrost.*sullivan\b|\bbloomberg nef award\b",
     "delta":-35, "group":"noise", "reason":"Industry award/recognition — not a commercial signal"},

    # ── NOISE: Conference / Event appearances ─────────────────────────
    # Being at a conference ≠ commercial progress
    {"id":"n_conference",   "pattern": r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b|\battends? (conference|summit|forum)\b|\bpresents? at\b",
     "delta":-30, "group":"noise", "reason":"Conference appearance — not a commercial event"},

    # ── NOISE: Reports / Research ────────────────────────────────────
    {"id":"n_report",       "pattern": r"\bpublishes? (report|study|whitepaper|analysis)\b|\bnew (report|research|analysis|study)\b|\baccording to (a |the )?(report|study|research)\b",
     "delta":-25, "group":"noise", "reason":"Report/research publication — informational only"},

    # ── VETO: Hard drop regardless of base score ──────────────────────
    # If any of these match, signal is dropped even if event_type is high
    {"id":"v_opinion",      "pattern": r"\bopinion:\b|\bcommentary:\b|\bop-ed\b|\banalysis:\b|\bviewpoint:\b",
     "delta":-60, "group":"veto",  "reason":"Opinion/commentary — not a news event"},
    {"id":"v_market_wrap",  "pattern": r"\bmarket (wrap|roundup|update|summary)\b|\bweekly (round-?up|digest)\b|\bmonthly (round-?up|digest)\b",
     "delta":-60, "group":"veto",  "reason":"Market wrap/digest — not a single actionable signal"},
    {"id":"v_job_generic",  "pattern": r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b|\bcareer opportunit\b",
     "delta":-50, "group":"veto",  "reason":"Generic hiring post — not a finance/BD hire signal"},
]

# Readable rulebook for UI transparency panel
SCORE_RULEBOOK_DISPLAY = [
    {"group":"KEPT (always)",     "color":"#16A34A", "items":[
        "Negative signals → always surfaced regardless of score",
        "Certification, Contract, Deployment → base score 85-90",
        "Strategic pilot (utility/hyperscaler/shipyard) → base score 78",
        "CFO / Head of Finance hire → base score 75",
        "Financing round (Series A-E) → base score 80",
    ]},
    {"group":"BOOST (+points)",   "color":"#1A56DB", "items":[
        "Tier-1 strategic buyer named (KEPCO, Microsoft, Google): +18",
        "Major industrial/OEM named (Hyundai, Samsung, Shell): +12",
        "Specific funding amount ($45M, €200M): +15",
        "Specific capacity figure (500MWh, 2GW): +10",
        "Concrete timeframe (Q3 2026, by end of 2026): +8",
        "Event matched to tracked company: +10",
    ]},
    {"group":"NOISE (-points)",   "color":"#D97706", "items":[
        "Vague exploratory language (exploring, in discussions, potential): -35",
        "Forward-looking intent without confirmed action (aims to, plans to): -20",
        "Generic PR language (proud to announce, excited to share): -40",
        "Vision/strategy announcement (unveils strategy, roadmap): -30",
        "Industry award/recognition (Gartner, wins award): -35",
        "Conference/webinar appearance only: -30",
        "Report/research publication: -25",
    ]},
    {"group":"VETO (always drop)","color":"#DC2626", "items":[
        "Opinion/commentary article: -60",
        "Market wrap / weekly digest: -60",
        "Generic job posting (not finance/BD): -50",
        "Rebranding / new logo / new website: -55",
    ]},
    {"group":"THRESHOLDS",        "color":"#6E6E6E", "items":[
        "Score >= 60 → HIGH (shown in default feed)",
        "Score 35-59 → MEDIUM (shown when Medium filter selected)",
        "Score 20-34 → LOW (in DB, not shown in feed)",
        "Score < 20  → DROPPED (logged in filteredOut, not in DB)",
        "Negative signals exempt from threshold — always shown",
    ]},
]

# ══════════════════════════════════════════════════════════
# EVIDENCE CARD LIBRARIES
# Each event type gets a sector-aware "why it matters" explanation
# and a list of what is structurally missing.
# No speculative language. Internal memo tone.
# ══════════════════════════════════════════════════════════

# Why it matters — keyed by (event_type, segment)
# Fallback: (event_type, "default")
WHY_IT_MATTERS = {
    ("Certification", "marine_fc"):   "Class approval (DNV GL / ClassNK) is the single most important commercialization gate for marine fuel cells. Without it, shipyards cannot specify the technology in newbuild contracts. This event, if confirmed, removes the primary procurement barrier.",
    ("Certification", "ess"):         "Third-party certification (UL / IEC / KS) is required for grid interconnection and utility procurement in most regulated markets. Certification de-risks the buyer's liability and accelerates RFP inclusion.",
    ("Certification", "grid_sw"):     "KPX interface certification is the legal prerequisite for participating in Korea's ancillary services market (frequency regulation, DR). This directly unlocks a recurring revenue stream.",
    ("Certification", "hvdc"):        "TÜV / DNV component qualification is required for entry into OEM supply chains (Siemens Energy, ABB, Hitachi Energy). Without it, no grid-scale project procurement is possible.",
    ("Certification", "default"):     "Third-party certification reduces buyer-side risk and is a standard prerequisite for regulated-market procurement. Signal quality depends on which body issued it and for what specific application.",

    ("Contract",      "grid_sw"):     "A named utility contract moves this company from 'pilot-stage' to 'commercial-stage' in the investment framework. Key unknowns: ACV (annual contract value), contract duration, and whether it is a framework or project-specific agreement.",
    ("Contract",      "ess"):         "An offtake or supply agreement with a named buyer is the clearest signal of commercial-stage transition. LCOS (levelized cost of storage) competitiveness is implied but not confirmed without contract terms.",
    ("Contract",      "marine_fc"):   "A named shipyard or shipping company contract following certification is the standard commercialization sequence for marine fuel cells. This represents the first revenue-generating event.",
    ("Contract",      "hydrogen"):    "An offtake agreement is the critical missing link in most hydrogen project theses. Green hydrogen without a named buyer at contracted price remains unviable as an investment.",
    ("Contract",      "default"):     "A commercial contract is the clearest signal of product-market fit and revenue visibility. Terms (ACV, duration, exclusivity) determine whether this is a reference sale or scalable revenue.",

    ("Deployment",    "default"):     "Actual deployment (commissioning, go-live) confirms TRL-9 status and real-world operational performance. This is stronger than a pilot — it represents committed capex from the buyer.",

    ("Pilot",         "grid_sw"):     "A utility-sponsored pilot is significantly stronger than an internal demo. It implies the buyer has allocated opex budget and is evaluating procurement. Conversion rate to commercial contract is the key metric to track.",
    ("Pilot",         "marine_fc"):   "A shipyard-hosted pilot validates that the technology can be integrated into a real vessel architecture. DNV involvement in the pilot substantially increases the probability of subsequent class approval.",
    ("Pilot",         "ess"):         "A grid-connected pilot (vs. behind-the-meter) signals that the company is targeting utility-scale deployment. Grid pilots require NERC/KPX interface compliance, which itself is a commercialization gate.",
    ("Pilot",         "dc_power"):    "A hyperscaler-hosted pilot is the strongest possible commercial signal for data center power technology. Hyperscalers move slowly on procurement decisions but are high-ACV, low-churn customers once contracted.",
    ("Pilot",         "default"):     "A pilot project indicates field-level technical validation. Signal strength depends heavily on who is sponsoring it (utility/OEM vs. government/academic) and whether it is a paid engagement.",

    ("Financing",     "default"):     "An equity financing round confirms external capital validation. Key variables: investor identity (strategic vs. financial), round size relative to capex requirements, and implied valuation relative to revenue run-rate.",

    ("Hiring",        "default"):     "A CFO hire with prior Series B+ experience is empirically correlated with fundraising within 3–6 months. A BD/VP Sales hire signals active contract pipeline building. Neither is confirmatory on its own.",

    ("Partnership",   "default"):     "A named strategic partnership with an industrial buyer is a directional signal. An MOU alone does not confirm commercial intent — the critical variable is whether binding terms (exclusivity, minimum volume, payment) are included.",

    ("Grant",         "default"):     "Government grant funding validates the technology's policy relevance but does not confirm market demand. Non-dilutive capital is positive for the balance sheet, but grant-dependent revenue is not investable without a commercial anchor.",

    ("Negative",      "default"):     "A delay, cost overrun, or competitive displacement event requires reassessment of the investment timeline. The critical distinction is whether the negative signal is project-level (isolated) or structural (market/technology).",

    ("News",          "default"):     "This event did not match a specific investment signal pattern. It is retained for context but should not be weighted in investment assessment without additional corroboration.",
}

# Missing evidence — what is structurally absent for each event type + sector
# Used to populate the "What is missing" field in Evidence Cards
MISSING_BY_TYPE = {
    ("Certification", "marine_fc"):   ["No named shipyard contract confirmed post-certification", "Hydrogen fuel supply chain partner not identified", "Commercial vessel delivery schedule not disclosed"],
    ("Certification", "ess"):         ["No utility offtake agreement accompanying certification", "LCOS ($/kWh) target achievement not confirmed", "Manufacturing scale-up plan not disclosed"],
    ("Certification", "grid_sw"):     ["Certification scope (specific product/service) not confirmed", "Commercial contract with KEPCO or utility not yet disclosed", "Revenue from certified service not quantified"],
    ("Certification", "default"):     ["Commercial application of certification not specified", "Customer or procurement pipeline not disclosed", "Revenue timing from certification unclear"],

    ("Contract",      "default"):     ["Contract ACV (annual contract value) not disclosed", "Contract duration and renewal terms not public", "Exclusivity and geographic scope unknown"],
    ("Deployment",    "default"):     ["Operational performance data (uptime, efficiency) not yet available", "Customer satisfaction and renewal intent not disclosed", "Unit economics at deployment scale not confirmed"],
    ("Pilot",         "default"):     ["Pilot success criteria not publicly defined", "Conversion probability to commercial contract not disclosed", "Pilot sponsor's procurement timeline unknown"],
    ("Financing",     "default"):     ["Post-money valuation not confirmed", "Use of proceeds not specified", "Revenue run-rate at time of raise not public"],
    ("Hiring",        "default"):     ["Fundraising timeline not confirmed", "Whether hire reflects inbound investor interest or proactive preparation unknown", "Compensation structure (equity vs. cash) not disclosed"],
    ("Partnership",   "default"):     ["Binding terms (exclusivity, minimum volume) not confirmed", "MOU-to-contract conversion rate for this partner unknown", "Joint development scope and IP ownership unclear"],
    ("Grant",         "default"):     ["Commercial co-funding partner not identified", "Grant milestones and disbursement schedule not public", "Path from grant to commercial revenue not articulated"],
    ("Negative",      "default"):     ["Root cause of negative event not confirmed", "Management mitigation plan not public", "Impact on existing contracts or investor commitments not disclosed"],
    ("News",          "default"):     ["No investment-relevant pattern matched", "Signal quality insufficient for investment assessment", "Primary research required before forming a view"],
}

# Confidence logic — based on tier, score, and whether company is matched
def compute_confidence(clf_tier, signal_strength, is_matched, is_negative):
    """
    Returns (label, rationale) — no speculation, strictly rule-based.
    """
    if is_negative:
        return "Low", "Negative signals require primary-source verification before forming a view."
    if clf_tier == 1 and signal_strength >= 75 and is_matched:
        return "Medium-High", "Tier-1 event (certification/contract/deployment) with named company match and high score. Awaiting source corroboration."
    if clf_tier == 1 and signal_strength >= 60:
        return "Medium", "Tier-1 event type, but either company unmatched or score modifiers are mixed. Source verification needed."
    if clf_tier == 2 and signal_strength >= 65 and is_matched:
        return "Medium", "Tier-2 event (pilot/hire/financing) with company match. Commercial confirmation absent."
    if clf_tier == 2 and signal_strength >= 50:
        return "Medium-Low", "Tier-2 event without strong score modifiers. Directional signal, not confirmatory."
    if clf_tier <= 3 and signal_strength >= 40:
        return "Low", "Tier-3 event (MOU/grant/partnership) or score below threshold. Not actionable without additional evidence."
    return "Low", "Score below signal threshold or event type is generic. Context only."

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
                return {
                    "type":        rule["type"],
                    "impact":      rule["impact"],
                    "base_score":  rule["score"],
                    "tier":        rule["tier"],
                    "matched":     kw,
                    "neg_subtype": rule.get("neg_subtype"),
                }
    return {"type":"News","impact":"Informational","base_score":15,"tier":5,"matched":None,"neg_subtype":None}

def infer_segment(raw_text, source_segments):
    for seg, kws in SEGMENT_KWS.items():
        if any(kw in raw_text for kw in kws):
            return seg
    return source_segments[0] if source_segments else "unknown"

def score(raw_text, base, is_matched):
    """
    Additive signal scoring engine.
    Every point delta is explained and logged in score_breakdown.

    Returns dict with:
      signal_strength  : 0-100 final score
      signal_tier      : high / medium / low / noise
      score_breakdown  : list of {id, delta, reason} — full audit trail
      is_noise         : True if score < SCORE_THRESHOLD_KEEP
      drop_reason      : reason string if noise, else None
    """
    s        = base + (SCORE_RULES[8]["delta"] if is_matched else 0)  # company_match boost
    breakdown = []

    if is_matched:
        breakdown.append({
            "id":     "company_match",
            "delta":  SCORE_RULES[8]["delta"],
            "reason": SCORE_RULES[8]["reason"],
            "group":  "boost",
        })

    for rule in SCORE_RULES:
        if rule["id"] == "company_match":
            continue  # already handled above
        if rule["pattern"] is None:
            continue
        if re.search(rule["pattern"], raw_text, re.I):
            s += rule["delta"]
            breakdown.append({
                "id":     rule["id"],
                "delta":  rule["delta"],
                "reason": rule["reason"],
                "group":  rule["group"],
            })

    final = max(0, min(100, round(s)))

    if   final >= SCORE_THRESHOLD_HIGH:   tier = "high"
    elif final >= SCORE_THRESHOLD_MEDIUM: tier = "medium"
    elif final >= SCORE_THRESHOLD_KEEP:   tier = "low"
    else:                                 tier = "noise"

    # Drop reason = highest-magnitude penalty applied
    penalties = [b for b in breakdown if b["delta"] < 0]
    penalties.sort(key=lambda x: x["delta"])
    drop_reason = penalties[0]["reason"] if penalties and tier == "noise" else None

    return {
        "signal_strength":  final,
        "signal_tier":      tier,
        "score_breakdown":  breakdown,
        "is_noise":         tier == "noise",
        "drop_reason":      drop_reason,
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

        # ── Evidence Card fields ──────────────────────────────
        # why_it_matters: sector-specific, no speculation
        why_key     = (clf["type"], segment) if (clf["type"], segment) in WHY_IT_MATTERS else (clf["type"], "default")
        why_text    = WHY_IT_MATTERS.get(why_key, WHY_IT_MATTERS.get((clf["type"],"default"), "No sector-specific rationale available."))

        # missing_evidence: structural gaps for this event type
        miss_key    = (clf["type"], segment) if (clf["type"], segment) in MISSING_BY_TYPE else (clf["type"], "default")
        missing     = MISSING_BY_TYPE.get(miss_key, MISSING_BY_TYPE.get((clf["type"],"default"), ["No structured gap analysis available for this event type."]))

        # confidence: rule-based, no guessing
        conf_label, conf_rationale = compute_confidence(clf["tier"], strength["signal_strength"], co_id is not None, is_negative)

        # observed_facts: strictly from source (title + summary excerpt)
        # No inference. No addition. Exactly what the source says.
        obs_fact = item["title"].strip()
        if item["summary"] and len(item["summary"].strip()) > 20:
            # First sentence of summary only — avoid hallucination by trimming
            first_sent = item["summary"].strip().split(".")[0].strip()
            if first_sent and first_sent.lower() != obs_fact.lower() and len(first_sent) > 20:
                obs_fact_detail = first_sent + "."
            else:
                obs_fact_detail = None
        else:
            obs_fact_detail = None

        event = {
            "id":             make_id(item["source_id"], item["title"], item["published_date"]),

            # ── Raw source data (100% fact) ──────────────────
            "title":          item["title"],
            "summary":        item["summary"],
            "event_date":     item["published_date"],
            "source_name":    item["source_name"],
            "source_url":     item["source_url"],

            # ── Classification ────────────────────────────────
            "event_type":     clf["type"],
            "impact_type":    clf["impact"],
            "matched_rule":   clf["matched"],
            "tier":           clf["tier"],
            "signal_stage":   "commercial" if clf["type"] in ("Contract","Certification","Deployment") else
                              "early"      if clf["type"] in ("Pilot","Milestone") else "strategic",

            # ── Scoring ───────────────────────────────────────
            "signal_strength":strength["signal_strength"],
            "signal_tier":    strength["signal_tier"],
            "score_breakdown":strength["score_breakdown"],

            # ── Entity matching ───────────────────────────────
            "segment":        segment,
            "company_id":     co_id,
            "company_name":   co_nm or "Unassigned",
            "is_negative":    is_negative,
            "neg_subtype":    clf["neg_subtype"],
            "is_noise":       strength["is_noise"] and not is_negative,

            # ── Evidence Card fields (mandatory) ─────────────
            "evidence": {
                "observed_fact":       obs_fact,
                "observed_fact_detail":obs_fact_detail,
                "source_label":        f"{item['source_name']} · {item['published_date']}",
                "matched_rule_name":   clf["matched"] or "no rule matched",
                "matched_rule_tier":   f"Tier {clf['tier']} — {clf['type']}",
                "why_it_matters":      why_text,
                "missing_evidence":    missing,
                "confidence":          conf_label,
                "confidence_rationale":conf_rationale,
            },
        }

        if not strength["is_noise"] or is_negative:
            kept.append(event)
        else:
            filtered.append({**event, "drop_reason": strength["drop_reason"] or "score below threshold"})

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
# PANEL BUILDERS
# ══════════════════════════════════════════════════════════

NEG_SUBTYPE_META = {
    "delay":         {"label":"Project / Certification Delay",   "icon":"⏱","severity":"high",    "memo":"Timeline extension increases capital-at-risk. Determine if delay is project-level (isolated) or structural (technology/market)."},
    "funding_risk":  {"label":"Funding / Runway Risk",           "icon":"⚠","severity":"critical","memo":"Capital-constrained signal. Bridge or down-round possible. Monitor existing investor behavior."},
    "cost_overrun":  {"label":"Cost Overrun",                    "icon":"📈","severity":"high",   "memo":"Capex overshoot compresses returns and signals execution risk. Reassess unit economics assumptions."},
    "supply_chain":  {"label":"Supply Chain Issue",              "icon":"🔗","severity":"medium", "memo":"Component shortage can delay deployment timelines. Check if issue is systemic (sector-wide) or isolated (single vendor)."},
    "hiring_freeze": {"label":"Hiring Freeze / Layoffs",         "icon":"👥","severity":"high",   "memo":"Headcount reduction signals cost pressure or strategic pivot. If post-funding, indicates burn rate concern."},
    "cancellation":  {"label":"Project / Contract Cancellation", "icon":"✗", "severity":"critical","memo":"Cancellation removes projected revenue. Determine if demand-side (customer) or supply-side (execution)."},
    "competitor_win":{"label":"Competitor Win",                  "icon":"🏆","severity":"medium", "memo":"Named competitor secured contract in same addressable market. Assess technology and cost differentiation."},
    "subsidy_risk":  {"label":"Subsidy / Policy Risk",           "icon":"🏛","severity":"high",   "memo":"Subsidy-dependent revenue is not investable without commercial anchor. Policy reversal impacts TAM directly."},
}

MISSING_RULES = [
    {
        "id":"no_commercial_contract",
        "label":"No Commercial Contract",
        "check": lambda evs: not any(e["event_type"] in ("Contract","Deployment") for e in evs),
        "severity":"critical",
        "memo":"No binding commercial agreement with a named buyer on record. All revenue is hypothetical until an offtake or supply contract is confirmed.",
        "sectors":"all",
    },
    {
        "id":"no_certification",
        "label":"No Third-Party Certification",
        "check": lambda evs: not any(e["event_type"] == "Certification" for e in evs),
        "severity":"high",
        "memo":"No independent certification (DNV GL, TUV, KPX, UL) confirmed. In regulated energy markets this is a legal prerequisite for procurement.",
        "sectors":["marine_fc","ess","hvdc","grid_sw"],
    },
    {
        "id":"no_named_customer",
        "label":"No Named Strategic Buyer",
        "check": lambda evs: not any(
            re.search(r"kepco|utility|shipyard|hyperscaler|microsoft|google|amazon|engie|hanwha|hyundai|samsung",
                      (e.get("title","")+" "+e.get("summary","")).lower())
            for e in evs
        ),
        "severity":"high",
        "memo":"No named strategic buyer (utility, shipyard, hyperscaler, EPC) in any collected signal. Demand-side validation is absent.",
        "sectors":"all",
    },
    {
        "id":"no_deployment",
        "label":"No Deployment / Go-Live",
        "check": lambda evs: not any(e["event_type"] == "Deployment" for e in evs),
        "severity":"medium",
        "memo":"No operational deployment or commissioning confirmed. TRL-9 status in a commercial setting is unverified.",
        "sectors":"all",
    },
    {
        "id":"pilot_no_contract",
        "label":"Pilot Present — No Commercial Follow-On",
        "check": lambda evs: (
            any(e["event_type"] == "Pilot" for e in evs) and
            not any(e["event_type"] in ("Contract","Deployment") for e in evs)
        ),
        "severity":"high",
        "memo":"Pilot exists but has not converted to a commercial contract. This is the most common failure point in energy hardware commercialization.",
        "sectors":"all",
    },
    {
        "id":"grant_no_commercial",
        "label":"Grant Only — No Commercial Anchor",
        "check": lambda evs: (
            any(e["event_type"] == "Grant" for e in evs) and
            not any(e["event_type"] in ("Contract","Pilot","Deployment") for e in evs)
        ),
        "severity":"high",
        "memo":"Grant funding present but no commercial customer, pilot, or strategic partner. Grant-only signal is not sufficient for commercial-stage investment thesis.",
        "sectors":"all",
    },
]


def build_panels(all_signals, company_insights):
    sev_order = {"critical":0,"high":1,"medium":2,"low":3}

    # Panel 1: Negative Signals
    negative_signals = []
    for ev in all_signals:
        if not ev["is_negative"]:
            continue
        subtype = ev.get("neg_subtype") or "delay"
        meta = NEG_SUBTYPE_META.get(subtype, {
            "label":"Negative Signal","icon":"⚠","severity":"high",
            "memo":"Negative signal detected. Primary-source verification required."
        })
        negative_signals.append({
            "event_id":    ev["id"],
            "title":       ev["title"],
            "source_name": ev["source_name"],
            "source_url":  ev["source_url"],
            "event_date":  ev["event_date"],
            "company_id":  ev.get("company_id"),
            "company_name":ev.get("company_name","Unassigned"),
            "segment":     ev.get("segment","unknown"),
            "neg_subtype": subtype,
            "label":       meta["label"],
            "icon":        meta["icon"],
            "severity":    meta["severity"],
            "memo":        meta["memo"],
        })
    negative_signals.sort(key=lambda x: sev_order.get(x["severity"], 9))

    # Panel 2: Missing Evidence (per-company)
    missing_evidence = []
    for co_id, co_data in company_insights.items():
        co_evs  = co_data.get("events", [])
        sector  = co_data.get("sector","unknown")
        co_name = co_data.get("name","Unknown")
        co_gaps = []
        for rule in MISSING_RULES:
            sectors = rule["sectors"]
            if sectors != "all" and sector not in sectors:
                continue
            try:
                is_gap = rule["check"](co_evs)
            except Exception:
                is_gap = False
            if is_gap:
                co_gaps.append({
                    "rule_id":  rule["id"],
                    "label":    rule["label"],
                    "severity": rule["severity"],
                    "memo":     rule["memo"],
                })
        if co_gaps:
            co_gaps.sort(key=lambda x: sev_order.get(x["severity"], 9))
            missing_evidence.append({
                "company_id":    co_id,
                "company_name":  co_name,
                "sector":        sector,
                "stage":         co_data.get("stage","unknown"),
                "gaps":          co_gaps,
                "gap_count":     len(co_gaps),
                "critical_gaps": sum(1 for g in co_gaps if g["severity"]=="critical"),
                "high_gaps":     sum(1 for g in co_gaps if g["severity"]=="high"),
            })
    missing_evidence.sort(key=lambda x: (-(x["critical_gaps"]*10+x["high_gaps"]), x["company_name"]))

    return {
        "negative_signals": negative_signals,
        "missing_evidence": missing_evidence,
        "panel_stats": {
            "negative_count":      len(negative_signals),
            "critical_neg":        sum(1 for n in negative_signals if n["severity"]=="critical"),
            "companies_with_gaps": len(missing_evidence),
            "total_critical_gaps": sum(c["critical_gaps"] for c in missing_evidence),
        },
    }


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

    # 4. 패널 생성 (Missing Evidence + Negative Signals)
    print("④ 패널 생성 중...")
    panels = build_panels(kept, company_insights)
    print(f"  Negative: {panels['panel_stats']['negative_count']}건 | Missing gaps: {panels['panel_stats']['companies_with_gaps']}개 기업\n")

    # 5. 브리핑
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
        "panels":       panels,
        "score_rulebook": SCORE_RULEBOOK_DISPLAY,
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

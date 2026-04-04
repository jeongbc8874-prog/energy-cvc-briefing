"""
structure_insight.py
════════════════════
Raw article → 구조화 signal 변환 모듈.
collect_energy_signals.py에서 import해서 사용.

규칙:
  - 완전 rule-based. AI 없음. 모든 필드 추적 가능.
  - sector / event_type 값은 출력 스키마와 정확히 일치.
  - why_it_matters_investment는 CVC 투자 관점 전용.
  - 노이즈는 None 반환 (negative signals 제외).
"""

from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ════════════════════════════════════════════════════════════════════
# 1. SECTOR MAP
#    우선순위 순서로 매칭 (구체적 → 일반적).
#    값은 출력 스키마의 sector 필드와 1:1 대응.
# ════════════════════════════════════════════════════════════════════

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "long_duration_storage": [
        "long duration", "long-duration", "ldes",
        "iron-air", "iron air", "vanadium flow", "flow battery",
        "multi-day storage", "seasonal storage", "liquid air energy",
        "gravitational storage", "compressed air energy storage",
        "multi-week storage", "iron flow", "weeks of storage",
    ],
    "green_hydrogen": [
        "green hydrogen", "electrolyzer", "electrolysis",
        "pem electrolyzer", "alkaline electrolyzer",
        "hydrogen production", "clean hydrogen", "renewable hydrogen",
        "blue hydrogen", "h2 hub", "hydrogen hub",
        "hydrogen offtake", "hydrogen fuel", "hydrogen storage",
        "ammonia production", "power-to-x", "power to hydrogen",
    ],
    "advanced_nuclear": [
        "nuclear", "smr", "small modular reactor", "advanced reactor",
        "fusion energy", "molten salt reactor", "fast reactor",
        "fission", "nrc license", "nuclear power plant",
        "next-generation nuclear", "microreactor", "natrium",
    ],
    "geothermal": [
        "geothermal", "enhanced geothermal", "egs",
        "geothermal power", "geothermal energy",
        "hot rock", "ground source", "geothermal drilling",
        "geothermal heat pump",
    ],
    "offshore_wind": [
        "offshore wind", "floating wind", "fixed-bottom wind",
        "offshore turbine", "offshore wind farm", "monopile",
        "jacket foundation", "offshore wind cable",
        "floating offshore", "bottom-fixed wind",
    ],
    "transmission": [
        "transmission line", "hvdc", "high voltage direct current",
        "subsea cable", "grid interconnect", "interregional transmission",
        "transmission siting", "transmission permitting",
        "power line", "grid expansion", "ferc transmission",
        "offshore cable", "grid congestion",
    ],
    "grid_software": [
        "vpp", "virtual power plant", "demand response",
        "grid software", "grid control", "ferc order",
        "ferc rule", "ancillary services", "frequency regulation",
        "flexibility market", "dispatch optimization",
        "energy management system", "ems", "grid modernization",
        "smart grid", "grid intelligence", "grid operator software",
    ],
    "data_center_power": [
        "data center", "data centre", "hyperscaler",
        "azure power", "aws energy", "google cloud energy",
        "ai infrastructure power", "cfe",
        "24/7 clean energy", "corporate ppa", "tech company energy",
        "ai power demand", "ai energy",
    ],
    "battery_storage": [
        "battery storage", "bess",
        "energy storage system", "lithium-ion", "lithium ion",
        "grid battery", "utility-scale battery",
        "electrochemical storage", "sodium-ion", "solid state battery",
        "grid-scale battery", "li-ion battery",
        "battery system", "stationary storage",
    ],
    "other_cleantech": [
        "clean energy", "renewable energy", "solar power",
        "wind energy", "cleantech", "decarbonization",
        "net zero", "climate tech", "energy transition",
        "carbon capture", "ccus", "ccs",
        "carbon removal", "direct air capture",
    ],
}

# 우선순위 순서 (구체적 → 일반적)
SECTOR_PRIORITY: list[str] = [
    "long_duration_storage",
    "green_hydrogen",
    "advanced_nuclear",
    "geothermal",
    "offshore_wind",
    "transmission",
    "grid_software",
    "data_center_power",
    "battery_storage",
    "other_cleantech",
]


def infer_sector(raw_text: str, source_segments: list[str] | None = None) -> str:
    """텍스트에서 sector 추론. 매칭 없으면 소스 기본 segment → other_cleantech."""
    t = raw_text.lower()
    for seg in SECTOR_PRIORITY:
        if any(kw in t for kw in SECTOR_KEYWORDS.get(seg, [])):
            return seg
    # 소스 선언 segment 중 유효한 값이 있으면 사용
    valid = set(SECTOR_KEYWORDS.keys())
    for s in (source_segments or []):
        if s in valid:
            return s
    return "other_cleantech"


# ════════════════════════════════════════════════════════════════════
# 2. EVENT TYPE RULES
#    base_score = 이 이벤트 타입의 기본 투자 가중치 (0-100).
#    kws는 lowercase 매칭. 첫 번째 매칭된 규칙이 사용됨.
# ════════════════════════════════════════════════════════════════════

EVENT_RULES: list[dict] = [
    # ── Tier 1: 상업적 확정 이벤트 ─────────────────────────────────
    {
        "event_type": "contract",
        "base_score": 90,
        "kws": [
            "signs contract", "awarded contract", "secures contract",
            "contract awarded", "contract signed", "offtake agreement",
            "supply agreement", "framework agreement",
            "power purchase agreement", "ppa signed", "ppa awarded",
            "long-term agreement", "commercial agreement",
            "procurement contract", "binding agreement",
        ],
    },
    {
        "event_type": "deployment",
        "base_score": 88,
        "kws": [
            "goes live", "commercial operation", "commissioned",
            "begins operation", "starts operation", "deployed at",
            "installed at", "goes online", "comes online",
            "construction complete", "opens facility",
            "first power", "energized", "operational",
            "system online", "plant opens",
        ],
    },
    # ── Tier 2: 자본 이벤트 ─────────────────────────────────────────
    {
        "event_type": "funding",
        "base_score": 82,
        "kws": [
            "series a", "series b", "series c", "series d",
            "seed round", "closes funding", "funding round",
            "investment round", "equity raise", "capital raise",
            "closes $", "raises $", "secures $",
            "closes €", "raises €", "million raised",
            "billion raised", "venture capital", "secures investment",
        ],
    },
    {
        "event_type": "grant",
        "base_score": 65,
        "kws": [
            "grant awarded", "receives grant", "doe award",
            "doe funding", "doe selects", "doe announces",
            "government grant", "eu grant", "federal grant",
            "loan guarantee", "doe loan", "ira funding",
            "sbir award", "nsf grant", "department of energy",
            "clean energy grant", "innovation grant",
        ],
    },
    # ── Tier 2: 기술 검증 ───────────────────────────────────────────
    {
        "event_type": "pilot",
        "base_score": 70,
        "kws": [
            "pilot project", "demonstration project", "demo project",
            "field trial", "proof of concept",
            "first deployment", "initial deployment",
            "prototype tested", "demonstration plant",
            "test project", "trial deployment",
        ],
    },
    # ── Tier 2: 규제/정책 ───────────────────────────────────────────
    {
        "event_type": "regulatory",
        "base_score": 62,
        "kws": [
            "ferc order", "ferc approves", "ferc issues",
            "ferc rule", "ferc notice", "ferc docket",
            "permit granted", "permitting approved",
            "interconnection approval", "nrc approves", "nrc license",
            "epa rule", "transmission permit",
            "environmental approval",
        ],
    },
    {
        "event_type": "policy",
        "base_score": 55,
        "kws": [
            "inflation reduction act", "infrastructure law",
            "tax credit", "itc extended", "ptc extended",
            "clean energy standard", "renewable portfolio standard",
            "executive order energy", "national strategy",
            "energy mandate", "carbon standard",
        ],
    },
    # ── Tier 3: 전략적 ──────────────────────────────────────────────
    {
        "event_type": "partnership",
        "base_score": 48,
        "kws": [
            "strategic partnership", "signs mou",
            "memorandum of understanding", "joint venture",
            "collaboration agreement", "strategic alliance",
            "teaming agreement", "co-development agreement",
        ],
    },
]

_DEFAULT_EVENT = {"event_type": "other", "base_score": 15, "matched_kw": None}


def classify_event(raw_text: str) -> dict:
    """첫 번째 매칭 이벤트 규칙 반환. 매칭 없으면 default."""
    t = raw_text.lower()
    for rule in EVENT_RULES:
        for kw in rule["kws"]:
            if kw in t:
                return {
                    "event_type": rule["event_type"],
                    "base_score": rule["base_score"],
                    "matched_kw": kw,
                }
    return _DEFAULT_EVENT.copy()


# ════════════════════════════════════════════════════════════════════
# 3. SCORE ENGINE
#    additive rule-based. 완전 감사 가능.
# ════════════════════════════════════════════════════════════════════

BOOST_RULES: list[tuple[str, int, str]] = [
    # 전략적 바이어
    (r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b"
     r"|\bvattenfall\b|\bnational grid\b|\borsted\b|\bequinor\b",
     +18, "Tier-1 strategic buyer named"),
    (r"\bhyundai\b|\bsamsung\b|\bsiemens\b|\babb\b|\bhitachi\b"
     r"|\bhanwha\b|\bshell\b|\bbp\b|\btotalenergies\b|\bplugged\b",
     +12, "Major industrial / OEM buyer named"),
    # 정량적 사실
    (r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion"
     r"|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]|₩[\d,]+억",
     +15, "Specific financial figure"),
    (r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b"
     r"|[\d,]+\s*kg.{0,5}h2|[\d,]+\s*tonne",
     +10, "Specific capacity / volume figure"),
    (r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ months?"
     r"|h[12] 20[2-9]\d|in \d{4}",
     +8,  "Concrete timeframe stated"),
    # 출처 신뢰도
    (r"\beia\b|\bdoe\b|\bferc\b|\biea\b|\birena\b|\bnrel\b|\blbl\b",
     +6,  "Government / intergovernmental body mentioned"),
    # 지역 특정성
    (r"\bbusan\b|\bincheon\b|\bulsan\b|\brotterdam\b|\bsingapore\b"
     r"|\btexas\b|\bcalifornia\b|\bokla\b|\bwyoming\b|\bscotland\b",
     +5,  "Named project location"),
]

NOISE_RULES: list[tuple[str, int, str]] = [
    (r"\bproud to (announce|partner|share)\b"
     r"|\bexcited to (announce|share)\b|\bpleased to announce\b",
     -40, "Generic PR language"),
    (r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b",
     -20, "Intent only — no confirmed action"),
    (r"\bcould (become|reach|achieve|unlock)\b|\bhas the potential to\b",
     -25, "Speculative outcome"),
    (r"\bexploring\b.{0,50}\bpartner|\bin early discussions\b"
     r"|\bpotential (partner|deal)\b|\bdiscussing potential\b",
     -30, "Exploratory / pre-commercial language"),
    (r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b"
     r"|\broadmap for\b",
     -30, "Vision / strategy announcement only"),
    (r"\bwins? award\b|\brecognized as\b"
     r"|\bnamed (a )?(top|leading|best)\b|\bgartner\b|\baward-winning\b",
     -35, "Vanity award / recognition"),
    (r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b"
     r"|\bwebinar\b|\battends? (conference|summit)\b",
     -30, "Conference appearance only"),
    (r"\bpublishes? (report|study|whitepaper|index)\b"
     r"|\bnew (report|research|study)\b|\blaunches? report\b",
     -25, "Report / research publication"),
    (r"\brebrands?\b|\bnew (logo|brand|name|identity|website)\b",
     -55, "Rebranding / marketing"),
    (r"\bopinion:\b|\bcommentary:\b|\bop-ed\b|\beditorial:\b",
     -60, "Opinion / commentary"),
    (r"\bmarket (wrap|roundup|update|recap)\b"
     r"|\bweekly (round-?up|digest)\b|\bmonthly digest\b",
     -60, "Market digest / roundup"),
    (r"\bwe('re| are) hiring\b|\bjoin our team\b"
     r"|\bopen (position|role)\b|\bcareer opportunit\b",
     -50, "Generic job posting"),
]

# 노이즈 확정 판단 키워드 (점수와 무관, 무조건 drop)
HARD_NOISE_KWS: list[str] = [
    "opinion:", "commentary:", "op-ed:", "letter to the editor",
    "weekly wrap", "monthly digest", "market roundup",
    "we are hiring", "join our team", "job opening",
    "new logo", "rebrand",
]

SCORE_HIGH   = 60
SCORE_MEDIUM = 35
SCORE_LOW    = 20


def score_signal(raw_text: str, base: int) -> tuple[int, str, list[dict]]:
    """
    점수 계산. Returns (final_score, tier, breakdown).
    tier: "high" | "medium" | "low" | "noise"
    """
    s  = base
    bd: list[dict] = []

    for pattern, delta, reason in BOOST_RULES:
        if re.search(pattern, raw_text, re.I):
            s += delta
            bd.append({"delta": delta, "reason": reason, "type": "boost"})

    for pattern, delta, reason in NOISE_RULES:
        if re.search(pattern, raw_text, re.I):
            s += delta
            bd.append({"delta": delta, "reason": reason, "type": "noise"})

    s = max(0, min(100, round(s)))

    if s >= SCORE_HIGH:
        tier = "high"
    elif s >= SCORE_MEDIUM:
        tier = "medium"
    elif s >= SCORE_LOW:
        tier = "low"
    else:
        tier = "noise"

    return s, tier, bd


def is_hard_noise(raw_text: str) -> bool:
    """무조건 drop해야 하는 콘텐츠."""
    t = raw_text.lower()
    return any(kw in t for kw in HARD_NOISE_KWS)


# ════════════════════════════════════════════════════════════════════
# 4. ENTITY EXTRACTION
#    추적 중인 기업 별칭 → 정식명.
# ════════════════════════════════════════════════════════════════════

COMPANY_ALIASES: dict[str, str] = {
    # Long-duration / flow battery
    "form energy":          "Form Energy",
    "ambri":                "Ambri",
    "eos energy":           "Eos Energy",
    "hydrostor":            "Hydrostor",
    "energy vault":         "Energy Vault",
    "invinity":             "Invinity Energy",
    "enervenue":            "EnerVenue",
    "iron air":             "Form Energy",   # 기술 매핑
    # Green hydrogen
    "verdagy":              "Verdagy",
    "electric hydrogen":    "Electric Hydrogen",
    "ohmium":               "Ohmium",
    "plug power":           "Plug Power",
    "bloom energy":         "Bloom Energy",
    "sunfire":              "Sunfire",
    "hysata":               "Hysata",
    # Grid software / VPP
    "autogrid":             "AutoGrid",
    "gridwiz":              "그리드위즈",
    "그리드위즈":            "그리드위즈",
    "sixtyhz":              "식스티헤르츠",
    "식스티헤르츠":          "식스티헤르츠",
    "빈센":                  "빈센",
    "standard energy":      "스탠다드에너지",
    "fluence":              "Fluence",
    "stem inc":             "Stem",
    # Nuclear
    "kairos power":         "Kairos Power",
    "terrapower":           "TerraPower",
    "x-energy":             "X-Energy",
    "nuscale":              "NuScale",
    "oklo":                 "Oklo",
    # Geothermal
    "fervo":                "Fervo Energy",
    "sage geosystems":      "Sage Geosystems",
    # Offshore wind
    "orsted":               "Ørsted",
    "equinor":              "Equinor",
    "vestas":               "Vestas",
    "siemens gamesa":       "Siemens Gamesa",
    # Storage / battery
    "amogy":                "Amogy",
    "ceres power":          "Ceres Power",
}


def extract_companies(raw_text: str) -> list[str]:
    """텍스트에서 추적 기업 추출. 정식명 반환, 중복 제거."""
    t = raw_text.lower()
    found: list[str] = []
    for alias, canonical in COMPANY_ALIASES.items():
        if alias in t and canonical not in found:
            found.append(canonical)
    return found


# ════════════════════════════════════════════════════════════════════
# 5. WHY IT MATTERS (CVC 투자 관점)
#    event_type × sector 조합으로 구체적 투자 설명 반환.
# ════════════════════════════════════════════════════════════════════

_WHY: dict[tuple[str, str], str] = {
    ("contract", "long_duration_storage"):
        "Binding offtake is the critical de-risking event for LDES project finance. "
        "Confirms demand-side validation; structured debt now possible.",
    ("contract", "battery_storage"):
        "Offtake/supply agreement is the clearest commercial-stage signal. "
        "LCOS competitiveness implied; contract terms needed for confirmation.",
    ("contract", "green_hydrogen"):
        "Offtake at contracted price is the key missing link in most hydrogen theses. "
        "Without a named buyer at a locked price, projects remain financially unviable.",
    ("contract", "grid_software"):
        "Named utility contract moves company from pilot to commercial stage. "
        "Key unknowns: ACV, duration, exclusivity, framework vs. project-specific.",
    ("contract", "offshore_wind"):
        "CfD or PPA award confirms revenue certainty. "
        "Construction finance now possible; supply chain commitments follow.",
    ("contract", "advanced_nuclear"):
        "PPA for nuclear signals long-duration, high-value decarbonization commitment. "
        "Rare — watch for corporate buyer identity and pricing terms.",
    ("contract", "data_center_power"):
        "Hyperscaler PPA is the strongest commercial signal for clean power. "
        "High ACV, sticky demand, low churn — de-risks developer revenue.",
    ("deployment", "long_duration_storage"):
        "First commercial LDES deployment is a sector-defining milestone. "
        "Establishes real-world LCOS baseline; de-risks project finance for the sector.",
    ("deployment", "battery_storage"):
        "Operational deployment confirms TRL-9 in commercial setting. "
        "Utilities can reference-site; next signal is contract replication.",
    ("deployment", "advanced_nuclear"):
        "Nuclear commissioning confirms regulatory pathway and cost baseline. "
        "Watch for SMR cost-overrun data vs. projections.",
    ("funding", "default"):
        "External capital validation. Key: investor type (strategic >> financial), "
        "round size vs. capex needs, lead investor sector positioning.",
    ("grant", "default"):
        "Government grant validates technology policy relevance but not market demand. "
        "Grant-only is insufficient without a commercial anchor (offtaker, contract).",
    ("grant", "green_hydrogen"):
        "DOE/IRA hydrogen grants ($50M–$1B+) are transformative but require "
        "named industrial offtakers to close project finance.",
    ("pilot", "grid_software"):
        "Utility-sponsored pilot implies allocated opex budget. "
        "Pilot-to-commercial conversion rate is the key watch metric.",
    ("pilot", "battery_storage"):
        "Grid-connected pilot signals utility-scale targeting. "
        "Interface compliance is the commercialization gate.",
    ("pilot", "green_hydrogen"):
        "Pilot electrolyzer data establishes real LCOH. "
        "Key question: is there a named industrial offtaker co-funding the pilot?",
    ("regulatory", "grid_software"):
        "FERC orders directly expand addressable market for VPPs and storage. "
        "Order 2222 implementation is the key regulatory catalyst for grid software.",
    ("regulatory", "transmission"):
        "Transmission permitting is the primary bottleneck for renewable buildout. "
        "FERC and DOE permitting reform directly expand grid capacity.",
    ("policy", "green_hydrogen"):
        "IRA §45V hydrogen PTC ($3/kg clean, $0.60/kg blue) is the largest H2 subsidy globally. "
        "Final guidance clarity determines electrolyzer project bankability.",
    ("policy", "battery_storage"):
        "IRA standalone storage ITC transforms project finance economics. "
        "State-level mandates create additional demand floor.",
    ("policy", "advanced_nuclear"):
        "NRC licensing reform and DOE loan guarantees are critical SMR enablers. "
        "Policy signals directly de-risk first-of-a-kind capital.",
    ("partnership", "default"):
        "Named strategic partnership is directional. "
        "MOU alone does not confirm commercial intent — watch for binding term conversion.",
}

def why_investment(event_type: str, sector: str) -> str:
    return (
        _WHY.get((event_type, sector))
        or _WHY.get((event_type, "default"))
        or (f"{event_type.capitalize()} event in {sector.replace('_', ' ')} sector. "
            f"Assess binding terms, named counterparties, and capital efficiency.")
    )


# ════════════════════════════════════════════════════════════════════
# 6. MISSING EVIDENCE (투자 결정 전 확인 필요한 gap)
# ════════════════════════════════════════════════════════════════════

MISSING_BY_EVENT: dict[str, list[str]] = {
    "contract": [
        "Contract ACV (annual contract value) not disclosed",
        "Duration and renewal terms not public",
        "Exclusivity and geographic scope unknown",
    ],
    "funding": [
        "Post-money valuation not confirmed",
        "Lead investor type (strategic vs. financial) unknown",
        "Use of proceeds not specified",
    ],
    "grant": [
        "Commercial co-funding partner not identified",
        "Path from grant to commercial revenue unclear",
        "Private-sector offtaker required for project finance?",
    ],
    "pilot": [
        "Pilot success KPIs not publicly defined",
        "Pathway to commercial contract post-pilot unclear",
        "Named third-party validator not confirmed",
    ],
    "deployment": [
        "Revenue / offtake terms not disclosed",
        "Performance guarantee and warranty unknown",
        "Scale-up roadmap not public",
    ],
    "partnership": [
        "Binding terms (exclusivity, minimum volume) not confirmed",
        "MOU vs. binding contract distinction not stated",
        "Financial commitments not disclosed",
    ],
    "regulatory": [
        "Effective date and implementation timeline not stated",
        "Compliance costs not disclosed",
    ],
    "policy": [
        "Implementation regulations not yet issued",
        "Budget appropriation certainty unknown",
    ],
    "other": [
        "No investment-specific gap analysis available",
        "Primary research required",
    ],
}

def missing_evidence(event_type: str) -> list[str]:
    return MISSING_BY_EVENT.get(event_type, MISSING_BY_EVENT["other"])


# ════════════════════════════════════════════════════════════════════
# 7. MAIN NORMALIZER
#    raw article dict → structured signal dict (출력 스키마).
#    Returns None if article is noise / error.
# ════════════════════════════════════════════════════════════════════

def normalize(raw: dict) -> Optional[dict]:
    """
    raw article → structured signal.

    Input keys expected:
      article_id, title, source_name, source_url, source_segments,
      summary, published_date, raw_text, reliability, tier

    Returns None for noise or on error.
    Never raises.
    """
    try:
        raw_text    = raw.get("raw_text", "")
        title       = raw.get("title", "").strip()
        source_url  = raw.get("source_url", "")
        source_name = raw.get("source_name", "")
        pub_date    = raw.get("published_date", TODAY)
        summary     = raw.get("summary", "")

        # Hard noise check (무조건 drop)
        if is_hard_noise(raw_text):
            return None

        clf          = classify_event(raw_text)
        sect         = infer_sector(raw_text, raw.get("source_segments"))
        final, tier, breakdown = score_signal(raw_text, clf["base_score"])

        # Negative signal detection
        neg_kws = [
            "delay", "postponed", "cancelled", "cancels",
            "funding shortfall", "struggles to raise",
            "project terminated", "deal collapsed",
            "behind schedule", "cost overrun",
        ]
        is_neg = any(kw in raw_text.lower() for kw in neg_kws)

        # Drop noise (negative signals bypass threshold)
        if tier == "noise" and not is_neg:
            return None

        # Observed fact: first substantive sentence from summary
        clean_summary = re.sub(r"<[^>]+>", " ", summary)
        clean_summary = re.sub(r"\s+", " ", clean_summary).strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_summary)
                     if len(s.strip()) > 30]
        observed = sentences[0] if sentences else title

        return {
            # ── 출력 스키마 필수 필드 ─────────────────────────────
            "id":                        raw["article_id"],
            "title":                     title,
            "source_name":               source_name,
            "source_url":                source_url,
            "published_date":            pub_date,
            "observed_fact":             observed,
            "why_it_matters_investment": why_investment(clf["event_type"], sect),
            "missing_evidence":          missing_evidence(clf["event_type"]),
            "signal_tier":               tier,
            "signal_strength":           final,
            "sector":                    sect,
            "event_type":                clf["event_type"],
            "companies_mentioned":       extract_companies(raw_text),
            # ── 내부 / 디버그 필드 ────────────────────────────────
            "is_negative":               is_neg,
            "matched_keyword":           clf["matched_kw"],
            "score_breakdown":           breakdown,
            "source_reliability":        raw.get("reliability", "★"),
            "source_tier":               raw.get("tier", 3),
            "raw_summary":               clean_summary[:400] if clean_summary else title,
            "fetched_at":                raw.get("fetched_at", TODAY),
        }

    except Exception as ex:
        # 절대 raise하지 않음 — 로깅만
        import logging
        logging.getLogger("structure_insight").debug(
            f"normalize error: {ex} — {raw.get('title', '')[:60]}"
        )
        return None

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ENERGY CAPITAL INTELLIGENCE  —  Signal Pipeline v3.0                      ║
║  Commercial B2B Product for Energy VC / CVC / Infrastructure Teams         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  COMMERCIALISATION ROADMAP                                                  ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║                                                                              ║
║  TIER 1 — MVP  (internal use, $0, validates core value)                    ║
║    ✓ RSS ingestion + daily JSON → Cloudflare Pages                         ║
║    ✓ Rule-based classification (Tiers 1-4)                                 ║
║    ✓ Signal scoring (additive, auditable)                                  ║
║    ✓ Evidence cards (6-field structured format)                            ║
║    ✓ Company pages (stage, pattern, gaps, timeline)                        ║
║    ✓ Project pages (developer, offtaker, EPC, capex)                      ║
║    ✓ Strategic buyer pages (procurement signals, activity)                 ║
║    ✓ Missing evidence + negative signal panels                             ║
║    ✓ Sector rulebooks (transparent scoring)                                ║
║    ✓ Reliability / source health bar                                       ║
║    ✓ Score Rules tab (full transparency)                                   ║
║                                                                              ║
║  TIER 2 — PAID PILOT  ($500-2,000/seat/month, 3-5 seats per fund)         ║
║    ○ Analyst notes  (per company/project — free-text, timestamped)        ║
║    ✓ Watchlist  (localStorage — companies/projects/segments/buyers)        ║
║    ✓ Alerts    (in-app alert feed, what changed + why + confidence)        ║
║    ○ Alerts    (email/Slack delivery — Paid Pilot upgrade)                 ║
║    ○ Evidence history  (30-90 day signal timeline per company)            ║
║    ○ Triage status  (Pass / Watch / Investigate per company)               ║
║    ○ Team workflow  (shared notes, activity log, @mentions)               ║
║    ○ Export to CSV / PDF deal memo  (one-click)                           ║
║    ○ Sector-gated modules  (ESS / Marine FC / Hydrogen — separate SKUs)   ║
║                                                                              ║
║  TIER 3 — SCALE  ($3,000-8,000/seat/month, 10+ seats)                     ║
║    ○ Outcome tracking  (what happened after signal → result logging)       ║
║    ○ API access  (GET /api/company/{id}/card — programmatic)               ║
║    ○ Webhook alerts  (pattern-match fires → Slack/Zapier)                 ║
║    ○ Proprietary data integration  (DART, SEC EDGAR, LinkedIn)            ║
║    ○ Comparables DB  (deal terms, post-money, round history)              ║
║    ○ Custom entity registry  (client adds own watchlist companies)        ║
║    ○ White-label / embed  (iframe or API for LP portal)                   ║
║    ○ Segment heat maps  (capital flow intensity by sector × geography)    ║
║                                                                              ║
║  REVENUE MODEL                                                              ║
║    Seat-based SaaS:     $/seat/month × seats per fund                     ║
║    Sector modules:      add-on pricing per segment pack                   ║
║    Analyst data:        premium curated dataset licence                   ║
║    API access:          usage-based or flat API tier                      ║
║    Custom integrations: professional services / setup fee                 ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  DATA MODEL                                                                 ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║                                                                              ║
║  PUBLIC (this file → data/latest.json):                                    ║
║    signals[]          Raw ingested + scored events                         ║
║    companies{}        Enriched company intelligence objects                ║
║    projects[]         Project-level intelligence                           ║
║    strategic_buyers[] Buyer registry + activity                            ║
║    buyer_activity{}   Per-buyer event history                              ║
║    panels{}           Missing evidence + negative signal panels            ║
║    source_log[]       Per-source reliability data                          ║
║    score_rulebook[]   Scoring rules for UI transparency                    ║
║    reliability{}      Pipeline health aggregate                            ║
║                                                                              ║
║  PRIVATE (future DB — never in public JSON):                               ║
║    analyst_notes{}    { company_id, author, text, timestamp, visibility }  ║
║    watchlist[]        { company_id, user_id, threshold, added_at }        ║
║    alerts[]           { company_id, signal_id, sent_at, channel }         ║
║    triage_status{}    { company_id, status, set_by, set_at, rationale }   ║
║    evidence_history[] { company_id, signal_id, date, outcome, noted_by }  ║
║    outcomes[]         { signal_id, outcome_type, outcome_date, note }      ║
║    team_activity[]    { user_id, action, entity_id, timestamp }           ║
║    comparables[]      { deal_terms, post_money, source, confidence }       ║
║                                                                              ║
║  RULE-BASED (never changes without deliberate code edit):                  ║
║    • Event classification    keyword tiers 1-4                             ║
║    • Signal scoring          additive deltas, fully auditable              ║
║    • Noise filtering         veto patterns, threshold gates                ║
║    • Stage inference         evidence-ladder, event-based                  ║
║    • Missing evidence        structural gap rules per sector               ║
║    • Buyer matching          named entity keyword lists                    ║
║    • TTR classification      Near / Mid / Long-term                        ║
║    • Pattern detection       multi-signal cluster rules                    ║
║                                                                              ║
║  AI-ASSISTED (Claude API, optional, graceful fallback):                    ║
║    • Daily intelligence brief                                              ║
║    • Pattern narrative generation (from evidence only)                     ║
║    ⚠ Never generates numbers, valuations, or facts not in source          ║
║                                                                              ║
║  HUMAN REVIEW REQUIRED:                                                     ║
║    • Analyst notes and triage decisions                                    ║
║    • Watchlist membership and alert thresholds                             ║
║    • Outcome tracking and result logging                                   ║
║    • Unassigned event confirmation                                         ║
║    • Comparables database curation                                         ║
║                                                                              ║
║  FUTURE PROPRIETARY DATA (DB only, never public):                          ║
║    • DART API — KR regulatory filings                                      ║
║    • SEC EDGAR — US company filings                                        ║
║    • LinkedIn hiring velocity                                              ║
║    • Patent filing velocity per company/segment                           ║
║    • NDA-covered term sheets and cap table snapshots                       ║
║    • Primary meeting notes                                                 ║
║                                                                              ║
║  PREMIUM / API-ONLY (future tier):                                         ║
║    GET  /api/company/{id}/card    Evidence card as JSON                    ║
║    GET  /api/segments/heatmap     Capital flow intensity map               ║
║    GET  /api/buyers/{id}/activity Strategic buyer movement                 ║
║    POST /api/watchlist/diff       Diff alerts via webhook                  ║
║    POST /api/memo/{id}/export     PDF deal memo export                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import re, json, hashlib, os, socket
from datetime import datetime, timezone
from pathlib import Path

try:
    import feedparser; HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TODAY    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
TODAY_KR = datetime.now(timezone.utc).strftime("%Y년 %m월 %d일")


# ══════════════════════════════════════════════════════════════════════════
# SECTION 1  CURATED SOURCE REGISTRY
# ══════════════════════════════════════════════════════════════════════════
#
# POLICY: Sources are NEVER added automatically.
# Every source must be explicitly approved by an analyst and added here.
# New sources proposed via UI are written to data/source_proposals.json
# and require a human to move them into this file.
#
# SOURCE SCHEMA:
#   id              unique slug, no spaces
#   name            display name
#   url             RSS feed URL
#   source_type     "industry" | "company" | "government" | "academic"
#   reliability     1 (primary/verified) | 2 (secondary/trade) | 3 (aggregator/blog)
#   topics          list of covered topics (for display and filtering)
#   segments        internal segment IDs used by scoring engine
#   geography       "KR" | "US" | "EU" | "GLOBAL"
#   language        "en" | "ko" | "de" etc.
#   access          "free" | "premium" | "requires_key"
#   approved_by     analyst who added this source
#   approved_date   ISO date of approval
#   notes           why this source was approved, any known limitations
#
# RELIABILITY TIERS:
#   Tier 1 — Primary source: regulatory filings, official press releases,
#             direct company announcements, government publications.
#             Signals from T1 sources carry higher evidential weight.
#   Tier 2 — Trade press: industry-specialist publications with editorial
#             standards. Good for market news, deal announcements.
#             Verify financial figures against primary source.
#   Tier 3 — Aggregators / general tech press / blogs. Useful for breadth,
#             but all figures require primary-source verification before citing.
#
# ══════════════════════════════════════════════════════════════════════════

SOURCE_REGISTRY = [

    # ── Tier 2 — Energy trade press (approved, free RSS) ─────────────────

    {
        "id":            "utilitydive",
        "name":          "Utility Dive",
        "url":           "https://www.utilitydive.com/feeds/news/",
        "source_type":   "industry",
        "reliability":   2,
        "topics":        ["grid software","demand response","VPP","utility procurement",
                          "energy storage","data center power","regulatory"],
        "segments":      ["grid_sw","ess","dc_power"],
        "geography":     "US",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Strong US utility market coverage. Financial figures are secondary — verify against FERC/SEC filings.",
    },
    {
        "id":            "pvmagazine",
        "name":          "PV Magazine",
        "url":           "https://www.pv-magazine.com/feed/",
        "source_type":   "industry",
        "reliability":   2,
        "topics":        ["solar PV","energy storage","hydrogen","grid forecasting",
                          "electrolyzer","green hydrogen","battery"],
        "segments":      ["ess","hydrogen","forecasting"],
        "geography":     "GLOBAL",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Good European + global coverage. Project figures should be verified against developer announcements.",
    },
    {
        "id":            "energystoragenews",
        "name":          "Energy Storage News",
        "url":           "https://www.energy-storage.news/feed/",
        "source_type":   "industry",
        "reliability":   2,
        "topics":        ["battery storage","BESS","grid-scale ESS","flow battery",
                          "long-duration storage","utility ESS"],
        "segments":      ["ess"],
        "geography":     "GLOBAL",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Specialist ESS trade press. Good for deployment and contract announcements.",
    },
    {
        "id":            "offshorewind",
        "name":          "Offshore Wind Biz",
        "url":           "https://www.offshorewind.biz/feed/",
        "source_type":   "industry",
        "reliability":   2,
        "topics":        ["offshore wind","HVDC","subsea cable","port infrastructure",
                          "OEM contracts","grid connection"],
        "segments":      ["hvdc","ess"],
        "geography":     "EU",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Strong North Sea / European offshore coverage. Useful for HVDC cable and interconnect signals.",
    },
    {
        "id":            "electrek",
        "name":          "Electrek",
        "url":           "https://electrek.co/feed/",
        "source_type":   "industry",
        "reliability":   3,
        "topics":        ["EV","energy storage","clean energy","DC power",
                          "hyperscaler energy","utility-scale battery"],
        "segments":      ["ess","dc_power","forecasting"],
        "geography":     "US",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Tier 3 — broad coverage, often first to report but verify all figures. "
                         "Replaced Recharge News (Informa paywall). Not suitable as primary citation.",
    },
    {
        "id":            "h2view",
        "name":          "H2 View",
        "url":           "https://www.h2-view.com/feed/",
        "source_type":   "industry",
        "reliability":   2,
        "topics":        ["green hydrogen","electrolyzer","hydrogen production",
                          "hydrogen transport","marine hydrogen","bunkering",
                          "fuel cell","PEM","SOEC"],
        "segments":      ["hydrogen","marine_fc"],
        "geography":     "GLOBAL",
        "language":      "en",
        "access":        "free",
        "approved_by":   "analyst",
        "approved_date": "2025-01-01",
        "notes":         "Replaced Hydrogen Insight (Informa paywall blocked RSS). "
                         "Specialist hydrogen trade press. Verify project capex against developer filings.",
    },

    # ── PROPOSED (not yet approved — do not add to RSS_SOURCES below) ────
    # To propose a source, use the UI → Sources tab → Propose New Source.
    # These entries exist for transparency; they are NOT fetched.
    # To approve: analyst moves entry to the active list above, sets
    # approved_by and approved_date, then deploys.

    # {"id":"fuelcellsworks","name":"Fuel Cells Works","url":"https://fuelcellsworks.com/feed/",
    #  "source_type":"industry","reliability":3,
    #  "topics":["fuel cell","hydrogen","marine FC","stationary power"],
    #  "segments":["marine_fc","hydrogen"],"geography":"GLOBAL","language":"en","access":"free",
    #  "status":"proposed","proposed_by":"analyst","proposed_date":"2026-03-01",
    #  "proposed_reason":"Additional marine FC coverage. Verify editorial standards before approving."},

    # {"id":"greencarcongress","name":"Green Car Congress","url":"https://www.greencarcongress.com/atom.xml",
    #  "source_type":"industry","reliability":3,
    #  "topics":["hydrogen","fuel cell","clean transportation","electrolyzer"],
    #  "segments":["hydrogen","marine_fc"],"geography":"US","language":"en","access":"free",
    #  "status":"proposed","proposed_by":"analyst","proposed_date":"2026-03-01",
    #  "proposed_reason":"Broad hydrogen + fuel cell coverage. Tier 3 only."},
]

# ── Build active RSS_SOURCES from approved registry entries ───────────
# Only entries WITHOUT a "status" field (i.e. approved) are fetched.
# Proposed entries are excluded automatically.
RSS_SOURCES = [
    {
        "id":       s["id"],
        "name":     s["name"],
        "url":      s["url"],
        "segments": s["segments"],
        # Pass through metadata for source_log enrichment
        "source_type":  s["source_type"],
        "reliability":  s["reliability"],
        "topics":       s["topics"],
        "geography":    s.get("geography","GLOBAL"),
        "language":     s.get("language","en"),
        "approved_by":  s.get("approved_by","unknown"),
        "approved_date":s.get("approved_date","unknown"),
    }
    for s in SOURCE_REGISTRY
    if "status" not in s  # only approved sources (no status key = approved)
]


# ══════════════════════════════════════════════════════════════════════════
# SECTION 2  ENTITY REGISTRY
# ══════════════════════════════════════════════════════════════════════════
# MVP: static registry — curated by analyst, checked into code
# Paid pilot: analyst adds companies via UI → stored in DB
# Scale: client-configurable per seat/team — custom entity registry per fund

COMPANIES = [
    # ── Korean ──────────────────────────────────────────────────────────
    {"id":"c_gridwiz",    "name":"그리드위즈",
     "aliases":["gridwiz","grid wiz"],
     "sector":"grid_sw",   "country":"KR", "stage":"First Commercial",
     "investor_type":"Strategic/CVC",
     "founded":2016,
     "hq":"서울, KR",
     "description":"KPX-certified VPP/DR platform operator. First commercial contracts with KEPCO underway. CFO hired Q4 2025.",
     "tags":["비상장","VPP","KPX인증","Series-B"],
     "known_investors":["한국투자파트너스","LS일렉트릭"],
     "watchlist_default":True},   # pre-curated — appears on default watchlist
    {"id":"c_sixtyhertz", "name":"식스티헤르츠",
     "aliases":["sixty hertz","60hz","sixtyhertz"],
     "sector":"grid_sw",   "country":"KR", "stage":"First Commercial",
     "investor_type":"VC",
     "founded":2018,
     "hq":"서울, KR",
     "description":"AI-powered renewable energy forecasting. KEPCO 3-year contract. Kakao Ventures Series A. 98.3% accuracy claim.",
     "tags":["비상장","AI예측","Series-A"],
     "known_investors":["카카오벤처스","소프트뱅크벤처스"],
     "watchlist_default":True},
    {"id":"c_vincen",     "name":"빈센",
     "aliases":["vincen","vinsen"],
     "sector":"marine_fc", "country":"KR", "stage":"Pilot",
     "investor_type":"Strategic/CVC",
     "founded":2019,
     "hq":"부산, KR",
     "description":"Marine hydrogen PEM fuel cell. HD HHI MOU. 1MW pilot aboard test vessel Busan port. Pre-DNV certification.",
     "tags":["비상장","IMO2030","PEM","Series-A"],
     "known_investors":["산업부 R&D","HD한국조선해양"],
     "watchlist_default":False},
    {"id":"c_standard_e", "name":"스탠다드에너지",
     "aliases":["standard energy"],
     "sector":"ess",       "country":"KR", "stage":"Demo",
     "investor_type":"Strategic/CVC",
     "founded":2015,
     "hq":"서울, KR",
     "description":"Vanadium redox flow battery. Hanwha Solutions Series B. DOE grant application pending. 100kWh 1,000h endurance test completed.",
     "tags":["비상장","VRFB","Series-B"],
     "known_investors":["한화솔루션","KDB산업은행"],
     "watchlist_default":True},
    {"id":"c_hylium",     "name":"하이리움산업",
     "aliases":["hylium","하이리움"],
     "sector":"hydrogen",  "country":"KR", "stage":"Demo",
     "investor_type":"Strategic/CVC",
     "founded":2014,
     "hq":"경기, KR",
     "description":"First domestic liquid hydrogen plant operational. Hyundai Motor supply chain registration complete. Ministry of Industry core company designation.",
     "tags":["비상장","LH2","Series-B"],
     "known_investors":["현대기술투자","산업부"],
     "watchlist_default":False},
    {"id":"c_cs_energy",  "name":"씨에스에너지",
     "aliases":["cs energy","씨에스에너지"],
     "sector":"ess",       "country":"KR", "stage":"First Commercial",
     "investor_type":"Strategic/CVC",
     "founded":2013,
     "hq":"울산, KR",
     "description":"ESS system integrator. SK Innovation supply chain. Ulsan 100MWh reference. ISO 9001 certified.",
     "tags":["비상장","ESS-SI","Series-A"],
     "known_investors":["SK이노베이션","중소기업은행"],
     "watchlist_default":False},
    # ── Global benchmarks ────────────────────────────────────────────────
    {"id":"c_form_energy","name":"Form Energy",
     "aliases":["form energy","formenergy"],
     "sector":"ess",       "country":"US", "stage":"Scaling",
     "investor_type":"Infrastructure/PF",
     "founded":2017,
     "hq":"Somerville MA, US",
     "description":"Iron-air 100h+ LDES. ArcelorMittal $100M strategic. Georgia gigafactory under construction. Three US utility contracts.",
     "tags":["비상장","Iron-Air","Series-E"],
     "known_investors":["ArcelorMittal","GS Energy","Breakthrough Energy"],
     "watchlist_default":True},
    {"id":"c_autogrid",   "name":"AutoGrid",
     "aliases":["autogrid","auto grid"],
     "sector":"grid_sw",   "country":"US", "stage":"Scaling",
     "investor_type":"Growth",
     "founded":2011,
     "hq":"Redwood City CA, US",
     "description":"VPP/Energy Intelligence Platform. Engie/E.ON/Shell investors. Commercial in 20+ countries. Singapore DC pilot underway.",
     "tags":["비상장","VPP","Series-D"],
     "known_investors":["Engie","E.ON","Shell"],
     "watchlist_default":True},
    {"id":"c_sunfire",    "name":"Sunfire",
     "aliases":["sunfire"],
     "sector":"hydrogen",  "country":"DE", "stage":"First Commercial",
     "investor_type":"Infrastructure/PF",
     "founded":2010,
     "hq":"Dresden, DE",
     "description":"SOEC electrolyzer. €215M raised. Carbon Direct capital management strategic. Supply agreements with multiple EU hydrogen projects.",
     "tags":["비상장","SOEC","Series-E"],
     "known_investors":["Carbon Direct","SMS Group","Neste"],
     "watchlist_default":False},
    {"id":"c_amogy",      "name":"Amogy",
     "aliases":["amogy"],
     "sector":"marine_fc", "country":"US", "stage":"Pilot",
     "investor_type":"Strategic/CVC",
     "founded":2020,
     "hq":"Brooklyn NY, US",
     "description":"Ammonia-to-power marine fuel cell. Tug boat 1MW demo completed. Samsung Heavy Industries investor.",
     "tags":["비상장","Ammonia-FC","Series-B"],
     "known_investors":["Samsung Heavy Industries","SK Innovation","Aramco Ventures"],
     "watchlist_default":False},
    {"id":"c_hysata",     "name":"Hysata",
     "aliases":["hysata"],
     "sector":"hydrogen",  "country":"AU", "stage":"Pilot",
     "investor_type":"Strategic/CVC",
     "founded":2021,
     "hq":"Wollongong, AU",
     "description":"Capillary-fed electrolyzer. Claims lowest LCOH path to date. Fortescue Future Industries backed.",
     "tags":["비상장","Electrolyzer","Series-B"],
     "known_investors":["Fortescue Future Industries","IP Group"],
     "watchlist_default":False},
    {"id":"c_ceres",      "name":"Ceres Power",
     "aliases":["ceres power","ceres"],
     "sector":"marine_fc", "country":"UK", "stage":"First Commercial",
     "investor_type":"Strategic/CVC",
     "founded":2001,
     "hq":"Horsham, UK",
     "description":"SOFC platform licensor. Bosch/Doosan/Delta strategic partners. LSE listed. Licensing model = asset-light commercial.",
     "tags":["상장","SOFC","Licensed"],
     "known_investors":["Bosch","Doosan","Delta Electronics"],
     "watchlist_default":False},
    {"id":"c_invinity",   "name":"Invinity Energy",
     "aliases":["invinity"],
     "sector":"ess",       "country":"UK", "stage":"First Commercial",
     "investor_type":"Growth",
     "founded":2019,
     "hq":"Edinburgh, UK",
     "description":"Vanadium flow battery manufacturer. Listed. UK/US/Australia commercial deployments.",
     "tags":["상장","VRFB","Commercial"],
     "known_investors":["Public","British Columbia Investment"],
     "watchlist_default":False},
]

# Strategic buyers — tracked independently for procurement signal intelligence
# MVP: static list, keyword matching
# Scale: buyer registry with procurement calendar, RFP database integration
STRATEGIC_BUYERS = [
    {"id":"b_kepco",      "name":"KEPCO",          "type":"Utility",    "region":"KR",
     "aliases":["kepco","한국전력","kpx"],
     "active_segments":["grid_sw","ess","hydrogen"],
     "procurement_notes":"VPP 실증사업 RFP 발주. DR·보조서비스 시장 참여기업 수요.",
     "annual_capex_est":"not disclosed — internal estimate removed",
     "decision_cycle":"RFP 공고 → 3-6개월"},
    {"id":"b_hd_hhi",     "name":"HD한국조선해양", "type":"Shipyard",   "region":"KR",
     "aliases":["hd hyundai","hd 현대","한국조선해양","hd hhi"],
     "active_segments":["marine_fc","hydrogen"],
     "procurement_notes":"암모니아 이중연료 선박 수주 확대. 연료전지 기술 내재화 검토.",
     "annual_capex_est":"not disclosed",
     "decision_cycle":"기술 검토 → MOU → 공식 수주 12-24개월"},
    {"id":"b_microsoft",  "name":"Microsoft",      "type":"Hyperscaler","region":"US",
     "aliases":["microsoft","azure","msft"],
     "active_segments":["dc_power","ess","forecasting"],
     "procurement_notes":"Nuclear PPA. 24/7 CFE 목표. DC power 파일럿 확대.",
     "annual_capex_est":"public figure: see Microsoft annual report for infrastructure capex",
     "decision_cycle":"파일럿 → 프레임워크 계약 → 스케일업 18-36개월"},
    {"id":"b_ls_elec",    "name":"LS일렉트릭",     "type":"EPC/OEM",   "region":"KR",
     "aliases":["ls electric","ls일렉트릭","ls elec"],
     "active_segments":["ess","grid_sw","hvdc"],
     "procurement_notes":"VPP 플랫폼 내재화 전략 추진. ESS 턴키 계약 확대.",
     "annual_capex_est":"not disclosed",
     "decision_cycle":"협력사 검토 → 파트너십 → 공급계약 6-18개월"},
    {"id":"b_engie",      "name":"Engie",          "type":"Utility",    "region":"EU",
     "aliases":["engie"],
     "active_segments":["ess","grid_sw","hydrogen"],
     "procurement_notes":"유럽 ESS 입찰 활성화. VPP 플랫폼 투자자이자 고객.",
     "annual_capex_est":"not disclosed — Engie annual report reference only",
     "decision_cycle":"파일럿 RFP → 평가 → 계약 6-12개월"},
    {"id":"b_samsung_hvy","name":"삼성중공업",     "type":"Shipyard",   "region":"KR",
     "aliases":["samsung heavy","삼성중공업","samsung hvy"],
     "active_segments":["marine_fc","hvdc"],
     "procurement_notes":"선박 연료전지 파일럿 프로그램. HVDC 해상풍력 연계.",
     "annual_capex_est":"not disclosed",
     "decision_cycle":"기술검토 → 파일럿 → 양산 24-36개월"},
    {"id":"b_google",     "name":"Google",         "type":"Hyperscaler","region":"US",
     "aliases":["google","alphabet","gcp"],
     "active_segments":["dc_power","ess","wte"],
     "procurement_notes":"24/7 CFE 100% 목표. 새로운 ESS 기술 파일럿 적극적.",
     "annual_capex_est":"public figure: see Alphabet annual report for infrastructure capex",
     "decision_cycle":"파일럿 → 배포 계약 12-24개월"},
    {"id":"b_sk_eco",     "name":"SK에코플랜트",   "type":"EPC",        "region":"KR",
     "aliases":["sk eco","sk에코","sk ecoplant"],
     "active_segments":["hydrogen","wte","ess"],
     "procurement_notes":"바이오가스→수소 전환. EPC로서 에너지 신기술 도입.",
     "annual_capex_est":"not disclosed",
     "decision_cycle":"기술 검증 → 파트너십 → 계약 12-18개월"},
]

# ══════════════════════════════════════════════════════════════════════════
# PROJECTS — Signal-Based Tracking
# ══════════════════════════════════════════════════════════════════════════
#
# Design: Projects are NOT static records. They are tracked through their
# signal history. Each project has:
#   - A fixed identity block (id, name, location, parties)
#   - A curated signal_log[] of known events, each with a source citation
#   - keyword_aliases[] so the RSS pipeline can auto-match new signals
#   - what_is_known[] / what_is_missing[] derived from the signal_log
#
# SIGNAL EVENT TYPES (project-level):
#   announcement    First public disclosure of the project's existence
#   pilot           Pilot / demonstration phase started or completed
#   partner         New partner, investor, or buyer involvement confirmed
#   certification   Third-party certification applied for or obtained
#   funding         Grant, equity, or debt financing confirmed
#   contract        Binding commercial agreement or offtake signed
#   construction    Physical construction or installation commenced
#   deployment      Commercial operation / go-live confirmed
#   delay           Timeline extension or cancellation announced
#   regulatory      Regulatory filing, permit, or EIA submitted / approved
#
# DATA INTEGRITY:
#   Every signal_log entry requires a source citation (source_of_record).
#   capacity / capex / timelines are shown ONLY if confirmed in that source.
#   "not disclosed" / "unknown" / "to be confirmed" are the correct defaults.
#   Do NOT generate or estimate any numerical value.
#
# PIPELINE INTEGRATION:
#   match_project(raw_text) checks keyword_aliases[] against each RSS item.
#   If matched, the event is appended to the project's inbound_signals[]
#   (separate from the curated signal_log, which is analyst-curated).
# ══════════════════════════════════════════════════════════════════════════

PROJECTS = [

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_busan_h2",
        "name":     "부산항 수소 벙커링 인프라",
        "location": "부산, KR",
        "type":     "port",
        "segments": ["hydrogen","marine_fc"],

        # Confirmed parties (source-cited only)
        "developer": "한국가스공사",
        "offtaker":  "HD한국조선해양",
        "epc":       "SK에코플랜트",

        # Pipeline matching — RSS items containing these keywords are
        # automatically flagged as potentially related to this project.
        # Analyst reviews inbound_signals[] and moves confirmed ones to signal_log[].
        "keyword_aliases": [
            "부산 수소 벙커링", "busan hydrogen bunkering",
            "한국가스공사 수소", "kogas hydrogen",
            "hd hhi bunkering", "imo 2030 busan",
        ],

        # Curated signal log — analyst-maintained, source-cited
        # Each entry: date, event_type, headline, source, confirmed facts, what_is_unknown
        "signal_log": [
            {
                "date":             "2023-06-15",
                "event_type":       "announcement",
                "headline":         "산업부, 부산항 수소 벙커링 실증사업 착수 발표",
                "source_of_record": "산업통상자원부 보도자료 2023-06-15",
                "source_url":       None,
                "confirmed_facts": [
                    "산업통상자원부가 부산항 수소 벙커링 실증 사업을 공식 발표",
                    "한국가스공사가 개발사로 지정",
                    "HD한국조선해양이 수소 오프테이커로 확인",
                ],
                "what_is_unknown": [
                    "사업 용량: 미공개",
                    "사업비: 미공개",
                    "운영 개시 일정: 미발표",
                ],
            },
            {
                "date":             "2023-11-20",
                "event_type":       "partner",
                "headline":         "SK에코플랜트, 부산 수소 벙커링 EPC 계약 체결 확인",
                "source_of_record": "SK에코플랜트 보도자료 2023-11-20",
                "source_url":       None,
                "confirmed_facts": [
                    "SK에코플랜트가 EPC 계약자로 확인",
                ],
                "what_is_unknown": [
                    "EPC 계약 금액: 미공개",
                    "시공 일정: 미발표",
                ],
            },
            {
                "date":             "2024-03-01",
                "event_type":       "pilot",
                "headline":         "부산항 수소 벙커링 파일럿 1단계 시설 설치 착수",
                "source_of_record": "에너지경제신문 2024-03-01 (1차 소스 확인 필요)",
                "source_url":       None,
                "confirmed_facts": [
                    "파일럿 단계 시설 설치 착수 보도",
                ],
                "what_is_unknown": [
                    "파일럿 용량: 미확인",
                    "DNV GL 수소 벙커링 인증 신청 여부: 미공개",
                    "수소 공급 가격 및 오프테이크 조건: 미공개",
                ],
            },
        ],

        # Derived from signal_log — updated by build_project_intel()
        # (Do not edit manually — regenerated on each pipeline run)
        "current_stage":   "Pilot",
        "what_is_known":   [],  # populated by build_project_intel()
        "what_is_missing": [],  # populated by build_project_intel()

        "investment_angle": "Korea's first hydrogen bunkering pilot — confirms IMO 2030 demand is real. Commercial terms and scale not yet public.",
        "linked_companies": ["c_vincen","c_hylium"],
        "linked_buyers":    ["b_hd_hhi","b_sk_eco"],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_jeju_hvdc",
        "name":     "제주 해상풍력 HVDC 연계",
        "location": "제주, KR",
        "type":     "grid",
        "segments": ["hvdc","ess"],

        "developer": "한국해상풍력",
        "offtaker":  "KEPCO",
        "epc":       "LS일렉트릭",

        "keyword_aliases": [
            "제주 hvdc", "jeju hvdc", "제주 해상풍력",
            "한국해상풍력 kepco", "jeju offshore wind",
            "제주-육지 연계",
        ],

        "signal_log": [
            {
                "date":             "2022-09-10",
                "event_type":       "announcement",
                "headline":         "KEPCO, 제주 해상풍력 HVDC 연계 사업 계획 공개",
                "source_of_record": "KEPCO 보도자료 2022-09-10",
                "source_url":       None,
                "confirmed_facts": [
                    "KEPCO가 제주-육지 HVDC 연계 사업 계획 발표",
                    "한국해상풍력이 개발사로 참여 확인",
                    "LS일렉트릭 EPC 계약 체결 — LS 보도자료 확인",
                ],
                "what_is_unknown": [
                    "용량: 500MW 보도 있으나 정부 공식 발표 원문 미확인",
                    "사업비: 언론 추정치 — 공식 수치 아님",
                    "환경영향평가 신청 현황: 미공개",
                ],
            },
            {
                "date":             "2023-04-05",
                "event_type":       "regulatory",
                "headline":         "제주 HVDC 사업 환경영향평가 협의 착수 보도",
                "source_of_record": "제주도청 보도자료 (확인 필요)",
                "source_url":       None,
                "confirmed_facts": [
                    "환경영향평가 협의 절차 착수 보도",
                ],
                "what_is_unknown": [
                    "환경영향평가 완료 예상 시점: 미발표",
                    "ESS 동반 탑재 여부: 미결정",
                    "착공 일정: 미공개",
                ],
            },
        ],

        "current_stage":   "Planned",
        "what_is_known":   [],
        "what_is_missing": [],

        "investment_angle": "KEPCO offtake confirmed. ESS co-location possible but not announced. Primary gate: EIA completion.",
        "linked_companies": ["c_standard_e"],
        "linked_buyers":    ["b_kepco","b_ls_elec"],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_incheon_vpp",
        "name":     "인천 LNG 터미널 VPP 실증",
        "location": "인천, KR",
        "type":     "grid",
        "segments": ["grid_sw","ess"],

        "developer": "SK E&S",
        "offtaker":  "KEPCO",
        "epc":       "그리드위즈",

        "keyword_aliases": [
            "인천 vpp", "인천 수요반응", "sk e&s vpp",
            "gridwiz kepco", "그리드위즈 인천",
            "incheon lng vpp", "kpx 보조서비스 인천",
        ],

        "signal_log": [
            {
                "date":             "2024-01-18",
                "event_type":       "announcement",
                "headline":         "SK E&S, KEPCO와 인천 LNG 터미널 VPP 실증 계약 체결",
                "source_of_record": "SK E&S 보도자료 2024-01-18",
                "source_url":       None,
                "confirmed_facts": [
                    "SK E&S와 KEPCO 간 VPP 실증 계약 체결 확인",
                    "그리드위즈가 VPP/DR 기술 공급자로 지정",
                    "실증 위치: 인천 LNG 터미널 단지",
                    "KPX 보조서비스 시장 참여가 사업 목표로 명시",
                ],
                "what_is_unknown": [
                    "DR 용량: 공식 발표 없음",
                    "계약 금액: 미공개",
                    "파일럿 기간 및 KPI 목표: 미공개",
                ],
            },
            {
                "date":             "2024-06-10",
                "event_type":       "pilot",
                "headline":         "인천 VPP 실증 운영 개시 — KPX 보조서비스 시장 시험 참여",
                "source_of_record": "그리드위즈 보도자료 2024-06-10",
                "source_url":       None,
                "confirmed_facts": [
                    "파일럿 운영 개시 확인",
                    "KPX 보조서비스 시장 시험 참여 확인",
                ],
                "what_is_unknown": [
                    "파일럿 성과 지표: 미공개",
                    "상업 계약으로의 전환 조건: 미공개",
                    "실적 데이터 공개 일정: 미발표",
                ],
            },
        ],

        "current_stage":   "Pilot",
        "what_is_known":   [],
        "what_is_missing": [],

        "investment_angle": "그리드위즈 Series C 선행 검증 프로젝트. KPX 실적 공개가 핵심 촉매.",
        "linked_companies": ["c_gridwiz"],
        "linked_buyers":    ["b_kepco","b_ls_elec"],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_sg_dc",
        "name":     "Singapore DC Power Optimisation",
        "location": "Singapore",
        "type":     "data_center",
        "segments": ["dc_power","forecasting"],

        "developer": "GIC (reported — primary source unconfirmed)",
        "offtaker":  "Microsoft",
        "epc":       "unknown — not yet announced",

        "keyword_aliases": [
            "autogrid singapore", "singapore vpp microsoft",
            "gic data center singapore", "microsoft cfe singapore",
            "singapore dc power optimisation",
        ],

        "signal_log": [
            {
                "date":             "2024-09-05",
                "event_type":       "partner",
                "headline":         "AutoGrid confirms Microsoft partnership for VPP platform in Singapore",
                "source_of_record": "AutoGrid press release 2024-09-05",
                "source_url":       None,
                "confirmed_facts": [
                    "AutoGrid–Microsoft partnership for Singapore VPP deployment confirmed",
                    "Microsoft 24/7 CFE commitment is publicly stated policy",
                ],
                "what_is_unknown": [
                    "GIC as developer: trade press only — not confirmed in primary filing",
                    "Project capacity / MW: not disclosed",
                    "Contract value: not disclosed",
                    "EPC contractor: not announced",
                    "Project timeline: not public",
                ],
            },
        ],

        "current_stage":   "Planned",
        "what_is_known":   [],
        "what_is_missing": [],

        "investment_angle": "Hyperscaler-backed VPP pilot. AutoGrid SEA commercial validation. All financial terms undisclosed.",
        "linked_companies": ["c_autogrid"],
        "linked_buyers":    ["b_microsoft"],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_ulsan_ess",
        "name":     "울산 산업단지 ESS 실증",
        "location": "울산, KR",
        "type":     "industrial",
        "segments": ["ess"],

        "developer": "울산시",
        "offtaker":  "SK이노베이션",
        "epc":       "씨에스에너지",

        "keyword_aliases": [
            "울산 ess", "울산 에너지저장", "씨에스에너지 울산",
            "sk이노베이션 ess", "울산 산업단지 ess",
            "ulsan ess", "cs energy ulsan",
        ],

        "signal_log": [
            {
                "date":             "2023-08-22",
                "event_type":       "announcement",
                "headline":         "울산시, 산업단지 ESS 실증 사업 착수 발표",
                "source_of_record": "울산시청 보도자료 2023-08-22",
                "source_url":       None,
                "confirmed_facts": [
                    "울산시가 산업단지 ESS 실증 사업 공식 발표",
                    "씨에스에너지가 EPC 계약자로 확인 — 씨에스에너지 보도자료",
                    "SK이노베이션이 산업 오프테이커로 지정",
                ],
                "what_is_unknown": [
                    "용량: 100MWh 보도 있으나 DART 공시 원문 확인 필요",
                    "계약금액: ₩760억 보도 — DART 원문 확인 필요",
                ],
            },
            {
                "date":             "2024-02-14",
                "event_type":       "construction",
                "headline":         "울산 ESS 실증 시설 착공 확인",
                "source_of_record": "씨에스에너지 보도자료 2024-02-14",
                "source_url":       None,
                "confirmed_facts": [
                    "착공 확인 — 씨에스에너지 공식 발표",
                    "공사 중 단계로 전환 확인",
                ],
                "what_is_unknown": [
                    "준공 및 상업운전 개시 일정: 미발표",
                    "성능 보증 조건: 미공개",
                ],
            },
        ],

        "current_stage":   "Construction",
        "what_is_known":   [],
        "what_is_missing": [],

        "investment_angle": "씨에스에너지 첫 대기업 공급망 ESS 레퍼런스. 상업운전 발표가 핵심 이벤트.",
        "linked_companies": ["c_cs_energy"],
        "linked_buyers":    ["b_sk_eco"],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "id":       "p_rotterdam",
        "name":     "Rotterdam Green Hydrogen Terminal",
        "location": "Rotterdam, NL",
        "type":     "port",
        "segments": ["hydrogen"],

        "developer": "Port of Rotterdam Authority",
        "offtaker":  "unknown — no binding offtake agreement announced",
        "epc":       "unknown — tender not issued",

        "keyword_aliases": [
            "rotterdam hydrogen terminal", "port of rotterdam hydrogen",
            "rotterdam green hydrogen", "maasvlakte hydrogen",
            "rotterdam electrolyzer", "rotterdam h2",
        ],

        "signal_log": [
            {
                "date":             "2021-11-10",
                "event_type":       "announcement",
                "headline":         "Port of Rotterdam publishes hydrogen import terminal concept in planning documents",
                "source_of_record": "Port of Rotterdam Authority planning documentation (non-binding)",
                "source_url":       "https://www.portofrotterdam.com",
                "confirmed_facts": [
                    "Port of Rotterdam Authority has published hydrogen terminal concept",
                    "Terminal purpose: import and distribution of green hydrogen",
                    "Capacity figure (1GW electrolyzer) is aspirational — from planning docs, not binding commitment",
                    "CapEx figure (€4.2B) is aspirational estimate — no FID made",
                ],
                "what_is_unknown": [
                    "Binding offtake agreement: not announced",
                    "EPC contractor: not selected",
                    "Final Investment Decision: not made — date unknown",
                    "Capital commitment: no committed capital — aspirational only",
                    "Regulatory approval: unknown",
                    "H2 supply origin (domestic EU vs. import): not confirmed",
                ],
            },
            {
                "date":             "2023-05-22",
                "event_type":       "partner",
                "headline":         "Engie and Port of Rotterdam sign hydrogen cooperation agreement",
                "source_of_record": "Engie press release 2023-05-22 (verification recommended)",
                "source_url":       None,
                "confirmed_facts": [
                    "Engie and Port of Rotterdam cooperation agreement reported",
                ],
                "what_is_unknown": [
                    "Agreement type: MOU vs. binding contract not confirmed",
                    "Engie's financial commitment: not disclosed",
                    "Volume or pricing terms: not public",
                ],
            },
        ],

        "current_stage":   "Planned",
        "what_is_known":   [],
        "what_is_missing": [],

        "investment_angle": "EU H2 import infrastructure concept. No binding commitments. Long-term demand signal only — not a near-term investment catalyst.",
        "linked_companies": ["c_hylium"],
        "linked_buyers":    ["b_engie"],
    },
]


# Sector rulebooks — per-segment investment signal logic
# MVP: embedded in scoring/why_it_matters
# Paid pilot: sector modules (ESS pack, Marine FC pack, Hydrogen pack) as separate SKUs
# Scale: analyst-curated sector rulebooks updated quarterly
SECTOR_RULEBOOKS = {
    "ess": {
        "name": "Long-Duration Energy Storage",
        "key_gate": "Third-party certification (UL 9540, IEC 62619) + grid interconnection agreement",
        "commercial_threshold": "First offtake or supply agreement with named utility/industrial",
        "buyer_types": ["Grid operators","Utilities","Hyperscalers","Industrial C&I"],
        "lcos_benchmark": "Industry estimates vary — verify against latest BNEF/Wood Mackenzie reports before citing. No single authoritative figure.",
        "policy_driver": "IRA Storage ITC (US), EU Battery Regulation, KR RPS ESS 가중치",
        "red_flags": ["Grant-only (no offtaker)","Li-ion commodity competition","Single geography exposure"],
        "positive_signals": ["Utility framework contract","Hyperscaler pilot with CFE mandate","Co-location with offshore wind","DOE grant + offtaker co-investment"],
    },
    "marine_fc": {
        "name": "Marine Fuel Cells",
        "key_gate": "DNV GL or ClassNK class approval (Type Approval Certificate)",
        "commercial_threshold": "Named shipyard contract post-certification (newbuild or retrofit)",
        "buyer_types": ["Shipyards","Shipping companies","Port operators"],
        "lcos_benchmark": "Cost benchmarks not standardised across vessels. Verify against shipyard-specific RFQ data.",
        "policy_driver": "IMO CII 2024, EU ETS Ships 2024, IMO 2030 GHG Strategy",
        "red_flags": ["No DNV GL path defined","Hydrogen supply chain unresolved","Single fuel-type dependency"],
        "positive_signals": ["DNV GL/ClassNK type approval","Shipyard newbuild specification","Port bunkering infrastructure co-development"],
    },
    "grid_sw": {
        "name": "Grid Software / VPP",
        "key_gate": "Grid operator certification (KPX, FERC, ENTSO-E) + first recurring revenue contract",
        "commercial_threshold": "Multi-year framework contract with named utility/TSO",
        "buyer_types": ["Utilities","TSOs/DSOs","C&I aggregators","Hyperscalers"],
        "lcos_benchmark": "No public benchmark standard. Contract values vary widely by utility size and geography.",
        "policy_driver": "FERC 2222 (US), EU Flexibility Markets, KPX 보조서비스 제도 개편",
        "red_flags": ["Single utility dependency","No API/integration layer","Vertical incumbent competition (Siemens, GE)"],
        "positive_signals": ["KPX/FERC certified","Multi-utility framework","CFO hire + international BD"],
    },
    "hydrogen": {
        "name": "Hydrogen Infrastructure",
        "key_gate": "Named offtaker at contracted price (not MOU) + permits",
        "commercial_threshold": "First commercial delivery or long-term supply agreement (>3 years)",
        "buyer_types": ["Refineries","Port operators","Industrial facilities","Shipping companies"],
        "lcos_benchmark": "EU target: <$2/kg by 2030 (source: EU Hydrogen Strategy). US DOE target: <$1/kg by 2031 (source: DOE H2 Earthshot). Current cost varies — verify against latest project data.",
        "policy_driver": "EU Green Hydrogen Standard, US Inflation Reduction Act §45V, MOTIE 수소경제 로드맵",
        "red_flags": ["Grant-only (no offtaker)","LCOH without credible cost-down pathway to offtaker-viable price","No offtake contract"],
        "positive_signals": ["Named industrial offtaker + contracted price","Port/bunkering infrastructure connection","EU H2 Bank award"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# SECTION 3  CLASSIFICATION RULEBOOK  (transparent, no black-box)
# ══════════════════════════════════════════════════════════════════════════
# MVP: embedded, transparent to any user
# Scale: sector-specific rulebooks, analyst-overridable thresholds

EVENT_RULES = [
    # Tier 1: Concrete commercial/technical action  base 85-92
    {"kws":["class approval","dnv gl","dnv certified","kpx certified","atex certified","tuv certified","ul listed","iec certified","type approved"],
     "type":"Certification","impact":"Commercial","score":88,"tier":1,"neg_subtype":None},
    {"kws":["commercial contract","offtake agreement","supply agreement","signed contract","power purchase agreement","ppa signed","framework contract","master supply","long-term supply"],
     "type":"Contract","impact":"Commercial","score":92,"tier":1,"neg_subtype":None},
    {"kws":["commissioned","now operational","goes live","first delivery","deployed at","system online","live deployment","commercial operation date","cod achieved"],
     "type":"Deployment","impact":"Commercial","score":88,"tier":1,"neg_subtype":None},
    # Tier 2: Validated progress  base 60-82
    {"kws":["utility pilot","kepco pilot","hyperscaler pilot","shipyard pilot","grid operator pilot","named buyer pilot"],
     "type":"Pilot","impact":"Technical","score":80,"tier":2,"neg_subtype":None},
    {"kws":["pilot project","pilot program","field trial","demonstration project","demo installation","test deployment"],
     "type":"Pilot","impact":"Technical","score":62,"tier":2,"neg_subtype":None},
    {"kws":["series a","series b","series c","series d","series e","raised $","raised €","raised £","funding round","growth equity","venture round","strategic investment"],
     "type":"Financing","impact":"Financing","score":82,"tier":2,"neg_subtype":None},
    {"kws":["cfo","chief financial officer","appoints cfo","new cfo","vp finance","head of finance","finance director joins"],
     "type":"Hiring","impact":"Funding Signal","score":78,"tier":2,"neg_subtype":None},
    {"kws":["vp sales","chief commercial officer","vp business development","head of business development","commercial director"],
     "type":"Hiring","impact":"Commercial","score":68,"tier":2,"neg_subtype":None},
    # Tier 3: Directional  base 36-72
    {"kws":["strategic partnership with","mou signed with","joint development agreement","cooperation agreement signed"],
     "type":"Partnership","impact":"Commercial","score":58,"tier":3,"neg_subtype":None},
    {"kws":["partnership","mou","collaboration","memorandum of understanding","joint development"],
     "type":"Partnership","impact":"Commercial","score":36,"tier":3,"neg_subtype":None},
    {"kws":["doe grant","eu grant","government grant","awarded grant","horizon europe","innovate uk","nrel award","motie grant"],
     "type":"Grant","impact":"Policy","score":46,"tier":3,"neg_subtype":None},
    {"kws":["gigafactory","manufacturing plant","new production facility","scale-up facility","opens facility"],
     "type":"Expansion","impact":"Commercial","score":72,"tier":3,"neg_subtype":None},
    # Tier 4: Negative — always surfaced, no threshold
    {"kws":["delay","postponed","behind schedule","timeline slips","pushed back","project delayed"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"delay"},
    {"kws":["funding shortfall","struggles to raise","runway concerns","bridge loan needed"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"funding_risk"},
    {"kws":["cost overrun","over budget","capex increase","construction cost increase"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"cost_overrun"},
    {"kws":["supply chain issue","component shortage","material shortage","delivery delay"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"supply_chain"},
    {"kws":["hiring freeze","layoffs","redundancies","headcount reduction","staff cuts"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"hiring_freeze"},
    {"kws":["project cancelled","contract cancelled","project terminated","deal collapsed"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"cancellation"},
    {"kws":["competitor wins","competitor awarded","rival secures","loses contract to","outbid by"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"competitor_win"},
    {"kws":["subsidy ends","grant expires","policy reversal","mandate removed"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"subsidy_risk"},
]

SEGMENT_KWS = {
    "ess":         ["battery","energy storage","ess","vanadium","iron-air","flow battery","long duration","bess","grid storage"],
    "marine_fc":   ["marine","vessel","ship","fuel cell","amogy","shipping","imo cii","bunkering","maritime"],
    "grid_sw":     ["vpp","virtual power","demand response","grid software","kepco","ancillary","frequency regulation"],
    "hvdc":        ["hvdc","transmission","subsea cable","offshore wind cable","interconnect"],
    "hydrogen":    ["hydrogen","electrolyzer","h2","liquid hydrogen","green hydrogen","electrolysis","ammonia"],
    "dc_power":    ["data center","hyperscaler","azure","aws","google cloud","power electronics","ai infrastructure"],
    "wte":         ["waste-to-energy","biogas","biomass","waste","incineration"],
    "forecasting": ["forecast","prediction","renewable forecast","grid forecast","ai grid"],
}


# ══════════════════════════════════════════════════════════════════════════
# SECTION 4  SCORING ENGINE
# ══════════════════════════════════════════════════════════════════════════

SCORE_THRESHOLD_HIGH   = 60
SCORE_THRESHOLD_MEDIUM = 35
SCORE_THRESHOLD_KEEP   = 20

SCORE_RULES = [
    {"id":"buyer_t1",  "pattern":r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\be\.on\b|\bvattenfall\b|\bnationalgrid\b",
     "delta":+18,"group":"boost","reason":"Tier-1 strategic buyer named"},
    {"id":"buyer_t2",  "pattern":r"\bhyundai\b|\bsamsung\b|\bhanwha\b|\bshell\b|\bbp\b|\bsiemens\b|\babb\b|\bhitachi\b",
     "delta":+12,"group":"boost","reason":"Major industrial/OEM buyer named"},
    {"id":"buyer_kr",  "pattern":r"\bls electric\b|\bls일렉트릭\b|\bsk e&s\b|\bsk에코\b|\bposco\b|\bhd hyundai\b|\b한국가스공사\b",
     "delta":+10,"group":"boost","reason":"Korean strategic buyer named"},
    {"id":"fig_money", "pattern":r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]|₩[\d,]+억",
     "delta":+15,"group":"boost","reason":"Specific financial figure"},
    {"id":"fig_mw",    "pattern":r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b",
     "delta":+10,"group":"boost","reason":"Specific capacity figure"},
    {"id":"timeframe", "pattern":r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month|H[12] 20[2-9]\d",
     "delta":+8, "group":"boost","reason":"Concrete timeframe stated"},
    {"id":"geography", "pattern":r"\bbusan\b|\bincheon\b|\bulsan\b|\brotterdam\b|\bsingapore\b|\bhamburg\b|\baberdeen\b",
     "delta":+5, "group":"boost","reason":"Named project location"},
    {"id":"co_match",  "pattern":None,
     "delta":+10,"group":"boost","reason":"Event matched to tracked company"},
    {"id":"n_vague",   "pattern":r"\bexploring\b.{0,30}\bpartner|\blooking to\b.{0,20}\bpartner|\bin (early )?discussions\b|\bpotential (partner|deal)\b",
     "delta":-35,"group":"noise","reason":"Vague exploratory language"},
    {"id":"n_intent",  "pattern":r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b",
     "delta":-20,"group":"noise","reason":"Intent stated, no confirmed action"},
    {"id":"n_specul",  "pattern":r"\bcould (become|reach|achieve|unlock)\b|\bmay (become|unlock)\b|\bhas the potential\b",
     "delta":-25,"group":"noise","reason":"Speculative outcome framing"},
    {"id":"n_pr",      "pattern":r"\bproud to (announce|partner|share)\b|\bexcited to (announce|share)\b|\bpleased to announce\b",
     "delta":-40,"group":"noise","reason":"Generic PR language"},
    {"id":"n_vision",  "pattern":r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b",
     "delta":-30,"group":"noise","reason":"Vision/strategy announcement"},
    {"id":"n_award",   "pattern":r"\bwins? award\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b|\bgartner\b",
     "delta":-35,"group":"noise","reason":"Vanity recognition"},
    {"id":"n_conf",    "pattern":r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b|\battends? (conference|summit)\b",
     "delta":-30,"group":"noise","reason":"Conference appearance only"},
    {"id":"n_report",  "pattern":r"\bpublishes? (report|study|whitepaper)\b|\bnew (report|research|study)\b",
     "delta":-25,"group":"noise","reason":"Report/research only"},
    {"id":"v_rebrand", "pattern":r"\brebrands?\b|\bnew (logo|brand|website)\b",
     "delta":-55,"group":"veto", "reason":"Rebranding/marketing"},
    {"id":"v_opinion", "pattern":r"\bopinion:\b|\bcommentary:\b|\bop-ed\b",
     "delta":-60,"group":"veto", "reason":"Opinion/commentary"},
    {"id":"v_digest",  "pattern":r"\bmarket (wrap|roundup|update)\b|\bweekly (round-?up|digest)\b|\bmonthly digest\b",
     "delta":-60,"group":"veto", "reason":"Market wrap/digest"},
    {"id":"v_job",     "pattern":r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b|\bcareer opportunit\b",
     "delta":-50,"group":"veto", "reason":"Generic job posting"},
]

SCORE_RULEBOOK_DISPLAY = [
    {"group":"ALWAYS KEPT",        "color":"#16A34A","items":["Negative signals — exempt from threshold","Tier 1: Certification/Contract/Deployment — base 88-92"]},
    {"group":"BOOST (+points)",    "color":"#1A56DB","items":["Tier-1 buyer (KEPCO, Microsoft, Google): +18","Major industrial/OEM (Hyundai, Samsung): +12","Specific financial figure ($45M, ₩760억): +15","Specific capacity (500MWh, 2GW): +10","Concrete timeframe (Q3 2026): +8","Tracked company matched: +10"]},
    {"group":"NOISE (−points)",    "color":"#D97706","items":["Vague language (exploring, potential): -35","Intent without action (aims to): -20","Generic PR (proud to announce): -40","Vision/strategy: -30","Industry award/Gartner: -35","Conference appearance: -30","Report publication: -25"]},
    {"group":"VETO (always drop)", "color":"#DC2626","items":["Opinion/commentary: -60","Market wrap/digest: -60","Generic job posting: -50","Rebranding: -55"]},
    {"group":"THRESHOLDS",         "color":"#6E6E6E","items":["≥ 60 → HIGH (default feed)","35–59 → MEDIUM","20–34 → LOW (DB only)","< 20 → DROPPED","Negatives: exempt"]},
]

NEG_SUBTYPE_META = {
    "delay":         {"label":"Delay",                  "icon":"⏱","severity":"high",    "memo":"Timeline extension raises capital-at-risk. Project-level vs. structural distinction is key."},
    "funding_risk":  {"label":"Funding / Runway Risk",  "icon":"⚠","severity":"critical","memo":"Capital constraint signal. Bridge or down-round possible. Monitor investor behavior."},
    "cost_overrun":  {"label":"Cost Overrun",           "icon":"📈","severity":"high",   "memo":"Capex overshoot compresses returns. Reassess unit economics."},
    "supply_chain":  {"label":"Supply Chain Issue",     "icon":"🔗","severity":"medium", "memo":"Component shortage delays deployment. Check if systemic or single-vendor."},
    "hiring_freeze": {"label":"Hiring Freeze / Layoffs","icon":"👥","severity":"high",   "memo":"Headcount reduction signals cost pressure or strategic pivot."},
    "cancellation":  {"label":"Cancellation",           "icon":"✗","severity":"critical","memo":"Revenue removed. Determine demand vs. execution cause."},
    "competitor_win":{"label":"Competitor Win",         "icon":"🏆","severity":"medium", "memo":"Named competitor contract in same TAM. Reassess differentiation thesis."},
    "subsidy_risk":  {"label":"Policy / Subsidy Risk",  "icon":"🏛","severity":"high",   "memo":"Subsidy-dependent revenue without commercial anchor is not investable."},
}

MISSING_RULES = [
    {"id":"no_contract",  "label":"No Commercial Contract",          "severity":"critical",
     "check": lambda evs: not any(e["event_type"] in ("Contract","Deployment") for e in evs),
     "memo": "No binding commercial agreement on record. All revenue is hypothetical.",
     "sectors":"all"},
    {"id":"no_cert",      "label":"No Third-Party Certification",    "severity":"high",
     "check": lambda evs: not any(e["event_type"]=="Certification" for e in evs),
     "memo": "No independent certification (DNV GL, TÜV, KPX, UL). Required for regulated procurement.",
     "sectors":["marine_fc","ess","hvdc","grid_sw"]},
    {"id":"no_buyer",     "label":"No Named Strategic Buyer",        "severity":"high",
     "check": lambda evs: not any(re.search(r"kepco|utility|shipyard|hyperscaler|microsoft|google|amazon|engie|hanwha|hyundai|samsung|ls electric",(e.get("title","")+" "+e.get("summary","")).lower()) for e in evs),
     "memo": "No named strategic buyer in any signal. Demand-side validation absent.",
     "sectors":"all"},
    {"id":"no_deploy",    "label":"No Deployment / Go-Live",         "severity":"medium",
     "check": lambda evs: not any(e["event_type"]=="Deployment" for e in evs),
     "memo": "No operational deployment confirmed. TRL-9 in commercial setting unverified.",
     "sectors":"all"},
    {"id":"pilot_gap",    "label":"Pilot → No Contract Conversion",  "severity":"high",
     "check": lambda evs: any(e["event_type"]=="Pilot" for e in evs) and not any(e["event_type"] in ("Contract","Deployment") for e in evs),
     "memo": "Pilot present but no commercial conversion. Most common failure point in energy hardware.",
     "sectors":"all"},
    {"id":"grant_only",   "label":"Grant Only — No Commercial Anchor","severity":"high",
     "check": lambda evs: any(e["event_type"]=="Grant" for e in evs) and not any(e["event_type"] in ("Contract","Pilot","Deployment") for e in evs),
     "memo": "Grant funding without commercial anchor. Not investable as standalone signal.",
     "sectors":"all"},
]


# ══════════════════════════════════════════════════════════════════════════
# SECTION 5  EVIDENCE CARD LIBRARIES
# ══════════════════════════════════════════════════════════════════════════

WHY_IT_MATTERS = {
    ("Certification","marine_fc"):  "Class approval removes the primary procurement barrier for marine fuel cells. Without it, shipyards cannot specify the technology in newbuild contracts.",
    ("Certification","ess"):        "Third-party certification (UL/IEC/KS) is required for grid interconnection and utility procurement. De-risks buyer liability.",
    ("Certification","grid_sw"):    "KPX interface certification is the legal prerequisite for Korea's ancillary services market. Directly unlocks recurring revenue.",
    ("Certification","hvdc"):       "TÜV/DNV component qualification required for OEM supply chains (Siemens, ABB, Hitachi). Without it, no grid-scale procurement is possible.",
    ("Contract","grid_sw"):         "Named utility contract moves company from pilot-stage to commercial-stage. Key unknowns: ACV, duration, framework vs. project-specific.",
    ("Contract","ess"):             "Offtake/supply agreement is the clearest commercial-stage signal. LCOS competitiveness implied but requires contract terms for confirmation.",
    ("Contract","marine_fc"):       "Named shipyard/shipping contract post-certification is the standard commercialization sequence. First revenue-generating event.",
    ("Contract","hydrogen"):        "Offtake agreement is the critical missing link in most hydrogen project theses. Without a named buyer at contracted price, projects remain unviable.",
    ("Pilot","grid_sw"):            "Utility-sponsored pilot implies buyer has allocated opex budget. Pilot-to-commercial conversion rate is the key metric.",
    ("Pilot","marine_fc"):          "Shipyard pilot validates vessel integration architecture. DNV involvement substantially increases class approval probability.",
    ("Pilot","ess"):                "Grid-connected pilot signals utility-scale targeting. Requires KPX/NERC interface compliance — itself a commercialization gate.",
    ("Pilot","dc_power"):           "Hyperscaler pilot is the strongest commercial signal for DC power tech. High ACV, low churn once contracted.",
    ("Financing","default"):        "Equity round confirms external capital validation. Key variables: investor identity (strategic vs. financial), round size vs. capex needs.",
    ("Hiring","default"):           "CFO hire with Series B+ experience correlates with fundraising within 3–6 months. BD/Sales hire signals active contract pipeline.",
    ("Partnership","default"):      "Named strategic partnership is directional. MOU alone does not confirm commercial intent — check for binding terms.",
    ("Grant","default"):            "Government grant validates technology policy relevance but not market demand. Grant-only is not investable without commercial anchor.",
    ("Negative","default"):         "Negative signals require investment timeline reassessment. Determine if project-level or structural.",
    ("News","default"):             "No specific investment pattern matched. Context only — not weighted without corroboration.",
}

MISSING_BY_TYPE = {
    ("Contract","default"):   ["Contract ACV not disclosed","Duration and renewal terms not public","Exclusivity and geographic scope unknown"],
    ("Pilot","default"):      ["Pilot success criteria not publicly defined","Conversion probability to commercial unknown"],
    ("Financing","default"):  ["Post-money valuation not confirmed","Use of proceeds not specified"],
    ("Hiring","default"):     ["Fundraising timeline not confirmed","Whether hire reflects inbound interest or proactive prep unknown"],
    ("Partnership","default"):["Binding terms (exclusivity, minimum volume) not confirmed","IP ownership unclear"],
    ("Grant","default"):      ["Commercial co-funding partner not identified","Path from grant to commercial revenue not articulated"],
    ("Negative","default"):   ["Root cause not confirmed","Management mitigation plan not public"],
    ("News","default"):       ["No investment-relevant pattern matched","Primary research required"],
}


# ══════════════════════════════════════════════════════════════════════════
# SECTION 6  PIPELINE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def classify(raw_text):
    for rule in EVENT_RULES:
        for kw in rule["kws"]:
            if kw in raw_text:
                return {"type":rule["type"],"impact":rule["impact"],"base_score":rule["score"],
                        "tier":rule["tier"],"matched":kw,"neg_subtype":rule["neg_subtype"]}
    return {"type":"News","impact":"Informational","base_score":15,"tier":5,"matched":None,"neg_subtype":None}

def infer_segment(raw_text, src_segs):
    for seg, kws in SEGMENT_KWS.items():
        if any(kw in raw_text for kw in kws): return seg
    return src_segs[0] if src_segs else "unknown"

def match_company(raw_text):
    for co in COMPANIES:
        if any(a.lower() in raw_text for a in co["aliases"]):
            return co["id"], co["name"]
    return None, None

def match_buyers(raw_text):
    return [{"id":b["id"],"name":b["name"],"type":b["type"]}
            for b in STRATEGIC_BUYERS if any(a.lower() in raw_text for a in b["aliases"])]

def match_project(raw_text):
    """Match RSS item against project keyword_aliases.
    Returns list of matching project IDs.
    These become inbound_signals on the project — analyst reviews before adding to signal_log."""
    return [p["id"] for p in PROJECTS
            if any(kw.lower() in raw_text for kw in p.get("keyword_aliases", []))]

# Signal type metadata for UI rendering
PROJECT_SIGNAL_TYPES = {
    "announcement":  {"label":"Announcement",   "icon":"📣", "color":"#1A56DB", "weight":1},
    "pilot":         {"label":"Pilot",           "icon":"🔬", "color":"#7D4E00", "weight":3},
    "partner":       {"label":"Partner",         "icon":"🤝", "color":"#5B21B6", "weight":2},
    "certification": {"label":"Certification",   "icon":"✓",  "color":"#0A6640", "weight":4},
    "funding":       {"label":"Funding",         "icon":"💰", "color":"#0A6640", "weight":3},
    "contract":      {"label":"Contract",        "icon":"📄", "color":"#0A6640", "weight":5},
    "construction":  {"label":"Construction",    "icon":"🏗",  "color":"#1A56DB", "weight":3},
    "deployment":    {"label":"Deployment",      "icon":"🚀", "color":"#16A34A", "weight":5},
    "delay":         {"label":"Delay",           "icon":"⏱",  "color":"#C0392B", "weight":-2},
    "regulatory":    {"label":"Regulatory",      "icon":"🏛",  "color":"#6E6E6E", "weight":1},
}

# Stage progression ladder for projects
# stage is inferred from the most recent signal_log event type
PROJECT_STAGE_LADDER = [
    ("Deployed",     "#16A34A", {"deployment"}),
    ("Construction", "#1A56DB", {"construction","contract"}),
    ("Pilot",        "#7D4E00", {"pilot","certification"}),
    ("Partner",      "#5B21B6", {"partner","funding"}),
    ("Announced",    "#6E6E6E", {"announcement","regulatory"}),
    ("Unknown",      "#A8A8A8", set()),
]

def infer_project_stage(signal_log):
    """Infer current project stage from signal history.
    Most advanced confirmed event type wins."""
    types_seen = {e["event_type"] for e in signal_log}
    for label, color, required in PROJECT_STAGE_LADDER:
        if required & types_seen:
            return label, color
    return "Unknown", "#A8A8A8"

def build_project_intel(project, inbound_signals=None):
    """
    Enrich a project with derived intelligence from its signal_log.
    - Derives current_stage from most advanced confirmed event
    - Builds what_is_known from all confirmed_facts across signal_log
    - Builds what_is_missing from most recent entry's what_is_unknown
    - Computes signal velocity (events per 90 days)
    - Attaches inbound_signals from RSS pipeline (analyst review required)
    - No invented data. Only aggregates from signal_log entries.
    """
    log = project.get("signal_log", [])

    # Sort by date
    log_sorted = sorted(log, key=lambda e: e.get("date",""), reverse=True)
    log_asc    = sorted(log, key=lambda e: e.get("date",""))

    # Infer stage
    stage_label, stage_color = infer_project_stage(log)

    # Aggregate all confirmed facts
    all_known = []
    for entry in log_asc:
        date = entry.get("date","")
        stype = entry.get("event_type","")
        meta  = PROJECT_SIGNAL_TYPES.get(stype,{})
        for fact in entry.get("confirmed_facts",[]):
            all_known.append({
                "fact":       fact,
                "date":       date,
                "event_type": stype,
                "icon":       meta.get("icon","●"),
                "source":     entry.get("source_of_record","unknown source"),
            })

    # Most recent entry's unknowns = current missing evidence
    all_missing = []
    if log_sorted:
        latest = log_sorted[0]
        for unk in latest.get("what_is_unknown",[]):
            all_missing.append({
                "item":   unk,
                "as_of":  latest.get("date",""),
                "source": latest.get("source_of_record",""),
            })

    # Negative signals in log
    negative_events = [e for e in log if e.get("event_type") == "delay"]

    # Signal velocity — how many events in last 90 days
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_events = [e for e in log if e.get("date","") >= cutoff]

    # Detect current signal pattern
    types = {e["event_type"] for e in log}
    has_contract    = "contract"  in types or "deployment" in types
    has_pilot       = "pilot"     in types
    has_cert        = "certification" in types
    has_partner     = "partner"   in types
    has_delay       = "delay"     in types
    has_funding     = "funding"   in types

    if has_delay:
        pattern = "⚠ Delay detected — reassess timeline assumptions."
        pattern_color = "#C0392B"
    elif has_contract:
        pattern = "Commercial confirmation — binding agreement or deployment on record."
        pattern_color = "#0A6640"
    elif has_cert and has_pilot:
        pattern = "Technical gates clearing — certification + pilot both confirmed."
        pattern_color = "#1A56DB"
    elif has_pilot and has_partner:
        pattern = "Strategic validation — pilot with named partner confirmed."
        pattern_color = "#5B21B6"
    elif has_pilot:
        pattern = "Pilot stage — no commercial conversion confirmed yet."
        pattern_color = "#7D4E00"
    elif has_partner or has_funding:
        pattern = "Early momentum — partner or funding signal, no technical gate cleared."
        pattern_color = "#7D4E00"
    else:
        pattern = "Announced only — no technical or commercial gate cleared."
        pattern_color = "#6E6E6E"

    return {
        **project,
        "current_stage":     stage_label,
        "stage_color":       stage_color,
        "signal_log_sorted": log_sorted,
        "what_is_known":     all_known,
        "what_is_missing":   all_missing,
        "negative_events":   negative_events,
        "recent_event_count":len(recent_events),
        "total_event_count": len(log),
        "pattern":           pattern,
        "pattern_color":     pattern_color,
        "inbound_signals":   inbound_signals or [],  # from RSS pipeline, pending analyst review
    }

def score_event(raw_text, base, is_matched):
    s, bd = base + (10 if is_matched else 0), []
    if is_matched: bd.append({"id":"co_match","delta":10,"reason":"Event matched to tracked company","group":"boost"})
    for rule in SCORE_RULES:
        if rule["id"]=="co_match" or not rule["pattern"]: continue
        if re.search(rule["pattern"], raw_text, re.I):
            s += rule["delta"]
            bd.append({"id":rule["id"],"delta":rule["delta"],"reason":rule["reason"],"group":rule["group"]})
    final = max(0, min(100, round(s)))
    tier = "high" if final>=SCORE_THRESHOLD_HIGH else "medium" if final>=SCORE_THRESHOLD_MEDIUM else "low" if final>=SCORE_THRESHOLD_KEEP else "noise"
    penalties = sorted([b for b in bd if b["delta"]<0], key=lambda x:x["delta"])
    return {"signal_strength":final,"signal_tier":tier,"score_breakdown":bd,
            "is_noise":tier=="noise","drop_reason":penalties[0]["reason"] if penalties and tier=="noise" else None}

def compute_confidence(tier, strength, is_matched, is_neg):
    if is_neg:             return "Low","Negative — primary source verification required."
    if tier==1 and strength>=75 and is_matched: return "Medium-High","Tier-1 event with company match and high score."
    if tier==1 and strength>=60: return "Medium","Tier-1 event type; company unmatched or mixed modifiers."
    if tier==2 and strength>=65 and is_matched: return "Medium","Tier-2 event with company match."
    if tier==2 and strength>=50: return "Medium-Low","Tier-2 directional — not confirmatory."
    if tier<=3 and strength>=40: return "Low","Tier-3 or borderline. Context only."
    return "Low","Score below threshold. Context only."

def make_id(sid, title, date):
    return hashlib.sha256(f"{sid}:{title}:{date}".encode()).hexdigest()[:12]

def fetch_sources():
    raw, source_log = [], []
    if not HAS_FEEDPARSER:
        return raw, [{"id":s["id"],"name":s["name"],"url":s["url"],"status":"failed",
                       "error":"feedparser not installed","items":0,"fetched_at":datetime.now(timezone.utc).isoformat()} for s in RSS_SOURCES]
    for s in RSS_SOURCES:
        ts = datetime.now(timezone.utc).isoformat()
        try:
            socket.setdefaulttimeout(15)
            feed = feedparser.parse(s["url"])
            if getattr(feed,"status",None) and feed.status>=400: raise Exception(f"HTTP {feed.status}")
            count, errors = 0, []
            for entry in feed.entries[:20]:
                title   = getattr(entry,"title",""); summary = getattr(entry,"summary","")[:500]
                link    = getattr(entry,"link","")
                if not title or title=="[Removed]": continue
                t = entry.get("published_parsed") or entry.get("updated_parsed")
                date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}" if t else TODAY
                raw.append({"source_id":s["id"],"source_name":s["name"],"source_url":link,
                             "source_segments":s["segments"],"title":title,"summary":summary,
                             "published_date":date,"raw_text":(title+" "+summary).lower()})
                count += 1
            if count==0: errors.append("Feed returned 0 usable items")
            source_log.append({
                                "id":s["id"],"name":s["name"],"url":s["url"],
                                "status":"success" if count>0 else "partial",
                                "error":errors[0] if errors else None,
                                "items":count,"fetched_at":ts,
                                # registry metadata — passed through for UI
                                "source_type":  s.get("source_type","industry"),
                                "reliability":  s.get("reliability",3),
                                "topics":       s.get("topics",[]),
                                "geography":    s.get("geography","GLOBAL"),
                                "approved_by":  s.get("approved_by","unknown"),
                                "approved_date":s.get("approved_date","unknown"),
                            })
            print(f"  ✓ {s['name']}: {count}")
        except Exception as ex:
            source_log.append({
                                "id":s["id"],"name":s["name"],"url":s["url"],
                                "status":"failed","error":str(ex),"items":0,"fetched_at":ts,
                                "source_type":  s.get("source_type","industry"),
                                "reliability":  s.get("reliability",3),
                                "topics":       s.get("topics",[]),
                                "geography":    s.get("geography","GLOBAL"),
                                "approved_by":  s.get("approved_by","unknown"),
                                "approved_date":s.get("approved_date","unknown"),
                            })
            print(f"  ✗ {s['name']}: {ex}")
    return raw, source_log

def normalize(raw_items):
    kept, filtered = [], []
    for item in raw_items:
        clf       = classify(item["raw_text"])
        segment   = infer_segment(item["raw_text"], item["source_segments"])
        co_id, co_nm = match_company(item["raw_text"])
        buyers    = match_buyers(item["raw_text"])
        project_matches = match_project(item["raw_text"])
        strength  = score_event(item["raw_text"], clf["base_score"], co_id is not None)
        is_neg    = clf["type"]=="Negative"
        why_key   = (clf["type"],segment) if (clf["type"],segment) in WHY_IT_MATTERS else (clf["type"],"default")
        why_text  = WHY_IT_MATTERS.get(why_key, WHY_IT_MATTERS.get((clf["type"],"default"),"No rationale available."))
        miss_key  = (clf["type"],segment) if (clf["type"],segment) in MISSING_BY_TYPE else (clf["type"],"default")
        missing   = MISSING_BY_TYPE.get(miss_key, ["No gap analysis available."])
        conf_l, conf_r = compute_confidence(clf["tier"],strength["signal_strength"],co_id is not None,is_neg)
        obs    = item["title"].strip()
        fs     = item["summary"].strip().split(".")[0].strip() if item["summary"] else ""
        detail = (fs+".") if fs and fs.lower()!=obs.lower() and len(fs)>20 else None
        event = {
            "id":make_id(item["source_id"],item["title"],item["published_date"]),
            "title":item["title"],"summary":item["summary"],"event_date":item["published_date"],
            "source_name":item["source_name"],"source_url":item["source_url"],
            "event_type":clf["type"],"impact_type":clf["impact"],"matched_rule":clf["matched"],"tier":clf["tier"],
            "signal_stage":"commercial" if clf["type"] in ("Contract","Certification","Deployment") else "early" if clf["type"] in ("Pilot","Milestone") else "strategic",
            "signal_strength":strength["signal_strength"],"signal_tier":strength["signal_tier"],"score_breakdown":strength["score_breakdown"],
            "segment":segment,"company_id":co_id,"company_name":co_nm or "Unassigned",
            "buyer_matches":buyers,"project_matches":project_matches,"is_negative":is_neg,"neg_subtype":clf["neg_subtype"],"is_noise":strength["is_noise"] and not is_neg,
            "evidence":{"observed_fact":obs,"observed_fact_detail":detail,
                        "source_label":f"{item['source_name']} · {item['published_date']}",
                        "matched_rule_name":clf["matched"] or "no rule matched",
                        "matched_rule_tier":f"Tier {clf['tier']} — {clf['type']}",
                        "why_it_matters":why_text,"missing_evidence":missing,"confidence":conf_l,"confidence_rationale":conf_r},
        }
        if not strength["is_noise"] or is_neg: kept.append(event)
        else: filtered.append({**event,"drop_reason":strength["drop_reason"] or "score below threshold"})
    kept.sort(key=lambda e:(-(e["signal_strength"]),e["event_date"]))
    return kept, filtered


# ══════════════════════════════════════════════════════════════════════════
# SECTION 7  COMPANY ENRICHMENT
# ══════════════════════════════════════════════════════════════════════════

STAGE_LADDER = [
    ("PF-Ready",        "#0F4C75",{"Contract","Deployment"},
     "Multiple commercial deployments or project-financed asset. Infrastructure/PF framework applicable."),
    ("Scaling",         "#0A6640",{"Contract","Deployment"},
     "Commercial contracts in place. Revenue visible. Expanding geographically or into second buyer."),
    ("First Commercial","#1A56DB",{"Contract","Deployment"},
     "First binding commercial agreement or live deployment confirmed. Revenue visibility emerging."),
    ("Demo",            "#5B21B6",{"Certification"},
     "Technical gate cleared (certification or strategic pilot). Commercial conversion not yet confirmed."),
    ("Pilot",           "#7D4E00",{"Pilot","Partnership"},
     "Third-party validation in progress. No commercial gate cleared."),
    ("Lab",             "#6E6E6E",set(),
     "Limited public signal. Company at lab/early stage or undisclosed."),
]

PATTERN_RULES = [
    {"id":"series_c_prep","label":"Pre-Series C Cluster","color":"#1A56DB",
     "req":lambda t,h,n:"Certification" in t and ("Contract" in t or "Pilot" in t) and "Hiring" in t and h>=2 and n==0,
     "memo":"Three reinforcing signals: regulatory gate, commercial engagement, finance hire. Comparable cases preceded Series C within 6–12 months."},
    {"id":"commercial_breakout","label":"Commercial Breakout","color":"#0A6640",
     "req":lambda t,h,n:("Contract" in t or "Deployment" in t) and h>=2 and n==0,
     "memo":"Commercial-stage signal with multiple high-quality events. Revenue visibility beginning to emerge."},
    {"id":"cert_gate","label":"Certification Gate Cleared","color":"#0050B3",
     "req":lambda t,h,n:"Certification" in t and "Contract" not in t and "Deployment" not in t and n==0,
     "memo":"Certification obtained but no commercial contract yet. Hardest technical gate cleared; commercial conversion is next."},
    {"id":"strategic_momentum","label":"Strategic Momentum","color":"#5B21B6",
     "req":lambda t,h,n:"Partnership" in t and ("Pilot" in t or "Financing" in t) and n==0,
     "memo":"Strategic partnership combined with pilot or financing. Watch for partnership-to-contract conversion."},
    {"id":"fundraise_signal","label":"Fundraising Signal","color":"#7D4E00",
     "req":lambda t,h,n:"Hiring" in t and "Financing" not in t and n==0,
     "memo":"Finance/BD hire without confirmed round. CFO hire historically correlates with raise within 3–6 months."},
    {"id":"grant_dependent","label":"Grant-Dependent","color":"#D97706",
     "req":lambda t,h,n:"Grant" in t and "Contract" not in t and "Pilot" not in t and "Certification" not in t,
     "memo":"Grant-only signal. Non-dilutive capital without commercial anchor is insufficient for commercial-stage thesis."},
    {"id":"negative_flags","label":"Negative Signals — Reassess","color":"#C0392B",
     "req":lambda t,h,n:n>=1,
     "memo":"Negative signals detected. Positive signals must be reassessed in context of identified headwinds."},
    {"id":"low_density","label":"Insufficient Signal","color":"#A8A8A8",
     "req":lambda t,h,n:True,
     "memo":"Signal density insufficient for pattern recognition. Primary research required."},
]

TTR_RULES = [
    ("Near-term","#C0392B",lambda sl,pid,h:sl in ("PF-Ready","Scaling") or (sl=="First Commercial" and pid in ("series_c_prep","commercial_breakout") and h>=2)),
    ("Mid-term", "#7D4E00",lambda sl,pid,h:sl in ("First Commercial","Demo","Pilot") and pid not in ("grant_dependent","low_density","negative_flags")),
    ("Long-term","#6E6E6E",lambda sl,pid,h:True),
]

def infer_stage(co, evs):
    types = {e["event_type"] for e in evs}
    for label, color, req_types, desc in STAGE_LADDER:
        if req_types and not (req_types & types): continue
        return label, color, desc
    return "Lab","#6E6E6E","Limited public signal. Primary research required."

def detect_pattern(types, high_ct, neg_ct):
    for r in PATTERN_RULES:
        if r["req"](types,high_ct,neg_ct):
            return {"id":r["id"],"label":r["label"],"color":r["color"],"memo":r["memo"]}
    return {"id":"low_density","label":"Insufficient Signal","color":"#A8A8A8","memo":"Primary research required."}

def build_insight(co, evs):
    if not evs:
        return {"observed_facts":[],"matched_pattern":"Insufficient signal. Primary research required.",
                "may_indicate":["No pattern without events"],"missing":["No public events ingested"],
                "confidence":"Low","next_check":"Direct outreach recommended.","event_count":0,"high_signal":0}
    types = [e["event_type"] for e in evs]
    has_cert = "Certification" in types; has_ctr = "Contract" in types or "Deployment" in types
    has_hire = "Hiring" in types; has_plt = "Pilot" in types; has_fin = "Financing" in types
    has_neg  = any(e["is_negative"] for e in evs); has_grnt = "Grant" in types
    high_ct  = sum(1 for e in evs if e["signal_tier"]=="high")
    facts = [f"[{e['event_type']}] {e['title']} — {e['source_name']} ({e['event_date']})" for e in evs if e["signal_strength"]>=40][:5]
    if has_cert and has_ctr and has_hire:
        pat="Pre-Series C signal cluster: regulatory certification, named commercial contract, and finance-function hire in the same window. Comparable domestic cases preceded formal raise processes within 6–12 months."; ind=["Series C within 6–12 months based on cluster","Strategic investor seeking anchor position","Watch for international BD hire"]; pid,conf="series_c_prep","Medium-High"
    elif has_cert and has_ctr:
        pat="Third-party certification and first commercial contract secured. Supply chain entry demonstrated. Revenue visibility emerging; scale and exclusivity unconfirmed."; ind=["Second OEM customer in parallel pursuit","M&A interest from EPC or OEM","Bridge financing if ramp slower than projected"]; pid,conf="supply_entry","Medium"
    elif has_plt and (has_fin or has_ctr):
        pat="Field-level technical progress alongside financing or commercial engagement. Certification gate not yet cleared — commercial signals remain conditional."; ind=["Certification application likely in progress","Partnership may convert to LOI upon certification"]; pid,conf="cert_gate","Medium-Low"
    elif has_grnt and not has_ctr:
        pat="Primary visible signal is government grant funding. Grants validate technology direction but not market demand. Without a named offtaker, the investment thesis cannot advance."; ind=["Technology at TRL 4–6: government-funded validation","Commercial pipeline may be early or undisclosed"]; pid,conf="grant_only","Low"
    elif has_fin and has_ctr:
        pat="Financing round alongside a commercial contract — strongest single-window signal combination. External capital validation and initial revenue visibility together."; ind=["Revenue ramp expected 12–18 months","Strategic investor may hold first-refusal","Follow-on at higher valuation once KPIs are met"]; pid,conf="strategic_capital","High"
    elif has_neg:
        pat="One or more negative signals detected. Positive signals must be reassessed in context of identified headwinds."; ind=["Timeline extension likely","Bridge or down-round possible"]; pid,conf="negative","Low"
    else:
        pat=f"{len(evs)} event(s) from {len(set(e['source_name'] for e in evs))} source(s). Signal density insufficient to confirm a pattern. Primary research recommended."; ind=["Early stage or limited public disclosure"]; pid,conf="low_density","Low"
    missing = []
    if not has_ctr: missing.append("No commercial contract — all revenue hypothetical until confirmed")
    if not has_cert and co.get("sector") in ("marine_fc","ess","hvdc"): missing.append("No third-party certification — procurement prerequisite in this sector")
    if high_ct==0: missing.append("No high-confidence signals — current events are directional only")
    if has_grnt and not has_ctr: missing.append("Grant present but no commercial anchor — insufficient alone")
    next_map={"series_c_prep":"Monitor overseas VP Sales posting or second KEPCO-scale contract ACV.","supply_entry":"Verify contract scope (project vs. framework).","cert_gate":"Confirm certification application formally submitted.","grant_only":"Determine if grant requires commercial co-funding partner.","strategic_capital":"Identify strategic investor sector position. Check M&A history.","negative":"Determine if negative is project-level or structural.","low_density":"Direct outreach recommended."}
    return {"observed_facts":facts,"matched_pattern":pat,"pattern_id":pid,"may_indicate":ind,"missing":missing,"confidence":conf,"next_check":next_map.get(pid,"Review events and cross-check primary sources."),"event_count":len(evs),"high_signal":high_ct,"note":"Generated from existing events only. No data invented."}

def enrich_company(co, evs):
    types   = {e["event_type"] for e in evs}
    high_ct = sum(1 for e in evs if e["signal_tier"]=="high")
    neg_ct  = sum(1 for e in evs if e["is_negative"])
    reinf   = len({e["event_type"] for e in evs if e["signal_tier"]=="high"})
    type_counts = {}
    for e in evs: type_counts[e["event_type"]] = type_counts.get(e["event_type"],0)+1
    stage_label, stage_color, stage_desc = infer_stage(co, evs)
    pattern  = detect_pattern(types,high_ct,neg_ct)
    ttr_l,ttr_c = next(((l,c) for l,c,f in TTR_RULES if f(stage_label,pattern["id"],high_ct)), ("Long-term","#6E6E6E"))
    sev_ord = {"critical":0,"high":1,"medium":2}
    gaps = []
    for rule in MISSING_RULES:
        secs = rule["sectors"]
        if secs!="all" and co.get("sector") not in secs: continue
        try:
            if rule["check"](evs): gaps.append({"rule_id":rule["id"],"label":rule["label"],"severity":rule["severity"],"memo":rule["memo"]})
        except: pass
    gaps.sort(key=lambda x:sev_ord.get(x["severity"],9))
    buyer_act = {}
    for e in evs:
        for b in e.get("buyer_matches",[]):
            buyer_act.setdefault(b["id"],{"name":b["name"],"type":b["type"],"count":0,"events":[]})
            buyer_act[b["id"]]["count"] += 1
            buyer_act[b["id"]]["events"].append({"date":e["event_date"],"title":e["title"],"event_type":e["event_type"],"score":e["signal_strength"]})
    linked_proj = [{"id":p["id"],"name":p["name"],"status":p["status"],"location":p["location"],
                    "offtaker":p.get("offtaker","TBD"),"capex":p.get("capex","—"),
                    "milestone_next":p.get("milestone_next","—")} for p in PROJECTS if co["id"] in p["linked_companies"]]
    sector_rb = SECTOR_RULEBOOKS.get(co.get("sector",""),{})
    return {**co,
            "events":sorted(evs,key=lambda e:e["event_date"],reverse=True)[:10],
            "insight":build_insight(co,evs),
            "signal_count":len(evs),"high_count":high_ct,"neg_count":neg_ct,"reinforcing":reinf,"type_counts":type_counts,
            "stage_label":stage_label,"stage_color":stage_color,"stage_desc":stage_desc,"pattern":pattern,
            "ttr":ttr_l,"ttr_color":ttr_c,"gaps":gaps,
            "critical_gaps":sum(1 for g in gaps if g["severity"]=="critical"),"high_gaps":sum(1 for g in gaps if g["severity"]=="high"),
            "buyer_activity":buyer_act,"linked_projects":linked_proj,
            "sector_rulebook":{"key_gate":sector_rb.get("key_gate","—"),"commercial_threshold":sector_rb.get("commercial_threshold","—"),
                               "policy_driver":sector_rb.get("policy_driver","—"),"red_flags":sector_rb.get("red_flags",[]),
                               "positive_signals":sector_rb.get("positive_signals",[])}}


# ══════════════════════════════════════════════════════════════════════════
# SECTION 8  PANEL BUILDERS + ALERT ENGINE
# ══════════════════════════════════════════════════════════════════════════
#
# ALERT SYSTEM DESIGN
# ────────────────────
# The pipeline emits alert_candidates[] in the JSON — one per HIGH/NEG signal
# that occurred today. The UI checks alert_candidates against the user's
# localStorage watchlist and surfaces matches as alerts.
#
# Alert candidate schema:
#   signal_id      the event id
#   entity_type    "company" | "project" | "segment" | "buyer"
#   entity_id      the matched entity id
#   entity_name    display name
#   alert_type     "high_signal" | "negative" | "pattern_change" | "new_inbound"
#   event_type     Certification / Contract / Pilot / Negative / etc.
#   headline       event title
#   why_it_matters sector-specific explanation from evidence card
#   confidence     Low / Medium / Medium-High / High
#   score          signal_strength 0-100
#   date           event_date
#   source         source_name
#   source_url     link to original article
#
# In Paid Pilot tier, alert_candidates are additionally sent via:
#   - Email digest (daily batch, per-user watchlist filter)
#   - Slack webhook (immediate, per-team channel)
#   Both channels are NOT wired in this MVP build — stubs documented below.
#
# EMAIL DIGEST STUB (Paid Pilot):
#   POST https://alerts.yourdomain.com/digest
#   Body: { user_id, watchlist_ids, alert_candidates, date }
#   → Service filters by watchlist, formats HTML email, sends via SES/Postmark
#
# SLACK WEBHOOK STUB (Paid Pilot):
#   POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL
#   Body: { text: alert_summary, blocks: [...] }
#   → SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
# ══════════════════════════════════════════════════════════════════════════

def build_alert_candidates(signals, company_insights, enriched_projects, buyer_activity):
    """
    Produce alert candidates from today's signals.
    One candidate per HIGH or NEGATIVE signal, enriched with:
      - entity match (company / project / segment / buyer)
      - why_it_matters from evidence card
      - confidence + score
    These are checked against the user's watchlist in the UI.
    """
    candidates = []
    seen_ids = set()

    for ev in signals:
        # Only surface HIGH signals and all NEGATIVE signals
        if ev["signal_tier"] not in ("high","medium") and not ev["is_negative"]:
            continue
        if ev["id"] in seen_ids:
            continue
        seen_ids.add(ev["id"])

        ev2 = ev.get("evidence", {})
        base = {
            "signal_id":    ev["id"],
            "alert_type":   "negative" if ev["is_negative"] else "high_signal",
            "event_type":   ev["event_type"],
            "headline":     ev["title"],
            "why_it_matters": ev2.get("why_it_matters",""),
            "confidence":   ev2.get("confidence","Low"),
            "score":        ev["signal_strength"],
            "date":         ev["event_date"],
            "source":       ev["source_name"],
            "source_url":   ev.get("source_url",""),
            "segment":      ev.get("segment",""),
        }

        # Match to company
        if ev.get("company_id"):
            co = company_insights.get(ev["company_id"], {})
            candidates.append({
                **base,
                "entity_type": "company",
                "entity_id":   ev["company_id"],
                "entity_name": ev.get("company_name",""),
                "stage":       co.get("stage_label",""),
                "pattern":     co.get("pattern",{}).get("label",""),
            })

        # Match to project via project_matches
        for pid in ev.get("project_matches", []):
            proj = next((p for p in enriched_projects if p["id"] == pid), None)
            if proj:
                candidates.append({
                    **base,
                    "entity_type": "project",
                    "entity_id":   pid,
                    "entity_name": proj.get("name",""),
                    "stage":       proj.get("current_stage",""),
                    "pattern":     "",
                })

        # Match to buyer
        for bm in ev.get("buyer_matches", []):
            candidates.append({
                **base,
                "entity_type": "buyer",
                "entity_id":   bm["id"],
                "entity_name": bm["name"],
                "stage":       "",
                "pattern":     "",
            })

        # Segment-level (always add)
        if ev.get("segment"):
            candidates.append({
                **base,
                "entity_type": "segment",
                "entity_id":   ev["segment"],
                "entity_name": ev["segment"],
                "stage":       "",
                "pattern":     "",
            })

    # Deduplicate: one alert per (entity_id, signal_id)
    seen_pairs = set()
    deduped = []
    for c in candidates:
        key = (c["entity_id"], c["signal_id"])
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped.append(c)

    # Sort: negative first, then by score desc
    deduped.sort(key=lambda x: (0 if x["alert_type"]=="negative" else 1, -(x["score"])))
    return deduped


def build_panels(signals, cos):
    sev = {"critical":0,"high":1,"medium":2,"low":3}
    negs = []
    for ev in signals:
        if not ev["is_negative"]: continue
        sub  = ev.get("neg_subtype") or "delay"
        meta = NEG_SUBTYPE_META.get(sub,{"label":"Negative","icon":"⚠","severity":"high","memo":"Verify primary source."})
        negs.append({"event_id":ev["id"],"title":ev["title"],"source_name":ev["source_name"],"source_url":ev["source_url"],
                     "event_date":ev["event_date"],"company_id":ev.get("company_id"),"company_name":ev.get("company_name","Unassigned"),
                     "segment":ev.get("segment","unknown"),"neg_subtype":sub,
                     "label":meta["label"],"icon":meta["icon"],"severity":meta["severity"],"memo":meta["memo"]})
    negs.sort(key=lambda x:sev.get(x["severity"],9))
    miss = []
    for co_id, co in cos.items():
        co_gaps = co.get("gaps",[])
        if co_gaps:
            miss.append({"company_id":co_id,"company_name":co.get("name",""),"sector":co.get("sector",""),
                         "stage":co.get("stage_label",""),"gaps":co_gaps,"gap_count":len(co_gaps),
                         "critical_gaps":co.get("critical_gaps",0),"high_gaps":co.get("high_gaps",0)})
    miss.sort(key=lambda x:(-(x["critical_gaps"]*10+x["high_gaps"]),x["company_name"]))
    # Default watchlist from curated flag
    watchlist = [{"company_id":co["id"],"company_name":co["name"],"ttr":cos[co["id"]].get("ttr","Long-term"),"stage":cos[co["id"]].get("stage_label","Lab"),"high_count":cos[co["id"]].get("high_count",0),"pattern_id":cos[co["id"]].get("pattern",{}).get("id","low_density")} for co in COMPANIES if co.get("watchlist_default") and co["id"] in cos]
    return {"negative_signals":negs,"missing_evidence":miss,"watchlist":watchlist,
            "panel_stats":{"negative_count":len(negs),"critical_neg":sum(1 for n in negs if n["severity"]=="critical"),
                           "companies_with_gaps":len(miss),"total_critical_gaps":sum(c["critical_gaps"] for c in miss),
                           "watchlist_count":len(watchlist)}}


# ══════════════════════════════════════════════════════════════════════════
# SECTION 9  BRIEF GENERATION
# ══════════════════════════════════════════════════════════════════════════

def call_claude(prompt):
    if not ANTHROPIC_KEY: return None
    import urllib.request as ur
    body = json.dumps({"model":"claude-sonnet-4-20250514","max_tokens":800,"messages":[{"role":"user","content":prompt}]}).encode()
    req  = ur.Request("https://api.anthropic.com/v1/messages",data=body,
           headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01"})
    try:
        with ur.urlopen(req,timeout=30) as r: return json.loads(r.read())["content"][0]["text"]
    except Exception as ex: print(f"  Claude API: {ex}"); return None

def generate_brief(events):
    high = [e for e in events if e["signal_tier"]=="high"][:8]
    if ANTHROPIC_KEY and high:
        lines = "\n".join(f"- [{e['event_type']}] {e['company_name']} ({e['source_name']}): {e['title']}" for e in high)
        result = call_claude(f"You are a senior analyst at an energy-focused VC/CVC fund writing an internal deal flow memo.\nDate: {TODAY_KR}\n\nHigh-signal events today:\n{lines}\n\nWrite 4–5 sentences. Internal memo tone. No invented numbers. Cite company names and sources. Focus on pattern, timing, and what to watch next.")
        if result: return result.strip()
    if not high: return f"{TODAY_KR}: No high-signal events collected. Check source status."
    return f"{TODAY_KR}. {len(high)} high-signal events. Top signals: {'; '.join(e['title'] for e in high[:2])}. High-signal companies: {', '.join(set(e['company_name'] for e in high if e['company_id']))}."


# ══════════════════════════════════════════════════════════════════════════
# SECTION 10  MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'═'*60}\nEnergy Capital Intelligence  v3.0\n{TODAY_KR}\n{'═'*60}\n")
    Path("data").mkdir(exist_ok=True)

    print("① Fetch..."); raw, source_log = fetch_sources(); print(f"  {len(raw)} raw\n")
    print("② Classify + score + filter..."); kept, filtered = normalize(raw); print(f"  Kept: {len(kept)} | Filtered: {len(filtered)}\n")
    print("③ Company enrichment...")
    co_evs = {}
    for e in kept:
        if e["company_id"]: co_evs.setdefault(e["company_id"],[]).append(e)
    co_intel = {co["id"]:enrich_company(co,co_evs.get(co["id"],[])) for co in COMPANIES if co_evs.get(co["id"])}
    print(f"  {len(co_intel)} companies\n")
    print("④ Project intelligence...")
    project_inbound = {}  # { project_id: [signal_event, ...] }
    for ev in kept:
        for pid in ev.get("project_matches",[]):
            project_inbound.setdefault(pid,[]).append({
                "event_id":    ev["id"],
                "date":        ev["event_date"],
                "title":       ev["title"],
                "event_type":  ev["event_type"],
                "source_name": ev["source_name"],
                "source_url":  ev["source_url"],
                "score":       ev["signal_strength"],
                "note":        "Auto-matched from RSS — analyst review required before adding to signal_log",
            })
    enriched_projects = [
        build_project_intel(p, project_inbound.get(p["id"],[]))
        for p in PROJECTS
    ]
    n_inbound = sum(len(v) for v in project_inbound.values())
    print(f"  {len(enriched_projects)} projects enriched, {n_inbound} inbound signals")
    print()

    print("⑤ Buyer activity...")
    buyer_global = {}
    for ev in kept:
        for b in ev.get("buyer_matches",[]):
            buyer_global.setdefault(b["id"],{"id":b["id"],"name":b["name"],"type":b["type"],"events":[]})
            buyer_global[b["id"]]["events"].append({"date":ev["event_date"],"title":ev["title"],"event_type":ev["event_type"],"source":ev["source_name"],"score":ev["signal_strength"]})
    print(f"  {len(buyer_global)} buyers active\n")
    print("⑥ Panels...")
    panels = build_panels(kept, co_intel)
    alert_candidates = build_alert_candidates(kept, co_intel, enriched_projects, buyer_global)
    print(f"  Neg: {panels['panel_stats']['negative_count']} | Gaps: {panels['panel_stats']['companies_with_gaps']} companies | Alerts: {len(alert_candidates)}")
    print()
    print("⑦ Brief..."); brief = generate_brief(kept)
    stats = {"total":len(kept),"high":sum(1 for e in kept if e["signal_tier"]=="high"),"medium":sum(1 for e in kept if e["signal_tier"]=="medium"),
             "negative":sum(1 for e in kept if e["is_negative"]),"matched":sum(1 for e in kept if e["company_id"]),"filtered_out":len(filtered),
             "companies_with_signals":len(co_intel),"by_segment":{},"by_type":{}}
    for e in kept:
        stats["by_segment"][e["segment"]] = stats["by_segment"].get(e["segment"],0)+1
        stats["by_type"][e["event_type"]]  = stats["by_type"].get(e["event_type"],0)+1
    output = {"date":TODAY,"dateKr":TODAY_KR,"generatedAt":datetime.now(timezone.utc).isoformat(),
              "brief":brief,"stats":stats,"signals":kept,"filteredOut":filtered[:20],
              "companies":co_intel,"projects":enriched_projects,"strategic_buyers":STRATEGIC_BUYERS,
              "buyer_activity":buyer_global,"panels":panels,"alert_candidates":alert_candidates,"source_log":source_log,
              "source_registry":SOURCE_REGISTRY,"score_rulebook":SCORE_RULEBOOK_DISPLAY,"sector_rulebooks":SECTOR_RULEBOOKS,
              "reliability":{"sources_total":len(source_log),"sources_ok":sum(1 for s in source_log if s["status"]=="success"),
                             "sources_partial":sum(1 for s in source_log if s["status"]=="partial"),"sources_failed":sum(1 for s in source_log if s["status"]=="failed"),
                             "new_events":len(kept),"filtered_out":len(filtered)},
              # Feature stubs — these fields will be populated by private DB in paid tier
              "_feature_stubs": {
                  "analyst_notes":     "⚠ PAID PILOT — stored in private DB, not in public JSON",
                  "watchlist_custom":  "✓ MVP — client-side localStorage watchlist (companies/projects/segments/buyers). Upgrade to DB in Paid Pilot.",
                  "alerts":            "✓ MVP — in-app alerts from alert_candidates[] checked against localStorage watchlist. Email/Slack delivery in Paid Pilot.",
                  "triage_status":     "⚠ PAID PILOT — Pass / Watch / Investigate per company",
                  "evidence_history":  "⚠ PAID PILOT — 90-day per-company signal timeline",
                  "outcome_tracking":  "⚠ SCALE — analyst logs what happened after each signal",
                  "comparables_db":    "⚠ SCALE — proprietary deal terms and round history",
                  "api_access":        "⚠ SCALE — GET /api/company/{id}/card + webhooks",
              }}
    with open("data/latest.json","w",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,indent=2)
    with open(f"data/{TODAY}.json","w",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,indent=2)
    idx_p = Path("data/index.json"); idx = []
    if idx_p.exists():
        try: idx=json.loads(idx_p.read_text())
        except: pass
    if not any(d["date"]==TODAY for d in idx):
        idx.insert(0,{"date":TODAY,"dateKr":TODAY_KR,"stats":stats})
        idx_p.write_text(json.dumps(idx[:90],ensure_ascii=False,indent=2))
    print(f"✅  Signals: {stats['total']} | High: {stats['high']} | Companies: {stats['companies_with_signals']}\n")

if __name__=="__main__": main()

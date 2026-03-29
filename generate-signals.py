"""
╔══════════════════════════════════════════════════════════════════╗
║  ENERGY CAPITAL INTELLIGENCE  —  Signal Pipeline v2.0           ║
║  For: Energy VC / CVC / Infrastructure Investment Teams         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  PRODUCT ARCHITECTURE                                            ║
║                                                                  ║
║  RULE-BASED (never AI, never changes without deliberate edit):  ║
║    • Event classification  (keyword tiers 1-4)                  ║
║    • Signal scoring        (additive deltas, fully auditable)   ║
║    • Noise filtering       (veto patterns, threshold gates)     ║
║    • Stage inference       (evidence-ladder, event-based)       ║
║    • Missing evidence      (structural gap rules per sector)    ║
║    • Buyer matching        (named entity keyword lists)         ║
║    • TTR classification    (Near / Mid / Long-term)             ║
║    • Pattern detection     (multi-signal cluster rules)         ║
║                                                                  ║
║  HUMAN REVIEW REQUIRED:                                          ║
║    • Analyst notes (free-text memo per company / project)       ║
║    • Watchlist add/remove decisions                             ║
║    • Alert threshold overrides per company                      ║
║    • Unassigned event confirmation                              ║
║    • Final triage status  (Pass / Watch / Investigate)          ║
║                                                                  ║
║  FUTURE PROPRIETARY DATA  (store in DB, never in public JSON):  ║
║    • Primary meeting notes, LP-level intelligence               ║
║    • NDA-covered term sheets and cap table snapshots            ║
║    • Proprietary comparables DB (deal terms, valuations)        ║
║    • DART API  — KR regulatory filings  (DART_API_KEY)         ║
║    • SEC EDGAR — US company filings                             ║
║    • LinkedIn hiring velocity  (requires scraping layer)        ║
║    • Patent filing velocity per company / segment              ║
║                                                                  ║
║  PREMIUM / API-ONLY  (future product tier):                     ║
║    • Evidence card API  GET /api/company/{id}/card              ║
║    • Segment heatmap feed  GET /api/segments/heatmap            ║
║    • Watchlist diff alerts  (webhook on new HIGH signal)        ║
║    • Buyer movement API  GET /api/buyers/{id}/activity          ║
║    • Pattern-match webhook  (fires when cluster condition met)  ║
║    • PDF deal memo export  POST /api/memo/{id}/export           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
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


# ──────────────────────────────────────────────────────────────────────────
# SECTION 1  DATA SOURCES
# ──────────────────────────────────────────────────────────────────────────

RSS_SOURCES = [
    {"id":"utilitydive",      "name":"Utility Dive",       "url":"https://www.utilitydive.com/feeds/news/",      "segments":["grid_sw","ess","dc_power"]},
    {"id":"pvmagazine",       "name":"PV Magazine",         "url":"https://www.pv-magazine.com/feed/",            "segments":["ess","hydrogen","forecasting"]},
    {"id":"energystoragenews","name":"Energy Storage News", "url":"https://www.energy-storage.news/feed/",        "segments":["ess"]},
    {"id":"offshorewind",     "name":"Offshore Wind Biz",   "url":"https://www.offshorewind.biz/feed/",           "segments":["hvdc","ess"]},
    {"id":"electrek",         "name":"Electrek",            "url":"https://electrek.co/feed/",                    "segments":["ess","dc_power","forecasting"]},
    {"id":"h2view",           "name":"H2 View",             "url":"https://www.h2-view.com/feed/",                "segments":["hydrogen","marine_fc"]},
]


# ──────────────────────────────────────────────────────────────────────────
# SECTION 2  ENTITY REGISTRY
# ──────────────────────────────────────────────────────────────────────────

COMPANIES = [
    {"id":"c_gridwiz",    "name":"그리드위즈",     "aliases":["gridwiz","grid wiz"],
     "sector":"grid_sw",  "country":"KR","stage":"First Commercial","investor_type":"Strategic/CVC",
     "description":"KPX-certified VPP/DR platform. First commercial contracts with KEPCO underway.",
     "tags":["비상장","VPP","KPX인증","Series-B"]},
    {"id":"c_sixtyhertz", "name":"식스티헤르츠",   "aliases":["sixty hertz","60hz","sixtyhertz"],
     "sector":"grid_sw",  "country":"KR","stage":"First Commercial","investor_type":"VC",
     "description":"AI-powered renewable energy forecasting. KEPCO 3-year contract. Kakao Ventures backed.",
     "tags":["비상장","AI예측","Series-A"]},
    {"id":"c_vincen",     "name":"빈센",           "aliases":["vincen","vinsen"],
     "sector":"marine_fc","country":"KR","stage":"Pilot",           "investor_type":"Strategic/CVC",
     "description":"Marine hydrogen PEM fuel cell. HD HHI MOU. 1MW pilot installed.",
     "tags":["비상장","IMO2030","PEM","Series-A"]},
    {"id":"c_standard_e", "name":"스탠다드에너지", "aliases":["standard energy"],
     "sector":"ess",      "country":"KR","stage":"Demo",            "investor_type":"Strategic/CVC",
     "description":"Vanadium redox flow battery. Hanwha Solutions Series B. DOE grant application.",
     "tags":["비상장","VRFB","Series-B"]},
    {"id":"c_hylium",     "name":"하이리움산업",   "aliases":["hylium","하이리움"],
     "sector":"hydrogen", "country":"KR","stage":"Demo",            "investor_type":"Strategic/CVC",
     "description":"First domestic liquid hydrogen plant operational. Hyundai Motor supply chain registered.",
     "tags":["비상장","LH2","Series-B"]},
    {"id":"c_cs_energy",  "name":"씨에스에너지",   "aliases":["cs energy","씨에스에너지"],
     "sector":"ess",      "country":"KR","stage":"First Commercial","investor_type":"Strategic/CVC",
     "description":"ESS system integrator. SK Innovation supply chain. Ulsan 100MWh reference.",
     "tags":["비상장","ESS-SI","Series-A"]},
    {"id":"c_form_energy","name":"Form Energy",    "aliases":["form energy","formenergy"],
     "sector":"ess",      "country":"US","stage":"Scaling",         "investor_type":"Infrastructure/PF",
     "description":"Iron-air 100h+ LDES. ArcelorMittal strategic. Georgia gigafactory under construction.",
     "tags":["비상장","Iron-Air","Series-E"]},
    {"id":"c_autogrid",   "name":"AutoGrid",       "aliases":["autogrid","auto grid"],
     "sector":"grid_sw",  "country":"US","stage":"Scaling",         "investor_type":"Growth",
     "description":"VPP/Energy Intelligence Platform. Engie/E.ON/Shell investors. Commercial in 20+ countries.",
     "tags":["비상장","VPP","Series-D"]},
    {"id":"c_sunfire",    "name":"Sunfire",         "aliases":["sunfire"],
     "sector":"hydrogen", "country":"DE","stage":"First Commercial","investor_type":"Infrastructure/PF",
     "description":"SOEC electrolyzer. €215M raised. Carbon Direct strategic investor.",
     "tags":["비상장","SOEC","Series-E"]},
    {"id":"c_amogy",      "name":"Amogy",           "aliases":["amogy"],
     "sector":"marine_fc","country":"US","stage":"Pilot",           "investor_type":"Strategic/CVC",
     "description":"Ammonia-to-power marine fuel cell. Tug boat demo completed.",
     "tags":["비상장","Ammonia-FC","Series-B"]},
    {"id":"c_hysata",     "name":"Hysata",          "aliases":["hysata"],
     "sector":"hydrogen", "country":"AU","stage":"Pilot",           "investor_type":"Strategic/CVC",
     "description":"Capillary-fed electrolyzer. Claims lowest LCOH path. Fortescue backed.",
     "tags":["비상장","Electrolyzer","Series-B"]},
    {"id":"c_ceres",      "name":"Ceres Power",     "aliases":["ceres power","ceres"],
     "sector":"marine_fc","country":"UK","stage":"First Commercial","investor_type":"Strategic/CVC",
     "description":"SOFC platform licensor. Bosch/Doosan/Delta strategic. LSE listed.",
     "tags":["상장","SOFC","Licensed"]},
    {"id":"c_invinity",   "name":"Invinity Energy", "aliases":["invinity"],
     "sector":"ess",      "country":"UK","stage":"First Commercial","investor_type":"Growth",
     "description":"Vanadium flow battery manufacturer. Listed. UK/US/Australia commercial.",
     "tags":["상장","VRFB","Commercial"]},
]

STRATEGIC_BUYERS = [
    {"id":"b_kepco",      "name":"KEPCO",          "type":"Utility",    "region":"KR",
     "aliases":["kepco","한국전력","kpx"],
     "active_segments":["grid_sw","ess","hydrogen"],
     "procurement_signal":"VPP 실증 RFP 발주. DR·보조서비스 참여기업 수요 확대."},
    {"id":"b_hd_hhi",     "name":"HD한국조선해양", "type":"Shipyard",   "region":"KR",
     "aliases":["hd hyundai","hd 현대","한국조선해양","hd hhi"],
     "active_segments":["marine_fc","hydrogen"],
     "procurement_signal":"암모니아 이중연료 선박 수주 확대. 연료전지 내재화 검토."},
    {"id":"b_microsoft",  "name":"Microsoft",      "type":"Hyperscaler","region":"US",
     "aliases":["microsoft","azure","msft"],
     "active_segments":["dc_power","ess","forecasting"],
     "procurement_signal":"Nuclear PPA. 24/7 CFE 목표. DC power 파일럿 확대."},
    {"id":"b_ls_elec",    "name":"LS일렉트릭",     "type":"EPC/OEM",   "region":"KR",
     "aliases":["ls electric","ls일렉트릭","ls elec"],
     "active_segments":["ess","grid_sw","hvdc"],
     "procurement_signal":"VPP 플랫폼 내재화 전략 추진. ESS 턴키 계약 확대."},
    {"id":"b_engie",      "name":"Engie",          "type":"Utility",    "region":"EU",
     "aliases":["engie"],
     "active_segments":["ess","grid_sw","hydrogen"],
     "procurement_signal":"유럽 ESS 입찰 활성화. VPP 플랫폼 투자자이자 고객."},
    {"id":"b_samsung_hvy","name":"삼성중공업",     "type":"Shipyard",   "region":"KR",
     "aliases":["samsung heavy","삼성중공업","samsung hvy"],
     "active_segments":["marine_fc","hvdc"],
     "procurement_signal":"선박 연료전지 파일럿 프로그램. HVDC 해상풍력 연계."},
    {"id":"b_google",     "name":"Google",         "type":"Hyperscaler","region":"US",
     "aliases":["google","alphabet","gcp"],
     "active_segments":["dc_power","ess","wte"],
     "procurement_signal":"CFE 100% 목표. 새로운 ESS 기술 파일럿 적극적."},
    {"id":"b_sk_eco",     "name":"SK에코플랜트",   "type":"EPC",        "region":"KR",
     "aliases":["sk eco","sk에코","sk ecoplant"],
     "active_segments":["hydrogen","wte","ess"],
     "procurement_signal":"바이오가스→수소 전환. EPC로서 에너지 신기술 도입."},
]

PROJECTS = [
    {"id":"p_busan_h2",   "name":"부산항 수소 벙커링 인프라",
     "location":"부산, KR","type":"port","status":"Pilot",
     "developer":"한국가스공사","offtaker":"HD한국조선해양","epc":"SK에코플랜트",
     "capacity":"5,000톤/년","capex":"₩2,300억","segments":["hydrogen","marine_fc"],
     "linked_companies":["c_vincen","c_hylium"],"linked_buyers":["b_hd_hhi","b_sk_eco"],
     "description":"Korea's first hydrogen bunkering pilot. Critical enabler for IMO 2030 fleet compliance."},
    {"id":"p_jeju_hvdc",  "name":"제주 해상풍력 HVDC 연계",
     "location":"제주, KR","type":"grid","status":"Planned",
     "developer":"한국해상풍력","offtaker":"KEPCO","epc":"LS일렉트릭",
     "capacity":"500MW","capex":"₩8,700억","segments":["hvdc","ess"],
     "linked_companies":["c_standard_e"],"linked_buyers":["b_kepco","b_ls_elec"],
     "description":"Offshore wind HVDC backbone. Long-duration ESS co-located opportunity."},
    {"id":"p_incheon_vpp","name":"인천 LNG 터미널 VPP 실증",
     "location":"인천, KR","type":"grid","status":"Pilot",
     "developer":"SK E&S","offtaker":"KEPCO","epc":"그리드위즈",
     "capacity":"200MW DR","capex":"₩340억","segments":["grid_sw","ess"],
     "linked_companies":["c_gridwiz"],"linked_buyers":["b_kepco","b_ls_elec"],
     "description":"VPP/DR pilot linked directly to KPX ancillary services market entry."},
    {"id":"p_sg_dc",      "name":"Singapore DC Power Optimisation",
     "location":"Singapore","type":"data_center","status":"Planned",
     "developer":"GIC","offtaker":"Microsoft","epc":"TBD",
     "capacity":"50MW","capex":"$120M","segments":["dc_power","forecasting"],
     "linked_companies":["c_autogrid"],"linked_buyers":["b_microsoft"],
     "description":"Hyperscaler-backed DC power optimisation. AutoGrid VPP platform pilot."},
    {"id":"p_ulsan_ess",  "name":"울산 산업단지 ESS 실증",
     "location":"울산, KR","type":"industrial","status":"Construction",
     "developer":"울산시","offtaker":"SK이노베이션","epc":"씨에스에너지",
     "capacity":"100MWh","capex":"₩760억","segments":["ess"],
     "linked_companies":["c_cs_energy"],"linked_buyers":["b_sk_eco"],
     "description":"Industrial ESS reference. SK Innovation supply chain qualification in progress."},
    {"id":"p_rotterdam",  "name":"Rotterdam Green Hydrogen Terminal",
     "location":"Rotterdam, NL","type":"port","status":"Planned",
     "developer":"Port of Rotterdam","offtaker":"TBD","epc":"TBD",
     "capacity":"1GW electrolyzer","capex":"€4.2B","segments":["hydrogen"],
     "linked_companies":["c_hylium"],"linked_buyers":["b_engie"],
     "description":"European hydrogen import terminal. Structural demand anchor for liquid H2 logistics chain."},
]


# ──────────────────────────────────────────────────────────────────────────
# SECTION 3  CLASSIFICATION RULEBOOK  (transparent, no black-box)
# ──────────────────────────────────────────────────────────────────────────

EVENT_RULES = [
    # Tier 1: Concrete commercial/technical action  base 85-92
    {"kws":["class approval","dnv gl","dnv certified","kpx certified","atex certified","tuv certified","ul listed","iec certified","type approved"],
     "type":"Certification","impact":"Commercial","score":88,"tier":1,"neg_subtype":None},
    {"kws":["commercial contract","offtake agreement","supply agreement","signed contract","power purchase agreement","ppa signed","framework contract","master supply","long-term supply"],
     "type":"Contract","impact":"Commercial","score":92,"tier":1,"neg_subtype":None},
    {"kws":["commissioned","now operational","goes live","first delivery","deployed at","system online","live deployment","commercial operation date","cod achieved"],
     "type":"Deployment","impact":"Commercial","score":88,"tier":1,"neg_subtype":None},
    # Tier 2: Validated progress  base 60-82
    {"kws":["utility pilot","kepco pilot","hyperscaler pilot","shipyard pilot","grid operator pilot","epc pilot","offtaker pilot","named buyer pilot"],
     "type":"Pilot","impact":"Technical","score":80,"tier":2,"neg_subtype":None},
    {"kws":["pilot project","pilot program","field trial","demonstration project","demo installation","test deployment","live pilot"],
     "type":"Pilot","impact":"Technical","score":62,"tier":2,"neg_subtype":None},
    {"kws":["series a","series b","series c","series d","series e","raised $","raised €","raised £","funding round","growth equity","venture round","growth investment","strategic investment"],
     "type":"Financing","impact":"Financing","score":82,"tier":2,"neg_subtype":None},
    {"kws":["cfo","chief financial officer","appoints cfo","new cfo","vp finance","head of finance","finance director joins","appoints finance chief"],
     "type":"Hiring","impact":"Funding Signal","score":78,"tier":2,"neg_subtype":None},
    {"kws":["vp sales","chief commercial officer","vp business development","head of business development","bd director","appoints commercial","commercial director"],
     "type":"Hiring","impact":"Commercial","score":68,"tier":2,"neg_subtype":None},
    # Tier 3: Directional  base 36-72
    {"kws":["strategic partnership with","mou signed with","joint development agreement","framework agreement signed","cooperation agreement signed"],
     "type":"Partnership","impact":"Commercial","score":58,"tier":3,"neg_subtype":None},
    {"kws":["partnership","mou","collaboration","memorandum of understanding","joint development","co-development"],
     "type":"Partnership","impact":"Commercial","score":36,"tier":3,"neg_subtype":None},
    {"kws":["doe grant","eu grant","government grant","awarded grant","horizon europe","innovate uk","nrel award","motie grant"],
     "type":"Grant","impact":"Policy","score":46,"tier":3,"neg_subtype":None},
    {"kws":["gigafactory","manufacturing plant","new production facility","scale-up facility","opens facility","production expansion"],
     "type":"Expansion","impact":"Commercial","score":72,"tier":3,"neg_subtype":None},
    # Tier 4: Negative — always surfaced, no threshold
    {"kws":["delay","postponed","behind schedule","timeline slips","pushed back","project delayed"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"delay"},
    {"kws":["funding shortfall","struggles to raise","runway concerns","bridge loan needed","emergency funding"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"funding_risk"},
    {"kws":["cost overrun","over budget","capex increase","construction cost increase"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"cost_overrun"},
    {"kws":["supply chain issue","component shortage","material shortage","delivery delay"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"supply_chain"},
    {"kws":["hiring freeze","layoffs","redundancies","headcount reduction","staff cuts"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"hiring_freeze"},
    {"kws":["project cancelled","contract cancelled","project terminated","deal collapsed","deal fell through"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"cancellation"},
    {"kws":["competitor wins","competitor awarded","rival secures","loses contract to","outbid by"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"competitor_win"},
    {"kws":["subsidy ends","grant expires","policy reversal","mandate removed","government support withdrawn"],
     "type":"Negative","impact":"Risk","score":0,"tier":4,"neg_subtype":"subsidy_risk"},
]

SEGMENT_KWS = {
    "ess":         ["battery","energy storage","ess","vanadium","iron-air","flow battery","long duration","long-duration","bess","grid storage"],
    "marine_fc":   ["marine","vessel","ship","fuel cell","amogy","shipping","seafarer","imo cii","bunkering","maritime fuel"],
    "grid_sw":     ["vpp","virtual power","demand response","grid software","kepco","ancillary","frequency regulation","smart grid","dr platform"],
    "hvdc":        ["hvdc","transmission","subsea cable","offshore wind cable","interconnect","power cable","dc transmission"],
    "hydrogen":    ["hydrogen","electrolyzer","h2","liquid hydrogen","green hydrogen","electrolysis","pem electrolyzer","soec","ammonia"],
    "dc_power":    ["data center","hyperscaler","azure","aws","google cloud","power electronics","ai infrastructure","data centre"],
    "wte":         ["waste-to-energy","biogas","biomass","waste","incineration","landfill gas"],
    "forecasting": ["forecast","prediction","renewable forecast","grid forecast","ai grid","power prediction"],
}


# ──────────────────────────────────────────────────────────────────────────
# SECTION 4  SCORING ENGINE  (additive, every point explained)
# ──────────────────────────────────────────────────────────────────────────

SCORE_THRESHOLD_HIGH   = 60   # shown in default feed
SCORE_THRESHOLD_MEDIUM = 35   # shown when Medium filter active
SCORE_THRESHOLD_KEEP   = 20   # kept in DB, hidden from feed
# below KEEP → dropped to filteredOut log

SCORE_RULES = [
    {"id":"buyer_t1",   "pattern":r"\bkepco\b|\bmicrosoft\b|\bgoogle\b|\bamazon\b|\bengie\b|\be\.on\b|\bvattenfall\b|\bnationalgrid\b",
     "delta":+18,"group":"boost","reason":"Tier-1 strategic buyer named"},
    {"id":"buyer_t2",   "pattern":r"\bhyundai\b|\bsamsung\b|\bhanwha\b|\bshell\b|\bbp\b|\bsiemens\b|\babb\b|\bhitachi\b|\bmitsubishi\b",
     "delta":+12,"group":"boost","reason":"Major industrial/OEM buyer named"},
    {"id":"buyer_kr",   "pattern":r"\bls electric\b|\bls일렉트릭\b|\bsk e&s\b|\bsk에코\b|\bposco\b|\bhd hyundai\b|\b한국가스공사\b",
     "delta":+10,"group":"boost","reason":"Korean strategic buyer named"},
    {"id":"fig_money",  "pattern":r"\$[\d,]+\s*[mb]|\$[\d,]+\s*million|\$[\d,]+\s*billion|€[\d,]+\s*[mb]|£[\d,]+\s*[mb]|₩[\d,]+억",
     "delta":+15,"group":"boost","reason":"Specific financial figure"},
    {"id":"fig_mw",     "pattern":r"[\d,]+\s*mwh|[\d,]+\s*gwh|[\d,]+\s*mw\b|[\d,]+\s*gw\b",
     "delta":+10,"group":"boost","reason":"Specific capacity figure"},
    {"id":"timeframe",  "pattern":r"q[1-4]\s*20[2-9]\d|by 20[2-9]\d|within \d+ month|H[12] 20[2-9]\d",
     "delta":+8, "group":"boost","reason":"Concrete timeframe stated"},
    {"id":"geography",  "pattern":r"\bbusan\b|\bincheon\b|\bulsan\b|\brotterdam\b|\bsingapore\b|\bhamburg\b|\baberdeen\b",
     "delta":+5, "group":"boost","reason":"Named project location"},
    {"id":"co_match",   "pattern":None,
     "delta":+10,"group":"boost","reason":"Event matched to tracked company"},
    # noise
    {"id":"n_vague",    "pattern":r"\bexploring\b.{0,30}\bpartner|\blooking to\b.{0,20}\bpartner|\bin (early )?discussions\b|\bpotential (partner|deal|agreement)\b",
     "delta":-35,"group":"noise","reason":"Vague exploratory language"},
    {"id":"n_intent",   "pattern":r"\baims to\b|\bseeks to\b|\bplans to\b|\bhopes to\b|\bintends to\b",
     "delta":-20,"group":"noise","reason":"Intent stated, no confirmed action"},
    {"id":"n_specul",   "pattern":r"\bcould (become|reach|achieve|unlock)\b|\bmay (become|unlock)\b|\bhas the potential\b",
     "delta":-25,"group":"noise","reason":"Speculative outcome framing"},
    {"id":"n_pr",       "pattern":r"\bproud to (announce|partner|share)\b|\bexcited to (announce|share)\b|\bpleased to announce\b",
     "delta":-40,"group":"noise","reason":"Generic PR language"},
    {"id":"n_vision",   "pattern":r"\bunveils? (vision|strategy|roadmap)\b|\bstrategic vision\b",
     "delta":-30,"group":"noise","reason":"Vision/strategy announcement"},
    {"id":"n_award",    "pattern":r"\bwins? award\b|\brecognized as\b|\bnamed (a )?(top|leading|best)\b|\bgartner\b|\bfrost.*sullivan\b",
     "delta":-35,"group":"noise","reason":"Vanity recognition"},
    {"id":"n_conf",     "pattern":r"\bkeynote\b|\bspeaks? at\b|\bpanel (discussion|session)\b|\bwebinar\b|\battends? (conference|summit)\b",
     "delta":-30,"group":"noise","reason":"Conference appearance only"},
    {"id":"n_report",   "pattern":r"\bpublishes? (report|study|whitepaper)\b|\bnew (report|research|study)\b",
     "delta":-25,"group":"noise","reason":"Report/research only"},
    # veto
    {"id":"v_rebrand",  "pattern":r"\brebrands?\b|\bnew (logo|brand|website)\b|\blaunch(es)? website\b",
     "delta":-55,"group":"veto","reason":"Rebranding/marketing"},
    {"id":"v_opinion",  "pattern":r"\bopinion:\b|\bcommentary:\b|\bop-ed\b|\bviewpoint:\b",
     "delta":-60,"group":"veto","reason":"Opinion/commentary"},
    {"id":"v_digest",   "pattern":r"\bmarket (wrap|roundup|update)\b|\bweekly (round-?up|digest)\b|\bmonthly digest\b",
     "delta":-60,"group":"veto","reason":"Market wrap/digest"},
    {"id":"v_job",      "pattern":r"\bwe('re| are) hiring\b|\bjoin our team\b|\bopen (position|role)\b|\bcareer opportunit\b",
     "delta":-50,"group":"veto","reason":"Generic job posting"},
]

SCORE_RULEBOOK_DISPLAY = [
    {"group":"ALWAYS KEPT",        "color":"#16A34A","items":["Negative signals — exempt from threshold","Tier 1: Certification/Contract/Deployment — base 88-92"]},
    {"group":"BOOST (+points)",    "color":"#1A56DB","items":["Tier-1 buyer (KEPCO, Microsoft, Google): +18","Major industrial/OEM (Hyundai, Samsung): +12","Specific financial figure ($45M, ₩760억): +15","Specific capacity (500MWh, 2GW): +10","Concrete timeframe (Q3 2026): +8","Tracked company matched: +10"]},
    {"group":"NOISE (−points)",    "color":"#D97706","items":["Vague language (exploring, potential): -35","Intent without action (aims to): -20","Generic PR (proud to announce): -40","Vision/strategy announcement: -30","Industry award/Gartner: -35","Conference appearance: -30","Report publication: -25"]},
    {"group":"VETO (always drop)", "color":"#DC2626","items":["Opinion/commentary: -60","Market wrap/digest: -60","Generic job posting: -50","Rebranding: -55"]},
    {"group":"THRESHOLDS",         "color":"#6E6E6E","items":["≥ 60 → HIGH (default feed)","35–59 → MEDIUM","20–34 → LOW (DB only)","< 20 → DROPPED","Negatives: exempt"]},
]

NEG_SUBTYPE_META = {
    "delay":         {"label":"Delay",                    "icon":"⏱","severity":"high",    "memo":"Timeline extension raises capital-at-risk. Determine if project-level (isolated) or structural (market/tech)."},
    "funding_risk":  {"label":"Funding / Runway Risk",    "icon":"⚠","severity":"critical","memo":"Capital constraint signal. Bridge or down-round possible. Monitor existing investor behavior."},
    "cost_overrun":  {"label":"Cost Overrun",             "icon":"📈","severity":"high",   "memo":"Capex overshoot compresses returns. Reassess unit economics assumptions."},
    "supply_chain":  {"label":"Supply Chain Issue",       "icon":"🔗","severity":"medium", "memo":"Component shortage may delay deployment. Check if systemic or single-vendor."},
    "hiring_freeze": {"label":"Hiring Freeze / Layoffs",  "icon":"👥","severity":"high",   "memo":"Headcount reduction signals cost pressure or strategic pivot."},
    "cancellation":  {"label":"Cancellation",             "icon":"✗","severity":"critical","memo":"Revenue removed. May trigger investor clause review. Determine demand vs. execution cause."},
    "competitor_win":{"label":"Competitor Win",           "icon":"🏆","severity":"medium", "memo":"Named competitor contract in same TAM. Reassess differentiation thesis."},
    "subsidy_risk":  {"label":"Policy / Subsidy Risk",    "icon":"🏛","severity":"high",   "memo":"Subsidy-dependent revenue without commercial anchor is not investable."},
}


# ──────────────────────────────────────────────────────────────────────────
# SECTION 5  EVIDENCE CARD LIBRARIES
# ──────────────────────────────────────────────────────────────────────────

WHY_IT_MATTERS = {
    ("Certification","marine_fc"):  "Class approval removes the primary procurement barrier for marine fuel cells. Without it, shipyards cannot specify the technology in newbuild contracts.",
    ("Certification","ess"):        "Third-party certification (UL/IEC/KS) is required for grid interconnection and utility procurement. De-risks buyer liability and accelerates RFP inclusion.",
    ("Certification","grid_sw"):    "KPX interface certification is the legal prerequisite for Korea's ancillary services market participation. Directly unlocks recurring revenue streams.",
    ("Certification","hvdc"):       "TÜV/DNV component qualification is required for OEM supply chains (Siemens, ABB, Hitachi). Without it, no grid-scale procurement is possible.",
    ("Contract","grid_sw"):         "Named utility contract moves company from pilot-stage to commercial-stage in the investment framework. Key unknowns: ACV, duration, framework vs. project-specific.",
    ("Contract","ess"):             "Offtake/supply agreement is the clearest commercial-stage signal. LCOS competitiveness is implied but unconfirmed without disclosed contract terms.",
    ("Contract","marine_fc"):       "Named shipyard/shipping contract post-certification is the standard commercialization sequence. Represents first revenue-generating event.",
    ("Contract","hydrogen"):        "Offtake agreement is the critical missing link in most hydrogen project theses. Without a named buyer at contracted price, projects remain unviable.",
    ("Pilot","grid_sw"):            "Utility-sponsored pilot implies buyer has allocated opex budget and is evaluating procurement. Pilot-to-commercial conversion rate is the key metric.",
    ("Pilot","marine_fc"):          "Shipyard pilot validates vessel integration architecture. DNV involvement substantially increases class approval probability.",
    ("Pilot","ess"):                "Grid-connected pilot signals utility-scale targeting. Requires KPX/NERC interface compliance — itself a commercialization gate.",
    ("Pilot","dc_power"):           "Hyperscaler pilot is the strongest commercial signal for DC power tech. High ACV, low churn once contracted.",
    ("Financing","default"):        "Equity round confirms external capital validation. Key variables: investor identity (strategic vs. financial), round size vs. capex needs.",
    ("Hiring","default"):           "CFO hire with Series B+ experience correlates with fundraising within 3–6 months. BD/Sales hire signals active contract pipeline building.",
    ("Partnership","default"):      "Named strategic partnership is directional. MOU alone does not confirm commercial intent — check for binding terms (exclusivity, minimum volume).",
    ("Grant","default"):            "Government grant validates technology policy relevance but not market demand. Non-dilutive capital is positive but grant-only is not investable.",
    ("Negative","default"):         "Negative signals require investment timeline reassessment. Determine if project-level (isolated) or structural (market/technology).",
    ("News","default"):             "No specific investment pattern matched. Context only — not weighted in assessment without corroboration.",
}

MISSING_BY_TYPE = {
    ("Certification","default"):  ["Commercial application of certification not specified","Customer procurement pipeline not disclosed"],
    ("Contract","default"):       ["Contract ACV (annual contract value) not disclosed","Duration and renewal terms not public","Exclusivity and geographic scope unknown"],
    ("Pilot","default"):          ["Pilot success criteria not publicly defined","Conversion probability to commercial contract unknown","Sponsor procurement timeline not disclosed"],
    ("Financing","default"):      ["Post-money valuation not confirmed","Use of proceeds not specified","Revenue run-rate at raise not public"],
    ("Hiring","default"):         ["Fundraising timeline not confirmed","Whether hire reflects inbound interest or proactive preparation unknown"],
    ("Partnership","default"):    ["Binding terms (exclusivity, minimum volume) not confirmed","IP ownership and development scope unclear"],
    ("Grant","default"):          ["Commercial co-funding partner not identified","Path from grant to commercial revenue not articulated"],
    ("Negative","default"):       ["Root cause not confirmed","Management mitigation plan not public","Impact on existing contracts not disclosed"],
    ("News","default"):           ["No investment-relevant pattern matched","Primary research required before forming a view"],
}

MISSING_RULES = [
    {"id":"no_contract",  "label":"No Commercial Contract",         "severity":"critical",
     "check": lambda evs: not any(e["event_type"] in ("Contract","Deployment") for e in evs),
     "memo":  "No binding commercial agreement on record. All revenue is hypothetical until an offtake or supply contract is confirmed.",
     "sectors":"all"},
    {"id":"no_cert",      "label":"No Third-Party Certification",   "severity":"high",
     "check": lambda evs: not any(e["event_type"]=="Certification" for e in evs),
     "memo":  "No independent certification (DNV GL, TÜV, KPX, UL) confirmed. Required for procurement in most regulated energy segments.",
     "sectors":["marine_fc","ess","hvdc","grid_sw"]},
    {"id":"no_buyer",     "label":"No Named Strategic Buyer",       "severity":"high",
     "check": lambda evs: not any(re.search(r"kepco|utility|shipyard|hyperscaler|microsoft|google|amazon|engie|hanwha|hyundai|samsung|ls electric",(e.get("title","")+" "+e.get("summary","")).lower()) for e in evs),
     "memo":  "No named strategic buyer in any collected signal. Demand-side validation is absent.",
     "sectors":"all"},
    {"id":"no_deploy",    "label":"No Deployment / Go-Live",        "severity":"medium",
     "check": lambda evs: not any(e["event_type"]=="Deployment" for e in evs),
     "memo":  "No operational deployment confirmed. TRL-9 in a commercial setting is unverified.",
     "sectors":"all"},
    {"id":"pilot_gap",    "label":"Pilot → No Contract Conversion", "severity":"high",
     "check": lambda evs: any(e["event_type"]=="Pilot" for e in evs) and not any(e["event_type"] in ("Contract","Deployment") for e in evs),
     "memo":  "Pilot present but no commercial conversion. Most common failure point in energy hardware commercialization.",
     "sectors":"all"},
    {"id":"grant_only",   "label":"Grant Only — No Commercial Anchor","severity":"high",
     "check": lambda evs: any(e["event_type"]=="Grant" for e in evs) and not any(e["event_type"] in ("Contract","Pilot","Deployment") for e in evs),
     "memo":  "Grant funding without commercial anchor. Not sufficient for commercial-stage investment thesis.",
     "sectors":"all"},
]


# ──────────────────────────────────────────────────────────────────────────
# SECTION 6  PIPELINE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────

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

def score_event(raw_text, base, is_matched):
    s, breakdown = base + (10 if is_matched else 0), []
    if is_matched:
        breakdown.append({"id":"co_match","delta":10,"reason":"Event matched to tracked company","group":"boost"})
    for rule in SCORE_RULES:
        if rule["id"]=="co_match" or not rule["pattern"]: continue
        if re.search(rule["pattern"], raw_text, re.I):
            s += rule["delta"]
            breakdown.append({"id":rule["id"],"delta":rule["delta"],"reason":rule["reason"],"group":rule["group"]})
    final = max(0, min(100, round(s)))
    tier = "high" if final>=SCORE_THRESHOLD_HIGH else "medium" if final>=SCORE_THRESHOLD_MEDIUM else "low" if final>=SCORE_THRESHOLD_KEEP else "noise"
    penalties = sorted([b for b in breakdown if b["delta"]<0], key=lambda x:x["delta"])
    return {"signal_strength":final,"signal_tier":tier,"score_breakdown":breakdown,
            "is_noise":tier=="noise","drop_reason":penalties[0]["reason"] if penalties and tier=="noise" else None}

def compute_confidence(tier, strength, is_matched, is_neg):
    if is_neg:            return "Low","Negative signal — primary source verification required."
    if tier==1 and strength>=75 and is_matched: return "Medium-High","Tier-1 event with company match and high score."
    if tier==1 and strength>=60: return "Medium","Tier-1 event type; company unmatched or mixed score modifiers."
    if tier==2 and strength>=65 and is_matched: return "Medium","Tier-2 event with company match. Commercial confirmation absent."
    if tier==2 and strength>=50: return "Medium-Low","Tier-2 directional signal — not confirmatory."
    if tier<=3 and strength>=40: return "Low","Tier-3 or borderline score. Context only."
    return "Low","Score below signal threshold. Context only."

def make_id(sid, title, date):
    return hashlib.sha256(f"{sid}:{title}:{date}".encode()).hexdigest()[:12]

def fetch_sources():
    raw, source_log = [], []
    if not HAS_FEEDPARSER:
        return raw, [{"id":s["id"],"name":s["name"],"url":s["url"],"status":"failed","error":"feedparser not installed","items":0,"fetched_at":datetime.now(timezone.utc).isoformat()} for s in RSS_SOURCES]
    for s in RSS_SOURCES:
        ts = datetime.now(timezone.utc).isoformat()
        try:
            socket.setdefaulttimeout(15)
            feed = feedparser.parse(s["url"])
            if getattr(feed,"status",None) and feed.status>=400: raise Exception(f"HTTP {feed.status}")
            count, errors = 0, []
            for entry in feed.entries[:20]:
                title = getattr(entry,"title",""); summary = getattr(entry,"summary","")[:500]
                link  = getattr(entry,"link","")
                if not title or title=="[Removed]": continue
                t = entry.get("published_parsed") or entry.get("updated_parsed")
                date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}" if t else TODAY
                raw.append({"source_id":s["id"],"source_name":s["name"],"source_url":link,
                             "source_segments":s["segments"],"title":title,"summary":summary,
                             "published_date":date,"raw_text":(title+" "+summary).lower()})
                count += 1
            if count==0: errors.append("Feed returned 0 usable items")
            source_log.append({"id":s["id"],"name":s["name"],"url":s["url"],"status":"success" if count>0 else "partial","error":errors[0] if errors else None,"items":count,"fetched_at":ts})
            print(f"  ✓ {s['name']}: {count}")
        except Exception as ex:
            source_log.append({"id":s["id"],"name":s["name"],"url":s["url"],"status":"failed","error":str(ex),"items":0,"fetched_at":ts})
            print(f"  ✗ {s['name']}: {ex}")
    return raw, source_log

def normalize(raw_items):
    kept, filtered = [], []
    for item in raw_items:
        clf       = classify(item["raw_text"])
        segment   = infer_segment(item["raw_text"], item["source_segments"])
        co_id, co_nm = match_company(item["raw_text"])
        buyers    = match_buyers(item["raw_text"])
        strength  = score_event(item["raw_text"], clf["base_score"], co_id is not None)
        is_neg    = clf["type"]=="Negative"
        why_key   = (clf["type"],segment) if (clf["type"],segment) in WHY_IT_MATTERS else (clf["type"],"default")
        why_text  = WHY_IT_MATTERS.get(why_key, WHY_IT_MATTERS.get((clf["type"],"default"),"No rationale available."))
        miss_key  = (clf["type"],segment) if (clf["type"],segment) in MISSING_BY_TYPE else (clf["type"],"default")
        missing   = MISSING_BY_TYPE.get(miss_key, ["No gap analysis available."])
        conf_l, conf_r = compute_confidence(clf["tier"],strength["signal_strength"],co_id is not None,is_neg)
        obs       = item["title"].strip()
        fs        = item["summary"].strip().split(".")[0].strip() if item["summary"] else ""
        detail    = (fs+".") if fs and fs.lower()!=obs.lower() and len(fs)>20 else None
        event = {
            "id":make_id(item["source_id"],item["title"],item["published_date"]),
            "title":item["title"],"summary":item["summary"],"event_date":item["published_date"],
            "source_name":item["source_name"],"source_url":item["source_url"],
            "event_type":clf["type"],"impact_type":clf["impact"],"matched_rule":clf["matched"],"tier":clf["tier"],
            "signal_stage":"commercial" if clf["type"] in ("Contract","Certification","Deployment") else "early" if clf["type"] in ("Pilot","Milestone") else "strategic",
            "signal_strength":strength["signal_strength"],"signal_tier":strength["signal_tier"],"score_breakdown":strength["score_breakdown"],
            "segment":segment,"company_id":co_id,"company_name":co_nm or "Unassigned",
            "buyer_matches":buyers,"is_negative":is_neg,"neg_subtype":clf["neg_subtype"],"is_noise":strength["is_noise"] and not is_neg,
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


# ──────────────────────────────────────────────────────────────────────────
# SECTION 7  COMPANY ENRICHMENT
# ──────────────────────────────────────────────────────────────────────────

STAGE_LADDER = [
    # (label, color, required_event_types, description)
    ("PF-Ready",        "#0F4C75",{"Contract","Deployment"},
     "Multiple commercial deployments or project-financed asset. Infrastructure/PF investment framework applicable."),
    ("Scaling",         "#0A6640",{"Contract","Deployment"},
     "Commercial contracts in place. Revenue visible. Expanding into second geography or second buyer."),
    ("First Commercial","#1A56DB",{"Contract","Deployment"},
     "First binding commercial agreement or live deployment confirmed. Revenue visibility beginning to emerge."),
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
     "memo":"Certification obtained but no commercial contract yet. Hardest technical gate cleared; commercial conversion is next critical event."},
    {"id":"strategic_momentum","label":"Strategic Momentum","color":"#5B21B6",
     "req":lambda t,h,n:"Partnership" in t and ("Pilot" in t or "Financing" in t) and n==0,
     "memo":"Strategic partnership combined with pilot or financing. Watch for partnership-to-contract conversion timeline."},
    {"id":"fundraise_signal","label":"Fundraising Signal","color":"#7D4E00",
     "req":lambda t,h,n:"Hiring" in t and "Financing" not in t and n==0,
     "memo":"Finance/BD hire without confirmed round. CFO hire historically correlates with raise within 3–6 months."},
    {"id":"grant_dependent","label":"Grant-Dependent","color":"#D97706",
     "req":lambda t,h,n:"Grant" in t and "Contract" not in t and "Pilot" not in t and "Certification" not in t,
     "memo":"Grant-only signal. Non-dilutive capital without commercial anchor is insufficient for commercial-stage thesis."},
    {"id":"negative_flags","label":"Negative Signals — Reassess","color":"#C0392B",
     "req":lambda t,h,n:n>=1,
     "memo":"Negative signals detected. Reassess positive signals in context of headwinds. Determine if project-level or structural."},
    {"id":"low_density","label":"Insufficient Signal","color":"#A8A8A8",
     "req":lambda t,h,n:True,
     "memo":"Signal density insufficient for pattern recognition. Primary research required before forming a view."},
]

TTR_RULES = [
    ("Near-term","#C0392B",lambda sl,pid,h:sl in ("PF-Ready","Scaling") or (sl=="First Commercial" and pid in ("series_c_prep","commercial_breakout") and h>=2)),
    ("Mid-term", "#7D4E00",lambda sl,pid,h:sl in ("First Commercial","Demo","Pilot") and pid not in ("grant_dependent","low_density","negative_flags")),
    ("Long-term","#6E6E6E",lambda sl,pid,h:True),
]

def infer_stage(co, evs):
    types, co_stage = {e["event_type"] for e in evs}, co.get("stage","").lower()
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
    types     = [e["event_type"] for e in evs]
    has_cert  = "Certification" in types;  has_ctr  = "Contract" in types or "Deployment" in types
    has_hire  = "Hiring" in types;         has_plt  = "Pilot" in types
    has_fin   = "Financing" in types;      has_neg  = any(e["is_negative"] for e in evs)
    has_grnt  = "Grant" in types;          high_ct  = sum(1 for e in evs if e["signal_tier"]=="high")
    facts = [f"[{e['event_type']}] {e['title']} — {e['source_name']} ({e['event_date']})" for e in evs if e["signal_strength"]>=40][:5]
    if has_cert and has_ctr and has_hire:
        pat="Pre-Series C signal cluster: regulatory certification, named commercial contract, and finance-function hire observed in the same window. Comparable domestic cases have preceded formal raise processes within 6–12 months."; ind=["Series C process likely within 6–12 months","Strategic investor seeking anchor position","Watch for international BD hire as leading indicator"]; pid,conf="series_c_prep","Medium-High"
    elif has_cert and has_ctr:
        pat="Third-party certification and first commercial contract secured. Supply chain entry — the hardest gate for component vendors — is now demonstrated. Revenue visibility emerging; scale and exclusivity terms unconfirmed."; ind=["Second OEM customer likely in parallel pursuit","M&A interest from EPC or OEM possible","Bridge financing if contract ramp is slower than projected"]; pid,conf="supply_entry","Medium"
    elif has_plt and (has_fin or has_ctr):
        pat="Field-level technical progress alongside financing or commercial engagement. Certification gate not yet cleared — all commercial signals remain conditional."; ind=["Certification application likely in progress","Partnership may convert to LOI upon certification"]; pid,conf="cert_gate","Medium-Low"
    elif has_grnt and not has_ctr:
        pat="Primary visible signal is government grant funding. Grants validate technology direction but not market demand. Without a named offtaker or strategic buyer, the investment thesis cannot advance."; ind=["Technology at TRL 4–6: government-funded validation","Commercial pipeline may be early or undisclosed"]; pid,conf="grant_only","Low"
    elif has_fin and has_ctr:
        pat="Financing round closed alongside a commercial contract — strongest single-window signal combination. External capital validation and initial revenue visibility appearing together materially de-risks the near-term investment thesis."; ind=["Revenue ramp expected within 12–18 months","Strategic investor may hold first-refusal or M&A option","Follow-on at higher valuation once KPIs are met"]; pid,conf="strategic_capital","High"
    elif has_neg:
        pat="One or more negative signals detected. Positive signals must be reassessed in context of identified headwinds."; ind=["Timeline extension likely","Bridge or down-round possible if delay compounds"]; pid,conf="negative","Low"
    else:
        pat=f"{len(evs)} event(s) from {len(set(e['source_name'] for e in evs))} source(s). Signal density insufficient to confirm a pattern. Primary research recommended."; ind=["Early stage or limited public disclosure"]; pid,conf="low_density","Low"
    missing=[]
    if not has_ctr: missing.append("No commercial contract — all revenue hypothetical until confirmed")
    if not has_cert and co.get("sector") in ("marine_fc","ess","hvdc"): missing.append("No third-party certification — procurement prerequisite in this sector")
    if high_ct==0: missing.append("No high-confidence signals — current events are directional only")
    if has_grnt and not has_ctr: missing.append("Grant present but no commercial anchor — grant-only is insufficient")
    next_map={"series_c_prep":"Monitor for overseas VP Sales posting or second KEPCO-scale contract ACV.","supply_entry":"Verify contract scope (project vs. framework). Check if second OEM RFP in progress.","cert_gate":"Confirm whether certification application is formally submitted.","grant_only":"Determine if grant requires commercial co-funding partner — this would surface a buyer.","strategic_capital":"Identify strategic investor sector position. Check prior M&A history in segment.","negative":"Determine if negative is project-level or structural.","low_density":"Direct outreach or channel check recommended."}
    return {"observed_facts":facts,"matched_pattern":pat,"pattern_id":pid,"may_indicate":ind,"missing":missing,"confidence":conf,"next_check":next_map.get(pid,"Review latest events and cross-check primary sources."),"event_count":len(evs),"high_signal":high_ct,"note":"Generated from existing events only. No data invented."}

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
    linked_proj = [{"id":p["id"],"name":p["name"],"status":p["status"],"location":p["location"]} for p in PROJECTS if co["id"] in p["linked_companies"]]
    return {**co,"events":sorted(evs,key=lambda e:e["event_date"],reverse=True)[:10],"insight":build_insight(co,evs),
            "signal_count":len(evs),"high_count":high_ct,"neg_count":neg_ct,"reinforcing":reinf,"type_counts":type_counts,
            "stage_label":stage_label,"stage_color":stage_color,"stage_desc":stage_desc,"pattern":pattern,
            "ttr":ttr_l,"ttr_color":ttr_c,"gaps":gaps,
            "critical_gaps":sum(1 for g in gaps if g["severity"]=="critical"),"high_gaps":sum(1 for g in gaps if g["severity"]=="high"),
            "buyer_activity":buyer_act,"linked_projects":linked_proj}


# ──────────────────────────────────────────────────────────────────────────
# SECTION 8  PANEL BUILDERS
# ──────────────────────────────────────────────────────────────────────────

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
    return {"negative_signals":negs,"missing_evidence":miss,
            "panel_stats":{"negative_count":len(negs),"critical_neg":sum(1 for n in negs if n["severity"]=="critical"),
                           "companies_with_gaps":len(miss),"total_critical_gaps":sum(c["critical_gaps"] for c in miss)}}


# ──────────────────────────────────────────────────────────────────────────
# SECTION 9  BRIEF GENERATION
# ──────────────────────────────────────────────────────────────────────────

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
    return f"{TODAY_KR}. {len(high)} high-signal events. Top: {'; '.join(e['title'] for e in high[:2])}. Companies: {', '.join(set(e['company_name'] for e in high if e['company_id']))}."


# ──────────────────────────────────────────────────────────────────────────
# SECTION 10  MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*60}\nEnergy Capital Intelligence  v2.0\n{TODAY_KR}\n{'═'*60}\n")
    Path("data").mkdir(exist_ok=True)

    print("① Fetch...")
    raw, source_log = fetch_sources()
    print(f"  {len(raw)} raw items\n")

    print("② Classify + score + filter...")
    kept, filtered = normalize(raw)
    print(f"  Kept: {len(kept)} | Filtered: {len(filtered)}\n")

    print("③ Company enrichment...")
    co_evs = {}
    for e in kept:
        if e["company_id"]: co_evs.setdefault(e["company_id"],[]).append(e)
    co_intel = {co["id"]:enrich_company(co,co_evs.get(co["id"],[])) for co in COMPANIES if co_evs.get(co["id"])}
    print(f"  {len(co_intel)} companies enriched\n")

    print("④ Strategic buyer activity...")
    buyer_global = {}
    for ev in kept:
        for b in ev.get("buyer_matches",[]):
            buyer_global.setdefault(b["id"],{"id":b["id"],"name":b["name"],"type":b["type"],"events":[]})
            buyer_global[b["id"]]["events"].append({"date":ev["event_date"],"title":ev["title"],"event_type":ev["event_type"],"source":ev["source_name"],"score":ev["signal_strength"]})
    print(f"  {len(buyer_global)} buyers with activity\n")

    print("⑤ Panels...")
    panels = build_panels(kept, co_intel)
    print(f"  Negative: {panels['panel_stats']['negative_count']} | Gaps: {panels['panel_stats']['companies_with_gaps']} companies\n")

    print("⑥ Brief...")
    brief = generate_brief(kept)

    stats = {"total":len(kept),"high":sum(1 for e in kept if e["signal_tier"]=="high"),
             "medium":sum(1 for e in kept if e["signal_tier"]=="medium"),"negative":sum(1 for e in kept if e["is_negative"]),
             "matched":sum(1 for e in kept if e["company_id"]),"filtered_out":len(filtered),
             "companies_with_signals":len(co_intel),"by_segment":{},"by_type":{}}
    for e in kept:
        stats["by_segment"][e["segment"]] = stats["by_segment"].get(e["segment"],0)+1
        stats["by_type"][e["event_type"]]  = stats["by_type"].get(e["event_type"],0)+1

    output = {"date":TODAY,"dateKr":TODAY_KR,"generatedAt":datetime.now(timezone.utc).isoformat(),
              "brief":brief,"stats":stats,"signals":kept,"filteredOut":filtered[:20],
              "companies":co_intel,"projects":PROJECTS,"strategic_buyers":STRATEGIC_BUYERS,
              "buyer_activity":buyer_global,"panels":panels,"source_log":source_log,
              "score_rulebook":SCORE_RULEBOOK_DISPLAY,
              "reliability":{"sources_total":len(source_log),
                             "sources_ok":sum(1 for s in source_log if s["status"]=="success"),
                             "sources_partial":sum(1 for s in source_log if s["status"]=="partial"),
                             "sources_failed":sum(1 for s in source_log if s["status"]=="failed"),
                             "new_events":len(kept),"filtered_out":len(filtered)}}

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

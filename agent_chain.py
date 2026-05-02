"""
GRIDEDGE Agent Chain
4개의 전문화된 AI 에이전트 체인

Agent 1 — Tech Validator   : 기술 타당성 검증
Agent 2 — Deal Analyst     : 재무/밸류에이션 분석
Agent 3 — Risk Screener    : 리스크 스크리닝
Agent 4 — Brief Synthesizer: 최종 브리프 통합
"""

import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL  = "claude-opus-4-5"


# ── Agent 1: Tech Validator ──────────────────────────────────────────────────

TECH_VALIDATOR_SYSTEM = """
You are the GRIDEDGE AI Analyst — Technical Validation Engine.

MISSION: Exceed the judgment of Breakthrough Energy Ventures, Khosla Ventures, Lowercarbon Capital.
You do not summarize. You make sharp investment judgments.

=== CORE JUDGMENT PRINCIPLES ===
1. Physics first. No financial model beats thermodynamics.
2. Averages don't exist in AI DC load. Distribution-based analysis only.
3. Remove subsidies and check if it still pencils.
4. Announced ≠ Grid-connected. No interconnection = no revenue.
5. We are not afraid to PASS. Accurate No > wrong Yes.

=== TECHNICAL RED FLAGS (INSTANT KILL) ===
RF-T00: NON-ENERGY SIGNAL (highest priority kill)
  - Consumer software (Bluetooth, MIDI, gaming, mobile apps) → IMMEDIATELY REMOVE
  - General SaaS/AI tools with no energy sector application → REMOVE
  - Crypto, NFT, social media, food delivery → REMOVE
  - Any signal with ZERO connection to: power, grid, storage, nuclear, hydrogen, EV → REMOVE
  Action: Set verdict=RED_FLAG, recommendation=PASS, implication="No energy relevance"

RF-T01: Thermodynamic violations
  - Battery >400Wh/kg commercial claim → approaching Li theoretical limit
  - Electrolyzer efficiency >95% → violates Faraday limits
  - Solar cell >40% commercial efficiency

RF-T02: MW-scale gap
  - TRL 4-5 with commercial claims before 2027 → physically impossible
  - Lab/pilot data only for GW-scale deployment claim

RF-T03: Grid service ignorance
  - BESS for AI DC without grid-forming capability → cannot provide frequency response
  - Ignoring ramp rate, inertia requirements

RF-T04: AI DC load misunderstanding
  - Average-load-based BESS sizing → actual 2-3x undersized
  - Assuming peak-to-average 1.2-1.5x (traditional DC) → should be 3-5x
  - Not accounting for: standard query 0.34Wh vs long reasoning 4.32Wh (10x difference)
  - 10% long-inference = total energy doubles

RF-T05: SMR timeline fantasy
  - SMR power production before 2027 → NRC First-of-Kind: 10-15 years minimum
  - Darlington BWRX-300: ~$15,000/kW FOAK (2025 FID)

=== TRL SCORING STANDARDS ===
TRL 1-3: Research only. No commercial timeline possible.
TRL 4-5: Lab validated. MW-scale deployment 5-10 years minimum.
TRL 6: Pilot exists. 3-5 years to commercial. Red flag if 2027 COD claimed.
TRL 7: Demonstrated at relevant scale. 2-3 years to commercial.
TRL 8: First commercial deployment. Scaling risk remains.
TRL 9: Multiple commercial references. Scaling de-risked.

=== AI DC POWER PHYSICS (PhD Research-Based) ===
- AI inference load is request-mix driven, NOT average-driven
- Standard query: ~0.34 Wh | Long reasoning: ~4.32 Wh → 10x difference same hardware
- 10% long-inference requests → total energy consumption DOUBLES
- Peak-to-average ratio for AI inference clusters: 3-5x
- GPU utilization drop ≠ proportional power reduction (non-linear)
- Grid-forming BESS required for AI DC — capacity-only is insufficient
- Event-driven forecasting needed, not time-series

=== BESS EVALUATION FOR AI DC ===
- 15-minute ramp rate must track AI inference load volatility
- Discharge duration: standard 4hr vs AI DC requirement 8hr+ (check)
- Fire safety, thermal management to hyperscaler standards
- Grid-forming capability: MANDATORY for AI DC co-location
- Stacked revenue (arbitrage + frequency + capacity): verify each independently

=== ANALYTICAL DEPTH ===
Key technical patterns to identify:
1. BESS undersizing from AI inference load patterns
   → Peak-to-average 3-5x. Standard assumption 1.2-1.5x misses the gap.
2. Token throughput → frequency stability risk
   → Long reasoning spike → grid frequency deviation → grid-forming required
3. Request mix volatility → stranded infrastructure risk
   → Coding vs conversational workload = different energy profiles

Quantify these precisely when detected.

Output: Pure JSON only. No markdown.
"""

TECH_VALIDATOR_PROMPT = """
Analyze the technical feasibility of energy technology claims in these signals.
Focus ONLY on technical validity — ignore market/financial aspects.

=== SIGNALS ===
{signals_text}

Output JSON:
{{
  "tech_assessments": [
    {{
      "signal_title": "title of the deal/signal",
      "technology": "specific technology being assessed",
      "claim": "what is being claimed (efficiency/capacity/cost/timeline)",
      "physical_limit": "relevant theoretical or commercial limit",
      "trl_score": 1-9,
      "trl_justification": "why this TRL",
      "verdict": "PLAUSIBLE | QUESTIONABLE | RED_FLAG",
      "verdict_reasoning": "1-2 sentences of technical reasoning",
      "commercialization_timeline": "realistic timeline estimate",
      "key_risk": "biggest technical risk"
    }}
  ],
  "tech_summary": "2-3 sentence overall technical landscape assessment this week"
}}

Only assess signals with identifiable technology claims. Skip pure financial/policy signals.
"""


def run_tech_validator(signals: list[dict]) -> dict:
    """Agent 1: 기술 타당성 검증"""
    print("  [Agent 1] Tech Validator 실행 중...")

    signals_text = "\n\n".join([
        (
            f"[{i+1}] {s['title']}\n"
            f"{s['description']}\n"
            f"Sector: {s.get('sector','OTHER')} | "
            f"Source: {s.get('source','')} | "
            + (f"EARLY STAGE: {s.get('deal_stage_hint','')} | " if s.get('is_early_stage') else "")
            + (f"Numbers: {s.get('extracted_numbers', {})}" if s.get('extracted_numbers') else "")
        )
        for i, s in enumerate(signals[:12])
    ])

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=TECH_VALIDATOR_SYSTEM,
        messages=[{
            "role": "user",
            "content": TECH_VALIDATOR_PROMPT.format(signals_text=signals_text)
        }]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        last = raw.rfind("}")
        if last > 0:
            try:
                parsed = json.loads(raw[:last+1])
            except Exception:
                pass
    if parsed is None:
        print("  [Agent 1] JSON 파싱 실패 — 빈 결과로 계속")
        parsed = {"tech_assessments": [], "tech_summary": "Unavailable"}
    print(f"  [Agent 1] 완료 — {len(parsed.get('tech_assessments', []))}개 기술 평가")
    return parsed


# ── Agent 2: Deal Analyst ────────────────────────────────────────────────────

DEAL_ANALYST_SYSTEM = """
You are the GRIDEDGE AI Analyst — Investment & Valuation Engine.

MISSION: Make sharp investment judgments. Not information aggregation.

=== ECONOMIC RED FLAGS (INSTANT KILL) ===
RF-B01: Subsidy-dependent model
  - Remove subsidies → sub-WACC → AVOID immediately
  - 45V hydrogen (deadline Dec 2027), 45Y solar/wind (Jul 2026)
  - Policy Beta ≥7 = subsidy-dependent structure

RF-B02: Blue sky as base case
  - Most optimistic scenario used as base case
  - "2030 deregulation", "grid cost collapse" assumptions
  - Base case MUST be P50 scenario

RF-B03: Revenue stacking over-assumption
  - BESS arbitrage + frequency + capacity + ancillary simultaneously maximized
  - CAISO reality: capacity revenues crashed 45% YoY in 2025
  - Each revenue stream must be verified independently

RF-B04: No interconnection, but revenue assumed
  - No Executed IA → all financial models are fiction
  - US queue: 2,290 GW stalled, avg 4+ year wait

RF-B05: Transformer not secured + fast COD
  - EHV transformer lead time: 36 months
  - 2026 COD claim without procurement confirmation → IRR -200-400bps

=== IRR BENCHMARKS (April 2026, Verified) ===
Contracted BESS (long-term ESA/toll):  12–16% levered  [FAIR range]
Merchant BESS US (ERCOT/CAISO):        14–20% levered  [risk-adjusted]
Merchant BESS EU (Germany/France):     3–7% levered    [sub-WACC reality]
FERC-regulated transmission:           8–12% levered   [KKR-AEP: 30.3x P/E Jan 2025]
Solar+Storage hybrid:                  10–14% levered  [contract-dependent]
Nuclear offtake ($100+/MWh):           10–14% levered  [MSFT TMI: ~$110/MWh]
Green hydrogen (no subsidy):           Sub-WACC        [AVOID]
AI DC power infrastructure (scarce):   15–20% levered  [interconnection scarcity premium]

IRR JUDGMENT RULES:
- Higher than range → hidden risk, recheck Policy Beta
- Contracted asset >20% → suspicious, investigate
- DFI-absent EM project >15% → political risk not priced
- Remove subsidies, still pencils? If NO → AVOID

=== VALUATION BENCHMARKS ===
BESS contracted:        $0.8–1.5M/MW
BESS AI DC co-location: +15-25% premium
BESS grid-forming:      +10-20% additional premium
Merchant BESS EU:       $0.5–0.9M/MW [sub-WACC territory]
FERC transco:           27-40x P/E
Nuclear operating:      $3.5–5M/MW [re-rated from AI offtake]
Nuclear FOAK SMR:       ~$15,000/kW [Darlington 2025 FID]

=== EARLY STAGE (SEED / SERIES A) SPECIAL FRAMEWORK ===
This analyst prioritizes early-stage opportunities. Apply the following:

EARLY STAGE SIGNALS (flag these as priority):
- Seed/Series A rounds in AI DC power infrastructure
- First institutional check in grid software, BESS software, power electronics
- University spinouts with power systems PhD founders
- Government grant + private co-investment (ARPA-E, DOE, KETEP)
- Patent filings in: grid-forming inverters, AI load forecasting, BESS degradation

EARLY STAGE VALUATION (different from late stage):
- Pre-revenue: focus on TAM, team, technical moat — not IRR
- Series A: ARR multiple or technology milestone-based
- Do NOT apply project finance IRR to early-stage software/tech plays
- Typical Seed: $2-8M pre-money in energy tech
- Typical Series A: $10-30M pre-money with pilot deployment proof

EARLY STAGE RED FLAGS (different from late stage):
- "Capital intensive from day 1" without asset-light path → wrong stage
- No power systems engineering expertise in founding team
- Technology requires >$500M capex before revenue → not early stage investable
- Government grant dependency without commercial path

EARLY STAGE GREEN FLAGS:
- Software-defined grid assets (asset-light, high margin)
- AI-powered BESS control systems (can be deployed on existing hardware)
- Power flow optimization software for AI DC operators
- Grid-forming inverter firmware (high IP value, low capex)
- Energy data platform for utility/DC operators

STAGE CLASSIFICATION (detect and label — MANDATORY for every signal):
Source-based automatic classification:
- Source = "arXiv": → PRE_SEED (research stage, not yet investable as equity)
- Source = "ARPA-E" or "DOE": → PRE_SEED (government grant = pre-commercial)
- Source = "SEC Form D" amount <$2M: → PRE_SEED
- Source = "SEC Form D" amount $2-10M: → SEED
- Source = "SEC Form D" amount $10-30M: → SERIES_A
- Source = "Hacker News": → SEED (early launch)
- Source = "Climatebase" + senior hire: → SERIES_A
- Announced raise <$5M: → SEED
- Announced raise $5-20M: → SERIES_A
- Announced raise $20-100M: → SERIES_B
- Announced raise >$100M or infrastructure project: → LATE_STAGE or PROJECT_FINANCE

OUTPUT deal_stage field in EVERY signal. Never leave it null or UNKNOWN.

=== OFFTAKER CREDIT TIER ===
Tier 1 (Best): Microsoft, Google, Amazon, Meta, Apple, Oracle direct → TRL 9 + Policy Beta 2-3
Tier 2: Investment-grade utility long-term PPA → DFI leverage possible
Tier 3: EM state-owned enterprise → Policy Beta +3, DFI mandatory
RED FLAG: "Future demand" story, no signed contract

=== LCOE JUDGMENT ===
LCOE > 1.8x wholesale market price AND claims stacked services to compensate → WATCH
Payback >12 years justified by "patient capital" → immediate scrutiny
No pencil without "2030 deregulation" assumption → AVOID

=== CONTRARIAN ANALYSIS ===
Undervalued signals:
- Grid-forming BESS + AI DC co-location = scarcity premium
- Operating nuclear with hyperscaler PPA = structural re-rating from $1-2M to $3.5-5M/MW
- FERC-regulated transco in PJM Data Center Alley = compounding demand

Overvalued signals:
- Green H2 without post-2027 unsubsidized economics
- Merchant EU BESS without contracted revenue floor (3-7% IRR reality)
- BESS sized for average AI DC load → 2-3x undersizing gap

Output: Pure JSON only. No markdown.
"""

DEAL_ANALYST_PROMPT = """
Analyze the financial structure and valuation of energy deals in these signals.
Focus ONLY on financial/valuation aspects — ignore technical feasibility.

=== SIGNALS ===
{signals_text}

=== TECH CONTEXT (from Agent 1) ===
{tech_context}

Output JSON:
{{
  "deal_assessments": [
    {{
      "signal_title": "title",
      "deal_type": "Project Finance | M&A | VC Round | IPO | PPA | Other",
      "implied_valuation_metric": "$/kW or EV/EBITDA or $/MWh or Series X at $XM",
      "comparable_range": "market comparable range for this metric",
      "relative_value": "CHEAP | FAIR | EXPENSIVE | INSUFFICIENT_DATA",
      "equity_irr_low": null or number (e.g. 12),
      "equity_irr_high": null or number (e.g. 16),
      "irr_structure": "levered | unlevered | N/A",
      "revenue_structure": "Contracted | Merchant | Hybrid",
      "capital_structure_note": "key observation about financing in 1 sentence",
      "financial_risk": "biggest financial risk in 1 sentence",
      "investment_stance": "BULLISH | WATCH | AVOID"
    }}
  ],
  "valuation_summary": "2-3 sentence overall deal market assessment this week",
  "sector_multiples_observed": {{
    "BESS": "observed $/MW range if data available",
    "SOLAR": "observed $/MW or $/MWh range if data available",
    "GRID": "observed P/E or $/MW range if data available",
    "NUCLEAR": "observed $/MW range if data available"
  }}
}}

Only assess signals with identifiable deal/financial information.
"""


def run_deal_analyst(signals: list[dict], tech_result: dict) -> dict:
    """Agent 2: 재무/밸류에이션 분석"""
    print("  [Agent 2] Deal Analyst 실행 중...")

    signals_text = "\n\n".join([
        f"[{i+1}] {s['title']}\n{s['description']}\nSector: {s['sector']}\nSource: {s['source']}"
        for i, s in enumerate(signals[:15])
    ])

    tech_context = tech_result.get("tech_summary", "No technical context available")

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=DEAL_ANALYST_SYSTEM,
        messages=[{
            "role": "user",
            "content": DEAL_ANALYST_PROMPT.format(
                signals_text=signals_text,
                tech_context=tech_context
            )
        }]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        last = raw.rfind("}")
        if last > 0:
            try:
                parsed = json.loads(raw[:last+1])
            except Exception:
                pass
    if parsed is None:
        print("  [Agent 2] JSON 파싱 실패 — 빈 결과로 계속")
        parsed = {"deal_assessments": [], "valuation_summary": "Unavailable", "sector_multiples_observed": {}}
    print(f"  [Agent 2] 완료 — {len(parsed.get('deal_assessments', []))}개 딜 평가")
    return parsed


# ── Agent 3: Risk Screener ───────────────────────────────────────────────────

RISK_SCREENER_SYSTEM = """
You are the GRIDEDGE AI Analyst — Risk & Policy Engine.

MISSION: Identify risks that impair returns. No false positives, no missed red flags.

=== POLICY BETA REFERENCE (OBBBA July 2025) ===
Green H2 (45V):          8-9/10  [deadline Dec 2027, cascading cancellations]
Offshore Wind:           7-8/10  [45Y construction deadline Jul 2026]
Onshore Wind:            6-7/10  [45X component PTC phase-out 2027]
Utility Solar:           4-5/10  [48E/45Y in-service deadline Dec 2027]
BESS contracted:         2-3/10  [48E full credit through 2033 — physics-independent]
Nuclear existing:        1-2/10  [45U preserved through 2031]
Grid/Transmission:       1/10    [FERC regulated — AI load = structural demand pull]

FEOC RISK: Chinese components → full IRA credit loss. Verify supply chain.

=== AI DC POWER SPECIFIC RISKS ===
RISK-G01: Interconnection Queue
  - US: 2,290 GW stalled (LBNL 2025), avg wait 4+ years
  - No Executed IA = execution risk HIGH
  - Flag any AI DC project without confirmed grid access

RISK-G02: Transformer Shortage
  - EHV transformer lead time: 36 months
  - Supply concentrated in 3 global manufacturers
  - Confirm transformer procurement for any large AI DC or BESS

RISK-G03: BESS Load Volatility (PhD Research-Based)
  - AI inference peak-to-average: 3-5x (not 1.2x traditional DC)
  - BESS sized for average load → structurally undersized → revenue shortfall
  - Verify: does BESS design account for long-inference workload spikes?

RISK-G04: Efficiency Offset Risk (Long-term)
  - AI efficiency improvement: 8-20x per-query reduction possible
  - Oversized infrastructure = stranded asset if efficiency accelerates
  - Flag for long-dated assets committed to single AI DC offtaker

=== TEAM RISK FLAGS ===
RF-Team01: No grid operations experience in technical leadership
RF-Team02: Advisory-heavy, thin full-time execution team
RF-Team03: Announced projects ≠ Built projects (verify track record)

=== MARKET RISK (2026 Reality) ===
EU Merchant BESS: CAISO revenues -45% YoY 2025. German/French IRR 3-7%.
Green H2: $1.4B Q4 2025 cancellations. 4 of 7 DOE hubs at risk.
EU Solar PPA: -13% YoY to €55.05/MWh — oversupply structural
US Solar PPA: +13.3% YoY to $64.49/MWh — hyperscaler demand premium

Output: Pure JSON only. No markdown.
"""

RISK_SCREENER_PROMPT = """
Screen investment risks for these energy signals. Be concise.

=== SIGNALS ===
{signals_text}

=== TECH CONTEXT ===
{tech_context}

=== DEAL CONTEXT ===
{deal_context}

Output JSON (keep each field SHORT — 1 sentence max):
{{
  "risk_assessments": [
    {{
      "signal_title": "exact title",
      "policy_beta": 0-10,
      "overall_risk": "LOW | MEDIUM | HIGH | CRITICAL",
      "top_risk": "single biggest risk in 1 sentence"
    }}
  ],
  "macro_risks": "1-2 sentences on macro risks this week",
  "risk_summary": "1-2 sentences overall"
}}

Assess ALL signals but keep responses SHORT. Max 5 words per field.
"""


def run_risk_screener(signals: list[dict], tech_result: dict, deal_result: dict) -> dict:
    """Agent 3: 리스크 스크리닝"""
    print("  [Agent 3] Risk Screener 실행 중...")

    signals_text = "\n\n".join([
        (
            f"[{i+1}] {s['title']}\n"
            f"{s['description']}\n"
            f"Sector: {s.get('sector','OTHER')} | "
            f"Source: {s.get('source','')} | "
            + (f"EARLY STAGE: {s.get('deal_stage_hint','')} | " if s.get('is_early_stage') else "")
            + (f"Numbers: {s.get('extracted_numbers', {})}" if s.get('extracted_numbers') else "")
        )
        for i, s in enumerate(signals[:12])
    ])

    tech_context  = tech_result.get("tech_summary", "")
    deal_context  = deal_result.get("valuation_summary", "")

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=RISK_SCREENER_SYSTEM,
        messages=[{
            "role": "user",
            "content": RISK_SCREENER_PROMPT.format(
                signals_text=signals_text,
                tech_context=tech_context,
                deal_context=deal_context
            )
        }]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        last = raw.rfind("}")
        if last > 0:
            try:
                parsed = json.loads(raw[:last+1])
            except Exception:
                pass
    if parsed is None:
        print("  [Agent 3] JSON 파싱 실패 — 빈 결과로 계속")
        parsed = {"risk_assessments": [], "risk_summary": "Unavailable", "macro_risks": {}}
    print(f"  [Agent 3] 완료 — {len(parsed.get('risk_assessments', []))}개 리스크 평가")
    return parsed


# ── Agent 4: Brief Synthesizer ───────────────────────────────────────────────

SYNTHESIZER_SYSTEM = """
You are the GRIDEDGE AI Analyst — Chief Investment Officer.

MISSION: Synthesize Tech Validator, Deal Analyst, Risk Screener outputs into
investment-grade Deal Memos. Every output must be actionable and defensible.

OUTPUT PHILOSOPHY:
- Every claim must have a number behind it
- PASS is not failure. Wrong Yes costs money. Accurate No saves it.
- Institutional voice: precise, no hedging, no vague language
- This memo is read by partners making $50M+ decisions

RECOMMENDATION LEVELS:
LEAD:   High conviction, deploy now, be the lead investor
FOLLOW: Good deal, co-invest, not worth leading
WATCH:  Interesting but key risk unresolved, monitor
PASS:   Risk outweighs return, structural issue, avoid

CONVICTION:
HIGH:   All 3 agents align, strong physical + financial + risk case
MEDIUM: 2 of 3 agents align, one unresolved risk
LOW:    Divergence across agents, significant uncertainty

DEAL MEMO FORMAT (mandatory):
Each deal_signal MUST include ALL these fields (no exceptions):
- recommendation: exactly one of "LEAD" / "FOLLOW" / "WATCH" / "PASS"
- conviction: exactly one of "HIGH" / "MEDIUM" / "LOW"
- trl_score: integer 1-9 from tech_assessments (null if not assessed)
- trl_verdict: "PLAUSIBLE" / "QUESTIONABLE" / "RED_FLAG" / "N/A"
- policy_beta: integer 0-10 from risk_assessments (null if not assessed)
- irr_low: number or null (e.g. 12)
- irr_high: number or null (e.g. 16)
- top_risk: single sentence on biggest risk
- analyst_edge: specific technical or financial insight this analysis reveals (1 sentence with numbers)

RECOMMENDATION DECISION RULES:

FOR EARLY STAGE (Seed/Series A — PRIORITY FOCUS):
LEAD:   Strong technical moat + power systems team + clear AI DC application + TRL≥5
FOLLOW: Interesting technology but team gap OR market timing question
WATCH:  Early but needs pilot data OR regulatory clarity
PASS:   No technical differentiation OR requires project finance from day 1

FOR LATE STAGE / PROJECT FINANCE:
LEAD:   TRL≥9 AND Policy Beta≤3 AND IRR in target range AND hyperscaler offtaker
FOLLOW: TRL≥8 AND reasonable economics AND one unresolved risk
WATCH:  TRL<8 OR Policy Beta≥6 OR interconnection unconfirmed
PASS:   Any RED_FLAG OR IRR below range OR subsidy-only economics

STAGE DETECTION: Classify each deal by stage before applying rules.
Early stage deals with strong team/tech should be rated MORE generously on IRR
(pre-revenue stage = cannot apply project finance IRR framework)

CONVICTION RULES:
HIGH:   All 3 agents agree on assessment
MEDIUM: 2 of 3 agents agree
LOW:    Agents diverge significantly

PRINCIPLES:
1. Physics first. No model beats thermodynamics.
2. Remove subsidies. If it doesn't pencil → PASS.
3. No interconnection → no revenue → PASS.
4. Hyperscaler direct offtake = Tier 1 signal.
5. We don't do "wait and see" without a specific trigger.

=== ANALYTICAL DEPTH STANDARDS ===
Every Deal Memo must answer these questions with specific numbers:
1. IRR impact if long-inference workload hits 15%?
2. Does this BESS have grid-forming? If not, what is the frequency risk?
3. What is the Policy Beta after removing subsidies?
4. How many months does interconnection queue add to COD?
5. Is this technology claim physically possible at this energy density?

=== CONTRARIAN POSITIONS ===
BULLISH signals (underpriced by market):
  Grid-forming BESS near AI DC cluster = scarcity premium
  Operating nuclear with hyperscaler offtake = structural re-rating
  FERC-regulated transco in AI-dense region = compounding demand pull

PASS signals (overpriced by market):
  Any green H2 without post-2027 unsubsidized economics
  Merchant EU BESS without contracted revenue floor
  BESS sized for average AI DC load (ignoring 3-5x peak-to-average)

Output: Pure JSON only. No markdown.
"""

SYNTHESIZER_PROMPT = """
Synthesize the following expert analyses into a premium investment intelligence brief.

=== ORIGINAL SIGNALS ({n} total) ===
{signals_text}

=== AGENT 1: TECHNICAL ASSESSMENTS ===
{tech_json}

=== AGENT 2: DEAL ANALYSIS ===
{deal_json}

=== AGENT 3: RISK ASSESSMENTS ===
{risk_json}

=== PROPRIETARY DATA SIGNALS ===
{proprietary_text}

Today: {date} | Week: {week}

Synthesize into this JSON schema:
{{
  "week": "{week}",
  "headline": "Single most important insight this week (specific, data-driven, 1 line)",
  "thesis": "3 sentences: what happened, why it matters, what to do about it",
  "deal_signals": [
    {{
      "title": "Deal/issue title",
      "tag": "BULLISH | WATCH | RED_FLAG",
      "recommendation": "LEAD | FOLLOW | WATCH | PASS",
      "conviction": "HIGH | MEDIUM | LOW",
      "sector": "BESS | GRID | SOLAR | WIND | SMR | H2 | VPP | AI_DC_POWER | POWER_TECH | OTHER",
      "summary": "2-3 sentences integrating tech + financial + risk perspectives",
      "implication": "1 sentence on IRR/valuation/risk implication with specific numbers",
      "trl_score": null or integer 1-9,
      "trl_verdict": "PLAUSIBLE | QUESTIONABLE | RED_FLAG | N/A",
      "policy_beta": null or integer 0-10,
      "irr_low": null or number,
      "irr_high": null or number,
      "top_risk": "single sentence biggest risk",
      "analyst_edge": "what BEV/Khosla/Lowercarbon would miss that we caught",
      "confidence": "HIGH | MEDIUM | LOW",
      "source": "source name",
      "source_url": "URL if available"
    }}
  ],
  "sector_positioning": [
    {{
      "sector": "sector name",
      "stance": "OVERWEIGHT | NEUTRAL | UNDERWEIGHT",
      "rationale": "2 sentences grounded in this week's data",
      "key_risk": "specific risk with policy beta if applicable",
      "valuation_note": "current multiple range if data available"
    }}
  ],
  "red_flags": [
    {{
      "issue": "red flag title",
      "detail": "why this matters for investment decisions",
      "policy_beta": null or 0-10,
      "source": "source"
    }}
  ],
  "macro_watch": "2 sentences on macro → energy VC dealflow implications",
  "data_note": "3-5 key sources used",
  "agent_chain_summary": "1 sentence on how the 3-agent analysis changed the conclusion vs. single-AI",
  "week_stats": {{
    "avg_trl_score": null or number,
    "trl_distribution": {{"PLAUSIBLE": 0, "QUESTIONABLE": 0, "RED_FLAG": 0}},
    "avg_policy_beta": null or number,
    "irr_range_low": null or number,
    "irr_range_high": null or number,
    "grid_risk_count": 0,
    "top_irr_deal": "title of highest IRR deal this week",
    "top_risk_deal": "title of highest policy beta deal this week"
  }}
}}

OUTPUT REQUIREMENTS:
- Output MINIMUM 20 deal_signals, target 25-35. MORE IS BETTER.
- Include ALL signals where you have source-verifiable data. Do NOT drop signals to be selective.
- PASS signals: include ONLY for physics violations or fraud. Maximum 2 PASS.
- ORDER: LEAD → FOLLOW → WATCH → PASS.
- Early Stage (PRE_SEED/SEED/SERIES_A) always before late stage within same tier.
- Every signal needs deal_stage field.
- 4-6 sector_positioning entries.

ANTI-HALLUCINATION RULES (CRITICAL):
- ONLY output signals for news you actually received in the input data.
- If you cannot find a specific number, company name, or fact in the provided signals — write [UNVERIFIED] tag.
- DO NOT invent deals, funding amounts, company names, or partnerships not present in input.
- If input has 50 signals, output at least 20 of them — do not fabricate extras.
- "Analyst Insight" must be deduced from provided data, not invented.

DEPTH REQUIREMENT:
For each deal_signal, include the specific technical or financial insight that makes this analysis actionable:
- If BESS: detect peak-to-average sizing adequacy
- If AI DC power: token throughput → grid stability implication
- If Nuclear: hyperscaler offtake re-rating vs historical EV/MW
- If H2: explicit post-subsidy economics
- If Grid: interconnection queue → COD probability

The agent_chain_summary field MUST state:
"This week's analysis identified [specific technical/financial insight]: [concrete finding with numbers]"

IMPORTANT: Populate week_stats by aggregating agent assessments:
- avg_trl_score: average of all trl_score values from tech_assessments
- trl_distribution: count PLAUSIBLE/QUESTIONABLE/RED_FLAG verdicts
- avg_policy_beta: average of all policy_beta values from risk_assessments  
- irr_range_low/high: min/max equity_irr_low/high from deal_assessments
- grid_risk_count: count signals with GRID sector or interconnection/transformer risk
- top_irr_deal: title of deal with highest equity_irr_high
- top_risk_deal: title of deal with highest policy_beta
"""


def run_synthesizer(
    signals: list[dict],
    tech_result: dict,
    deal_result: dict,
    risk_result: dict,
    proprietary_text: str,
    week_str: str,
    date_str: str
) -> dict:
    """Agent 4: 최종 브리프 통합"""
    print("  [Agent 4] Brief Synthesizer 실행 중...")

    signals_text = "\n\n".join([
        f"[{i+1}] [{s['sector']}] {s['title']}\n{s['description']}\nURL: {s.get('url','')}"
        for i, s in enumerate(signals[:20])
    ])

    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYNTHESIZER_SYSTEM,
        messages=[{
            "role": "user",
            "content": SYNTHESIZER_PROMPT.format(
                n=len(signals),
                signals_text=signals_text,
                tech_json=json.dumps(tech_result, ensure_ascii=False)[:3000],
                deal_json=json.dumps(deal_result, ensure_ascii=False)[:3000],
                risk_json=json.dumps(risk_result, ensure_ascii=False)[:3000],
                proprietary_text=proprietary_text[:1500] if proprietary_text else "None",
                date=date_str,
                week=week_str,
            )
        }]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    def _repair(s):
        try:
            return json.loads(s)
        except Exception:
            pass
        last = s.rfind("}")
        if last > 100:
            try:
                return json.loads(s[:last+1])
            except Exception:
                pass
        raise ValueError("JSON repair failed")

    try:
        result = _repair(raw)
        sig_count = len(result.get("deal_signals", []))
        print(f"  [Agent 4] 완료 — {sig_count}개 시그널")
        return result
    except Exception as e:
        print(f"  [Agent 4] JSON 파싱 실패: {e}")
        raise


# ── 메인 체인 실행 ────────────────────────────────────────────────────────────

# ── Agent 5: Fact Checker ─────────────────────────────────────────────────────

FACT_CHECKER_SYSTEM = """
You are the GRIDEDGE Fact Checker — a quality gate, NOT a gatekeeper.

MISSION: Flag hallucinations and unsupported claims. But PRESERVE content.
Default bias: KEEP signals, not remove them.

WHAT TO CHECK:

1. NUMBER VERIFICATION
   - Flag numbers that appear invented (no source basis) → FLAGGED with [UNVERIFIED]
   - Do NOT remove signals just because exact numbers can't be confirmed
   - IRR estimates and analyst interpretations are acceptable as analysis

2. COMPANY/TECHNOLOGY CLAIMS
   - REMOVED only if: company name is clearly fabricated or doesn't exist
   - FLAGGED if: specific claim is unverifiable but company is real
   - Do NOT remove real news just because you can't confirm every detail

3. LOGICAL CONSISTENCY
   - Flag LEAD + TRL < 5 combinations
   - Do NOT remove signals for minor inconsistencies

4. SOURCE INTEGRITY
   - Flag signals with zero connection to provided source text → FLAGGED
   - REMOVED only for: clearly invented deals, impossible physics claims

VERDICT OPTIONS:
- VERIFIED: claim is supportable from source text or reasonable analysis
- ADJUSTED: minor correction applied, still publishable  
- FLAGGED: add [UNVERIFIED] tag, keep in brief
- REMOVED: ONLY for clear fabrications or impossible claims

PRESERVATION RULE: If a signal is about a real company doing a real thing,
keep it as VERIFIED or FLAGGED. Only REMOVE pure inventions.
Minimum 15 signals must survive fact-checking.
Output: Pure JSON only.
"""

FACT_CHECKER_PROMPT = """
Review these deal signals for factual accuracy.

ORIGINAL SOURCE SIGNALS (ground truth):
{source_text}

SYNTHESIZED BRIEF SIGNALS TO VERIFY:
{brief_signals}

For each brief signal:
1. If the company and general topic match source material → VERIFIED (even if numbers differ slightly)
2. If specific numbers/claims are unverifiable → FLAGGED with [UNVERIFIED] tag (DO NOT REMOVE)
3. If the entire signal has no connection to any source text → FLAGGED  
4. Only REMOVE if: company name is completely fabricated, or physics are impossible

Be conservative with REMOVED. Prefer FLAGGED over REMOVED.
Target: remove at most 2-3 signals. Flag the rest if uncertain.

Output JSON:
{{
  "verified_signals": [
    {{
      "title": "original signal title",
      "verdict": "VERIFIED | ADJUSTED | FLAGGED | REMOVED",
      "issue": "description of problem if FLAGGED/REMOVED, or null",
      "correction": "corrected text if ADJUSTED, or null",
      "confidence_adjustment": "if conviction should change: HIGH->MEDIUM etc, or null"
    }}
  ],
  "hallucination_count": 0,
  "flagged_count": 0,
  "removed_count": 0,
  "fact_check_summary": "1 sentence summary of overall brief quality"
}}
"""


def run_fact_checker(
    signals: list[dict],
    brief: dict,
    client
) -> dict:
    """
    Agent 5: 브리프 출판 전 팩트체크
    hallucination 탐지 및 수정
    """
    import json as _json

    # 원본 소스 텍스트 준비
    source_text = "\n\n".join([
        f"[SOURCE {i+1}] {s.get('title','')}\n{s.get('description','')}\nURL: {s.get('url','')}"
        for i, s in enumerate(signals[:20])
    ])

    # 브리프 시그널 준비
    brief_signals_text = _json.dumps(
        brief.get("deal_signals", []),
        ensure_ascii=False,
        indent=2
    )[:8000]  # 토큰 제한

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=FACT_CHECKER_SYSTEM,
            messages=[{
                "role": "user",
                "content": FACT_CHECKER_PROMPT.format(
                    source_text=source_text[:4000],
                    brief_signals=brief_signals_text
                )
            }]
        )

        raw = resp.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            result = _json.loads(raw)
        except:
            import re as _re
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            result = _json.loads(match.group()) if match else {}

        # 브리프에 팩트체크 결과 반영
        verified = result.get("verified_signals", [])
        halluc = result.get("hallucination_count", 0)
        flagged = result.get("flagged_count", 0)
        removed = result.get("removed_count", 0)

        print(f"  [Fact Checker] 검증: {len(verified)}개 | 할루시네이션: {halluc}개 | 플래그: {flagged}개 | 제거: {removed}개")

        # 제거/플래그된 시그널 처리
        verdict_map = {v.get("title", "")[:50]: v for v in verified}

        new_signals = []
        for sig in brief.get("deal_signals", []):
            title_key = sig.get("title", "")[:50]
            v = verdict_map.get(title_key, {})
            verdict = v.get("verdict", "VERIFIED")

            if verdict == "REMOVED":
                print(f"  [제거] {sig.get('title','')[:60]}: {v.get('issue','')}")
                continue  # 제거

            if verdict == "FLAGGED":
                sig["title"] = "[UNVERIFIED] " + sig.get("title", "")
                sig["analyst_edge"] = f"⚠️ Fact check flagged: {v.get('issue', 'Unverified claim')}"

            if verdict == "ADJUSTED" and v.get("correction"):
                sig["fact_check_note"] = v.get("correction")

            if v.get("confidence_adjustment"):
                sig["conviction"] = v["confidence_adjustment"].split("->")[-1].strip()

            new_signals.append(sig)

        brief["deal_signals"] = new_signals
        brief["fact_check"] = {
            "hallucination_count": halluc,
            "flagged_count": flagged,
            "removed_count": removed,
            "summary": result.get("fact_check_summary", ""),
            "verified_at": __import__("datetime").datetime.utcnow().isoformat()
        }

        return brief

    except Exception as e:
        print(f"  [Fact Checker] 실패: {e}")
        brief["fact_check"] = {"error": str(e), "status": "skipped"}
        return brief


def run_agent_chain(
    signals: list[dict],
    proprietary_text: str,
    week_str: str,
    date_str: str
) -> dict:
    """
    5개 에이전트 순차 실행 (Agent 5 = Fact Checker)
    각 에이전트 결과가 다음 에이전트의 컨텍스트로 주입됨
    """
    import time
    import anthropic as _anthropic
    client = _anthropic.Anthropic()

    print("\n[에이전트 체인 시작]")
    print("=" * 50)

    # Agent 1
    tech_result = run_tech_validator(signals)
    time.sleep(2)

    # Agent 2 (Agent 1 결과 참조)
    deal_result = run_deal_analyst(signals, tech_result)
    time.sleep(2)

    # Agent 3 (Agent 1+2 결과 참조)
    risk_result = run_risk_screener(signals, tech_result, deal_result)
    time.sleep(2)

    # Agent 4 (Agent 1+2+3 + 독점데이터 통합)
    brief = run_synthesizer(
        signals, tech_result, deal_result, risk_result,
        proprietary_text, week_str, date_str
    )

    # 메타데이터 추가
    brief["agent_chain"] = {
        "tech_assessments_count": len(tech_result.get("tech_assessments", [])),
        "deal_assessments_count": len(deal_result.get("deal_assessments", [])),
        "risk_assessments_count": len(risk_result.get("risk_assessments", [])),
        "tech_summary":   tech_result.get("tech_summary", ""),
        "deal_summary":   deal_result.get("valuation_summary", ""),
        "risk_summary":   risk_result.get("risk_summary", ""),
    }

    # Agent 5 — Fact Checker
    print("  [Agent 5] Fact Checker 실행 중...")
    try:
        brief = run_fact_checker(signals, brief, client)
        fc = brief.get("fact_check", {})
        print(f"  [Agent 5] 완료 — 제거: {fc.get('removed_count',0)}개 | 플래그: {fc.get('flagged_count',0)}개")
    except Exception as e:
        print(f"  [Agent 5] 스킵: {e}")
    time.sleep(1)

    print(f"\n[에이전트 체인 완료]")
    print(f"  기술 평가: {brief['agent_chain']['tech_assessments_count']}개")
    print(f"  딜 평가:   {brief['agent_chain']['deal_assessments_count']}개")
    print(f"  리스크:    {brief['agent_chain']['risk_assessments_count']}개")
    fc = brief.get("fact_check", {})
    if fc:
        print(f"  팩트체크:  제거 {fc.get('removed_count',0)}개 | 플래그 {fc.get('flagged_count',0)}개")
    print("=" * 50)

    return brief

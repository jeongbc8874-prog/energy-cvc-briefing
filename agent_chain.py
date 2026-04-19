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
You are a PhD-level energy technology expert and investment analyst.
Your sole job is to validate the technical feasibility of energy technology claims.

You have deep expertise in:
- Battery electrochemistry (thermodynamic limits, degradation mechanisms)
- Power systems physics (grid stability, frequency response, interconnection)
- Solar PV (Shockley-Queisser limit, degradation, BOS costs)
- Hydrogen production (Faradaic efficiency, electrolyzer stack lifetime)
- Nuclear engineering (neutronics, licensing timelines, cost drivers)
- Wind energy (Betz limit, capacity factors, offshore logistics)

For each technology claim, you MUST:
1. Identify the specific physical/chemical constraint being tested
2. Compare claim against known theoretical and commercial limits
3. Assign TRL score (1-9) with justification
4. Give a PLAUSIBLE / QUESTIONABLE / RED_FLAG verdict
5. Estimate realistic commercialization timeline

Be brutally honest. If a claim defies physics, say so explicitly.
Output: Pure JSON only.
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
        f"[{i+1}] {s['title']}\n{s['description']}\nSector: {s['sector']}"
        for i, s in enumerate(signals[:10])
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
You are a Senior Investment Analyst at a top-tier energy-focused VC/PE fund.
Your sole job is to assess the financial structure and valuation of energy deals.

You have deep expertise in:
- Project finance (IRR, DSCR, LLCR, merchant vs. contracted revenue)
- Energy asset valuation (EV/MW, EV/EBITDA, EV/Revenue multiples by subsector)
- Capital structure (DFI debt, tax equity, sponsor equity, blended cost of capital)
- Exit multiples and liquidity paths for energy assets
- PPA/offtake contract structures and their impact on valuation
- Comparable transaction analysis in energy M&A

For each deal, you MUST:
1. Identify the implied valuation metric ($/kW, EV/EBITDA, etc.)
2. Compare against recent comparable transactions
3. Assess whether the deal is CHEAP / FAIR / EXPENSIVE
4. Estimate realistic equity IRR range
5. Identify key financial risk

Be rigorous. Use specific numbers. No vague language.
Output: Pure JSON only.
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
      "equity_irr_estimate": "X-Y% range or null",
      "revenue_structure": "Contracted | Merchant | Hybrid",
      "capital_structure_note": "key observation about financing",
      "financial_risk": "biggest financial risk",
      "investment_stance": "BULLISH | WATCH | AVOID"
    }}
  ],
  "valuation_summary": "2-3 sentence overall deal market assessment this week",
  "sector_multiples_observed": {{
    "BESS": "observed range if data available",
    "SOLAR": "observed range if data available",
    "GRID": "observed range if data available"
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
You are a Risk Officer at an energy-focused investment fund.
Your sole job is to identify and quantify risks that could impair investment returns.

You specialize in:
- Policy/regulatory risk (subsidy dependency, permitting, grid codes)
- Supply chain risk (concentration, counterparty quality, logistics)
- Technology risk (unproven at scale, IP disputes, key-person)
- Market risk (merchant price exposure, offtaker credit quality)
- Geopolitical risk (trade restrictions, resource nationalism, sanctions)
- ESG/reputational risk (environmental permits, community opposition)

For each signal, compute a Policy Beta score (0-10):
  0-3: Low policy dependency (merchant, private contracts)
  4-6: Moderate (some subsidy but commercially viable without)
  7-10: High (subsidy-dependent, would not pencil without government support)

Be specific about which policy/regulation creates the risk.
Output: Pure JSON only.
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
        f"[{i+1}] {s['title']}\n{s['description']}\nSector: {s['sector']}"
        for i, s in enumerate(signals[:10])
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
You are the Editor-in-Chief of GRIDEDGE Intelligence, a premium energy investment brief.
Your job is to synthesize expert analysis from three specialist agents into a cohesive,
actionable investment intelligence brief.

You receive:
- Technical assessments from a PhD-level technology expert
- Financial/valuation analysis from a senior investment analyst
- Risk assessments from a risk officer

Your output must:
1. Integrate all three perspectives into unified deal signals
2. Produce sector positioning with conviction
3. Highlight the week's most important insight that no competitor has
4. Write in institutional voice — precise, data-driven, no hedging language
5. Every claim must be traceable to the input analysis

The brief is read by energy VC/PE partners making $50M+ investment decisions.
It must be worth $500/month to them. Write accordingly.
Output: Pure JSON only.
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
      "sector": "BESS | GRID | SOLAR | WIND | SMR | H2 | VPP | CCS | EV | OTHER",
      "summary": "2-3 sentences integrating tech + financial + risk perspectives",
      "implication": "1 sentence on IRR/valuation/risk implication with specific numbers",
      "confidence": "HIGH | MEDIUM | LOW",
      "trl_score": extract from tech_assessments or null,
      "trl_verdict": "PLAUSIBLE | QUESTIONABLE | RED_FLAG | N/A",
      "policy_beta": extract from risk_assessments or estimate 0-10,
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
  "agent_chain_summary": "1 sentence on how the 3-agent analysis changed the conclusion vs. single-AI"
}}

Minimum 5 deal_signals, 4-6 sector_positioning. Prioritize signals where all 3 agents agree.
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
        max_tokens=8192,
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

    try:
        result = json.loads(raw)
        print(f"  [Agent 4] 완료 — 브리프 통합 완료")
        return result
    except json.JSONDecodeError:
        last = raw.rfind("}")
        if last > 0:
            return json.loads(raw[:last+1])
        raise


# ── 메인 체인 실행 ────────────────────────────────────────────────────────────

def run_agent_chain(
    signals: list[dict],
    proprietary_text: str,
    week_str: str,
    date_str: str
) -> dict:
    """
    4개 에이전트 순차 실행
    각 에이전트 결과가 다음 에이전트의 컨텍스트로 주입됨
    """
    import time

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

    print(f"\n[에이전트 체인 완료]")
    print(f"  기술 평가: {brief['agent_chain']['tech_assessments_count']}개")
    print(f"  딜 평가:   {brief['agent_chain']['deal_assessments_count']}개")
    print(f"  리스크:    {brief['agent_chain']['risk_assessments_count']}개")
    print("=" * 50)

    return brief

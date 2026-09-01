"""
Mock LLM responses that mirror what a real Gemini call would plausibly
return for the Nimbus Dynamics sample filing. Used across tests and the
demo script so mock-mode output tells a coherent, internally consistent
story instead of empty placeholders.
"""

MOCK_EXTRACTION = {
    "company": "Nimbus Dynamics, Inc.",
    "fiscal_year": "FY2025",
    "revenue_signals": [
        {
            "period": "FY2025",
            "segment": "Consolidated",
            "trend": "decline",
            "yoy_change_pct": -6.3,
            "note": "Total revenue fell to $842M from $898M, driven by Cloud Infrastructure.",
        },
        {
            "period": "FY2025",
            "segment": "Cloud Infrastructure",
            "trend": "decline",
            "yoy_change_pct": -14.0,
            "note": "Largest segment declined as enterprise renewals were delayed.",
        },
        {
            "period": "FY2025",
            "segment": "Managed Services",
            "trend": "growth",
            "yoy_change_pct": 9.0,
            "note": "Partially offset the Cloud Infrastructure decline.",
        },
        {
            "period": "FY2025",
            "segment": "Data Analytics",
            "trend": "growth",
            "yoy_change_pct": 22.0,
            "note": "Fastest-growing but smallest segment at $122M.",
        },
    ],
    "debt_covenants": [
        {
            "covenant_type": "leverage ratio",
            "threshold": "3.5x max",
            "current_status": "compliant",
            "note": "Reported 3.3x vs 3.5x limit - limited headroom given revenue decline.",
        },
        {
            "covenant_type": "interest coverage ratio",
            "threshold": "2.5x min",
            "current_status": "compliant",
            "note": "Reported 2.7x, down from 3.4x prior year - margin of safety shrinking.",
        },
    ],
    "legal_risks": [
        {
            "matter": "FTC Civil Investigative Demand - data retention",
            "severity": "high",
            "potential_exposure": "$15M-$40M (reasonably possible, unaccrued)",
            "note": "Active FTC inquiry into Cloud Infrastructure segment data practices.",
        },
        {
            "matter": "Putative class action - auto-renewal billing",
            "severity": "medium",
            "potential_exposure": None,
            "note": "Early-stage litigation; company disputes claims and exposure is not estimable yet.",
        },
    ],
}

MOCK_EXTRACTION_FY2024 = {
    "company": "Nimbus Dynamics, Inc.",
    "fiscal_year": "FY2024",
    "revenue_signals": [
        {
            "period": "FY2024",
            "segment": "Consolidated",
            "trend": "growth",
            "yoy_change_pct": 11.0,
            "note": "Total revenue grew to $898M from $809M, led by Cloud Infrastructure.",
        },
        {
            "period": "FY2024",
            "segment": "Cloud Infrastructure",
            "trend": "growth",
            "yoy_change_pct": 18.0,
            "note": "Strong enterprise renewal rates drove segment growth to $361M.",
        },
        {
            "period": "FY2024",
            "segment": "Managed Services",
            "trend": "growth",
            "yoy_change_pct": 6.0,
            "note": "Grew to $376M.",
        },
        {
            "period": "FY2024",
            "segment": "Data Analytics",
            "trend": "growth",
            "yoy_change_pct": 40.0,
            "note": "Grew to $100M from a small base.",
        },
    ],
    "debt_covenants": [
        {
            "covenant_type": "leverage ratio",
            "threshold": "3.5x max",
            "current_status": "compliant",
            "note": "Reported 2.9x, comfortably within the covenant limit.",
        },
        {
            "covenant_type": "interest coverage ratio",
            "threshold": "2.5x min",
            "current_status": "compliant",
            "note": "Reported 3.4x, reflecting healthy debt service capacity.",
        },
    ],
    "legal_risks": [],
}

MOCK_COMPARISON = {
    "company": "Nimbus Dynamics, Inc.",
    "prior_fiscal_year": "FY2024",
    "current_fiscal_year": "FY2025",
    "trend_shifts": [
        {
            "metric": "Cloud Infrastructure revenue",
            "prior_period": "FY2024",
            "current_period": "FY2025",
            "prior_value": "+18% YoY ($361M)",
            "current_value": "-14% YoY ($310M)",
            "direction": "deteriorating",
            "materiality": "high",
            "note": "Swung from the fastest-growing segment to the primary driver of consolidated decline.",
        },
        {
            "metric": "Leverage ratio",
            "prior_period": "FY2024",
            "current_period": "FY2025",
            "prior_value": "2.9x",
            "current_value": "3.3x",
            "direction": "deteriorating",
            "materiality": "medium",
            "note": "Headroom against the 3.5x covenant limit narrowed significantly.",
        },
        {
            "metric": "Legal/regulatory risk profile",
            "prior_period": "FY2024",
            "current_period": "FY2025",
            "prior_value": "No material proceedings disclosed",
            "current_value": "Active FTC investigation ($15M-$40M exposure) + class action",
            "direction": "deteriorating",
            "materiality": "high",
            "note": "Company had a clean legal profile a year ago; now has two active matters.",
        },
    ],
    "overall_trajectory": "deteriorating",
    "narrative": (
        "Nimbus Dynamics' trajectory reversed sharply between FY2024 and FY2025. "
        "A year ago the company was growing across all segments with a clean legal "
        "profile and comfortable covenant headroom. In FY2025, its largest segment "
        "swung from double-digit growth to double-digit decline, covenant headroom "
        "compressed, and two legal matters emerged - one involving a federal "
        "investigation. None of these individually breach a covenant or represent "
        "an acute crisis, but the combined direction of travel warrants closer "
        "monitoring than the prior year's filing would have suggested."
    ),
}

MOCK_SYNTHESIS = {
    "company": "Nimbus Dynamics, Inc.",
    "fiscal_year": "FY2025",
    "executive_summary": (
        "Nimbus Dynamics posted a 6.3% consolidated revenue decline in FY2025, "
        "concentrated in its largest segment (Cloud Infrastructure, -14%), partially "
        "offset by growth in Managed Services and Data Analytics. Leverage and "
        "interest coverage covenants remain technically compliant but with "
        "meaningfully reduced headroom versus the prior year. An active FTC "
        "inquiry into data retention practices represents the most material "
        "near-term contingent liability."
    ),
    "top_risks": [
        {
            "category": "legal",
            "severity": "high",
            "headline": "Active FTC investigation into data retention practices",
            "detail": "Reasonably possible loss of $15M-$40M, unaccrued; outcome and timeline uncertain.",
        },
        {
            "category": "revenue",
            "severity": "medium",
            "headline": "Core segment revenue decline eroding covenant headroom",
            "detail": (
                "Cloud Infrastructure -14% YoY is the primary driver of both "
                "revenue decline and reduced covenant cushion."
            ),
        },
        {
            "category": "debt",
            "severity": "medium",
            "headline": "Shrinking interest coverage margin",
            "detail": (
                "Interest coverage fell from 3.4x to 2.7x YoY against a 2.5x minimum - "
                "a continued decline of similar magnitude would breach the covenant."
            ),
        },
    ],
    "recommendation": (
        "Proceed with continued monitoring rather than immediate action. The FTC "
        "inquiry and shrinking covenant headroom warrant a quarterly re-review "
        "trigger rather than a full re-underwriting today; any further decline in "
        "Cloud Infrastructure revenue or an adverse FTC outcome should prompt "
        "immediate reassessment of credit terms or investment thesis."
    ),
    "confidence_score": 0.78,
}

# A "clean" scenario (no active legal risk, stable covenants) for testing the
# auto-approval path - contrast with MOCK_SYNTHESIS above, which deliberately
# has a lower confidence score given genuine uncertainty (an active FTC
# investigation with an unaccrued, unresolved contingent liability).
MOCK_SYNTHESIS_HIGH_CONFIDENCE = {
    "company": "Nimbus Dynamics, Inc.",
    "fiscal_year": "FY2024",
    "executive_summary": (
        "Nimbus Dynamics posted solid FY2024 results: 5.1% consolidated revenue "
        "growth, comfortable covenant headroom (2.9x leverage vs. 3.5x limit), and "
        "no material legal proceedings outside the ordinary course of business."
    ),
    "top_risks": [],
    "recommendation": ("No immediate action required. Continue standard quarterly monitoring."),
    "confidence_score": 0.95,
}

# --- Portfolio Intelligence fixtures: two contrasting companies alongside
# Nimbus Dynamics, for a meaningful cross-company ranking demo. ---

MOCK_EXTRACTION_SOLARA = {
    "company": "Solara Energy Corp",
    "fiscal_year": "FY2025",
    "revenue_signals": [
        {
            "period": "FY2025",
            "segment": "Consolidated",
            "trend": "growth",
            "yoy_change_pct": 28.0,
            "note": "Revenue grew to $1.24B from $969M, led by Utility-Scale Solar.",
        },
        {
            "period": "FY2025",
            "segment": "Utility-Scale Solar",
            "trend": "growth",
            "yoy_change_pct": 34.0,
            "note": "Largest segment, accelerating demand for grid-scale renewable capacity.",
        },
        {
            "period": "FY2025",
            "segment": "Residential Solar",
            "trend": "growth",
            "yoy_change_pct": 19.0,
            "note": "Steady growth in residential installations.",
        },
        {
            "period": "FY2025",
            "segment": "Storage Systems",
            "trend": "growth",
            "yoy_change_pct": 22.0,
            "note": "Growing attach rate of storage with solar installations.",
        },
    ],
    "debt_covenants": [
        {
            "covenant_type": "leverage ratio",
            "threshold": "3.0x max",
            "current_status": "compliant",
            "note": "Reported 1.8x vs 3.0x limit - substantial headroom.",
        },
        {
            "covenant_type": "interest coverage ratio",
            "threshold": "3.0x min",
            "current_status": "compliant",
            "note": "Reported 5.2x, up from 4.1x prior year - improving margin of safety.",
        },
    ],
    "legal_risks": [],
}

MOCK_EXTRACTION_VANTAGE = {
    "company": "Vantage Robotics, Inc.",
    "fiscal_year": "FY2025",
    "revenue_signals": [
        {
            "period": "FY2025",
            "segment": "Consolidated",
            "trend": "decline",
            "yoy_change_pct": -11.0,
            "note": "Revenue fell to $412M from $463M, driven by Industrial Automation.",
        },
        {
            "period": "FY2025",
            "segment": "Industrial Automation",
            "trend": "decline",
            "yoy_change_pct": -19.0,
            "note": "Largest segment declined amid reduced manufacturing capex.",
        },
        {
            "period": "FY2025",
            "segment": "Service & Maintenance",
            "trend": "growth",
            "yoy_change_pct": 4.0,
            "note": "Modest growth, partially offsetting the decline.",
        },
    ],
    "debt_covenants": [
        {
            "covenant_type": "leverage ratio",
            "threshold": "4.0x max",
            "current_status": "breached",
            "note": "Reported 4.3x vs 4.0x limit - in breach, temporary lender waiver obtained.",
        },
        {
            "covenant_type": "interest coverage ratio",
            "threshold": "2.0x min",
            "current_status": "breached",
            "note": "Reported 1.6x vs 2.0x minimum - also below required level, same waiver.",
        },
    ],
    "legal_risks": [
        {
            "matter": "Breach-of-contract action - automation equipment delivery",
            "severity": "medium",
            "potential_exposure": "$18M sought by plaintiff",
            "note": "Company disputes claims; no reasonable loss estimate available yet.",
        },
    ],
}

MOCK_PORTFOLIO_NARRATIVE = (
    "Solara Energy leads the portfolio on growth (+28% YoY) with ample covenant "
    "headroom, reflecting strong secular demand for utility-scale renewables. "
    "Nimbus Dynamics shows moderate risk concentrated in an unresolved FTC "
    "inquiry, with revenue pressure eroding covenant cushion. Vantage Robotics "
    "is the clear outlier on downside risk: a covenant breach under lender "
    "waiver, declining revenue, and active litigation together suggest closer "
    "monitoring or a credit-committee review before any further exposure."
)

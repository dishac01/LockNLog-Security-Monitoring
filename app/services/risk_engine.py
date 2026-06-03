from __future__ import annotations

SEVERITY_WEIGHTS = {
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "critical": 1.0,
}


def severity_weight(severity: str | None) -> float:
    if not severity:
        return 0.5
    return SEVERITY_WEIGHTS.get(str(severity).lower(), 0.5)


def normalize_business_value(business_value: float | None) -> float:
    if business_value is None:
        return 0.5
    v = float(business_value)
    return max(0.0, min(1.0, v / 100.0))


def compute_risk_score(
    anomaly_score: float,
    business_value: float | None,
    severity: str | None,
) -> tuple[float, str]:
    """
    risk_score = anomaly_score + normalized_business_value + severity_weight
    Each component is normalised to [0, 1]; max total = 3.0
    """
    a = max(0.0, float(anomaly_score))
    bv = normalize_business_value(business_value)
    sw = severity_weight(severity)

    # Simple additive sum as requested
    risk = a + bv + sw
    risk = max(0.0, min(3.0, risk))  # cap at 3.0

    band = assign_risk_band(risk)
    return risk, band


def assign_risk_band(risk_score: float) -> str:
    # Adjust thresholds since max score is now potentially 3.0 instead of 1.0
    if risk_score < 0.75:
        return "LOW"
    if risk_score < 1.5:
        return "MEDIUM"
    if risk_score < 2.25:
        return "HIGH"
    return "CRITICAL"




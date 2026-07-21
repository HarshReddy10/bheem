"""Confidence thresholds and evaluation logic."""

class ConfidenceThresholds:
    """Thresholds for lead field statuses."""
    CONFIRMED = 0.90
    PARTIALLY_KNOWN = 0.50

def determine_status(confidence: float) -> str:
    """Determine the status of a field based on its confidence score."""
    if confidence >= ConfidenceThresholds.CONFIRMED:
        return "confirmed"
    if confidence >= ConfidenceThresholds.PARTIALLY_KNOWN:
        return "partially_known"
    return "unknown"

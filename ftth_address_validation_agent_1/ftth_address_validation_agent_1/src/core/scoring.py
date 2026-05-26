from src.models.schemas import ProviderResult, ComparisonResult


def score_provider_result(result: ProviderResult) -> int:
    score = 0
    if result.dpv_match == "Y": score += 40
    elif result.dpv_match in {"S", "D"}: score += 20
    if result.zip_plus_4 and "-" in str(result.zip_plus_4): score += 20
    if result.geocode_precision and str(result.geocode_precision).upper() in {"ROOFTOP", "ZIP9", "PREMISE"}: score += 15
    if result.unit_detected: score += 10
    if result.vacant is False or result.vacant is None: score += 10
    if result.lacs_status in {None, "", "N"}: score += 5
    return min(score, 100)


def choose_result(smarty: ProviderResult, melissa: ProviderResult, comparison: ComparisonResult):
    smarty_score = score_provider_result(smarty)
    melissa_score = score_provider_result(melissa)
    if comparison.better_provider == "smarty":
        chosen, score = smarty, smarty_score
    elif comparison.better_provider == "melissa":
        chosen, score = melissa, melissa_score
    else:
        if smarty_score >= melissa_score:
            chosen, score = smarty, smarty_score
        else:
            chosen, score = melissa, melissa_score
    if comparison.conflict_level == "AGREE":
        score = min(100, score + 5)
    elif comparison.conflict_level == "MAJOR_CONFLICT":
        score = max(0, score - 20)
    return chosen, score


def structure_hint(result: ProviderResult, raw_address: str) -> str:
    text = raw_address.upper()
    if any(tok in text for tok in [" APT ", " UNIT ", " STE ", " SUITE ", " BLDG ", "#"]):
        return "MDU_OR_MXU_HINT"
    if result.record_type and str(result.record_type).upper() in {"H", "HIGHRISE", "M"}:
        return "MDU_HINT"
    if result.record_type and str(result.record_type).upper() in {"F", "BUSINESS", "FIRM"}:
        return "ANCHOR_OR_MXU_HINT"
    return "SFU_HINT"


def validation_status(score, chosen, comparison):
    
    # Handle comparison failure safely
    if comparison is None:

        if chosen and chosen.success:

            return "AUTO_ACCEPT", None

        return "REJECT", "Both providers failed"

    # Existing logic
    if score >= 90:

        return "AUTO_ACCEPT", None

    elif score >= 70:

        return "MANUAL_REVIEW", (
            f"{comparison.conflict_level}: "
            f"{comparison.reason}"
        )

    else:

        return "REJECT", (
            f"{comparison.conflict_level}: "
            f"{comparison.reason}"
        )

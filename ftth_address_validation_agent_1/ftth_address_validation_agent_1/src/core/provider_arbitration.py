from src.core.compare import compare_results


def is_smarty_valid(smarty):

    return (
        smarty is not None
        and smarty.success
        and smarty.dpv_match == "Y"
    )


def is_melissa_valid(melissa):

    return (
        melissa is not None
        and melissa.success
        and melissa.dpv_match is not None
    )


def provider_arbitration(
    smarty,
    melissa
):

    smarty_valid = is_smarty_valid(smarty)

    melissa_valid = is_melissa_valid(melissa)

    # CASE 1
    if smarty_valid and not melissa_valid:

        return smarty, 90

    # CASE 2
    elif melissa_valid and not smarty_valid:

        return melissa, 85

    # CASE 3
    elif smarty_valid and melissa_valid:

        comparison = compare_results(
            smarty,
            melissa
        )

        if comparison.conflict_level == "NO_CONFLICT":
            return smarty, 95

        elif comparison.conflict_level == "MINOR_CONFLICT":
            return smarty, 80

        else:
            return smarty, 60

    # CASE 4
    else:

        return smarty, 20
"""Safe presentation of results reconstructed from ratio-scale intervals."""

import math
from decimal import Decimal, localcontext

from ._core import level_text


def _ratio_strings(log_values, ratios, changes):
    """Round ratios without hiding their ordering or their side of one.

    Even a nonzero log ratio can exponentiate to exactly 1 in binary64. For
    extremely small changes use 1 +/- expm1(x), rather than claiming exactly
    one or forcing spurious extra digits on the other interval endpoints.
    """
    for digits in range(4, 18):
        texts, keys = [], []
        # The smallest binary64 increment may be ~1e-324; decimal keys let
        # even an expression like 1 + 5e-324 remain distinguishable from 1.
        with localcontext() as ctx:
            ctx.prec = 350
            for x, ratio, change in zip(log_values, ratios, changes):
                if x != 0.0 and (ratio == 1.0 or abs(change) < 1e-12):
                    offset = format(abs(change), f".{digits}g")
                    texts.append(f"1 {'+' if x > 0 else '-'} {offset}")
                    value = Decimal(1) + (Decimal(offset) if x > 0 else -Decimal(offset))
                else:
                    text = format(ratio, f".{digits}g")
                    texts.append(text)
                    value = Decimal(text)
                keys.append(value)
                if value <= 0 or (x > 0 and value <= 1) or (x < 0 and value >= 1):
                    break
                # Near one, accuracy of the change matters much more than
                # relative accuracy of the ratio itself. Otherwise 0.99995
                # could be printed as 0.9999 while the percent says -0.005%.
                exact_change = Decimal.from_float(change)
                if abs((value - 1) - exact_change) > Decimal("0.005") * abs(exact_change):
                    break
            else:
                if all((log_values[i] < log_values[j] and keys[i] < keys[j])
                       or (log_values[i] > log_values[j] and keys[i] > keys[j])
                       or (log_values[i] == log_values[j] and keys[i] == keys[j])
                       for i in range(len(keys)) for j in range(i)):
                    return texts
    return None


def _percentage_strings(log_values, percentages):
    """Retain signs, ordering and the open -100% boundary when rounding."""
    def valid(texts, check_accuracy=False):
        values = [float(text) for text in texts]
        for x, exact, shown in zip(log_values, percentages, values):
            if (not math.isfinite(shown) or (x > 0 and shown <= 0)
                    or (x < 0 and not -100 < shown < 0) or (x == 0 and shown != 0)):
                return False
            # One decimal is familiar for ordinary changes, but not when it
            # would discard more than half a percent of a small change.
            if check_accuracy and abs(shown - exact) > 0.005 * abs(exact):
                return False
        return all((log_values[i] < log_values[j] and values[i] < values[j])
                   or (log_values[i] > log_values[j] and values[i] > values[j])
                   or (log_values[i] == log_values[j] and values[i] == values[j])
                   for i in range(len(values)) for j in range(i))

    if all(abs(value) < 1e8 for value in percentages):
        texts = [format(value, "+.1f") for value in percentages]
        if valid(texts, check_accuracy=True):
            return texts
    for digits in range(4, 18):
        texts = [format(value, f"+.{digits}g") for value in percentages]
        if valid(texts):
            return texts
    return None


def ratio_scale_note(estimate, interval, level):
    """Format the reconstructed ratio and percent, or retain the log result.

    Nothing here modifies evidence or adds non-finite numbers to the report.
    ``expm1`` retains small changes which would vanish in ``exp(x) - 1``.
    """
    log_values = (estimate, *interval)
    context = ("The estimate is reconstructed from the input interval on the log scale; "
               "any displayed ratio-scale values are rounded, and the comparison order is as supplied. "
               "The relative change is in the quantity compared by the ratio "
               "(for example, odds rather than risk for an odds ratio).")
    fallback = (
        f"On the ratio scale: the reconstructed estimate or {level_text(level)} CI cannot be "
        "safely displayed with floating-point range or precision, so the ratio and percentage "
        "summary is omitted. The estimate and interval remain available on the log scale in "
        "evidence (estimate and zero_test.interval). For a log value x, the ratio is exp(x) "
        "and the relative change is expm1(x); multiply the latter by 100 for percent. "
        "These conversions may require greater range or precision. " + context
    )
    try:
        ratios = [math.exp(x) for x in log_values]
        changes = [math.expm1(x) for x in log_values]
        percentages = [change * 100 for change in changes]
    except OverflowError:
        return fallback
    if (not all(math.isfinite(r) and r > 0 for r in ratios)
            or not all(math.isfinite(p) for p in percentages)):
        return fallback
    ratios_text = _ratio_strings(log_values, ratios, changes)
    percents_text = _percentage_strings(log_values, percentages)
    if ratios_text is None or percents_text is None:
        return fallback
    mid, lo, hi = ratios_text
    mid_pct, lo_pct, hi_pct = percents_text
    return (f"On the ratio scale: {mid} ({level_text(level)} CI {lo} to {hi}), a relative change of "
            f"{mid_pct}% ({lo_pct}% to {hi_pct}%). " + context)

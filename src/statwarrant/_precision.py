"""Conservative checks at boundaries that convert numeric inputs to float."""

import math
from decimal import Decimal, InvalidOperation
from numbers import Integral, Rational

import numpy as np


def checked_float(value, name):
    """Convert to float without silently narrowing an exact integral input.

    Fractional inputs may undergo the ordinary rounding inherent in binary64.
    A float that was rounded before reaching this function cannot be recovered.
    """
    if type(value) is float:
        return value
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} is too large to represent as a finite float; rescale the inputs") from exc

    # Decimal strings have long been accepted by explicit numeric inputs. Treat
    # integral strings like their Decimal equivalents, without requiring exact
    # representation of ordinary non-integral decimal values.
    original = value
    if isinstance(original, np.ndarray) and original.size == 1:
        original = original.item()
    if isinstance(value, str):
        try:
            original = Decimal(value)
        except InvalidOperation:
            return result  # float() above remains the authority on accepted syntax

    if isinstance(original, Integral):
        exact_integer = int(original)
    elif isinstance(original, Decimal):
        if not original.is_finite():
            return result
        if not math.isfinite(result):
            raise ValueError(f"{name} is too large to represent as a finite float; rescale the inputs")
        if original == original.to_integral_value() and original != Decimal.from_float(result):
            raise ValueError(f"{name} is an integer that cannot be represented exactly as a float; rescale the inputs")
        return result
    elif isinstance(original, Rational):
        if original.denominator != 1:
            return result
        exact_integer = original.numerator
    elif isinstance(original, np.floating):
        if not np.isfinite(original):
            return result
        if not math.isfinite(result):
            raise ValueError(f"{name} is too large to represent as a finite float; rescale the inputs")
        if original != np.trunc(original):
            return result
        exact_integer = int(original)
    else:
        return result

    if not math.isfinite(result) or int(result) != exact_integer:
        raise ValueError(f"{name} is an integer that cannot be represented exactly as a float; rescale the inputs")
    return result

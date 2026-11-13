"""Design sensitivity at extreme values: values stay finite or are refused, and reports export.

Reproduces a review finding: a design table with an assumed effect tiny relative to the SE
produced an infinite exaggeration ratio, and the JSON report could not be exported.
"""

import json
import math
import warnings

import pytest
from scipy import integrate, stats

import statwarrant as sw
from statwarrant.design import design_point


@pytest.mark.parametrize("effect,se", [(1.0, 1.7e308), (5e-324, 1.0)])
def test_unrepresentable_exaggeration_ratio_is_refused(effect, se):
    with pytest.raises(ValueError, match="too small relative to the standard error"):
        design_point(effect, se)


def test_tiny_assumed_effect_no_longer_breaks_export():
    res = sw.declare().analyze(estimate=1.0, se=1.0)
    with pytest.raises(ValueError, match="too small relative"):
        res.design([5e-324, 0.5], source="test")
    json.loads(res.to_json())


@pytest.mark.parametrize("effect,se", [(1.7e308, 1.0), (1.0, 1e-300), (1.7e308, 5e-324), (1e308, 1e308)])
def test_extreme_design_values_stay_finite(effect, se):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p = design_point(effect, se)
    assert all(math.isfinite(v) for v in (p.power, p.type_s, p.exaggeration))


def test_huge_exaggeration_ratio_exports_compactly():
    res = sw.declare().analyze(estimate=1.0, se=1.0)
    table = res.design([1e-300, 0.0, 0.5], source="test")
    d = json.loads(res.to_json())
    assert d["design"]["points"][0]["exaggeration_ratio"] > 1e299
    assert "2.34e+300" in table.to_markdown() and "| undefined | undefined |" in table.to_markdown()
    assert max(len(line) for line in str(res).splitlines()) < 400


@pytest.mark.parametrize("effect,se", [(2.0, 1.0), (-0.3, 0.2), (0.05, 1.0), (2.8, 1.0)])
def test_design_values_match_numerical_integration(effect, se):
    c = stats.norm.isf(0.025) * se
    pdf = stats.norm(effect, se).pdf
    power = stats.norm(effect, se).sf(c) + stats.norm(effect, se).cdf(-c)
    wrong = stats.norm(effect, se).cdf(-c) if effect > 0 else stats.norm(effect, se).sf(c)
    lo, hi = effect - 40 * se, effect + 40 * se
    mean_abs = (integrate.quad(lambda x: x * pdf(x), c, max(hi, c), epsabs=0, epsrel=1e-12)[0]
                - integrate.quad(lambda x: x * pdf(x), min(lo, -c), -c, epsabs=0, epsrel=1e-12)[0])
    p = design_point(effect, se)
    assert p.power == pytest.approx(power, rel=1e-9)
    assert p.type_s == pytest.approx(wrong / power, rel=1e-9)
    assert p.exaggeration == pytest.approx(mean_abs / power / abs(effect), rel=1e-8)


def test_gelman_carlin_worked_example():
    # Gelman & Carlin (2014): true effect 2.8 with SE 1 gives power 0.80, Type S 1.2e-6, exaggeration about 1.12
    p = design_point(2.8, 1.0)
    assert p.power == pytest.approx(0.80, abs=0.005)
    assert p.type_s == pytest.approx(1.2e-6, rel=0.05)
    assert p.exaggeration == pytest.approx(1.12, abs=0.01)

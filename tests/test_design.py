import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant.design import design_point, design_table


def simulate(A, se, alpha=0.05, n=1_000_000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(A, se, n)
    sig = np.abs(x) > stats.norm.ppf(1 - alpha / 2) * se
    power = sig.mean()
    wrong = (np.sign(x[sig]) != np.sign(A)).mean()
    return power, wrong, np.abs(x[sig]).mean() / abs(A)


@pytest.mark.parametrize("A", [0.1, 0.2, 0.3, -0.15, 0.05])
def test_closed_form_matches_simulation(A):
    se = 0.1
    p = design_point(A, se)
    power, wrong, ratio = simulate(A, se)
    assert p.power == pytest.approx(power, abs=0.003)
    assert p.type_s == pytest.approx(wrong, abs=0.003)
    assert p.exaggeration == pytest.approx(ratio, rel=0.01)


def test_reference_values_in_report():
    # values quoted in the project report (SE = 0.1, alpha = 0.05)
    assert design_point(0.1, 0.1).power == pytest.approx(0.170, abs=1e-3)
    assert design_point(0.1, 0.1).exaggeration == pytest.approx(2.49, abs=0.01)
    assert design_point(0.2, 0.1).power == pytest.approx(0.516, abs=1e-3)
    assert design_point(0.3, 0.1).power == pytest.approx(0.851, abs=1e-3)


def test_zero_effect_is_undefined_not_half():
    p = design_point(0.0, 0.1)
    assert p.power == pytest.approx(0.05)
    assert p.type_s is None and p.exaggeration is None
    assert "undefined" in p.sentence(0.1, 0.05)


def test_symmetry_in_sign():
    a, b = design_point(0.17, 0.1), design_point(-0.17, 0.1)
    assert a.power == pytest.approx(b.power)
    assert a.type_s == pytest.approx(b.type_s)
    assert a.exaggeration == pytest.approx(b.exaggeration)


def test_table_requires_range_and_source():
    with pytest.raises(ValueError, match="at least two"):
        design_table([0.2], 0.1, 0.05, "prior study")
    with pytest.raises(ValueError, match="come from"):
        design_table([0.1, 0.2], 0.1, 0.05, "")


def test_warns_when_assumed_equals_observed():
    res = sw.declare().analyze(estimate=0.2, se=0.1)
    table = res.design([0.2, 0.3], source="this study")
    assert any("observed estimate" in w for w in table.warnings)
    assert "design" in res.to_dict()

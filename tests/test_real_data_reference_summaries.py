"""Regression tests using fixed real-data summaries and independent t-tail references.

These cases exercise inference FROM fixed estimates/SE/df; they do not refit the
underlying data. SESOIs are illustrative, not clinical/biological standards.
NIST certifies coefficients and SEs for Norris/Pontius, not derived p-values here.
The independent t-tail reference was calculated with mpmath's incomplete beta.
See the dataset sources below and check model assumptions before interpretation.
"""
import pytest
import statwarrant as sw


# id, estimate, SE, df, illustrative SESOI, independent p-zero,
# independent 95% CI, differs from zero, TOST established, MET established.
CASES = [
    # https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Norris.shtml
    ("NIST Norris slope", 1.00211681802045, 0.000429796848199937, 34, 0.1,
     4.654040852472409e-90, (1.001243365735578, 1.002990270305331), True, False, True),
    # https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Pontius.shtml
    ("NIST Pontius quadratic coefficient", -3.1608187134502924e-15, 4.8665284999203585e-17, 37, 1e-15,
     9.835633727948689e-40, (-3.2594239471268425e-15, -3.0622134797737423e-15), True, False, True),
    # https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/PlantGrowth.html
    ("PlantGrowth trt1 minus ctrl", -0.371, 0.3114348514002032, 16.5235850568593, 0.5,
     0.25038250858754824, (-1.0295162213468108, 0.28751622134681076), False, False, False),
    # https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/iris.html
    ("Iris versicolor minus virginica", -1.292, 0.10250893440404626, 95.57043500645413, 1.0,
     4.900287527398179e-22, (-1.495490299194289, -1.0885097008057107), True, False, True),
    # https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/ChickWeight.html
    ("ChickWeight Diet 1 day 2 minus day 0", 5.85, 0.8952359289154187, 19, 4.0,
     2.9401640812085356e-06, (3.976249666409461, 7.723750333590539), True, False, False),
]


@pytest.mark.parametrize("name,estimate,se,df,sesoi,p,ci,differs,equivalent,exceeds", CASES)
def test_real_data_reference_summaries(name, estimate, se, df, sesoi, p, ci, differs, equivalent, exceeds):
    plan = sw.declare(sesoi=sesoi, sesoi_source="illustrative, not a domain standard",
                      interval_policy="standard")
    ev = plan.analyze(estimate=estimate, se=se, df=df).evidence
    # A default absolute tolerance would make tests for tiny p or coefficients vacuous.
    assert ev.p_zero == pytest.approx(p, rel=1e-9, abs=1e-300), name
    assert ev.zero_interval == pytest.approx(ci, rel=1e-9, abs=0), name
    assert (ev.differs_from_zero, ev.equivalent, ev.exceeds_sesoi) == (differs, equivalent, exceeds), name

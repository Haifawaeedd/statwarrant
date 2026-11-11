"""statwarrant quick start: run with `python examples/quickstart.py`."""

import numpy as np
from scipy import stats

import statwarrant as sw

# 1. Declare the rules before looking at the result.
plan = sw.declare(
    sesoi=3,  # smallest effect size of interest: +/- 3 exam points
    sesoi_source="smallest score gain teachers said would change their practice",
    units="points",
    scope="first-year students, one university, one term",
)

# 2. Analyse. Here: a two-group comparison run with scipy.
rng = np.random.default_rng(7)
new_method = rng.normal(64, 6, 30)
old_method = rng.normal(60, 6, 30)
res = plan.analyze(stats.ttest_ind(new_method, old_method))

print(res.to_markdown())
print()

# 3. Check sentences before you write them.
for sentence in [
    "The new method significantly improved scores.",
    "The new method produced a large improvement.",
    "The new method works for all students.",
    "There is no difference between the methods.",
]:
    print(res.check(sentence))
    print()

# 4. How does this design behave under plausible true effects?
print(res.design([2, 3, 5], source="effects reported in two earlier studies of the method"))

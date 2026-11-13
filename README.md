# statwarrant

**What your statistical result warrants you to say.**

[![tests](https://github.com/Haifawaeedd/statwarrant/actions/workflows/tests.yml/badge.svg)](https://github.com/Haifawaeedd/statwarrant/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`statwarrant` turns an estimate and its uncertainty into a **claim contract**: the
statements your result supports, the statements it does not, and the reason for
each. It shows how the conclusion changes for every possible threshold of practical
importance, and it can flag common misreadings in a sentence you are about to write.

> **Status: experimental alpha.** The statistics follow published methods and are tested
> against SciPy and statsmodels, but the package has not been independently validated,
> and the sentence linter's accuracy has not been measured. Use it as an aid to careful
> reporting, not as a validator, and check its output. Reports of wrong results are very welcome.

> **0.5.0 — public trial.** Please try it on your own results and tell us where it is
> wrong. The sentence checker is pattern-based and partial: a **conflict** contradicts the
> result; **not verified** lists parts it could not check, for you to review; no warning
> is never an approval. Always check group order, outcome, contrast and the complete
> sentence yourself. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

**Try it** in the [quick-start notebook on Colab](https://colab.research.google.com/github/Haifawaeedd/statwarrant/blob/main/examples/quickstart.ipynb)
(nothing to install). **Found a sentence the checker judged wrongly?**
[Report it](https://github.com/Haifawaeedd/statwarrant/issues/new?template=linter.yml); this is
the most useful feedback. Reports are public: do not paste confidential or unpublished text.

It does not invent new statistics. It combines established methods (tests of
difference, equivalence and minimal effect; design analysis) into one consistent
reading, and aims to flag claims the data cannot carry.

```python
import statwarrant as sw

plan = sw.declare(
    sesoi=3, sesoi_source="smallest score gain teachers act on",
    units="points", scope="first-year students, one university, one term",
    outcome="exam score", contrast="new method minus existing method",
)
res = plan.analyze(estimate=4.2, se=1.6, df=58)   # or a scipy / statsmodels result

print(res)
```

```text
The effect is positive (95% CI [0.997, 7.4] (endpoints rounded for display)); whether it reaches the smallest effect size of interest (3 points) is not determined by these data. Scope: first-year students, one university, one term.
Do not say: "There is no effect."; "The effect is practically important."; "The two conditions are equivalent."; "The effect generalizes to all settings."; "The results prove the effect is exactly the estimated value."
Every threshold: an effect beyond ±d for any d below 0.9972 points; equivalence within ±d for any d above 7.403 points; neither from 0.9972520253676211 to 7.402747974632379 (exact cut-offs).
```

The result is statistically significant (p = 0.011), yet the declared 3-point threshold
is neither reached nor ruled out. The last line answers the question "what if someone
uses a different threshold?" for every threshold at once.

```python
print(res.check("The new method improved scores by about 4 points and is safe for all students."))
```

```text
[1 conflict, 2 to verify] The new method improved scores by about 4 points and is safe for all students.
  Conflicts with the result:
  - generalization         "for all": An average effect does not show that every individual or
    case is affected, and the evidence comes from 'first-year students, one university, one
    term' only.
    Check: Limit the claim to the declared scope and to the average effect.
  Not verified (statwarrant could not check these; review them by hand):
  - direction              "improved": The direction's relationship to the declared contrast,
    compared groups or time points and their order could not be verified. Check the wording
    and contrast by hand.
  - magnitude              "by about 4 … points": Not checked against the result: this size
    depends on which way the comparison runs, and the wording could not be tied to the
    declared contrast (new method minus existing method). Check it by hand.
  Not checked: "The new method", "scores", "and is safe", "students".
  Unit checking is pattern-based and partial: a limited set of simple units adjacent to a
  recognised effect or estimate are compared. Other units and conversions may be unchecked;
  verify them by hand.
  A warning is a prompt for review, not proof that the sentence is false.
```

The checker only warns; it never approves a sentence. A **conflict** contradicts the
result. **Not verified** lists parts it recognised but could not check, for you to review.
"Is safe" was not checked at all, and the output says so.

## Why

* Between 76% and 85% of psychology articles (2009 to 2021) that discussed a
  non-significant finding read it as evidence that the effect is absent
  (Murphy et al., 2025).
* Language models summarising research overgeneralise conclusions; in one study
  of 10 models, summaries were about five times more likely than human-written ones
  to broaden the scope of a finding (Peters & Chin-Yee, 2025).
* The computations to prevent these mistakes exist, but in Python they are spread
  over several packages, and we know of none that checks the sentences you write
  against the result. (In R, TOSTER already describes equivalence results in plain
  language; see [Related tools](#related-tools).)

## What it does

| Feature | What you get |
| --- | --- |
| Declare first | The smallest effect size of interest (SESOI) needs a stated reason. The plan has a fingerprint you can register before analysis. Without a SESOI, claims about importance and equivalence are withheld. |
| Three tests, one reading | Difference from zero, equivalence (TOST) and minimal effect (MET), read from intervals. |
| Claim contract | Allowed statements with numbers filled in, and a list of blocked statements with reasons. |
| Every threshold at once | Two numbers give the decision for every symmetric threshold: below one, the effect exceeds it; above the other, equivalence holds; in between, neither. |
| Report with provenance | Outcome, contrast, scope, the declared threshold and its reason, the plan fingerprint and registration link, and a list of what statwarrant does not verify. Versioned JSON and a Markdown report. |
| Sentence linter (warnings only) | `res.check("...")` flags possible misreadings in an English sentence, with the exact words, a rule id and what to check. Numbers are read by role (estimate, interval, standard error, threshold) and sign, intervals as ordered pairs; a number whose role is unclear is flagged, not passed. It never approves a sentence and lists the text it did not check. Checked sentences are kept in the report. |
| Level-conflict detection | Under the TOSTER-style policy, flags when equivalence rests on the 90% interval while the 95% interval reaches outside the bounds. |
| Input checks | Adapters check the original statistic and p-value, with limitations for extremely small p-values; see known issues. |
| Design sensitivity | Power, Type S and exaggeration ratio under assumed effects, with the source of each assumption required. |
| Scope | The linter can warn about some generalizations; it does not verify the stated scope or catch every overgeneralization. |
| Absolute and relative | With a `baseline`, both changes are reported side by side. A ratio (`ratio=True`) is reported as a relative change on the ratio scale; a baseline cannot be combined with a ratio or log-scale result. |
| Common inputs | scipy t-test results, statsmodels fits, estimate + SE, a published interval, or paired item scores (e.g. two models on the same test questions, with cluster-robust SE). |

## Install

```bash
pip install "git+https://github.com/Haifawaeedd/statwarrant@v0.5.0"
```

Pin the version you used (the `v0.5.0` tag), so your analysis can be reproduced.
Requires Python 3.9+, NumPy 1.22+ and SciPy 1.11+. If an earlier development snapshot is
installed, add `--force-reinstall` so it is not reused silently. statwarrant is not yet on
PyPI.

## Real-data regression example

The tests include the historical Longley economic regression and compare its seven
coefficients and standard errors with [NIST-certified reference values](https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Longley.shtml).
The p-values and confidence intervals are recomputed from those values using SciPy;
NIST does not certify these derived quantities on that page, and statwarrant also
uses SciPy. Five additional tests use **fixed summaries**, not fresh model fits,
from Norris, Pontius, PlantGrowth, Iris and ChickWeight; their t-tail references
were computed independently using mpmath. The tests use illustrative thresholds,
not established practical standards. Run both groups with:

```bash
pip install -e ".[test]"
pytest -q tests/test_nist_longley_validation.py tests/test_real_data_reference_summaries.py
```

These examples are not certification of all statistical methods or of the sentence
linter. Longley's OLS model has strongly correlated predictors; interpretation of
any estimate depends on the original data and model assumptions, not on statwarrant.

## How it is checked

[VALIDATION.md](VALIDATION.md) lists what has been checked and how: NIST reference values,
independently computed tails, design analysis against numerical integration and a published
worked example, adapters that recompute reported statistics, results from six published
studies, the supported environments, and what has not been checked yet.
[examples/published_results.py](examples/published_results.py) runs statwarrant on results
from two published trials.

## Independent human evaluation

The [human-review starter kit](evaluation/human-review/README.md) contains empty CSV
templates and Arabic instructions for collecting real claims and recording two blinded,
independent human reviews. It contains no study data or completed labels. A 30-claim
pilot can test the process, but does not measure general accuracy; a separate,
held-out evaluation is still needed. Do not commit confidential data or unlicensed text.

## Usage

### From scipy or statsmodels

```python
from scipy import stats
res = plan.analyze(stats.ttest_ind(group_a, group_b))      # two-sided t-tests
res = plan.analyze(stats.ttest_1samp(scores, 100))         # effect = mean - 100

import statsmodels.formula.api as smf
fit = smf.ols("score ~ method + age", data=df).fit()
res = plan.analyze(fit, term="method[T.new]")
```

statwarrant uses the degrees of freedom statsmodels itself uses for inference
(`df_resid_inference`, e.g. G - 1 with cluster-robust errors). Adapters compare
the reported statistic and p-value to recomputed values and generally raise
`AdapterMismatch` for discrepancies. Extremely small p-values have a known
verification limitation; see [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

### From a published interval

```python
res = plan.analyze(ci=(1.0, 7.4), df=58)
res = plan.analyze(estimate=4.2, ci=(1.0, 7.4), df=58)     # estimate is checked against the midpoint

# a published odds, risk, rate or hazard ratio, as printed (analysed on the log scale)
res = sw.declare(units="log hazard ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
```

Intervals must be symmetric (estimate ± critical value × SE). An asymmetric interval
is refused instead of being silently symmetrised. Endpoints alone cannot prove that
the original interval was symmetric: give `estimate=` too when you have it, so the
check can run. An interval far from zero relative to its width (say 10^14 ± 0.3) is
refused, because its width cannot be recovered accurately; give `estimate=` and `se=`. For ratios (odds, risk, rate, hazard), pass the printed
numbers with `ratio=True`, or give log-scale numbers; the symmetry check allows for the
rounding of the printed digits. A small gap between the estimate and the midpoint is
tolerated (5% of the half-width plus rounding); statwarrant then uses the midpoint and
says whether rounding explains the gap. With `ratio=True` the report adds the ratio and
the relative change with its interval (`0.83 (0.75 to 0.93)` is -16.5%, -25.0% to
-7.0%); `baseline=` is refused for ratios and log-scale units, because the result is
already relative. For bootstrap or other asymmetric intervals, give `estimate=` and `se=`.

### Describing the study

```python
sw.declare(..., design="randomised")      # or "observational"; used to judge causal wording
sw.declare(..., subgroup="patients on mechanical ventilation")   # the result is a subgroup result
```

Both are your own description, reported and never verified. With `design="randomised"`,
causal wording about an established average effect is not flagged; with
`"observational"` it is a conflict. With `subgroup`, a sentence naming that subgroup is
not flagged as a subgroup claim.

### Comparing two models on the same test items

```python
plan = sw.declare(sesoi=0.01, sesoi_source="smallest accuracy gain worth switching models",
                  units="accuracy", scope="MMLU test split, one run per model")
res = plan.analyze_paired(correct_a, correct_b, cluster=passage_ids)
```

The uncertainty is over test items, for these two fixed models. It says nothing about
variation across training runs or seeds.

### Every threshold at once

```python
th = res.thresholds
th.met_below           # 0.99725...: an effect beyond ±d is established for every d below this
th.equivalence_above   # 7.40275...: equivalence within ±d is established for every d above this
th.decision(8)         # 'equivalent'
```

Both cut-offs are strict. In printed reports they are rounded in the safe direction
(0.9972 down, 7.403 up), so "every d below 0.9972" is literally true.

Both decisions are read from intervals, so these two numbers settle every symmetric
threshold. This is a re-reading of the same interval, not a set of new tests, and it is
there so readers with other thresholds can see their answer, not so that a threshold can
be chosen after seeing the data. The report keeps your declared threshold as the
primary one.

### Interval policy

```python
sw.declare(..., interval_policy="single")    # default: every decision from one 95% interval
sw.declare(..., interval_policy="standard")  # equivalence (TOST) from the 90% interval, as in TOSTER
```

The policy only changes the equivalence test. The minimal-effect test ("the effect
exceeds the SESOI") can succeed in either direction, so it always splits alpha over the
two directions (2.5% each) and reads the 95% interval; this keeps its type I error at
or below 5%. (Version 0.1.0 ran it at 5% per side under `"standard"`, which could
reach almost 10%.)

The two levels of `"standard"` can contradict each other. With an estimate of 0.10,
SE 0.058 and a SESOI of 0.2, the 90% interval [0.005, 0.195] lies inside the bounds, so
TOST declares equivalence, while the 95% interval [-0.014, 0.214] reaches past 0.2.
Under `"standard"`, statwarrant reports this conflict; under `"single"` it cannot arise.
The price of `"single"` is slightly less power for equivalence.

### Declaring before analysis

`declare()` records a timestamp, but that is only your computer's clock and proves
nothing. To make the plan verifiable, register its fingerprint (or `plan.to_dict()`)
somewhere a third party timestamps it (OSF, AsPredicted, a public commit) before you
see the result. statwarrant never verifies a registration: the report always says that
the timing is unverified and that the registration reference is your own text.

```python
plan.fingerprint     # SHA-256 of the plan's content; the same plan always gives the same value
sw.declare(..., registration="https://osf.io/...")   # where you registered it (not part of the fingerprint)
plan.fingerprint_for(1)   # the 0.2.0 format, for plans registered with that release
```

### Design sensitivity

```python
res.design([2, 3, 5], source="effects reported in two earlier studies")
```

These numbers describe the design under each assumed effect. They are **not** a
statement about the observed estimate, and should not be used to "correct" it.

### Output

`res.to_markdown()`, `res.to_json()` and `res.to_dict()` give a report: what was
compared (your description), your declared plan, the tests, every threshold at once,
the claims, the sentences you checked with their warnings, input information, and
what statwarrant does not verify. For model objects and paired inputs, the recorded
inputs are summaries, not the original objects or raw data. The JSON carries a schema
version (`statwarrant-result/2`). Name a result with `analyze(..., label="H1")`.
Extreme finite inputs can overflow and prevent JSON export; see known issues.

## What it does not do

* It does not check that your data or model are right; it interprets the estimate it is given.
* It cannot show an effect is exactly zero; only that it is smaller than your SESOI.
* It does not verify your descriptions (outcome, contrast, scope), causal claims, or
  generalisation beyond the data; every report lists these.
* The sentence linter is pattern-based, English-only and warnings-only. No warning is
  not a clearance: it checks only the words it recognises and lists the rest.
* The linter's accuracy has not been measured on sentences annotated by independent
  researchers; until it is, treat it as an experimental aid. The test corpus in
  `tests/test_sentences.py` was annotated by the maintainers and guards against
  regressions only. Sentences it handles wrongly are the most useful feedback you can give.
* It handles one effect at a time; multiple comparisons are not adjusted.
* `res.check()` stores each sentence in the report by default. Remove them before sharing a
  report with confidential text, or use `res.check(sentence, record=False)`. To remove all
  previously stored checks from future reports, use `res.checked.clear()`; this does not
  delete previously exported reports or returned check objects. Review all other fields too.
* Paired comparisons with cluster labels refuse missing labels; drop or label those items first.

## Related tools

statwarrant builds on the same methods as these tools and is checked against some of them.

* [TOSTER](https://cran.r-project.org/package=TOSTER) (R): a much fuller toolkit for equivalence and minimal-effect testing (many designs, effect-size options, plots), with plain-language descriptions of results. If you work in R, start there. statwarrant covers far fewer designs; what it adds is a claim contract and a sentence checker, in Python.
* [statsmodels](https://www.statsmodels.org/) (Python): TOST functions; used as a reference in our tests.
* [baycomp](https://baycomp.readthedocs.io/) and [autorank](https://github.com/sherbold/autorank) (Python): Bayesian comparison of models with a region of practical equivalence.
* [retrodesign](https://cran.r-project.org/package=retrodesign) (R): Type S and Type M errors.
* [metacheck](https://scienceverse.github.io/metacheck) (R): automated checks of research papers, including matching reported numbers to analyses.
* [statcheck](https://michelenuijten.shinyapps.io/statcheck-web/) (R): extracts reported test statistics from papers and recomputes their p-values.

None of statwarrant's ingredients is new. What it tries to add is their combination in
one Python workflow: a declared threshold, the tests, every threshold at once, a claim
contract and a record of the sentences checked. We have not surveyed every tool, so we
do not claim it is the first or only one.

## Feedback

This is an early release and your opinion shapes it.

* **A sentence the checker handled wrongly** (a false warning, or a misreading it missed):
  [report it](https://github.com/Haifawaeedd/statwarrant/issues/new?template=linter.yml). This is
  the most useful report we can get.
* **A wrong number, a crash or contradictory output:**
  [bug report](https://github.com/Haifawaeedd/statwarrant/issues/new?template=bug_report.yml).
* **How it went overall:** [feedback form](https://github.com/Haifawaeedd/statwarrant/issues/new?template=feedback.yml).
* **Questions and ideas:** [Discussions](https://github.com/Haifawaeedd/statwarrant/discussions).

Feedback here is public and used to improve the software. Do not paste confidential or
unpublished text. Security problems: see [SECURITY.md](SECURITY.md).

## How statwarrant is developed

statwarrant is designed and maintained by Haifaa Owayed, who chooses its scope, methods,
claim wording and validation plan. Much of the code, tests and documentation is written
with AI coding assistants (including Claude by Anthropic), and several review rounds were
carried out with AI systems; these are not independent human reviews. The statistics are
tested against SciPy, statsmodels and published reference values; independent human
validation of the sentence checker is still to come (see [KNOWN_ISSUES.md](KNOWN_ISSUES.md)
and the [human-review kit](evaluation/human-review/README.md)).

## Citing

See [CITATION.cff](CITATION.cff). Please also cite the methods you rely on (below).

## References

* Schuirmann, D. J. (1987). A comparison of the two one-sided tests procedure and the power approach for assessing the equivalence of average bioavailability. *Journal of Pharmacokinetics and Biopharmaceutics*, 15, 657–680.
* Lakens, D., Scheel, A. M., & Isager, P. M. (2018). Equivalence testing for psychological research: A tutorial. *Advances in Methods and Practices in Psychological Science*, 1(2), 259–269.
* Gelman, A., & Carlin, J. (2014). Beyond power calculations: Assessing Type S (sign) and Type M (magnitude) errors. *Perspectives on Psychological Science*, 9(6), 641–651.
* Lu, J., Qiu, Y., & Deng, A. (2018). A note on Type S/M errors in hypothesis testing. *British Journal of Mathematical and Statistical Psychology*.
* Miller, E. (2024). Adding error bars to evals: A statistical approach to language model evaluations. arXiv:2411.00640.
* Murphy, S. L., Merz, R., Reimann, L.-E., & Fernández, A. (2025). Nonsignificance misinterpreted as an effect's absence in psychology. *Royal Society Open Science*, 12, 242167.
* Peters, U., & Chin-Yee, B. (2025). Generalization bias in large language model summarization of scientific research. *Royal Society Open Science*, 12, 241776.

## License

MIT. See [LICENSE](LICENSE).

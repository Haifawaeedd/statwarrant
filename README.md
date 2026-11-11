# statwarrant

**What your statistical result warrants you to say.**

[![tests](https://github.com/Haifawaeedd/statwarrant/actions/workflows/tests.yml/badge.svg)](https://github.com/Haifawaeedd/statwarrant/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`statwarrant` turns an estimate and its uncertainty into a **claim contract**: the
statements your result supports, the statements it does not, and the reason for
each. It can also check a sentence you are about to write.

It does not invent new statistics. It combines established methods (tests of
difference, equivalence and minimal effect; design analysis) into one consistent
reading, and refuses claims the data cannot carry.

```python
import statwarrant as sw

plan = sw.declare(
    sesoi=3, sesoi_source="smallest score gain teachers act on",
    units="points", scope="first-year students, one university, one term",
)
res = plan.analyze(estimate=4.2, se=1.6, df=58)   # or a scipy / statsmodels result

print(res)
```

```text
The effect is positive (95% CI [0.997, 7.4]); whether it reaches the smallest effect size
of interest (3 points) is not determined by these data. Scope: first-year students, one
university, one term.
Do not say: "There is no effect."; "The effect is practically important."; "The two
conditions are equivalent."; "The effect generalizes to all settings."; "The results prove
the effect is exactly the estimated value."
```

```python
print(res.check("The new method produced a large improvement."))
```

```text
[BLOCKED] The new method produced a large improvement.
  - The 95% CI [0.997, 7.4] includes values smaller than the smallest effect size of
    interest ([-3, 3]).
```

The result is statistically significant (p = 0.011), yet a "large improvement" is
not supported: the data are also compatible with a 1-point gain.

## Why

* Between 76% and 85% of psychology articles (2009 to 2021) that discussed a
  non-significant finding read it as evidence that the effect is absent
  (Murphy et al., 2025).
* Language models summarising research overgeneralise conclusions; in one study
  of 10 models, summaries were about five times more likely than human-written ones
  to broaden the scope of a finding (Peters & Chin-Yee, 2025).
* The computations to prevent these mistakes exist, but in Python they are spread
  over several packages and none of them says what you may *write*.

## What it does

| Feature | What you get |
| --- | --- |
| Declare first | The smallest effect size of interest (SESOI) needs a stated reason, fixed before analysis. Without a SESOI, claims about importance and equivalence are withheld. |
| Three tests, one reading | Difference from zero, equivalence (TOST) and minimal effect (MET), read from intervals. |
| Claim contract | Allowed statements with numbers filled in, and a list of blocked statements with reasons. |
| Sentence checker | `res.check("...")` judges an English sentence: `allowed`, `blocked`, `needs_care` or `unrecognized`. |
| Level-conflict detection | Flags when the zero test and the threshold test disagree because they use different interval levels. |
| Design sensitivity | Power, Type S and exaggeration ratio under assumed effects, with the source of each assumption required. |
| Scope on every claim | Generalising beyond the declared scope is blocked. |
| Absolute and relative | With a `baseline`, both changes are reported side by side. |
| Common inputs | scipy t-test results, statsmodels fits, estimate + SE, a published interval, or paired item scores (e.g. two models on the same test questions, with cluster-robust SE). |

## Install

```bash
pip install git+https://github.com/Haifawaeedd/statwarrant
```

Requires Python 3.9+, NumPy and SciPy 1.11+. A PyPI release (`pip install statwarrant`) will follow.

## Usage

### From scipy or statsmodels

```python
from scipy import stats
res = plan.analyze(stats.ttest_ind(group_a, group_b))      # two-sided t-tests

import statsmodels.formula.api as smf
fit = smf.ols("score ~ method + age", data=df).fit()
res = plan.analyze(fit, term="method[T.new]")
```

### From a published interval

```python
res = plan.analyze(ci=(1.0, 7.4), df=58)
```

For ratios (odds, risk, hazard), give the estimate and interval on the log scale.

### Comparing two models on the same test items

```python
plan = sw.declare(sesoi=0.01, sesoi_source="smallest accuracy gain worth switching models",
                  units="accuracy", scope="MMLU test split, 5 seeds")
res = plan.analyze_paired(correct_a, correct_b, cluster=passage_ids)
```

### Interval policy

```python
sw.declare(..., interval_policy="single")    # default: every decision from one 95% interval
sw.declare(..., interval_policy="standard")  # zero test at 95%, TOST / MET at 90%, as in TOSTER
```

The standard levels can contradict each other. With an estimate of 1.9, SE 1.0 and a
SESOI of 0.1, the 95% interval [-0.06, 3.86] does not exclude zero (p = 0.057), while the
90% interval [0.26, 3.54] lies above 0.1 (p = 0.036). Under `"standard"`, statwarrant
reports this conflict; under `"single"` it cannot arise. The price of `"single"` is
slightly less power for equivalence and minimal-effect tests (each side at 2.5%).

### Design sensitivity

```python
res.design([2, 3, 5], source="effects reported in two earlier studies")
```

These numbers describe the design under each assumed effect. They are **not** a
statement about the observed estimate, and should not be used to "correct" it.

### Output

`res.to_markdown()`, `res.to_json()` and `res.to_dict()` give the full record: plan,
input, tests, claims and notes.

## What it does not do

* It does not check that your data or model are right; it interprets the estimate it is given.
* It cannot show an effect is exactly zero; only that it is smaller than your SESOI.
* The sentence checker is pattern-based and English-only in 0.1. It returns
  `unrecognized` rather than guessing.
* Version 0.1 handles one effect at a time; multiple comparisons are not adjusted.

## Related tools

statwarrant builds on the same methods as these tools and is checked against some of them.

* [TOSTER](https://cran.r-project.org/package=TOSTER) (R): equivalence and minimal-effect tests with plain-language descriptions. The closest relative.
* [statsmodels](https://www.statsmodels.org/) (Python): TOST functions; used as a reference in our tests.
* [baycomp](https://baycomp.readthedocs.io/) and [autorank](https://github.com/sherbold/autorank) (Python): Bayesian comparison of models with a region of practical equivalence.
* [retrodesign](https://cran.r-project.org/package=retrodesign) (R): Type S and Type M errors.
* [metacheck](https://scienceverse.github.io/metacheck) (R): automated checks of research papers.

## Feedback

This is an early release and your opinion shapes it.

* **Tell us how it went:** [open a feedback form](https://github.com/Haifawaeedd/statwarrant/issues/new?template=feedback.yml)
* **Found a sentence judged wrongly?** That is the most useful report we can get. Use the same form.
* **Questions and ideas:** [Discussions](https://github.com/Haifawaeedd/statwarrant/discussions)

Feedback here is public and used to improve the software.

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

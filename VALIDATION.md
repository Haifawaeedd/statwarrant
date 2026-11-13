# How statwarrant is checked

This page lists what has been checked, how, and what has not. Version 0.5.0.

## Statistics

| What | How | Where |
| --- | --- | --- |
| Zero, equivalence (TOST) and minimal-effect tests | Decisions from test statistics; printed cut-offs placed exactly where the decision changes, property-tested near floating-point cancellation | `tests/test_core.py`, `tests/test_observation_thresholds.py`, `tests/test_review6.py` |
| Regression coefficients and standard errors read from statsmodels | The Longley regression against NIST-certified values ([StRD](https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Longley.shtml)) | `tests/test_nist_longley_validation.py` |
| t-tail probabilities | Five fixed real-data summaries with tails computed independently in mpmath | `tests/test_real_data_reference_summaries.py` |
| Power, Type S and exaggeration ratio | Numerical integration, and the worked example of Gelman and Carlin (2014): true effect 2.8 with SE 1 gives power 0.80, Type S 1.2e-6, exaggeration about 1.12 | `tests/test_design_extremes.py` |
| SciPy and statsmodels adapters | The reported statistic and p-value are recomputed and must match; mismatches are refused | `tests/test_adapters.py` |
| Published ratios with rounded intervals | Property test: rounded intervals are accepted and give the same decisions as their log-scale values | `tests/test_published_wording.py` |
| Extreme inputs | Fuzzing across the floating-point range; values that cannot be represented are refused with a message | `tests/test_design_extremes.py`, `tests/test_critical_value_safety.py`, `tests/test_observation_underflow.py` |

**Published results.** Results from six published studies (five randomised trials and one
cohort) were entered as printed. Every one of the 18 results with a two-sided interval is accepted,
and the decisions follow the published intervals. Of the 7 p-values printed in those papers,
4 are reproduced from the rounded intervals at their printed precision. The other 3 differ
(for example 0.73 against 0.69) because the interval was rounded and the original model is
not reproduced exactly. See the
[published-paper experiment](https://github.com/Haifawaeedd/statwarrant/blob/main/KNOWN_ISSUES.md#sentences-from-published-papers).

**Environments.** The test suite (about 1,070 tests, including property-based tests) passes
on Python 3.9, 3.10 with the oldest supported NumPy 1.22.4, SciPy 1.11.4 and statsmodels
0.14.0, and 3.13 with NumPy 2.5 and SciPy 1.18, on Linux. Continuous integration is set up
to run it on Python 3.9 to 3.13 and on macOS and Windows; check the badge on the README for
its latest result. Printed output fits the Windows code pages for Western, Cyrillic,
Arabic, Japanese and Chinese text.

## Sentence checker

The checker is experimental. Its results so far, all on small sets labelled by an AI rather
than by independent people, so none is an accuracy estimate:

| Set | Sentences | Problems with a warning | Correct sentences with a false `conflict` |
| --- | --- | --- | --- |
| Third user trial: three real datasets, labels frozen before checking | 24 | 11 of 13 | 0 of 11 |
| Six published studies (33 excerpts from the papers, 8 from news and summaries) | 41 | 3 of 4 | 0 of 32 |

Rules were later changed after seeing these sentences, so the numbers are optimistic.
`conflict` is rare on correct text. Most correct sentences still have parts listed as
"not verified", usually direction words that cannot be tied to the declared contrast.

## Not yet checked

* Accuracy of the sentence checker on sentences labelled by independent researchers.
  A [human-review kit](evaluation/human-review/README.md) is ready.
* Independent human review of the code. All reviews so far were done with AI systems.
* Use by researchers other than the maintainer. That is what this trial is for.

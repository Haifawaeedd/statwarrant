# How statwarrant is checked

This page lists what has been checked, how, and what has not. Version 0.6.0; additions for 0.6.0 are marked.

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

**Environments.** The test suite (about 1,070 tests in 0.5.0; 1,945 in 0.6.0, including property-based tests) passes
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

### Reader experiment (development set)

405 sentences about 10 constructed and 9 published results, read blind by two AI reader
models (the materials will be published after the human reader study). Share of sentences
given a `conflict`:

| Sentences | 0.5.1 | 0.5.2 |
| --- | --- | --- |
| Misleading, constructed | 65 of 140 (46%) | 129 of 140 (92%) |
| Correct, constructed | 2 of 190 | 2 of 190 |
| Misleading, from published studies | 7 of 17 | 8 of 17 |
| Correct, from published studies | 0 of 43 | 0 of 43 |

The 0.5.2 rules were written after reading these sentences, and the constructed sentences
follow a few fixed templates, so these numbers are far more optimistic than performance on
new text. On 16 new wordings written for the 0.5.2 tests, 15 were judged as intended before
the last fix (`tests/test_real_data_trial_052.py`).

### First real-data trial

The maintainer ran statwarrant 0.5.1 on 11 paired comparisons from an LLM evaluation
project (1,000 PubMedQA cases, two models, several prompt conditions):

* Estimates, standard errors, degrees of freedom, 95% intervals and p-values matched an
  independent SciPy calculation in 11 of 11 comparisons (largest difference about 3e-17).
  statwarrant uses SciPy itself, so this is a consistency check, not an independent proof.
* Of 10 test sentences, the checker gave correct conflicts for "no difference", "every
  patient", "proves", a false "significantly improved" and "small" (the estimate was beyond
  the declared threshold). It missed a reversed direction ("improved" for a negative
  estimate), "guaranteed ... on all medical questions", and a measure read as a broader
  ability ("better at medical reasoning" for strict answer correctness). 0.5.2 fixes the
  first two; the third is outside what a rule checker can judge.

### Second numerical check (0.5.3)

An outside check of the PyPI release of 0.5.3 matched SciPy, statsmodels and independent
calculations on seven analyses: three ToothGrowth comparisons, two anorexia treatment-versus-
control comparisons, and two coefficients of a multiple regression on the trees data with HC3
standard errors. Three non-inferiority wordings gave "to verify" instead of the 0.5.2 false
conflict, and a wrong p-value attributed explicitly to the zero test was still a conflict.
ToothGrowth and anorexia had been used before, so this is a technical check, not a blind
evaluation on new data.

### Frozen evaluation

`evaluation/human-review/run_frozen.py` runs one frozen version on the human-review cases
after the reviews are frozen, and `scorecard.py` reports false reassurance, false alarms and
the share sent to review against the adjudicated labels, with 95% intervals.

### Held-out sentences

Sentences reported through the ["A sentence the linter got wrong"](.github/ISSUE_TEMPLATE/linter.yml)
issue form from 0.5.2 on are scored with the released version before any rule is changed
for them, and those scores are reported separately here. They are the first sentences the
rules were not written for.

## Additions in 0.6.0

### Independent numerical check (Wolfram Language)

Computed outside SciPy, in Wolfram Language, at 20 or more significant digits. statwarrant's values
agree to about 15 significant digits:

| Quantity | Wolfram | statwarrant |
| --- | --- | --- |
| README example (4.2, SE 1.6, df 58): `met_below` | 0.99725202536762222 | 0.99725202536762203 |
| README example: `equivalence_above` | 7.4027479746323778 | 7.4027479746323781 |
| README example: two-sided p of the zero test | 0.011059525082854976 | 0.011059525082854968 |
| README example: one-sided p of the minimal-effect test (bounds ±3) | 0.22814317283878459 | 0.2281431728387846 |
| Gelman & Carlin (true effect 2.8, SE 1): power | 0.79955687143565142 | 0.799556871435651 |
| Gelman & Carlin: Type S | 1.21084262271779909e-6 | 1.2108426227178e-6 |
| Gelman & Carlin: exaggeration ratio | 1.12521878178789223 | 1.12521878178789 |
| Relevance test, normal, bounds ±0.5 SE: folded-normal critical value | 2.1814774423281538 | 2.181477442328155 |

The last row is a regression test (`tests/test_relevance_060.py`).

### Minimal-effect test: split versus relevance (simulation)

`evaluation/simulations/relevance_size.py`: one-sample normal data with unknown variance, t
reference, 1,000,000 replications per cell (Monte Carlo standard error about 0.0002 for a
rejection rate of 0.05). The relevance test chooses its per-side level from the observed
standard error, so its size is checked here rather than assumed.

```
Size at the bound (true effect = d), alpha = 0.05, 1000000 replications per cell
| n | d / SE | split | relevance |
| --- | --- | --- | --- |
| 5 | 0.1 | 0.0417 | 0.0492 |
| 5 | 0.3 | 0.0321 | 0.0473 |
| 5 | 0.6 | 0.0265 | 0.0451 |
| 5 | 1.0 | 0.0250 | 0.0464 |
| 5 | 2.0 | 0.0249 | 0.0489 |
| 10 | 0.1 | 0.0413 | 0.0499 |
| 10 | 0.3 | 0.0311 | 0.0485 |
| 10 | 0.6 | 0.0263 | 0.0477 |
| 10 | 1.0 | 0.0248 | 0.0482 |
| 10 | 2.0 | 0.0252 | 0.0502 |
| 30 | 0.1 | 0.0406 | 0.0500 |
| 30 | 0.3 | 0.0304 | 0.0494 |
| 30 | 0.6 | 0.0260 | 0.0492 |
| 30 | 1.0 | 0.0251 | 0.0497 |
| 30 | 2.0 | 0.0251 | 0.0501 |
| 200 | 0.1 | 0.0405 | 0.0499 |
| 200 | 0.3 | 0.0302 | 0.0496 |
| 200 | 0.6 | 0.0258 | 0.0504 |
| 200 | 1.0 | 0.0248 | 0.0499 |
| 200 | 2.0 | 0.0251 | 0.0497 |

Power at true effect = d + 2.5 SE
| n | d / SE | split | relevance |
| --- | --- | --- | --- |
| 10 | 0.3 | 0.6057 | 0.6809 |
| 10 | 1.0 | 0.6060 | 0.7356 |
| 10 | 2.0 | 0.6062 | 0.7449 |
| 30 | 0.3 | 0.6762 | 0.7486 |
| 30 | 1.0 | 0.6750 | 0.7847 |
| 30 | 2.0 | 0.6767 | 0.7875 |
| 200 | 0.3 | 0.7020 | 0.7720 |
| 200 | 1.0 | 0.7018 | 0.8011 |
| 200 | 2.0 | 0.7007 | 0.8008 |
```

Under `"split"` the size is about 0.025 once the bounds are wider than about one standard error.
Under `"relevance"` it never exceeded 0.0504; across the grid it ranged from 0.045 to 0.050, below
the nominal level for small samples (0.045 to 0.049 at n = 5, several Monte Carlo standard errors below
0.05). Power is 7 to 14 points higher, a gain that partly reflects the split method's lower actual size.

### Structured assertions, language-model reader, MCP server

* `Result.verify()` agrees with the claim contract on the five example results in
  `tests/test_assertions_060.py`; what the contract blocks is never "supported".
* The language-model reader is tested only with scripted fake models
  (`tests/test_llm_060.py`): parsing, fallback on provider errors, re-checking of rewrites, and
  that the model is not shown the result's numbers. **Its accuracy has not been measured.**
* The MCP server is tested through the real protocol, in memory and over stdio
  (`tests/test_mcp_server_060.py`), and was checked manually over Streamable HTTP.

## Not yet checked

* Accuracy of the sentence checker on sentences labelled by independent researchers.
  A [human-review kit](evaluation/human-review/README.md) is ready.
* Accuracy of the language-model reader (0.6.0), against the human labels and with models from
  more than one provider.
* Independent human review of the code. All reviews so far were done with AI systems.
* Use by researchers other than the maintainer. That is what this trial is for.
* Whether a written claim matches what the measure means (for example "reasoning" for answer
  correctness). Rules cannot judge this; an optional reader layer is planned for 0.6.0
  (see [ROADMAP.md](ROADMAP.md)).

## Exploratory benchmark on real trial abstracts (MedLitSpin)

60 abstracts of 30 cancer trials (Yun et al., CHIL 2025), with spin labels set by others, checked with
0.6.0 and compared with 22 published and new language-model runs. Notebook, data, prompts and every model
answer: [evaluation/medlitspin/](evaluation/medlitspin/). The rules flagged 19 of 30 spun and 2 of 30
neutral abstracts; 8 of the 19 flags concerned the primary result. A one-phrase rule separates the
classes perfectly, so the benchmark cannot show which methods used the numbers.

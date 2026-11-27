# Changelog

## 0.6.0

New, all optional; existing results and fingerprints are unchanged. This release also
contains the two 0.5.4 fixes below; 0.5.4 itself was not published separately.

* **Structured claims.** `Assertion(kind, direction, value, polarity, quote)` and
  `Result.verify()` judge one claim written as fields with the same tests as the claim
  contract: supported, not established, contradicted or to verify. Denials and hedges are
  never cleared. A verdict concerns the statistical proposition only, never wording.
* **Language-model reader (experimental).** `Result.review(sentence, llm=...)`: a model lists
  the sentence's claims as assertions and notes what numbers cannot check; statwarrant judges
  them and runs the rule-based checker. The model is not shown the result's numbers. A
  rewrite from the allowed statements is offered only if it passes the checks again. Any
  provider: `AnthropicLLM`, `OpenAILLM` (also OpenAI-compatible local servers),
  `CallableLLM`. Extras: `statwarrant[anthropic]`, `statwarrant[openai]`. Experimental: tested
  only with scripted models, its accuracy has not been measured.
* **MCP server.** `statwarrant[mcp]` installs `statwarrant-mcp` (stdio, or Streamable HTTP
  with `--http`) with read-only tools `analyze_result`, `verify_assertions` and
  `check_sentences`, for Claude, ChatGPT and other assistants. A Hugging Face Space recipe
  is in `deploy/huggingface-space/`.
* **Test for relevant differences.** `declare(met_method="relevance")` runs the minimal-effect
  test of Hodges and Lehmann (1954): largest type I error exactly alpha, more power for wide
  bounds. The default `"split"` method is unchanged; its largest type I error is close to
  alpha / 2 for bounds wider than about one standard error, which is now documented.
* **Estimand.** `analyze(..., estimand="...")` records what the estimate is. SciPy t-test
  results, which do not record trimming (Yuen's test), Welch or pooling, get a note when no
  estimand is given: with `trim=0.2` the estimate is a difference of trimmed means.
* Tests: `tests/test_relevance_060.py`, `test_estimand_060.py`, `test_assertions_060.py`,
  `test_llm_060.py`, `test_mcp_server_060.py` (1,945 tests in total).

## 0.5.4 (not published separately; included in 0.6.0)

Two known issues from outside checks of 0.5.3, fixed before the human-review evaluation
started.

* **Stated size bounds.** "The new method improved exam performance by at least 3 points"
  (estimate 4.27, 95% CI 0.40 to 8.15) was only "to verify" because the comparison could
  not be tied to the declared contrast. An effect of at least 3 points is not established
  whichever way the comparison runs, so "by at least / more than / over N" is now a
  conflict when the interval rules it out in both orders. Negated or hedged bounds, and
  numbers written with another unit, are unchanged.
* **Causal nouns.** "The results prove causality" flagged only "prove". "causality" and
  "causation" are now recognised as causal claims (a conflict with a declared
  observational design, otherwise "to verify").
* Regression tests: `tests/test_known_issues_054.py`.

## 0.5.3

A test statwarrant does not run is never judged against, or replaced by, the zero test.

* **Non-inferiority.** "P<0.001 for noninferiority", "the noninferiority test was
  significant" and "Aspirin was noninferior to heparin (P<0.001)" were conflicts in 0.5.2:
  the p-value was compared with the zero test (p = 0.75 in PREVENT CLOT) and the advice was
  to copy the zero test's p-value, which would have put a wrong value in the paper. They are
  now "to verify", with the advice to check them against the non-inferiority test. A
  non-inferiority claim itself is listed as not checked. Superiority and non-superiority
  tests are recognised as other tests too. A p-value explicitly tied to the zero test is
  still judged.
* "non-inferior" is no longer read as the direction word "inferior".
* Any p-value or significance statement sent to review now says to check it against the
  test it belongs to, never to copy the zero test's value.
* Regression tests from PREVENT CLOT (O'Toole et al., NEJM 2023):
  `tests/test_noninferiority_053.py`.

## 0.5.2

Fixes from the first real-data trial (11 paired comparisons from an LLM evaluation project,
run by the author on 1,000 PubMedQA cases).

* **Direction.** A stated change ("improved", "reduced", "lowered") is a **conflict** when
  the interval includes zero, whichever way the comparison runs. In 0.5.1 a declared
  contrast sent every such sentence to "to verify": "Adding justification significantly
  improved accuracy" for an estimate of -1.6 points (95% CI -3.7 to 0.5) got a conflict on
  "significantly" but nothing on "improved". Comparatives ("higher", "lower") and changes
  asked about ("could not determine whether it raised ...") stay "to verify".
* **Reversed direction.** When the contrast is declared as "A minus B" and the sentence names
  the outcome and only A ("Adding evidence reduced accuracy", "Accuracy was lower with
  evidence"), a direction opposite to the established one is a **conflict**. A matching
  direction is only "to verify", never consistent. The rule does not apply when B, a
  comparison cue (than, versus, compared with ...), or a removal of A ("without evidence",
  "removing evidence", "less evidence") appears, or when the outcome is not named. In 0.5.1
  reversed direction was never detected.
* **Guarantees.** "guaranteed" is certainty wording (a conflict); "not guaranteed" and "does
  not guarantee" are cautions. "all" followed by one describing word and a noun such as
  questions, items, cases or patients ("all medical questions") is a generalisation; counts
  ("all three groups") are not.
* **Two-sided significance.** A significance claim that names no direction ("differed
  significantly between the groups", "a significant difference between the conditions") is
  consistent with a significant result and a conflict with a non-significant one. Sentences
  with any ordering word (than, outperformed, inverse, positive, "-er for ...") stay "to
  verify".
* **Reversed direction in a comparison.** "A lowered the outcome compared with B" and "A led
  to lower ... than B" are conflicts when the result points the other way. Only the order
  A, change, outcome, cue, B is read; "B ... than A" stays "to verify".
* **Practical importance.** "A large and practically important improvement" is a conflict
  when the interval is not wholly beyond the smallest effect size of interest, whichever
  way the comparison runs. Hedged or negated wording ("not clear whether the benefit is
  large enough to matter", "no meaningful difference", "negligible") is not judged by this
  rule.
* **Trends.** "A trend toward higher scores" is judged like a stated change: a conflict when
  the interval includes zero.
* **Unattached negations.** A claim that follows a negation the checker cannot attach, in the
  same clause, is "to verify" instead of judged: "The diet did not produce a clinically
  meaningful weight loss" was a false conflict in 0.5.1.
* On the 405 sentences of the reader experiment, conflicts on misleading constructed
  sentences rose from 65 to 129 of 140 (46% to 92%), with no new conflicts on correct
  sentences (2 of 190; 0 of 43 published). These sentences were read while writing the
  rules and follow fixed templates, so this is far from an unbiased accuracy estimate. See
  VALIDATION.md.
* New: ROADMAP.md (the optional reader layer planned for 0.6.0) and VALIDATION.md sections
  on the reader experiment, the real-data trial and held-out reported sentences.
* Regression tests: `tests/test_real_data_trial_052.py`.

## 0.5.1

* A claim of significance ("significantly improved", "significantly different between the
  groups", "scored significantly higher than ...") is a **conflict** when the test of
  difference from zero is not significant, whichever way the comparison runs. In 0.5.0 it
  got only "to verify" whenever the comparison could not be tied to the declared contrast:
  the quick start's own sentence, "The new method significantly improved scores.", was not
  flagged for a non-significant result (p = 0.258), and declaring the contrast or passing a
  SciPy result weakened the warning that estimate + SE without a contrast gave. This is the
  rule already used for ratios: a conflict when ruled out in both orders. With a
  significant result the order still decides, so those claims stay "to verify".
* Significance wording after a negation or hedge in its clause ("failed to significantly
  improve", "whether ... significantly improved ...") is "to verify" instead of a false
  conflict.
* Wording that statwarrant recommends is no longer a conflict: "too small to matter" is read
  as a claim of a negligible effect, "compatible with no effect and with an effect larger
  than ..." as an interval statement, and "the data neither show an effect nor rule out a
  meaningful one" as a statement that the result is inconclusive. In a blind reader
  experiment on 405 sentences these gave 15 false conflicts on 190 correct sentences (8%);
  after the change, 2 (1%). Each wording still conflicts with a result it does not describe.
  Regression tests: `tests/test_recommended_wording_051.py`.
* A p-value or "significant" is tied to the test named nearest before it in its part of the
  sentence. "The one-sided test was significant despite the equivalence test giving
  p = 0.000063" keeps the conflict on the equivalence test's p-value and leaves "significant"
  to verify, instead of judging both against the equivalence test. Tests statwarrant does
  not run (permutation, bootstrap, chi-square, Fisher's exact, interaction, sensitivity,
  a one-sided test and others) are recognised: a p-value or significance claim tied to one
  of them is "to verify", never consistent ("the permutation test, whose p-value was
  0.000063" was called consistent with the zero test). Naming "the zero test" ties a
  p-value to it. Found in the claim-binding review (draft pull request #2); regression
  tests: `tests/test_test_binding_051.py`.
* After the review of the 0.5.1 candidate (draft pull request #3): a p-value or
  "significant" binds to a test named after it with a preposition ("significant in the
  equivalence test") and through an opening phrase ("For the zero test, p = ...": a
  mismatch is a conflict, a match is "to verify"); parts of a sentence end at words such as
  "whereas", "despite" and "whose"; of overlapping test names the first wins ("the
  permutation test of zero" is a permutation test). Causal wording is never "consistent"
  (still a conflict with `design="observational"`), and a subgroup claim is always "to
  verify", as in draft pull request #2: statwarrant cannot check the outcome or group the
  wording names. A claim inside a parenthetical aside, or after "yet", within an interval
  statement is checked on its own. Regression tests: `tests/test_review_v2_051.py`.
* The README install line is `pip install statwarrant` (the package is on PyPI).
* Regression tests: `tests/test_significance_both_orders_051.py`.

First public trial release. Built on the comparison-safety branch (commit 8ad4164)
after the third user trial, two external reviews and a check on sentences from six
published studies. The sentence checker remains experimental (see KNOWN_ISSUES.md).

* Design sensitivity is computed in units of the standard error; an exaggeration ratio
  that cannot be represented is refused with a message, instead of a report whose JSON
  export fails. Checked against numerical integration and Gelman and Carlin (2014).
* "Neither X nor Y was established" (and "the data support neither ...", "neither a
  significant difference nor equivalence") is judged item by item instead of being read
  as a claim of no effect. The conservative rule for "neither equivalence nor an effect"
  is kept and now also covers a size qualifier on "an effect".
* In comparisons that cannot be tied to the declared contrast, warnings on numbers,
  sizes and percentages say what was not checked, instead of repeating the direction
  message.
* Ratio wording ("doubled the odds", "a 3-fold increase"), interval ends ("could be as
  large as 2.5"), "not associated with" and size words after a longer subject are
  checked. These rules were written on the second trial's sentences, before the third
  trial's sentences existed, and were not changed after it.
* After an independent review of this branch: "neither ... nor" items stop at clause
  boundaries so later claims are checked, and items about another outcome or margin get
  a check; ratios are compared only when odds, risk, rate or hazard match the log scale,
  are never marked consistent (order not verified) and conflict only when ruled out in
  both orders; "as high as" / "as low as" use the matching interval end and sign;
  unrecognised ratio wording no longer raises. The release workflow can only be started
  by the owner with a typed confirmation; the notebook installs this branch.
* After checking sentences from six published studies: the printed result lists
  conflicts first and parts that could not be verified separately
  (`[1 conflict, 2 to verify]`), with `.conflicts` and `.to_verify`; `declare()` takes
  `design=` and `subgroup=`; `analyze(..., ratio=True)` takes a published ratio and its
  interval as printed, and the symmetry check allows for rounding; counts, time points
  and group shares are listed as not checked; "does not prove" is a caution; outcome
  names such as "cause-specific mortality" and study sizes such as "a large study" are
  no longer read as claims.
* Before release: printed output fits Windows code pages (an "approximately equal" sign
  broke printing to a redirected Windows console); the rounding allowance assumes one
  printed precision; a note says when the midpoint replaces a given estimate; design
  aliases (RCT, cohort, ...); `VALIDATION.md` and `examples/published_results.py`.
* After review of the release candidate (draft pull request #1): `baseline=` is refused
  for ratios and log-scale units (it gave a relative change of about -90% for a risk
  ratio of 0.83; the reconstructed geometric midpoint 0.8352 implies about -16.5%),
  and `ratio=True` reports the ratio and the relative change with its interval when
  safely representable; the note on an estimate that differs from the interval's
  midpoint gives the gap and the assumptions used by the rounding heuristic;
  "the difference in p-values was 0.01" and "the p-values differed" get a check instead
  of being read as one p-value; a size qualifier after "neither equivalence nor an effect"
  stops at a conjunction or verb, so later claims ("and prove the treatment caused harm
  for everyone") are checked one by one.
* After follow-up review of `c237c3d`: the baseline guard also covers `analyze_paired()`
  and common log2/log10/lnRR labels. Ratio-scale display uses adaptive precision and
  safely omits unrepresentable conversions rather than crashing or printing infinity.
  Float inputs cannot establish printed precision or the reason for a midpoint gap;
  `raw_input["estimate_vs_midpoint"]["explained_by_rounding"]` is now `None` rather
  than a Boolean, with the assumed allowance recorded separately. The input CI level
  is distinguished from the displayed test CI level. `ratio=True` rejects explicit
  non-natural or ambiguous log bases; the linter requests review for factor claims on
  such bases and avoids converting percentage points against recognized log/ratio
  units. Numeric p-value differences request review instead of being compared with an
  effect CI; selected coordinated-negation patterns stop at standalone/em dashes so
  subsequent claims are not consumed. Unit-name recognition, natural-language parsing
  and floating-point representations remain limited; see `KNOWN_ISSUES.md`.
* Public-trial files: Colab quick-start notebook, an issue form for sentences the
  checker gets wrong, CI on macOS and Windows, a manually started and approved release
  workflow (TestPyPI or PyPI), `SECURITY.md`, `CODE_OF_CONDUCT.md`, and an AI-use
  statement in the README.

## 0.4.3.dev0 (unreleased comparison-safety branch)

* Bind a restricted set of exact English group and time-order sentences to the
  user-declared outcome and `A minus B` contrast; selected ambiguous comparisons,
  signed numbers and direction-bearing negations ask for human review instead.
  Binding is withheld for SciPy inputs and nonzero or unresolved nulls. Metadata
  are not verified against the data, and unrecognized wording can still lead to a
  misleading judgment. See `KNOWN_ISSUES.md`.
* Added independent regression cases for reversed groups and time points, compound
  claims, signed values, and reconstructed nulls. These are targeted tests, not an
  estimate of real-world sentence-checker accuracy.
* Added empty human-review templates and Arabic instructions. No real case data or
  human ratings are included; a pilot and separate held-out evaluation remain needed.
* Distinguished the development version from the previous 0.4.2 snapshots. No public
  release or tag is implied.

## Unreleased validation-observations branch

* Added NIST Longley coefficient/SE regression checks, inference tests from five
  frozen real-data summaries, and the external sleep review's named-test cases.
  These are targeted tests, not independent human validation or an accuracy measure.
* Added partial, conservative unit checks for simple units adjacent to effect numbers;
  mismatched units request review and are not automatically converted. Other units and
  phrasings may remain unchecked.
* Improved several targeted coefficient, negation, undefined-size, probability-tail,
  threshold-display, null-provenance and paired-integer cases. Lossy integral inputs
  and critical values that fail a self-consistency check are refused. Extreme numerical
  accuracy is not guaranteed; see `KNOWN_ISSUES.md`.
* Narrow nonzero confidence intervals get enough displayed digits to avoid collapsing
  solely through formatting; already-collapsed machine-precision intervals are disclosed.

## 0.4.2 (unreleased)

Fixes from the first-user experiment (three real datasets), its independent review, and
`KNOWN_ISSUES.md` for 0.4.1.

**Sentence linter**

* p-values and "significant" / "not significant" are bound to the test named in the
  same phrase, before or after the p-value, for equalities and inequalities. A p-value
  that matches a test named elsewhere in the sentence gives `check`; naming two tests
  together gives `check`.
* "Percentage points" are rescaled when the result is stored as a proportion
  (0.9 percentage points = 0.009).
* "Did not differ significantly" is read as non-significance, not as "no effect" plus
  "significant".
* A direction noun that names the outcome ("effect on grade improvement", or the
  declared outcome's own wording) is not read as a direction claim.
* "Equivalently" is recognised; "within ±0.02" is checked against the declared bounds;
  "was A to B" is read as an interval.
* Acronyms ("PSI", "SVM's") and words of the declared outcome or scope inside a hedge
  are treated as names, not unchecked content.

**Statistics and inputs**

* Every decision is computed from a test statistic in which the bound is subtracted
  before dividing by the standard error; `Thresholds.decision()` uses the same
  arithmetic. Decisions and p-values now agree near a threshold.
* SciPy null reconstruction uses a tolerance tied to machine precision. Some small
  nonzero null values can still be recorded as zero; see `KNOWN_ISSUES.md`.
* Malformed reported p-values are refused; tiny p-values are compared on the log scale;
  inputs too large for floating point are refused.
* `analyze_paired` records the number of differing items and adds a caution when fewer
  than 10 items differ.

**Docs**

* `KNOWN_ISSUES.md` lists what 0.4.2 fixed and what remains.

**After independent review of the release-0.4.2 branch**

* A p-value or significance word in a clause that names another test is never marked
  consistent with the zero test (`"For the equivalence test, p = 0.011."` gives `check`).
  Contrastive conjunctions ("but", "whereas", "while") end a clause.
* Percentage points are converted only for proportion units and only for numbers
  attached to "percentage points"; other units give `check`; an unattached number that
  fits only after conversion gives `check`, not `conflict`.
* A negation excuses direction words only in its own clause. Size words separated from
  their noun ("a small but significant decrease") are read as size claims.
* Printed threshold cut-offs were adjusted to align with `thresholds.decision()` in the
  reported examples; further edge cases remain (see `KNOWN_ISSUES.md`).
* Some small null values that may be unresolvable now receive a note; a
  reported p = 0 is accepted only with a matching statistic and a note; tiny baselines
  that overflow the relative change are refused; several paired large-integer cases now
  preserve their differences. Further null, p-value and mixed-integer edge cases remain.

## 0.4.1

Fixes from the final review of 0.4.0. One changed numerical results: SciPy results
on data far from zero relative to their spread (for example 1e14 +/- 0.3).

**Statistics and adapters**

* SciPy: the standard error is taken from SciPy's own stored value when available,
  checked against the confidence interval as far as the interval's precision allows.
  Without it, an interval too narrow for its distance from zero is refused. 0.4.0
  rebuilt the SE from the interval endpoints, which lost precision with large offsets
  and could flip the equivalence decision.
* Published intervals (`ci=`) that cannot be converted to an SE accurately are refused.
* The adapter self-check compares p-values unless both underflow; one tiny and one
  ordinary p-value is a mismatch.
* The "touches the bound" tolerance is computed separately for each bound, so a huge
  lower bound can no longer hide an upper crossing.

**Sentence linter**

* "Compatible with ..." phrases stop before negation, causal wording, quantifiers and
  new clauses, so those are judged by their own rules.
* A hedge phrase that contains words the linter does not assess ("compatible with a
  positive effect on mood") gets `check`, not `consistent`.
* p-values are bound to a test: the zero test unless the sentence names the
  equivalence or minimal-effect test. "p = 0" conflicts.
* A stated interval level is bound to the endpoints: a 90% interval labelled 95%
  conflicts.
* Naming a procedure ("the equivalence test", "TOST") is not read as a claim.

**Report**

* The "neither" range between the cut-offs uses the exact cut-off values.
* The recorded cluster count is the one the inference used; statsmodels results
  record their own statistic and p-value.
* Allowed claims show the real interval level (99.9%, not 100%).
* Non-finite design assumptions are refused.
* The README describes the package as an experimental alpha, gives a version-pinned
  install command, and warns that checked sentences are stored in reports.

## 0.4.0

Fixes from an independent review of 0.3.0. Two of these changed numerical results;
if you used 0.3.0 with cluster labels or with SciPy results on a very small scale,
rerun your analyses.

**Numerical fixes**

* `analyze_paired(..., cluster=)` refuses missing cluster labels (NaN, None, pandas
  NA). 0.3.0 dropped NaN labels into separate clusters and merged None labels into
  one, which could turn p = 0.10 into p = 0.006.
* SciPy one-sample tests: the tested difference is read as statistic x SE at every
  scale. 0.3.0 set a null value below 1e-9 to zero, which changed the conclusion for
  data on a 1e-9 scale.
* Adapter self-check is scale-free and mandatory: statwarrant compares the test
  statistic and the p-value with relative tolerances, and refuses results without a
  finite statistic and p-value.
* An interval that touches a SESOI bound without passing it gets its own class,
  `inconclusive_at_bound`, instead of a claim about effects "beyond" the bound.
* Critical values use the inverse survival function (stable for small alpha);
  alpha must be at least 1e-10. Infinite df is the normal reference and is stored as
  such.

**Sentence linter**

* Numbers are read by role and sign: "the effect was -4.2" or "the effect was 1.6"
  (the SE) no longer pass. A number whose role is unclear gets a `check` warning,
  even if it equals something in the result.
* Intervals are read as ordered pairs: reversed endpoints or the wrong interval
  conflict.
* p-value inequalities are compared exactly ("p <= 0.01" when p = 0.011 conflicts).
* "Compatible with" and "cannot be ruled out" check the direction ("compatible with
  a negative effect" when the interval is positive conflicts), and cite the interval
  the decision used. Under the standard policy, a 90%/95% disagreement gives a
  `check` that names both intervals.
* The declared scope no longer hides quantifiers ("All students..." with scope
  "students").
* `Part.spans` replaces `start`/`end`: one span per piece of text.

**Report**

* Printed threshold cut-offs are rounded in the safe direction, with the unrounded
  value beside them.
* The registration reference is always reported as unverified, and the timing
  disclaimer is always shown. The section is now "Declared plan (timing not verified)".
* Near-symmetric bounds are treated as asymmetric (no symmetric threshold summary).
* `Plan.fingerprint_for(1)` reproduces the 0.2.0 fingerprint format; reports show the
  fingerprint version. 0.3.0 changed the format by adding outcome and contrast.
* `raw_input` keeps the inputs as submitted; `checked_sentences` keeps every
  sentence checked with `res.check()` and its warnings. JSON schema
  `statwarrant-result/2`, strict JSON (`allow_nan=False`).
* Interval levels show the digits they need (99.9%, not 100%).

## 0.3.0

Changes prompted by a second review. The sentence checker gave a sentence-level
"allowed" to sentences such as "Scores increased and the treatment is safe", where
only "increased" had been checked.

**Breaking: the sentence checker is now a warnings-only linter**

* `check()` never approves a sentence. `CheckResult.status` is `warnings`,
  `no_warnings` or `no_supported_pattern`; `CheckResult.level` is `conflict`,
  `check` or `None`. The old `verdict` (`allowed` / `blocked` / `needs_care` /
  `unrecognized`) is removed.
* Each warning carries a rule id, the exact words from the sentence (with
  character offsets), the reason and what to check.
* `CheckResult.unchecked` lists the parts of the sentence no rule looked at.
* New warnings: Bayesian wording for a frequentist interval ("credible
  interval", "posterior"), claims about a subgroup or one group alone, and
  probability misreadings ("95% probability that the effect...", "due to chance").

**Every threshold at once**

* `Result.thresholds` / `Evidence.thresholds()`: two numbers that give the
  decision for every symmetric threshold. Below `met_below` the effect exceeds the
  threshold; above `equivalence_above` equivalence holds; in between, neither.
  Property-tested against `evaluate()` for both policies.

**Report**

* `declare(outcome=, contrast=, registration=)` and `analyze(label=)`. Outcome and
  contrast are part of the fingerprint; the registration link is not, so it can
  be added after registering.
* Markdown and JSON reports show what was compared, what was declared, every
  threshold at once and a list of what statwarrant does not verify. JSON has
  `schema: "statwarrant-result/1"`.

## 0.2.0

Fixes from an external review of 0.1.0. Several of these changed results; if you
used 0.1.0, rerun your analyses.

**Statistical fixes**

* statsmodels: degrees of freedom now follow statsmodels' own inference
  (`df_resid_inference`, e.g. G - 1 with cluster-robust errors). 0.1.0 used
  `df_resid`, which overstated significance with few clusters.
* scipy `ttest_1samp(x, popmean)` with `popmean != 0`: the effect is now
  `mean - popmean`. 0.1.0 tested the mean against zero.
* Minimal-effect test: alpha is split over the two directions under both policies.
  Under `"standard"`, 0.1.0 used 5% per side, so the type I error could approach 10%.
  The level conflict is redefined accordingly (equivalence at 90% while the 95%
  interval leaves the bounds).
* Inconclusive results are described with the 95% interval under both policies.
* Asymmetric intervals given with `ci=` and `estimate=` are refused; 0.1.0 warned and
  symmetrised them.
* Adapters verify themselves: if statwarrant cannot reproduce the p-value reported
  by the original result, it raises `AdapterMismatch`.
* Input validation: `baseline=0`, NaN degrees of freedom and infinite SESOI bounds
  are refused.

**Sentence checker**

* Verdicts list the parts that were checked (`CheckResult.parts`).
* Negated directions ("no increase", "not lower"), contradictory directions
  ("negative and significant" when positive), individual-level generalisations
  ("every student", "nobody") and wrong p-values are blocked.
* Numbers are checked: an effect size outside the interval is blocked, and a number
  that matches nothing in the result gives `needs_care`, never `allowed`.
* Size words ("large", "huge", "dramatic") are no longer treated as "exceeds the SESOI":
  they give `needs_care` at best. "Small", "negligible" and "slightly" are checked
  against equivalence.
* A negation the checker cannot attach to a claim gives `needs_care`.
* New: causal wording, evidence-strength wording, "marginally significant",
  hedges such as "not established" and "cannot be ruled out".

**Other**

* `Plan.fingerprint`: SHA-256 of the plan, to register before analysis. The README no
  longer implies that the timestamp is a preregistration.
* `Evidence` fields renamed: `equivalence_*` and `met_*` replace `bounds_*`;
  JSON output has `equivalence_test` and `minimal_effect_test`.
* CI builds the package, installs the wheel in a clean environment, tests the
  oldest supported NumPy and SciPy, and reports coverage.

## 0.1.0 (unreleased)

First public version.

* `declare()` then `analyze()`: SESOI with a required reason, fixed before analysis.
* Difference from zero, equivalence (TOST) and minimal effect (MET) from one plan.
* Interval policies `"single"` (default) and `"standard"`, with level-conflict detection.
* Claim contract: allowed statements, blocked statements with reasons, notes.
* `Result.check()`: pattern-based sentence checker (English).
* `Result.design()`: power, Type S and exaggeration ratio with exact truncated-normal moments.
* Inputs: estimate + SE, interval, scipy t-tests, statsmodels fits, paired item scores with optional cluster-robust SE.
* Markdown, JSON and dict output.

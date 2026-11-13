# Changelog

## Unreleased (0.5.1.dev0)

* Recognised subgroup wording now requires manual review rather than being marked
  consistent on the basis of overlapping words. This includes apparently exact matches.
* Recognised causal wording in a declared randomised study now requires manual review;
  a declared design and statistical significance do not verify the intervention,
  outcome, contrast, scope, or assumptions. Existing caution and observational-design
  rules retain limitations described in KNOWN_ISSUES.md.

These changes are not in the published 0.5.0 release. Recognition remains partial;
the new targeted tests are not a measure of accuracy on unseen sentences.

## 0.5.0

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

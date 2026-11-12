# Known issues in the 0.4.2 experimental alpha

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## Improvements in 0.4.2 and remaining limitations

Several specific examples reported for 0.4.1 improved, each with a regression test in
`tests/test_review5.py`. Independent review found related cases that still fail; see
the sections below. These examples are not a comprehensive validation:

* Some direct p-value and significance statements are bound to the named test,
  whether the name comes before or after the p-value, for equalities and inequalities.
  `"The equivalence test gave p < 0.05."` now conflicts when the equivalence-test
  p-value is 0.77, but other wordings remain unsafe.
* Decisions are computed from test statistics in which the bound is subtracted before
  dividing by the standard error, so a decision and its p-value agree near a threshold.
  The 0.4.1 example (`base = 1e9`) now gives `exceeds_sesoi = True` with p = 0.0058.
* The previously reported non-zero SciPy null value is recorded correctly, but other
  large-offset cases are still recorded incorrectly.
* Tested malformed p-values (negative, above 1) are refused, and some mismatched tiny
  p-values are compared on the log scale. Some extreme inputs are refused instead of
  producing non-finite intervals; other overflows remain possible.

## 1. The sentence linter is pattern-based

* **Named tests.** Some direct test-name and p-value expressions are bound correctly,
  but a comma can break the binding and cause the zero-test p-value to be used silently.
  For example, with zero-test p = 0.0111 and equivalence-test p = 0.7719,
  `For the equivalence test, p = 0.011.` is incorrectly marked consistent. Check the
  named test and p-value yourself, even if the linter reports no warnings.
* **Scales.** Numbers are compared on the scale of the analysis. A correct odds ratio
  for a log-odds result gets `check` ("cannot tell what this number stands for").
  The percentage-point heuristic may assume an outcome is a proportion merely because
  its values are within ±1, even if the units are metres or log-odds. It can also
  rescale numbers elsewhere in the same sentence that use a different scale. Verify
  every unit and conversion independently.
* **Other blind spots.** Unusual wording, long sentences with several claims, and
  claims about things statwarrant does not model (safety, mechanisms, other outcomes)
  may not be checked. Some unchecked words may not appear in the "not checked" list;
  for example a negated significance clause can hide a conflicting direction in a
  later clause. Some spans may be marked consistent even when they overlap another
  conflicting part, or when a combined direction-and-threshold claim is unsupported.
  Do not treat a `consistent` span as a substitute for human review of the whole claim.

## 2. Paired comparisons with few differing items

`analyze_paired` uses a t approximation. With fewer than 10 items that differ between
the two conditions it adds a caution note, but it does not compute an exact interval.
The threshold of 10 is a warning heuristic, not proof of adequacy when 10 or more
items differ. Choose any alternative analysis according to the outcome, the estimand,
sampling assumptions and clustering; an interval conditional on discordant pairs is
not automatically an interval for the marginal mean or accuracy difference.

## 3. Extreme numerical precision

The previously reported high-offset decision now agrees with its p-value, but its
printed "exact" threshold boundaries can contradict `thresholds.decision()` at the
boundary. One-ULP discrepancies also appear near a cutoff in ordinary-scale inputs.
At extreme offsets the SciPy adapter can record a small nonzero null value as zero.
A reported p-value of zero can also bypass a comparison with a representable tiny
recomputed p-value, so verification is not conclusive in that case. Very small
baselines can overflow relative-change calculations and prevent JSON export. Paired
integers larger than 2**53 can lose differences when converted to float. Independently
verify edge cases; centre or rescale inputs when appropriate.

## 4. Input provenance

`raw_input` is not a full archive of original data: model results and paired inputs are
summarized. Keep the original analysis and source data separately, subject to
appropriate privacy safeguards.

## 5. Checked-sentence privacy

`res.check()` stores the checked sentence and related details in future reports by
default. Use `res.check(sentence, record=False)` for a new check you do not want
recorded. To remove all recorded checks from future reports, use
`res.checked.clear()`. This does not remove text from already exported reports or
from `CheckResult` objects already returned to you. Inspect every report field,
including scope and other plan descriptions, before sharing confidential material.

## 6. Accuracy not measured

The linter's accuracy has not been measured on sentences annotated by independent
researchers. The sentences in the tests and in the first-user experiment were written and
labelled by the maintainers; several 0.4.2 fixes were designed on them, so their results
on those sentences are not evidence of accuracy on new ones.

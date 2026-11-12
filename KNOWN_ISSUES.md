# Known issues in the 0.4.2 experimental alpha

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## Fixed on the review branch, awaiting independent re-review

The cases reported in the first review of this branch are fixed, each with a regression
test in `tests/test_review6.py`. These fixes have not yet been re-reviewed independently.

* **Named tests across a comma.** `"For the equivalence test, p = 0.011."` (zero-test
  p = 0.0111, equivalence-test p = 0.7719) now gives `check`: when the clause names
  another test, a p-value or significance word is never marked consistent with the zero
  test.
* **Percentage points.** Conversion happens only when the declared units are a
  proportion (`accuracy`, `proportion`, `rate`, `probability`, `recall`, `AUC` and
  similar) and only for numbers attached to "percentage points" (or an interval in the
  parenthesis right after them). For other units, such as metres or log-odds, those
  numbers get `check`. Other numbers in the sentence are read as written; one that fits
  only after conversion gets `check`, not `conflict`.
* **Hidden directions.** A negation excuses direction words only in its own clause:
  `"The difference was not significant, and scores decreased."` now checks "decreased".
  "A small but significant decrease" is read as a size claim.
* **Printed cut-offs.** Each threshold cut-off is moved to the exact floating-point
  value at which `thresholds.decision()` changes, so the printed cut-offs never
  contradict it (property-tested).
* **Small nulls at extreme offsets.** When the data scale makes a small null value
  impossible to resolve (for example data near 1e14 tested against 0.5), it is recorded
  as 0 with a note saying so.
* **Reported p = 0.** Accepted only after the test statistic matches, with a note that
  the p-value itself could not be verified.
* **Tiny baselines** that overflow the relative change are refused.
* **Large integers.** Paired integer scores are subtracted exactly before conversion,
  so differences beyond 2**53 are kept.

Earlier fixes (0.4.2 before branch review) are listed in `CHANGELOG.md`.

## 1. The sentence linter is pattern-based

* **Named tests.** A p-value is bound to a test named in the same phrase or in the words
  just before its parenthesis; otherwise, if the clause names a test, the result is
  `check`. Wording outside these patterns can still be misread. Check the named test and
  p-value yourself, even if the linter reports no warnings.
* **Scales.** Numbers are compared on the scale of the analysis. A correct odds ratio
  for a log-odds result gets `check`. Percentage-point conversion depends on the
  declared units; declare them precisely and verify every unit and conversion.
* **Other blind spots.** Unusual wording, long sentences with several claims, and
  claims about things statwarrant does not model (safety, mechanisms, other outcomes)
  may not be checked. Not every unchecked word is guaranteed to appear in the "not
  checked" list. Some spans may be marked consistent even when they overlap another
  conflicting part, or when a combined claim is worded in a way the patterns do not
  cover. Do not treat a `consistent` span as a substitute for human review of the whole
  claim.

## 2. Paired comparisons with few differing items

`analyze_paired` uses a t approximation. With fewer than 10 items that differ between
the two conditions it adds a caution note, but it does not compute an exact interval.
The threshold of 10 is a warning heuristic, not proof of adequacy when 10 or more
items differ. Choose any alternative analysis according to the outcome, the estimand,
sampling assumptions and clustering; an interval conditional on discordant pairs is
not automatically an interval for the marginal mean or accuracy difference.

## 3. Extreme numerical precision

Decisions are computed from test statistics and the printed cut-offs follow
`thresholds.decision()` exactly, but inputs whose values differ only in their last
floating-point digits (SciPy then warns about precision loss) are themselves unreliable.
Null values smaller than the data's resolution cannot be recovered from a SciPy result.
Other overflows with extreme finite inputs may remain. Independently verify edge cases;
centre or rescale inputs when appropriate.

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
labelled by the maintainers and reviewers; many fixes were designed on them, so their
results on those sentences are not evidence of accuracy on new ones.

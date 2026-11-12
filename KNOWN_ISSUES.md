# Known issues in the 0.4.2 experimental alpha

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## Changes after the first review, with limitations

Changes addressing the first review's examples have regression tests in
`tests/test_review6.py`. A follow-up AI review confirmed improvements but also found
remaining cases below. This is not independent human validation.

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
* **Printed cut-offs.** Transition search now covers the finite binary64 domain and
  checks adjacent floating-point values. The previously reported cancellation and
  extreme-export examples have regression tests; this is not a proof for all inputs.
* **Small nulls at extreme offsets.** SciPy does not retain its original null. The
  adapter attempts to reconstruct it and discloses the approximate rounding scale.
  An unresolved value can be recorded as unknown (`null` in JSON); even an inferred
  zero cannot rule out a nonzero null below the numerical resolution.
* **Reported p = 0.** An ordinary recomputed probability now causes rejection. Tiny
  probabilities may still be accepted with an explicit note that the reported p-value
  is unverified and that numerical loss is only one possible explanation. Positive
  extreme p-values are checked using log tails where available.
* **Tiny baselines** that overflow the relative change are refused.
* **Large integers.** Paired differences are subtracted before float conversion, with
  regression tests for mixed signs and numeric types. Precision lost before values
  are passed to statwarrant cannot be recovered; unrepresentable differences are refused.

Earlier fixes (0.4.2 before branch review) are listed in `CHANGELOG.md`.

## 1. The sentence linter is pattern-based

* **Named tests.** A p-value is bound to a test named in the same phrase or in the words
  just before its parenthesis; otherwise, if the clause names a test, the result is
  `check`. Wording outside these patterns can still be misread. Check the named test and
  p-value yourself, even if the linter reports no warnings.
* **Scales.** Numbers are compared on the scale of the analysis. A correct odds ratio
  for a log-odds result gets `check`. Percentage-point conversion depends on the
  declared units; declare them precisely and verify every unit and conversion.
  A limited set of simple units next to an effect number can be matched or flagged
  for review; different units are not automatically converted. This is partial and
  pattern-based: units on other quantities, compound or unrecognised units and some
  phrasings may remain unchecked. Even a numeric match is not approval of a sentence.
* **Other blind spots.** Unusual wording, long sentences with several claims, and
  claims about things statwarrant does not model (safety, mechanisms, other outcomes)
  may not be checked. Not every unchecked word is guaranteed to appear in the "not
  checked" list. Some spans may be marked consistent even when they overlap another
  conflicting part, or when a combined claim is worded in a way the patterns do not
  cover. A specific construction "neither equivalence ... nor an effect ..." now asks
  for manual review, but other negations can still be misread. Do not treat a
  `consistent` span as a substitute for human review of the whole claim.
* **Direction and comparison order.** This development branch binds a very small set
  of exact English comparison and time-order sentences to an explicit `A minus B`
  contrast and matching outcome supplied by the user. Other recognized comparisons
  often receive `check`. The metadata themselves are not verified against the data.
  A SciPy result's null is reconstructed approximately, so exact named-group binding
  is withheld for that input; it is also withheld for an unknown or nonzero null.
  This is a partial safety guard, not general language understanding. A comparison cue
  or outcome may be missed entirely; a number, significance or direction span can still
  appear consistent or conflicting when the full claim has not been validated. For
  example, with no contrast declared, `Scores decreased over follow-up` can still get
  `no_warnings` while `over follow-up` is unchecked. Even `no_warnings` does not
  validate which group or time point is higher. Check the contrast, scales, outcome
  and complete sentence manually.

## 2. Paired comparisons with few differing items

`analyze_paired` uses a t approximation. With fewer than 10 items that differ between
the two conditions it adds a caution note, but it does not compute an exact interval.
The threshold of 10 is a warning heuristic, not proof of adequacy when 10 or more
items differ. Choose any alternative analysis according to the outcome, the estimand,
sampling assumptions and clustering; an interval conditional on discordant pairs is
not automatically an interval for the marginal mean or accuracy difference.

## 3. Extreme numerical precision

Decisions are computed from test statistics. Inputs whose values differ only in their
last floating-point digits (SciPy may warn about precision loss) are themselves
unreliable. SciPy's original null is not stored and must be reconstructed or reported
as unknown; the stated rounding scale is a diagnostic, not a confidence bound. Even
when the raw interval endpoints differ, displayed values are rounded; if the endpoints
have already collapsed to the same floating-point value, display cannot recover them.
Other overflows or precision failures with extreme finite inputs may remain. The tool
cannot repair an inaccurate input model fit: numerical conditioning depends on the
data and their scaling. Independently verify edge cases; centre or rescale inputs when
appropriate and retain the original analysis.

Some extreme positive p-values are recovered on a log scale; when a probability
underflows or a tail calculation is unavailable, zero is not an exact probability
and the linter requests manual review. Student-t tail recovery uses floating-point
quadrature in some cases and has not been proven accurate for all inputs. A critical
value that does not invert its own reference tail within tolerance is rejected, which
prevents some failures at exceptionally small degrees of freedom; this check alone
cannot guarantee accuracy. Exact integer inputs that cannot be represented without
loss as floats are refused, but pre-rounded floats and earlier model outputs cannot be
recovered. Binary64 and input-model limitations still apply.

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

## 7. Development snapshots share the same version

The `release-0.4.2` and validation branches contain different source code but both
report version `0.4.2`. When one is already installed, an ordinary pip install from
a different commit can keep the old code. Use `--force-reinstall --no-deps` for the
chosen Git commit after installing its dependencies, and verify the installed commit
or source-file hashes. Version text alone is insufficient to identify the snapshot.

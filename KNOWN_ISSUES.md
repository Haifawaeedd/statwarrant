# Known issues in the 0.5.0.dev0 experimental alpha

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## 0.5.0.dev0 follow-up review — changed on this branch, not yet re-reviewed

An independent review reproduced the failures below on commit `fff60a1`. Changes addressing
each have regression tests in `tests/test_review_050.py`; they have not been reviewed again.
They are targeted counterexamples, not estimates of frequency.

* **Coordinated negation could hide other claims.** `The data support neither a difference
  nor equivalence and prove the treatment caused harm for everyone.` was one `consistent`
  span. Each "neither ... nor" item is now a short phrase that stops at a clause boundary
  or conjunction, so "prove", "caused" and "for everyone" are checked. An item that names
  something other than the declared outcome or contrast (`a difference in mortality`), or
  its own margin, gets `check`. Items longer than eight words are not read as this
  construction at all.
* **Ratio types and comparison order.** `risk doubled` with a log-odds result was
  `consistent`, and so was the reverse treatment/control order. A ratio is now compared
  only when the sentence's quantity (odds, risk, rate, hazard) matches the log scale named
  in the units; it is never `consistent`, because statwarrant does not verify which group
  is the numerator, and it is a `conflict` only when the factor is ruled out in both
  orders. Negated ratio wording and factors whose clause names no quantity get `check`.
  The units must say what was logged (`log-odds`, `log rate ratio`); `log ratio` alone is
  not enough. Verify the quantity, base and order yourself.
* **Interval endpoint and sign.** With estimate -2 and SE 0.1, `could be as high as 2.2`
  was `consistent`. "As high as" and "as low as" are now compared with the matching end and
  its sign; "as large as" with no stated sign gets `check` when the matching end is
  negative; "as small as" gets `check` when the interval includes zero.
* **Unsupported wording raised.** `The odds were two fold.` raised `KeyError`; it now gets
  `check`. Random combinations of ratio, negation and interval wording (5,000 sentences)
  raised no exception; that is not a proof for all inputs.

The release workflow runs only when the repository owner starts it by hand and types a
confirmation, and PyPI uploads must run from a version tag. Naming a GitHub environment
still does not require approval by itself, and the workflow cannot check the environment's
settings: configure the `pypi` environment's required reviewers before any trusted
publisher. The quick-start notebook now installs this branch (`integrate/0.5.0`) and prints
the installed commit.

## Third user trial (new data, sentences frozen before checking)

Three real datasets (RAND Health Insurance Experiment, credit-card expenditure, two
classifiers on the breast-cancer data) and 24 sentences labelled before any check were
run on commit 8ad4164. The sentences and labels were written by an AI that had also
written linter rules, so this is not an independent evaluation, and 24 sentences give
very wide uncertainty.

* **Statistics.** statwarrant read the fitted models exactly (estimates, SEs, p-values
  and decisions). This was an extraction check against the same fitted models, not an
  independent re-analysis.
* **The analyses had problems statwarrant cannot see.** The RAND rows come from 5,912
  people observed repeatedly; row-level robust SEs understate uncertainty (person-
  clustered SE 0.0110 instead of 0.0072). statsmodels' `lncoins` disagrees with the
  source file's `logc` in 4,855 rows; with `logc` and clustering, equivalence within the
  illustrative threshold is no longer established. statwarrant interprets the numbers it
  is given; it does not check the model, the coding or the standard errors.
* **Sentence checker on 8ad4164:** 10 of 13 problem sentences got a warning; 9 of 11
  acceptable sentences got one (8 `check`, 1 `conflict`). Any warning on any part was
  counted, so a "caught" problem was not always caught for the right reason.
  "Coinsurance halved the number of doctor visits.", "Homeowners and renters spent the
  same amount." and "Home ownership was unrelated to credit-card spending." were not
  recognised at all (`no_supported_pattern`). "Neither a difference nor equivalence
  could be shown." got a false `conflict`.
* **On this integration branch:** 11 of 13 and 7 of 11 (all `check`, no `conflict`).
  The rules that changed these numbers were written before the sentences, but by the same
  author, so the improvement is optimistic. The remaining `check` warnings on acceptable
  sentences come from comparisons that cannot be tied to the declared contrast, numbers
  whose role is unknown (group accuracies, item counts, ratio-scale values) and
  percentages whose scale is not stated. The linter was not changed for these 24
  sentences; they stay an evaluation set for this version only.

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
  A design table with an assumed effect tiny relative to the SE could still break JSON
  export until 0.5.0.dev0, which refuses such effects with a message.
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
* **Ratio wording.** Ratio words are judged only when their clause names a ratio
  quantity (odds, risk, rate, hazard, likelihood, chance, probability, incidence), and
  only for log-scale units or with a declared baseline; otherwise they get `check`.
  "Halved the number of visits" is not recognised. "Doubled the dose" in such a clause
  would be misread as a claim about the result.

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

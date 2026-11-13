# Known issues in statwarrant 0.5.0 (experimental alpha)

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## Review of the 0.5.0 release candidate

A review of the release candidate (draft pull request #1, commit `a5269d0`) reproduced the
four cases below while all tests passed. Changes have regression tests in
`tests/test_review_release_050.py`. A subsequent review of `c237c3d` found additional
edge cases; the follow-up changes have targeted tests in `tests/test_safety_*_050.py`.
These examples are not an estimate of accuracy on new data or sentences.

* **Relative change of a ratio.** `analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True,
  baseline=0.2)` reported a relative change of about -90%: the log of the ratio was divided
  by the baseline. A baseline is refused with `ratio=True` or recognized log-scale units
  in both `analyze()` and `analyze_paired()`; common `log2`, `log10`, `lnRR` and `logit`
  labels are included. Free-text detection is partial: an unrecognized or unstated
  transformed scale can still be treated as linear. The original ratio 0.83 corresponds
  to -17%; the -16.5% previously shown is for its reconstructed geometric midpoint
  (about 0.8352), not for the number 0.83. The ratio quantity and order matter.
* **Estimate and midpoint.** `analyze(estimate=4.4, ci=(1.0, 7.4))` used the midpoint 4.2
  and said rounding explained the difference. The symmetry check still assumes a common
  decimal precision when estimating its rounding allowance: here the assumed allowance is
  0.1 and the gap is 0.2, but floats do not reveal the actual precision of each printed
  number or why they differ. The note states those assumptions and requests review.
  `raw_input["estimate_vs_midpoint"]` records the two analysis-scale values, their scale,
  the assumed allowance and a conditional comparison. Its `explained_by_rounding` value is
  now `null`/`None`, not a Boolean: code consuming that field should be updated.
  The acceptance tolerance itself (5% of the half-width plus the allowance) is unchanged;
  scientific-notation float representations still get a zero allowance in this heuristic
  and may be rejected even if a different printed precision could explain the discrepancy.
* **Ratio display and numerical range.** Small changes and close CI limits need extra
  displayed digits; if the transformed ratio or percentage cannot be represented safely,
  the ratio summary is omitted with a note and the evidence remains on the log scale.
  A displayed CI is calculated at `1 - alpha`; this need not equal the input CI level.
  `ratio=True` analyses on the natural-log scale and refuses known non-natural or unclear
  bases in the units; the unit name is free text, so unknown spellings can be missed.
  The linter requests review of ratio-factor claims with recognized non-natural or unclear
  bases, and will not convert percentage points directly against recognized log/ratio units.
* **Difference between p-values.** `The difference in p-values was 0.0111.` was read as a
  p-value equal to the result's. Differences, changes, gaps and comparisons between
  p-values, "the p-values differed" and "p dropped from 0.04 to 0.01" now get `check`
  (the last was a false direction conflict): a difference between p-values is not the
  p-value of any test. Other phrasings are not recognised.
* **Claims after "neither equivalence nor an effect larger than ...".** The size qualifier
  took the rest of the sentence, so "and prove the treatment caused harm for everyone" was
  not checked. The qualifier now stops at a conjunction, a relative pronoun or a verb
  (at most eight words); the rest of the sentence is checked as usual.

Found while re-testing, not changed: a "sentence" of thousands of characters with no
punctuation can take seconds to check, because some clause patterns scan back over the
whole run of words. Ordinary text is not affected (a 3,000-character paragraph takes
milliseconds); the patterns will be bounded in 0.6.0.

## Review of the 0.5.0 development branch — changed, not yet re-reviewed

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
publisher. The quick-start notebook installs the released version and prints the
installed commit.

## Sentences from published papers

41 excerpts from six published studies (five randomised trials and one cohort; 33 from
the papers, 8 from news and summaries) were linked by hand to the 19 results they
describe and labelled before any check. The labeller is an AI, 15 excerpts are clauses
(the retrieval tool limited quotes to 125 characters), and 32 of the 41 are correct
wording, so this mainly measures noise on real text.

* **Before the 0.5.0 fixes** (commit 248714d, contrast declared): 27 of 32 correct
  excerpts got a warning, one a false `conflict` ("does not prove cause and effect"), and
  5 of 18 published estimates could not be entered with their rounded interval.
* **After** (design, subgroup and ratio inputs, counts skipped, cautions read, separate
  display): no correct excerpt gets a `conflict`, all 18 estimates are accepted, and the
  parts to verify on correct excerpts fell from 50 to 33. These fixes were made after
  seeing the excerpts, so the improvement is optimistic.
* **What remains.** 25 of 32 correct excerpts still have parts to verify, mostly
  direction words (18) that cannot be tied to the declared contrast; declaring group
  names is not supported yet. Of the 4 problem excerpts, one gets a `conflict` (an
  importance claim without a threshold), two only parts to verify, and one is not
  recognised ("but not among those receiving no respiratory support"). "The trial did
  not show a difference" is not recognised. Causal claims in other words ("may extend
  your life") are not recognised.
* **p-values from rounded intervals.** Recomputed from the printed interval, 3 of 7
  published two-sided p-values differ at their printed precision (for example 0.727
  against 0.69). statwarrant does not compare a sentence's p-value with tolerance for
  this rounding. Do not assume rounding is the cause; check the original analysis,
  model, confidence level and precision.

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
* **On the earlier integration branch:** 11 of 13 and 7 of 11 (all `check`, no `conflict`).
  A later replay on `c237c3d` found 11 of 13 problem sentences with some warning and
  6 of 11 acceptable sentences with `check`, none with `conflict`; one sentence formerly
  warned about was no longer recognized. The rules were written by the same
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
  parenthesis right after them). For other units, such as metres or recognized log/ratio
  scales, those
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

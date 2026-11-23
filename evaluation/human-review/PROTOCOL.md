# Evaluation protocol: does statwarrant flag conclusions the result does not support?

Version 0.1 (draft, 2026-11-22). Fixed before any sentence is collected; changes after that
are recorded below with a date and a reason. Field-level instructions for reviewers are in
[README.md](README.md).

## Question

On conclusion sentences from published randomised trials, how often does statwarrant
0.5.3 (a) give no warning on a conclusion that human reviewers judge unsupported by the
reported result (false reassurance), and (b) give a conflict on a conclusion they judge
supported (false alarm)?

## Sample

* **Source:** PubMed records with publication type "Randomized Controlled Trial",
  published in 2025, English abstract, whose abstract reports at least one effect estimate
  with a confidence interval.
* **Draw:** a random sample of records (the search string, date and random seed are
  recorded before drawing). Records are screened in the drawn order; excluded records and
  reasons are logged.
* **Unit:** one case per paper: the **first sentence of the abstract's Conclusions** (or the
  last sentence of the abstract if it has no Conclusions heading), checked against the
  **primary-outcome estimate and interval** reported in the same abstract. One sentence per
  paper keeps cases independent.
* **Size:** pilot of 30 papers to test this protocol, then a main sample of 150 new papers
  (no overlap with the pilot). The pilot is reported separately and never pooled.

## Smallest effect size of interest (SESOI)

Taken only from the paper: a stated non-inferiority or equivalence margin, or a minimal
clinically important difference named in the paper. Its source is quoted in `cases.csv`.
If the paper states none, the case is analysed **without a SESOI**, and claims of size or
importance in it are judged by reviewers on the paper's own terms; the two strata are
reported separately. Nobody invents a SESOI for a paper.

## Labels

Two reviewers (a statistician and a researcher who reports trial results) label each
sentence independently as `supported`, `unsupported` or `unclear`, with a short reason,
seeing the sentence and the abstract but **never the tool's output**. Reviewer files are
locked, then disagreements are adjudicated by a third person or by discussion recorded in
`adjudication.csv`. A sentence is *misleading* if its adjudicated label is `unsupported`,
*faithful* if `supported`; `unclear` cases are counted and reported but not scored.

## Tool run

After the labels are locked: `pip install statwarrant==0.5.3`, then `run_frozen.py`. The
library is not changed during the evaluation; problems found go to KNOWN_ISSUES.md.

## Outcomes (reported with 95% Wilson intervals)

1. False reassurance: misleading sentences with no warning at all.
2. Misleading sentences given a conflict; given any warning.
3. False alarm: faithful sentences given a conflict.
4. Share of all sentences sent to review ("to verify" only).
5. Cases the tool could not run, with reasons.
6. Reviewer agreement before adjudication (Cohen's kappa).

No single accuracy figure is reported: misleading sentences may be a minority, so accuracy
would mostly reflect the base rate.

## Limits stated in advance

One field (randomised trials), English only, abstracts only, one conclusion sentence per
paper. Results do not generalise to other designs, full texts or other languages. The
author built the tool; reviewers and the adjudicator are independent of its development.

## Changes

| Date | Change | Reason |
| --- | --- | --- |
| | | |

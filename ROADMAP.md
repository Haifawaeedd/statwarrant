# Roadmap

## 0.5.x: rule checker

Fix sentences reported through the issue forms, keep the conflict rate on correct text near
zero, and report held-out results in [VALIDATION.md](VALIDATION.md).

## 0.6.0: optional reader layer

Status: released in 0.6.0 (structured assertions, `res.review()`, MCP server, relevance test,
estimand). The reader is released as **experimental** before step 4: its accuracy has not been
measured, and it stays labelled experimental until it is. Still to do: step 4 (evaluation) and
the within-group change warning.

Rules match words; they cannot judge meaning. Some overclaims need a reader:

* a measure described as a broader ability ("51 points better at medical reasoning" when
  the outcome was strict answer correctness);
* a claim about a different comparison, population or outcome than the one analysed;
* reversed direction or size claims in wording the rules do not cover.

Plan:

1. **Blind reading.** A language model reads only the sentence and a one-line description
   of the study, never the result, and chooses what the sentence says the study found
   (clear benefit, uncertain benefit, negligible effect, inconclusive, no meaningful
   difference, harm, or cannot tell).
2. **Comparison with the contract.** statwarrant compares that reading with the situation
   it computes from the estimate, interval and smallest effect size of interest. A mismatch
   is reported as "a reader would take this sentence to mean X; the result shows Y".
3. **Separate and optional.** The reader is an extra, off by default, with the model and its
   answers recorded. It never turns a rule conflict into a pass and never approves a
   sentence; it can only add a warning.
4. **Measured before it loses the experimental label.** The reader is evaluated against the human reader study and
   against at least one model from a different provider, with results published in
   VALIDATION.md.

Other items for 0.6.0: a warning when a within-group change is reported while a control
group exists, and preparation for pyOpenSci review.

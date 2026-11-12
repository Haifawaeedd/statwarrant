# Known issues in the 0.4.1 experimental alpha

These are known, unresolved issues. The examples are targeted checks, not estimates
of how often errors occur. Use statwarrant as an aid, not an automated validator;
independently check calculations and the full text of research claims.

## 1. Named tests in sentence checks

A p-value inequality or a significance statement naming an equivalence or
minimal-effect test can be checked against the zero test instead. For example:

```python
import statwarrant as sw

r = sw.declare(sesoi=3, sesoi_source="example", interval_policy="standard").analyze(
    estimate=4.2, se=1.6, df=58
)
print(r.evidence.p_zero)         # about 0.0111
print(r.evidence.p_equivalence)  # about 0.7719
print(r.check("The equivalence test gave p < 0.05.", record=False))
```

In 0.4.1 the linter marks `p < 0.05` consistent even though the equivalence-test
p-value is greater than 0.05. `no_warnings` is not sentence approval, but this
recognized-part judgment is still wrong. It can also produce false warnings for
correct named-test sentences. Compare each sentence with the p-value and threshold
for the specific named test yourself.

The linter also has other known blind spots, including claims combining a direction
and a practical threshold. Some spans may be marked consistent even when they overlap
another conflicting part. Do not treat a `consistent` span as a substitute for human
review of the whole claim.

## 2. Extreme precision near a threshold

When an estimate and a threshold are separated by only a few floating-point steps,
rounding an interval endpoint can make the minimal-effect decision disagree with the
reported p-value. One extreme example is below; SciPy warns that the original data
have suffered precision loss.

```python
import numpy as np
from scipy import stats
import statwarrant as sw

base = 1e9
step = np.spacing(base)
x = base + np.tile([-1., 1.], 15) * (4 * step)
d = float(base - 2 * step)
r = sw.declare(sesoi=d, sesoi_source="numerical test fixture").analyze(
    stats.ttest_1samp(x, 0)
)
print(r.evidence.p_minimal_effect, r.evidence.met_threshold,
      r.evidence.exceeds_sesoi, r.thresholds.decision(d))
# approximately: 0.005827 0.025 False undetermined
print(stats.ttest_1samp(x - base, d - base, alternative="greater").pvalue)
# approximately: 0.005827
```

For results close to a boundary, especially when SciPy warns about numerical
precision, verify with an independent calculation and an appropriately centered or
rescaled analysis. Do not assume that rescaling alone fixes every problem.

## 3. SciPy null value and input provenance

For some large-offset SciPy tests, the tested difference and p-value can be correct
while the report incorrectly records a nonzero null as zero. Check the original
SciPy call and do not use the recorded `null_value` as the only source of provenance.

`raw_input` is not a full archive of original data: model results and paired inputs
are summarized. Keep the original analysis and source data separately, subject to
appropriate privacy safeguards.

## 4. Other numerical limitations

The adapter p-value cross-check can accept disagreeing, representable p-values when
both are extremely small; it can also accept a malformed negative tiny p-value. This
was demonstrated with deliberately inconsistent result objects, not with ordinary
unmodified model results. Very large but finite inputs can produce non-finite derived
intervals and cause strict JSON export to fail. Independently check extreme inputs.

If you used 0.4.0 on SciPy results for data far from zero relative to their spread,
rerun and independently check those analyses: 0.4.1 corrects a standard-error
reconstruction defect for the previously reported example.

## 5. Checked-sentence privacy

`res.check()` stores the checked sentence and related details in future reports by
default. Use `res.check(sentence, record=False)` for a new check you do not want
recorded. To remove all recorded checks from future reports, use
`res.checked.clear()`. This does not remove text from already exported reports or
from `CheckResult` objects already returned to you. Inspect every report field,
including scope and other plan descriptions, before sharing confidential material.

"""statwarrant on results from two published randomised trials.

Numbers are as printed in the papers. The sentences are adapted from the papers' wording,
except the second subgroup sentence, which is a deliberate misreading for comparison.
RECOVERY Collaborative Group, N Engl J Med 2021;384:693-704 (dexamethasone).
Manson et al., N Engl J Med 2019;380:33-44 (VITAL, vitamin D).
"""

import statwarrant as sw

# 1. Dexamethasone: 28-day mortality, rate ratio 0.83 (95% CI 0.75 to 0.93), as printed.
dexa = sw.declare(units="log rate ratio", outcome="28-day mortality", contrast="dexamethasone vs usual care",
                  design="randomised", scope="hospitalised Covid-19 patients, UK, 2020")
res = dexa.analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True, label="RECOVERY, all patients")
print(res)
print()
print(res.check("Dexamethasone resulted in lower 28-day mortality than usual care.", record=False))
print()

# 2. The subgroup with no respiratory support: rate ratio 1.19 (0.91 to 1.55).
none = sw.declare(units="log rate ratio", outcome="28-day mortality", contrast="dexamethasone vs usual care",
                  design="randomised", subgroup="patients receiving no respiratory support")
sub = none.analyze(estimate=1.19, ci=(0.91, 1.55), ratio=True, label="RECOVERY, no respiratory support")
for sentence in [
    "There was no evidence that dexamethasone provided any benefit among patients who were not receiving "
    "respiratory support.",
    "Dexamethasone had no effect among patients who were not receiving respiratory support.",
]:
    print(sub.check(sentence, record=False))
    print()

# 3. VITAL: invasive cancer, hazard ratio 0.96 (0.88 to 1.06). Without a declared margin,
#    statwarrant does not let "no effect" stand for "not significant".
vital = sw.declare(units="log hazard ratio", outcome="invasive cancer", contrast="vitamin D vs placebo",
                   design="randomised", scope="US adults aged 50 and over")
res = vital.analyze(estimate=0.96, ci=(0.88, 1.06), ratio=True, label="VITAL, invasive cancer")
print(res.check("Supplementation with vitamin D was not associated with a lower risk of invasive cancer.",
                record=False))

# Experiment: statwarrant 0.6.0 vs LLMs on MedLitSpin (written before any statwarrant run)

Data: MedLitSpin (Yun et al., CHIL 2025; Apache-2.0), data/spin_and_no_spin_abstracts.csv.
60 abstracts of 30 cancer RCTs with non-significant primary outcomes: 30 with spin (Boutron et al. 2014,
SPIIN) and 30 neutral rewrites. Label = abstract_type. Labels are external to this project.

Primary result per trial: extracted from the NEUTRAL abstract only (numbers are shared by both versions),
before running statwarrant, into extraction.csv. Represented as a signed z statistic (estimate = z,
SE = 1, normal reference): positive = favours treatment A. z comes from the reported CI when a ratio
with CI is given (z = -ln(ratio)/SE_log for hazard ratios; +ln(OR)/SE_log for odds ratios of a good
outcome), else from the reported two-sided p and the direction of the reported summaries, else from
the reported counts (two-proportion z). No SESOI is declared (none is reported).

Text checked: the abstract's conclusion = text after the last "Conclusion(s):", "Interpretation:" or
"In conclusion,"; if none, the last two sentences. Same rule for both versions.

Conditions
A. statwarrant 0.6.0 rules: res.check(conclusion). Flag spin if >= 1 conflict. Secondary: any warning.
B. LLM alone: the published per-model results of Yun et al. (22 LLMs, same 60 abstracts, prompt in
   code/run_spin_detection_evaluation.py), plus new runs of current Claude models with the same prompt.
C. LLM reads, statwarrant decides: res.review(conclusion, llm) with replayed model outputs; flag spin
   if any asserted claim is contradicted or not established, or any rule conflict.
D. Numbers: statwarrant zero-test p-values vs SciPy / statsmodels on the extracted results, and vs the
   p-values printed in the abstracts.

Metrics: accuracy, sensitivity (spin flagged), specificity (neutral not flagged), with 95% Wilson
intervals; paired comparison by exact McNemar where per-abstract predictions exist.
All results are reported whatever they show. No rule in statwarrant is changed for this data.

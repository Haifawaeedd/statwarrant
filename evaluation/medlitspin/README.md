# statwarrant vs language models on MedLitSpin

Open `statwarrant_medlitspin_experiment.ipynb` in Jupyter and run all cells (Kernel → Restart & Run All).
It already contains the outputs from a full run, so you can read it before running it.

Requirements: `pip install statwarrant==0.6.0 pandas scipy statsmodels` (0.6.1 gives the same results).

Folders
- `data/` — MedLitSpin abstracts and labels (Apache-2.0, licence included), the protocol, both extractions, the code key.
- `published_llm_outputs/` — per-abstract answers of the 22 models published by Yun et al. (2025).
- `llm_answers/` — the Claude answers recorded for this study, and the exact texts the models were given.

`data/primary_linked.csv` classifies each conflict raised by the rules by whether it concerns the primary
result (one rater). The Claude runs used the "haiku", "sonnet" and "opus" models of Anthropic's agent
framework on 27 November 2026, 30 items per context; exact model identifiers were not logged.

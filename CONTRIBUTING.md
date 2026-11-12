# Contributing to statwarrant

Thank you for helping. The most valuable contributions right now are:

1. **Sentences the linter handles wrongly.** If `res.check()` warns about something
   that is fine, or misses a misreading, open a
   [feedback issue](https://github.com/Haifawaeedd/statwarrant/issues/new?template=feedback.yml)
   with the sentence, the numbers, and the warning you expected.
2. **New input adapters** for results you use often.
3. **Clearer wording** for allowed claims and reasons.

## Ground rules

* Every statistical method must cite its published source in the docstring.
* Implement from the publication. Do not translate code from GPL-licensed packages
  (for example TOSTER or pingouin); their numeric output may be used as test references.
* Any change to allowed claims must keep `tests/test_claims.py::test_allowed_claims_never_fail_the_checker` passing:
  the contract's allowed statements must never trigger a linter warning.
* The linter never approves a sentence. New rules add warnings; they do not add verdicts.
* Add a test for every bug you fix.

## Development

```bash
git clone https://github.com/Haifawaeedd/statwarrant
cd statwarrant
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest
```

## Conduct

Be kind and specific. Disagreements about statistics are welcome; personal attacks are not.

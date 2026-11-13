"""Everything statwarrant writes can be printed on a Windows code page (cp1252).

A redirected or older Windows console uses the locale encoding; a character outside it
(such as an 'approximately equal' sign) raised UnicodeEncodeError when printing a report.
"""

import json

import pytest

import statwarrant as sw


def _outputs():
    plan = sw.declare(sesoi=3, sesoi_source="teachers", units="points", outcome="score", contrast="new minus old",
                      design="randomised", subgroup="first-year students", scope="one university")
    res = plan.analyze(estimate=4.2, se=1.6, df=58)
    res.check("The new method improved scores by about 4 points (95% CI 1.0 to 7.4) for all students.")
    res.check("Neither equivalence nor an effect was established.")
    table = res.design([2, 3], source="earlier studies")
    ratio = sw.declare(units="log hazard ratio", design="observational").analyze(estimate=0.83, ci=(0.75, 0.93),
                                                                                ratio=True)
    paired = sw.declare().analyze_paired([1, 0, 1, 1, 0, 1, 1, 1], [0, 0, 1, 0, 0, 1, 0, 1])
    for r in (res, ratio, paired):
        yield str(r)
        yield r.to_markdown()
        yield r.to_json()
    yield str(table)
    yield table.to_markdown()
    yield str(res.check("The difference was small and not significant (p = 0.011).", record=False))


# Windows ANSI code pages used when output is redirected (Western, Cyrillic, Arabic, Japanese, Chinese)
@pytest.mark.parametrize("encoding", ["cp1252", "cp1251", "cp1256", "cp932", "cp936"])
def test_output_encodes_on_windows_code_pages(encoding):
    for text in _outputs():
        text.encode(encoding)


def test_json_is_plain_ascii_safe():
    for text in _outputs():
        if text.lstrip().startswith("{"):
            json.loads(text)

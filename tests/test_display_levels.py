"""Conflicts are shown as warnings; parts that could not be verified are listed separately."""

import statwarrant as sw

RES = sw.declare(sesoi=3, sesoi_source="test", units="points", outcome="exam score",
                 contrast="new method minus existing method", scope="one university").analyze(
    estimate=4.2, se=1.6, df=58)


def test_conflicts_and_unverified_parts_are_separate():
    out = RES.check("The new method improved scores by about 4 points and is safe for all students.", record=False)
    text = str(out)
    assert text.startswith("[1 conflict, 2 to verify]")
    assert text.index("Conflicts with the result:") < text.index("Not verified")
    assert [p.rule for p in out.conflicts] == ["generalization"]
    assert {p.rule for p in out.to_verify} == {"direction", "magnitude"}
    d = out.to_dict()
    assert len(d["conflicts"]) == 1 and len(d["to_verify"]) == 2 and len(d["warnings"]) == 3


def test_check_only_result_says_no_conflicts_and_is_not_a_clearance():
    out = RES.check("The new method improved scores.", record=False)
    text = str(out)
    assert text.startswith("[no conflicts, 1 to verify]")
    assert "Conflicts with the result" not in text
    assert "not a clearance" in text
    assert out.level == "check"  # the API level is unchanged

"""Run one frozen statwarrant version on cases.csv, after the human reviews are frozen.

    python run_frozen.py cases.csv --version 0.5.3 --out tool_outputs.csv

Refuses to run on any other installed version, records the input file's SHA-256, and never
reads the reviewer or adjudication files. Each case is checked against the result described
by its own columns; cases without an estimate and an SE or interval are reported as
"not runnable", never dropped.
"""
import argparse
import csv
import hashlib
import json
import math
import sys

import statwarrant as sw


def num(row, key):
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def text(row, key):
    v = (row.get(key) or "").strip()
    return v or None


def plan_for(row):
    kw = {}
    low, high = num(row, "sesoi_lower_bound"), num(row, "sesoi_upper_bound")
    if low is not None and high is not None:
        kw["sesoi"] = (low, high)
    elif num(row, "sesoi_reported_value") is not None:
        kw["sesoi"] = abs(num(row, "sesoi_reported_value"))
    if "sesoi" in kw:
        kw["sesoi_source"] = text(row, "sesoi_justification") or text(row, "sesoi_provenance") or "reported in source"
    better = (text(row, "outcome_benefit_direction") or "").lower()
    if better in ("higher", "lower"):
        kw["better"] = better
    for key, col in (("units", "outcome_unit"), ("outcome", "outcome_name"), ("contrast", "contrast_definition")):
        if text(row, col):
            kw[key] = text(row, col)
    design = (text(row, "study_design") or "").lower()
    if any(w in design for w in ("random", "rct")):
        kw["design"] = "randomised"
    elif any(w in design for w in ("observational", "cohort", "case-control", "cross-sectional")):
        kw["design"] = "observational"
    return sw.declare(**kw)


def result_for(plan, row):
    est = num(row, "estimate_value")
    if est is None:
        raise ValueError("no estimate_value")
    kw = {"estimate": est}
    se, low, high = num(row, "standard_error_value"), num(row, "ci_lower"), num(row, "ci_upper")
    if se is not None:
        kw["se"] = se
    elif low is not None and high is not None:
        kw["ci"] = (low, high)
        level = num(row, "ci_level")
        if level is not None:
            kw["ci_level"] = level / 100 if level > 1 else level
    else:
        raise ValueError("no standard_error_value and no ci_lower/ci_upper")
    if num(row, "df_denominator") is not None:
        kw["df"] = num(row, "df_denominator")
    return plan.analyze(**kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--version", required=True, help="the frozen version, e.g. 0.5.3")
    ap.add_argument("--out", default="tool_outputs.csv")
    a = ap.parse_args()
    if sw.__version__ != a.version:
        sys.exit(f"installed statwarrant is {sw.__version__}, not the frozen {a.version}; "
                 f"run: pip install statwarrant=={a.version}")
    raw = open(a.cases, "rb").read()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    out = []
    for row in rows:
        rec = {"case_id": row.get("case_id", ""), "statwarrant_version": sw.__version__}
        try:
            res = result_for(plan_for(row), row)
            chk = res.check(row["sentence_text"], record=False)
            rec.update(runnable="yes", tool_level=chk.level or "none",
                       conflicts=sum(p.status == "conflict" for p in chk.parts),
                       checks=sum(p.status == "check" for p in chk.parts),
                       parts=json.dumps([[p.rule, p.status, p.text] for p in chk.parts], ensure_ascii=False),
                       output=str(chk))
        except Exception as e:  # recorded, never dropped
            rec.update(runnable="no", tool_level="", conflicts="", checks="", parts="", output=f"not runnable: {e}")
        out.append(rec)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ["case_id"])
        w.writeheader()
        w.writerows(out)
    meta = {"statwarrant_version": sw.__version__, "cases_file": a.cases,
            "cases_sha256": hashlib.sha256(raw).hexdigest(), "n_cases": len(rows),
            "n_runnable": sum(r["runnable"] == "yes" for r in out)}
    json.dump(meta, open(a.out + ".meta.json", "w"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()

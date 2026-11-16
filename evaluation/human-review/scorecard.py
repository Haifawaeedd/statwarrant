"""Scorecard: frozen statwarrant outputs against adjudicated human labels.

    python scorecard.py --cases cases.csv --tool tool_outputs.csv --adjudication adjudication.csv \
        --reviewer-a reviewer_A.csv --reviewer-b reviewer_B.csv --out scorecard.md

Sentence-level reading of the claim-level labels:
  misleading  at least one adjudicated claim is "unsupported"
  faithful    every adjudicated claim is "supported"
  unclear     anything else (reported, not scored)

Reported, each with a 95% Wilson interval:
  false reassurance  misleading sentences given no warning at all (the most serious error)
  caught             misleading sentences given a conflict; given any warning
  false alarm        faithful sentences given a conflict
  sent to review     sentences whose only warnings are "to verify"
plus reviewer agreement (A vs B, before adjudication) and the cases that could not be run.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict


def rows(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


def sentence_label(labels):
    labels = [l.strip().lower() for l in labels if l and l.strip()]
    if not labels:
        return None
    if "unsupported" in labels:
        return "misleading"
    if all(l == "supported" for l in labels):
        return "faithful"
    return "unclear"


def by_case(path, key):
    d = defaultdict(list)
    for r in rows(path):
        d[r["case_id"]].append(r.get(key, ""))
    return {k: sentence_label(v) for k, v in d.items()}


def wilson(k, n):
    if n == 0:
        return None, None, None
    z, p = 1.959964, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, c - h), min(1.0, c + h)


def kappa(a, b):
    keys = [k for k in a if k in b and a[k] and b[k]]
    if not keys:
        return None, 0
    cats = sorted({a[k] for k in keys} | {b[k] for k in keys})
    po = sum(a[k] == b[k] for k in keys) / len(keys)
    pe = sum((sum(a[k] == c for k in keys) / len(keys)) * (sum(b[k] == c for k in keys) / len(keys)) for c in cats)
    return (None if pe == 1 else (po - pe) / (1 - pe)), len(keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--tool", required=True)
    ap.add_argument("--adjudication", required=True)
    ap.add_argument("--reviewer-a")
    ap.add_argument("--reviewer-b")
    ap.add_argument("--out", default="scorecard.md")
    a = ap.parse_args()

    cases = {r["case_id"]: r for r in rows(a.cases)}
    tool = {r["case_id"]: r for r in rows(a.tool)}
    final = by_case(a.adjudication, "final_label")
    versions = sorted({r.get("statwarrant_version", "") for r in tool.values()})

    scored = {k: v for k, v in final.items() if v in ("misleading", "faithful") and tool.get(k, {}).get("runnable") == "yes"}
    level = {k: tool[k]["tool_level"] for k in scored}
    mis = [k for k, v in scored.items() if v == "misleading"]
    fai = [k for k, v in scored.items() if v == "faithful"]
    allk = list(scored)

    def line(name, k, n, note):
        p, lo, hi = wilson(k, n)
        ci = "n/a" if p is None else f"{100 * p:.0f}% (95% CI {100 * lo:.0f}–{100 * hi:.0f}%)"
        return f"| {name} | {k} of {n} | {ci} | {note} |"

    table = [
        "| Measure | Count | Rate | What it means |", "| --- | --- | --- | --- |",
        line("False reassurance", sum(level[k] == "none" for k in mis), len(mis),
             "misleading sentence, no warning at all"),
        line("Caught as conflict", sum(level[k] == "conflict" for k in mis), len(mis),
             "misleading sentence flagged as a conflict"),
        line("Caught by any warning", sum(level[k] != "none" for k in mis), len(mis),
             "conflict or 'to verify'"),
        line("False alarm", sum(level[k] == "conflict" for k in fai), len(fai),
             "correct sentence flagged as a conflict"),
        line("Sent to review", sum(level[k] == "check" for k in allk), len(allk),
             "only 'to verify' warnings"),
    ]
    agree = ""
    if a.reviewer_a and a.reviewer_b:
        ka, n = kappa(by_case(a.reviewer_a, "human_label"), by_case(a.reviewer_b, "human_label"))
        agree = (f"Reviewer agreement before adjudication (sentence level, {n} sentences): "
                 f"Cohen's kappa = {'n/a' if ka is None else f'{ka:.2f}'}.")
    unclear = sum(v == "unclear" for v in final.values())
    not_run = [k for k in final if tool.get(k, {}).get("runnable") != "yes"]
    missing = [k for k in cases if k not in final]
    raw = open(a.cases, "rb").read()
    md = "\n".join([
        "# statwarrant scorecard", "",
        f"* statwarrant version tested: {', '.join(versions)}",
        f"* cases file SHA-256: `{hashlib.sha256(raw).hexdigest()}`",
        f"* sentences: {len(cases)}; adjudicated: {len(final)}; scored: {len(scored)} "
        f"({len(mis)} misleading, {len(fai)} faithful); unclear: {unclear}; "
        f"not runnable: {len(not_run)}; not yet adjudicated: {len(missing)}", "",
        *table, "", agree, "",
        "Labels are human and adjudicated; the tool output was produced after the labels were frozen. "
        "Small samples give wide intervals: read the interval, not the point.", "",
        "## Misleading sentences given no warning", "",
        *([f"* {k}: {cases.get(k, {}).get('sentence_text', '')}" for k in mis if level[k] == "none"] or ["None."]),
        "", "## Correct sentences flagged as a conflict", "",
        *([f"* {k}: {cases.get(k, {}).get('sentence_text', '')}" for k in fai if level[k] == "conflict"] or ["None."]),
        "",
    ])
    open(a.out, "w", encoding="utf-8").write(md)
    json.dump({"versions": versions, "scored": len(scored), "misleading": len(mis), "faithful": len(fai)},
              open(a.out + ".json", "w"), indent=1)
    print(md)


if __name__ == "__main__":
    main()

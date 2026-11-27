"""Monte Carlo size and power of the minimal-effect test: split versus relevance.

One-sample normal data with unknown variance (t reference, df = n - 1). The relevance
test chooses its per-side level from the observed standard error (a plug-in), so its size
is checked here rather than assumed. Run:

    python evaluation/simulations/relevance_size.py --reps 1000000
"""

import argparse

import numpy as np
from scipy import stats

from statwarrant._core import relevance_critical


def simulate(rng, reps, n, d_over_se, shift_se, alpha=0.05):
    df = n - 1
    true_se = 1 / np.sqrt(n)
    d = d_over_se * true_se
    theta = d + shift_se * true_se
    est = theta + rng.standard_normal(reps) * true_se
    se = np.sqrt(rng.chisquare(df, reps) / df) / np.sqrt(n)
    grid = np.linspace(0, 80, 8001)  # width 2d/se in standard errors
    qgrid = np.array([relevance_critical(w, alpha, df) for w in grid])
    q_rel = np.interp(np.minimum(2 * d / se, 80), grid, qgrid)
    q_split = stats.t(df).isf(alpha / 2)
    out = {}
    for name, q in (("split", q_split), ("relevance", q_rel)):
        out[name] = float((((est - d) / se > q) | ((est + d) / se < -q)).mean())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=20261124)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    print(f"Size at the bound (true effect = d), alpha = 0.05, {a.reps} replications per cell")
    print("| n | d / SE | split | relevance |\n| --- | --- | --- | --- |")
    for n in (5, 10, 30, 200):
        for r in (0.1, 0.3, 0.6, 1.0, 2.0):
            o = simulate(rng, a.reps, n, r, 0.0)
            print(f"| {n} | {r} | {o['split']:.4f} | {o['relevance']:.4f} |")
    print(f"\nPower at true effect = d + 2.5 SE")
    print("| n | d / SE | split | relevance |\n| --- | --- | --- | --- |")
    for n in (10, 30, 200):
        for r in (0.3, 1.0, 2.0):
            o = simulate(rng, a.reps, n, r, 2.5)
            print(f"| {n} | {r} | {o['split']:.4f} | {o['relevance']:.4f} |")


if __name__ == "__main__":
    main()

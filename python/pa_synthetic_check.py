#!/usr/bin/env python3
"""Synthetic validation of the two preferential-attachment estimators used in pa_fix.py.
Old nodes take the empirical in-degree distribution of one snapshot (default: USDT January 2023); new edges attach to an
old node of degree k with probability proportional to k^beta; the binned estimator (primary) and the Jeong–Néda–Barabási
cumulative estimator are then applied exactly as in pa_fix.py. Usage: python pa_synthetic_check.py [degree_hist.csv] [n_new_edges]"""
import sys, numpy as np, pandas as pd
from scipy import stats

hist_file = sys.argv[1] if len(sys.argv) > 1 else "data/topo/zip/degree_hist/USDT_2023-01-01_indeg.csv"
n_new = int(sys.argv[2]) if len(sys.argv) > 2 else 769_000           # new edges attaching to old nodes (USDT Jan→Feb 2023: 769k)
h = pd.read_csv(hist_file); h = h[h.degree > 0]
k_all = np.repeat(h.degree.to_numpy().astype(int), h["count"].to_numpy())   # degree of every old node

def estimate(k_all, k_hits):
    """same code path as pa_fix.py: Π(k) = hits / nodes; cumulative slope − 1; binned log–log slope."""
    ks = np.unique(k_all)
    hits = pd.Series(k_hits).value_counts().reindex(ks, fill_value=0).to_numpy()
    cnt = pd.Series(k_all).value_counts().reindex(ks, fill_value=0).to_numpy()
    pi = hits / cnt; kappa = np.cumsum(pi)
    m = (kappa > 0) & (cnt >= 5)
    s_cum = stats.linregress(np.log(ks[m]), np.log(kappa[m])).slope - 1
    edges = np.unique(np.round(np.logspace(0, np.log10(ks.max() + 1), 25)).astype(int))
    idx = np.digitize(ks, edges)
    bh = np.bincount(idx, weights=hits, minlength=len(edges) + 1)
    bc = np.bincount(idx, weights=cnt, minlength=len(edges) + 1)
    bk = np.bincount(idx, weights=ks * cnt, minlength=len(edges) + 1)
    ok = (bc >= 50) & (bh > 0)
    s_bin = stats.linregress(np.log(bk[ok] / bc[ok]), np.log(bh[ok] / bc[ok])).slope
    return s_bin, s_cum

rows = []
for beta in (0.5, 1.0, 1.5):
    for seed in range(5):
        rng = np.random.default_rng(seed)
        w = k_all.astype(float) ** beta; w /= w.sum()
        k_hits = rng.choice(k_all, size=n_new, replace=True, p=w)     # recipient degree of each new edge, Π(k) ∝ k^beta
        b, c = estimate(k_all, k_hits); rows.append(dict(beta=beta, seed=seed, beta_bin=b, beta_cum=c))
r = pd.DataFrame(rows)
summary = r.groupby("beta")[["beta_bin", "beta_cum"]].agg(["mean", "std"]).round(3)
print(f"old nodes: {len(k_all):,}; new edges: {n_new:,}; source: {hist_file}")
print(summary.to_string())
r.to_csv("pa_synthetic_check.csv", index=False)

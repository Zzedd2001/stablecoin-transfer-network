#!/usr/bin/env python3
"""Survival-conditioned preferential-attachment test (robustness check for pa_fix.py).
Same 13 month pairs, same estimators, but Π(k) is computed over the old nodes that are still active in month t+1
(as sender or recipient), so that the higher survival probability of well-connected addresses cannot inflate β.
Reads the cached edge lists written by topology_snapshots.py / pa_fix.py (out/cache/*.parquet); months missing from the
cache are fetched from BigQuery. Output: out/pa_results_survival.csv (one row per token x month pair x direction).
Usage (Mac, conda env `stable`):  nohup caffeinate -i python -u pa_survival.py --project YOUR_PROJECT > pa_surv.log 2>&1 &"""
import argparse, time
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
from pa_fix import PAIRS

def pa_survival(d0, d1):
    allv = pd.concat([d0.from_address, d0.to_address, d1.from_address, d1.to_address], ignore_index=True)
    codes, uniq = pd.factorize(allv)
    N = len(uniq); n0 = len(d0); n1 = len(d1)
    f0 = codes[:n0].astype(np.int64); t0 = codes[n0:2 * n0].astype(np.int64)
    f1 = codes[2 * n0:2 * n0 + n1].astype(np.int64); t1 = codes[2 * n0 + n1:].astype(np.int64)
    active1 = np.zeros(N, dtype=bool); active1[f1] = True; active1[t1] = True          # active in month t+1 in any role
    new = ~np.isin(f1 * N + t1, f0 * N + t0)
    out = {}
    for mode in ("in", "out"):
        tgt0, src0 = (t0, f0) if mode == "in" else (f0, t0)
        deg = pd.Series(src0).groupby(tgt0).nunique()                                   # degree in month t
        deg = deg[active1[deg.index.to_numpy()]]                                        # keep only survivors
        tgt1 = (t1 if mode == "in" else f1)[new]
        k_hits = deg.reindex(tgt1).dropna().to_numpy().astype(int)
        k_all = deg.to_numpy(); ks = np.unique(k_all)
        hits = pd.Series(k_hits).value_counts().reindex(ks, fill_value=0).to_numpy()
        cnt = pd.Series(k_all).value_counts().reindex(ks, fill_value=0).to_numpy()
        pi = hits / cnt; kappa = np.cumsum(pi)
        m = (kappa > 0) & (cnt >= 5)
        s, _, r, _, se = stats.linregress(np.log(ks[m]), np.log(kappa[m]))
        edges = np.unique(np.round(np.logspace(0, np.log10(ks.max() + 1), 25)).astype(int))
        idx = np.digitize(ks, edges)
        bh = np.bincount(idx, weights=hits, minlength=len(edges) + 1)
        bc = np.bincount(idx, weights=cnt, minlength=len(edges) + 1)
        bk = np.bincount(idx, weights=ks * cnt, minlength=len(edges) + 1)
        ok = (bc >= 50) & (bh > 0)
        if ok.sum() >= 3:
            s2, _, r2, _, se2 = stats.linregress(np.log(bk[ok] / bc[ok]), np.log(bh[ok] / bc[ok]))
        else:
            s2, r2, se2 = np.nan, np.nan, np.nan
        out[mode] = dict(beta_cum=s - 1, beta_cum_se=se, beta_bin=s2, beta_bin_se=se2, r2_bin=r2 ** 2,
                         n_old_surviving=int(len(deg)), n_new_to_old=int(len(k_hits)))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--tokens", nargs="+", default=["USDC", "USDT", "DAI"])
    args = ap.parse_args()
    from google.cloud import bigquery
    from topology_snapshots import fetch_edges
    client = bigquery.Client(project=args.project)
    out = Path("out"); (out / "cache").mkdir(parents=True, exist_ok=True)
    res_path = out / "pa_results_survival.csv"
    rows = pd.read_csv(res_path).to_dict("records") if res_path.exists() else []
    done = {(r["token"], r["month_t"], r["mode"]) for r in rows}
    for token in args.tokens:
        for m0, m1 in PAIRS:
            if (token, m0, "in") in done: continue
            t = time.time()
            d0 = fetch_edges(client, args.project, token, m0, out / "cache"); d1 = fetch_edges(client, args.project, token, m1, out / "cache")
            res = pa_survival(d0, d1)
            for mode, r in res.items():
                r.update(token=token, month_t=m0, month_t1=m1, mode=mode); rows.append(r)
            pd.DataFrame(rows).to_csv(res_path, index=False)
            print(f"PA-survival {token} {m0}->{m1}: in beta_bin={res['in']['beta_bin']:.2f} | out beta_bin={res['out']['beta_bin']:.2f} [{time.time()-t:.0f}s]", flush=True)
    print("done ->", res_path.resolve())

if __name__ == "__main__":
    main()

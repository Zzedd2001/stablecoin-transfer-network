#!/usr/bin/env python3
"""
Preferential-attachment test (fixed version). The PA stage of the main script ran out of memory on USDC 2026 when comparing edge keys;
this version uses integer-encoded keys, extends the test to two month pairs per year (Jan→Feb, Jul→Aug) and reports two β estimators:
  beta_bin : slope of log Π(k) ~ log k after logarithmic binning (primary estimate; synthetic networks with β = 0.5/1.0/1.5 give 0.49/1.00/1.50)
  beta_cum : Jeong–Néda–Barabási cumulative function κ(k), double-log slope minus 1 (original method; biased low by about 0.1 at this sample size; reference only)
Reads edge lists from out/cache; missing months are fetched from BigQuery (1–3 GB each, about 0.01 USD per month).
Usage:
  cd ~/stablecoin && conda activate stable
  nohup caffeinate -i python -u pa_fix.py --project YOUR_PROJECT > pa.log 2>&1 &
Output: out/pa_results_v2.csv (one row per token × month pair × direction)
"""
import argparse, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

PAIRS = [(f"{y}-01-01", f"{y}-02-01") for y in range(2020, 2027)] + [(f"{y}-07-01", f"{y}-08-01") for y in range(2020, 2026)]


def pa_both_modes(d0, d1):
    """returns {"in": {...}, "out": {...}}"""
    allv = pd.concat([d0.from_address, d0.to_address, d1.from_address, d1.to_address], ignore_index=True)
    codes, uniq = pd.factorize(allv)
    N = len(uniq); n0 = len(d0); n1 = len(d1)
    f0 = codes[:n0].astype(np.int64); t0 = codes[n0:2 * n0].astype(np.int64)
    f1 = codes[2 * n0:2 * n0 + n1].astype(np.int64); t1 = codes[2 * n0 + n1:].astype(np.int64)
    new = ~np.isin(f1 * N + t1, f0 * N + t0)                       # edges present in month t+1 but not in month t
    out = {}
    for mode in ("in", "out"):
        tgt0, src0 = (t0, f0) if mode == "in" else (f0, t0)
        deg = pd.Series(src0).groupby(tgt0).nunique()               # degree in month t: number of distinct counterparties
        tgt1 = (t1 if mode == "in" else f1)[new]
        k_hits = deg.reindex(tgt1).dropna().to_numpy().astype(int)  # new edges attaching to old nodes, by the old node's degree
        k_all = deg.to_numpy()
        ks = np.unique(k_all)
        hits = pd.Series(k_hits).value_counts().reindex(ks, fill_value=0).to_numpy()
        cnt = pd.Series(k_all).value_counts().reindex(ks, fill_value=0).to_numpy()
        pi = hits / cnt
        kappa = np.cumsum(pi)
        m = (kappa > 0) & (cnt >= 5)
        s, _, r, _, se = stats.linregress(np.log(ks[m]), np.log(kappa[m]))
        # direct estimate on logarithmic bins
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
        out[mode] = dict(beta_cum=s - 1, beta_cum_se=se, r2_cum=r ** 2, beta_bin=s2, beta_bin_se=se2, r2_bin=r2 ** 2,
                         n_new_edges=int(new.sum()), n_new_to_old=int(len(k_hits)), n_old_nodes=int(len(deg)),
                         share_new_to_old=float(len(k_hits) / max(1, new.sum())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--tokens", nargs="+", default=["USDC", "USDT", "DAI"])
    args = ap.parse_args()
    from google.cloud import bigquery
    from topology_snapshots import fetch_edges
    client = bigquery.Client(project=args.project)
    out = Path("out"); (out / "cache").mkdir(parents=True, exist_ok=True)
    res_path = out / "pa_results_v2.csv"
    rows = pd.read_csv(res_path).to_dict("records") if res_path.exists() else []
    done = {(r["token"], r["month_t"], r["mode"]) for r in rows}
    for token in args.tokens:
        for m0, m1 in PAIRS:
            if (token, m0, "in") in done:
                continue
            t0 = time.time()
            d0 = fetch_edges(client, args.project, token, m0, out / "cache")
            d1 = fetch_edges(client, args.project, token, m1, out / "cache")
            res = pa_both_modes(d0, d1)
            for mode, r in res.items():
                r.update(token=token, month_t=m0, month_t1=m1, mode=mode); rows.append(r)
            pd.DataFrame(rows).to_csv(res_path, index=False)
            print(f"PA {token} {m0}->{m1}: in beta_cum={res['in']['beta_cum']:.2f} beta_bin={res['in']['beta_bin']:.2f} | "
                  f"out beta_cum={res['out']['beta_cum']:.2f} beta_bin={res['out']['beta_bin']:.2f} [{time.time()-t0:.0f}s]", flush=True)
    print("done ->", res_path.resolve())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Supplementary script (run after the main script; no BigQuery access, reads only out/cache/*.parquet):
  1) log-binned histograms of in-/out-strength (USD) for each snapshot  -> out/strength_hist/{token}_{month}_{in|out}str.csv
  2) power-law fits of in-/out-degree and in-strength (continuous approximation) with likelihood-ratio comparisons against log-normal, exponential and truncated power law -> out/tail_fits.csv
Usage:
  cd ~/stablecoin && conda activate stable && python strength_fits.py
Run time (v2, strengths rounded to 3 significant figures): about 0.5–5 minutes per snapshot; can be interrupted, re-runs skip finished snapshots.
"""
import warnings, glob, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path("out"); (OUT / "strength_hist").mkdir(parents=True, exist_ok=True)
RESULT = OUT / "tail_fits.csv"
done = set()
if RESULT.exists():
    prev = pd.read_csv(RESULT); done = set(zip(prev.token, prev.month))
else:
    prev = pd.DataFrame()


def fit_tail(values, discrete):
    """CSN power-law fit + likelihood-ratio comparisons; returns a dict"""
    import powerlaw
    v = np.asarray(values, dtype=float); v = v[v > 0]
    r = {"n": int(len(v)), "max": float(v.max()) if len(v) else np.nan}
    if len(v) < 1000:
        return r
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # xmin search range: degrees 2–1000; strengths 100 USD to the 99.9th percentile
        if discrete:
            fit = powerlaw.Fit(v, discrete=True, xmin=(2, 1000), verbose=False)
        else:
            # strengths rounded to 3 significant figures: the xmin candidates fall from hundreds of thousands to a few thousand, about 50× faster, no material effect on the fits
            e = np.floor(np.log10(v)); f = 10.0 ** (e - 2); v = np.round(v / f) * f
            hi = max(1e3, float(np.quantile(v, 0.999)))
            fit = powerlaw.Fit(v, discrete=False, xmin=(100.0, hi), verbose=False)
        r.update(alpha=fit.power_law.alpha, xmin=fit.power_law.xmin, sigma=fit.power_law.sigma,
                 n_tail=int(np.sum(v >= fit.power_law.xmin)), ks=getattr(fit.power_law, "D", np.nan))
        # comparisons use the continuous approximation (the discrete log-normal often cannot be normalised over a wide range)
        fc = fit if not discrete else powerlaw.Fit(v, discrete=False, xmin=fit.power_law.xmin, verbose=False)
        for alt in ("lognormal", "exponential"):
            try:
                R, p = fc.distribution_compare("power_law", alt, normalized_ratio=True)
            except Exception:
                R, p = np.nan, np.nan
            r[f"LR_pl_vs_{alt}"] = R; r[f"p_pl_vs_{alt}"] = p
        try:
            R, p = fc.distribution_compare("power_law", "truncated_power_law")  # nested models, p from the chi-squared distribution
        except Exception:
            R, p = np.nan, np.nan
        r["LR_pl_vs_truncated"] = R; r["p_pl_vs_truncated"] = p
        try:
            r["lognormal_mu"] = fc.lognormal.mu; r["lognormal_sigma"] = fc.lognormal.sigma
        except Exception:
            pass
    return r


def log_hist(values, path):
    v = np.asarray(values, dtype=float); v = v[v > 0]
    if len(v) == 0:
        return
    bins = np.arange(0, np.ceil(np.log10(v.max())) + 0.1, 0.1)  # 10 bins per decade
    cnt, edges = np.histogram(np.log10(v), bins=bins)
    pd.DataFrame({"log10_left": edges[:-1].round(2), "count": cnt}).to_csv(path, index=False)


rows = [] if prev.empty else prev.to_dict("records")
files = sorted(glob.glob(str(OUT / "cache" / "*.parquet")))
print(f"{len(files)} cached snapshots, {len(done)} already done")
for f in files:
    token, month = Path(f).stem.split("_", 1)
    if (token, month) in done:
        continue
    t0 = time.time()
    df = pd.read_parquet(f, columns=["from_address", "to_address", "w"])
    s_in = df.groupby("to_address").w.sum().to_numpy(); s_out = df.groupby("from_address").w.sum().to_numpy()
    k_in = df.groupby("to_address").size().to_numpy(); k_out = df.groupby("from_address").size().to_numpy()
    log_hist(s_in, OUT / "strength_hist" / f"{token}_{month}_instr.csv")
    log_hist(s_out, OUT / "strength_hist" / f"{token}_{month}_outstr.csv")
    row = dict(token=token, month=month, nodes=int(len(set(df.from_address) | set(df.to_address))), edges=int(len(df)))
    for name, vals, disc in [("in_degree", k_in, True), ("out_degree", k_out, True), ("in_strength", np.round(s_in), False), ("out_strength", np.round(s_out), False)]:
        row.update({f"{name}_{k}": v for k, v in fit_tail(vals, disc).items()})
    row["seconds"] = round(time.time() - t0, 1)
    rows.append(row)
    pd.DataFrame(rows).to_csv(RESULT, index=False)
    print(f"{token} {month}: n={row['nodes']:,} in_alpha={row.get('in_degree_alpha', float('nan')):.2f} "
          f"instr_alpha={row.get('in_strength_alpha', float('nan')):.2f} LR(pl vs logn, in-deg)={row.get('in_degree_LR_pl_vs_lognormal', float('nan')):.2f} "
          f"[{row['seconds']}s]")
print("done ->", RESULT.resolve())

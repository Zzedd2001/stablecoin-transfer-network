#!/usr/bin/env python3
"""Re-do the degree-distribution model comparisons without powerlaw's default alpha cap ([0, 3]).
For every token x quarterly snapshot x direction: discrete power law on the k >= 10 tail (the same tail as alpha(k>=10)),
uncapped (alpha in [0, 20]); normalised likelihood-ratio tests vs log-normal and exponential; nested LR vs truncated power law.
Also the continuous-approximation comparison at the KS-selected x_min, uncapped, for reference."""
import os
from pathlib import Path
DATA = Path(os.environ.get("STABLECOIN_DATA", "data"))   # repository data folder (run from the repository root)
import pandas as pd, numpy as np, warnings, time, os, sys
warnings.filterwarnings("ignore")
import powerlaw
# run from the repository root; data are read from $STABLECOIN_DATA (default data/)
t = pd.read_csv(DATA / "topo" / "topology_metrics.csv")
out = "degree_fits_k10_uncapped.csv"
rows = pd.read_csv(out).to_dict("records") if os.path.exists(out) else []
done = {(r["token"], r["month"]) for r in rows}
PR = {"alpha": [0, 20]}
for r in t.itertuples():
    if (r.token, r.month) in done: continue
    t0 = time.time(); row = dict(token=r.token, month=r.month)
    for kind, ks_xmin in [("in", r.in_degree_xmin), ("out", r.out_degree_xmin)]:
        h = pd.read_csv(DATA / "topo" / "zip" / "degree_hist" / f"{r.token}_{r.month}_{kind}deg.csv"); h = h[h.degree > 0]
        v = np.repeat(h.degree.to_numpy().astype(float), h["count"].to_numpy())
        # fixed tail k >= 10, discrete, uncapped
        fd = powerlaw.Fit(v, discrete=True, xmin=10.0, verbose=False, parameter_ranges=PR)
        R1, p1 = fd.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        R2, p2 = fd.distribution_compare("power_law", "exponential", normalized_ratio=True)
        try:
            R3, p3 = fd.distribution_compare("power_law", "truncated_power_law")
        except Exception:
            R3, p3 = np.nan, np.nan
        row.update({f"{kind}_k10_alpha": fd.power_law.alpha, f"{kind}_k10_ntail": int((v >= 10).sum()),
                    f"{kind}_k10_LR_logn": R1, f"{kind}_k10_p_logn": p1, f"{kind}_k10_logn_mu": fd.lognormal.mu, f"{kind}_k10_logn_sigma": fd.lognormal.sigma,
                    f"{kind}_k10_LR_exp": R2, f"{kind}_k10_p_exp": p2, f"{kind}_k10_LR_trunc": R3, f"{kind}_k10_p_trunc": p3,
                    f"{kind}_k10_trunc_alpha": getattr(fd.truncated_power_law, "alpha", np.nan), f"{kind}_k10_trunc_lambda": getattr(fd.truncated_power_law, "Lambda", np.nan)})
        # KS-selected x_min, continuous approximation, uncapped (reference)
        fc = powerlaw.Fit(v, discrete=False, xmin=float(ks_xmin), verbose=False, parameter_ranges=PR)
        Rc, pc = fc.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        row.update({f"{kind}_ks_xmin": ks_xmin, f"{kind}_ks_cont_alpha": fc.power_law.alpha, f"{kind}_ks_LR_logn": Rc, f"{kind}_ks_p_logn": pc})
    row["seconds"] = round(time.time() - t0, 1); rows.append(row)
    pd.DataFrame(rows).to_csv(out, index=False); print(r.token, r.month, row["seconds"], flush=True)
print("done")

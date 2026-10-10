import os
from pathlib import Path
DATA = Path(os.environ.get("STABLECOIN_DATA", "data"))   # repository data folder (run from the repository root)
import pandas as pd, numpy as np, warnings, time, os
warnings.filterwarnings("ignore")
import powerlaw
t = pd.read_csv(DATA / "topo" / "topology_metrics.csv")
out = "degree_fits_offline.csv"
rows = pd.read_csv(out).to_dict("records") if os.path.exists(out) else []
done = {(r["token"], r["month"]) for r in rows}
for r in t.itertuples():
    if (r.token, r.month) in done: continue
    t0=time.time(); row = dict(token=r.token, month=r.month)
    for kind, xmin in [("in", r.in_degree_xmin), ("out", r.out_degree_xmin)]:
        h = pd.read_csv(DATA / "topo" / "zip" / "degree_hist" / f"{r.token}_{r.month}_{kind}deg.csv"); h = h[h.degree>0]
        v = np.repeat(h.degree.to_numpy().astype(float), h["count"].to_numpy())
        fit = powerlaw.Fit(v, discrete=True, xmin=xmin, verbose=False)
        fc = powerlaw.Fit(v, discrete=False, xmin=xmin, verbose=False)
        R1,p1 = fc.distribution_compare("power_law","lognormal", normalized_ratio=True)
        R2,p2 = fc.distribution_compare("power_law","exponential", normalized_ratio=True)
        try: R3,p3 = fc.distribution_compare("power_law","truncated_power_law")
        except Exception: R3,p3 = np.nan,np.nan
        row.update({f"{kind}_alpha": fit.power_law.alpha, f"{kind}_xmin": xmin, f"{kind}_ntail": int((v>=xmin).sum()),
                    f"{kind}_LR_logn": R1, f"{kind}_p_logn": p1, f"{kind}_LR_exp": R2, f"{kind}_p_exp": p2, f"{kind}_LR_trunc": R3, f"{kind}_p_trunc": p3,
                    f"{kind}_logn_mu": fc.lognormal.mu, f"{kind}_logn_sigma": fc.lognormal.sigma})
    row["seconds"]=round(time.time()-t0,1); rows.append(row)
    pd.DataFrame(rows).to_csv(out, index=False); print(r.token, r.month, row["seconds"], flush=True)
print("done")

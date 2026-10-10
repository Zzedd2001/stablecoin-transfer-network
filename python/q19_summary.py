#!/usr/bin/env python3
"""Q19 post-processing: fixed-count net-inflow shares at the size of the 2026 top 1%.
Usage: python q19_summary.py q19_fixed_count_share_month.csv [concentration_all_schemes.csv]
Prints (1) annual means of every fixed-count share by token, (2) Kendall's tau of each series with time over the 81 months,
(3) the like-for-like comparison: for each token, the fixed N closest to the mean size of its 2026 top 1%, the share of
those N recipients in 2020 and in 2026, next to the percentile-based top-1% share (which compares sets of different size).
Writes q19_annual_means.csv (for S5 Table) and prints the sentences for the manuscript."""
import sys
import numpy as np, pandas as pd
from scipy import stats

f = sys.argv[1] if len(sys.argv) > 1 else "q19_fixed_count_share_month.csv"
conc = sys.argv[2] if len(sys.argv) > 2 else None
d = pd.read_csv(f, parse_dates=["month"]).sort_values(["token", "month"])
d["year"] = d.month.dt.year
cols = [c for c in d.columns if c.startswith("top") and c.endswith("_share")]
assert len(d) == 243 and d.month.nunique() == 81, (len(d), d.month.nunique())

# (1) annual means (2026 = January-September) and (2) Kendall's tau with time
rows = []
for tok, g in d.groupby("token"):
    for y, gy in g.groupby("year"):
        rows.append(dict(token=tok, year=("2026 (Jan-Sep)" if y == 2026 else y), n_receivers=round(gy.n_receivers.mean()), n_top1pct=round(gy.n_top1pct.mean()),
                         **{c: round(100 * gy[c].mean(), 1) for c in cols}))
    t = np.arange(len(g)); taus = {}
    for c in cols:
        tau, p = stats.kendalltau(t, g[c].to_numpy()); taus[c] = f"{tau:+.2f} (p {'< 0.001' if p < 0.001 else '= ' + format(p, '.2g')})"
    rows.append(dict(token=tok, year="Kendall's tau (p)", n_receivers=None, n_top1pct=None, **taus))
ann = pd.DataFrame(rows); print(ann.to_string(index=False)); ann.to_csv("q19_annual_means.csv", index=False)

# (3) like-for-like: fixed N closest to the mean 2026 top-1% size, share in 2020 vs 2026
print("\nLike-for-like comparison at the size of the 2026 top 1%:")
thr = {c: int(c[3:-6]) for c in cols}
for tok, g in d.groupby("token"):
    n26 = g[g.year == 2026].n_top1pct.mean(); n20 = g[g.year == 2020].n_top1pct.mean()
    c = min(cols, key=lambda c: abs(thr[c] - n26))
    s20 = 100 * g[g.year == 2020][c].mean(); s26 = 100 * g[g.year == 2026][c].mean()
    tau, p = stats.kendalltau(np.arange(len(g)), g[c].to_numpy())
    line = (f"{tok}: 2026 top 1% = {n26:,.0f} addresses (2020: {n20:,.0f}); the {thr[c]:,} largest recipients took {s20:.1f}% of net inflow in 2020 and {s26:.1f}% in 2026, "
            f"tau = {tau:+.2f}, p {'< 0.001' if p < 0.001 else '= ' + format(p, '.2g')}")
    if conc:
        a = pd.read_csv(conc, parse_dates=["month"]); a["year"] = a.month.dt.year
        sch = "G_net_xf" if tok == "DAI" else "G_net"
        if sch == "G_net_xf" and not (a.scheme == "G_net_xf").any():
            sch = None
        if sch:
            aa = a[(a.token == tok) & (a.scheme == sch)]
            line += f" | percentile-based top-1% share: {100 * aa[aa.year == 2020].top_1pct_share.mean():.1f}% (2020) -> {100 * aa[aa.year == 2026].top_1pct_share.mean():.1f}% (2026)"
    print(" ", line)
print("\nReading: if the fixed-N share in 2020 is close to the 2026 top-1% share, the rise of the top-1% share mostly reflects the growth of the set;"
      " if it is clearly lower, concentration rose among a set of fixed size as well.")

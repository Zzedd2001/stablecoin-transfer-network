#!/usr/bin/env python3
"""Re-analyse the tails from the degree histograms: discrete power-law MLE with fixed xmin and with the KS-optimal xmin; likelihood ratios against log-normal/exponential/truncated power law (continuous approximation); CCDF figure"""
import glob, warnings
import os
from pathlib import Path
import numpy as np, pandas as pd
import powerlaw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

warnings.filterwarnings("ignore")
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
for cand in ["Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans CJK HK"]:
    if any(f.name == cand for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = [cand, "DejaVu Sans"]; break
plt.rcParams["axes.unicode_minus"] = False
HD = Path(os.environ.get("STABLECOIN_DATA", "data")) / "topo" / "zip" / "degree_hist"


def load(token, month, kind):
    h = pd.read_csv(HD / f"{token}_{month}_{kind}deg.csv")
    h = h[h.degree > 0]
    return h.degree.to_numpy(), h["count"].to_numpy()


def expand(deg, cnt):
    return np.repeat(deg.astype(float), cnt.astype(int))


def discrete_alpha(deg, cnt, xmin):
    """discrete power-law MLE (approximation of eq. 3.7 in Clauset et al. 2009: alpha = 1 + n / sum(ln(x/(xmin-0.5))))"""
    m = deg >= xmin
    n = cnt[m].sum()
    if n < 50:
        return np.nan, int(n)
    s = np.sum(cnt[m] * np.log(deg[m] / (xmin - 0.5)))
    return 1 + n / s, int(n)


rows = []
for f in sorted(HD.glob("*_indeg.csv")):
    token, month, _ = f.stem.split("_")
    r = dict(token=token, month=month)
    for kind in ("in", "out"):
        deg, cnt = load(token, month, kind)
        n_nodes = cnt.sum()
        r[f"{kind}_n_nonzero"] = int(n_nodes)
        r[f"{kind}_share_deg1"] = float(cnt[deg == 1].sum() / n_nodes)
        r[f"{kind}_share_deg_ge100"] = float(cnt[deg >= 100].sum() / n_nodes)
        r[f"{kind}_max"] = int(deg.max())
        for xm in (2, 10, 50):
            a, n = discrete_alpha(deg, cnt, xm); r[f"{kind}_alpha_xmin{xm}"] = a; r[f"{kind}_ntail_xmin{xm}"] = n
        data = expand(deg, cnt)
        fit = powerlaw.Fit(data, discrete=True, xmin=(2, 1000), verbose=False)
        r[f"{kind}_alpha_ks"] = fit.power_law.alpha; r[f"{kind}_xmin_ks"] = fit.power_law.xmin; r[f"{kind}_D_ks"] = fit.power_law.D
        # model comparisons under the continuous approximation, all on the k >= 10 tail
        fc = powerlaw.Fit(data, discrete=False, xmin=10, verbose=False)
        for alt in ("lognormal", "exponential"):
            R, p = fc.distribution_compare("power_law", alt, normalized_ratio=True)
            r[f"{kind}_LR_{alt}_x10"] = R; r[f"{kind}_p_{alt}_x10"] = p
        R, p = fc.distribution_compare("power_law", "truncated_power_law")
        r[f"{kind}_LR_trunc_x10"] = R; r[f"{kind}_p_trunc_x10"] = p
    rows.append(r)
    print(token, month, f"in: a2={r['in_alpha_xmin2']:.2f} a10={r['in_alpha_xmin10']:.2f} aKS={r['in_alpha_ks']:.2f}@{r['in_xmin_ks']:.0f} LRlogn={r['in_LR_lognormal_x10']:.1f} | out: a2={r['out_alpha_xmin2']:.2f} a10={r['out_alpha_xmin10']:.2f}")
res = pd.DataFrame(rows); res.to_csv("degree_tail_fits.csv", index=False)

# ---------------- CCDF figure: January snapshots, in-degree, three tokens ----------------
fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), dpi=180, facecolor=SURF)
fig.subplots_adjust(left=0.05, right=0.985, top=0.80, bottom=0.14, wspace=0.2)
years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
cmap = plt.get_cmap("viridis")
for ax, tok in zip(axes, ["USDT", "USDC", "DAI"]):
    for i, y in enumerate(years):
        deg, cnt = load(tok, f"{y}-01-01", "in")
        ccdf = 1 - np.cumsum(cnt) / cnt.sum() + cnt / cnt.sum()   # P(K >= k)
        ax.loglog(deg, ccdf, color=cmap(i / (len(years) - 1)), linewidth=1.4, label=str(y))
    ax.set_facecolor(SURF); ax.set_title(f"{tok}  in-degree CCDF P(K ≥ k), January snapshots", loc="left", fontsize=10.5, color=INK)
    ax.grid(True, which="major", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ["top", "right"]: ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5); ax.set_xlabel("In-degree k (distinct senders)", fontsize=9, color=INK2)
    ax.set_ylim(1e-7, 1.1)
axes[0].set_ylabel("P(K ≥ k)", fontsize=9, color=INK2)
axes[2].legend(frameon=False, fontsize=8.5, labelcolor=INK2, loc="upper right", ncol=2)
fig.suptitle("In-degree distribution of the monthly netted network (G_net, flash loans and DAI flash mints removed): heavy-tailed and stable in shape over seven years", x=0.05, ha="left", fontsize=13, color=INK)
fig.text(0.05, 0.02, "Double-logarithmic axes. Straight segments correspond to power laws; the curves flatten at k≈10–30, where the KS-optimal fit gives α≈1.7–1.9 above that point and α≈2.6–2.9 over the whole k≥2 range.", fontsize=8, color=MUTED)
fig.savefig("fig_indegree_ccdf.png", facecolor=SURF)
print("ok")

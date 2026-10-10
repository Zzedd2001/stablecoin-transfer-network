#!/usr/bin/env python3
"""English, submission-ready versions of Figs 1–9 (PLOS ONE: ≤ 7.5 in wide, 300 dpi, PNG + LZW TIFF).
Run from the repository root: python python/make_figures_en.py. Reads data/ (or $STABLECOIN_DATA) and writes figures/ (or $FIG_OUT)."""
import pandas as pd, numpy as np, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pathlib import Path

import os
DATA = Path(os.environ.get("STABLECOIN_DATA", "data"))
OUTDIR = Path(os.environ.get("FIG_OUT", "figures")); OUTDIR.mkdir(parents=True, exist_ok=True)
SURF, INK, INK2, MUTED, GRID, AXIS = "#ffffff", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
TOKEN_C = {"USDT": "#2a78d6", "USDC": "#eb6834", "DAI": "#1baf7a"}
SCHEME_C = {"G_all": "#2a78d6", "G_net": "#eb6834", "G_net_xf": "#7c4dbd", "G_simple": "#1baf7a"}
plt.rcParams["font.family"] = ["Liberation Sans", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
EVENTS = ["2022-05-09", "2022-11-08", "2023-03-10", "2025-10-10"]
W = 7.5  # inches

def style(ax, title, ylabel=None, log=False, events=True, xgrid=False):
    ax.set_facecolor(SURF); ax.set_title(title, loc="left", fontsize=8.5, color=INK, pad=4, fontweight="bold")
    if ylabel: ax.set_ylabel(ylabel, fontsize=7.5, color=INK2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    if xgrid: ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    for s in ["top", "right", "left"]: ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS); ax.tick_params(axis="both", colors=MUTED, length=0, labelsize=7)
    if log:
        ax.set_yscale("log"); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.tick_params(axis="y", which="minor", length=0)
    if events:
        for d in EVENTS: ax.axvline(pd.Timestamp(d), color=AXIS, linewidth=0.6, linestyle=(0, (3, 3)))

def save(fig, name):
    from PIL import Image
    fig.savefig(OUTDIR / f"{name}.png", dpi=300, facecolor=SURF)
    # PLOS: RGB TIFF (no alpha channel), 300 dpi, LZW
    Image.open(OUTDIR / f"{name}.png").convert("RGB").save(OUTDIR / f"{name}.tif", compression="tiff_lzw", dpi=(300, 300))
    plt.close(fig); print("saved", name)

pct = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
c4 = pd.read_csv(DATA / "concentration_four_ways.csv", parse_dates=["month"])
allc = pd.read_csv(DATA / "concentration_all_schemes.csv", parse_dates=["month"])
f = pd.read_csv(DATA / "flow_composition_month.csv", parse_dates=["month"])
d = pd.read_csv(DATA / "dyad_month.csv", parse_dates=["month"])
fm = pd.read_csv(DATA / "dai/dai_flashmint_share.csv", parse_dates=["month"])
top = pd.read_csv(DATA / "top_receivers_net.csv", parse_dates=["month"])
lab = pd.read_csv(os.environ.get("STABLECOIN_LABELS", "labels/labels_final.csv")); lab["address"] = lab.address.str.lower()
cat = pd.read_csv(DATA / "entity/inflow_category_share_month.csv", parse_dates=["month"])
t = pd.read_csv(DATA / "topo/topology_metrics.csv", parse_dates=["month"]).merge(pd.read_csv(DATA / "topo/alpha_fixed_xmin.csv", parse_dates=["month"])[["token", "month", "in_alpha_xmin10", "out_alpha_xmin10"]], on=["token", "month"])
tf = pd.read_csv(DATA / "topo/v4/tail_fits.csv").set_index(["token", "month"])
pa = pd.read_csv(DATA / "topo/v2/pa_results_v2.csv"); pa["t"] = pd.to_datetime(pa.month_t)

# ---------------- Fig 1: flow composition ----------------
d["share"] = d.usd / d.groupby(["scheme", "token", "month"]).usd.transform("sum")
sc_share = (1 - d[(d.scheme == "G_net") & (d.dyad == "EOA->EOA")].set_index(["token", "month"]).share).rename("sc_share").reset_index()
fig, axes = plt.subplots(1, 3, figsize=(W, 2.9), dpi=300, facecolor=SURF)
fig.subplots_adjust(left=0.065, right=0.99, top=0.82, bottom=0.13, wspace=0.22)
for tok in ["USDT", "USDC", "DAI"]:
    g = f[f.token == tok].sort_values("month")
    axes[0].plot(g.month, g.flashloan_share, color=TOKEN_C[tok], linewidth=1.2, label=tok)
    axes[1].plot(g.month, g.simple_usd_share, color=TOKEN_C[tok], linewidth=1.2, label=tok)
    h = sc_share[sc_share.token == tok].sort_values("month")
    axes[2].plot(h.month, h.sc_share, color=TOKEN_C[tok], linewidth=1.2, label=tok)
style(axes[0], "A  Flash-loan-like round trips\n(share of gross value)", "Share")
style(axes[1], "B  Direct token-contract calls (G_simple)\n(share of value)")
style(axes[2], "C  Contract on at least one side\n(share of G_net value)")
for ax in axes: ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(pct)
axes[0].legend(frameon=False, fontsize=7, labelcolor=INK2, loc="upper left")
save(fig, "Fig1_flow_composition")

# ---------------- Fig 2: DAI flash mint & funnel ----------------
MCD = "0x60744434d6339a6b27d73d9eda62b6f66a0a04fa"
dd = top[top.token == "DAI"].merge(lab[["address", "entity_group", "category"]], on="address", how="left").merge(fm[["month", "flashmint_share"]], on="month")
dd = dd[dd.address != MCD].copy(); dd["share_xf"] = dd.share_of_month / (1 - dd.flashmint_share)
def bucket(r):
    if r.entity_group == "Sky": return "Sky/Maker issuer-side contracts"
    if r.category == "CEX": return "Centralised exchanges"
    if r.category == "DeFi-lending": return "Lending protocols"
    if r.category in ("DeFi-DEX", "DEX-aggregator"): return "DEX pools and aggregators"
    if pd.isna(r.category): return "Unlabelled top-20 addresses"
    return "Other labelled"
dd["bucket"] = dd.apply(bucket, axis=1)
piv = dd.pivot_table(index="month", columns="bucket", values="share_xf", aggfunc="sum").fillna(0)
piv["Outside top 20"] = (1 - piv.sum(axis=1)).clip(lower=0)
order = [o for o in ["Sky/Maker issuer-side contracts", "Lending protocols", "DEX pools and aggregators", "Centralised exchanges", "Other labelled", "Unlabelled top-20 addresses", "Outside top 20"] if o in piv.columns]
cols = {"Sky/Maker issuer-side contracts": "#7c4dbd", "Lending protocols": "#eb6834", "DEX pools and aggregators": "#1baf7a", "Centralised exchanges": "#2a78d6", "Other labelled": "#c9a227", "Unlabelled top-20 addresses": "#b8b6ae", "Outside top 20": "#e6e4dc"}
fig, axes = plt.subplots(1, 3, figsize=(W, 3.7), dpi=300, facecolor=SURF)
fig.subplots_adjust(left=0.065, right=0.99, top=0.90, bottom=0.36, wspace=0.26)
ax = axes[0]; ax.fill_between(fm.month, 0, fm.flashmint_share, color="#7c4dbd", alpha=0.25, linewidth=0); ax.plot(fm.month, fm.flashmint_share, color="#7c4dbd", linewidth=1.2)
style(ax, "A  MCD Flash share of DAI net inflow", "Share"); ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(pct)
ax = axes[1]
for s_, lab_ in [("G_net", "G_net (flash-mint repayment leg included)"), ("G_net_xf", "G_net_xf (flash-mint module removed)")]:
    g = c4[(c4.token == "DAI") & (c4.scheme == s_)].sort_values("month"); ax.plot(g.month, g.nakamoto_50, color=SCHEME_C[s_], linewidth=1.2, label=lab_)
style(ax, "B  DAI Nakamoto coefficient", "Recipients for 50% of inflow", log=True)
hB, lB = ax.get_legend_handles_labels()
ax = axes[2]; ax.stackplot(piv.index, [piv[o] for o in order], labels=order, colors=[cols[o] for o in order], linewidth=0)
style(ax, "C  Destination of DAI net inflow", events=False); ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(pct)
hC, lC = ax.get_legend_handles_labels()
fig.legend(hB, lB, frameon=False, fontsize=6.3, labelcolor=INK2, loc="upper left", bbox_to_anchor=(0.065, 0.21), ncol=1, title="Panel B", title_fontsize=6.5)
fig.legend(hC, lC, frameon=False, fontsize=6.3, labelcolor=INK2, loc="upper left", bbox_to_anchor=(0.47, 0.21), ncol=2, columnspacing=1.0, handlelength=1.2, title="Panel C", title_fontsize=6.5)
save(fig, "Fig2_DAI_flash_mint_funnel")

# ---------------- Fig 3: concentration under definitions ----------------
SL = {"G_all": "G_all (all transfers)", "G_net": "G_net (netted, flash loans removed)", "G_net_xf": "G_net_xf (DAI: flash mint removed)", "G_simple": "G_simple (direct token-contract calls)"}
fig, axes = plt.subplots(2, 3, figsize=(W, 5.0), dpi=300, facecolor=SURF, sharex=True)
fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.07, hspace=0.32, wspace=0.24)
for j, tok in enumerate(["USDT", "USDC", "DAI"]):
    for s in ["G_all", "G_net", "G_net_xf", "G_simple"]:
        g = c4[(c4.token == tok) & (c4.scheme == s)].sort_values("month")
        if g.empty: continue
        ls = (0, (4, 2)) if s == "G_net_xf" else "-"
        axes[0, j].plot(g.month, g.nakamoto_50, color=SCHEME_C[s], linewidth=1.1, label=SL[s], linestyle=ls)
        axes[1, j].plot(g.month, g.top_1pct_share, color=SCHEME_C[s], linewidth=1.1, label=SL[s], linestyle=ls)
    style(axes[0, j], f"{tok}: Nakamoto coefficient", "Recipients (log)" if j == 0 else None, log=True)
    style(axes[1, j], f"{tok}: top-1% inflow share", "Share" if j == 0 else None)
h, l = axes[0, 2].get_legend_handles_labels(); fig.legend(h, l, loc="upper left", bbox_to_anchor=(0.07, 0.995), ncol=2, frameon=False, fontsize=6.8, labelcolor=INK2)
save(fig, "Fig3_concentration_definitions")

# ---------------- Fig 4: address vs entity level ----------------
SC = {"G_net": ("#eb6834", "Address level (G_net; DAI: G_net_xf)"), "G_net_entity": ("#2a78d6", "Entity level, intra-entity transfers removed"), "G_net_entity_xissuer": ("#1baf7a", "Entity level, issuer-side addresses removed")}
fig, axes = plt.subplots(2, 3, figsize=(W, 5.0), dpi=300, facecolor=SURF, sharex=True)
fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.07, hspace=0.32, wspace=0.24)
for j, tok in enumerate(["USDT", "USDC", "DAI"]):
    for s, (col, lab_) in SC.items():
        se = "G_net_xf" if (s == "G_net" and tok == "DAI") else s
        g = allc[(allc.token == tok) & (allc.scheme == se)].sort_values("month")
        axes[0, j].plot(g.month, g.nakamoto_50, color=col, linewidth=1.1, label=lab_)
        axes[1, j].plot(g.month, g.top_1pct_share, color=col, linewidth=1.1, label=lab_)
    style(axes[0, j], f"{tok}: Nakamoto coefficient", "Recipients/entities (log)" if j == 0 else None, log=True)
    style(axes[1, j], f"{tok}: top-1% inflow share", "Share" if j == 0 else None)
h, l = axes[0, 0].get_legend_handles_labels(); fig.legend(h, l, loc="upper left", bbox_to_anchor=(0.07, 0.995), ncol=2, frameon=False, fontsize=6.8, labelcolor=INK2)
save(fig, "Fig4_address_vs_entity")

# ---------------- Fig 5: destination by category ----------------
groups = {"Exchange hot wallets (labelled)": ["CEX"], "Issuer treasuries": ["Issuer"], "Lending protocols": ["DeFi-lending"], "DEX pools and aggregators": ["DeFi-DEX", "DEX-aggregator"],
          "Sky PSM / conversion modules": ["DeFi-PSM"], "Bridges, MEV bots, identified EOA clusters": ["Bridge", "MEV-bot", "unknown-EOA", "loop-like contract"],
          "Unlabelled contracts": ["unlabelled contract"], "Unlabelled EOAs": ["unlabelled EOA"]}
gcol = {"Exchange hot wallets (labelled)": "#2a78d6", "Issuer treasuries": "#0b4f9c", "Lending protocols": "#eb6834", "DEX pools and aggregators": "#1baf7a", "Sky PSM / conversion modules": "#7c4dbd",
        "Bridges, MEV bots, identified EOA clusters": "#c9a227", "Unlabelled contracts": "#b8b6ae", "Unlabelled EOAs": "#e6e4dc"}
fig, axes = plt.subplots(1, 3, figsize=(W, 3.1), dpi=300, facecolor=SURF)
fig.subplots_adjust(left=0.065, right=0.99, top=0.88, bottom=0.30, wspace=0.22)
for j, tok in enumerate(["USDT", "USDC", "DAI"]):
    g = cat[cat.token == tok].set_index("month").sort_index()
    series = [g[[c for c in v if c in g.columns]].sum(axis=1).rolling(3, min_periods=1).mean() for v in groups.values()]
    axes[j].stackplot(g.index, series, labels=list(groups.keys()), colors=[gcol[k] for k in groups], linewidth=0)
    style(axes[j], f"{tok}: destination of net inflow", "Share" if j == 0 else None, events=False)
    axes[j].set_ylim(0, 1); axes[j].yaxis.set_major_formatter(pct); axes[j].set_xlim(pd.Timestamp("2020-01-01"), pd.Timestamp("2026-09-01"))
h, l = axes[0].get_legend_handles_labels(); fig.legend(h, l, loc="upper left", bbox_to_anchor=(0.065, 0.17), ncol=4, frameon=False, fontsize=6.2, labelcolor=INK2, columnspacing=1.0)
save(fig, "Fig5_destination_by_category")

# ---------------- Fig 6: topology structure ----------------
panels = [("nodes", "A  Active addresses", True, None), ("bowtie_scc", "B  Largest strongly connected component", False, pct), ("reciprocity", "C  Reciprocity", False, pct),
          ("assortativity_deg", "D  Degree assortativity", False, None), ("max_kcore", "E  Maximum k-core", False, None), ("in_alpha_xmin10", "F  Tail exponent α (k ≥ 10)\nin-degree solid, out-degree dashed", False, None)]
fig, axes = plt.subplots(2, 3, figsize=(W, 5.0), dpi=300, facecolor=SURF, sharex=True)
fig.subplots_adjust(left=0.07, right=0.99, top=0.90, bottom=0.07, hspace=0.42, wspace=0.26)
for ax, (col, title, log, fmt) in zip(axes.flat, panels):
    for tok in ["USDT", "USDC", "DAI"]:
        g = t[t.token == tok].sort_values("month")
        ax.plot(g.month, g[col], color=TOKEN_C[tok], linewidth=1.1, marker="o", markersize=1.8, label=tok)
        if col == "in_alpha_xmin10": ax.plot(g.month, g.out_alpha_xmin10, color=TOKEN_C[tok], linewidth=0.9, linestyle=(0, (4, 2)), alpha=0.8)
    style(ax, title, log=log)
    if fmt: ax.yaxis.set_major_formatter(fmt)
    if col == "assortativity_deg": ax.axhline(0, color=AXIS, linewidth=0.6)
h, l = axes[0, 0].get_legend_handles_labels(); fig.legend(h, l, loc="upper left", bbox_to_anchor=(0.07, 0.99), ncol=3, frameon=False, fontsize=7, labelcolor=INK2)
save(fig, "Fig6_topology_structure")

# ---------------- Fig 7: in-degree CCDF ----------------
YEARS = {"2020-01-01": "#b8b6ae", "2023-01-01": "#7c4dbd", "2026-07-01": "#0b0b0b"}
fig, axes = plt.subplots(1, 3, figsize=(W, 2.8), dpi=300, facecolor=SURF)
fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.17, wspace=0.26)
for ax, tok in zip(axes, ["USDT", "USDC", "DAI"]):
    for i, (m, col) in enumerate(YEARS.items()):
        h = pd.read_csv(DATA / f"topo/zip/degree_hist/{tok}_{m}_indeg.csv"); h = h[h.degree > 0].sort_values("degree"); n = h["count"].sum()
        ccdf = 1 - (h["count"].cumsum() - h["count"]) / n
        ax.plot(h.degree, ccdf, color=col, linewidth=1.1)
        a = t[(t.token == tok) & (t.month == m)].iloc[0]
        ax.text(0.98, 0.95 - 0.09 * i, f"{m[:7]}: α(k≥10) = {a.in_alpha_xmin10:.2f}", transform=ax.transAxes, ha="right", va="top", fontsize=6.8, color=col)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("In-degree k (distinct senders)", fontsize=7.5, color=INK2)
    style(ax, f"{tok}: P(K ≥ k)", events=False, xgrid=True)
axes[0].set_ylabel("P(K ≥ k)", fontsize=7.5, color=INK2)
save(fig, "Fig7_indegree_ccdf")

# ---------------- Fig 8: in-strength CCDF ----------------
fig, axes = plt.subplots(1, 3, figsize=(W, 2.8), dpi=300, facecolor=SURF)
fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.17, wspace=0.26)
for ax, tok in zip(axes, ["USDT", "USDC", "DAI"]):
    for i, (m, col) in enumerate(YEARS.items()):
        h = pd.read_csv(DATA / f"topo/v4/zip/strength_hist/{tok}_{m}_instr.csv"); n = h["count"].sum()
        ccdf = (n - h["count"].cumsum() + h["count"]) / n; x = 10 ** h.log10_left
        ax.plot(x[ccdf > 0], ccdf[ccdf > 0], color=col, linewidth=1.1)
        a = tf.loc[(tok, m)]
        ax.text(0.03, 0.05 + 0.09 * (2 - i), f"{m[:7]}: α = {a.in_strength_alpha:.2f}, $x_{{\\min}}$ ≈ \\${a.in_strength_xmin/1e3:,.0f}k", transform=ax.transAxes, ha="left", va="bottom", fontsize=6.8, color=col)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("Monthly in-strength s (USD)", fontsize=7.5, color=INK2)
    style(ax, f"{tok}: P(S ≥ s)", events=False, xgrid=True)
axes[0].set_ylabel("P(S ≥ s)", fontsize=7.5, color=INK2)
save(fig, "Fig8_instrength_ccdf")

# ---------------- Fig 9: preferential attachment ----------------
fig, axes = plt.subplots(1, 2, figsize=(W, 3.0), dpi=300, facecolor=SURF, sharey=True)
fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.12, wspace=0.08)
for ax, mode, title in zip(axes, ["in", "out"], ["A  In-degree: $\\Pi(k) \\propto k^{\\beta}$", "B  Out-degree"]):
    for tok in ["USDT", "USDC", "DAI"]:
        g = pa[(pa.token == tok) & (pa["mode"] == mode)].sort_values("t")
        ax.errorbar(g.t, g.beta_bin, yerr=1.96 * g.beta_bin_se, color=TOKEN_C[tok], fmt="o", markersize=2.8, capsize=1.5, elinewidth=0.8, label=tok)
        ax.plot(g.t, g.beta_bin, color=TOKEN_C[tok], linewidth=0.9, alpha=0.7)
    ax.axhline(1.0, color=INK, linewidth=0.8, linestyle=(0, (4, 2)))
    style(ax, title, "β" if mode == "in" else None, events=False); ax.set_ylim(0.8, 2.2)
axes[0].legend(frameon=False, fontsize=7, labelcolor=INK2, loc="upper right", ncol=3)
save(fig, "Fig9_preferential_attachment")
print("done")

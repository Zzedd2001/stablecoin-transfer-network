#!/usr/bin/env python3
"""Fact sheet: recompute every statistic quoted in the manuscript directly from the exported CSVs."""
import pandas as pd, numpy as np, glob
from scipy import stats
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 500)
import os
P = os.environ.get("STABLECOIN_DATA", "data").rstrip("/") + "/"   # repository data folder (run from the repository root)
def tau(x):
    t = np.arange(len(x)); r = stats.kendalltau(t, x); return r[0], r[1]
def sec(t): print("\n" + "=" * 12, t, "=" * 12)

c = pd.read_csv(P + "concentration_three_ways.csv", parse_dates=["month"])
xf = pd.read_csv(P + "dai/concentration_dai_net_xf.csv", parse_dates=["month"])
ent = pd.read_csv(P + "entity/concentration_entity_level.csv", parse_dates=["month"])
allc = pd.concat([c, xf, ent], ignore_index=True); allc["year"] = allc.month.dt.year
f = pd.read_csv(P + "flow_composition_month.csv", parse_dates=["month"]); f["year"] = f.month.dt.year
d = pd.read_csv(P + "dyad_month.csv", parse_dates=["month"]); d["year"] = d.month.dt.year
fm = pd.read_csv(P + "dai/dai_flashmint_share.csv", parse_dates=["month"]); fm["year"] = fm.month.dt.year
top = pd.read_csv(P + "top_receivers_net.csv", parse_dates=["month"])
te = pd.read_csv(P + "entity/top_receivers_entity.csv", parse_dates=["month"])
lab = pd.read_csv(os.environ.get("STABLECOIN_LABELS", "labels/labels_final.csv")); lab["address"] = lab.address.str.lower()
cat = pd.read_csv(P + "entity/inflow_by_category_month.csv", parse_dates=["month"]); cat["year"] = cat.month.dt.year
topo = pd.read_csv(P + "topo/topology_metrics.csv", parse_dates=["month"])
afx = pd.read_csv(P + "topo/alpha_fixed_xmin.csv", parse_dates=["month"])
dfo = pd.read_csv(P + "topo/degree_fits_offline.csv", parse_dates=["month"])
tf = pd.read_csv(P + "topo/v4/tail_fits.csv"); tfq = tf[tf.month.str[5:7].isin(["01", "04", "07", "10"])]
pa = pd.read_csv(P + "topo/v2/pa_results_v2.csv"); pa["year"] = pa.month_t.str[:4].astype(int)

# ------------------------------------------------------------------ Scale / Table 1
sec("ABSTRACT / SCALE / TABLE 1")
print("raw non-mint events (M):", round(f.all_n.sum() / 1e6, 1), "| transfers/month 2020 vs 2026 (M):", round(f[f.year == 2020].groupby("month").all_n.sum().mean() / 1e6, 1), round(f[f.year == 2026].groupby("month").all_n.sum().mean() / 1e6, 1))
print("gross value 2020 / 2026 (T):", round(f[f.year == 2020].gross_usd.sum() / 1e12, 2), round(f[f.year == 2026].gross_usd.sum() / 1e12, 2))
for s_ in ["G_all", "G_net", "G_simple"]:
    g = c[c.scheme == s_]; print(s_, "records (M)", round(g.n_transfers.sum() / 1e6, 1), "value (T)", round(g.volume_usd.sum() / 1e12, 2))
t1 = c.groupby(["token", "scheme"]).agg(rec_M=("n_transfers", lambda v: v.sum() / 1e6), val_T=("volume_usd", lambda v: v.sum() / 1e12), recv=("n_receivers", "mean"), send=("n_senders", "mean"))
print(t1.round(2)); x = xf; print("DAI G_net_xf", round(x.n_transfers.sum() / 1e6, 1), round(x.volume_usd.sum() / 1e12, 2), round(x.n_receivers.mean()), round(x.n_senders.mean()))
for tok in ["USDT", "USDC", "DAI"]:
    a = c[(c.token == tok) & (c.scheme == "G_all")].n_transfers.sum(); n = c[(c.token == tok) & (c.scheme == "G_net")].n_transfers.sum()
    va = c[(c.token == tok) & (c.scheme == "G_all")].volume_usd.sum(); vn = c[(c.token == tok) & (c.scheme == "G_net")].volume_usd.sum()
    print(tok, f"netting removes records {(a-n)/a:.1%} value {(va-vn)/va:.1%}")
rec = c[c.scheme == "G_net"].pivot_table(index="token", columns="year", values="n_receivers", aggfunc="mean") if "year" in c else None
c["year"] = c.month.dt.year
print("mean monthly receivers G_net by year:\n", c[c.scheme == "G_net"].pivot_table(index="token", columns="year", values="n_receivers", aggfunc="mean").round(0))
# simple share 2020 & 2026 by token (count & value, value-weighted)
# payment-like (G_simple) shares. NOTE: simple_n / all_n in flow_composition_month.csv count ALL non-mint events (sub-dollar dust
# included; this is the last column of S1 Table). The count share reported in the paper (92% -> 57% for USDT) is computed on the
# filtered network: G_simple n_transfers / G_all n_transfers from concentration_all_schemes.csv. The value share is reported against
# net value (simple_usd / net_usd); the gross-based share (simple_usd / gross_usd) is given in S1 Table for comparison.
cnt = c.pivot_table(index=["token", "month"], columns="scheme", values="n_transfers"); cnt["share"] = cnt["G_simple"] / cnt["G_all"]; cnt = cnt.reset_index(); cnt["year"] = cnt.month.dt.year
for tok in ["USDT", "USDC", "DAI"]:
    g0 = f[(f.token == tok) & (f.year == 2020)]; g1 = f[(f.token == tok) & (f.year == 2026)]
    k0 = cnt[(cnt.token == tok) & (cnt.year == 2020)]; k1 = cnt[(cnt.token == tok) & (cnt.year == 2026)]
    print(tok, "simple count share, filtered network 2020→2026: %.3f → %.3f | all non-mint events: %.3f → %.3f" % (k0.G_simple.sum() / k0.G_all.sum(), k1.G_simple.sum() / k1.G_all.sum(), g0.simple_n.sum() / g0.all_n.sum(), g1.simple_n.sum() / g1.all_n.sum()))
    print("   simple value share vs NET value: %.3f → %.3f | vs gross value: %.3f → %.3f" % (g0.simple_usd.sum() / g0.net_usd.sum(), g1.simple_usd.sum() / g1.net_usd.sum(), g0.simple_usd.sum() / g0.gross_usd.sum(), g1.simple_usd.sum() / g1.gross_usd.sum()))
    print("   G_simple transfers per month (M), 2020 vs 2026: %.2f vs %.2f" % (k0.G_simple.mean() / 1e6, k1.G_simple.mean() / 1e6))
    kk = cnt[cnt.token == tok].sort_values("month"); gg = f[f.token == tok].sort_values("month")
    print("   tau filtered count share", tuple(round(v, 3) if i == 0 else float(f"{v:.1g}") for i, v in enumerate(tau(kk.share))), "| tau net-value share", tuple(round(v, 3) if i == 0 else float(f"{v:.1g}") for i, v in enumerate(tau(gg.simple_usd / gg.net_usd))))
# dyad shares value-weighted
dy = d.groupby(["scheme", "token", "year", "dyad"]).agg(usd=("usd", "sum"), n=("n", "sum")).reset_index()
dy["vs"] = dy.usd / dy.groupby(["scheme", "token", "year"]).usd.transform("sum"); dy["cs"] = dy.n / dy.groupby(["scheme", "token", "year"]).n.transform("sum")
sc = dy[dy.dyad != "EOA->EOA"].groupby(["scheme", "token", "year"]).agg(sc_v=("vs", "sum"), sc_c=("cs", "sum"))
print("contract-involving value share (G_net):\n", sc.loc["G_net"].sc_v.unstack("year").round(3))
print("contract-involving count share (G_net):\n", sc.loc["G_net"].sc_c.unstack("year").round(3))
print("EOA->EOA value share 2020 G_net:", dy[(dy.scheme == "G_net") & (dy.year == 2020) & (dy.dyad == "EOA->EOA")][["token", "vs"]].round(3).to_dict("records"))
print("SC->SC value share 2026 G_all vs G_net:", dy[(dy.year == 2026) & (dy.dyad == "SC->SC")][["scheme", "token", "vs"]].round(3).to_dict("records"))

# ------------------------------------------------------------------ Flow composition (S1 Table)
sec("FLOW COMPOSITION (S1 TABLE)")
cy = f.groupby(["token", "year"]).apply(lambda g: pd.Series({"gross_B": g.gross_usd.sum() / 1e9, "net_B": g.net_usd.sum() / 1e9, "rt": g.flashloan_like_usd.sum() / g.gross_usd.sum(), "nr": 1 - g.net_usd.sum() / g.gross_usd.sum(), "sv_gross": g.simple_usd.sum() / g.gross_usd.sum(), "sv_net": g.simple_usd.sum() / g.net_usd.sum(), "sc_all_events": g.simple_n.sum() / g.all_n.sum()}))
cy["sc_filtered"] = cnt.groupby(["token", "year"]).apply(lambda k: k.G_simple.sum() / k.G_all.sum())
print(cy.round(3))
for tok in ["USDT", "USDC", "DAI"]:
    g = f[f.token == tok]; i = g.flashloan_share.idxmax(); print(tok, "peak month", g.loc[i, "month"].strftime("%Y-%m"), round(g.loc[i, "flashloan_share"], 3), "gross B", round(g.loc[i, "gross_usd"] / 1e9), "fl B", round(g.loc[i, "flashloan_like_usd"] / 1e9))
print("USDC 2024 vs 2026 net T:", round(f[(f.token == "USDC") & (f.year == 2024)].net_usd.sum() / 1e12, 2), round(f[(f.token == "USDC") & (f.year == 2026)].net_usd.sum() / 1e12, 2), "gross ratio", round(f[(f.token == "USDC") & (f.year == 2026)].gross_usd.sum() / f[(f.token == "USDC") & (f.year == 2024)].gross_usd.sum(), 2))
print("non-flash netting (nr - rt) 2026:", (cy.loc[("USDT", 2026), "nr"] - cy.loc[("USDT", 2026), "rt"]).round(4), (cy.loc[("USDC", 2026), "nr"] - cy.loc[("USDC", 2026), "rt"]).round(4))

# ------------------------------------------------------------------ DAI flash mint
sec("DAI FLASH MINT")
print(fm.groupby("year").apply(lambda g: g.flashmint_usd.sum() / g.net_inflow_usd.sum()).round(3).to_dict())
print("2023+ :", round(fm[fm.year >= 2023].flashmint_usd.sum() / fm[fm.year >= 2023].net_inflow_usd.sum(), 3), "| peak", fm.loc[fm.flashmint_share.idxmax(), ["month", "flashmint_share", "flashmint_usd"]].to_dict(), "| first", fm[fm.flashmint_usd > 0].month.min().strftime("%Y-%m"))
print("2026-09:", fm[fm.month == "2026-09-01"][["flashmint_usd", "net_inflow_usd", "flashmint_share"]].round(3).to_dict("records"))
print("DAI net value G_net vs G_net_xf (T):", round(c[(c.token == "DAI") & (c.scheme == "G_net")].volume_usd.sum() / 1e12, 2), round(xf.volume_usd.sum() / 1e12, 2))

# ------------------------------------------------------------------ Concentration (Table 2)
sec("CONCENTRATION (TABLE 2)")
for (tok, s_), g in allc.groupby(["token", "scheme"]):
    g = g.sort_values("month"); yr = g.groupby("year").agg(gini=("gini_inflow", "mean"), t1=("top_1pct_share", "mean"), t01=("top_0_1pct_share", "mean"), nak=("nakamoto_50", "mean"))
    tg, pg = tau(g.gini_inflow); tt, pt = tau(g.top_1pct_share); tn, pn = tau(g.nakamoto_50)
    print(f"{tok:4s} {s_:22s} gini {yr.loc[2020,'gini']:.3f}/{yr.loc[2023,'gini']:.3f}/{yr.loc[2026,'gini']:.3f} tau {tg:+.2f} p={pg:.1g} | top1 {yr.loc[2020,'t1']:.3f}/{yr.loc[2023,'t1']:.3f}/{yr.loc[2026,'t1']:.3f} tau {tt:+.2f} p={pt:.1g} | top0.1 {yr.loc[2020,'t01']:.3f}→{yr.loc[2026,'t01']:.3f} | N50 {yr.loc[2020,'nak']:.0f}/{yr.loc[2023,'nak']:.0f}/{yr.loc[2026,'nak']:.1f} tau {tn:+.2f} p={pn:.1g}")
late = allc[allc.month >= "2025-07-01"]
print("Jul25–Sep26 mean N50:\n", late.pivot_table(index="token", columns="scheme", values="nakamoto_50", aggfunc="mean").round(1))
for tok in ["USDT", "USDC"]:
    a = late[(late.token == tok) & (late.scheme == "G_all")]; n = late[(late.token == tok) & (late.scheme == "G_net")]
    print(tok, "months N50<=2 under G_all:", int((a.nakamoto_50 <= 2).sum()), "of", len(a), "| min N50 G_net:", int(n.nakamoto_50.min()))
print("USDC 2026 mean receivers (G_net):", round(c[(c.token == "USDC") & (c.scheme == "G_net") & (c.year == 2026)].n_receivers.mean()))

# ------------------------------------------------------------------ Labels / destination (S2 Table) / regular players
sec("LABELS, DESTINATION, REGULAR PLAYERS")
print("labels:", len(lab), lab.confidence.value_counts().to_dict(), lab.category.value_counts().to_dict(), "entities", lab.entity_group.nunique())
print("top20 rows", len(top), "distinct addresses", top.address.nunique(), top.groupby("token").address.nunique().to_dict())
top["labeled"] = top.address.isin(set(lab.address)); top["year"] = top.month.dt.year
print("label coverage of top-20 inflow:", top.groupby("token").apply(lambda g: g.loc[g.labeled, "inflow_usd"].sum() / g.inflow_usd.sum()).round(3).to_dict())
cov = top.groupby(["token", "year"]).share_of_month.sum().div(top.groupby(["token", "year"]).month.nunique()).unstack(0)
print("top-20 share of monthly inflow by year:\n", cov.round(3))
tot = cat.groupby(["token", "year"]).usd.sum(); sh = cat.groupby(["token", "year", "category"]).usd.sum().div(tot).unstack("category").fillna(0) * 100
print((sh.round(1)))
sh["labelled"] = 100 - sh["unlabelled contract"] - sh["unlabelled EOA"]; print("labelled share range:", sh.labelled.groupby("token").agg(["min", "max"]).round(1).to_dict())
print("unlabelled EOA range:", sh["unlabelled EOA"].groupby("token").agg(["min", "max"]).round(1).to_dict())
m = cat.pivot_table(index=["token", "month"], columns="category", values="usd", aggfunc="sum").fillna(0); m = m.div(m.sum(axis=1), axis=0)
print("DAI 2026-09 PSM share:", round(m.loc[("DAI", pd.Timestamp("2026-09-01")), "DeFi-PSM"], 3))
# persistence
def persist(t, label, col="node"):
    out = {}
    for tok, g in t.groupby("token"):
        cnt = g.groupby(col).month.nunique(); out[tok] = dict(distinct=len(cnt), ge65=int((cnt >= 65).sum()), ge41=int((cnt >= 41).sum()),
            share2026_regulars=round(g[(g.month >= "2026-01-01") & (g[col].isin(cnt[cnt >= 41].index))].share_of_month.sum() / g[g.month >= "2026-01-01"].month.nunique(), 3))
    print(label, out)
persist(top.rename(columns={"address": "node"}), "address level"); persist(te, "entity level")
for tok, g in te.groupby("token"):
    cnt = g.groupby("node").agg(months=("month", "nunique"), first=("month", "min"), last=("month", "max")).sort_values("months", ascending=False).head(9)
    print(tok, [(i, int(r.months), r["first"].strftime("%Y-%m"), r["last"].strftime("%Y-%m")) for i, r in cnt.iterrows()])
arb = te[te.node == "Unlabeled-arb-operator"]; print("arb operator months by token:", arb.groupby("token").month.nunique().to_dict(), "max USDC share", round(arb[arb.token == "USDC"].share_of_month.max(), 3), arb[arb.token == "USDC"].sort_values("share_of_month").iloc[-1].month.strftime("%Y-%m"))
bot = top[top.address == "0xa69babef1ca67a37ffaf7a485dfff3382056e78c"]; print("inventory bot USDC months", int(bot[bot.token == "USDC"].month.nunique()), bot[bot.token == "USDC"].month.min().strftime("%Y-%m"), bot[bot.token == "USDC"].month.max().strftime("%Y-%m"), "max share", round(bot[bot.token == "USDC"].share_of_month.max(), 3))

# ------------------------------------------------------------------ Events (Table 4)
sec("EVENTS (TABLE 4)")
ev = {"Terra": "2022-05-01", "FTX": "2022-11-01", "USDC depeg": "2023-03-01", "Oct-10 crash": "2025-10-01"}
for tok, s_ in [("USDT", "G_net"), ("USDC", "G_net"), ("DAI", "G_net_xf"), ("USDC", "G_all")]:
    x = allc[(allc.token == tok) & (allc.scheme == s_)].set_index("month").sort_index()
    met = {"nak": np.log(x.nakamoto_50), "top1": x.top_1pct_share, "recv": np.log(x.n_receivers), "vol": np.log(x.volume_usd)}
    for name, mth in ev.items():
        mth = pd.Timestamp(mth); pre = x.loc[mth - pd.DateOffset(months=3): mth - pd.DateOffset(months=1)]
        row = f"{tok} {s_} {name}: N50 {x.loc[mth,'nakamoto_50']}/{pre.nakamoto_50.mean():.1f}  top1 {100*(x.loc[mth,'top_1pct_share']-pre.top_1pct_share.mean()):+.1f}pp  vol x{x.loc[mth,'volume_usd']/pre.volume_usd.mean():.2f}  recv x{x.loc[mth,'n_receivers']/pre.n_receivers.mean():.2f}"
        pcts = []
        for k, ser in met.items():
            prior = ser.shift(1).rolling(3).mean(); ch = (ser - prior).dropna(); placebo = ch[~ch.index.isin([pd.Timestamp(v) for v in ev.values()])]
            pcts.append(f"{k}:{(placebo < ch.loc[mth]).mean()*100:.0f}")
        print(row, "| pct", " ".join(pcts), "| n_placebo", len(placebo))
print("USDC 2025-10 gross/net B:", f[(f.token == "USDC") & (f.month == "2025-10-01")][["gross_usd", "net_usd"]].div(1e9).round(0).to_dict("records"))

# ------------------------------------------------------------------ Topology (Table 5)
sec("TOPOLOGY (TABLE 5)")
tt = topo.merge(afx[["token", "month", "in_alpha_xmin10", "out_alpha_xmin10"]], on=["token", "month"]).merge(dfo, on=["token", "month"])
for tok, g in tt.groupby("token"):
    g = g.sort_values("month"); f0, l0 = g.iloc[0], g.iloc[-1]
    print(tok, f"nodes {f0.nodes:,}→{l0.nodes:,} max {g.nodes.max():,} ({g.loc[g.nodes.idxmax(),'month']:%Y-%m}) | edges {f0.edges/1e6:.2f}M→{l0.edges/1e6:.2f}M | lwcc {g.lwcc_share.min():.3f}–{g.lwcc_share.max():.3f} | SCC {g.bowtie_scc.min():.2f}–{g.bowtie_scc.max():.2f} (2020-01 {f0.bowtie_scc:.2f}, 2026-07 {l0.bowtie_scc:.2f}) IN/OUT 2026-07 {l0.bowtie_in:.2f}/{l0.bowtie_out:.2f} | recip {g.reciprocity.min():.3f}–{g.reciprocity.max():.3f} | assort {g.assortativity_deg.min():.2f}–{g.assortativity_deg.max():.2f} | kcore {int(f0.max_kcore)}→{int(l0.max_kcore)} (min {int(g.max_kcore.min())} max {int(g.max_kcore.max())}) | transitivity median {g.transitivity_global.median():.1e} | sc nodes {f0.share_sc_nodes:.3f}→{l0.share_sc_nodes:.3f}")
    print("    alpha in k>=10 mean %.2f (%.2f–%.2f) out %.2f (%.2f–%.2f)" % (g.in_alpha_xmin10.mean(), g.in_alpha_xmin10.min(), g.in_alpha_xmin10.max(), g.out_alpha_xmin10.mean(), g.out_alpha_xmin10.min(), g.out_alpha_xmin10.max()),
          "| logn better in/out: %d/%d, pl better %d/%d, inconclusive %d/%d" % (((g.in_p_logn < .05) & (g.in_LR_logn < 0)).sum(), ((g.out_p_logn < .05) & (g.out_LR_logn < 0)).sum(), ((g.in_p_logn < .05) & (g.in_LR_logn > 0)).sum(), ((g.out_p_logn < .05) & (g.out_LR_logn > 0)).sum(), (g.in_p_logn >= .05).sum(), (g.out_p_logn >= .05).sum()),
          "| trunc better in %d out %d | pl vs exp all positive in %s out %s" % ((g.in_p_trunc < .05).sum(), (g.out_p_trunc < .05).sum(), bool((g.in_LR_exp > 0).all()), bool((g.out_LR_exp > 0).all())))
    print("    trends: recip tau %.2f p=%.2g | assort tau %.2f p=%.2g | kcore tau %.2f p=%.2g | in_alpha10 tau %.2f p=%.2g | out_alpha10 tau %.2f p=%.2g" % (*tau(g.reciprocity), *tau(g.assortativity_deg), *tau(g.max_kcore), *tau(g.in_alpha_xmin10), *tau(g.out_alpha_xmin10)))
print("all tokens: logn better in", int(((tt.in_p_logn < .05) & (tt.in_LR_logn < 0)).sum()), "pl better in", int(((tt.in_p_logn < .05) & (tt.in_LR_logn > 0)).sum()), "| out", int(((tt.out_p_logn < .05) & (tt.out_LR_logn < 0)).sum()), int(((tt.out_p_logn < .05) & (tt.out_LR_logn > 0)).sum()), "| trunc in", int((tt.in_p_trunc < .05).sum()), tt[tt.in_p_trunc < .05].groupby("token").size().to_dict(), "out", int((tt.out_p_trunc < .05).sum()))
print("USDC yearly recip:", tt[tt.token == "USDC"].groupby(tt.month.dt.year).reciprocity.mean().round(3).to_dict())
print("USDT yearly assort:", tt[tt.token == "USDT"].groupby(tt.month.dt.year).assortativity_deg.mean().round(3).to_dict())
print("USDT kcore 2022-2023 range:", tt[(tt.token == "USDT") & (tt.month.dt.year.isin([2022, 2023]))].max_kcore.agg(["min", "max"]).to_dict(), "| 2020-10:", int(tt[(tt.token == "USDT") & (tt.month == "2020-10-01")].max_kcore.iloc[0]))
# degree shares
for tok in ["USDT", "USDC", "DAI"]:
    for mth in ["2020-01-01", "2026-07-01"]:
        h = pd.read_csv(P + f"topo/zip/degree_hist/{tok}_{mth}_indeg.csv"); n = h["count"].sum(); hp = h[h.degree > 0]; npos = hp["count"].sum()
        print(tok, mth, "share k=1 among receivers %.3f | k>=10 %.4f | k>=1000 %d | max %d" % (hp.loc[hp.degree == 1, "count"].sum() / npos, hp.loc[hp.degree >= 10, "count"].sum() / npos, hp.loc[hp.degree >= 1000, "count"].sum(), hp.degree.max()))
# strength fits
for tok, g in tfq.groupby("token"):
    g = g.sort_values("month")
    print(tok, "in_strength alpha %.2f (%.2f–%.2f) out %.2f (%.2f–%.2f) | xmin median %.0f | logn better %d pl better %d | trunc %d | exp all %s | tau alpha %.2f p=%.2g" % (g.in_strength_alpha.mean(), g.in_strength_alpha.min(), g.in_strength_alpha.max(), g.out_strength_alpha.mean(), g.out_strength_alpha.min(), g.out_strength_alpha.max(), g.in_strength_xmin.median(), ((g.in_strength_p_pl_vs_lognormal < .05) & (g.in_strength_LR_pl_vs_lognormal < 0)).sum(), ((g.in_strength_p_pl_vs_lognormal < .05) & (g.in_strength_LR_pl_vs_lognormal > 0)).sum(), (g.in_strength_p_pl_vs_truncated < .05).sum(), bool((g.in_strength_LR_pl_vs_exponential > 0).all()), *tau(g.in_strength_alpha)))
    print("    xmin range", g.in_strength_xmin.min(), g.in_strength_xmin.max(), "| n_tail range", int(g.in_strength_n_tail.min()), int(g.in_strength_n_tail.max()), "| USDT alpha 2020-10..2021-07 vs 2025-26:", g[(g.month >= "2020-10-01") & (g.month <= "2021-07-01")].in_strength_alpha.mean().round(2), g[g.month >= "2025-01-01"].in_strength_alpha.mean().round(2))

# ------------------------------------------------------------------ PA (Table 6)
sec("PREFERENTIAL ATTACHMENT (TABLE 6)")
pa["lo"] = pa.beta_bin - 1.96 * pa.beta_bin_se
print("n", len(pa), "all beta_bin>1:", bool((pa.beta_bin > 1).all()), "| lower95>1:", int((pa.lo > 1).sum()), "| exception:", pa.loc[pa.lo <= 1, ["token", "month_t", "mode", "beta_bin", "beta_bin_se"]].round(2).to_dict("records"))
print("r2_bin min/median/max", pa.r2_bin.min().round(3), pa.r2_bin.median().round(3), pa.r2_bin.max().round(3))
g2 = pa[pa.year >= 2021]
print(g2.groupby(["token", "mode"]).beta_bin.agg(["mean", "min", "max"]).round(2)); print(g2.groupby(["token", "mode"]).beta_cum.mean().round(2))
print(pa.groupby(["token", "mode"]).share_new_to_old.agg(["min", "max"]).round(2))
print("bull vs bear:", round(pa[pa.year.isin([2021, 2024, 2025])].beta_bin.mean(), 3), round(pa[pa.year.isin([2022, 2023])].beta_bin.mean(), 3), "MWU p=%.2g" % stats.mannwhitneyu(pa[pa.year.isin([2021, 2024, 2025])].beta_bin, pa[pa.year.isin([2022, 2023])].beta_bin)[1])
for a, b in [("DAI", "USDC"), ("USDC", "USDT"), ("DAI", "USDT")]:
    print(a, b, "MWU p=%.2g" % stats.mannwhitneyu(g2[g2.token == a].beta_bin, g2[g2.token == b].beta_bin)[1])
pv = pa.pivot_table(index=["token", "year", "mode"], columns=pa.month_t.str[5:7], values="beta_bin"); dd_ = (pv["01"] - pv["07"]).abs().dropna(); print("Jan-Jul abs diff median %.2f max %.2f" % (dd_.median(), dd_.max()))

# ------------------------------------------------------------------ Fixed-count shares at the size of the top 1% (Q19, S5 Table)
sec("FIXED-COUNT SHARES, Q19 (S5 TABLE)")
try:
    q19 = pd.read_csv(P + "followup/q19_fixed_count_share_month.csv", parse_dates=["month"]).sort_values(["token", "month"]); q19["year"] = q19.month.dt.year
    qc = [c_ for c_ in q19.columns if c_.startswith("top")]
    for tok, g in q19.groupby("token"):
        print(tok, "top-1% size 2020 / 2026:", round(g[g.year == 2020].n_top1pct.mean()), "/", round(g[g.year == 2026].n_top1pct.mean()),
              "| recipients 2020 / 2026:", round(g[g.year == 2020].n_receivers.mean()), "/", round(g[g.year == 2026].n_receivers.mean()))
        for c_ in qc:
            t_, p_ = tau(g[c_].values)
            print(f"   {c_:15s} 2020 {100 * g[g.year == 2020][c_].mean():5.1f}%  2026 {100 * g[g.year == 2026][c_].mean():5.1f}%  tau {t_:+.2f} p {p_:.2g}")
    q18_ = pd.read_csv(P + "followup/q18_topN_inflow_share_month.csv", parse_dates=["month"])
    mm = q19.merge(q18_[["token", "month", "top1000_share"]], on=["token", "month"])
    for y in (2020, 2026):
        gy = mm[(mm.token == "USDC") & (mm.year == y)]; print("USDC layer 1,001-12,500 share", y, round(100 * (gy.top12500_share - gy.top1000_share).mean(), 1), "| 12,500 as % of recipients", round(100 * 12500 / gy.n_receivers.mean(), 1))
except FileNotFoundError:
    print("q19_fixed_count_share_month.csv not found")

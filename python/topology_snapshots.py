#!/usr/bin/env python3
"""
Topology metrics: stream the monthly G_net edge list of each quarterly snapshot from BigQuery, compute network-structure
metrics with igraph, and run the Jeong–Néda–Barabási preferential-attachment test on consecutive months.

Run locally (Mac):
  python3 -m venv venv && source venv/bin/activate
  pip install google-cloud-bigquery google-cloud-bigquery-storage db-dtypes pyarrow pandas numpy scipy python-igraph powerlaw
  gcloud auth application-default login          # one-off browser login
  python topology_snapshots.py --project YOUR_PROJECT --tokens USDC USDT DAI

Outputs (out/ in the current directory):
  topology_metrics.csv   one row of structure metrics per (token, month)
  pa_results.csv         preferential-attachment exponent β for consecutive months
  degree_hist/*.csv      in-/out-degree histograms (for CCDF plots)
  cache/*.parquet        cached edge lists (re-runs cost nothing)
Cost: each month scans one partition range of transfers_netted (about 1–3 GB); 27 snapshots × 3 tokens < 0.5 USD.
"""
import argparse, os, sys, time, json
from pathlib import Path
import numpy as np
import pandas as pd

# ------------------------------------------------------------------ configuration
QUARTER_MONTHS = [f"{y}-{m:02d}-01" for y in range(2020, 2027) for m in (1, 4, 7, 10)]
QUARTER_MONTHS = [m for m in QUARTER_MONTHS if m <= "2026-07-01"]          # 27 snapshots
PA_PAIRS = [(f"{y}-01-01", f"{y}-02-01") for y in range(2020, 2027)]        # January→February of each year

# addresses removed as flash-loan legs (verified; e.g. the MakerDAO Flash Mint Module)
EXCLUDE_ADDRESSES = {
    "0x60744434d6339a6b27d73d9eda62b6f66a0a04fa",     # Sky: MCD Flash (DAI flash-mint module, verified)
}

SQL_EDGES = """
SELECT t.from_address, t.to_address,
       SUM(t.usd_value_net) AS w, COUNT(*) AS n,
       IF(cf.address IS NOT NULL AND cf.created_at <= TIMESTAMP(@month_end), 'SC', 'EOA') AS from_type,
       IF(ct.address IS NOT NULL AND ct.created_at <= TIMESTAMP(@month_end), 'SC', 'EOA') AS to_type
FROM `{project}.stable.transfers_netted` t
LEFT JOIN `{project}.stable.contracts` cf ON cf.address = t.from_address
LEFT JOIN `{project}.stable.contracts` ct ON ct.address = t.to_address
WHERE t.token = @token
  AND t.block_timestamp >= TIMESTAMP(@month_start) AND t.block_timestamp < TIMESTAMP(@month_end)
  AND NOT t.is_flashloan_like AND t.usd_value_net >= 1
GROUP BY 1, 2, 5, 6
"""


def fetch_edges(client, project, token, month, cache_dir):
    """fetch one month of the netted edge list (cached)"""
    from google.cloud import bigquery
    cache = cache_dir / f"{token}_{month}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    month_end = (pd.Timestamp(month) + pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    job = client.query(SQL_EDGES.format(project=project), job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("token", "STRING", token),
        bigquery.ScalarQueryParameter("month_start", "STRING", month),
        bigquery.ScalarQueryParameter("month_end", "STRING", month_end)]))
    df = job.result().to_dataframe(create_bqstorage_client=True)
    if EXCLUDE_ADDRESSES:
        df = df[~df.from_address.isin(EXCLUDE_ADDRESSES) & ~df.to_address.isin(EXCLUDE_ADDRESSES)]
    df.to_parquet(cache, index=False)
    print(f"   fetched {token} {month}: {len(df):,} edges, {job.total_bytes_processed/1e9:.2f} GB scanned")
    return df


def build_graph(df):
    import igraph as ig
    nodes = pd.Index(pd.unique(pd.concat([df.from_address, df.to_address], ignore_index=True)))
    g = ig.Graph(n=len(nodes), directed=True)
    g.add_edges(list(zip(nodes.get_indexer(df.from_address), nodes.get_indexer(df.to_address))))
    g.es["w"] = df.w.to_numpy(dtype=float)
    typ = pd.Series(df.from_type.values, index=df.from_address.values)
    typ = pd.concat([typ, pd.Series(df.to_type.values, index=df.to_address.values)])
    typ = typ[~typ.index.duplicated()]
    g.vs["type"] = typ.reindex(nodes).fillna("EOA").tolist()
    return g


def tail_fit(values, name):
    import powerlaw
    v = np.asarray(values, dtype=float); v = v[v > 0]
    if len(v) < 1000:
        return {f"{name}_alpha": np.nan}
    # restrict the xmin search range on large samples to bound run time
    fit = powerlaw.Fit(v, discrete=True, xmin=(2, 1000), verbose=False)
    R, p = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    return {f"{name}_alpha": fit.power_law.alpha, f"{name}_xmin": fit.power_law.xmin, f"{name}_sigma": fit.power_law.sigma,
            f"{name}_LR_pl_vs_lognormal": R, f"{name}_LR_p": p}


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return 2 * np.sum(np.arange(1, n + 1) * x) / (n * x.sum()) - (n + 1) / n if n and x.sum() else np.nan


def nakamoto(x, share=0.5):
    x = np.sort(np.asarray(x, float))[::-1]; cum = np.cumsum(x) / x.sum()
    return int(np.searchsorted(cum, share) + 1)


def metrics(g, df, token, month, out_hist_dir):
    t0 = time.time()
    indeg = np.array(g.degree(mode="in")); outdeg = np.array(g.degree(mode="out"))
    s_in = np.array(g.strength(mode="in", weights="w"))
    wcc = g.connected_components(mode="weak"); scc = g.connected_components(mode="strong")
    giant_scc = set(max(scc, key=len)); seed = next(iter(giant_scc))
    reach_out = set(g.subcomponent(seed, mode="out")); reach_in = set(g.subcomponent(seed, mode="in"))
    n = g.vcount()
    core = np.array(g.coreness(mode="all"))
    types = np.array(g.vs["type"])
    row = dict(token=token, month=month, nodes=n, edges=g.ecount(), volume_usd=float(np.sum(g.es["w"])),
               share_sc_nodes=float(np.mean(types == "SC")),
               lwcc_share=max(len(c) for c in wcc) / n,
               bowtie_scc=len(giant_scc) / n, bowtie_in=len(reach_in - giant_scc) / n,
               bowtie_out=len(reach_out - giant_scc) / n,
               bowtie_other=1 - len(giant_scc | reach_in | reach_out) / n,
               reciprocity=g.reciprocity(), assortativity_deg=g.assortativity_degree(directed=True),
               max_kcore=int(core.max()), share_nodes_kcore_ge5=float(np.mean(core >= 5)),
               mean_in_degree=float(indeg.mean()), median_in_degree=float(np.median(indeg)),
               max_in_degree=int(indeg.max()), max_out_degree=int(outdeg.max()),
               gini_in_strength=gini(s_in[s_in > 0]), nakamoto_in_strength=nakamoto(s_in[s_in > 0]),
               value_share_EOA_EOA=float(df.loc[(df.from_type == "EOA") & (df.to_type == "EOA"), "w"].sum() / df.w.sum()),
               value_share_SC_SC=float(df.loc[(df.from_type == "SC") & (df.to_type == "SC"), "w"].sum() / df.w.sum()))
    # the clustering coefficient is very slow when hub degrees are huge; computed only for mid-sized graphs
    if g.ecount() <= 2_000_000:
        row["transitivity_global"] = g.transitivity_undirected()
    row.update(tail_fit(indeg, "in_degree")); row.update(tail_fit(outdeg, "out_degree"))
    row.update(tail_fit(np.round(s_in), "in_strength"))
    # degree histograms (for CCDFs)
    for name, arr in [("in", indeg), ("out", outdeg)]:
        vals, cnts = np.unique(arr, return_counts=True)
        pd.DataFrame({"degree": vals, "count": cnts}).to_csv(out_hist_dir / f"{token}_{month}_{name}deg.csv", index=False)
    row["seconds"] = round(time.time() - t0, 1)
    return row


def preferential_attachment(df_t, df_t1, mode="in"):
    """degree k in month t predicts the attachment probability of new edges in month t+1, Π(k)∝k^β; returns β (slope of the cumulative function minus 1)"""
    from scipy import stats
    col = "to_address" if mode == "in" else "from_address"
    other = "from_address" if mode == "in" else "to_address"
    deg_t = df_t.groupby(col)[other].nunique()
    edges_t = pd.MultiIndex.from_arrays([df_t.from_address, df_t.to_address])
    edges_t1 = pd.MultiIndex.from_arrays([df_t1.from_address, df_t1.to_address])
    new = df_t1[~edges_t1.isin(edges_t)]
    targets = new[col][new[col].isin(deg_t.index)]
    if targets.empty:
        return {"beta": np.nan}
    k_hits = deg_t.reindex(targets).to_numpy(); k_all = deg_t.to_numpy()
    ks = np.unique(k_all)
    hits = pd.Series(k_hits).value_counts().reindex(ks, fill_value=0).to_numpy()
    cnt = pd.Series(k_all).value_counts().reindex(ks, fill_value=0).to_numpy()
    kappa = np.cumsum(hits / cnt)
    mask = (kappa > 0) & (ks >= 1) & (cnt >= 5)
    slope, intercept, r, p, se = stats.linregress(np.log(ks[mask]), np.log(kappa[mask]))
    return {"beta": slope - 1, "beta_se": se, "r2": r ** 2, "n_new_edges": int(len(targets)), "n_old_nodes": int(len(deg_t))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--tokens", nargs="+", default=["USDC", "USDT", "DAI"])
    ap.add_argument("--months", nargs="*", default=QUARTER_MONTHS)
    ap.add_argument("--skip-pa", action="store_true")
    args = ap.parse_args()
    from google.cloud import bigquery
    client = bigquery.Client(project=args.project)
    out = Path("out"); (out / "degree_hist").mkdir(parents=True, exist_ok=True); (out / "cache").mkdir(exist_ok=True)
    rows = []
    for token in args.tokens:
        for month in args.months:
            print(f"== {token} {month}")
            df = fetch_edges(client, args.project, token, month, out / "cache")
            g = build_graph(df)
            rows.append(metrics(g, df, token, month, out / "degree_hist"))
            pd.DataFrame(rows).to_csv(out / "topology_metrics.csv", index=False)   # write after every step
            print("   ", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items() if k in ("nodes", "edges", "reciprocity", "assortativity_deg", "lwcc_share", "max_kcore", "in_degree_alpha", "seconds")})
    if not args.skip_pa:
        pa_rows = []
        for token in args.tokens:
            for m0, m1 in PA_PAIRS:
                d0 = fetch_edges(client, args.project, token, m0, out / "cache")
                d1 = fetch_edges(client, args.project, token, m1, out / "cache")
                for mode in ("in", "out"):
                    r = preferential_attachment(d0, d1, mode); r.update(token=token, month_t=m0, month_t1=m1, mode=mode); pa_rows.append(r)
                pd.DataFrame(pa_rows).to_csv(out / "pa_results.csv", index=False)
                print(f"   PA {token} {m0}->{m1}:", {k: round(v, 3) for k, v in pa_rows[-2].items() if isinstance(v, float)})
    print("done ->", out.resolve())


if __name__ == "__main__":
    main()

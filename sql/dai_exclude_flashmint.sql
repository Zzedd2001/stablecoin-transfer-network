-- =====================================================================
--  DAI supplementary definition G_net_xf: on top of netting, remove all transfers to and from Sky: MCD Flash (the DAI flash-mint module,
--  0x60744434d6339a6b27d73d9eda62b6f66a0a04fa).
--  Reason: the lending leg of a flash mint comes from the zero address (already excluded), so only the repayment leg into this contract remains and intra-transaction netting cannot cancel it.
--  After running: Save results → CSV, name it concentration_dai_net_xf.csv (about 81 rows)
--  Scan: only the DAI partitions of transfers_netted, < 10 GB
-- =====================================================================
WITH base AS (
  SELECT 'G_net_xf' AS scheme, token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         from_address, to_address, usd_value_net AS usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'DAI'
    AND block_timestamp >= TIMESTAMP('2020-01-01')
    AND NOT is_flashloan_like AND usd_value_net >= 1
    AND from_address <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
    AND to_address   <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
),
node AS (
  SELECT scheme, token, month, to_address AS address, SUM(usd) AS x
  FROM base GROUP BY 1, 2, 3, 4
),
r AS (
  SELECT scheme, token, month, x,
    ROW_NUMBER() OVER (PARTITION BY scheme, token, month ORDER BY x)      AS i_asc,
    ROW_NUMBER() OVER (PARTITION BY scheme, token, month ORDER BY x DESC) AS i_desc,
    COUNT(*)     OVER (PARTITION BY scheme, token, month)                  AS n,
    SUM(x)       OVER (PARTITION BY scheme, token, month)                  AS total,
    SUM(x)       OVER (PARTITION BY scheme, token, month ORDER BY x DESC
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)   AS cum_desc
  FROM node
),
agg AS (
  SELECT scheme, token, month,
    ANY_VALUE(n) AS n_receivers, ANY_VALUE(total) AS inflow_usd,
    2 * SUM(i_asc * x) / (ANY_VALUE(n) * ANY_VALUE(total)) - (ANY_VALUE(n) + 1) / ANY_VALUE(n) AS gini_inflow,
    SUM(IF(i_desc <= GREATEST(1, CAST(FLOOR(n * 0.001) AS INT64)), x, 0)) / ANY_VALUE(total) AS top_0_1pct_share,
    SUM(IF(i_desc <= GREATEST(1, CAST(FLOOR(n * 0.01)  AS INT64)), x, 0)) / ANY_VALUE(total) AS top_1pct_share,
    MIN(IF(cum_desc >= 0.5 * total, i_desc, NULL)) AS nakamoto_50
  FROM r GROUP BY 1, 2, 3
  HAVING ANY_VALUE(total) > 0
),
vol AS (
  SELECT scheme, token, month, COUNT(*) AS n_transfers, SUM(usd) AS volume_usd,
         COUNT(DISTINCT from_address) AS n_senders
  FROM base GROUP BY 1, 2, 3
)
SELECT a.*, v.n_transfers, v.volume_usd, v.n_senders
FROM agg a JOIN vol v USING (scheme, token, month)
ORDER BY month;

-- Also: the module's monthly share of DAI net inflow (repayment flows absorbed), used to document the difference between definitions
-- SELECT DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
--        SUM(IF(to_address = '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa', usd_value_net, 0)) / SUM(usd_value_net) AS flashmint_share
-- FROM `YOUR_PROJECT.stable.transfers_netted`
-- WHERE token = 'DAI' AND NOT is_flashloan_like AND usd_value_net >= 1 AND block_timestamp >= TIMESTAMP('2020-01-01')
-- GROUP BY 1 ORDER BY 1;

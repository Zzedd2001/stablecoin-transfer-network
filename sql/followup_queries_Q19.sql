-- =====================================================================
--  Q19: fixed-count concentration at the size of the 2026 top 1% (added after the fourth verification round)
--    Question it answers: the top 1% of USDC recipients is about 2,100 addresses in 2020 and about 12,500 in 2026, so the
--    rise of the top-1% share compares sets of different size. Q19 gives the monthly net-inflow share of the N largest
--    recipients for fixed N = 250, 750, 2,500, 5,000, 10,000, 12,500, 20,000 and 25,000, which brackets the 2026 top-1%
--    size of every token (DAI about 250, USDC about 12,500, USDT about 20,600 addresses) and the 2020 sizes (DAI about 740,
--    USDC about 2,100, USDT about 12,100). Same definition as Q18: G_net (flash-loan-like pairs removed, net flows of at
--    least 1 USD), DAI additionally without the MCD Flash module (G_net_xf). 243 rows = 3 tokens x 81 months.
--  How to run: BigQuery console -> paste -> replace YOUR_PROJECT -> Run -> Save results -> CSV (local file)
--              -> name it q19_fixed_count_share_month.csv. Scans the transfers_netted table once (about the cost of Q18, < 0.5 USD).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Q19 [export -> q19_fixed_count_share_month.csv]
-- ---------------------------------------------------------------------
WITH inflow AS (
  SELECT token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month, to_address, SUM(usd_value_net) AS usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01') AND NOT is_flashloan_like AND usd_value_net >= 1
    AND NOT (token = 'DAI' AND (to_address = '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
                                OR from_address = '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'))
  GROUP BY 1, 2, 3
),
ranked AS (
  SELECT token, month, usd,
         ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY usd DESC) AS rk,
         SUM(usd)  OVER (PARTITION BY token, month) AS total_usd,
         COUNT(*)  OVER (PARTITION BY token, month) AS n_receivers
  FROM inflow
)
SELECT token, month,
       MAX(n_receivers)                                   AS n_receivers,
       MAX(total_usd)                                     AS total_inflow_usd,
       CAST(FLOOR(0.01 * MAX(n_receivers)) AS INT64)      AS n_top1pct,          -- size of the month's top 1% (same rule as the paper)
       SUM(IF(rk <= 250,   usd, 0)) / MAX(total_usd)      AS top250_share,
       SUM(IF(rk <= 750,   usd, 0)) / MAX(total_usd)      AS top750_share,
       SUM(IF(rk <= 2500,  usd, 0)) / MAX(total_usd)      AS top2500_share,
       SUM(IF(rk <= 5000,  usd, 0)) / MAX(total_usd)      AS top5000_share,
       SUM(IF(rk <= 10000, usd, 0)) / MAX(total_usd)      AS top10000_share,
       SUM(IF(rk <= 12500, usd, 0)) / MAX(total_usd)      AS top12500_share,
       SUM(IF(rk <= 20000, usd, 0)) / MAX(total_usd)      AS top20000_share,
       SUM(IF(rk <= 25000, usd, 0)) / MAX(total_usd)      AS top25000_share
FROM ranked
GROUP BY 1, 2
ORDER BY 1, 2;

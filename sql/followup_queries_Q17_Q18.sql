-- =====================================================================
--  Q17-Q18: two optional queries added after the sixth internal audit (replace YOUR_PROJECT with your project id)
--    Q17 -> DAI flash-loan-like round trips 2021-2024, decomposed by participating address (S4 Table; Results 2.1)
--    Q18 -> fixed-count concentration: monthly net-inflow shares of the 10 / 100 / 1,000 largest recipients
--           (G_net; DAI under G_net_xf) as a robustness check for the percentile shares (S5 Table; Results 3.1)
--  Run each statement separately and export the result to CSV; together they scan < 0.5 USD of data.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q17 [export -> q17_dai_roundtrip_by_address_by_year.csv]
--      DAI flash-loan-like round trips, 2021-2024 by year, by participating address (top 15 per year; gross value credited to both endpoints)
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT EXTRACT(YEAR FROM block_timestamp) AS year, transaction_hash, from_address, to_address, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'DAI' AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2021-01-01')
    AND block_timestamp <  TIMESTAMP('2025-01-01')
),
tot AS (SELECT year, SUM(gross_usd) AS total_usd FROM fl GROUP BY 1),
ends AS (
  SELECT year, from_address AS address, gross_usd FROM fl
  UNION ALL
  SELECT year, to_address   AS address, gross_usd FROM fl
),
by_addr AS (
  SELECT year, address, SUM(gross_usd) AS usd, COUNT(*) AS n_pairs FROM ends GROUP BY 1, 2
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY year ORDER BY usd DESC) AS rk FROM by_addr
)
SELECT r.year, r.rk, r.address,
       (c.address IS NOT NULL) AS is_contract,
       l.entity, l.category,
       r.usd, r.n_pairs, r.usd / t.total_usd AS share_of_roundtrip_gross, t.total_usd
FROM ranked r
JOIN tot t USING (year)
LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = r.address
LEFT JOIN `YOUR_PROJECT.stable.labels`    l ON LOWER(l.address) = r.address
WHERE r.rk <= 15
ORDER BY r.year, r.rk;


-- ---------------------------------------------------------------------
-- Q18 [export -> q18_topN_inflow_share_month.csv]
--      Monthly net-inflow shares of the 10, 100 and 1,000 largest receiving addresses (G_net, flash-loan-like pairs removed;
--      DAI additionally without the MCD Flash module, i.e. G_net_xf); 243 rows = 3 tokens x 81 months
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
         SUM(usd) OVER (PARTITION BY token, month) AS total_usd,
         COUNT(*) OVER (PARTITION BY token, month) AS n_receivers
  FROM inflow
)
SELECT token, month, MAX(n_receivers) AS n_receivers, MAX(total_usd) AS total_inflow_usd,
       SUM(IF(rk <= 10,   usd, 0)) / MAX(total_usd) AS top10_share,
       SUM(IF(rk <= 100,  usd, 0)) / MAX(total_usd) AS top100_share,
       SUM(IF(rk <= 1000, usd, 0)) / MAX(total_usd) AS top1000_share
FROM ranked
GROUP BY 1, 2
ORDER BY 1, 2;

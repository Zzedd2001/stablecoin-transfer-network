-- =====================================================================
--  Supplementary queries Q14–Q16 (replace YOUR_PROJECT with your project ID)
--  Purpose:
--    Q14 → who produced the 2022 USDC round trips (decomposition by participating address / entry contract / month)
--    Q15 → how many contracts dominate flash-loan-like round trips of USDC/USDT, Jan 2025 – Sep 2026
--    Q16 → gas actually used by transactions that call the token contracts directly
--  Run each query separately and export the result as CSV with the file name given in its header.
--  Cost: all queries scan only our own tables (transfers_netted / tx_meta / contracts / labels); about 1 USD in total.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q14a [export → q14a_usdc2022_roundtrip_by_address.csv]
--      USDC flash-loan-like round trips in 2022: decomposition by participating address (top 40).
--      Each pair's gross value is credited to both endpoint addresses, so `share` is the share of
--      round-trip gross value in which the address is one endpoint; shares sum to more than 100%
--      (lender and borrower are both counted), which is intended.
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT transaction_hash, from_address, to_address, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'USDC' AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2022-01-01')
    AND block_timestamp <  TIMESTAMP('2023-01-01')
),
tot AS (SELECT SUM(gross_usd) AS total_usd, COUNT(*) AS n_pairs FROM fl),
ends AS (
  SELECT from_address AS address, gross_usd, transaction_hash FROM fl
  UNION ALL
  SELECT to_address   AS address, gross_usd, transaction_hash FROM fl
),
by_addr AS (
  SELECT address, SUM(gross_usd) AS usd, COUNT(*) AS n_pairs,
         COUNT(DISTINCT transaction_hash) AS n_tx
  FROM ends GROUP BY 1
)
SELECT b.address,
       (c.address IS NOT NULL)           AS is_contract,
       l.entity, l.category,                       -- existing label (NULL if none)
       b.usd, b.n_pairs, b.n_tx,
       b.usd / t.total_usd               AS share_of_roundtrip_gross,
       t.total_usd                       AS total_roundtrip_usd_2022
FROM by_addr b CROSS JOIN tot t
LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = b.address
LEFT JOIN `YOUR_PROJECT.stable.labels`    l ON LOWER(l.address) = b.address
ORDER BY b.usd DESC
LIMIT 40;


-- ---------------------------------------------------------------------
-- Q14b [export → q14b_usdc2022_roundtrip_by_entry.csv]
--      The same round trips by entry contract (the contract called directly by the signing EOA, tx_to), top 30.
--      Shows what kind of program executed the round trips: private MEV contracts, DEX routers, lending protocols,
--      liquidators, automation networks ... n_signers = number of distinct signing EOAs (1–2 indicates a single operator).
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT transaction_hash, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'USDC' AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2022-01-01')
    AND block_timestamp <  TIMESTAMP('2023-01-01')
),
tot AS (SELECT SUM(gross_usd) AS total_usd FROM fl),
j AS (
  SELECT fl.transaction_hash, fl.gross_usd, m.tx_to, m.tx_from
  FROM fl LEFT JOIN `YOUR_PROJECT.stable.tx_meta` m USING (transaction_hash)
)
SELECT j.tx_to                          AS entry_contract,
       (c.address IS NOT NULL)          AS is_contract,
       l.entity, l.category,
       SUM(j.gross_usd)                 AS usd,
       COUNT(DISTINCT j.transaction_hash) AS n_tx,
       COUNT(DISTINCT j.tx_from)        AS n_signers,
       SUM(j.gross_usd) / MAX(t.total_usd) AS share_of_roundtrip_gross
FROM j CROSS JOIN tot t
LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = j.tx_to
LEFT JOIN `YOUR_PROJECT.stable.labels`    l ON LOWER(l.address) = j.tx_to
GROUP BY 1, 2, 3, 4
ORDER BY usd DESC
LIMIT 30;


-- ---------------------------------------------------------------------
-- Q14c [export → q14c_usdc_roundtrip_month_top5.csv]
--      USDC by month, 2021-01 to 2023-12: round-trip gross value and the part involving the five most active
--      participating addresses of 2022 (shows whether the June–September 2022 peak came from the same contracts,
--      and when they appeared and disappeared).
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         block_timestamp, from_address, to_address, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'USDC' AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2021-01-01')
    AND block_timestamp <  TIMESTAMP('2024-01-01')
),
ends22 AS (
  SELECT from_address AS address, gross_usd FROM fl WHERE EXTRACT(YEAR FROM block_timestamp) = 2022
  UNION ALL
  SELECT to_address   AS address, gross_usd FROM fl WHERE EXTRACT(YEAR FROM block_timestamp) = 2022
),
top5 AS (
  SELECT address, ROW_NUMBER() OVER (ORDER BY SUM(gross_usd) DESC) AS rk
  FROM ends22 GROUP BY 1
  QUALIFY rk <= 5
),
gross_month AS (
  SELECT token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month, SUM(gross_usd) AS gross_all_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token = 'USDC'
    AND block_timestamp >= TIMESTAMP('2021-01-01')
    AND block_timestamp <  TIMESTAMP('2024-01-01')
  GROUP BY 1, 2
)
SELECT fl.month,
       g.gross_all_usd,
       SUM(fl.gross_usd)                                                   AS roundtrip_usd,
       SUM(IF(a.address IS NOT NULL OR b.address IS NOT NULL, fl.gross_usd, 0)) AS roundtrip_usd_top5,
       SAFE_DIVIDE(SUM(fl.gross_usd), g.gross_all_usd)                     AS roundtrip_share,
       SAFE_DIVIDE(SUM(IF(a.address IS NOT NULL OR b.address IS NOT NULL, fl.gross_usd, 0)),
                   SUM(fl.gross_usd))                                      AS top5_share_of_roundtrip
FROM fl
LEFT JOIN top5 a ON a.address = fl.from_address
LEFT JOIN top5 b ON b.address = fl.to_address
JOIN gross_month g ON g.month = fl.month
GROUP BY 1, 2
ORDER BY 1;


-- ---------------------------------------------------------------------
-- Q15a [export → q15a_roundtrip_2025_2026_by_address.csv]
--      USDC and USDT, 2025-01 to 2026-09: flash-loan-like round trips by participating address (top 20 per token).
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT token, transaction_hash, from_address, to_address, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token IN ('USDC', 'USDT') AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2025-01-01')
    AND block_timestamp <  TIMESTAMP('2026-10-01')
),
tot AS (SELECT token, SUM(gross_usd) AS total_usd FROM fl GROUP BY 1),
ends AS (
  SELECT token, from_address AS address, gross_usd, transaction_hash FROM fl
  UNION ALL
  SELECT token, to_address   AS address, gross_usd, transaction_hash FROM fl
),
by_addr AS (
  SELECT token, address, SUM(gross_usd) AS usd, COUNT(*) AS n_pairs,
         COUNT(DISTINCT transaction_hash) AS n_tx
  FROM ends GROUP BY 1, 2
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY token ORDER BY usd DESC) AS rk FROM by_addr
)
SELECT r.token, r.rk, r.address,
       (c.address IS NOT NULL) AS is_contract,
       l.entity, l.category,
       r.usd, r.n_pairs, r.n_tx,
       r.usd / t.total_usd     AS share_of_roundtrip_gross
FROM ranked r
JOIN tot t USING (token)
LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = r.address
LEFT JOIN `YOUR_PROJECT.stable.labels`    l ON LOWER(l.address) = r.address
WHERE r.rk <= 20
ORDER BY r.token, r.rk;


-- ---------------------------------------------------------------------
-- Q15b [export → q15b_roundtrip_2025_2026_coverage.csv]
--      Same period: share of round-trip gross value "covered" by the 1 / 5 / 10 / 20 most active addresses
--      (a pair is covered when at least one endpoint is among the top N). Also split by year (2025, 2026).
-- ---------------------------------------------------------------------
WITH fl AS (
  SELECT token, EXTRACT(YEAR FROM block_timestamp) AS year, from_address, to_address, gross_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE token IN ('USDC', 'USDT') AND is_flashloan_like
    AND block_timestamp >= TIMESTAMP('2025-01-01')
    AND block_timestamp <  TIMESTAMP('2026-10-01')
),
ends AS (
  SELECT token, from_address AS address, gross_usd FROM fl
  UNION ALL
  SELECT token, to_address   AS address, gross_usd FROM fl
),
ranked AS (
  SELECT token, address, ROW_NUMBER() OVER (PARTITION BY token ORDER BY SUM(gross_usd) DESC) AS rk
  FROM ends GROUP BY 1, 2
  QUALIFY rk <= 20
),
cov AS (
  SELECT fl.token, fl.year, fl.gross_usd,
         LEAST(COALESCE(a.rk, 999), COALESCE(b.rk, 999)) AS best_rk
  FROM fl
  LEFT JOIN ranked a ON a.token = fl.token AND a.address = fl.from_address
  LEFT JOIN ranked b ON b.token = fl.token AND b.address = fl.to_address
)
SELECT token, year,
       SUM(gross_usd)                                   AS roundtrip_usd,
       SUM(IF(best_rk <= 1,  gross_usd, 0)) / SUM(gross_usd) AS covered_by_top1,
       SUM(IF(best_rk <= 5,  gross_usd, 0)) / SUM(gross_usd) AS covered_by_top5,
       SUM(IF(best_rk <= 10, gross_usd, 0)) / SUM(gross_usd) AS covered_by_top10,
       SUM(IF(best_rk <= 20, gross_usd, 0)) / SUM(gross_usd) AS covered_by_top20
FROM cov
GROUP BY 1, 2
UNION ALL
SELECT token, 0 AS year,                               -- year = 0: whole period 2025-01 to 2026-09
       SUM(gross_usd),
       SUM(IF(best_rk <= 1,  gross_usd, 0)) / SUM(gross_usd),
       SUM(IF(best_rk <= 5,  gross_usd, 0)) / SUM(gross_usd),
       SUM(IF(best_rk <= 10, gross_usd, 0)) / SUM(gross_usd),
       SUM(IF(best_rk <= 20, gross_usd, 0)) / SUM(gross_usd)
FROM cov
GROUP BY 1
ORDER BY token, year;


-- ---------------------------------------------------------------------
-- Q16 [export → q16_direct_call_gas.csv]
--      Transactions that call a token contract directly (tx_to = token contract): gas-used percentiles by token and year,
--      and the share with gas < 120,000 (i.e. how much of the direct calls the is_simple rule covers).
--      Note: tx_meta contains only transactions after 2017-11 with at least one transfer of the three tokens.
-- ---------------------------------------------------------------------
SELECT
  CASE tx_to
    WHEN '0xdac17f958d2ee523a2206206994597c13d831ec7' THEN 'USDT'
    WHEN '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48' THEN 'USDC'
    WHEN '0x6b175474e89094c44da98b954eedeac495271d0f' THEN 'DAI'
  END AS token,
  EXTRACT(YEAR FROM block_timestamp) AS year,
  COUNT(*)                                        AS n_tx,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(5)]      AS gas_p05,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(25)]     AS gas_p25,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(50)]     AS gas_p50,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(75)]     AS gas_p75,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(95)]     AS gas_p95,
  APPROX_QUANTILES(gas_used, 100)[OFFSET(99)]     AS gas_p99,
  COUNTIF(gas_used < 120000) / COUNT(*)           AS share_below_120k
FROM `YOUR_PROJECT.stable.tx_meta`
WHERE to_token_contract
  AND block_timestamp >= TIMESTAMP('2020-01-01')
  AND block_timestamp <  TIMESTAMP('2026-10-01')
GROUP BY 1, 2
ORDER BY 1, 2;

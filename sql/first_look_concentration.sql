-- =====================================================================
--  First look: monthly inflow concentration of USDT / USDC / DAI, 2020-01 to 2026-09
--  One query, one scan (about 1–1.5 TB; check the 'This query will process X GB' estimate before running)
--  Output about 243 rows: token, month, number of receiving addresses, monthly inflow (USD), Gini, top-0.1%/1% shares,
--  Nakamoto coefficient (smallest number of addresses reaching 50% of inflow), transfer count, monthly volume, number of senders
--  After running: Save results → CSV (local file), name it concentration_month.csv
-- =====================================================================
-- The date range is set in the WHERE clause below (second block_timestamp condition):
--   full version from 2020-01-01; on a tight budget use 2024-01-01 (about one third of the scan)
WITH t AS (
  SELECT
    CASE LOWER(token_address)
      WHEN '0xdac17f958d2ee523a2206206994597c13d831ec7' THEN 'USDT'
      WHEN '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48' THEN 'USDC'
      WHEN '0x6b175474e89094c44da98b954eedeac495271d0f' THEN 'DAI'
    END AS token,
    DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
    LOWER(from_address) AS from_address,
    LOWER(to_address)   AS to_address,
    CAST(value AS BIGNUMERIC) /
      IF(LOWER(token_address) = '0x6b175474e89094c44da98b954eedeac495271d0f', 1e18, 1e6) AS usd
  FROM `bigquery-public-data.crypto_ethereum.token_transfers`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01')   -- ← on a tight budget: '2024-01-01'
    AND block_timestamp <  TIMESTAMP('2026-10-01')
    AND LOWER(token_address) IN (
      '0xdac17f958d2ee523a2206206994597c13d831ec7',
      '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
      '0x6b175474e89094c44da98b954eedeac495271d0f')
),
e AS (   -- address-to-address network: mints/burns, self-transfers and dust removed
  SELECT * FROM t
  WHERE from_address <> '0x0000000000000000000000000000000000000000'
    AND to_address   <> '0x0000000000000000000000000000000000000000'
    AND from_address <> to_address
    AND usd >= 1
),
node AS (   -- monthly in-strength of each receiving address
  SELECT token, month, to_address AS address, SUM(usd) AS x
  FROM e GROUP BY 1, 2, 3
),
r AS (
  SELECT token, month, x,
    ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY x)      AS i_asc,
    ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY x DESC) AS i_desc,
    COUNT(*)     OVER (PARTITION BY token, month)                  AS n,
    SUM(x)       OVER (PARTITION BY token, month)                  AS total,
    SUM(x)       OVER (PARTITION BY token, month ORDER BY x DESC
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_desc
  FROM node
),
agg AS (
  SELECT token, month,
    ANY_VALUE(n)     AS n_receivers,
    ANY_VALUE(total) AS inflow_usd,
    -- Gini = 2*Σ(i*x_i)/(n*Σx) - (n+1)/n
    2 * SUM(i_asc * x) / (ANY_VALUE(n) * ANY_VALUE(total)) - (ANY_VALUE(n) + 1) / ANY_VALUE(n) AS gini_inflow,
    SUM(IF(i_desc <= GREATEST(1, CAST(FLOOR(n * 0.001) AS INT64)), x, 0)) / ANY_VALUE(total) AS top_0_1pct_share,
    SUM(IF(i_desc <= GREATEST(1, CAST(FLOOR(n * 0.01)  AS INT64)), x, 0)) / ANY_VALUE(total) AS top_1pct_share,
    MIN(IF(cum_desc >= 0.5 * total, i_desc, NULL)) AS nakamoto_50
  FROM r
  GROUP BY 1, 2
),
vol AS (
  SELECT token, month,
         COUNT(*)                     AS n_transfers,
         SUM(usd)                     AS volume_usd,
         COUNT(DISTINCT from_address) AS n_senders
  FROM e GROUP BY 1, 2
)
SELECT a.token, a.month, a.n_receivers, a.inflow_usd, a.gini_inflow,
       a.top_0_1pct_share, a.top_1pct_share, a.nakamoto_50,
       v.n_transfers, v.volume_usd, v.n_senders
FROM agg a JOIN vol v USING (token, month)
ORDER BY a.token, a.month;

-- ---------------------------------------------------------------------
-- Reduced version when the budget is short: change '2020-01-01' above to '2024-01-01' (scan falls to about one third).
-- Keeping a single token does not reduce the scan (columnar storage) but returns fewer rows and runs faster.
-- Sandbox mode (no billing account) gives 1 TB free per month; beyond that, attach the trial credit (300 USD) under Billing.
-- ---------------------------------------------------------------------

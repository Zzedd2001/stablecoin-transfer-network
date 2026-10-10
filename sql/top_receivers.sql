-- =====================================================================
--  Hub identification: the 20 largest recipients per month (three tokens), used to explain the months with a Nakamoto coefficient of 2
--  Version A (fits the remaining free quota of the month, about 250 GB): 2025-01 to 2026-09 only
--  Version B (after billing is enabled or the quota resets): change the date to 2020-01-01, about 580 GB
--  After running: Save results → CSV, file name top_receivers.csv; look up address labels on Etherscan
-- =====================================================================
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
  WHERE block_timestamp >= TIMESTAMP('2025-01-01')   -- ← version B: '2020-01-01'
    AND block_timestamp <  TIMESTAMP('2026-10-01')
    AND LOWER(token_address) IN (
      '0xdac17f958d2ee523a2206206994597c13d831ec7',
      '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
      '0x6b175474e89094c44da98b954eedeac495271d0f')
),
e AS (
  SELECT * FROM t
  WHERE from_address <> '0x0000000000000000000000000000000000000000'
    AND to_address   <> '0x0000000000000000000000000000000000000000'
    AND from_address <> to_address
    AND usd >= 1
),
src AS (   -- monthly flow of each directed edge (sender → recipient)
  SELECT token, month, to_address, from_address, SUM(usd) AS src_usd, COUNT(*) AS n
  FROM e GROUP BY 1, 2, 3, 4
),
node AS (  -- monthly aggregate per receiving address
  SELECT token, month, to_address AS address,
         SUM(src_usd)             AS inflow_usd,
         SUM(n)                   AS n_in,
         COUNT(*)                 AS in_degree,
         MAX(src_usd) / SUM(src_usd) AS top_source_share   -- close to 1 = two-party back-and-forth / loop flow
  FROM src GROUP BY 1, 2, 3
),
ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY inflow_usd DESC) AS rk,
         inflow_usd / SUM(inflow_usd) OVER (PARTITION BY token, month)        AS share_of_month
  FROM node
)
SELECT r.token, r.month, r.rk, r.address,
       (c.address IS NOT NULL) AS is_contract,
       r.inflow_usd, r.share_of_month, r.n_in, r.in_degree, r.top_source_share
FROM ranked r
LEFT JOIN (SELECT DISTINCT LOWER(address) AS address
           FROM `bigquery-public-data.crypto_ethereum.contracts`) c
       ON c.address = r.address
WHERE r.rk <= 20
ORDER BY r.token, r.month, r.rk;

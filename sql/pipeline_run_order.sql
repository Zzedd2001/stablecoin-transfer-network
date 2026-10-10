-- =====================================================================
--  Full pipeline: run block by block in order (select a block, click Run; start the next block only after the previous one succeeded)
--  Preparation: 1) create a dataset named `stable` in BigQuery (location: US multi-region, same as the public dataset)
--               2) replace every YOUR_PROJECT in this file with your project ID (not the project name)
--  Cost estimate (6.25 USD per TB scanned):
--               block 1 about 620 GB ≈ 4 USD; block 3 about 400–600 GB ≈ 3–4 USD; the remaining blocks scan only our own tables, < 1 USD
-- =====================================================================


-- ---------------------------------------------------------------------
-- Block 1 · materialise all transfers of the three tokens (from each token's launch; every later query scans only this table)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.stable.transfers`
PARTITION BY DATE(block_timestamp)
CLUSTER BY token, from_address, to_address AS
SELECT
  CASE LOWER(t.token_address)
    WHEN '0xdac17f958d2ee523a2206206994597c13d831ec7' THEN 'USDT'
    WHEN '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48' THEN 'USDC'
    WHEN '0x6b175474e89094c44da98b954eedeac495271d0f' THEN 'DAI'
  END AS token,
  t.block_timestamp, t.block_number, t.transaction_hash, t.log_index,
  LOWER(t.from_address) AS from_address,
  LOWER(t.to_address)   AS to_address,
  SAFE_CAST(t.value AS BIGNUMERIC) /
    IF(LOWER(t.token_address) = '0x6b175474e89094c44da98b954eedeac495271d0f', 1e18, 1e6) AS usd_value
FROM `bigquery-public-data.crypto_ethereum.token_transfers` t
WHERE LOWER(t.token_address) IN (
        '0xdac17f958d2ee523a2206206994597c13d831ec7',
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
        '0x6b175474e89094c44da98b954eedeac495271d0f')
  AND t.block_timestamp >= TIMESTAMP('2017-11-01')
  AND t.block_timestamp <  TIMESTAMP('2026-10-01');


-- ---------------------------------------------------------------------
-- Block 2 · contract addresses with creation time (for dynamic EOA / SC node typing by month)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.stable.contracts` AS
SELECT LOWER(address) AS address, MIN(block_timestamp) AS created_at
FROM `bigquery-public-data.crypto_ethereum.contracts`
GROUP BY 1;


-- ---------------------------------------------------------------------
-- Block 3 · transaction-level metadata: signer, called contract, gas; 'simple transfer' = the transaction calls the token contract directly and uses < 120k gas
--           (i.e. an EOA calling transfer() directly — payment-like; anything routed through a router/protocol/smart wallet counts as 'complex')
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.stable.tx_meta`
PARTITION BY DATE(block_timestamp) AS
SELECT x.hash AS transaction_hash, x.block_timestamp,
       LOWER(x.from_address) AS tx_from,
       LOWER(x.to_address)   AS tx_to,
       x.receipt_gas_used    AS gas_used,
       LOWER(x.to_address) IN ('0xdac17f958d2ee523a2206206994597c13d831ec7',
                               '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                               '0x6b175474e89094c44da98b954eedeac495271d0f') AS to_token_contract,
       (LOWER(x.to_address) IN ('0xdac17f958d2ee523a2206206994597c13d831ec7',
                                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                                '0x6b175474e89094c44da98b954eedeac495271d0f')
        AND x.receipt_gas_used < 120000) AS is_simple
FROM `bigquery-public-data.crypto_ethereum.transactions` x
WHERE x.block_timestamp >= TIMESTAMP('2017-11-01')
  AND x.block_timestamp <  TIMESTAMP('2026-10-01')
  AND x.hash IN (SELECT DISTINCT transaction_hash FROM `YOUR_PROJECT.stable.transfers`);


-- ---------------------------------------------------------------------
-- Block 4 · intra-transaction netted table + flash-loan/loop flags (handles the Morpho Blue cluster)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.stable.transfers_netted`
PARTITION BY DATE(block_timestamp)
CLUSTER BY token, from_address, to_address AS
WITH signed AS (
  SELECT token, block_timestamp, transaction_hash,
         LEAST(from_address, to_address)    AS a,
         GREATEST(from_address, to_address) AS b,
         IF(from_address < to_address, usd_value, -usd_value) AS signed_usd,
         usd_value AS gross_usd
  FROM `YOUR_PROJECT.stable.transfers`
  WHERE from_address <> to_address
    AND from_address <> '0x0000000000000000000000000000000000000000'
    AND to_address   <> '0x0000000000000000000000000000000000000000'
),
net AS (
  SELECT token, transaction_hash, a, b,
         MIN(block_timestamp) AS block_timestamp,
         SUM(signed_usd) AS net_usd, SUM(gross_usd) AS gross_usd, COUNT(*) AS n_legs,
         COUNTIF(signed_usd > 0) > 0 AND COUNTIF(signed_usd < 0) > 0 AS is_roundtrip
  FROM signed GROUP BY 1, 2, 3, 4
)
SELECT token, block_timestamp, transaction_hash,
       IF(net_usd >= 0, a, b) AS from_address,
       IF(net_usd >= 0, b, a) AS to_address,
       ABS(net_usd) AS usd_value_net, gross_usd, n_legs, is_roundtrip,
       is_roundtrip AND ABS(net_usd) <= 0.001 * gross_usd AS is_flashloan_like
FROM net;


-- ---------------------------------------------------------------------
-- Block 5 · [export → concentration_three_ways.csv] monthly inflow concentration under three network definitions (2020-01 to 2026-09)
--           G_all: all address-to-address transfers; G_net: intra-transaction netting with flash-loan-like pairs removed; G_simple: direct calls to the token contract
-- ---------------------------------------------------------------------
WITH base AS (
  SELECT 'G_all' AS scheme, token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         from_address, to_address, usd_value AS usd
  FROM `YOUR_PROJECT.stable.transfers`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01')
    AND from_address <> '0x0000000000000000000000000000000000000000'
    AND to_address   <> '0x0000000000000000000000000000000000000000'
    AND from_address <> to_address AND usd_value >= 1
  UNION ALL
  SELECT 'G_net', token, DATE_TRUNC(DATE(block_timestamp), MONTH),
         from_address, to_address, usd_value_net
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01')
    AND NOT is_flashloan_like AND usd_value_net >= 1
  UNION ALL
  SELECT 'G_simple', t.token, DATE_TRUNC(DATE(t.block_timestamp), MONTH),
         t.from_address, t.to_address, t.usd_value
  FROM `YOUR_PROJECT.stable.transfers` t
  JOIN `YOUR_PROJECT.stable.tx_meta` m USING (transaction_hash)
  WHERE t.block_timestamp >= TIMESTAMP('2020-01-01') AND m.is_simple
    AND t.from_address <> '0x0000000000000000000000000000000000000000'
    AND t.to_address   <> '0x0000000000000000000000000000000000000000'
    AND t.from_address <> t.to_address AND t.usd_value >= 1
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
ORDER BY scheme, token, month;


-- ---------------------------------------------------------------------
-- Block 6 · [export → flow_composition_month.csv] monthly flow composition: flash-loan-like share, netting reduction, simple-transfer share
-- ---------------------------------------------------------------------
WITH n AS (
  SELECT token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         SUM(gross_usd) AS gross_usd, SUM(usd_value_net) AS net_usd,
         SUM(IF(is_flashloan_like, gross_usd, 0)) AS flashloan_like_usd
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01') GROUP BY 1, 2
),
s AS (
  SELECT t.token, DATE_TRUNC(DATE(t.block_timestamp), MONTH) AS month,
         SUM(IF(m.is_simple, t.usd_value, 0)) AS simple_usd,
         SUM(IF(m.is_simple, 1, 0))           AS simple_n,
         COUNT(*)                             AS all_n
  FROM `YOUR_PROJECT.stable.transfers` t
  LEFT JOIN `YOUR_PROJECT.stable.tx_meta` m USING (transaction_hash)
  WHERE t.block_timestamp >= TIMESTAMP('2020-01-01')
    AND t.from_address <> '0x0000000000000000000000000000000000000000'
    AND t.to_address   <> '0x0000000000000000000000000000000000000000'
  GROUP BY 1, 2
)
SELECT n.token, n.month, n.gross_usd, n.net_usd, n.flashloan_like_usd,
       SAFE_DIVIDE(n.flashloan_like_usd, n.gross_usd) AS flashloan_share,
       1 - SAFE_DIVIDE(n.net_usd, n.gross_usd)        AS netting_reduction,
       s.simple_usd, SAFE_DIVIDE(s.simple_usd, n.gross_usd) AS simple_usd_share,
       s.simple_n, s.all_n, SAFE_DIVIDE(s.simple_n, s.all_n) AS simple_count_share
FROM n JOIN s USING (token, month)
ORDER BY 1, 2;


-- ---------------------------------------------------------------------
-- Block 7 · [export → dyad_month.csv] monthly dyad-type shares (EOA→EOA / EOA→SC / SC→EOA / SC→SC) under G_all and G_net
-- ---------------------------------------------------------------------
WITH e AS (
  SELECT 'G_all' AS scheme, token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         from_address, to_address, usd_value AS usd, block_timestamp
  FROM `YOUR_PROJECT.stable.transfers`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01')
    AND from_address <> '0x0000000000000000000000000000000000000000'
    AND to_address   <> '0x0000000000000000000000000000000000000000'
    AND from_address <> to_address AND usd_value >= 1
  UNION ALL
  SELECT 'G_net', token, DATE_TRUNC(DATE(block_timestamp), MONTH),
         from_address, to_address, usd_value_net, block_timestamp
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01') AND NOT is_flashloan_like AND usd_value_net >= 1
),
typed AS (
  SELECT e.scheme, e.token, e.month, e.usd,
         IF(cf.address IS NOT NULL AND cf.created_at <= e.block_timestamp, 'SC', 'EOA') AS from_type,
         IF(ct.address IS NOT NULL AND ct.created_at <= e.block_timestamp, 'SC', 'EOA') AS to_type
  FROM e
  LEFT JOIN `YOUR_PROJECT.stable.contracts` cf ON cf.address = e.from_address
  LEFT JOIN `YOUR_PROJECT.stable.contracts` ct ON ct.address = e.to_address
)
SELECT scheme, token, month, CONCAT(from_type, '->', to_type) AS dyad,
       SUM(usd) AS usd, COUNT(*) AS n
FROM typed GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;


-- ---------------------------------------------------------------------
-- Block 8 · [export → top_receivers_net.csv] 20 largest recipients per month under G_net (from 2020), used for the label table and hub analysis
-- ---------------------------------------------------------------------
WITH src AS (
  SELECT token, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month, to_address, from_address,
         SUM(usd_value_net) AS src_usd, COUNT(*) AS n
  FROM `YOUR_PROJECT.stable.transfers_netted`
  WHERE block_timestamp >= TIMESTAMP('2020-01-01') AND NOT is_flashloan_like AND usd_value_net >= 1
  GROUP BY 1, 2, 3, 4
),
node AS (
  SELECT token, month, to_address AS address, SUM(src_usd) AS inflow_usd, SUM(n) AS n_in,
         COUNT(*) AS in_degree, MAX(src_usd) / SUM(src_usd) AS top_source_share
  FROM src GROUP BY 1, 2, 3
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY inflow_usd DESC) AS rk,
         inflow_usd / SUM(inflow_usd) OVER (PARTITION BY token, month) AS share_of_month
  FROM node
)
SELECT r.token, r.month, r.rk, r.address, (c.address IS NOT NULL) AS is_contract,
       r.inflow_usd, r.share_of_month, r.n_in, r.in_degree, r.top_source_share
FROM ranked r LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = r.address
WHERE r.rk <= 20
ORDER BY r.token, r.month, r.rk;

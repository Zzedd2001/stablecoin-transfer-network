-- =====================================================================
--  Entity-level queries (prerequisite: stable.labels exists, 96 rows; address is a 42-character lower-case string)
--  Run and export the three queries separately:
--    Q11 → concentration_entity_level.csv (about 486 rows = 2 definitions × 3 tokens × 81 months)
--    Q12 → inflow_by_category_month.csv (about 3,000 rows)
--    Q13 → top_receivers_entity.csv     (4,860 rows = 3 tokens × 81 months × top 20)
--  Each scans only transfers_netted (about 60–100 GB), < 1 USD each
--  Common rules: netted definition (G_net); flash-loan-like round trips removed; Sky MCD Flash (DAI flash-mint module) removed;
--                labelled addresses mapped to entity_group; transfers within the same entity removed
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q11 · entity-level concentration: G_net_entity (entity aggregation + intra-entity transfers removed)
--                                    G_net_entity_xissuer (additionally removes the issuer side: Issuer / DeFi-PSM / flash-mint categories)
-- ---------------------------------------------------------------------
WITH lab AS (
  SELECT LOWER(address) AS address, entity_group, category
  FROM `YOUR_PROJECT.stable.labels`
),
base AS (
  SELECT t.token, DATE_TRUNC(DATE(t.block_timestamp), MONTH) AS month,
         COALESCE(lf.entity_group, t.from_address) AS from_node,
         COALESCE(lt.entity_group, t.to_address)   AS to_node,
         lf.category AS from_cat, lt.category AS to_cat,
         t.usd_value_net AS usd
  FROM `YOUR_PROJECT.stable.transfers_netted` t
  LEFT JOIN lab lf ON lf.address = t.from_address
  LEFT JOIN lab lt ON lt.address = t.to_address
  WHERE t.block_timestamp >= TIMESTAMP('2020-01-01')
    AND NOT t.is_flashloan_like AND t.usd_value_net >= 1
    AND t.from_address <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
    AND t.to_address   <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
),
schemes AS (
  SELECT 'G_net_entity' AS scheme, token, month, from_node, to_node, usd
  FROM base
  WHERE from_node <> to_node
  UNION ALL
  SELECT 'G_net_entity_xissuer', token, month, from_node, to_node, usd
  FROM base
  WHERE from_node <> to_node
    AND COALESCE(from_cat, '') NOT IN ('Issuer', 'DeFi-PSM', 'flash-mint')
    AND COALESCE(to_cat, '')   NOT IN ('Issuer', 'DeFi-PSM', 'flash-mint')
),
node AS (
  SELECT scheme, token, month, to_node AS address, SUM(usd) AS x
  FROM schemes GROUP BY 1, 2, 3, 4
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
         COUNT(DISTINCT from_node) AS n_senders
  FROM schemes GROUP BY 1, 2, 3
)
SELECT a.*, v.n_transfers, v.volume_usd, v.n_senders
FROM agg a JOIN vol v USING (scheme, token, month)
ORDER BY scheme, token, month;


-- ---------------------------------------------------------------------
-- Q12 · monthly net inflow by recipient label category (unlabelled addresses split into contracts and EOAs)
-- ---------------------------------------------------------------------
WITH lab AS (
  SELECT LOWER(address) AS address, entity_group, category
  FROM `YOUR_PROJECT.stable.labels`
),
e AS (
  SELECT t.token, DATE_TRUNC(DATE(t.block_timestamp), MONTH) AS month,
         t.to_address, t.block_timestamp, t.usd_value_net AS usd,
         lt.category AS to_cat,
         COALESCE(lf.entity_group, t.from_address) AS from_node,
         COALESCE(lt.entity_group, t.to_address)   AS to_node
  FROM `YOUR_PROJECT.stable.transfers_netted` t
  LEFT JOIN lab lf ON lf.address = t.from_address
  LEFT JOIN lab lt ON lt.address = t.to_address
  WHERE t.block_timestamp >= TIMESTAMP('2020-01-01')
    AND NOT t.is_flashloan_like AND t.usd_value_net >= 1
    AND t.from_address <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
    AND t.to_address   <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
)
SELECT e.token, e.month,
       COALESCE(e.to_cat,
                IF(c.address IS NOT NULL AND c.created_at <= e.block_timestamp,
                   'unlabelled contract', 'unlabelled EOA')) AS category,
       SUM(e.usd) AS usd, COUNT(*) AS n, COUNT(DISTINCT e.to_address) AS n_receivers
FROM e
LEFT JOIN `YOUR_PROJECT.stable.contracts` c ON c.address = e.to_address
WHERE e.from_node <> e.to_node
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;


-- ---------------------------------------------------------------------
-- Q13 · entity-level monthly top-20 recipients (re-ranked after aggregation), for the regular-player / persistence analysis
-- ---------------------------------------------------------------------
WITH lab AS (
  SELECT LOWER(address) AS address, entity_group, category
  FROM `YOUR_PROJECT.stable.labels`
),
base AS (
  SELECT t.token, DATE_TRUNC(DATE(t.block_timestamp), MONTH) AS month,
         COALESCE(lf.entity_group, t.from_address) AS from_node,
         COALESCE(lt.entity_group, t.to_address)   AS to_node,
         lt.category AS to_cat,
         t.usd_value_net AS usd
  FROM `YOUR_PROJECT.stable.transfers_netted` t
  LEFT JOIN lab lf ON lf.address = t.from_address
  LEFT JOIN lab lt ON lt.address = t.to_address
  WHERE t.block_timestamp >= TIMESTAMP('2020-01-01')
    AND NOT t.is_flashloan_like AND t.usd_value_net >= 1
    AND t.from_address <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
    AND t.to_address   <> '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa'
),
node AS (
  SELECT token, month, to_node AS node, ANY_VALUE(to_cat) AS category,
         SUM(usd) AS inflow_usd, COUNT(*) AS n_in, COUNT(DISTINCT from_node) AS in_degree
  FROM base
  WHERE from_node <> to_node
  GROUP BY 1, 2, 3
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY token, month ORDER BY inflow_usd DESC) AS rk,
         inflow_usd / SUM(inflow_usd) OVER (PARTITION BY token, month) AS share_of_month
  FROM node
)
SELECT token, month, rk, node, category, inflow_usd, share_of_month, n_in, in_degree
FROM ranked
WHERE rk <= 20
ORDER BY token, month, rk;

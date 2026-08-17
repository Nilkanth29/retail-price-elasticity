-- ============================================================================
-- Retail Price Elasticity & Promotion Uplift Warehouse
-- Source: dunnhumby "The Complete Journey" (2,469 households, 1 year, full US grocery retailer)
-- Engine: DuckDB
-- ============================================================================

-- -----------------------------------------------------------------------
-- 1. DIMENSION: PRODUCT
-- -----------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_product AS
SELECT
    product_id,
    manufacturer_id,
    department,
    brand,
    product_category,
    product_type,
    package_size
FROM read_parquet('/home/claude/project/data/products.parquet');

-- -----------------------------------------------------------------------
-- 2. DIMENSION: HOUSEHOLD (demographics available for ~801 of 2,469 hh)
-- -----------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_household AS
SELECT
    household_id,
    age,
    income,
    home_ownership,
    marital_status,
    household_size,
    household_comp,
    kids_count
FROM read_parquet('/home/claude/project/data/demographics.parquet');

-- -----------------------------------------------------------------------
-- 3. DIMENSION: CAMPAIGN
-- -----------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_campaign AS
SELECT campaign_id, campaign_type, start_date, end_date
FROM read_parquet('/home/claude/project/data/campaign_descriptions.parquet');

CREATE OR REPLACE TABLE bridge_household_campaign AS
SELECT campaign_id, household_id
FROM read_parquet('/home/claude/project/data/campaigns.parquet');

-- -----------------------------------------------------------------------
-- 4. FACT: TRANSACTIONS (grain = one row per product per basket line)
-- -----------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_transactions AS
SELECT
    household_id,
    store_id,
    basket_id,
    product_id,
    week,
    CAST(transaction_timestamp AS DATE) AS transaction_date,
    quantity,
    sales_value,
    retail_disc,
    coupon_disc,
    coupon_match_disc,
    -- net unit price actually paid, the core variable for elasticity modelling
    CASE WHEN quantity > 0 THEN sales_value / quantity ELSE NULL END AS unit_price,
    -- total discount stack, used to separate "price effect" from "promo effect"
    (COALESCE(retail_disc,0) + COALESCE(coupon_disc,0) + COALESCE(coupon_match_disc,0)) AS total_discount
FROM read_parquet('/home/claude/project/data/transactions.parquet')
WHERE quantity > 0 AND sales_value >= 0;

-- -----------------------------------------------------------------------
-- 5. FACT: PROMOTIONS (grain = product x store x week; the causal "treatment" table)
--    display_location: '0' = no in-store display, else a display location code
--    mailer_location:  '0' = no mailer/flyer feature, else a mailer placement code
-- -----------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_promotions AS
SELECT
    product_id,
    store_id,
    week,
    display_location,
    mailer_location,
    CASE WHEN display_location <> '0' THEN 1 ELSE 0 END AS is_displayed,
    CASE WHEN mailer_location  <> '0' THEN 1 ELSE 0 END AS is_mailed
FROM read_parquet('/home/claude/project/data/promotions.parquet');

-- -----------------------------------------------------------------------
-- 6. Sanity checks
-- -----------------------------------------------------------------------
SELECT 'fact_transactions' AS tbl, COUNT(*) AS n_rows FROM fact_transactions
UNION ALL SELECT 'fact_promotions', COUNT(*) FROM fact_promotions
UNION ALL SELECT 'dim_product', COUNT(*) FROM dim_product
UNION ALL SELECT 'dim_household', COUNT(*) FROM dim_household
UNION ALL SELECT 'dim_campaign', COUNT(*) FROM dim_campaign;

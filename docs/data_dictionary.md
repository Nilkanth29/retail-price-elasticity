# Data Dictionary

Source: dunnhumby "The Complete Journey" — 2,469 households, one year of
complete grocery purchase history at a single US retailer. Redistributed via
https://github.com/bradleyboehmke/completejourney (originally from 84.51°).

## fact_transactions (1,460,438 rows)
One row per product line within a basket.

| Column | Type | Notes |
|---|---|---|
| household_id | str | shopper identifier |
| store_id | str | store identifier |
| basket_id | str | one shopping trip |
| product_id | str | joins to dim_product |
| week | int | week number, 1-102 |
| transaction_date | date | |
| quantity | float | units purchased |
| sales_value | float | $ actually paid, net of discounts |
| retail_disc | float | retailer discount applied |
| coupon_disc | float | manufacturer coupon discount |
| coupon_match_disc | float | retailer coupon match |
| unit_price | float | **derived**: sales_value / quantity — the core variable for elasticity modelling |
| total_discount | float | **derived**: sum of the three discount columns |

## fact_promotions (20,940,529 rows)
One row per product × store × week **where that product had some promotional
activity at that store that week**. This is not a full cross-join — there is
no row for a product-store-week with zero promotion. Treat any (product,
store, week) combination absent from this table as the untreated baseline.

| Column | Type | Notes |
|---|---|---|
| product_id | str | |
| store_id | str | |
| week | int | |
| display_location | str | '0' = no display; other codes = in-store display location |
| mailer_location | str | '0' = no mailer; other codes = flyer placement (front page, interior, etc.) |
| is_displayed | int | **derived**: 1 if display_location != '0' |
| is_mailed | int | **derived**: 1 if mailer_location != '0' |

**Correct way to compute promo status for a transaction:** LEFT JOIN
fact_transactions to fact_promotions on (product_id, store_id, week); a
non-match means no promotion was active.

## dim_product (92,331 rows)
product_id, manufacturer_id, department, brand, product_category, product_type, package_size

## dim_household (801 rows)
Demographics are only available for 801 of the 2,469 households (opt-in).
household_id, age (banded), income (banded), home_ownership, marital_status, household_size, household_comp, kids_count

## dim_campaign (27 rows) / bridge_household_campaign
Direct marketing campaigns and which households were targeted by each.

## coupons / coupon_redemptions
coupons: which product each coupon_upc applies to, and which campaign issued it.
coupon_redemptions: which household redeemed which coupon, and when.

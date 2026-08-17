# Retail Price Elasticity & Promotion Uplift Analysis

**Status: in progress — data warehouse built, EDA next**

## The business question

A retailer runs promotions (in-store displays, flyer/mailer features) on
thousands of products every week without a rigorous way to tell which ones
actually grow revenue versus which just shift spend that would have
happened anyway. This project estimates **price elasticity of demand** and
the **causal uplift from promotion** for a set of grocery categories, then
turns that into a concrete recommendation: which products should be
promoted, and roughly how much extra revenue that's worth.

This is harder than a typical "sales dashboard" portfolio project because
price and promotion are not randomly assigned — a naive regression of
quantity sold on price will confuse the retailer's own pricing decisions
with actual consumer demand response (price endogeneity). Isolating the
real causal effect is the core technical challenge here.

## Dataset

dunnhumby "The Complete Journey" — 2,469 households, one full year of
complete grocery purchase history at a real US retailer, including which
products were promoted (display/mailer) at which store in which week.
1.47M transactions, 20.9M promotion records, 92K products. See
[`docs/data_dictionary.md`](docs/data_dictionary.md) for the full schema.

## Project structure

```
├── data_raw/              # cloned source repo (gitignored)
├── data/                  # cleaned Parquet tables (gitignored — regenerate via script below)
├── scripts/
│   └── 01_acquire_data.py # pulls and converts the raw dataset
├── sql/
│   └── 01_build_warehouse.sql   # builds the star-schema DuckDB warehouse
├── notebooks/              # EDA and modelling (coming next)
├── dashboard/               # Streamlit app (coming later)
├── docs/
│   └── data_dictionary.md
├── warehouse.duckdb          # the built database (gitignored — regenerate)
└── requirements.txt
```

## Reproducing this

```bash
pip install -r requirements.txt
# also requires R (base R is enough) and git

python scripts/01_acquire_data.py     # ~2-3 min, downloads + converts ~46MB of data
python -c "
import duckdb
con = duckdb.connect('warehouse.duckdb')
con.execute(open('sql/01_build_warehouse.sql').read().replace(chr(45)*2 + chr(45)*0, ''))
"
# (or just run the statements in sql/01_build_warehouse.sql from any DuckDB client)
```

## Roadmap

- [x] **Phase 1 — Data engineering**: star-schema warehouse in DuckDB (fact_transactions, fact_promotions, dim_product, dim_household, dim_campaign)
- [ ] **Phase 2 — EDA**: price/promo distributions over time, seasonality, cross-store variation, category selection
- [ ] **Phase 3 — Price elasticity modelling**: log-log demand model with store/week fixed effects to address price endogeneity
- [ ] **Phase 4 — Promotion uplift**: causal estimate of display/mailer effect, separated from the price effect
- [ ] **Phase 5 — Optimization**: simulate revenue impact of alternative promo/price scenarios; recommend a promo calendar
- [ ] **Phase 6 — Dashboard**: interactive Streamlit app for exploring elasticity/uplift by category
- [ ] **Phase 7 — Write-up**: business memo translating findings into $ impact

## Focus categories (initial)

Selected for meaningful price variation and enough promotion activity to
detect an effect (see `docs/data_dictionary.md` for how promo rate is
correctly computed):

| Category | Transactions | Products | Revenue | Avg price | Price CV | True promo rate |
|---|---|---|---|---|---|---|
| Eggs | 16,011 | 91 | $22.4K | $1.18 | 0.49 | 31.3% |
| Bath Tissues | 8,007 | 121 | $34.9K | $3.99 | 0.75 | 23.8% |

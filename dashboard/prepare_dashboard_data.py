"""
Precomputes every table, model result, and chart input the dashboard needs,
and writes them as small files under dashboard/data/.

Why this exists: warehouse.duckdb is about 150MB, well over GitHub's 100MB
file limit, so it cannot be committed to the repo the dashboard deploys
from. Running this script once locally (where warehouse.duckdb exists)
produces a handful of small parquet and json files that ARE committed,
and the deployed app only ever reads those. This also makes the deployed
app load fast, since it never re-runs a regression on page load.

Usage, run from the project root:
    python dashboard/prepare_dashboard_data.py
"""
import os
import json
import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf

OUT_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUT_DIR, exist_ok=True)

con = duckdb.connect(os.path.join(os.path.dirname(__file__), '..', 'warehouse.duckdb'), read_only=True)

CATEGORIES = ['EGGS', 'BATH TISSUES']


def build_base_panel():
    store_size = con.execute(
        "SELECT store_id, COUNT(*) AS store_total_txns FROM fact_transactions GROUP BY store_id"
    ).fetchdf()

    query = """
    WITH agg AS (
        SELECT t.product_id, t.store_id, t.week, p.product_category,
            SUM(t.quantity) AS quantity, SUM(t.sales_value) AS sales_value,
            SUM(t.retail_disc) AS retail_disc
        FROM fact_transactions t
        JOIN dim_product p ON t.product_id = p.product_id
        WHERE p.product_category IN ('EGGS', 'BATH TISSUES')
        GROUP BY t.product_id, t.store_id, t.week, p.product_category
    )
    SELECT a.*, COALESCE(pr.is_displayed,0) AS is_displayed, COALESCE(pr.is_mailed,0) AS is_mailed
    FROM agg a
    LEFT JOIN fact_promotions pr ON a.product_id=pr.product_id AND a.store_id=pr.store_id AND a.week=pr.week
    """
    df = con.execute(query).fetchdf()
    df['gross_value'] = df['sales_value'] + df['retail_disc'].abs()
    df['unit_price'] = df['gross_value'] / df['quantity']
    df['net_unit_price'] = df['sales_value'] / df['quantity']
    df['discount_pct'] = (df['retail_disc'].abs() / df['gross_value'].replace(0, np.nan)).fillna(0)
    df = df[df.unit_price > 0].copy()
    df['log_qty'] = np.log(df['quantity'])
    df['log_price'] = np.log(df['unit_price'])
    df['log_net_price'] = np.log(df['net_unit_price'].clip(lower=0.01))
    df['is_promo'] = ((df.is_displayed == 1) | (df.is_mailed == 1)).astype(int)
    df = df.merge(store_size, on='store_id', how='left')
    df['log_store_size'] = np.log(df['store_total_txns'])
    df['log_store_size_c'] = df['log_store_size'] - df['log_store_size'].mean()
    return df


print("Building base panel...")
df = build_base_panel()
print(f"  {len(df):,} rows")

# ---------------------------------------------------------------------
# 1. Weekly trends (Phase 2): price, promo rate, volume over time
# ---------------------------------------------------------------------
weekly = df.groupby(['product_category', 'week']).agg(
    avg_price=('net_unit_price', 'mean'),
    total_qty=('quantity', 'sum'),
    n_txn=('quantity', 'count'),
    promo_rate=('is_promo', 'mean')
).reset_index()
weekly.to_parquet(os.path.join(OUT_DIR, 'weekly_trends.parquet'), index=False)
print("Wrote weekly_trends.parquet")

# ---------------------------------------------------------------------
# 2. Price by promo status (Phase 2, for the box plot)
# ---------------------------------------------------------------------
price_by_promo = df[['product_category', 'is_promo', 'net_unit_price']].copy()
price_by_promo.columns = ['product_category', 'is_promo', 'unit_price']
price_by_promo.to_parquet(os.path.join(OUT_DIR, 'price_by_promo.parquet'), index=False)
print("Wrote price_by_promo.parquet")

# ---------------------------------------------------------------------
# 3. Phase 3 models: naive vs fixed effects elasticity, promo uplift
# ---------------------------------------------------------------------
naive_results = {}
fe_results = {}
for cat in CATEGORIES:
    sub = df[df.product_category == cat].copy()
    sub['log_qty_net'] = np.log(sub['quantity'])
    naive = smf.ols('log_qty_net ~ log_net_price + is_displayed + is_mailed', data=sub).fit(
        cov_type='cluster', cov_kwds={'groups': sub['product_id']})
    naive_results[cat] = naive
    fe = smf.ols(
        'log_qty_net ~ log_net_price + is_displayed + is_mailed + C(product_id) + C(store_id) + C(week)',
        data=sub
    ).fit(cov_type='cluster', cov_kwds={'groups': sub['product_id']})
    fe_results[cat] = fe

elasticity_rows = []
for cat in CATEGORIES:
    elasticity_rows.append({
        'category': cat.title(), 'model': 'Naive',
        'elasticity': naive_results[cat].params['log_net_price'],
        'se': naive_results[cat].bse['log_net_price']
    })
    elasticity_rows.append({
        'category': cat.title(), 'model': 'Fixed Effects',
        'elasticity': fe_results[cat].params['log_net_price'],
        'se': fe_results[cat].bse['log_net_price']
    })
pd.DataFrame(elasticity_rows).to_json(os.path.join(OUT_DIR, 'elasticity_comparison.json'), orient='records')
print("Wrote elasticity_comparison.json")

promo_rows = []
for cat in CATEGORIES:
    m = fe_results[cat]
    for var, label in [('is_displayed', 'In-store display'), ('is_mailed', 'Mailer/flyer feature')]:
        pct_effect = (np.exp(m.params[var]) - 1) * 100
        promo_rows.append({
            'category': cat.title(), 'promo_type': label,
            'pct_lift': round(pct_effect, 1), 'p_value': round(m.pvalues[var], 4),
            'significant': bool(m.pvalues[var] < 0.05)
        })
pd.DataFrame(promo_rows).to_json(os.path.join(OUT_DIR, 'promo_uplift.json'), orient='records')
print("Wrote promo_uplift.json")

# ---------------------------------------------------------------------
# 4. Phase 4 / 5 combined model: discount depth and store size interactions
# ---------------------------------------------------------------------
combined_models = {}
for cat in CATEGORIES:
    sub = df[df.product_category == cat].copy()
    m = smf.ols(
        'log_qty ~ log_price + is_displayed*discount_pct + is_mailed*discount_pct'
        ' + is_displayed*log_store_size_c + is_mailed*log_store_size_c'
        ' + C(product_id) + C(store_id) + C(week)',
        data=sub
    ).fit(cov_type='cluster', cov_kwds={'groups': sub['product_id']})
    combined_models[cat] = m

# store size lift curve (for the line chart)
size_range = np.linspace(df['log_store_size_c'].quantile(0.05), df['log_store_size_c'].quantile(0.95), 40)
store_curve_rows = []
for cat in CATEGORIES:
    m = combined_models[cat]
    lift = (np.exp(m.params['is_displayed'] + m.params['is_displayed:log_store_size_c'] * size_range) - 1) * 100
    for x, y in zip(size_range, lift):
        store_curve_rows.append({'category': cat.title(), 'log_store_size_c': x, 'predicted_lift_pct': y})
pd.DataFrame(store_curve_rows).to_parquet(os.path.join(OUT_DIR, 'store_size_curve.parquet'), index=False)
print("Wrote store_size_curve.parquet")

# discount depth mechanism curve
discount_range = np.linspace(0, 0.5, 40)
discount_curve_rows = []
for cat in CATEGORIES:
    m = combined_models[cat]
    display_lift = (np.exp(m.params['is_displayed'] + m.params['is_displayed:discount_pct'] * discount_range) - 1) * 100
    mailer_lift = (np.exp(m.params['is_mailed'] + m.params['is_mailed:discount_pct'] * discount_range) - 1) * 100
    for d, dl, ml in zip(discount_range, display_lift, mailer_lift):
        discount_curve_rows.append({'category': cat.title(), 'discount_pct': d * 100,
                                     'promo_type': 'Display', 'predicted_lift_pct': dl})
        discount_curve_rows.append({'category': cat.title(), 'discount_pct': d * 100,
                                     'promo_type': 'Mailer', 'predicted_lift_pct': ml})
pd.DataFrame(discount_curve_rows).to_parquet(os.path.join(OUT_DIR, 'discount_depth_curve.parquet'), index=False)
print("Wrote discount_depth_curve.parquet")

# ---------------------------------------------------------------------
# 5. Phase 5 optimization: optimal discount table and revenue scenarios
# ---------------------------------------------------------------------
def solve_optimal_discount(model, promo_col):
    b_disc = model.params['discount_pct']
    b_int = model.params[f'{promo_col}:discount_pct']
    k = b_disc + b_int
    d_star = max(0.0, 1 - 1 / k) if k > 1 else 0.0
    return k, d_star


opt_rows = []
for cat in CATEGORIES:
    for promo_col, label in [('is_displayed', 'Display'), ('is_mailed', 'Mailer')]:
        k, d_star = solve_optimal_discount(combined_models[cat], promo_col)
        actual_avg = df[(df.product_category == cat) & (df[promo_col] == 1)]['discount_pct'].mean()
        opt_rows.append({
            'category': cat.title(), 'promo_type': label,
            'combined_slope_k': round(k, 3),
            'model_optimal_discount_pct': round(d_star * 100, 1),
            'current_avg_discount_pct': round(actual_avg * 100, 1)
        })
pd.DataFrame(opt_rows).to_json(os.path.join(OUT_DIR, 'optimal_discount_table.json'), orient='records')
print("Wrote optimal_discount_table.json")


def revenue_scenario(cat, promo_col, new_discount):
    m = combined_models[cat]
    b_disc = m.params['discount_pct']
    b_interact = m.params[f'{promo_col}:discount_pct']
    sub = df[(df.product_category == cat) & (df[promo_col] == 1)].copy()
    actual_revenue = sub['sales_value'].sum()
    delta_discount = new_discount - sub['discount_pct']
    delta_lp = delta_discount * (b_disc + b_interact)
    new_qty = sub['quantity'] * np.exp(delta_lp)
    new_net_price = sub['unit_price'] * (1 - new_discount)
    new_revenue = (new_net_price * new_qty).sum()
    return actual_revenue, new_revenue, new_revenue - actual_revenue


targets = [('EGGS', 'is_mailed', 0.40, 'Mailer to 40% discount'),
           ('EGGS', 'is_displayed', 0.0, 'Display to 0% discount'),
           ('BATH TISSUES', 'is_displayed', 0.0, 'Display to 0% discount'),
           ('BATH TISSUES', 'is_mailed', 0.0, 'Mailer to 0% discount')]
scenario_rows = []
for cat, promo_col, target, label in targets:
    actual_rev, new_rev, delta = revenue_scenario(cat, promo_col, target)
    scenario_rows.append({
        'category': cat.title(), 'change': label,
        'actual_revenue': round(actual_rev), 'scenario_revenue': round(new_rev),
        'delta': round(delta), 'pct_change': round(delta / actual_rev * 100, 1)
    })
scenario_df = pd.DataFrame(scenario_rows)
scenario_df.to_json(os.path.join(OUT_DIR, 'optimization_scenarios.json'), orient='records')
print("Wrote optimization_scenarios.json")

# store targeting scenario
eggs = df[df.product_category == 'EGGS']
displayed = eggs[eggs.is_displayed == 1]
current_avg_size = displayed['log_store_size_c'].mean()
store_sizes_unique = eggs.drop_duplicates('store_id')[['store_id', 'log_store_size_c']]
top_tercile_cutoff = store_sizes_unique['log_store_size_c'].quantile(2 / 3)
top_tercile_avg = store_sizes_unique[store_sizes_unique.log_store_size_c >= top_tercile_cutoff]['log_store_size_c'].mean()
b_disp_size = combined_models['EGGS'].params['is_displayed:log_store_size_c']
delta_size = top_tercile_avg - current_avg_size
actual_display_revenue = displayed['sales_value'].sum()
new_revenue_approx = actual_display_revenue * np.exp(delta_size * b_disp_size)

store_targeting = {
    'current_avg_size': round(current_avg_size, 3),
    'top_tercile_avg_size': round(top_tercile_avg, 3),
    'actual_revenue': round(actual_display_revenue),
    'scenario_revenue': round(new_revenue_approx),
    'delta': round(new_revenue_approx - actual_display_revenue),
    'pct_change': round((new_revenue_approx / actual_display_revenue - 1) * 100, 1)
}
with open(os.path.join(OUT_DIR, 'store_targeting_scenario.json'), 'w') as f:
    json.dump(store_targeting, f, indent=2)
print("Wrote store_targeting_scenario.json")

# ---------------------------------------------------------------------
# 6. Top-line summary numbers for the overview page
# ---------------------------------------------------------------------
total_category_revenue = int(df.groupby('product_category')['sales_value'].sum().sum())
summary = {
    'n_transactions': int(df.groupby('product_category').size().sum()),
    'n_products': int(df.groupby('product_category')['product_id'].nunique().sum()),
    'total_combined_delta': int(scenario_df['delta'].sum()),
    'total_promo_revenue': int(scenario_df['actual_revenue'].sum()),
    'pct_opportunity_vs_promo_revenue': round(scenario_df['delta'].sum() / scenario_df['actual_revenue'].sum() * 100, 1),
    'total_category_revenue': total_category_revenue,
    'pct_opportunity_vs_total_category_revenue': round(scenario_df['delta'].sum() / total_category_revenue * 100, 1),
    'categories': [c.title() for c in CATEGORIES]
}
with open(os.path.join(OUT_DIR, 'summary.json'), 'w') as f:
    json.dump(summary, f, indent=2)
print("Wrote summary.json")

print("\nAll dashboard data artifacts written to", OUT_DIR)
total_size = sum(
    os.path.getsize(os.path.join(OUT_DIR, f)) for f in os.listdir(OUT_DIR)
)
print(f"Total size: {total_size/1024:.1f} KB")

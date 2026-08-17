import json
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

BLUE = '#2563eb'
ORANGE = '#f59e0b'
GREEN = '#16a34a'
RED = '#dc2626'
SLATE = '#94a3b8'

st.set_page_config(
    page_title='Retail Price Elasticity and Promotion Uplift',
    page_icon='🥚',
    layout='wide'
)


@st.cache_data
def load_data():
    data = {}
    data['weekly'] = pd.read_parquet(os.path.join(DATA_DIR, 'weekly_trends.parquet'))
    data['price_by_promo'] = pd.read_parquet(os.path.join(DATA_DIR, 'price_by_promo.parquet'))
    data['store_curve'] = pd.read_parquet(os.path.join(DATA_DIR, 'store_size_curve.parquet'))
    data['discount_curve'] = pd.read_parquet(os.path.join(DATA_DIR, 'discount_depth_curve.parquet'))
    with open(os.path.join(DATA_DIR, 'elasticity_comparison.json')) as f:
        data['elasticity'] = pd.DataFrame(json.load(f))
    with open(os.path.join(DATA_DIR, 'promo_uplift.json')) as f:
        data['promo_uplift'] = pd.DataFrame(json.load(f))
    with open(os.path.join(DATA_DIR, 'optimal_discount_table.json')) as f:
        data['optimal_discount'] = pd.DataFrame(json.load(f))
    with open(os.path.join(DATA_DIR, 'optimization_scenarios.json')) as f:
        data['scenarios'] = pd.DataFrame(json.load(f))
    with open(os.path.join(DATA_DIR, 'store_targeting_scenario.json')) as f:
        data['store_targeting'] = json.load(f)
    with open(os.path.join(DATA_DIR, 'summary.json')) as f:
        data['summary'] = json.load(f)
    return data


data = load_data()

st.title('Retail Price Elasticity and Promotion Uplift')
st.caption(
    'A price elasticity and promotion optimization analysis built on the dunnhumby '
    'Complete Journey dataset, 2,469 households, one year of grocery transactions.'
)

page = st.sidebar.radio(
    'Section',
    ['Overview', 'Price and Promotion Trends', 'Price Elasticity',
     'Promotion Effectiveness', 'Optimization'],
)

st.sidebar.markdown('---')
st.sidebar.markdown(
    'Built by Nilkanth Changawala. Full analysis, including the fixed effects '
    'model design and every caveat, lives in the notebooks in this project\'s '
    'GitHub repository.'
)

CATEGORY_COLORS = {'Eggs': BLUE, 'Bath Tissues': ORANGE}


# ===========================================================================
# OVERVIEW
# ===========================================================================
if page == 'Overview':
    summary = data['summary']

    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Transactions analyzed', f"{summary['n_transactions']:,}")
    col2.metric('Products covered', summary['n_products'])
    col3.metric('Estimated revenue opportunity', f"${summary['total_combined_delta']:,}")
    col4.metric('Lift vs. promoted revenue', f"{summary['pct_opportunity_vs_promo_revenue']}%")

    st.markdown('### What this project does')
    st.markdown(
        'A retailer runs in store displays and mailer promotions on thousands of '
        'products every week without a reliable way to tell which ones actually grow '
        'revenue. This project estimates price elasticity of demand and the causal '
        'effect of promotion for two grocery categories, Eggs and Bath Tissues, then '
        'turns that into a specific, quantified recommendation for how deep a discount '
        'each promotion type should run.'
    )

    st.markdown('### Why this is harder than a typical sales dashboard')
    st.markdown(
        'Price and promotion are not randomly assigned by a retailer. A naive '
        'regression of quantity sold on price confuses the retailer\'s own pricing '
        'decisions with actual consumer demand response, a problem called price '
        'endogeneity. The core technical work of this project is isolating the real '
        'causal effect using product, store, and week fixed effects, and being honest '
        'about where that identification strategy could still be wrong.'
    )

    st.markdown('### The five phase pipeline')
    phase_cols = st.columns(5)
    phases = [
        ('1. Data warehouse', 'Star schema in DuckDB built from the raw dataset.'),
        ('2. Exploration', 'Found that promotion and price are confounded, differently by category.'),
        ('3. Elasticity', 'Fixed effects model, corrected the naive elasticity estimate.'),
        ('4. Heterogeneity', 'Tested whether promotion effect varies by income, store size, and discount depth.'),
        ('5. Optimization', 'Solved for the revenue maximizing discount depth per category and promo type.'),
    ]
    for col, (title, desc) in zip(phase_cols, phases):
        with col:
            st.markdown(f'**{title}**')
            st.caption(desc)

    st.info(
        'Every recommendation in this dashboard depends on an identifying assumption '
        'that could be wrong, see the Optimization section for the full caveat. Treat '
        'the numbers here as a strong, quantified starting point for a controlled test, '
        'not a guaranteed result.'
    )


# ===========================================================================
# PRICE AND PROMOTION TRENDS
# ===========================================================================
elif page == 'Price and Promotion Trends':
    st.header('Price and promotion trends over 53 weeks')

    category = st.selectbox('Category', ['Eggs', 'Bath Tissues'])
    weekly = data['weekly']
    weekly_cat = weekly[weekly.product_category == category.upper()]

    color = CATEGORY_COLORS[category]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                         subplot_titles=('Average unit price by week', 'Promotion rate by week'))
    fig.add_trace(go.Scatter(x=weekly_cat.week, y=weekly_cat.avg_price, mode='lines+markers',
                              line=dict(color=color), name='Avg price'), row=1, col=1)
    fig.add_trace(go.Bar(x=weekly_cat.week, y=weekly_cat.promo_rate, marker_color=ORANGE,
                          name='Promo rate'), row=2, col=1)
    fig.update_yaxes(title_text='Price, dollars', row=1, col=1)
    fig.update_yaxes(title_text='Share of transactions', row=2, col=1, range=[0, 1])
    fig.update_xaxes(title_text='Week', row=2, col=1)
    fig.update_layout(height=550, showlegend=False, margin=dict(t=40, b=20))
    st.plotly_chart(fig, width="stretch")

    st.markdown(
        'Both categories show real week to week price movement, and promotion '
        'activity is lumpy rather than seasonal. That volatility is exactly why the '
        'elasticity model needs week fixed effects rather than a smooth time trend.'
    )

    st.subheader('Does promotion coincide with a lower price')
    price_promo = data['price_by_promo']
    sub = price_promo[price_promo.product_category == category.upper()]
    fig2 = go.Figure()
    for status, label, box_color in [(0, 'Not promoted', SLATE), (1, 'Promoted', color)]:
        fig2.add_trace(go.Box(y=sub[sub.is_promo == status]['unit_price'], name=label,
                               marker_color=box_color))
    fig2.update_layout(height=420, yaxis_title='Unit price, dollars', margin=dict(t=20))
    st.plotly_chart(fig2, width="stretch")

    if category == 'Eggs':
        st.markdown(
            'For Eggs, promoted transactions run consistently cheaper, a real, '
            'material confound between price and promotion that the elasticity model '
            'has to account for directly.'
        )
    else:
        st.markdown(
            'For Bath Tissues, the picture is less obvious. Mean price is similar '
            'between promoted and non promoted transactions, but the median is higher '
            'when promoted. Only a minority of Bath Tissue products are ever promoted '
            'at all, and those tend to be larger pack sizes, a composition effect '
            'rather than a pricing effect. This is why the model needs product level '
            'fixed effects, not just a category level comparison.'
        )


# ===========================================================================
# PRICE ELASTICITY
# ===========================================================================
elif page == 'Price Elasticity':
    st.header('Naive versus fixed effects price elasticity')

    st.markdown(
        'The naive model regresses quantity on price alone. The fixed effects model '
        'adds product, store, and week fixed effects, isolating the real demand '
        'response from the retailer\'s own pricing and promotion decisions.'
    )

    elasticity = data['elasticity']
    fig = go.Figure()
    for model_name, color in [('Naive', SLATE), ('Fixed Effects', BLUE)]:
        sub = elasticity[elasticity.model == model_name]
        fig.add_trace(go.Bar(
            x=sub.category, y=sub.elasticity, name=model_name, marker_color=color,
            error_y=dict(type='data', array=1.96 * sub.se, visible=True)
        ))
    fig.update_layout(
        height=450, yaxis_title='Estimated price elasticity', barmode='group',
        margin=dict(t=20)
    )
    fig.add_hline(y=0, line_color='black', line_width=1)
    st.plotly_chart(fig, width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        st.metric('Eggs elasticity, corrected', '-0.52', delta='vs -0.20 naive', delta_color='off')
        st.caption(
            'Ignoring the confound understated Eggs price sensitivity by more than '
            'half. This is the clearest demonstration in the whole project of why '
            'the fixed effects correction matters.'
        )
    with col2:
        st.metric('Bath Tissues elasticity, corrected', '-0.19', delta='vs -0.21 naive', delta_color='off')
        st.caption(
            'The correction barely moves Bath Tissues, consistent with its confound '
            'being a product mix effect rather than a simple price and promotion '
            'correlation.'
        )

    st.subheader('Promotion uplift by type')
    promo_uplift = data['promo_uplift']
    colors = [GREEN if sig else SLATE for sig in promo_uplift.significant]
    fig2 = go.Figure(go.Bar(
        x=promo_uplift.pct_lift,
        y=promo_uplift.category + ', ' + promo_uplift.promo_type,
        orientation='h', marker_color=colors
    ))
    fig2.update_layout(height=350, xaxis_title='Percent lift in quantity sold', margin=dict(t=20))
    fig2.add_vline(x=0, line_color='black', line_width=1)
    st.plotly_chart(fig2, width="stretch")
    st.caption('Green bars are statistically significant at p less than 0.05.')

    st.markdown(
        'Both promo types genuinely move volume for Eggs, mailer features especially. '
        'For Bath Tissues the effect is much smaller, and in store display is not '
        'statistically significant at all, consistent with a more habitual, less '
        'promotion driven category.'
    )


# ===========================================================================
# PROMOTION EFFECTIVENESS (heterogeneity)
# ===========================================================================
elif page == 'Promotion Effectiveness':
    st.header('Where and why promotion effectiveness varies')

    st.subheader('Does display effectiveness scale with store size')
    store_curve = data['store_curve']
    fig = go.Figure()
    for cat in ['Eggs', 'Bath Tissues']:
        sub = store_curve[store_curve.category == cat]
        fig.add_trace(go.Scatter(x=sub.log_store_size_c, y=sub.predicted_lift_pct, mode='lines',
                                  name=cat, line=dict(color=CATEGORY_COLORS[cat], width=3)))
    fig.add_hline(y=0, line_color='black', line_width=1)
    fig.update_layout(
        height=420, xaxis_title='Store size, log transactions, centered on chain average',
        yaxis_title='Predicted display lift, percent', margin=dict(t=20)
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        'For Eggs, moving from a small store to one roughly 2.7 times larger adds '
        'about 10 percentage points of display lift on top of the baseline effect, '
        'a statistically significant relationship. Bath Tissues shows no comparable '
        'pattern. If display space is limited, Eggs displays belong in the highest '
        'traffic stores first.'
    )

    st.subheader('Is the promotion effect about visibility or about the price cut')
    st.markdown(
        'Displays and mailers almost always come bundled with some discount. This '
        'chart separates the two by holding regular price fixed and entering '
        'discount depth as its own variable, revealing whether a deeper discount '
        'makes the display or mailer itself more effective.'
    )
    discount_curve = data['discount_curve']
    category2 = st.selectbox('Category', ['Eggs', 'Bath Tissues'], key='mechanism_cat')
    sub = discount_curve[discount_curve.category == category2]
    fig2 = go.Figure()
    for promo_type, color in [('Display', BLUE), ('Mailer', ORANGE)]:
        s = sub[sub.promo_type == promo_type]
        fig2.add_trace(go.Scatter(x=s.discount_pct, y=s.predicted_lift_pct, mode='lines',
                                   name=promo_type, line=dict(color=color, width=3)))
    fig2.add_hline(y=0, line_color='black', line_width=1)
    fig2.update_layout(
        height=420, xaxis_title='Discount depth, percent', yaxis_title='Predicted lift, percent',
        margin=dict(t=20)
    )
    st.plotly_chart(fig2, width="stretch")

    if category2 == 'Eggs':
        st.markdown(
            'For Eggs, mailer and discount depth are complements, a mailer paired '
            'with a real price cut sells far more than a mailer alone, the lift '
            'roughly quadruples moving from a shallow to a deep discount. Display '
            'works the opposite way, its lift is strongest with little or no '
            'discount attached, meaning it is doing genuine visibility work on its '
            'own, separate from price.'
        )
    else:
        st.markdown(
            'For Bath Tissues, neither promo type gets more effective with a deeper '
            'discount, if anything both decline slightly. Deal depth does not appear '
            'to be what drives this category, plain visibility already captures most '
            'of what promotion can do here.'
        )

    st.subheader('Household income, a suggestive but unconfirmed lead')
    st.markdown(
        'Demographic data only covers about a third of households. For Eggs, lower '
        'income households show a directionally stronger response to in store '
        'display than higher income households, matching what you would expect from '
        'tighter grocery budgets, but the difference does not clear the standard '
        'significance bar at this sample size. Worth treating as a lead for future '
        'analysis with a larger demographic sample, not a confirmed result.'
    )


# ===========================================================================
# OPTIMIZATION
# ===========================================================================
elif page == 'Optimization':
    st.header('From model to recommendation')

    st.markdown(
        'For a product already running a promotion, revenue depends on discount '
        'depth in a specific way: quantity grows roughly exponentially with discount '
        'depth, while price falls linearly. Solving for where an extra point of '
        'discount stops paying for itself in volume gives the revenue maximizing '
        'discount depth for each category and promo type.'
    )

    opt_table = data['optimal_discount']
    st.dataframe(
        opt_table.rename(columns={
            'category': 'Category', 'promo_type': 'Promo type',
            'combined_slope_k': 'Combined slope',
            'model_optimal_discount_pct': 'Model optimal discount, percent',
            'current_avg_discount_pct': 'Current average discount, percent'
        }),
        width="stretch", hide_index=True
    )

    st.subheader('Estimated revenue impact of closing that gap')
    scenarios = data['scenarios']
    colors = [GREEN if x > 0 else RED for x in scenarios['pct_change']]
    fig = go.Figure(go.Bar(
        x=scenarios['pct_change'],
        y=scenarios.category + '<br>' + scenarios.change,
        orientation='h', marker_color=colors
    ))
    fig.add_vline(x=0, line_color='black', line_width=1)
    fig.update_layout(height=380, xaxis_title='Revenue change, percent, versus actual practice',
                       margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")

    summary = data['summary']
    col1, col2 = st.columns(2)
    col1.metric(
        'Combined opportunity vs. promoted revenue',
        f"{summary['pct_opportunity_vs_promo_revenue']}%",
        help='The estimated dollar gain as a share of the revenue these four promo '
             'programs generated in the observed period.'
    )
    col2.metric(
        'Combined opportunity vs. total category revenue',
        f"{summary['pct_opportunity_vs_total_category_revenue']}%",
        help='The same dollar gain as a share of all Eggs and Bath Tissues revenue, '
             'promoted and non promoted transactions combined, a more conservative view.'
    )

    st.subheader('A smaller, related opportunity: store targeting for Eggs display')
    st_data = data['store_targeting']
    st.markdown(
        f"Concentrating Eggs display slots into the highest traffic third of stores, "
        f"holding the total number of display weeks fixed, is worth an estimated "
        f"{st_data['pct_change']}%. Smaller than the discount depth opportunity above, "
        f"because current display placement is already somewhat skewed toward larger "
        f"stores rather than being random."
    )

    st.warning(
        'Every number above relies on one assumption: that after controlling for '
        'product, store, and week, the discount depth chosen in a given week is as '
        'good as random with respect to demand. If store managers deepen discounts '
        'specifically when they expect a slow week, that pattern would look like '
        '"deeper discounts do not help" in this data even if it is not true. The '
        'honest recommendation is not to act on these numbers directly, it is to run '
        'a controlled test, randomly assign discount depth across a sample of stores '
        'for a few weeks, and confirm the pattern holds before committing a full '
        'promo budget to it.'
    )

    st.caption(
        'This dataset tracks a panel of 2,469 households, a sample, not a retailer\'s '
        'full transaction volume. The dollar figures throughout this project scale '
        'with that sample and should be read as a percentage opportunity rather than '
        'a number to put directly into a real budget.'
    )

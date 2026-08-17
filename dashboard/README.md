# Dashboard

Interactive Streamlit dashboard presenting the price elasticity, promotion
heterogeneity, and optimization results from this project.

## Why this does not touch warehouse.duckdb

warehouse.duckdb is about 150MB, over GitHub's 100MB file limit, so it
cannot be committed to the repo this dashboard deploys from. Instead,
`prepare_dashboard_data.py` runs once locally, where warehouse.duckdb
exists, and writes small parquet and json files into `data/`, about 43KB
total. `app.py` only ever reads those small files. This also makes the
deployed app load fast, since it never re-runs a regression on page load.

## Running locally

From the project root, with the main requirements.txt already installed:

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Opens at http://localhost:8501.

## Regenerating the data if the model changes

If the analysis in the notebooks changes, rerun the prep script before the
dashboard will reflect it:

```bash
python dashboard/prepare_dashboard_data.py
```

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub, `data/` and `.streamlit/config.toml` are
   small enough to commit and already are not in .gitignore.
2. Go to share.streamlit.io, sign in with GitHub, click New app.
3. Point it at this repository, set the main file path to
   `dashboard/app.py`.
4. Streamlit Cloud installs from `dashboard/requirements.txt`
   automatically since it is in the same folder as the main file.
5. Deploy. You get a public URL to put on your resume and LinkedIn.

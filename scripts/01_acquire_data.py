"""
Acquire and convert the dunnhumby "Complete Journey" dataset.

Source: https://github.com/bradleyboehmke/completejourney
This is the same data used by the R package `completejourney`, redistributed
as raw .rda/.rds files. It is the FULL dataset (1.47M transactions, 20.9M
promotion records) -- not the smaller "sample" tables bundled in the R package.

Requirements:
    - git
    - R (base R is enough, no packages needed beyond what ships by default)
    - Python: pandas, pyarrow, duckdb, pyreadr  (pip install -r requirements.txt)

Why R is used at all: the `promotions` table is ~21M rows and pyreadr (the
pure-Python RDS reader) loads the whole object graph into memory before
converting to pandas, which OOMs on machines with <8GB RAM. Base R's
readRDS() is far more memory-efficient, so we shell out to R just for that
one file and write a CSV, which DuckDB then streams into Parquet without
ever materialising the whole thing in Python memory.

Usage:
    python scripts/01_acquire_data.py
"""

import os
import subprocess
import shutil
import pyreadr
import duckdb

REPO_URL = "https://github.com/bradleyboehmke/completejourney.git"
RAW_DIR = "data_raw/repo"
OUT_DIR = "data"

SMALL_TABLES = {
    "campaign_descriptions.rda": "campaign_descriptions",
    "campaigns.rda": "campaigns",
    "coupon_redemptions.rda": "coupon_redemptions",
    "coupons.rda": "coupons",
    "demographics.rda": "demographics",
    "products.rda": "products",
}

LARGE_TABLE = {"transactions.rds": "transactions"}          # ~1.5M rows, fine in Python
HUGE_TABLE = {"promotions.rds": "promotions"}                # ~21M rows, needs R


def clone_repo():
    if os.path.exists(RAW_DIR):
        print(f"Repo already present at {RAW_DIR}, skipping clone")
        return
    os.makedirs("data_raw", exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, RAW_DIR], check=True
    )


def convert_small_and_medium_tables():
    os.makedirs(OUT_DIR, exist_ok=True)
    data_dir = os.path.join(RAW_DIR, "data")
    for fname, tname in {**SMALL_TABLES, **LARGE_TABLE}.items():
        path = os.path.join(data_dir, fname)
        res = pyreadr.read_r(path)
        df = list(res.values())[0]
        out_path = os.path.join(OUT_DIR, f"{tname}.parquet")
        df.to_parquet(out_path, index=False)
        print(f"{tname}: {df.shape} -> {out_path}")


def convert_huge_table():
    fname, tname = list(HUGE_TABLE.items())[0]
    data_dir = os.path.join(RAW_DIR, "data")
    src = os.path.join(data_dir, fname)
    csv_tmp = os.path.join(OUT_DIR, f"{tname}.csv")
    parquet_out = os.path.join(OUT_DIR, f"{tname}.parquet")

    r_script = f"""
    df <- readRDS("{src}")
    write.csv(df, "{csv_tmp}", row.names = FALSE)
    cat("rows written:", nrow(df), "\\n")
    """
    subprocess.run(["Rscript", "-e", r_script], check=True)

    con = duckdb.connect()
    con.execute(
        f"""
        COPY (SELECT * FROM read_csv_auto('{csv_tmp}', header=True))
        TO '{parquet_out}' (FORMAT PARQUET)
        """
    )
    os.remove(csv_tmp)
    print(f"{tname}: streamed CSV -> {parquet_out}")


if __name__ == "__main__":
    clone_repo()
    convert_small_and_medium_tables()
    convert_huge_table()
    print("\nAll tables converted. Run sql/01_build_warehouse.sql next (see README).")

"""IO: read-side accessors for the clean/ layer.

`clean.py` owns the transform that writes
clean/. This module owns the read side of clean/.

The naming convention follows pandas/dbt:
    - `read_<table>(year)`     single-year slice
    - `read_all_<table>()`     all years concatenated
"""

from __future__ import annotations

import pandas as pd

from pipeline import extract

CLEANED_DIR = extract.REPO_ROOT / "clean"
REPORTS_DIR = extract.REPO_ROOT / "reports"
SQL_DIR = extract.REPO_ROOT / "sql"
DB_PATH = CLEANED_DIR / "nersc.duckdb"


def read_allocations(year: int) -> pd.DataFrame:
    df = pd.read_csv(CLEANED_DIR / "allocations.csv")
    return df[df["year"].astype(int) == year].reset_index(drop=True)


def read_ercap(year: int) -> pd.DataFrame:
    df = pd.read_csv(CLEANED_DIR / "ercap.csv")
    year_col = "year" if "year" in df.columns else "source_file_year"
    return df[df[year_col].astype(int) == year].reset_index(drop=True)


def read_all_allocations() -> pd.DataFrame:
    return pd.read_csv(CLEANED_DIR / "allocations.csv")


def read_all_ercap() -> pd.DataFrame:
    return pd.read_csv(CLEANED_DIR / "ercap.csv")


def read_users() -> pd.DataFrame:
    return pd.read_csv(CLEANED_DIR / "users.csv")


def read_repos() -> pd.DataFrame:
    return pd.read_csv(CLEANED_DIR / "repos.csv")


def read_alloc_repo_year_features() -> pd.DataFrame:
    """Per-(repo, year) network features built from allocations + graph code."""
    return pd.read_csv(CLEANED_DIR / "alloc_repo_year_features.csv")


def write_alloc_repo_year_features(df: pd.DataFrame) -> None:
    df.to_csv(CLEANED_DIR / "alloc_repo_year_features.csv", index=False)


def read_alloc_user_year_features() -> pd.DataFrame:
    """Per-(user, year) activity aggregates built from allocations."""
    return pd.read_csv(CLEANED_DIR / "alloc_user_year_features.csv")


def write_alloc_user_year_features(df: pd.DataFrame) -> None:
    df.to_csv(CLEANED_DIR / "alloc_user_year_features.csv", index=False)


def read_ercap_repo_year_features() -> pd.DataFrame:
    """Per-(repo, year) allocation-request aggregates."""
    return pd.read_csv(CLEANED_DIR / "ercap_repo_year_features.csv")


def write_ercap_repo_year_features(df: pd.DataFrame) -> None:
    df.to_csv(CLEANED_DIR / "ercap_repo_year_features.csv", index=False)

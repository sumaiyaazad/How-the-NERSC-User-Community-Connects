"""Extract: load raw CSVs from raw/ into DataFrames.

Two input files:
    - raw/allocations.csv  allocation records (one row per user-project-year)
    - raw/ercap.csv        request records (one row per project request)

This module ONLY loads and lightly standardizes (column-name normalization,
dropping the junk index column, tagging the source year). All semantic
cleaning lives in clean.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# Repo root is the parent of this file's parent (pipeline/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw"

ALLOC_FILE = RAW_DIR / "allocations.csv"
ERCAP_FILE = RAW_DIR / "ercap.csv"


def _detect_years() -> list[int]:
    """Find years present in both raw files."""
    if not ALLOC_FILE.exists() or not ERCAP_FILE.exists():
        return []
    alloc = _load_alloc_raw()
    ercap = _load_ercap_raw()
    alloc_years = set(alloc["year"].dropna().astype(int).unique())
    ercap_years = set(ercap["year"].dropna().astype(int).unique())
    # Return plain Python ints: numpy.int64 is not accepted as a random seed
    # by NetworkX/random, which the notebooks rely on.
    return sorted(int(y) for y in (alloc_years & ercap_years))

def _snake_case(name: str) -> str:
    """Turn CSV column names into snake_case."""
    name = name.strip()
    # Drop the leftover 'u_' prefix that some request-side columns carry.
    if name.startswith("u_"):
        name = name[2:]
    # Preserve the '%' meaning before we strip symbols, otherwise
    # '% CPU Used' would collapse to 'cpu_used' and lose the "percent" signal.
    name = name.replace("%", " pct ")
    # Replace anything that isn't alphanumeric with a single underscore.
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name.lower()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_snake_case(c) for c in df.columns]
    return df


def _drop_index_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop leftover pandas index columns if a CSV has them."""
    cols_to_drop = [c for c in df.columns if c == "" or c.startswith("unnamed")]
    return df.drop(columns=cols_to_drop, errors="ignore")


def _load_alloc_raw() -> pd.DataFrame:
    df = pd.read_csv(ALLOC_FILE)
    df = _normalize_columns(df)
    df = _drop_index_columns(df)
    return df


def _load_ercap_raw() -> pd.DataFrame:
    df = pd.read_csv(ERCAP_FILE)
    df = _normalize_columns(df)
    df = _drop_index_columns(df)
    df = df.rename(columns={
        "repo": "repo_listdisplay",
    })
    return df


def load_alloc(year: int) -> pd.DataFrame:
    """Load one year of allocation data."""
    df = _load_alloc_raw()
    return df[df["year"].astype(int) == year].reset_index(drop=True)


def load_ercap(year: int) -> pd.DataFrame:
    """Load one year of request data."""
    df = _load_ercap_raw()
    df = df[df["year"].astype(int) == year].reset_index(drop=True)
    df["source_file_year"] = year
    return df


def load_all_alloc() -> pd.DataFrame:
    """Stack all yearly allocation files into one long DataFrame."""
    return pd.concat([load_alloc(y) for y in YEARS], ignore_index=True)


def load_all_ercap() -> pd.DataFrame:
    """Stack all yearly request files into one long DataFrame."""
    return pd.concat([load_ercap(y) for y in YEARS], ignore_index=True)


YEARS = _detect_years()


if __name__ == "__main__":
    a = load_all_alloc()
    e = load_all_ercap()
    print(f"allocations: {len(a):,} rows, {len(a.columns)} columns, years {sorted(a['year'].unique())}")
    print(f"ercap:       {len(e):,} rows, {len(e.columns)} columns, years {sorted(e['source_file_year'].unique())}")

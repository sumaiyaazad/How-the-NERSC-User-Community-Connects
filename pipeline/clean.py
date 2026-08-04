"""Clean: turn raw DataFrames from extract.py into tidy, deduped CSVs.

Outputs (written to clean/):
    allocations.csv  clean allocation rows
    ercap.csv        clean request rows
    users.csv        deduped across years
    repos.csv        deduped across years

Cleaning -
    1. whitespace strip on all string columns
    2. generic whitespace normalization on key categorical fields
    3. parse date columns into real datetimes
    4. remove non-analysis repos if a local blacklist is supplied
    5. drop columns not needed for the network analysis
    6. drop exact-duplicate rows (and report how many)
"""

from __future__ import annotations

import pandas as pd

from pipeline import extract
from pipeline.io import CLEANED_DIR

# Columns we expect to be dates.
ALLOC_DATE_COLS = ["account_start_date"]
ERCAP_DATE_COLS = ["sys_created_on", "sys_updated_on"]

# Repo codes excluded by the legacy notebooks because they represent staff,
# training, guest, test, or placeholder allocations that distort analysis.
BLACKLISTED_REPOS: dict[str, str] = {}

# Categorical fields where whitespace drift causes false splits in groupby.
# Allocations-side and request-side columns share this list. The cleaner guards
# each field with `if col in df.columns`.
CATEGORICAL_COLS = [
    "office",
    "science_category",
]

# Keep only the fields used by the graph, feature, and validation layers.
ALLOC_ANALYSIS_COLUMNS = [
    "repo",
    "pi_user_id",
    "user_id",
    "office",
    "science_category",
    "cpu_node_hours_charged",
    "gpu_node_hours_charged",
    "year",
]

ERCAP_ANALYSIS_COLUMNS = [
    "year",
    "repo_listdisplay",
    "hours_requested",
    "hours_used",
    "gpu_requested",
    "gpu_used",
    "storage_requested",
    "storage_used",
    "source_file_year",
]

NUMERIC_COLUMNS = [
    "cpu_node_hours_charged",
    "gpu_node_hours_charged",
    "hours_requested",
    "hours_used",
    "gpu_requested",
    "gpu_used",
    "storage_requested",
    "storage_used",
]

BOOL_COLUMNS: list[str] = []

# Optional raw-to-canonical category remaps. None are configured.
ALIAS_MAPS: dict[str, dict[str, str]] = {}


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        # Strip + collapse internal whitespace.
        df[col] = (
            df[col]
            .astype("string")
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )
    return df


def _normalize_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()

    for col, mapping in ALIAS_MAPS.items():
        if col in df.columns and mapping:
            df[col] = df[col].replace(mapping)

    return df


def _coerce_analysis_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in BOOL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)
    return df


def _select_analysis_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df[columns]


def _parse_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _dedupe(df: pd.DataFrame, label: str) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    after = len(df)
    if before != after:
        print(f"  [{label}] dropped {before - after:,} exact-duplicate rows")
    return df


def _drop_blacklisted_repos(
    df: pd.DataFrame,
    repo_col: str,
    label: str,
) -> pd.DataFrame:
    """Remove repos that legacy notebook analyses explicitly excluded."""
    if repo_col not in df.columns:
        return df
    before = len(df)
    df = df.loc[~df[repo_col].isin(BLACKLISTED_REPOS)].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"  [{label}] dropped {dropped:,} rows from blacklisted repos")
    return df


def clean_alloc_year(year: int) -> pd.DataFrame:
    df = extract.load_alloc(year)
    df = _strip_strings(df)
    df = _normalize_categoricals(df)
    df = _parse_dates(df, ALLOC_DATE_COLS)
    df = _drop_blacklisted_repos(df, "repo", f"alloc {year}")
    df = _select_analysis_columns(df, ALLOC_ANALYSIS_COLUMNS)
    df = _coerce_analysis_types(df)
    df = _dedupe(df, f"alloc {year}")
    return df


def clean_ercap_year(year: int) -> pd.DataFrame:
    df = extract.load_ercap(year)
    df = _strip_strings(df)
    df = _normalize_categoricals(df)
    df = _parse_dates(df, ERCAP_DATE_COLS)
    df = _drop_blacklisted_repos(df, "repo_listdisplay", f"ercap {year}")
    df = _select_analysis_columns(df, ERCAP_ANALYSIS_COLUMNS)
    df = _coerce_analysis_types(df)
    df = _dedupe(df, f"ercap {year}")
    return df


def build_users(all_alloc: pd.DataFrame) -> pd.DataFrame:
    """One row per user_id, with tenure (number of active years) and lifetime
    project count."""
    g = all_alloc.groupby("user_id")
    years_active = g["year"].apply(lambda s: sorted(set(s)))
    users = pd.DataFrame({
        "user_id": g.size().index,
        "tenure": years_active.apply(len).astype(int).values,
        "n_repos_lifetime": g["repo"].nunique().values,
    }).reset_index(drop=True)
    return users


def build_repos(all_alloc: pd.DataFrame) -> pd.DataFrame:
    """One row per repo, with its dominant office and science category and its
    lifetime user count."""
    def _mode_or_none(s):
        m = s.mode(dropna=True)
        return m.iloc[0] if len(m) else None

    g = all_alloc.groupby("repo")
    repos = pd.DataFrame({
        "repo": g.size().index,
        "office": g["office"].apply(_mode_or_none).values if "office" in all_alloc.columns else None,
        "science_category": g["science_category"].apply(_mode_or_none).values if "science_category" in all_alloc.columns else None,
        "n_users_lifetime": g["user_id"].nunique().values,
    }).reset_index(drop=True)
    return repos


def write_cleaned() -> None:
    """Run all cleaning and write outputs to clean/."""
    CLEANED_DIR.mkdir(exist_ok=True)
    print("Cleaning allocations...")
    alloc_frames = []
    for y in extract.YEARS:
        df = clean_alloc_year(y)
        alloc_frames.append(df)
    print("Cleaning ercap...")
    ercap_frames = []
    for y in extract.YEARS:
        df = clean_ercap_year(y)
        ercap_frames.append(df)

    all_alloc = pd.concat(alloc_frames, ignore_index=True)
    all_ercap = pd.concat(ercap_frames, ignore_index=True)
    all_alloc.to_csv(CLEANED_DIR / "allocations.csv", index=False)
    all_ercap.to_csv(CLEANED_DIR / "ercap.csv", index=False)

    print("Building users.csv ...")
    users = build_users(all_alloc)
    users.to_csv(CLEANED_DIR / "users.csv", index=False)

    print("Building repos.csv ...")
    repos = build_repos(all_alloc)
    repos.to_csv(CLEANED_DIR / "repos.csv", index=False)

    print(f"Done. {len(users):,} users, {len(repos):,} repos.")


if __name__ == "__main__":
    write_cleaned()

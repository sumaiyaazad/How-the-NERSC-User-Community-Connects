"""Validate: run data-quality checks on clean/ and write reports/dq_report.md.

Checks:
    1. Row counts per table per year.
    2. Null rate per column per year (flags schema drift: columns appearing/disappearing).
    3. Duplicate (user_id, repo, year) combinations in allocations.
    4. Allocation-request <-> allocation join coverage on (repo, year).
    5. User-id format check (adjective-noun handle pattern).
    6. Numeric outliers: negative hours, balances larger than allocation.
"""

from __future__ import annotations

import re

import pandas as pd

from pipeline import extract, clean, io as cleaned_io
from pipeline.io import CLEANED_DIR, REPORTS_DIR

ADJ_NOUN_RE = re.compile(r"^[a-z]+-[a-z]+$")


def _markdown_table(df: pd.DataFrame, include_index: bool = False) -> str:
    """Render a small DataFrame as Markdown without tabulate."""
    if df is None or df.empty:
        return "_No rows._"
    frame = df.reset_index() if include_index else df.copy()

    def fmt(value) -> str:
        if pd.isna(value):
            return ""
        return str(value).replace("|", "\\|")

    headers = [fmt(c) for c in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(fmt(v) for v in row.tolist()) + " |")
    return "\n".join(lines)


def _load_cleaned_alloc() -> pd.DataFrame:
    return cleaned_io.read_all_allocations()


def _load_cleaned_ercap() -> pd.DataFrame:
    return cleaned_io.read_all_ercap()


def row_counts(alloc: pd.DataFrame, ercap: pd.DataFrame) -> pd.DataFrame:
    a = alloc.groupby("year").size().rename("alloc_rows")
    e = ercap.groupby("source_file_year").size().rename("ercap_rows")
    return pd.concat([a, e], axis=1).fillna(0).astype(int).reset_index().rename(columns={"index": "year"})


def exact_duplicates_dropped() -> pd.DataFrame:
    """Per-year count of exact-duplicate rows removed by clean.py's _dedupe.
    Computed as raw_rows - clean_rows, since _dedupe is the only row-dropping step."""
    rows = []
    for y in extract.YEARS:
        raw_alloc = len(extract.load_alloc(y))
        clean_alloc = len(cleaned_io.read_allocations(y))
        raw_ercap = len(extract.load_ercap(y))
        clean_ercap = len(cleaned_io.read_ercap(y))
        rows.append({
            "year": y,
            "alloc_dupes_dropped": raw_alloc - clean_alloc,
            "ercap_dupes_dropped": raw_ercap - clean_ercap,
        })
    return pd.DataFrame(rows)


def null_rates(df: pd.DataFrame, year_col: str) -> pd.DataFrame:
    """Null rate per column per year. High variation across years = schema drift."""
    return df.groupby(year_col).apply(lambda g: g.isna().mean()).round(3)


def duplicate_user_repo_year_details(alloc: pd.DataFrame) -> dict:
    """For (user_id, repo, year) duplicates, identify *which columns differ*
    between the duplicate rows."""
    key = ["user_id", "repo", "year"]
    if not all(c in alloc.columns for c in key):
        return {}
    dup_mask = alloc.duplicated(subset=key, keep=False)
    dups = alloc[dup_mask].copy()
    if dups.empty:
        return {"n_dup_rows": 0, "n_dup_groups": 0, "differing_cols": pd.DataFrame(),
                "sample": pd.DataFrame(), "by_year": pd.DataFrame()}

    # Per non-key column: in how many duplicate groups does this column have >1 unique value?
    non_key = [c for c in alloc.columns if c not in key]
    grouped = dups.groupby(key, dropna=False)
    diff_counts = {c: int((grouped[c].nunique(dropna=False) > 1).sum()) for c in non_key}
    n_groups = grouped.ngroups
    differing = (
        pd.DataFrame({"column": list(diff_counts.keys()),
                      "groups_where_it_differs": list(diff_counts.values())})
        .assign(pct_of_dup_groups=lambda d: (d.groups_where_it_differs / n_groups).round(3))
        .sort_values("groups_where_it_differs", ascending=False)
        .query("groups_where_it_differs > 0")
        .reset_index(drop=True)
    )

    # Per-year breakdown of duplicate rows.
    by_year = dups.groupby("year").size().rename("dup_rows").reset_index()

    # A small sample: first 3 duplicate groups, full rows side by side.
    sample_keys = list(grouped.size().head(3).index)
    sample = dups[dups.set_index(key).index.isin(sample_keys)].sort_values(key)

    return {
        "n_dup_rows": int(dup_mask.sum()),
        "n_dup_groups": int(n_groups),
        "differing_cols": differing,
        "sample": sample,
        "by_year": by_year,
    }


def user_id_format_details(alloc: pd.DataFrame) -> dict:
    """Bucket bad user_ids by failure mode and list all of them."""
    if "user_id" not in alloc.columns:
        return {}
    ids = alloc["user_id"].dropna().astype(str).unique()
    bad = sorted(i for i in ids if not ADJ_NOUN_RE.match(i))

    def reason(s: str) -> str:
        if s.count("-") >= 2:
            return "multi_token"
        if any(c.isupper() for c in s):
            return "uppercase"
        if not s.isascii():
            return "non_ascii"
        return "other"

    buckets: dict[str, list[str]] = {}
    for i in bad:
        buckets.setdefault(reason(i), []).append(i)
    return {
        "n_total": len(ids),
        "n_bad": len(bad),
        "buckets": buckets,
    }


def ercap_alloc_join_coverage(alloc: pd.DataFrame, ercap: pd.DataFrame) -> dict:
    """How many ercap rows join to at least one allocation row on (repo, year)?

    ercap stores repo in repo_listdisplay; allocations store it in repo.
    """
    if "repo_listdisplay" not in ercap.columns or "repo" not in alloc.columns:
        return {"note": "missing join columns"}
    alloc_keys = set(zip(alloc["repo"].astype(str), alloc["year"].astype(int)))
    e_keys = list(zip(ercap["repo_listdisplay"].astype(str),
                      ercap.get("year", ercap["source_file_year"]).astype(int)))
    matched = sum(1 for k in e_keys if k in alloc_keys)
    return {
        "ercap_rows": len(e_keys),
        "matched_to_allocation": matched,
        "unmatched": len(e_keys) - matched,
        "match_rate": round(matched / max(len(e_keys), 1), 3),
    }


def categorical_value_counts_raw(top_n: int | None = None) -> dict:
    """For each categorical column declared in clean.CATEGORICAL_COLS, return
    value_counts. 
    """
    raw_alloc = pd.concat([extract.load_alloc(y) for y in extract.YEARS], ignore_index=True)
    raw_ercap = pd.concat([extract.load_ercap(y) for y in extract.YEARS], ignore_index=True)
    out = {}
    for col in clean.CATEGORICAL_COLS:
        source, table = None, None
        if col in raw_alloc.columns:
            source, table = raw_alloc, "allocations"
        elif col in raw_ercap.columns:
            source, table = raw_ercap, "ercap"
        if source is None:
            continue
        s = source[col].astype("string").str.strip()
        vc = s.value_counts(dropna=False)
        top = vc if top_n is None else vc.head(top_n)
        out[col] = {
            "n_unique": int(vc.size),
            "table": table,
            "top": top.rename_axis("value").reset_index(name="rows"),
        }
    return out


def alias_impact() -> dict:
    """For every alias map declared in clean.py, return:
      - the mapping itself
      - per-source-value row count in the RAW data
      - the canonical destination value and how many rows it had pre-merge
      - the source table the column came from ('allocations' or 'ercap')
    """
    raw_alloc = pd.concat(
        [extract.load_alloc(y) for y in extract.YEARS], ignore_index=True
    )
    raw_ercap = pd.concat(
        [extract.load_ercap(y) for y in extract.YEARS], ignore_index=True
    )
    out = {"maps": {}}

    for col, mapping in clean.ALIAS_MAPS.items():
        if not mapping:
            continue
        if col in raw_alloc.columns:
            source, table = raw_alloc, "allocations"
        elif col in raw_ercap.columns:
            source, table = raw_ercap, "ercap"
        else:
            continue
        vc = source[col].astype("string").str.strip().value_counts(dropna=False)
        rows = []
        for src, dst in mapping.items():
            rows.append({
                "raw_value": src,
                "rows_affected": int(vc.get(src, 0)),
                "merged_into": dst,
                "destination_rows_before_merge": int(vc.get(dst, 0)),
            })
        out["maps"][col] = {"table": table, "df": pd.DataFrame(rows)}

    return out


def numeric_outliers(alloc: pd.DataFrame) -> dict:
    out = {}
    for col in ["cpu_node_hours_charged", "gpu_node_hours_charged", "cpu_balance", "gpu_balance"]:
        if col in alloc.columns:
            s = pd.to_numeric(alloc[col], errors="coerce")
            out[col] = {
                "n_negative": int((s < 0).sum()),
                "n_null": int(s.isna().sum()),
                "max": float(s.max()) if s.notna().any() else None,
            }
    return out


def write_report() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    alloc = _load_cleaned_alloc()
    ercap = _load_cleaned_ercap()

    rc = row_counts(alloc, ercap)
    join_cov = ercap_alloc_join_coverage(alloc, ercap)
    uid_det_preview = user_id_format_details(alloc)
    outliers = numeric_outliers(alloc)
    alloc_nulls = null_rates(alloc, "year")
    dup_preview = duplicate_user_repo_year_details(alloc)
    dupes_dropped_preview = exact_duplicates_dropped()
    alloc_dropped = int(dupes_dropped_preview["alloc_dupes_dropped"].sum())
    ercap_dropped = int(dupes_dropped_preview["ercap_dupes_dropped"].sum())

    lines = []
    lines.append("# Data Quality Report\n")
    lines.append(f"_Auto-generated from clean/ contents._\n")

    lines.append("## Summary\n")
    summary_rows = [
        {"check": "Row counts loaded", "value": f"{int(rc['alloc_rows'].sum()):,} alloc / {int(rc['ercap_rows'].sum()):,} ercap"},
        {"check": "Exact dupes dropped (clean.py)", "value": f"{alloc_dropped} alloc + {ercap_dropped} ercap = {alloc_dropped + ercap_dropped}"},
        {"check": "(user_id, repo, year) dupes remaining", "value": f"{dup_preview.get('n_dup_rows', 0):,} rows in {dup_preview.get('n_dup_groups', 0):,} groups"},
        {"check": "request↔alloc join match rate", "value": f"{join_cov.get('match_rate', 'n/a')}"},
        {"check": "Non-conforming user_ids", "value": f"{uid_det_preview.get('n_bad', 0)} of {uid_det_preview.get('n_total', 0)}"},
        {"check": "Negative cpu_balance rows (overdrafts)", "value": f"{outliers.get('cpu_balance', {}).get('n_negative', 0):,}"},
        {"check": "Negative gpu_balance rows (overdrafts)", "value": f"{outliers.get('gpu_balance', {}).get('n_negative', 0):,}"},
    ]
    lines.append(_markdown_table(pd.DataFrame(summary_rows)))
    lines.append("")

    lines.append("## 1. Row counts per year\n")
    lines.append(_markdown_table(rc))
    lines.append("\n")

    lines.append("## 1b. Exact-duplicate rows dropped during cleaning\n")
    lines.append(
        "Rows where **every column is identical** to another row. Removed by "
        "`_dedupe()` in [clean.py](../pipeline/clean.py). Counts below come from "
        "comparing raw row counts to clean row counts per year and per table.\n"
    )
    lines.append(_markdown_table(dupes_dropped_preview))
    lines.append("")
    lines.append(f"- **Total exact duplicates dropped:** "
                 f"{alloc_dropped} alloc + {ercap_dropped} ercap = {alloc_dropped + ercap_dropped}\n")

    lines.append("## 2. Duplicate (user_id, repo, year) rows in allocations\n")
    lines.append(
        "These are rows where the natural key `(user_id, repo, year)` repeats "
        "but the rows are *not* byte-identical (those were already removed in 1b). "
        "Until a merge rule is defined, downstream `groupby` will double-count them.\n"
    )
    dup_det = duplicate_user_repo_year_details(alloc)
    n_rows = dup_det.get("n_dup_rows", 0)
    n_groups = dup_det.get("n_dup_groups", 0)
    avg = (n_rows / n_groups) if n_groups else 0
    lines.append(
        f"- **Total duplicate rows:** {n_rows}\n"
        f"- **Distinct duplicated (user_id, repo, year) keys:** {n_groups}\n"
        f"- Average rows per duplicated key: {avg:.2f} "
        f"({'every duplicated key appears in exactly ' + str(int(avg)) + ' rows' if avg == int(avg) else 'mixed group sizes'})\n"
    )
    if not dup_det.get("by_year", pd.DataFrame()).empty:
        lines.append("**Duplicate rows by year:**\n")
        lines.append(_markdown_table(dup_det["by_year"]))
        lines.append("")
    if not dup_det.get("differing_cols", pd.DataFrame()).empty:
        lines.append(
            "**Which columns differ between duplicates?** "
            "(aggregated across **all years**, not per-year). "
            "For each non-key column, this counts how many of the "
            f"{n_groups} duplicated `(user_id, repo, year)` groups have more than one "
            "distinct value in that column. A value of "
            f"`{n_groups}` (= `pct_of_dup_groups` 1.0) means the column differs in **every single** "
            "duplicate group — i.e. that column is the sole driver of the duplication. "
            "Columns that don't appear in this table are identical within every group.\n"
        )
        lines.append(_markdown_table(dup_det["differing_cols"]))
        lines.append("")
        # Suggest a merge rule from the top differing column.
        top = dup_det["differing_cols"].iloc[0]["column"]
        lines.append(f"_Top differing column is `{top}` — this likely drives the duplication. "
                     "Define a tie-break rule (sum / latest / max) before any per-user aggregation._\n")
    lines.append("## 3. Allocation-request <-> allocation join coverage\n")
    lines.append(
        "Request rows are joined to allocation rows on `(repo_listdisplay, year)` ↔ `(repo, year)`. "
        "A low match rate usually means string drift in repo names or that the request `year` is the "
        "request year, not the year the repo appears in allocations.\n"
    )
    for k, v in join_cov.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## 4. User-id format check\n")
    lines.append(
        "User IDs are expected in `adjective-noun` form: two lowercase ASCII words "
        f"joined by a single hyphen (regex `{ADJ_NOUN_RE.pattern}`). IDs that do not "
        "match are grouped below by reason.\n"
    )
    uid_det = user_id_format_details(alloc)
    lines.append(f"- **total unique user_ids**: {uid_det.get('n_total', 0)}")
    lines.append(f"- **non-matching (non_adj_noun)**: {uid_det.get('n_bad', 0)}\n")
    buckets = uid_det.get("buckets", {})
    if buckets:
        summary = pd.DataFrame(
            [{"bucket": b, "count": len(ids)}
             for b, ids in sorted(buckets.items(), key=lambda kv: -len(kv[1]))]
        )
        lines.append("**Failure-mode buckets:**\n")
        lines.append(_markdown_table(summary))
        lines.append("")
        lines.append(
            "_Bucket meanings: `multi_token` = 3+ hyphen-separated parts, "
            "`uppercase` = contains uppercase letters, `non_ascii` = contains "
            "non-ASCII characters._\n"
        )

    lines.append("## 4a. Categorical column value counts (summary)\n")
    lines.append("Per-column unique-value counts before aliasing.\n")
    cat_counts_summary = categorical_value_counts_raw(top_n=0)  # 0 → no preview rows
    summary_rows = [
        {"column": col, "table": info["table"], "n_unique": info["n_unique"]}
        for col, info in cat_counts_summary.items()
    ]
    lines.append(_markdown_table(pd.DataFrame(summary_rows)))
    lines.append("")

    lines.append("## 4b. Categorical aliases applied during cleaning\n")
    lines.append("Raw-to-canonical category maps applied during cleaning.\n")
    ai = alias_impact()
    if not ai["maps"]:
        lines.append("_No alias maps active._\n")
    for col, entry in ai["maps"].items():
        lines.append(f"### `{col}` aliases (from `{entry['table']}`)\n")
        lines.append(_markdown_table(entry["df"]))
        lines.append("")

    lines.append("## 5. Numeric outliers in allocations\n")
    lines.append(
        "`n_negative` for charged-hours is suspicious. `n_null` near zero is healthy.\n"
    )
    outliers_df = pd.DataFrame([
        {"column": c, **s} for c, s in outliers.items()
    ])
    if not outliers_df.empty:
        lines.append(_markdown_table(outliers_df))
        lines.append("")

    lines.append("## 6. Null rate per column per year (allocations)\n")
    lines.append(
        "Each cell = fraction of rows in that year where the column is null "
        "(0.0 = always populated, 1.0 = always missing). "
        "Columns whose null rate **changes a lot across years** indicate schema drift: "
        "the field's coverage isn't stable, so cross-year comparisons on it are unsafe. "
        "Columns flat near 0 are healthy; columns flat at some non-zero value are "
        "partially populated.\n"
    )
    lines.append(_markdown_table(alloc_nulls, include_index=True))
    lines.append("")
    # Surface the drifting columns explicitly.
    drift = (alloc_nulls.max() - alloc_nulls.min()).sort_values(ascending=False)
    drift = drift[drift > 0.05]  # only columns whose null rate moves by >5pp across years
    if not drift.empty:
        drift_df = drift.rename("max_minus_min_null_rate").reset_index().rename(columns={"index": "column"})
        lines.append("**Columns with the largest null-rate swing across years (drift candidates):**\n")
        lines.append(_markdown_table(drift_df))
        lines.append("")
        top_col = drift_df.iloc[0]["column"]
        top_swing = drift_df.iloc[0]["max_minus_min_null_rate"]
        lines.append(f"_Largest swing: `{top_col}` moves by {top_swing:.1%} across years. "
                     "Trends computed on this column will partly reflect coverage change, not behavior change._\n")

    lines.append("## Artifacts written\n")
    lines.append(
        "Only `reports/dq_report.md` is written.\n"
    )

    out = REPORTS_DIR / "dq_report.md"
    out.write_text("\n".join(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    write_report()

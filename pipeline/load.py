"""Load: take the clean CSVs and 
(a) compute graph feature tables, then
(b) materialise everything into a DuckDB file with constraints, a
per-project lead-user history table, a small view library, and an invariant
check.

Outputs:
    clean/alloc_repo_year_features.csv   per-(repo, year) network features
    clean/alloc_user_year_features.csv   per-(user, year) activity
    clean/ercap_repo_year_features.csv   per-(repo, year) request aggregates
    clean/nersc.duckdb                   single-file DB with tables + views

Run via `python -m pipeline.run` (run.py chains extract → clean → validate → load)
or standalone via `python -m pipeline.load`.
"""

from __future__ import annotations

import time

import networkx as nx
import pandas as pd

from pipeline import extract, io as cleaned_io
from pipeline.io import CLEANED_DIR, SQL_DIR, DB_PATH


import sys
sys.path.append(str(extract.REPO_ROOT))
from nersc_graphs import generate_graph


# ---------------------------------------------------------------------------
# 1. Feature tables
# ---------------------------------------------------------------------------

def _load_alloc_all() -> pd.DataFrame:
    return cleaned_io.read_all_allocations()


def build_alloc_repo_year_features(alloc: pd.DataFrame, betweenness_sample: int = 500) -> pd.DataFrame:
    """For each (repo, year), compute network metrics on the repo-repo
    projection of the user-repo bipartite graph.
    """
    rows = []
    for y in extract.YEARS:
        df_y = alloc[alloc["year"] == y]
        if df_y.empty:
            continue
        G, _ = generate_graph(df_y, node_name="repo", edge_name="user_id")
        n = G.number_of_nodes()
        if n == 0:
            continue
        k = min(betweenness_sample, n)
        btw = nx.betweenness_centrality(G, weight="weight", k=k, seed=42)
        try:
            pr = nx.pagerank(G, weight="weight")
        except Exception:
            pr = {node: 0.0 for node in G.nodes()}
        clu = nx.clustering(G, weight="weight")
        kcore = nx.core_number(G)
        for node in G.nodes():
            rows.append({
                "repo": node,
                "year": y,
                "degree": int(G.degree(node)),
                "weighted_degree": float(G.degree(node, weight="weight")),
                "betweenness": float(btw.get(node, 0.0)),
                "pagerank": float(pr.get(node, 0.0)),
                "clustering": float(clu.get(node, 0.0)),
                "k_core": int(kcore.get(node, 0)),
                "n_users": int(G.nodes[node].get("weight", 0)),
            })
        print(f"  repo features {y}: {n:,} nodes, {G.number_of_edges():,} edges")
    return pd.DataFrame(rows)


def build_ercap_repo_year_features(ercap: pd.DataFrame) -> pd.DataFrame:
    """Per-(repo, year) allocation-request aggregates. Request rows are
    one-per-request; `repo_listdisplay` is the repo identifier on this side
    (allocations use `repo`).
    """
    if "repo_listdisplay" not in ercap.columns:
        return pd.DataFrame()
    year_col = "year" if "year" in ercap.columns else "source_file_year"

    e = ercap.copy()

    agg_spec = {}
    for col in ["hours_requested", "hours_used",
                "gpu_requested", "gpu_used",
                "storage_requested", "storage_used"]:
        if col in e.columns:
            agg_spec[col] = (col, "sum")
    agg_spec["n_requests"] = ("repo_listdisplay", "size")

    df = (e.groupby(["repo_listdisplay", year_col], dropna=False)
            .agg(**agg_spec)
            .reset_index()
            .rename(columns={"repo_listdisplay": "repo", year_col: "year"}))
    return df


def build_alloc_user_year_features(alloc: pd.DataFrame) -> pd.DataFrame:
    """Non-graph per-(user, year) metrics."""
    g = alloc.groupby(["user_id", "year"])
    df = g.agg(
        n_repos=("repo", "nunique"),
        n_offices_touched=("office", "nunique"),
        n_science_cats=("science_category", "nunique"),
        total_cpu_hours=("cpu_node_hours_charged", "sum"),
        total_gpu_hours=("gpu_node_hours_charged", "sum"),
    ).reset_index()
    denom = (df["total_cpu_hours"] + df["total_gpu_hours"]).replace(0, pd.NA)
    df["gpu_share"] = df["total_gpu_hours"] / denom
    return df


# ---------------------------------------------------------------------------
# 2. DuckDB layer
# ---------------------------------------------------------------------------

def _ensure_duckdb():
    try:
        import duckdb  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "duckdb not installed. Run: pip install duckdb"
        ) from e


def load_into_duckdb() -> None:
    """Create clean/nersc.duckdb with all tables, lead-user history, and views.
    """
    _ensure_duckdb()
    import duckdb

    if DB_PATH.exists():
        DB_PATH.unlink()  # fresh build each pipeline run
    con = duckdb.connect(str(DB_PATH))

    # Clean tables (CSV → DuckDB).
    con.execute(f"""
        CREATE OR REPLACE TABLE allocations AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/allocations.csv');
        CREATE OR REPLACE TABLE ercap AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/ercap.csv');
        CREATE OR REPLACE TABLE users AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/users.csv');
        CREATE OR REPLACE TABLE repos AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/repos.csv');
        CREATE OR REPLACE TABLE alloc_repo_year_features AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/alloc_repo_year_features.csv');
        CREATE OR REPLACE TABLE alloc_user_year_features AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/alloc_user_year_features.csv');
        CREATE OR REPLACE TABLE ercap_repo_year_features AS
          SELECT * FROM read_csv_auto('{CLEANED_DIR}/ercap_repo_year_features.csv');
    """)

    # Per-project lead-user history. Each row = a contiguous span of years
    # during which one lead user (pi_user_id) was recorded for the project.
    con.execute("""
        CREATE OR REPLACE TABLE repo_pi_history AS
        WITH distinct_pi AS (
          SELECT DISTINCT repo, pi_user_id, year
          FROM allocations
          WHERE pi_user_id IS NOT NULL
        ),
        ordered AS (
          SELECT repo, pi_user_id, year,
                 LAG(pi_user_id) OVER (PARTITION BY repo ORDER BY year) AS prev_pi
          FROM distinct_pi
        ),
        change_flags AS (
          SELECT *,
                 CASE WHEN prev_pi IS NULL OR prev_pi <> pi_user_id THEN 1 ELSE 0 END
                 AS new_span
          FROM ordered
        ),
        spans AS (
          SELECT repo, pi_user_id, year,
                 SUM(new_span) OVER (PARTITION BY repo ORDER BY year) AS span_id
          FROM change_flags
        )
        SELECT repo,
               pi_user_id,
               MIN(year) AS valid_from_year,
               MAX(year) AS valid_to_year
        FROM spans
        GROUP BY repo, pi_user_id, span_id
        ORDER BY repo, valid_from_year;
    """)

    # Views (loaded from sql/views.sql if present, else inlined).
    views_path = SQL_DIR / "views.sql"
    if views_path.exists():
        con.execute(views_path.read_text())
    else:
        con.execute(_INLINE_VIEWS_SQL)

    # Invariants — every check should return 0 rows. If any fail, raise.
    failures = run_invariants(con)
    if failures:
        for name, n in failures.items():
            print(f"  INVARIANT FAILED: {name} -> {n} offending rows")
        raise SystemExit("Invariant checks failed. See above.")

    print(f"DuckDB built at {DB_PATH}")
    con.close()


# Fallback if sql/views.sql is missing. The same SQL is checked in there.
_INLINE_VIEWS_SQL = """
CREATE OR REPLACE VIEW v_repo_year_metrics AS
SELECT a.repo, a.year,
       SUM(a.cpu_node_hours_charged) AS total_cpu_hours,
       SUM(a.gpu_node_hours_charged) AS total_gpu_hours,
       SUM(a.gpu_node_hours_charged) /
         NULLIF(SUM(a.cpu_node_hours_charged) + SUM(a.gpu_node_hours_charged), 0)
         AS gpu_share,
       COUNT(DISTINCT a.user_id) AS n_users,
       ANY_VALUE(a.office) AS office,
       ANY_VALUE(a.science_category) AS science_category,
       f.degree, f.weighted_degree, f.betweenness, f.pagerank,
       f.clustering, f.k_core,
       e.hours_requested, e.hours_used,
       e.gpu_requested,   e.gpu_used,
       e.storage_requested, e.storage_used,
       e.n_requests
FROM allocations a
LEFT JOIN alloc_repo_year_features f USING (repo, year)
LEFT JOIN ercap_repo_year_features e USING (repo, year)
GROUP BY a.repo, a.year,
         f.degree, f.weighted_degree, f.betweenness, f.pagerank,
         f.clustering, f.k_core,
         e.hours_requested, e.hours_used, e.gpu_requested, e.gpu_used,
         e.storage_requested, e.storage_used,
         e.n_requests;

CREATE OR REPLACE VIEW v_pi_succession AS
SELECT repo,
       COUNT(*) - 1 AS n_pi_changes,
       MIN(valid_from_year) AS first_year,
       MAX(valid_to_year) AS last_year
FROM repo_pi_history
GROUP BY repo;

CREATE OR REPLACE VIEW v_user_office_span AS
SELECT user_id, year,
       COUNT(DISTINCT office) AS n_offices_touched,
       COUNT(DISTINCT repo)   AS n_repos
FROM allocations
GROUP BY user_id, year;

CREATE OR REPLACE VIEW v_resource_concentration AS
SELECT office, year,
       SUM(cpu_node_hours_charged) AS office_cpu,
       SUM(gpu_node_hours_charged) AS office_gpu,
       COUNT(DISTINCT repo)        AS n_repos,
       COUNT(DISTINCT user_id)     AS n_users
FROM allocations
GROUP BY office, year;

CREATE OR REPLACE VIEW v_engagement_tier AS
WITH active AS (
  SELECT user_id, year,
         SUM(cpu_node_hours_charged + gpu_node_hours_charged) AS total_hours,
         BOOL_OR(user_id = pi_user_id) AS is_pi
  FROM allocations
  GROUP BY user_id, year
),
quartiles AS (
  SELECT year,
         quantile_cont(total_hours, 0.25) AS p25,
         quantile_cont(total_hours, 0.75) AS p75
  FROM active
  WHERE total_hours > 0
  GROUP BY year
)
SELECT a.user_id, a.year, a.total_hours, a.is_pi,
       CASE
         WHEN a.total_hours = 0 THEN 'peripheral'
         WHEN a.total_hours < q.p25 THEN 'casual'
         WHEN a.total_hours < q.p75 THEN 'active'
         ELSE 'core'
       END AS tier
FROM active a JOIN quartiles q USING (year);

CREATE OR REPLACE VIEW v_active_repos AS
SELECT year, repo, COUNT(DISTINCT user_id) AS n_active_users
FROM allocations
WHERE cpu_node_hours_charged + gpu_node_hours_charged > 0
GROUP BY year, repo;
"""


def run_invariants(con) -> dict:
    """Each named SQL should return 0 rows. Returns {name: row_count} of failures."""
    checks = {
        "alloc_has_negative_charged_cpu":
            "SELECT * FROM allocations WHERE cpu_node_hours_charged < 0",
        "alloc_has_negative_charged_gpu":
            "SELECT * FROM allocations WHERE gpu_node_hours_charged < 0",
        "user_id_null_in_alloc":
            "SELECT * FROM allocations WHERE user_id IS NULL",
        "repo_null_in_alloc":
            "SELECT * FROM allocations WHERE repo IS NULL",
        "pi_history_orphan":
            """SELECT * FROM repo_pi_history h
               WHERE NOT EXISTS (SELECT 1 FROM allocations a
                                  WHERE a.repo = h.repo
                                    AND a.pi_user_id = h.pi_user_id)""",
    }
    failures = {}
    for name, q in checks.items():
        n = con.execute(f"SELECT COUNT(*) FROM ({q})").fetchone()[0]
        if n > 0:
            failures[name] = n
    return failures


# ---------------------------------------------------------------------------
# Entry point used by run.py
# ---------------------------------------------------------------------------

def write_features_and_load_db() -> None:
    CLEANED_DIR.mkdir(exist_ok=True)
    alloc = _load_alloc_all()
    ercap = cleaned_io.read_all_ercap()

    print("Building alloc user-year features...")
    user_feat = build_alloc_user_year_features(alloc)
    cleaned_io.write_alloc_user_year_features(user_feat)
    print(f"  wrote alloc_user_year_features.csv ({len(user_feat):,} rows)")

    print("Building ercap repo-year features...")
    ercap_feat = build_ercap_repo_year_features(ercap)
    cleaned_io.write_ercap_repo_year_features(ercap_feat)
    print(f"  wrote ercap_repo_year_features.csv ({len(ercap_feat):,} rows)")

    print("Building alloc repo-year graph features...")
    t0 = time.time()
    repo_feat = build_alloc_repo_year_features(alloc)
    cleaned_io.write_alloc_repo_year_features(repo_feat)
    print(f"  wrote alloc_repo_year_features.csv ({len(repo_feat):,} rows) in {time.time()-t0:.1f}s")

    print("Loading into DuckDB and building lead-user history + views...")
    load_into_duckdb()


if __name__ == "__main__":
    write_features_and_load_db()

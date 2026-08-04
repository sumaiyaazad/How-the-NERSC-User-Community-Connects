# Data Dictionary

This file summarizes the tables the pipeline produces. Each table keeps only the
columns used by the network analysis; personal information, institution names,
and addresses are omitted.

Each table is written to the generated `clean/` directory and
is described below by name, with its filename in parentheses.

## Allocations (`allocations.csv`)

One row per user-project allocation for a given year: which users are on each
project, plus the CPU and GPU node-hours they were charged. This is the
user-level table.

| Column | Meaning |
|---|---|
| `repo` | Project code |
| `pi_user_id` | Project-lead handle |
| `user_id` | User handle |
| `office` | Funding office |
| `science_category` | Science category |
| `cpu_node_hours_charged` | CPU node-hours used |
| `gpu_node_hours_charged` | GPU node-hours used |
| `year` | Source year |

## Allocation requests (`ercap.csv`)

One row per project request for a given year: the CPU, GPU, and storage a
project requested and used. Unlike `allocations`, this is recorded per request
at the project level, not per user.

| Column | Meaning |
|---|---|
| `year` | Allocation year |
| `repo_listdisplay` | Project code as listed on the allocation-request side |
| `hours_requested` | CPU node-hours requested |
| `hours_used` | CPU node-hours used |
| `gpu_requested` | GPU node-hours requested |
| `gpu_used` | GPU node-hours used |
| `storage_requested` | Project storage requested |
| `storage_used` | Project storage used |
| `source_file_year` | Source file year |

## Users (`users.csv`)

One row per user.

| Column | Meaning |
|---|---|
| `user_id` | User handle |
| `tenure` | Number of active years |
| `n_repos_lifetime` | Number of projects joined |

## Projects (`repos.csv`)

One row per project.

| Column | Meaning |
|---|---|
| `repo` | Project code |
| `office` | Most common office |
| `science_category` | Most common science category |
| `n_users_lifetime` | Number of users on the project |

## Feature Tables

The pipeline builds feature tables that are easier to join into notebooks and
SQL views.

| Table | Grain | Description |
|---|---|---|
| `alloc_user_year_features.csv` | user, year | User activity by year, including project count, office count, science-category count, CPU hours, GPU hours, and GPU share |
| `alloc_repo_year_features.csv` | project, year | Network features for each project, including degree, weighted degree, betweenness, centrality score, clustering, k-core, and user count |
| `ercap_repo_year_features.csv` | project, year | Allocation-request totals by project and year: requested/used CPU and GPU hours, storage requested/used, and a request count (`n_requests`) |

## DuckDB database (`nersc.duckdb`)

The pipeline can load the cleaned tables and feature tables into a local DuckDB
database with SQL views for common analyses.

| View | Grain | Description |
|---|---|---|
| `v_repo_year_metrics` | project, year | Usage totals, graph features, and allocation-request fields joined together |
| `v_pi_succession` | project | Project-lead change summary |
| `v_user_office_span` | user, year | Number of offices and projects touched by a user |
| `v_resource_concentration` | office, year | CPU/GPU usage and user/project counts by office |
| `v_engagement_tier` | user, year | User activity tier for each year |
| `v_active_repos` | project, year | Projects with nonzero usage |

# How NERSC Connects

*Reproducibility artifact for the SC 2026 poster "How NERSC Connects."*

How NERSC Connects over time is a Python and Jupyter workflow for studying how
NERSC allocation projects, users, and science programs connect across years. It
builds allocation tables, user-project bipartite graphs, and projected
project graphs, validation reports, and a local DuckDB database for exploratory
network analysis.

## Features

- Allocation cleaning pipeline: normalizes yearly allocation and allocation-request CSVs into analysis-ready tables.
- Network construction: builds user-project bipartite graphs and project-project projections from shared users.
- Data validation: reports duplicate keys, null-rate drift, user-name format checks, and cross-table coverage.
- Local analytics database: materializes the tables, feature tables, per-project lead-user history, and SQL views in DuckDB.
- Notebook analysis: includes notebooks for quickstart queries, database features, community structure, bridge projects, and liaison analysis.

## Repository Layout

- `pipeline/`: Extract, clean, validate, and load stages for the allocation workflow.
- `notebooks/`: Jupyter notebooks for exploration and analysis.
- `docs/`: Short data dictionary for the tables and derived features.
- `nersc_graphs.py`: Shared NetworkX and Plotly graph utilities.
- `sql/views.sql`: DuckDB views used by the loading step.
- `requirements.txt`: Python dependencies for the pipeline and notebooks.

## Data

Data used in the poster analysis contains potentially sensitive information about users of the supercomputing facility. 
Therefore, we are not including the actual data in this artifact.
`raw/` holds two small example inputs — one allocations file and one
allocation-request file — with the same column layout the pipeline expects.

Related Office of Science user statistics are published at:

```text
https://science.osti.gov/User-Facilities/User-Statistics
```

## Prerequisites

- Python 3.10 or newer.
- The Python packages listed in `requirements.txt`: pandas, numpy, matplotlib,
  seaborn, networkx, duckdb, and plotly.
- Jupyter (plus an IPython kernel) if you want to run the notebooks.

No external services, credentials, or network access are required. The pipeline
reads local inputs and writes local outputs only.

## Installation

Create and activate a Python environment, then install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For notebook work, install an IPython kernel if your environment does not
already provide one:

```bash
pip install ipykernel
python -m ipykernel install --user --name nersc-graphs --display-name "NERSC Graphs"
```

## Running the Pipeline

From the repository root:

```bash
python -m pipeline.run
```

This runs the full workflow:

1. normalizes the yearly inputs,
2. writes validation and data-quality reports,
3. builds graph feature tables,
4. creates a local DuckDB database.

Its outputs land in `clean/` and `reports/`, both git-ignored; only the `raw/`
inputs are tracked.

## Notebooks

The notebooks are intended to be run after `python -m pipeline.run` has
generated the outputs.

- `notebooks/quickstart.ipynb`: Basic loading and query examples.
- `notebooks/db_features.ipynb`: Exploration of DuckDB views and feature tables.
- `notebooks/network_analysis.ipynb`: Community, bridge, and liaison-style network analysis.



## Acknowledgements

Supported by the Computing Sciences Summer Program at NERSC, LBL. ​
Special thanks to Kevin Gott and Rebecca Hartman-Baker for mentorship, and to the NERSC User Engagement Group for framing the problem. ​

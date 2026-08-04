"""NERSC allocation graphs pipeline.

Stages:
    extract  -> load raw CSVs from raw/
    clean    -> normalize, dedupe, parse, write clean/*.csv
    validate -> data-quality checks, write reports/dq_report.md
    run      -> one-command rebuild

Outputs are plain CSVs.
"""

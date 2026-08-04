"""One-command rebuild: extract -> clean -> validate -> load.

Usage:
    python -m pipeline.run

Regenerates everything in clean/ and reports/, then materialises the
DuckDB file with feature tables, lead-user history, and views.
"""

from __future__ import annotations

from pipeline import clean, load, validate


def main() -> None:
    print("== Step 1/3: clean ==")
    clean.write_cleaned()
    print("== Step 2/3: validate ==")
    validate.write_report()
    print("== Step 3/3: load (features + DuckDB) ==")
    load.write_features_and_load_db()
    print("Done.")


if __name__ == "__main__":
    main()

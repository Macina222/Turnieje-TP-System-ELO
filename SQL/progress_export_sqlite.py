#!/usr/bin/env python3
"""Export pair ELO progress from official SQLite data to CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlite_ranking_service import build_ranking_from_sqlite, load_config, parse_years_arg, write_progress_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export TTP ELO progress from SQLite to CSV.")
    parser.add_argument("--db", required=True, help="Path to SQLite database, e.g. ttp_official.sqlite")
    parser.add_argument("--category", required=True, help="Base category, e.g. V, VI, III")
    parser.add_argument("--years", nargs="*", help="Years or ranges, e.g. 2024 2025 or 2021-2025")
    parser.add_argument("--classes", nargs="*", help="Optional class filter, e.g. B A S OPEN")
    parser.add_argument("--config", default="config.txt", help="Path to legacy config.txt")
    parser.add_argument("--output", default="progress_sqlite.csv", help="Output CSV path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(args.config)
    run = build_ranking_from_sqlite(
        db_path=args.db,
        category=args.category,
        years=parse_years_arg(args.years),
        classes=args.classes,
        config=config,
    )
    write_progress_csv(run, args.output)
    print(f"Saved progress CSV to: {args.output}")
    print(f"Rows: {len(run.progress_rows)}")


if __name__ == "__main__":
    main()

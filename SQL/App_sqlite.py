#!/usr/bin/env python3
"""CLI application for calculating TTP ELO ranking from SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root so ranking_config can be imported from SQL/ context
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlite_ranking_service import (
    build_ranking_from_sqlite,
    format_ranking_report,
    get_available_classes,
    get_available_years,
    load_config,
    parse_years_arg,
)
from ranking_config import DEFAULT_CONFIG_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate TTP ELO ranking from official SQLite data.")
    parser.add_argument("--db", required=True, help="Path to SQLite database, e.g. ttp_official.sqlite")
    parser.add_argument("--category", required=True, help="Base category, e.g. V, VI, III")
    parser.add_argument("--years", nargs="*", help="Years or ranges, e.g. 2024 2025 or 2021-2025")
    parser.add_argument("--classes", nargs="*", help="Optional class filter, e.g. B A S OPEN")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to legacy config.txt")
    parser.add_argument("--output", help="Optional output report path")
    parser.add_argument("--list-years", action="store_true", help="List available years and exit")
    parser.add_argument("--list-classes", action="store_true", help="List available classes for selected category/years and exit")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    db_path = Path(args.db)

    if args.list_years:
        print("Available years:", ", ".join(map(str, get_available_years(db_path))))
        return

    years = parse_years_arg(args.years)

    if args.list_classes:
        print("Available classes:", ", ".join(get_available_classes(db_path, args.category, years)))
        return

    config = load_config(args.config)
    run = build_ranking_from_sqlite(
        db_path=db_path,
        category=args.category,
        years=years,
        classes=args.classes,
        config=config,
    )
    report = format_ranking_report(run)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Saved ranking report to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

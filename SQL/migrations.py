#!/usr/bin/env python3
"""
Migration framework for SQLite backend.

Provides schema versioning and ordered migration execution.
Migrations are pure SQL scripts stored as module-level constants.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Current schema version - increment when adding new migrations
CURRENT_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Migration:
    """A single schema migration."""
    version: int
    name: str
    up_sql: str
    down_sql: str = ""  # Optional rollback (not used in production)


# ---------------------------------------------------------------------------
# MIGRATIONS - Add new migrations here, increment CURRENT_SCHEMA_VERSION
# ---------------------------------------------------------------------------

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="initial_schema",
        up_sql="""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS source_files (
            source_file_id INTEGER PRIMARY KEY,
            file_name TEXT NOT NULL,
            absolute_path TEXT,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_name, absolute_path)
        );

        CREATE TABLE IF NOT EXISTS dancers (
            dancer_id INTEGER PRIMARY KEY,
            full_name TEXT,
            normalized_name TEXT
        );

        CREATE TABLE IF NOT EXISTS pairs (
            pair_id INTEGER PRIMARY KEY,
            display_name TEXT,
            normalized_name TEXT
        );

        CREATE TABLE IF NOT EXISTS pair_members (
            pair_id INTEGER NOT NULL,
            dancer_id INTEGER NOT NULL,
            member_order INTEGER NOT NULL,
            PRIMARY KEY (pair_id, dancer_id),
            UNIQUE(pair_id, member_order),
            FOREIGN KEY (pair_id) REFERENCES pairs(pair_id),
            FOREIGN KEY (dancer_id) REFERENCES dancers(dancer_id)
        );

        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL UNIQUE,
            normalized_name TEXT
        );

        CREATE TABLE IF NOT EXISTS tournaments (
            tournament_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            tournament_code TEXT NOT NULL,
            tournament_name TEXT NOT NULL,
            UNIQUE(season, tournament_code)
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY,
            tournament_id INTEGER NOT NULL,
            cat_code TEXT NOT NULL,
            base_category TEXT,
            class_code TEXT,
            UNIQUE(tournament_id, cat_code),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
        );

        CREATE TABLE IF NOT EXISTS results (
            result_id INTEGER PRIMARY KEY,
            event_id INTEGER NOT NULL,
            pair_id INTEGER NOT NULL,
            group_id INTEGER,
            rank REAL NOT NULL,
            points_before REAL,
            points_awarded REAL,
            medals_awarded REAL,
            points_after REAL,
            medals_after REAL,
            source_file_id INTEGER NOT NULL,
            source_row_number INTEGER NOT NULL,
            raw_dancers_id TEXT,
            raw_pair_name TEXT,
            FOREIGN KEY (event_id) REFERENCES events(event_id),
            FOREIGN KEY (pair_id) REFERENCES pairs(pair_id),
            FOREIGN KEY (group_id) REFERENCES groups(group_id),
            FOREIGN KEY (source_file_id) REFERENCES source_files(source_file_id)
        );

        CREATE TABLE IF NOT EXISTS import_warnings (
            warning_id INTEGER PRIMARY KEY,
            source_file_id INTEGER NOT NULL,
            source_row_number INTEGER,
            warning_type TEXT NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY (source_file_id) REFERENCES source_files(source_file_id)
        );

        CREATE INDEX IF NOT EXISTS idx_results_event ON results(event_id);
        CREATE INDEX IF NOT EXISTS idx_results_pair ON results(pair_id);
        CREATE INDEX IF NOT EXISTS idx_events_cat ON events(cat_code, base_category, class_code);
        CREATE INDEX IF NOT EXISTS idx_tournaments_season ON tournaments(season);

        -- Schema version table (created last in initial migration)
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT OR IGNORE INTO schema_version (version, name) VALUES (1, 'initial_schema');
        """,
        down_sql="""
        DROP TABLE IF EXISTS import_warnings;
        DROP TABLE IF EXISTS results;
        DROP TABLE IF EXISTS events;
        DROP TABLE IF EXISTS tournaments;
        DROP TABLE IF EXISTS groups;
        DROP TABLE IF EXISTS pair_members;
        DROP TABLE IF EXISTS pairs;
        DROP TABLE IF EXISTS dancers;
        DROP TABLE IF EXISTS source_files;
        DROP TABLE IF EXISTS schema_version;
        """,
    ),
    Migration(
        version=2,
        name="add_event_date_to_tournaments",
        up_sql="""
        -- Add event_date column to tournaments table for proper chronological ordering
        ALTER TABLE tournaments ADD COLUMN event_date TEXT;

        -- Create index for date-based queries
        CREATE INDEX IF NOT EXISTS idx_tournaments_event_date ON tournaments(event_date);

        -- Record migration
        INSERT OR IGNORE INTO schema_version (version, name) VALUES (2, 'add_event_date_to_tournaments');
        """,
        down_sql="""
        -- SQLite doesn't support DROP COLUMN directly; would need table rebuild
        -- This is a one-way migration in practice
        DELETE FROM schema_version WHERE version = 2;
        """,
    ),
]


def get_current_version(db_path: str | Path) -> int:
    """Get the current schema version of the database."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Check if schema_version table exists
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if not table_exists:
            return 0
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] if row[0] is not None else 0


def run_migrations(db_path: str | Path, target_version: int | None = None) -> list[int]:
    """
    Run pending migrations up to target_version (or CURRENT_SCHEMA_VERSION).

    Returns list of applied migration versions.
    """
    target = target_version or CURRENT_SCHEMA_VERSION
    current = get_current_version(db_path)

    if current >= target:
        return []

    applied = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for migration in MIGRATIONS:
            if migration.version <= current:
                continue
            if migration.version > target:
                break

            print(f"Applying migration {migration.version}: {migration.name}")
            conn.executescript(migration.up_sql)
            applied.append(migration.version)

        conn.commit()

    return applied


def ensure_schema(db_path: str | Path, target_version: int | None = None) -> None:
    """
    Ensure database schema is up to date.

    Creates schema_version table and runs all pending migrations.
    Should be called at application startup before any other DB operations.
    """
    run_migrations(db_path, target_version)


def get_applied_migrations(db_path: str | Path) -> list[tuple[int, str, str]]:
    """Get list of applied migrations with version, name, and applied_at."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_version ORDER BY version"
        ).fetchall()
        return [(r["version"], r["name"], r["applied_at"]) for r in rows]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run SQLite migrations")
    parser.add_argument("db", type=Path, help="Path to SQLite database")
    parser.add_argument("--target", type=int, help="Target version (default: latest)")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    if args.status:
        current = get_current_version(args.db)
        applied = get_applied_migrations(args.db)
        print(f"Current version: {current}")
        print(f"Target version: {CURRENT_SCHEMA_VERSION}")
        print("Applied migrations:")
        for version, name, applied_at in applied:
            print(f"  v{version}: {name} ({applied_at})")
        if current < CURRENT_SCHEMA_VERSION:
            print(f"\nPending migrations: {CURRENT_SCHEMA_VERSION - current}")
        exit(0)

    applied = run_migrations(args.db, args.target)
    if applied:
        print(f"Applied migrations: {applied}")
    else:
        print("No migrations to apply (already up to date)")
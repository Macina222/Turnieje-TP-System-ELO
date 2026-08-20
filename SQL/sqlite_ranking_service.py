#!/usr/bin/env python3
"""SQLite backend for Turnieje TP ELO ranking.

This module reads official TTP data imported with import_official_ttp_to_sqlite.py
and exposes the same kind of outputs as the file-based prototype:
- final ranking report
- pair-by-pair ELO progress rows

It deliberately treats official pair_id/dancer_id values as the source of truth.
"""

from __future__ import annotations

import math
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

# Unified config module (P1) - used by both XLSX and SQLite backends
# Add project root to sys.path so ranking_config can be imported from SQL/ context
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ranking_config import EloConfig, load_config


@dataclass
class PairRating:
    pair_id: int
    display_name: str
    rating: float
    events_count: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    last_group: Optional[str] = None
    last_category: Optional[str] = None
    last_class: Optional[str] = None


@dataclass(frozen=True)
class EventMeta:
    event_id: int
    tournament_id: int
    season: int
    tournament_code: str
    tournament_name: str
    cat_code: str
    base_category: str
    class_code: Optional[str]
    source_order: int
    event_date: Optional[str] = None


@dataclass(frozen=True)
class EventResult:
    result_id: int
    event_id: int
    pair_id: int
    pair_name: str
    group_name: Optional[str]
    rank: float


@dataclass
class RankingRun:
    category: str
    years: list[int]
    classes: list[str]
    processed_events: list[EventMeta] = field(default_factory=list)
    ratings: dict[int, PairRating] = field(default_factory=dict)
    progress_rows: list[dict] = field(default_factory=list)
    skipped_events: list[str] = field(default_factory=list)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def normalize_classes(classes: Optional[Sequence[str]]) -> list[str]:
    if not classes:
        return []
    out = []
    for cls in classes:
        if cls is None:
            continue
        item = str(cls).strip().upper()
        if item and item not in out:
            out.append(item)
    return out


def parse_years_arg(years: Optional[Sequence[str | int]]) -> list[int]:
    if not years:
        return []
    parsed: set[int] = set()
    for item in years:
        text = str(item).strip()
        if not text:
            continue
        if "-" in text:
            start, end = text.split("-", 1)
            start_i, end_i = int(start), int(end)
            if end_i < start_i:
                start_i, end_i = end_i, start_i
            parsed.update(range(start_i, end_i + 1))
        else:
            parsed.add(int(text))
    return sorted(parsed)


def get_available_years(db_path: str | Path) -> list[int]:
    with _connect(db_path) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT season FROM tournaments ORDER BY season")]


def get_available_categories_sqlite(db_path: str | Path, years: Optional[Sequence[int]] = None) -> list[str]:
    """Return base categories available in the DB for given years."""
    params: list[object] = []
    where = []
    if years:
        placeholders = ",".join("?" for _ in years)
        where.append(f"t.season IN ({placeholders})")
        params.extend(years)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT DISTINCT e.base_category
        FROM events e
        JOIN tournaments t ON t.tournament_id = e.tournament_id
        {where_clause}
        ORDER BY e.base_category
    """
    with _connect(db_path) as con:
        return [r[0] for r in con.execute(sql, params)]


def get_available_classes(db_path: str | Path, category: str, years: Optional[Sequence[int]] = None) -> list[str]:
    category = category.upper()
    params: list[object] = [category]
    where = ["e.base_category = ?"]
    if years:
        placeholders = ",".join("?" for _ in years)
        where.append(f"t.season IN ({placeholders})")
        params.extend(years)
    sql = f"""
        SELECT DISTINCT COALESCE(e.class_code, '') AS class_code
        FROM events e
        JOIN tournaments t ON t.tournament_id = e.tournament_id
        WHERE {' AND '.join(where)}
        ORDER BY class_code
    """
    with _connect(db_path) as con:
        classes = []
        for r in con.execute(sql, params):
            classes.append(r["class_code"] or "bez_sufiksu")
        return classes


def fetch_events(
    db_path: str | Path,
    category: str,
    years: Optional[Sequence[int]] = None,
    classes: Optional[Sequence[str]] = None,
) -> list[EventMeta]:
    """Return events in deterministic processing order.

    Order preference:
    1. event_date (if populated) - most accurate for chronological order
    2. season ascending + first source row order - fallback for official data
    """
    category = category.upper()
    classes_norm = normalize_classes(classes)

    params: list[object] = [category]
    where = ["e.base_category = ?"]

    if years:
        placeholders = ",".join("?" for _ in years)
        where.append(f"t.season IN ({placeholders})")
        params.extend(years)

    if classes_norm:
        class_conditions = []
        for cls in classes_norm:
            if cls in {"", "BEZ_SUФIKSU", "BEZ_SUFIKSU", "NONE", "NULL"}:
                class_conditions.append("e.class_code IS NULL")
            else:
                class_conditions.append("UPPER(e.class_code) = ?")
                params.append(cls)
        where.append("(" + " OR ".join(class_conditions) + ")")

    sql = f"""
        SELECT
            e.event_id,
            e.tournament_id,
            t.season,
            t.tournament_code,
            t.tournament_name,
            e.cat_code,
            e.base_category,
            e.class_code,
            MIN(r.source_row_number) AS source_order,
            t.event_date
        FROM events e
        JOIN tournaments t ON t.tournament_id = e.tournament_id
        JOIN results r ON r.event_id = e.event_id
        WHERE {' AND '.join(where)}
        GROUP BY e.event_id
        ORDER BY
            CASE WHEN t.event_date IS NOT NULL THEN 0 ELSE 1 END,
            t.event_date ASC,
            t.season ASC,
            source_order ASC,
            e.event_id ASC
    """
    with _connect(db_path) as con:
        return [EventMeta(**dict(r)) for r in con.execute(sql, params)]


def fetch_event_results(con: sqlite3.Connection, event_id: int) -> list[EventResult]:
    sql = """
        SELECT
            r.result_id,
            r.event_id,
            r.pair_id,
            COALESCE(p.display_name, r.raw_pair_name) AS pair_name,
            g.group_name,
            r.rank
        FROM results r
        JOIN pairs p ON p.pair_id = r.pair_id
        LEFT JOIN groups g ON g.group_id = r.group_id
        WHERE r.event_id = ?
        ORDER BY r.rank ASC, r.result_id ASC
    """
    return [EventResult(**dict(r)) for r in con.execute(sql, (event_id,))]


def expected_score(rating_a: float, rating_b: float, D: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / D))


def actual_score(rank_a: float, rank_b: float) -> float:
    if rank_a < rank_b:
        return 1.0
    if rank_a > rank_b:
        return 0.0
    return 0.5


def process_event(
    con: sqlite3.Connection,
    run: RankingRun,
    event: EventMeta,
    config: EloConfig,
) -> None:
    rows = fetch_event_results(con, event.event_id)
    if len(rows) < 2:
        run.skipped_events.append(
            f"{event.season} {event.tournament_name} {event.cat_code}: mniej niż 2 pary"
        )
        return

    # Initialize missing pairs before calculating this event, so every pair's
    # pre-event rating is frozen for all pairwise comparisons.
    for row in rows:
        if row.pair_id not in run.ratings:
            run.ratings[row.pair_id] = PairRating(
                pair_id=row.pair_id,
                display_name=row.pair_name,
                rating=config.default_for_class(event.class_code),
            )

    before = {row.pair_id: run.ratings[row.pair_id].rating for row in rows}
    deltas = {row.pair_id: 0.0 for row in rows}
    n = len(rows)
    effective_k = config.K / (n - 1)

    for a in rows:
        for b in rows:
            if a.pair_id == b.pair_id:
                continue
            actual = actual_score(a.rank, b.rank)
            expected = expected_score(before[a.pair_id], before[b.pair_id], config.D)
            deltas[a.pair_id] += actual - expected

    for row in rows:
        rating = run.ratings[row.pair_id]
        elo_before = before[row.pair_id]
        elo_delta = deltas[row.pair_id] * effective_k
        elo_after = elo_before + elo_delta

        rating.rating = elo_after
        rating.events_count += 1
        rating.last_group = row.group_name
        rating.last_category = event.base_category
        rating.last_class = event.class_code

        # Aggregate W/L/D from pairwise event outcomes.
        for other in rows:
            if other.pair_id == row.pair_id:
                continue
            actual = actual_score(row.rank, other.rank)
            if actual == 1.0:
                rating.wins += 1
            elif actual == 0.0:
                rating.losses += 1
            else:
                rating.draws += 1

        run.progress_rows.append(
            {
                "season": event.season,
                "tournament_code": event.tournament_code,
                "tournament_name": event.tournament_name,
                "event_id": event.event_id,
                "cat_code": event.cat_code,
                "base_category": event.base_category,
                "class_code": event.class_code or "",
                "rank": row.rank,
                "pair_id": row.pair_id,
                "pair": row.pair_name,
                "group": row.group_name or "",
                "punkty_przed": round(elo_before, 6),
                "punkty_po": round(elo_after, 6),
                "roznica_punktow": round(elo_delta, 6),
                "event_date": event.event_date or "",
            }
        )

    run.processed_events.append(event)


def build_ranking_from_sqlite(
    db_path: str | Path,
    category: str,
    years: Optional[Sequence[int]] = None,
    classes: Optional[Sequence[str]] = None,
    config: Optional[EloConfig] = None,
) -> RankingRun:
    config = config or load_config()
    category = category.upper()
    years_list = sorted([int(y) for y in years]) if years else get_available_years(db_path)
    classes_list = normalize_classes(classes)

    run = RankingRun(category=category, years=years_list, classes=classes_list)
    events = fetch_events(db_path, category, years_list, classes_list)

    with _connect(db_path) as con:
        for event in events:
            process_event(con, run, event, config)

    return run


def format_ranking_report(run: RankingRun) -> str:
    sorted_ratings = sorted(run.ratings.values(), key=lambda r: r.rating, reverse=True)
    classes_label = ", ".join(run.classes) if run.classes else "wszystkie dostępne"
    years_label = ", ".join(str(y) for y in run.years) if run.years else "wszystkie dostępne"
    subcats = sorted({event.cat_code for event in run.processed_events})

    lines = []
    lines.append(f"Ranking ELO — kategoria bazowa: {run.category}")
    lines.append(f"Lata: {years_label}")
    lines.append(f"Klasy: {classes_label}")
    lines.append(f"Liczba przetworzonych eventów: {len(run.processed_events)}")
    lines.append(f"Uwzględnione podkategorie: {', '.join(subcats) if subcats else '-'}")
    lines.append("")
    lines.append("Miejsce;Pair ID;Para;Ośrodek;ELO;Występy;Wygrane;Remisy;Porażki")

    for i, rating in enumerate(sorted_ratings, start=1):
        lines.append(
            ";".join(
                [
                    str(i),
                    str(rating.pair_id),
                    rating.display_name,
                    rating.last_group or "",
                    f"{rating.rating:.2f}",
                    str(rating.events_count),
                    str(rating.wins),
                    str(rating.draws),
                    str(rating.losses),
                ]
            )
        )

    if run.skipped_events:
        lines.append("")
        lines.append("Pominięte eventy:")
        lines.extend(f"- {item}" for item in run.skipped_events)

    return "\n".join(lines) + "\n"


def write_progress_csv(run: RankingRun, output_path: str | Path, delimiter: str = ";") -> None:
    import csv

    fieldnames = [
        "season",
        "tournament_code",
        "tournament_name",
        "event_date",
        "event_id",
        "cat_code",
        "base_category",
        "class_code",
        "rank",
        "pair_id",
        "pair",
        "group",
        "punkty_przed",
        "punkty_po",
        "roznica_punktow",
    ]
    with Path(output_path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(run.progress_rows)

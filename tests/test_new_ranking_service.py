from pathlib import Path
import tempfile
import unittest

import pandas as pd

from new_ranking_service import (
    build_new_progress_export,
    build_new_ranking,
    list_available_categories_for_years_xlsx,
    list_available_classes_for_category_and_years_xlsx,
    list_available_years_xlsx,
    load_xlsx_data,
)


def write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "K=50",
                "D=250",
                "defaulteloC=1000",
                "defaulteloB=1000",
                "defaulteloA=1000",
                "defaulteloS=1000",
                "defaulteloOPEN=1000",
            ]
        ),
        encoding="utf-8",
    )


def write_workbook(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_excel(path, index=False, startrow=3)


def create_sample_files(tmp_path: Path) -> tuple[Path, Path]:
    xlsx_path = tmp_path / "ranking_data.xlsx"
    config_path = tmp_path / "config.txt"
    write_config(config_path)
    write_workbook(
        xlsx_path,
        [
            {
                "season": 2025,
                "turnament code": "T2",
                "turnament name": "Second Tournament",
                "cat code": "VB",
                "pair id": 1,
                "pair": "PAIR ONE, DANCER A",
                "group": "",
                "rank": 2,
            },
            {
                "season": 2025,
                "turnament code": "T2",
                "turnament name": "Second Tournament",
                "cat code": "VB",
                "pair id": 2,
                "pair": "PAIR TWO, DANCER B",
                "group": "",
                "rank": 1,
            },
            {
                "season": 2024,
                "turnament code": "T1",
                "turnament name": "First Tournament",
                "cat code": "VA",
                "pair id": 1,
                "pair": "PAIR ONE, DANCER A",
                "group": "",
                "rank": 1,
            },
            {
                "season": 2024,
                "turnament code": "T1",
                "turnament name": "First Tournament",
                "cat code": "VA",
                "pair id": 2,
                "pair": "PAIR TWO, DANCER B",
                "group": "",
                "rank": 2,
            },
        ],
    )
    return xlsx_path, config_path


class NewRankingServiceTests(unittest.TestCase):
    def test_xlsx_discovery_finds_years_categories_and_classes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            xlsx_path, _ = create_sample_files(Path(raw_tmp))
            df = load_xlsx_data(xlsx_path)

            self.assertEqual(list_available_years_xlsx(df), [2024, 2025])
            self.assertEqual(
                list_available_categories_for_years_xlsx(df, [2025]),
                ["V"],
            )
            self.assertEqual(
                list_available_classes_for_category_and_years_xlsx(
                    df,
                    "V",
                    [2024, 2025],
                ),
                ["A", "B"],
            )

    def test_build_new_ranking_applies_filters_and_orders_by_elo(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            xlsx_path, config_path = create_sample_files(Path(raw_tmp))

            result = build_new_ranking(
                file_path=xlsx_path,
                years=[2025],
                category="V",
                classes=["B"],
                config_path=config_path,
            )

            self.assertEqual(result.category, "V")
            self.assertEqual(result.years, (2025,))
            self.assertEqual(result.included_categories, ("VB",))
            self.assertEqual(result.included_classes, ("B",))
            self.assertEqual(result.tournaments_processed, 1)
            self.assertEqual([entry.pair_id for entry in result.ranking], ["2", "1"])

    def test_build_new_progress_export_tracks_before_and_after_points(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            xlsx_path, config_path = create_sample_files(Path(raw_tmp))

            result = build_new_progress_export(
                file_path=xlsx_path,
                years=[2025],
                category="V",
                classes=["B"],
                config_path=config_path,
            )

            self.assertEqual(result.tournaments_processed, 1)
            self.assertEqual(len(result.rows), 2)
            winning_row = next(row for row in result.rows if row.pair_id == "2")
            self.assertAlmostEqual(winning_row.points_before, 1000.0)
            self.assertGreater(winning_row.points_after, winning_row.points_before)

    def test_load_xlsx_data_rejects_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            xlsx_path = Path(raw_tmp) / "bad.xlsx"
            write_workbook(xlsx_path, [{"season": 2025, "pair": "PAIR ONE, PAIR TWO"}])

            with self.assertRaisesRegex(ValueError, "wymaganych kolumn"):
                load_xlsx_data(xlsx_path)


if __name__ == "__main__":
    unittest.main()

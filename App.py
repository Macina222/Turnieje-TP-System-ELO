from __future__ import annotations

import argparse
from pathlib import Path

from ranking_service import (
    build_default_output_filename,
    build_ranking,
    format_ranking_report,
    list_available_categories_for_years,
    list_available_years,
    save_ranking_report,
)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


def parse_years_text(value: str, available_years: list[int]) -> list[int]:
    text = value.strip()
    if not text:
        raise ValueError("Nie podano lat.")

    lowered = text.lower()
    if lowered in {"all", "wszystkie", "*"}:
        return list(available_years)

    available_set = set(available_years)
    selected: set[int] = set()

    for chunk in text.replace(";", ",").split(","):
        part = chunk.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start > end:
                start, end = end, start
            for year in range(start, end + 1):
                selected.add(year)
            continue

        selected.add(int(part))

    invalid = sorted(year for year in selected if year not in available_set)
    if invalid:
        raise ValueError(
            "Niedostępne lata: " + ", ".join(str(year) for year in invalid)
        )

    return sorted(selected)


def parse_year_arguments(values: list[str] | None, available_years: list[int]) -> list[int]:
    if not values:
        return list(available_years)
    return parse_years_text(",".join(values), available_years)


def prompt_until_valid(prompt: str, parser) -> object:
    while True:
        raw_value = input(prompt).strip()
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Błąd: {exc}")


def prompt_for_years(available_years: list[int]) -> list[int]:
    print("Dostępne lata:")
    print(", ".join(str(year) for year in available_years))
    print("Wpisz np. 2024,2025 albo 2021-2025 albo all")
    return prompt_until_valid(
        "Lata do uwzględnienia: ",
        lambda value: parse_years_text(value, available_years),
    )


def prompt_for_category(categories: list[str]) -> str:
    print("Dostępne kategorie:")
    for index, category in enumerate(categories, start=1):
        print(f"{index}. {category}")

    def parse_category(value: str) -> str:
        text = value.strip().upper()
        if not text:
            raise ValueError("Nie podano kategorii.")
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(categories):
                return categories[index - 1]
            raise ValueError("Numer kategorii jest poza zakresem.")
        if text in categories:
            return text
        raise ValueError("Nieznana kategoria.")

    return prompt_until_valid("Kategoria (numer lub symbol): ", parse_category)


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[T/n]" if default else "[t/N]"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in {"t", "tak", "y", "yes"}


def run_cli_interactive(project_dir: Path) -> int:
    rsc_dir = project_dir / "rsc"
    available_years = list_available_years(rsc_dir)

    if not available_years:
        print("Nie znaleziono katalogów z latami w folderze rsc.")
        return 1

    selected_years = prompt_for_years(available_years)
    categories = list_available_categories_for_years(rsc_dir, selected_years)
    if not categories:
        print("Brak kategorii dla wybranych lat.")
        return 1

    selected_category = prompt_for_category(categories)
    result = build_ranking(selected_category, selected_years, rsc_dir)
    report = format_ranking_report(result)

    print()
    print(report)
    print()

    if prompt_yes_no("Zapisać ranking do pliku?", default=True):
        default_name = build_default_output_filename(result)
        suggested_path = project_dir / default_name
        target = input(
            f"Ścieżka zapisu [{suggested_path}]: "
        ).strip()
        output_path = Path(target) if target else suggested_path
        saved_path = save_ranking_report(report, output_path)
        print(f"Zapisano do: {saved_path}")

    return 0


def run_cli_from_args(args: argparse.Namespace, project_dir: Path) -> int:
    rsc_dir = project_dir / "rsc"
    available_years = list_available_years(rsc_dir)

    if not available_years:
        raise SystemExit("Nie znaleziono katalogów z latami w folderze rsc.")
    if not args.category:
        raise SystemExit("Podaj kategorię przez --category albo uruchom tryb interaktywny.")

    selected_years = parse_year_arguments(args.years, available_years)
    selected_category = args.category.strip().upper()
    report = format_ranking_report(
        build_ranking(selected_category, selected_years, rsc_dir)
    )

    print(report)

    if args.output:
        saved_path = save_ranking_report(report, args.output)
        print()
        print(f"Zapisano do: {saved_path}")

    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalkulator rankingu ELO dla plików rsc."
    )
    parser.add_argument(
        "--category",
        help="Kategoria bazowa rankingu, np. V albo III.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        help="Lata lub zakresy lat, np. 2024 2025 albo 2021-2025.",
    )
    parser.add_argument(
        "--output",
        help="Opcjonalna ścieżka pliku wyjściowego.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Wymuś tryb terminalowy nawet jeśli tkinter jest dostępny.",
    )
    return parser


if tk is not None:
    class RankingApp(tk.Tk):
        def __init__(self) -> None:
            super().__init__()

            self.title("Kalkulator rankingu ELO")
            self.geometry("1280x820")
            self.minsize(980, 640)

            self.project_dir = Path(__file__).resolve().parent
            self.rsc_dir = self.project_dir / "rsc"
            self.available_years = list_available_years(self.rsc_dir)
            self.current_result = None
            self.current_report = ""

            self.category_var = tk.StringVar()
            self.status_var = tk.StringVar(
                value="Wybierz kategorię i lata, a następnie kliknij \"Oblicz ranking\"."
            )
            self.summary_var = tk.StringVar(
                value="Ranking nie został jeszcze obliczony."
            )

            self._build_ui()
            self._select_all_years()
            self._refresh_category_choices()
            self.summary_var.set("Ranking nie został jeszcze obliczony dla bieżących filtrów.")
            self.status_var.set(
                "Wybierz kategorię i lata, a następnie kliknij \"Oblicz ranking\"."
            )

            if not self.available_years:
                self.calculate_button.state(["disabled"])
                self.status_var.set("Nie znaleziono katalogów z latami w folderze rsc.")

        def _build_ui(self) -> None:
            try:
                ttk.Style(self).theme_use("clam")
            except tk.TclError:
                pass

            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=1)

            container = ttk.Frame(self, padding=16)
            container.grid(row=0, column=0, sticky="nsew")
            container.columnconfigure(1, weight=1)
            container.rowconfigure(0, weight=1)

            sidebar = ttk.Frame(container)
            sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
            sidebar.columnconfigure(0, weight=1)

            filters_frame = ttk.LabelFrame(sidebar, text="Filtry", padding=12)
            filters_frame.grid(row=0, column=0, sticky="new")
            filters_frame.columnconfigure(0, weight=1)

            ttk.Label(filters_frame, text="Kategoria rankingu").grid(
                row=0, column=0, sticky="w"
            )
            self.category_combobox = ttk.Combobox(
                filters_frame,
                textvariable=self.category_var,
                state="readonly",
                width=20,
            )
            self.category_combobox.grid(row=1, column=0, sticky="ew", pady=(4, 12))
            self.category_combobox.bind("<<ComboboxSelected>>", self._on_filter_changed)

            ttk.Label(filters_frame, text="Lata uwzględniane w kalkulacji").grid(
                row=2, column=0, sticky="w"
            )

            years_frame = ttk.Frame(filters_frame)
            years_frame.grid(row=3, column=0, sticky="nsew", pady=(4, 12))
            years_frame.columnconfigure(0, weight=1)
            years_frame.rowconfigure(0, weight=1)

            self.years_listbox = tk.Listbox(
                years_frame,
                selectmode=tk.EXTENDED,
                exportselection=False,
                height=16,
                width=18,
            )
            self.years_listbox.grid(row=0, column=0, sticky="nsew")
            self.years_listbox.bind("<<ListboxSelect>>", self._on_year_selection_change)

            years_scroll = ttk.Scrollbar(
                years_frame, orient="vertical", command=self.years_listbox.yview
            )
            years_scroll.grid(row=0, column=1, sticky="ns")
            self.years_listbox.configure(yscrollcommand=years_scroll.set)

            for year in self.available_years:
                self.years_listbox.insert(tk.END, year)

            years_buttons = ttk.Frame(filters_frame)
            years_buttons.grid(row=4, column=0, sticky="ew")
            years_buttons.columnconfigure(0, weight=1)
            years_buttons.columnconfigure(1, weight=1)

            ttk.Button(
                years_buttons, text="Zaznacz wszystkie", command=self._select_all_years
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(
                years_buttons, text="Wyczyść wybór", command=self._clear_years_selection
            ).grid(row=0, column=1, sticky="ew")

            actions_frame = ttk.Frame(sidebar)
            actions_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            actions_frame.columnconfigure(0, weight=1)

            self.calculate_button = ttk.Button(
                actions_frame,
                text="Oblicz ranking",
                command=self._calculate_ranking,
            )
            self.calculate_button.grid(row=0, column=0, sticky="ew")

            self.save_button = ttk.Button(
                actions_frame,
                text="Zapisz ranking",
                command=self._save_ranking,
            )
            self.save_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))
            self.save_button.state(["disabled"])

            status_frame = ttk.LabelFrame(sidebar, text="Status", padding=12)
            status_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
            status_frame.columnconfigure(0, weight=1)

            ttk.Label(
                status_frame,
                textvariable=self.status_var,
                wraplength=280,
                justify="left",
            ).grid(row=0, column=0, sticky="w")

            results_frame = ttk.Frame(container)
            results_frame.grid(row=0, column=1, sticky="nsew")
            results_frame.columnconfigure(0, weight=1)
            results_frame.rowconfigure(1, weight=1)

            ttk.Label(
                results_frame,
                textvariable=self.summary_var,
                wraplength=760,
                justify="left",
            ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

            text_frame = ttk.Frame(results_frame)
            text_frame.grid(row=1, column=0, sticky="nsew")
            text_frame.columnconfigure(0, weight=1)
            text_frame.rowconfigure(0, weight=1)

            self.result_text = tk.Text(
                text_frame,
                wrap="none",
                font=("Courier New", 10),
                state="disabled",
            )
            self.result_text.grid(row=0, column=0, sticky="nsew")

            y_scroll = ttk.Scrollbar(
                text_frame, orient="vertical", command=self.result_text.yview
            )
            y_scroll.grid(row=0, column=1, sticky="ns")
            self.result_text.configure(yscrollcommand=y_scroll.set)

            x_scroll = ttk.Scrollbar(
                text_frame, orient="horizontal", command=self.result_text.xview
            )
            x_scroll.grid(row=1, column=0, sticky="ew")
            self.result_text.configure(xscrollcommand=x_scroll.set)

        def _get_selected_years(self) -> list[int]:
            return [
                int(self.years_listbox.get(index))
                for index in self.years_listbox.curselection()
            ]

        def _set_result_text(self, content: str) -> None:
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert("1.0", content)
            self.result_text.configure(state="disabled")

        def _select_all_years(self) -> None:
            if self.available_years:
                self.years_listbox.selection_set(0, tk.END)
            self._refresh_category_choices()
            self._mark_result_stale()

        def _clear_years_selection(self) -> None:
            self.years_listbox.selection_clear(0, tk.END)
            self._refresh_category_choices()
            self._mark_result_stale()

        def _on_year_selection_change(self, _event: tk.Event | None = None) -> None:
            self._refresh_category_choices()
            self._mark_result_stale()

        def _on_filter_changed(self, _event: tk.Event | None = None) -> None:
            self._mark_result_stale()

        def _refresh_category_choices(self) -> None:
            years = self._get_selected_years()
            categories = list_available_categories_for_years(
                self.rsc_dir, years if years else None
            )

            current_category = self.category_var.get()
            self.category_combobox.configure(values=categories)

            if current_category in categories:
                self.category_var.set(current_category)
            elif categories:
                self.category_var.set(categories[0])
            else:
                self.category_var.set("")

        def _mark_result_stale(self) -> None:
            self.current_result = None
            self.current_report = ""
            self.save_button.state(["disabled"])
            self.summary_var.set("Ranking nie został jeszcze obliczony dla bieżących filtrów.")
            self.status_var.set("Filtry zostały zmienione. Kliknij \"Oblicz ranking\".")

        def _calculate_ranking(self) -> None:
            category = self.category_var.get().strip()
            years = self._get_selected_years()

            if not category:
                messagebox.showerror("Brak kategorii", "Wybierz kategorię rankingu.")
                return
            if not years:
                messagebox.showerror("Brak lat", "Wybierz przynajmniej jeden rok.")
                return

            try:
                result = build_ranking(
                    category=category,
                    years=years,
                    rsc_dir=self.rsc_dir,
                )
            except Exception as exc:
                messagebox.showerror("Błąd obliczania", str(exc))
                return

            report = format_ranking_report(result)
            included_categories = ", ".join(result.included_categories) or "brak"

            self.current_result = result
            self.current_report = report
            self._set_result_text(report)
            self.summary_var.set(
                f"Kategoria {result.category} | lata: {', '.join(str(year) for year in result.years)} | "
                f"pliki: {len(result.processed_files)} | uwzględnione kategorie: {included_categories}"
            )
            if result.skipped_files:
                self.status_var.set(
                    f"Ranking obliczony. Pominięto {len(result.skipped_files)} plików z błędami."
                )
            else:
                self.status_var.set("Ranking został obliczony.")
            self.save_button.state(["!disabled"])

        def _save_ranking(self) -> None:
            if not self.current_result or not self.current_report:
                messagebox.showerror(
                    "Brak rankingu",
                    "Najpierw oblicz ranking, który ma zostać zapisany.",
                )
                return

            default_path = self.project_dir / build_default_output_filename(self.current_result)
            output_path = filedialog.asksaveasfilename(
                title="Zapisz ranking",
                initialdir=str(self.project_dir),
                initialfile=default_path.name,
                defaultextension=".txt",
                filetypes=(("Plik tekstowy", "*.txt"), ("Wszystkie pliki", "*.*")),
            )

            if not output_path:
                return

            try:
                saved_path = save_ranking_report(self.current_report, output_path)
            except Exception as exc:
                messagebox.showerror("Błąd zapisu", str(exc))
                return

            self.status_var.set(f"Ranking zapisany do pliku: {saved_path}")


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    parser = build_argument_parser()
    args = parser.parse_args()

    cli_requested = args.cli or bool(args.category or args.years or args.output)

    if cli_requested:
        raise SystemExit(run_cli_from_args(args, project_dir))

    if tk is None:
        print("Moduł tkinter nie jest dostępny. Uruchamiam tryb terminalowy.")
        raise SystemExit(run_cli_interactive(project_dir))

    app = RankingApp()
    app.mainloop()


if __name__ == "__main__":
    main()

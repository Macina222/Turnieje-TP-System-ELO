#!/usr/bin/env python3
"""
Unified configuration module for ELO ranking backends.

Both the XLSX backend (new_ranking_service.py) and SQLite backend
(sqlite_ranking_service.py) should use this module to load config.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.txt"

# Default ELO values (fallback if config.txt is missing some keys)
DEFAULT_VALUES = {
    "K": 50.0,
    "D": 250.0,
    "defaulteloC": 800.0,
    "defaulteloB": 900.0,
    "defaulteloA": 1000.0,
    "defaulteloS": 1100.0,
    "defaulteloOPEN": 950.0,
}


@dataclass(frozen=True)
class EloConfig:
    """Immutable ELO configuration parameters."""
    k_factor: float
    d_factor: float
    class_default_elos: dict[str, float]

    @property
    def K(self) -> float:
        """Alias for k_factor (legacy compatibility)."""
        return self.k_factor

    @property
    def D(self) -> float:
        """Alias for d_factor (legacy compatibility)."""
        return self.d_factor

    def default_for_class(self, class_code: Optional[str]) -> float:
        """Get default ELO for a class code."""
        cls = (class_code or "OPEN").upper()
        return self.class_default_elos.get(cls, self.class_default_elos.get("OPEN", DEFAULT_VALUES["defaulteloOPEN"]))


def _parse_config_number(raw_value: str, key: str, line_number: int) -> float:
    """Parse a single numeric value from config.txt with validation."""
    value = raw_value.split("#", 1)[0].strip().replace(",", ".")
    if not value:
        raise ValueError(
            f"Brak wartości dla {key} w pliku config.txt (linia {line_number})."
        )
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Nieprawidłowa wartość dla {key} w pliku config.txt "
            f"(linia {line_number}): {raw_value.strip()}"
        ) from exc


def load_config(config_path: str | Path | None = None) -> EloConfig:
    """
    Load ELO parameters from config.txt.

    Supported keys:
      K=<number>           — K factor
      D=<number>           — D factor
      defaulteloC=<number> — default ELO for class C
      defaulteloB=<number> — default ELO for class B
      defaulteloA=<number> — default ELO for class A
      defaulteloS=<number> — default ELO for class S
      defaulteloOPEN=<number> — default ELO for OPEN and other classes
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku konfiguracyjnego: {path}")

    values: dict[str, float] = {}
    class_elos: dict[str, float] = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Nieprawidłowy wpis w pliku config.txt (linia {line_number}): {raw_line}"
            )
        key, value = line.split("=", 1)
        normalized_key = key.strip().lower()

        if normalized_key in {"k", "d"}:
            values[normalized_key] = _parse_config_number(
                value, normalized_key.upper(), line_number
            )
        elif normalized_key.startswith("defaultelo"):
            klasa = normalized_key[len("defaultelo"):].upper()
            class_elos[klasa] = _parse_config_number(value, normalized_key, line_number)

    missing = [key.upper() for key in ("k", "d") if key not in values]
    if missing:
        raise ValueError(
            "Brakuje wymaganych wartości w config.txt: " + ", ".join(missing)
        )
    if values["k"] < 0:
        raise ValueError("Wartość K w config.txt nie może być ujemna.")
    if values["d"] <= 0:
        raise ValueError("Wartość D w config.txt musi być dodatnia.")

    # Merge with defaults for any missing class ELOs
    final_class_elos = {**DEFAULT_VALUES, **{k: v for k, v in class_elos.items() if k.startswith("defaultelo")}}
    # Filter to just the class_elos keys we care about
    class_elos_clean = {k.replace("defaultelo", ""): v for k, v in class_elos.items()}

    return EloConfig(
        k_factor=values["k"],
        d_factor=values["d"],
        class_default_elos=class_elos_clean,
    )


# Backwards compatibility aliases
RankingConfig = EloConfig  # legacy ranking_service.py uses this name
load_ranking_config = load_config  # legacy function name

# Backwards compatibility function - legacy.ranking_service expects this name
def get_default_elo_for_class(class_code: str | None, class_default_elos: dict[str, float]) -> float:
    """Get default ELO for a class code (legacy compatible signature)."""
    cls = (class_code or "OPEN").upper()
    return class_default_elos.get(cls, class_default_elos.get("OPEN", DEFAULT_VALUES["defaulteloOPEN"]))


if __name__ == "__main__":
    import sys
    cfg = load_config()
    print(f"K: {cfg.k_factor}")
    print(f"D: {cfg.d_factor}")
    print(f"Class defaults: {cfg.class_default_elos}")
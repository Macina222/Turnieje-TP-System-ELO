from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.txt"


@dataclass(frozen=True)
class RankingConfig:
    k_factor: float
    d_factor: float


def _parse_config_number(raw_value: str, key: str, line_number: int) -> float:
    value = raw_value.split("#", 1)[0].strip().replace(",", ".")
    if not value:
        raise ValueError(
            f"Brak wartosci dla {key} w pliku config.txt (linia {line_number})."
        )

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Nieprawidlowa wartosc dla {key} w pliku config.txt "
            f"(linia {line_number}): {raw_value.strip()}"
        ) from exc


def load_ranking_config(config_path: str | Path | None = None) -> RankingConfig:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.is_file():
        raise FileNotFoundError(f"Nie znaleziono pliku konfiguracyjnego: {path}")

    values: dict[str, float] = {}

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Nieprawidlowy wpis w pliku config.txt (linia {line_number}): {raw_line}"
            )

        key, value = line.split("=", 1)
        normalized_key = key.strip().lower()

        if normalized_key not in {"k", "d"}:
            continue

        values[normalized_key] = _parse_config_number(
            value,
            normalized_key.upper(),
            line_number,
        )

    missing = [key.upper() for key in ("k", "d") if key not in values]
    if missing:
        raise ValueError(
            "Brakuje wymaganych wartosci w config.txt: " + ", ".join(missing)
        )

    if values["k"] < 0:
        raise ValueError("Wartosc K w config.txt nie moze byc ujemna.")
    if values["d"] <= 0:
        raise ValueError("Wartosc D w config.txt musi byc dodatnia.")

    return RankingConfig(k_factor=values["k"], d_factor=values["d"])

"""Load the audit's thresholds from config/claims.toml.

Each entry mirrors a figure in PREREGISTRATION.md (locked, v1.0-lock) and carries the
section that defines it, the figure as printed there, and a quote that gives its
meaning. The loader refuses an entry whose value differs from its printed figure;
tests/test_claims_params.py checks every quote against the locked text.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

CLAIMS_TOML = Path(__file__).resolve().parents[2] / "config" / "claims.toml"
SCHEMA_VERSION = "1.0"
REQUIRED_FIELDS = ("value", "section", "text", "quote")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
REL_TOL = 1e-12

Number = int | float
Value = Number | tuple[Number, ...]


class ParameterError(ValueError):
    """A threshold entry is missing, malformed, or disagrees with its printed figure."""


@dataclass(frozen=True)
class Param:
    """One threshold, with the locked section and wording it comes from."""

    key: str
    value: Value
    section: str
    text: tuple[str, ...]
    quote: str


@dataclass(frozen=True)
class Params:
    """All thresholds, read-only, looked up by key such as "claim1.coherent_upper"."""

    entries: Mapping[str, Param]

    def number(self, key: str) -> float:
        """Return a single threshold as a float."""
        value = self._get(key).value
        if isinstance(value, tuple):
            raise ParameterError(f"{key}: holds {len(value)} values, not one")
        return float(value)

    def integer(self, key: str) -> int:
        """Return a single threshold that must be a whole number."""
        value = self._get(key).value
        if isinstance(value, tuple) or isinstance(value, float):
            raise ParameterError(f"{key}: not a whole number: {value!r}")
        return value

    def numbers(self, key: str) -> tuple[float, ...]:
        """Return a threshold that holds several values, in their printed order."""
        value = self._get(key).value
        if not isinstance(value, tuple):
            raise ParameterError(f"{key}: holds one value, not several")
        return tuple(float(v) for v in value)

    def _get(self, key: str) -> Param:
        if key not in self.entries:
            raise ParameterError(f"{key}: not in {CLAIMS_TOML.name}")
        return self.entries[key]


def parse_literal(text: str) -> float:
    """Return the number a printed figure stands for: "5%", "1,000", "−1.5", "three".

    A time of day such as "03:00" stands for its hour.
    """
    cleaned = text.strip().replace("−", "-").replace(",", "")
    if not cleaned:
        raise ParameterError("empty figure")
    if cleaned in NUMBER_WORDS:
        return float(NUMBER_WORDS[cleaned])
    if cleaned.endswith("%"):
        return float(cleaned[:-1]) / 100
    if ":" in cleaned:
        hours, minutes = cleaned.split(":")
        if minutes != "00":
            raise ParameterError(f"{text!r}: only whole hours are expected")
        return float(hours)
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ParameterError(f"{text!r}: not a figure") from exc


def load_params(path: Path = CLAIMS_TOML) -> Params:
    """Return every threshold in the file, each checked against its printed figure."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ParameterError(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
    entries: dict[str, Param] = {}
    for group in sorted(k for k in raw if k != "schema_version"):
        table = raw[group]
        if not isinstance(table, dict) or not table:
            raise ParameterError(f"{group}: expected a table of thresholds")
        for name in sorted(table):
            key = f"{group}.{name}"
            entries[key] = _build_param(key, table[name])
    if not entries:
        raise ParameterError(f"{path.name}: no thresholds found")
    return Params(MappingProxyType(entries))


def _build_param(key: str, entry: object) -> Param:
    if not isinstance(entry, dict):
        raise ParameterError(f"{key}: expected a table")
    missing = [f for f in REQUIRED_FIELDS if f not in entry]
    if missing:
        raise ParameterError(f"{key}: missing {', '.join(missing)}")
    value = _as_value(key, entry["value"])
    text = _as_text(key, entry["text"])
    numbers = value if isinstance(value, tuple) else (value,)
    if len(numbers) != len(text):
        raise ParameterError(f"{key}: {len(numbers)} values but {len(text)} figures")
    for number, figure in zip(numbers, text, strict=True):
        if not math.isclose(number, parse_literal(figure), rel_tol=REL_TOL):
            raise ParameterError(f"{key}: value {number} differs from {figure!r}")
    for figure in text:
        if figure not in str(entry["quote"]):
            raise ParameterError(f"{key}: figure {figure!r} is not in its quote")
    return Param(key, value, str(entry["section"]), text, str(entry["quote"]))


def _as_value(key: str, raw: object) -> Value:
    if isinstance(raw, bool):
        raise ParameterError(f"{key}: a true/false value is not a threshold")
    if isinstance(raw, int | float):
        return raw
    if isinstance(raw, list) and raw and all(_is_number(v) for v in raw):
        return tuple(raw)
    raise ParameterError(f"{key}: value must be a number or a list of numbers")


def _as_text(key: str, raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and raw and all(isinstance(v, str) for v in raw):
        return tuple(raw)
    raise ParameterError(f"{key}: text must be a string or a list of strings")


def _is_number(raw: object) -> bool:
    return isinstance(raw, int | float) and not isinstance(raw, bool)

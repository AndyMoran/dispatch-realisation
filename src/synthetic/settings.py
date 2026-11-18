"""Load config/synthetic.toml: what PREREGISTRATION §8 leaves open for the suite.

§8's own figures (U, η, cycles, runs, planted faults, lags) come from
config/claims.toml through src.model.params; this module refuses to read them here.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

SYNTHETIC_TOML = Path(__file__).resolve().parents[2] / "config" / "synthetic.toml"
SCHEMA_VERSION = "1.0"
# §8 figures, held in config/claims.toml; repeating one here would let it drift.
SECTION_8_KEYS = frozenset(
    {"capacity_mwh", "energy_mwh", "eta", "round_trip_eta", "cycles_per_day", "runs"}
)


class SettingsError(ValueError):
    """config/synthetic.toml is missing a value, malformed, or inconsistent."""


@dataclass(frozen=True)
class BatterySettings:
    """Power and daily pattern of the synthetic battery."""

    power_mw: float
    soc_low_share: float
    soc_high_share: float
    window_h: float
    charge_start_hours_utc: tuple[float, ...]
    discharge_start_hours_utc: tuple[float, ...]
    initial_soc_share: tuple[float, float]


@dataclass(frozen=True)
class RunLength:
    """One run length: an unscored adoption week, then scored ISO weeks (UTC)."""

    name: str
    adoption_week_start: datetime
    scored_weeks: int

    @property
    def first_scored_week(self) -> datetime:
        """Return the Monday 00:00 UTC that starts the first scored week."""
        return self.adoption_week_start + timedelta(days=7)

    @property
    def end(self) -> datetime:
        """Return the instant the last scored week ends (exclusive)."""
        return self.first_scored_week + timedelta(days=7 * self.scored_weeks)


@dataclass(frozen=True)
class ResponseCurve:
    """Dynamic Containment delivery curve and endurance (Service Terms v6, Sch. 2)."""

    source: str
    nominal_hz: float
    deadband_hz: float
    knee_hz: float
    knee_share: float
    full_hz: float
    delivery_duration_h: float
    contract_levels_mw: tuple[float, ...]


@dataclass(frozen=True)
class FrequencySettings:
    """Frequency input: files, links and the reading rules fixed before any read."""

    first_day: date
    last_day: date
    files: tuple[str, ...]
    urls: tuple[str, ...]
    header: tuple[str, str]
    slots_per_day: int
    hold_max_gap_s: int
    valid_hz: tuple[float, float]
    derived_file: str
    summary_file: str

    @property
    def days(self) -> int:
        """Return the number of UTC days covered, both ends included."""
        return (self.last_day - self.first_day).days + 1

    @property
    def start(self) -> datetime:
        """Return 00:00 UTC on the first day."""
        return datetime(
            self.first_day.year, self.first_day.month, self.first_day.day, tzinfo=UTC
        )


@dataclass(frozen=True)
class SyntheticSettings:
    """Every setting in config/synthetic.toml, checked."""

    battery: BatterySettings
    band_min_share: float
    master_seed: int
    lengths: tuple[RunLength, ...]
    boa_mean_per_day: float
    boa_duration_min: tuple[int, int]
    boa_offer_share: float
    boa_min_boundary_spanning_share: float
    resubmit_interval_min: int
    honest_lag_min: int
    meter_noise_sd_mwh: float
    ramp_limited_mw_per_min: float
    response: ResponseCurve
    reserve_change_probability: float
    reserve_step_mwh: tuple[float, float]
    reserve_range_mwh: tuple[float, float]
    frequency: FrequencySettings


def load_synthetic_settings(path: Path = SYNTHETIC_TOML) -> SyntheticSettings:
    """Return the suite's settings, refusing a missing, malformed or §8 value."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise SettingsError(f"{path.name}: schema_version must be {SCHEMA_VERSION}")
    _refuse_section_8(raw)
    runs = _table(raw, "runs")
    settings = SyntheticSettings(
        battery=_battery(_table(raw, "battery")),
        band_min_share=_share(_table(raw, "bands"), "min_share"),
        master_seed=_int(runs, "master_seed", minimum=0),
        lengths=_lengths(runs),
        boa_mean_per_day=_float(_table(raw, "boa"), "mean_per_day", positive=True),
        boa_duration_min=_int_pair(_table(raw, "boa"), "duration_min"),
        boa_offer_share=_share(_table(raw, "boa"), "offer_share"),
        boa_min_boundary_spanning_share=_share(
            _table(raw, "boa"), "min_boundary_spanning_share"
        ),
        resubmit_interval_min=_int(
            _table(raw, "declarations"), "resubmit_interval_min", minimum=1
        ),
        honest_lag_min=_int(_table(raw, "declarations"), "honest_lag_min", minimum=0),
        meter_noise_sd_mwh=_float(_table(raw, "meter"), "noise_sd_mwh"),
        ramp_limited_mw_per_min=_float(
            _table(raw, "ramp"), "ramp_limited_mw_per_min", positive=True
        ),
        response=_response(_table(raw, "response")),
        reserve_change_probability=_share(
            _table(raw, "reserve"), "change_probability_per_period"
        ),
        reserve_step_mwh=_float_pair(_table(raw, "reserve"), "step_mwh"),
        reserve_range_mwh=_float_pair(_table(raw, "reserve"), "range_mwh"),
        frequency=_frequency(_table(raw, "frequency")),
    )
    _check_calendar(settings)
    return settings


def _refuse_section_8(raw: dict[str, Any]) -> None:
    for name, table in raw.items():
        if isinstance(table, dict):
            clash = SECTION_8_KEYS & set(table)
            if clash:
                raise SettingsError(
                    f"[{name}] repeats §8 figures {sorted(clash)}; "
                    "they belong in config/claims.toml"
                )


def _battery(t: dict[str, Any]) -> BatterySettings:
    low, high = _share(t, "soc_low_share"), _share(t, "soc_high_share")
    if not low < high:
        raise SettingsError("soc_low_share must be below soc_high_share")
    initial = _float_pair(t, "initial_soc_share")
    if not (low <= initial[0] and initial[1] <= high):
        raise SettingsError("initial_soc_share must lie within the window targets")
    window_h = _float(t, "window_h", positive=True)
    starts = sorted(
        [(h, "charge") for h in _floats(t, "charge_start_hours_utc")]
        + [(h, "discharge") for h in _floats(t, "discharge_start_hours_utc")]
    )
    for (h0, _), (h1, _) in zip(
        starts, starts[1:] + [(starts[0][0] + 24, "")], strict=True
    ):
        if h1 - h0 < window_h:
            raise SettingsError(f"windows starting at {h0} h and {h1 % 24} h overlap")
    if any(not 0 <= h < 24 for h, _ in starts):
        raise SettingsError("window starts must lie in [0, 24) hours")
    return BatterySettings(
        power_mw=_float(t, "power_mw", positive=True),
        soc_low_share=low,
        soc_high_share=high,
        window_h=window_h,
        charge_start_hours_utc=_floats(t, "charge_start_hours_utc"),
        discharge_start_hours_utc=_floats(t, "discharge_start_hours_utc"),
        initial_soc_share=initial,
    )


def _lengths(runs: dict[str, Any]) -> tuple[RunLength, ...]:
    names = runs.get("lengths")
    if not isinstance(names, list) or not names:
        raise SettingsError("[runs] lengths must list at least one run length")
    out = []
    for name in names:
        t = _table(runs, str(name))
        start = _date(t, "adoption_week_start")
        if start.weekday() != 0:
            raise SettingsError(f"[runs.{name}] adoption week must start on a Monday")
        out.append(
            RunLength(
                name=str(name),
                adoption_week_start=datetime(
                    start.year, start.month, start.day, tzinfo=UTC
                ),
                scored_weeks=_int(t, "scored_weeks", minimum=1),
            )
        )
    return tuple(out)


def _response(t: dict[str, Any]) -> ResponseCurve:
    deadband, knee = _float(t, "deadband_hz"), _float(t, "knee_hz")
    full = _float(t, "full_hz")
    if not 0 <= deadband < knee < full:
        raise SettingsError("response curve needs 0 ≤ deadband < knee < full")
    levels = _floats(t, "contract_levels_mw")  # each checked ≥ 0
    source = t.get("source")
    if not isinstance(source, str) or not source:
        raise SettingsError("[response] source must name the service terms")
    return ResponseCurve(
        source=source,
        nominal_hz=_float(t, "nominal_hz", positive=True),
        deadband_hz=deadband,
        knee_hz=knee,
        knee_share=_share(t, "knee_share"),
        full_hz=full,
        delivery_duration_h=_float(t, "delivery_duration_h", positive=True),
        contract_levels_mw=levels,
    )


def _frequency(t: dict[str, Any]) -> FrequencySettings:
    files = _strings(t, "files")
    ids = _strings(t, "resource_ids")
    if len(files) != len(ids):
        raise SettingsError("[frequency] needs one resource id per file")
    prefix = t.get("url_prefix")
    if not isinstance(prefix, str) or not prefix.startswith("https://"):
        raise SettingsError("[frequency] url_prefix must be an https URL")
    header = _strings(t, "header")
    if len(header) != 2:
        raise SettingsError("[frequency] header must name two columns")
    first, last = _date(t, "first_day"), _date(t, "last_day")
    if last < first:
        raise SettingsError("[frequency] last_day is before first_day")
    return FrequencySettings(
        first_day=first,
        last_day=last,
        files=files,
        urls=tuple(
            f"{prefix}{i}/download/{f}" for i, f in zip(ids, files, strict=True)
        ),
        header=(header[0], header[1]),
        slots_per_day=_int(t, "slots_per_day", minimum=1),
        hold_max_gap_s=_int(t, "hold_max_gap_s", minimum=0),
        valid_hz=_float_pair(t, "valid_hz"),
        derived_file=_strings(t, "derived_file")[0],
        summary_file=_strings(t, "summary_file")[0],
    )


def _check_calendar(s: SyntheticSettings) -> None:
    """Every run must lie inside the frequency span, in whole UTC days."""
    span_end = s.frequency.start + timedelta(days=s.frequency.days)
    for length in s.lengths:
        if length.adoption_week_start < s.frequency.start or length.end > span_end:
            raise SettingsError(
                f"run {length.name} ({length.adoption_week_start:%Y-%m-%d} to "
                f"{length.end:%Y-%m-%d}) lies outside the frequency span"
            )


def _table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise SettingsError(f"missing table [{key}]")
    return value


def _float(t: dict[str, Any], key: str, positive: bool = False) -> float:
    value = t.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingsError(f"{key} must be a number")
    if value < 0 or (positive and value <= 0):
        raise SettingsError(f"{key} must be {'above' if positive else 'at least'} 0")
    return float(value)


def _int(t: dict[str, Any], key: str, minimum: int) -> int:
    value = t.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SettingsError(f"{key} must be a whole number ≥ {minimum}")
    return value


def _share(t: dict[str, Any], key: str) -> float:
    value = _float(t, key)
    if value > 1:
        raise SettingsError(f"{key} must lie in [0, 1]")
    return value


def _floats(t: dict[str, Any], key: str) -> tuple[float, ...]:
    value = t.get(key)
    if not isinstance(value, list) or not value:
        raise SettingsError(f"{key} must be a non-empty list of numbers")
    return tuple(_float({key: v}, key) for v in value)


def _float_pair(t: dict[str, Any], key: str) -> tuple[float, float]:
    values = _floats(t, key)
    if len(values) != 2 or not values[0] <= values[1]:
        raise SettingsError(f"{key} must be [low, high] with low ≤ high")
    return values[0], values[1]


def _int_pair(t: dict[str, Any], key: str) -> tuple[int, int]:
    value = t.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise SettingsError(f"{key} must be [low, high]")
    low = _int({key: value[0]}, key, minimum=1)
    high = _int({key: value[1]}, key, minimum=low)
    return low, high


def _strings(t: dict[str, Any], key: str) -> tuple[str, ...]:
    value = t.get(key)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise SettingsError(f"{key} must be text or a list of text")
    if not all(isinstance(v, str) and v for v in value):
        raise SettingsError(f"{key} must hold non-empty text only")
    return tuple(value)


def _date(t: dict[str, Any], key: str) -> date:
    value = t.get(key)
    if not isinstance(value, str):
        raise SettingsError(f"{key} must be a date written YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise SettingsError(f"{key}: {value!r} is not YYYY-MM-DD") from err

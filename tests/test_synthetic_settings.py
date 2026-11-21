"""config/synthetic.toml: pinned before the suite runs, and checked by its loader."""

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.synthetic.settings import (
    SYNTHETIC_TOML,
    SettingsError,
    load_synthetic_settings,
)

# SHA-256 of config/synthetic.toml as fixed on 18 Nov 2026, before the suite first ran
# and before any frequency file was read (PROJECT.md §11). Change it only with a
# decision-log row, and never after the first real unit is scored (§8).
SYNTHETIC_TOML_SHA256 = (
    "e5d2df8219a7263f869d14dabf660d457f1a62309330fcf9ce181f3d17ecbe35"
)


def test_settings_file_is_pinned() -> None:
    """The settings cannot change unseen after the suite has run."""
    digest = hashlib.sha256(SYNTHETIC_TOML.read_bytes()).hexdigest()
    assert digest == SYNTHETIC_TOML_SHA256


def test_settings_load_with_agreed_values() -> None:
    """Values agreed on 18 Nov 2026, read back through the loader."""
    s = load_synthetic_settings()
    assert s.battery.power_mw == pytest.approx(50.0)
    assert s.master_seed == 20261119
    short, long, *added = s.lengths
    assert [x.name for x in added] == ["w5", "w6", "w7", "w8", "w10", "w12", "w16"]
    assert [x.scored_weeks for x in added] == [5, 6, 7, 8, 10, 12, 16]
    assert all(x.end == datetime(2026, 10, 26, tzinfo=UTC) for x in added)
    assert (short.name, short.scored_weeks) == ("short", 4)
    assert short.first_scored_week == datetime(2026, 9, 28, tzinfo=UTC)
    assert (long.name, long.scored_weeks) == ("long", 20)
    assert long.first_scored_week == datetime(2026, 6, 8, tzinfo=UTC)
    # Both end at 24:00 UTC on Sunday 25 Oct 2026, the 25-hour UK day.
    assert short.end == long.end == datetime(2026, 10, 26, tzinfo=UTC)
    assert s.response.deadband_hz == pytest.approx(0.015)
    assert s.response.knee_share == pytest.approx(0.05)
    assert s.response.delivery_duration_h == pytest.approx(0.25)
    assert s.frequency.first_day == date(2026, 6, 1)
    assert s.frequency.days == 147
    assert s.frequency.urls[0].endswith("/download/fnew-2026-6.csv")


def edited(tmp_path: Path, old: str, new: str) -> Path:
    """Write a copy of the settings with one text replacement."""
    text = SYNTHETIC_TOML.read_text(encoding="utf-8")
    assert old in text, old
    path = tmp_path / "synthetic.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('schema_version = "1.0"', 'schema_version = "2.0"', "schema_version"),
        ("power_mw = 50.0", "power_mw = 50.0\neta = 0.9", "§8 figures"),
        ("power_mw = 50.0", "power_mw = 0.0", "power_mw"),
        ("soc_high_share = 0.85", "soc_high_share = 0.10", "below"),
        (
            "initial_soc_share = [0.30, 0.70]",
            "initial_soc_share = [0.10, 0.70]",
            "within",
        ),
        (
            "charge_start_hours_utc = [0.0, 11.0]",
            "charge_start_hours_utc = [0.0, 6.0]",
            "overlap",
        ),
        (
            'adoption_week_start = "2026-09-21"',
            'adoption_week_start = "2026-09-22"',
            "Monday",
        ),
        (
            'adoption_week_start = "2026-06-01"',
            'adoption_week_start = "2026-05-25"',
            "outside",
        ),
        ("scored_weeks = 4", "scored_weeks = 5", "outside"),
        ("knee_hz = 0.2", "knee_hz = 0.6", "deadband < knee < full"),
        (
            "contract_levels_mw = [0.0, 10.0, 20.0]",
            "contract_levels_mw = [-1.0]",
            "at least 0",
        ),
        ("offer_share = 0.5", "offer_share = 1.5", "[0, 1]"),
        ("duration_min = [30, 90]", "duration_min = [90, 30]", "duration_min"),
        ("step_mwh = [5.0, 15.0]", "step_mwh = [15.0, 5.0]", "low ≤ high"),
        ('header = ["dtm", "f"]', 'header = ["dtm"]', "two columns"),
        ('first_day = "2026-06-01"', 'first_day = "June"', "YYYY-MM-DD"),
        ('last_day = "2026-10-25"', 'last_day = "2026-05-01"', "before"),
        ("master_seed = 20261119", "master_seed = -1", "master_seed"),
        ("honest_lag_min = 1", "honest_lag_min = true", "honest_lag_min"),
        ('lengths = ["short", "long", "w5"', 'lengths = ["x"', "missing table"),
        (
            'lengths = ["short", "long", "w5", "w6", "w7", "w8", "w10", "w12", "w16"]',
            "lengths = []",
            "at least one",
        ),
        ('source = "NESO', 'source_old = "NESO', "service terms"),
        ('url_prefix = "https://', 'url_prefix = "http://', "https"),
    ],
)
def test_loader_refuses_bad_settings(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    """Each check refuses a value that would silently change a run."""
    with pytest.raises(SettingsError, match=message):
        load_synthetic_settings(edited(tmp_path, old, new))


def test_loader_needs_one_id_per_file(tmp_path: Path) -> None:
    """A file without its resource id would fetch the wrong month."""
    path = edited(tmp_path, '    "fnew-2026-10.csv",\n', "")
    with pytest.raises(SettingsError, match="one resource id per file"):
        load_synthetic_settings(path)


def test_loader_needs_every_table(tmp_path: Path) -> None:
    """A missing table is refused, not defaulted."""
    path = edited(tmp_path, "[meter]", "[meter_old]")
    with pytest.raises(SettingsError, match=r"\[meter\]"):
        load_synthetic_settings(path)

"""Frequency reduction for the frequency-response battery (config/synthetic.toml).

Hand-worked against NESO Response Services Service Terms v6, Schedule 2, and the
reading rules fixed before any file was read.
"""

import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import requests

from src.synthetic import frequency as fq
from src.synthetic.settings import (
    SYNTHETIC_TOML,
    FrequencySettings,
    ResponseCurve,
    load_synthetic_settings,
)

CURVE = load_synthetic_settings().response
START = datetime(2026, 6, 1, tzinfo=UTC)
T0 = int(START.timestamp())


def small(slots_per_day: int = 3600, hold_max_gap_s: int = 60) -> FrequencySettings:
    """One day of `slots_per_day` seconds: two settlement periods at 3,600."""
    return FrequencySettings(
        first_day=date(2026, 6, 1),
        last_day=date(2026, 6, 1),
        files=("a.csv",),
        urls=("https://example.test/a.csv",),
        header=("dtm", "f"),
        slots_per_day=slots_per_day,
        hold_max_gap_s=hold_max_gap_s,
        valid_hz=(49.0, 51.0),
        derived_file="data/derived/out.csv",
        summary_file="data/derived/out.json",
    )


def readings(pairs: list[tuple[int, str]]) -> fq.Readings:
    """Rows at seconds after 00:00 UTC on 1 Jun 2026, with value text."""
    return fq.Readings(
        seconds=np.array([T0 + s for s, _ in pairs], dtype=np.int64),
        text=np.array([t for _, t in pairs], dtype=np.str_),
        hz=np.array([fq.parse_value(t) for _, t in pairs], dtype=np.float64),
    )


def full_day(hz: float = 50.0, slots: int = 3600) -> list[tuple[int, str]]:
    return [(s, f"{hz}") for s in range(slots)]


# ------------------------------------------------------------------ curve


@pytest.mark.parametrize(
    ("hz", "share"),
    [
        (50.0, 0.0),
        (50.015, 0.0),  # edge of the deadband: still nothing
        (49.99, 0.0),
        (49.9855, 0.0),  # just inside the deadband
        # 49.9 Hz: 0.05 × (0.1 − 0.015)/(0.2 − 0.015) = 0.022973; Schedule 2's Table 1
        # gives 2.3% at 49.9 Hz.
        (49.9, 0.05 * 0.085 / 0.185),
        (49.8, 0.05),  # knee
        # 49.65 Hz: 0.05 + 0.95 × (0.35 − 0.2)/(0.5 − 0.2) = 0.525
        (49.65, 0.525),
        (49.5, 1.0),
        (49.2, 1.0),  # beyond full delivery: stays at 100%
        (50.1, -0.05 * 0.085 / 0.185),  # high frequency: import
        (50.5, -1.0),
    ],
)
def test_response_curve_hand_worked(hz: float, share: float) -> None:
    """Service Terms v6, Schedule 2: deadband, linear to the knee, linear to full."""
    got = fq.response_share(np.array([hz]), CURVE)
    assert got[0] == pytest.approx(share, abs=1e-12)


def test_zeroed_slot_requests_nothing() -> None:
    """A slot with no usable reading (NaN) gives no response."""
    assert fq.response_share(np.array([np.nan]), CURVE)[0] == 0.0


# ------------------------------------------------------------------ reading


@pytest.mark.parametrize(
    "text",
    [
        "2026-06-01 00:00:05",
        "2026-06-01T00:00:05",
        "2026-06-01 00:00:05.000",
        "2026-06-01 00:00:05Z",
        "2026-06-01T00:00:05+00:00",
    ],
)
def test_timestamps_in_gmt_whole_seconds(text: str) -> None:
    assert fq.parse_timestamps([text])[0] == T0 + 5


@pytest.mark.parametrize(
    "text",
    [
        "2026-06-01 00:00:05.500",  # not a whole second
        "2026-06-01 00:00:05+01:00",  # not GMT
        "01/06/2026 00:00:05",
        "2026-06-01 00:00",
        "2026-06-01 25:00:00",
    ],
)
def test_other_timestamps_stop(text: str) -> None:
    with pytest.raises(fq.FrequencyFormatError):
        fq.parse_timestamps([text])


def test_bare_date_reads_as_midnight() -> None:
    """August–October 2026 files write each midnight as a bare date."""
    assert fq.parse_timestamps(["2026-06-01"])[0] == T0


def body(*stamps: str) -> io.StringIO:
    return io.StringIO("dtm,f\n" + "".join(f"{t},50.0\n" for t in stamps))


def test_bare_date_between_its_neighbours_accepted() -> None:
    r = fq.read_rows(
        body(
            "2026-05-31 23:59:58",
            "2026-05-31 23:59:59",
            "2026-06-01",
            "2026-06-01 00:00:01",
        ),
        ("dtm", "f"),
        "x",
    )
    assert list(r.seconds - T0) == [-2, -1, 0, 1]


def test_bare_date_at_file_start_accepted() -> None:
    r = fq.read_rows(body("2026-06-01", "2026-06-01 00:00:01"), ("dtm", "f"), "x")
    assert list(r.seconds - T0) == [0, 1]


@pytest.mark.parametrize(
    "stamps",
    [
        ("2026-05-31 23:59:58", "2026-06-01", "2026-06-01 00:00:01"),  # gap before
        ("2026-05-31 23:59:59", "2026-06-01", "2026-06-01 00:00:02"),  # gap after
        ("2026-06-01 00:00:05", "2026-06-01", "2026-06-01 00:00:06"),  # out of place
        ("2026-06-01", "2026-06-01 00:00:01", "2026-06-01 00:00:00"),  # explicit too
    ],
)
def test_bare_date_out_of_place_stops(stamps: tuple[str, ...]) -> None:
    with pytest.raises(fq.FrequencyFormatError, match="midnight belongs"):
        fq.read_rows(body(*stamps), ("dtm", "f"), "x")


def test_read_rows_keeps_text_and_value() -> None:
    r = fq.read_rows(
        io.StringIO("dtm,f\n2026-06-01 00:00:00,49.95\n2026-06-01 00:00:01,\n"),
        ("dtm", "f"),
        "x",
    )
    assert list(r.seconds - T0) == [0, 1]
    assert list(r.text) == ["49.95", ""]
    assert r.hz[0] == pytest.approx(49.95)
    assert np.isnan(r.hz[1])


@pytest.mark.parametrize(
    "body",
    ["", "time,freq\n", "dtm,f,extra\n", "dtm,f\n2026-06-01 00:00:00,50.0,1\n"],
)
def test_wrong_header_or_row_shape_stops(body: str) -> None:
    with pytest.raises(fq.FrequencyFormatError):
        fq.read_rows(io.StringIO(body), ("dtm", "f"), "x")


# ------------------------------------------------------------------ grid


def test_complete_day_needs_no_rule() -> None:
    g = fq.build_grid([readings(full_day())], small())
    assert g.valid_per_day == (3600,)
    assert not g.held.any() and not g.zeroed.any()
    assert (g.rows_outside_span, g.duplicates_dropped, g.invalid_values) == (0, 0, 0)


def test_gap_of_60_s_holds_last_value() -> None:
    """Seconds 100–159 missing (60 slots): each holds second 99's value."""
    rows = [
        (s, "49.9" if s == 99 else "50.0") for s in range(3600) if not 100 <= s < 160
    ]
    g = fq.build_grid([readings(rows)], small())
    assert np.count_nonzero(g.held) == 60
    assert np.allclose(g.hz[100:160], 49.9)
    assert not g.zeroed.any()
    assert g.valid_per_day == (3540,)


def test_gap_of_61_s_gives_no_response() -> None:
    rows = [(s, "50.0") for s in range(3600) if not 100 <= s < 161]
    g = fq.build_grid([readings(rows)], small())
    assert not g.held.any()
    assert np.count_nonzero(g.zeroed) == 61
    assert np.isnan(g.hz[100:161]).all()


def test_gap_at_the_start_has_nothing_to_hold() -> None:
    rows = [(s, "50.0") for s in range(5, 3600)]
    g = fq.build_grid([readings(rows)], small())
    assert np.flatnonzero(g.zeroed).tolist() == [0, 1, 2, 3, 4]


def test_invalid_values_count_as_missing() -> None:
    """Blank, non-numeric and out-of-range readings join the gap rules."""
    rows = full_day()
    rows[10], rows[11], rows[12] = (10, ""), (11, "abc"), (12, "52.0")
    g = fq.build_grid([readings(rows)], small())
    assert g.invalid_values == 3
    assert np.flatnonzero(g.held).tolist() == [10, 11, 12]
    assert np.allclose(g.hz[10:13], 50.0)


def test_exact_duplicates_dropped_and_counted() -> None:
    rows = full_day() + [(7, "50.0"), (7, "50.0")]
    g = fq.build_grid([readings(rows)], small())
    assert g.duplicates_dropped == 2
    assert g.valid_per_day == (3600,)


def test_duplicate_invalid_row_counted_once() -> None:
    rows = full_day()
    rows[7] = (7, "")
    g = fq.build_grid([readings(rows + [(7, "")])], small())
    assert (g.duplicates_dropped, g.invalid_values) == (1, 1)


def test_differing_duplicates_stop() -> None:
    rows = full_day() + [(7, "49.99")]
    with pytest.raises(fq.ConflictingDuplicate, match="00:00:07"):
        fq.build_grid([readings(rows)], small())


def test_rows_outside_span_ignored_and_counted() -> None:
    """Monthly files cover more than the span; the extra rows are only counted."""
    rows = full_day() + [(-1, "50.0"), (3600, "50.0"), (7200, "50.0")]
    g = fq.build_grid([readings(rows)], small())
    assert g.rows_outside_span == 3


def test_grid_joins_files_in_time_order() -> None:
    late = readings([(s, "50.0") for s in range(1800, 3600)])
    early = readings([(s, "50.0") for s in range(1800)])
    g = fq.build_grid([late, early], small())
    assert g.valid_per_day == (3600,)


def test_hold_mask_on_empty_and_full_input() -> None:
    assert not fq.hold_mask(np.ones(5, dtype=bool), 60).any()
    assert not fq.hold_mask(np.zeros(5, dtype=bool), 60).any()


# ------------------------------------------------------------------ periods


def test_period_energy_hand_worked() -> None:
    """Period 1: 900 s at 49.8 Hz (5%) and 900 s at 50.2 Hz (−5%).

    Export = 900 × 0.05 / 3600 = 0.0125 MWh per MW; import the same. Their net is
    zero, which is what netting would show: the two directions stay separate.
    Period 2: 1,800 s at 49.5 Hz (100%) = 0.5 MWh per MW, the most a period can hold.
    """
    rows = [
        (s, "49.8" if s < 900 else "50.2" if s < 1800 else "49.5") for s in range(3600)
    ]
    e = fq.period_energy(fq.build_grid([readings(rows)], small()), CURVE, START)
    assert e.export_mwh_per_mw == pytest.approx([0.0125, 0.5])
    assert e.import_mwh_per_mw == pytest.approx([0.0125, 0.0])
    assert e.period_start == (START, datetime(2026, 6, 1, 0, 30, tzinfo=UTC))


def test_period_counts_held_and_zeroed() -> None:
    rows = [(s, "50.0") for s in range(3600) if not (10 <= s < 20 or 2000 <= s < 2100)]
    e = fq.period_energy(fq.build_grid([readings(rows)], small()), CURVE, START)
    assert e.held_s.tolist() == [10, 0]
    assert e.zeroed_s.tolist() == [0, 100]


def test_period_energy_needs_whole_periods() -> None:
    g = fq.build_grid([readings(full_day(slots=100))], small(slots_per_day=100))
    with pytest.raises(ValueError, match="whole settlement periods"):
        fq.period_energy(g, CURVE, START)


def test_derived_csv_fixed_format() -> None:
    rows = [(s, "49.8") for s in range(3600)]
    e = fq.period_energy(fq.build_grid([readings(rows)], small()), CURVE, START)
    lines = fq.derived_csv(e).splitlines()
    assert (
        lines[0]
        == "period_start_utc,export_mwh_per_mw,import_mwh_per_mw,held_s,zeroed_s"
    )
    assert lines[1] == "2026-06-01T00:00:00Z,0.025000000,0.000000000,0,0"
    assert len(lines) == 3


# ------------------------------------------------------------------ files


def write_raw(root: Path, name: str, rows: list[tuple[int, str]]) -> Path:
    path = root / "data" / "raw" / "frequency" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "dtm,f\n" + "".join(
        f"{datetime.fromtimestamp(T0 + s, tz=UTC):%Y-%m-%d %H:%M:%S},{v}\n"
        for s, v in rows
    )
    path.write_text(body, encoding="utf-8")
    return path


def write_manifest(root: Path, url: str, raw: Path, digest: str | None = None) -> Path:
    manifest = root / "data" / "manifests" / "frequency_manifest.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema_version": "1.0",
        "url": url,
        "utc_downloaded": "2026-11-19T09:00:00+00:00",
        "sha256": digest or fq.sha256_file(raw),
        "rows": "3600",
        "raw_file": raw.relative_to(root).as_posix(),
    }
    fq._append_manifest(manifest, row)
    return manifest


def test_reduce_end_to_end(tmp_path: Path) -> None:
    """Hashes checked, derived file written, summary written last and complete."""
    fs = small()
    rows = [(s, "49.8") for s in range(3600) if not 100 <= s < 200]
    raw = write_raw(tmp_path, "a__dl.csv", rows)
    manifest = write_manifest(tmp_path, fs.urls[0], raw)
    summary = fq.reduce(
        fs, CURVE, root=tmp_path, manifest=manifest, settings_path=SYNTHETIC_TOML
    )
    derived = tmp_path / fs.derived_file
    assert summary["derived_sha256"] == fq.sha256_file(derived)
    assert summary["zeroed_slots"] == 100
    assert summary["missing_slots_by_day"] == {"2026-06-01": 100}
    assert summary["curve_source"] == CURVE.source
    written = json.loads((tmp_path / fs.summary_file).read_text(encoding="utf-8"))
    assert written == summary
    # Byte-identical on a second run (PIPELINE_RULES §8).
    first = derived.read_bytes()
    _ = fq.reduce(
        fs, CURVE, root=tmp_path, manifest=manifest, settings_path=SYNTHETIC_TOML
    )
    assert derived.read_bytes() == first


def test_reduce_refuses_a_changed_raw_file(tmp_path: Path) -> None:
    fs = small()
    raw = write_raw(tmp_path, "a__dl.csv", full_day())
    manifest = write_manifest(tmp_path, fs.urls[0], raw, digest="0" * 64)
    with pytest.raises(fq.ManifestMismatch, match="SHA-256"):
        fq.reduce(fs, CURVE, root=tmp_path, manifest=manifest)


def test_reduce_refuses_an_unrecorded_or_missing_file(tmp_path: Path) -> None:
    fs = small()
    manifest = tmp_path / "m.csv"
    with pytest.raises(fq.ManifestMismatch, match="no manifest row"):
        fq.reduce(fs, CURVE, root=tmp_path, manifest=manifest)
    raw = write_raw(tmp_path, "a__dl.csv", full_day())
    manifest = write_manifest(tmp_path, fs.urls[0], raw)
    raw.unlink()
    with pytest.raises(fq.ManifestMismatch, match="missing"):
        fq.reduce(fs, CURVE, root=tmp_path, manifest=manifest)


def test_manifest_with_other_columns_refused(tmp_path: Path) -> None:
    path = tmp_path / "m.csv"
    path.write_text("url,sha256\n", encoding="utf-8")
    with pytest.raises(fq.ManifestMismatch, match="columns"):
        fq.manifest_rows(path)


# ------------------------------------------------------------------ fetch


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status_code = status
        self.body = body

    def iter_content(self, size: int) -> list[bytes]:
        return [self.body]


CSV_BODY = b"dtm,f\n2026-06-01 00:00:00,50.0\n2026-06-01 00:00:01,50.0\n"


def test_fetch_downloads_then_writes_manifest(tmp_path: Path) -> None:
    fs = small()
    manifest = tmp_path / "data" / "manifests" / "frequency_manifest.csv"
    with mock.patch("requests.get", return_value=FakeResponse(200, CSV_BODY)):
        fq.fetch(fs, root=tmp_path, manifest=manifest)
    rows = list(csv.DictReader(manifest.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 1 and rows[0]["rows"] == "2"
    raw = tmp_path / rows[0]["raw_file"]
    assert fq.sha256_file(raw) == rows[0]["sha256"]
    # A second fetch reuses the pinned file and downloads nothing.
    with mock.patch("requests.get") as get:
        fq.fetch(fs, root=tmp_path, manifest=manifest)
    get.assert_not_called()


def test_fetch_refuses_to_reuse_a_changed_file(tmp_path: Path) -> None:
    fs = small()
    manifest = tmp_path / "data" / "manifests" / "frequency_manifest.csv"
    with mock.patch("requests.get", return_value=FakeResponse(200, CSV_BODY)):
        fq.fetch(fs, root=tmp_path, manifest=manifest)
    raw = (
        tmp_path
        / next(csv.DictReader(manifest.read_text(encoding="utf-8").splitlines()))[
            "raw_file"
        ]
    )
    raw.write_text("dtm,f\n", encoding="utf-8")
    with pytest.raises(fq.ManifestMismatch):
        fq.fetch(fs, root=tmp_path, manifest=manifest)


def test_download_retries_only_transient_failures(tmp_path: Path) -> None:
    """Timeout, 503 and 429 are retried after waits of 2, 4 and 8 s; then success."""
    responses = [
        requests.Timeout(),
        FakeResponse(503),
        FakeResponse(429),
        FakeResponse(200, CSV_BODY),
    ]
    with (
        mock.patch("requests.get", side_effect=responses),
        mock.patch("time.sleep") as sleep,
    ):
        assert fq.download("https://example.test/a.csv", tmp_path / "a.csv") == 2
    assert [c.args[0] for c in sleep.call_args_list] == [2.0, 4.0, 8.0]


def test_download_gives_up_after_four_attempts(tmp_path: Path) -> None:
    with (
        mock.patch("requests.get", side_effect=requests.ConnectionError()),
        mock.patch("time.sleep"),
        pytest.raises(fq.FetchFailed, match="4 attempts"),
    ):
        fq.download("https://example.test/a.csv", tmp_path / "a.csv")
    assert not (tmp_path / "a.csv").exists()


def test_download_fails_at_once_on_404(tmp_path: Path) -> None:
    with (
        mock.patch("requests.get", return_value=FakeResponse(404)) as get,
        pytest.raises(fq.FetchFailed, match="404"),
    ):
        fq.download("https://example.test/a.csv", tmp_path / "a.csv")
    assert get.call_count == 1


def test_download_refuses_a_file_that_is_not_two_columns(tmp_path: Path) -> None:
    with (
        mock.patch("requests.get", return_value=FakeResponse(200, b"<html>\n")),
        pytest.raises(fq.FrequencyFormatError),
    ):
        fq.download("https://example.test/a.csv", tmp_path / "a.csv")
    assert list(tmp_path.iterdir()) == []


def test_curve_is_the_settings_curve() -> None:
    """The curve under test is the one config/synthetic.toml pins."""
    assert isinstance(CURVE, ResponseCurve)
    assert "v6" in CURVE.source

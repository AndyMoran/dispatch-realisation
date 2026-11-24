"""Private packs: isolation, labels, dates and the end-to-end path, with planted bugs.

Unit IDs and lead parties here are made up.
"""

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.ingest import pull
from src.scoring import packs as pk
from src.scoring import run as sr
from src.synthetic.fleet import synthetic_assembly

PREPARED = date(2026, 12, 18)
REPLY = date(2027, 1, 6)  # 10 working days after 18 Dec, past three bank holidays
RECORD = {
    "finished_utc": "2026-12-07T10:00:00+00:00",
    "code_commit": "abcdef0123456789",
}


def unit(uid: str, party: str, scored: bool = True) -> dict[str, Any]:
    c1: dict[str, Any] = {
        "scored_weeks": 6 if scored else 2,
        "score": 0.21 if scored else None,
        "signed": -0.03 if scored else None,
        "interval_95": [0.15, 0.30] if scored else None,
        "reason": None if scored else "fewer scored weeks than required",
    }
    c2: dict[str, Any] = {
        "scored_weeks": 6 if scored else 2,
        "violation_share_pooled": 0.012 if scored else None,
        "median_weekly_share": 0.01 if scored else None,
        "reason": None if scored else "fewer scored weeks than required",
    }
    branch = {"eta_hat": 0.86, "unscored_reason": None, "claim1": c1, "claim2": c2}
    c1b = {**c1, "score": 0.25} if scored else c1
    c2b = {**c2, "violation_share_pooled": 0.034} if scored else c2
    branch_b = {"eta_hat": 0.91, "unscored_reason": None, "claim1": c1b, "claim2": c2b}
    return {
        "unit": uid,
        "lead_party": party,
        "secondary": False,
        "registered_mw": 49.9,
        "adoption_week_start": "2026-07-06T00:00:00+00:00",
        "branches": {"A": branch, "B": branch_b},
        "claim5": {
            "boas": 40,
            "observed": 31,
            "censored": {"next acceptance": 5, "30 minutes": 3, "data end": 1},
            "median_min": 12.0,
            "p75_min": 21.5,
            "p90_min": None,
            "share_within_benchmark": 0.05,
            "benchmark_min": 1.0,
        },
        "m13_slope": {"slope": 1.02, "periods": 900, "weeks": 6},
    }


TABLE = {
    "units": [
        unit("T_ABC-1", "Alpha Energy Ltd"),
        unit("T_ABC-11", "Beta Power"),
        unit("T_XYZ-2", "Alpha Energy Ltd", scored=False),
        unit("E_QRS-1", "Gamma & Sons"),
    ]
}


def test_working_days_skip_weekends_and_bank_holidays() -> None:
    assert pk.working_days_between(PREPARED, REPLY) == 10
    assert pk.working_days_between(PREPARED, date(2027, 1, 5)) == 9
    assert pk.working_days_between(date(2026, 11, 24), date(2026, 12, 8)) == 10
    with pytest.raises(pk.PackError, match="bank holidays"):
        pk.working_days_between(PREPARED, date(2027, 2, 15))


def test_each_pack_holds_only_its_own_units() -> None:
    files = pk.build(TABLE, RECORD, PREPARED, REPLY)
    assert sorted(files) == ["alpha-energy-ltd.md", "beta-power.md", "gamma-sons.md"]
    alpha = files["alpha-energy-ltd.md"]
    assert "### T_ABC-1\n" in alpha and "### T_XYZ-2\n" in alpha
    assert "T_ABC-11" not in alpha and "E_QRS-1" not in alpha
    assert "Beta Power" not in alpha and "Gamma" not in alpha
    beta = files["beta-power.md"]
    assert "### T_ABC-11\n" in beta and not pk.mentions(beta, "T_ABC-1")


def test_labels_and_what_is_left_out() -> None:
    text = pk.build(TABLE, RECORD, PREPARED, REPLY)["alpha-energy-ltd.md"]
    for needed in (
        "No Claim 1 flag is given",
        "Not proof of under-declaration",
        "not certified contract-free",
        "Claim 3 was dropped",
        "Claim 4 was not run on real units",
        "may not be its operator or owner",
        pk.METHOD_DOI,
        "reply by 2027-01-06",
        "not scored: fewer scored weeks than required",
        "0.210 | 0.150 to 0.300 | -0.030",
        "1.2%",
        "| B | 0.910 | 6 | 0.250 |",
        "| B | 6 | 3.4% |",
    ):
        assert needed in text, needed
    for absent in ("H = 6 hours", "0.65", "sensitivity", "m13", "slope", "1.02"):
        assert absent not in text, absent


def test_a_leaked_unit_stops_the_packs(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pk.render

    def leaky(party: str, units: Any, *rest: Any) -> str:
        return real(party, units, *rest) + "\nSee also T_ABC-11.\n"

    monkeypatch.setattr(pk, "render", leaky)
    with pytest.raises(pk.PackError, match="another lead party's unit"):
        pk.build(TABLE, RECORD, PREPARED, REPLY)


def test_a_leaked_party_or_missing_unit_stops_the_packs() -> None:
    with pytest.raises(pk.PackError, match="another lead party"):
        pk.check_pack(
            "# Alpha Energy Ltd\nBeta Power",
            "Alpha Energy Ltd",
            set(),
            set(),
            {"Alpha Energy Ltd", "Beta Power"},
        )
    with pytest.raises(pk.PackError, match="leaves out"):
        pk.check_pack("# Alpha", "Alpha", {"T_ABC-1"}, {"T_ABC-1"}, {"Alpha"})


@pytest.mark.parametrize(
    ("table", "match"),
    [
        ({"units": [unit("U1", "")]}, "no lead party"),
        ({"units": [unit("U1", "P"), unit("U1", "P")]}, "twice"),
        ({"units": [unit("U1", "A&B Ltd"), unit("U2", "A B Ltd")]}, "same file name"),
        ({"units": [unit("U1", "???")]}, "empty file name"),
    ],
)
def test_bad_tables_stop(table: dict[str, Any], match: str) -> None:
    with pytest.raises(pk.PackError, match=match):
        pk.build(table, RECORD, PREPARED, REPLY)


def test_a_reply_date_too_soon_stops() -> None:
    with pytest.raises(pk.PackError, match="fewer than 10 working days"):
        pk.build(TABLE, RECORD, PREPARED, date(2027, 1, 5))


def test_from_the_pinned_run_to_the_packs(tmp_path: Path) -> None:
    (tmp_path / sr.KNOWN_ANSWER).parent.mkdir(parents=True)
    shutil.copy(pull.ROOT / sr.KNOWN_ANSWER, tmp_path / sr.KNOWN_ANSWER)
    assembly, end = synthetic_assembly()
    sr.run(tmp_path, workers=1, end=end, assembly=assembly, check_git=False)
    assert pk.main(["--reply-by", "2027-01-06"], root=tmp_path, today=PREPARED) == 0
    written = sorted((tmp_path / pk.PACKS_DIR).iterdir())
    assert [p.name for p in written] == [
        "lead-party-0.md",
        "lead-party-1.md",
        "lead-party-2.md",
    ]
    zero = written[0].read_text()
    assert zero.count("\n### UNIT-") == 3  # UNIT-00, 03, 06
    for uid in ("UNIT-01", "UNIT-02", "UNIT-04", "UNIT-05"):
        assert uid not in zero
    # A second run refuses while the first run's packs are still there.
    assert pk.main(["--reply-by", "2027-01-08"], root=tmp_path, today=PREPARED) == 1
    assert sorted((tmp_path / pk.PACKS_DIR).iterdir()) == written
    for f in written:
        f.unlink()
    assert pk.main(["--reply-by", "2026-12-21"], root=tmp_path, today=PREPARED) == 1
    assert not any((tmp_path / pk.PACKS_DIR).iterdir())  # too soon: nothing written
    (tmp_path / sr.RECORD_OUT).write_text("{not json")
    assert pk.main(["--reply-by", "2027-01-06"], root=tmp_path, today=PREPARED) == 1


def test_packs_folder_is_gitignored() -> None:
    ignored = (pull.ROOT / ".gitignore").read_text().split()
    assert "data/interim/" in ignored and str(pk.PACKS_DIR).startswith("data/interim/")
    assert json.dumps(str(pk.PACKS_DIR))


def test_a_bare_shorter_party_name_is_a_leak() -> None:
    parties = {"Alpha", "Alpha Energy Ltd"}
    own = "# Alpha Energy Ltd\nUnits of Alpha Energy Ltd."
    pk.check_pack(own, "Alpha Energy Ltd", set(), set(), parties)
    with pytest.raises(pk.PackError, match="another lead party"):
        pk.check_pack(
            own + "\nCompare Alpha.", "Alpha Energy Ltd", set(), set(), parties
        )


def test_party_names_are_stripped_and_pipes_escaped() -> None:
    table = {"units": [unit("U1", "Alpha "), unit("U2", "Alpha", scored=False)]}
    table["units"][1]["branches"]["A"]["claim1"]["reason"] = "a | b"
    files = pk.build(table, RECORD, PREPARED, REPLY)
    assert list(files) == ["alpha.md"]
    assert "not scored: a \\| b |" in files["alpha.md"]


def test_a_failed_write_leaves_no_partial_pack_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = pk.build(TABLE, RECORD, PREPARED, REPLY)
    out = tmp_path / pk.PACKS_DIR
    partial = out.with_name(out.name + ".partial")
    real = Path.write_text
    calls: list[str] = []

    def fail_second(self: Path, text: str, **kw: Any) -> int:
        calls.append(self.name)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(self, text, **kw)

    monkeypatch.setattr(Path, "write_text", fail_second)
    with pytest.raises(OSError):
        pk.write_all(files, out, partial)
    monkeypatch.undo()
    assert not out.exists()  # the packs folder never holds part of a set
    assert len(list(partial.iterdir())) == 1
    (tmp_path / sr.PRIVATE_OUT).parent.mkdir(parents=True)
    (tmp_path / sr.PRIVATE_OUT).write_text(json.dumps(TABLE))
    (tmp_path / sr.RECORD_OUT).parent.mkdir(parents=True)
    (tmp_path / sr.RECORD_OUT).write_text(json.dumps(RECORD))
    assert pk.main(["--reply-by", "2027-01-06"], root=tmp_path, today=PREPARED) == 1
    for f in partial.iterdir():
        f.unlink()
    partial.rmdir()
    assert pk.main(["--reply-by", "2027-01-06"], root=tmp_path, today=PREPARED) == 0
    assert sorted(f.name for f in out.iterdir()) == sorted(files)
    assert not partial.exists()

"""Deviation 5: accepted-BOA add-back only for instructions the record knew (§3; §12).

Hand-worked cases for `declared_series`, `in_force_publish_times` and the
settings that choose the rule.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.claims.claim4 import Claim4Settings
from src.claims.declared_series import declared_series
from src.claims.results import load_scoring_settings
from src.claims.unit import ClaimSettings, load_claim_settings
from src.model.types import LevelSegment, Submission, build_unit_inputs
from src.physics.declared import declared_at, in_force_publish_times

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
END = WEEK0 + timedelta(days=7)
MIN = timedelta(minutes=1)
ROUTINE = Submission("MDO", WEEK0, END, 40.0, None, WEEK0, 1)
REDECLARED = Submission("MDO", WEEK0 + 11 * MIN, END, 20.0, None, WEEK0 + 11 * MIN, 1)


def boa(accepted_min: int) -> LevelSegment:
    """20 MW export from minute 10 to 70, accepted at `accepted_min`; PN zero."""
    return LevelSegment(
        WEEK0 + 10 * MIN, WEEK0 + 70 * MIN, 20.0, 20.0, 1, WEEK0 + accepted_min * MIN
    )


def d(
    records: list[Submission], accepted_min: int, at_min: int, rule: str = "known"
) -> float | None:
    u = build_unit_inputs("u", None, records, [], [], [boa(accepted_min)])
    return declared_series(
        u,
        [WEEK0 + at_min * MIN],
        0.8,
        "A",
        3,
        None,
        9999.0,
        END,
        rule,  # type: ignore[arg-type]
    )[0]


def test_default_rule_is_known() -> None:
    """At minute 30, B^exp to minute 70 is 20 × 40/60 = 13.33 MWh."""
    u = build_unit_inputs("u", None, [ROUTINE], [], [], [boa(10)])
    t = [WEEK0 + 30 * MIN]
    assert declared_series(u, t, 0.8, "A", 3, None, 9999.0, END)[0] == pytest.approx(
        40.0
    )
    assert d([ROUTINE], 10, 30, "all") == pytest.approx(40.0 + 40.0 / 3.0)


@pytest.mark.parametrize(
    ("records", "accepted", "expected"),
    [
        ([ROUTINE], 10, 40.0),  # accepted after the record: not added back
        ([ROUTINE], -5, 40.0 + 40.0 / 3.0),  # accepted before it: added back
        ([ROUTINE], 0, 40.0),  # accepted at its publish minute: not added back
        ([ROUTINE, REDECLARED], 10, 20.0 + 40.0 / 3.0),  # redeclared after it
        ([ROUTINE, REDECLARED], 11, 20.0),  # same minute as the redeclaration
    ],
)
def test_known_rule_by_hand(
    records: list[Submission], accepted: int, expected: float
) -> None:
    assert d(records, accepted, 30) == pytest.approx(expected)


def test_no_record_means_no_declaration_under_either_rule() -> None:
    assert d([], 10, 30) is None
    assert d([], 10, 30, "all") is None


def test_publish_times_follow_the_record_in_force() -> None:
    times = [WEEK0 + m * MIN for m in (0, 10, 11, 20)]
    got = in_force_publish_times([ROUTINE, REDECLARED], "MDO", times, 9999.0, END)
    assert got == (WEEK0, WEEK0, WEEK0 + 11 * MIN, WEEK0 + 11 * MIN)
    default = Submission("MDO", WEEK0, END, 9999.0, None, WEEK0 + MIN, 1)
    records = [ROUTINE, default]
    pubs = in_force_publish_times(records, "MDO", times, 9999.0, END)
    levels = declared_at(records, "MDO", times, 9999.0, END)
    assert [p is None for p in pubs] == [v is None for v in levels]
    with pytest.raises(ValueError):
        in_force_publish_times([ROUTINE], "MDO", times[::-1], 9999.0, END)
    with pytest.raises(ValueError):
        in_force_publish_times([ROUTINE], "MDO", times, 0.0, END)


def test_settings_choose_the_rule(tmp_path: Path) -> None:
    assert load_scoring_settings().boa_addback == "known"
    assert load_claim_settings().boa_addback == "known"
    assert "boa_addback" in ClaimSettings.__dataclass_fields__
    text = Path("config/scoring.toml").read_text(encoding="utf-8")
    bad = tmp_path / "scoring.toml"
    bad.write_text(text.replace('boa_addback = "known"', 'boa_addback = "some"'))
    with pytest.raises(ValueError):
        load_scoring_settings(bad)
    missing = tmp_path / "missing.toml"
    missing.write_text(text.replace('boa_addback = "known"', ""))
    with pytest.raises(ValueError):
        load_scoring_settings(missing)


# ------------------------------------------------------------ wiring


class Spy:
    """Stands in for `declared_series`, recording the add-back rule it is given."""

    def __init__(self) -> None:
        self.rules: list[object] = []

    def __call__(self, *args: object) -> tuple[None, ...]:
        self.rules.append(args[8] if len(args) > 8 else "default")
        times = args[1]
        assert isinstance(times, tuple | list)
        return (None,) * len(times)


def unit_with_meter() -> object:
    from src.model.types import MeterPeriod

    meter = [
        MeterPeriod(WEEK0 + h * 30 * MIN, {2: -10.0, 4: 8.0}.get(h, 0.0), "SF")
        for h in range(336)
    ]
    return build_unit_inputs("u", None, [ROUTINE], meter, [], [])


@pytest.mark.parametrize("rule", ["known", "all"])
def test_scoring_passes_the_configured_rule(
    rule: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from src.claims import claim4, unit

    settings = replace(load_claim_settings(), boa_addback=rule)  # type: ignore[arg-type]
    for module in (unit, claim4):
        spy = Spy()
        monkeypatch.setattr(module, "declared_series", spy)
        u = unit_with_meter()
        if module is unit:
            unit.score_unit(u, WEEK0 - 7 * 1440 * MIN, END, settings, "A", frozenset())  # type: ignore[arg-type]
        else:
            claim4.score_unit_claim4(
                u,  # type: ignore[arg-type]
                WEEK0 - 7 * 1440 * MIN,
                END,
                settings,
                claim4.Claim4Settings(0.02, 1.02),
                "A",
                [100.0],
            )
        assert spy.rules == [rule]


def test_diagnostics_of_earlier_runs_keep_the_old_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.synthetic import claim4_decomposition, claim4_diagnosis, stale_addback

    assert claim4_diagnosis.ADDBACK == "all"
    assert claim4_decomposition.ADDBACK == "all"
    spy = Spy()
    monkeypatch.setattr(stale_addback, "declared_series", spy)
    times = [WEEK0, WEEK0 + 30 * MIN]
    stale_addback.both_rules(unit_with_meter(), times, 0.8, 3, 9999.0, END)  # type: ignore[arg-type]
    assert spy.rules == ["all"]
    spy = Spy()
    monkeypatch.setattr(claim4_diagnosis, "declared_series", spy)
    claim4_diagnosis.diagnose_unit(
        unit_with_meter(),  # type: ignore[arg-type]
        WEEK0 - 7 * 1440 * MIN,
        END,
        load_claim_settings(),
        Claim4Settings(0.02, 1.02),
        100.0,
        0.88,
    )
    assert spy.rules and set(spy.rules) == {"all"}

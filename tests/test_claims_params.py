"""config/claims.toml against the locked pre-registration, and the loader's checks.

The thresholds live in PREREGISTRATION.md, locked at tag v1.0-lock. config/claims.toml
is a copy the code reads. These tests fail if the copy drifts from the locked text,
or if the locked sections themselves are edited. Only §12, the deviations log, may
change after lock.
"""

import hashlib
import re
from pathlib import Path

import pytest

from src.model.params import (
    CLAIMS_TOML,
    ParameterError,
    load_params,
    parse_literal,
)

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "PREREGISTRATION.md"
DEVIATIONS_HEADING = "## 12. Deviations log"
# SHA-256 of PREREGISTRATION.md up to §12 at tag v1.0-lock (commit 4395934).
# Change only with a new lock tag (PREREGISTRATION §8).
LOCKED_SECTIONS_SHA256 = (
    "af019d05d6d60005f007d17062109522a3a91c601ce4da770a008b960277b06a"
)


def locked_text() -> str:
    """PREREGISTRATION.md before the deviations log, which may grow after lock."""
    text = PREREG.read_text(encoding="utf-8")
    head, found, _ = text.partition(DEVIATIONS_HEADING)
    assert found, "deviations-log heading missing from PREREGISTRATION.md"
    return head


def section(text: str, ident: str) -> str:
    """Body of section "4" (## 4.) or subsection "5.7" (### 5.7), to the next peer."""
    level = "###" if "." in ident else "##"
    marker = f"{ident}." if level == "##" else ident
    start = re.search(rf"^{level} {re.escape(marker)} ", text, re.MULTILINE)
    assert start, f"section {ident} not found"
    stop = r"^##+ " if level == "###" else r"^## "
    end = re.compile(stop, re.MULTILINE).search(text, start.end())
    return text[start.start() : end.start() if end else len(text)]


def test_locked_sections_unchanged() -> None:
    digest = hashlib.sha256(locked_text().encode("utf-8")).hexdigest()
    assert digest == LOCKED_SECTIONS_SHA256


def test_every_quote_is_in_its_locked_section() -> None:
    text = locked_text()
    params = load_params()
    missing = [
        f"{p.key} (§{p.section}): {p.quote!r}"
        for p in params.entries.values()
        if p.quote not in section(text, p.section)
    ]
    assert not missing, "quotes not found in their section:\n" + "\n".join(missing)


def test_section_finder_stops_at_the_next_peer() -> None:
    text = locked_text()
    assert "### 5.8" not in section(text, "5.7")
    assert "## 5." not in section(text, "4")
    assert "### 5.10" in section(text, "5")


@pytest.mark.parametrize(
    ("figure", "expected"),
    [
        ("5%", 0.05),
        ("1,000", 1000.0),
        ("−1.5", -1.5),
        ("three", 3.0),
        ("03:00", 3.0),
        ("0.70", 0.7),
    ],
)
def test_parse_literal(figure: str, expected: float) -> None:
    assert parse_literal(figure) == pytest.approx(expected)


@pytest.mark.parametrize("figure", ["", "abc", "03:30"])
def test_parse_literal_rejects(figure: str) -> None:
    with pytest.raises(ParameterError):
        parse_literal(figure)


def test_lookups_and_their_types() -> None:
    params = load_params()
    assert params.number("claim1.coherent_upper") == pytest.approx(0.05)
    assert params.integer("scoring.draws") == 1000
    assert params.numbers("known_answer.f_band") == pytest.approx((0.15, 0.25))
    with pytest.raises(ParameterError):
        params.integer("claim1.coherent_upper")
    with pytest.raises(ParameterError):
        params.number("known_answer.f_band")
    with pytest.raises(ParameterError):
        params.numbers("claim1.coherent_upper")
    with pytest.raises(ParameterError):
        params.number("claim1.no_such_threshold")


def test_efa_exclusion_count_is_consistent() -> None:
    """Six boundaries, one period either side of each: 12 of 48 a day (§4)."""
    params = load_params()
    boundaries = params.numbers("screens.efa_boundary_hours")
    assert len(boundaries) * 2 == params.integer("screens.efa_excluded_periods_per_day")


ENTRY = 'value = {value}\nsection = "4"\ntext = {text}\nquote = {quote}\n'


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "claims.toml"
    path.write_text(f'schema_version = "1.0"\n\n{body}', encoding="utf-8")
    return path


def test_rejects_value_that_differs_from_its_figure(tmp_path: Path) -> None:
    body = "[claim1.x]\n" + ENTRY.format(value=0.5, text='"0.05"', quote='"≤ 0.05"')
    with pytest.raises(ParameterError, match="differs"):
        load_params(write_config(tmp_path, body))


def test_rejects_figure_missing_from_its_quote(tmp_path: Path) -> None:
    body = "[claim1.x]\n" + ENTRY.format(value=0.05, text='"0.05"', quote='"no"')
    with pytest.raises(ParameterError, match="not in its quote"):
        load_params(write_config(tmp_path, body))


def test_rejects_missing_field(tmp_path: Path) -> None:
    body = '[claim1.x]\nvalue = 0.05\nsection = "4"\n'
    with pytest.raises(ParameterError, match="missing"):
        load_params(write_config(tmp_path, body))


def test_rejects_empty_file_and_wrong_schema(tmp_path: Path) -> None:
    with pytest.raises(ParameterError, match="no thresholds"):
        load_params(write_config(tmp_path, ""))
    path = tmp_path / "old.toml"
    path.write_text('schema_version = "0.9"\n', encoding="utf-8")
    with pytest.raises(ParameterError, match="schema_version"):
        load_params(path)


def test_rejects_boolean_and_mismatched_lists(tmp_path: Path) -> None:
    bool_body = "[a.x]\n" + ENTRY.format(value="true", text='"1"', quote='"1"')
    with pytest.raises(ParameterError, match="true/false"):
        load_params(write_config(tmp_path, bool_body))
    list_body = "[a.y]\n" + ENTRY.format(
        value="[1, 2]", text='["1"]', quote='"1 and 2"'
    )
    with pytest.raises(ParameterError, match="2 values but 1"):
        load_params(write_config(tmp_path, list_body))


def test_default_path_is_the_repository_config() -> None:
    assert CLAIMS_TOML == ROOT / "config" / "claims.toml"

# Coding Standard

How each function, module and test in this repository is written.

For: anyone writing or reviewing Python here.

`PIPELINE_RULES.md` says what the pipeline must do: fail visibly, keep excluded units, stay deterministic. This file says how the code that does it is written. Prose in comments, docstrings and commit messages follows `WRITING.md`. Definitions come from `PREREGISTRATION.md`; code implements them and never restates them in a different form.

Adapted from Holzmann's "Power of 10" rules for safety-critical code (NASA JPL, 2006) and from the project rules of an earlier BMRS project. The decision log (`PROJECT.md` §11, 18 Nov 2026) records what was dropped and why.

**Scope.** The rules apply to every file added after 18 November 2026. The scripts that produced the frozen outputs in `outputs/lock/` and `outputs/gate_a1/` are exempt and listed in `pyproject.toml`; they are not reformatted, so that the code that produced the lock stays as it ran. New ingestion code goes in new files and follows these rules.

**Must and prefer.** A **must** rule is broken only through the exception process below. A **prefer** rule is a default: break it when following it would make the code harder to read, and say why in a comment.

**Terms.**
- *Public function:* a function or method in `src/` whose name does not start with an underscore.
- *Data function:* a function that reads, parses, validates or transforms data from outside the code: a file, an API response, or a record built from one.

## 1. Structure

1. **Must:** no recursion.
2. **Must:** every public function has type hints and a docstring. The docstring's first line states its purpose or its result. A function that implements a pre-registered definition names its section: "PREREGISTRATION §4, Claim 1 weekly score."
3. **Must:** names carry units: `mdo_mwh`, `power_mw`, `lag_min`, `eta`. A sum of `_mwh` and `_mw` is then visibly wrong.
4. **Must:** `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
5. **Prefer:** functions of 60 lines or fewer, with at most two levels of nesting. These are prompts to simplify, not reasons to split a function in an awkward place.

## 2. Data and state

1. **Must:** inputs are immutable. Records are frozen dataclasses. A function never changes a caller's list or array; it returns a new one. Copy a numpy view before storing it.
2. **Must:** no mutable module-level state. Constants only. Configuration is loaded once and passed in.
3. **Must:** time is timezone-aware UTC. A naive `datetime` is an error. Settlement periods are derived from UTC timestamps, never from local clock time.
4. **Must:** floats are never compared with `==`. Tolerances come from `config/claims.toml`, with their source section.
5. **Must:** randomness is passed in. A function that needs random numbers takes a `numpy.random.Generator` seeded by its caller. There is no global random state.
6. **Prefer:** vectorised numpy to loops over rows. Where a loop is clearer, write the loop.

## 3. Checks and errors

1. **Must:** a check that protects a result is an explicit `if ...: raise`, or an `excluded(reason)` record (`PIPELINE_RULES.md` §2–§4). It is never an `assert`, because `python -O` removes assertions.
2. **Must:** each public function checks the contracts whose failure would silently corrupt a result. These are physical invariants (energy balance, sign, range), units, and time continuity. A check that repeats one the type system or a caller already makes is not required.
3. **Prefer:** `assert` only for conditions that can fail only if the code itself is wrong.
4. **Must:** exceptions are specific and named in their module (`ManifestMismatch`, `MissingSettlementPeriod`). No bare `except` and no `except ...: pass`. `except Exception` is allowed only at a retrieval boundary that records the failure with its reason and carries on.
5. **Must:** meaningful results and errors are handled. A return value discarded on purpose is assigned to `_`.

## 4. Determinism

`PIPELINE_RULES.md` §8 requires byte-identical outputs from the same inputs and code. In code, that means:

1. **Must:** every collection is sorted with an explicit key before it is iterated for output or written: `sorted(paths)`, units by ID, records by (unit, time).
2. **Must:** nothing depends on filesystem listing order, API response order, or set and dict ordering that came from unsorted input.
3. **Must:** JSON is written with `sort_keys=True` and a fixed float format, and CSV with a fixed column order.
4. **Must:** no output contains the current time, a random value, or an absolute path, except a manifest's download time.

## 5. Retrieval, files and the network

1. **Must:** every loop is bounded. `for` runs over a finite collection. A `while` loop (paging, retries, polling) has an explicit cap and raises when it reaches it.
2. **Must:** an HTTP request makes at most four attempts: the first, then up to 3 retries after waits of 2, 4 and 8 seconds. Each attempt times out after 60 seconds. Retries are for timeouts, connection errors, HTTP 429 and 5xx only; any other 4xx fails at once.
3. **Must:** each request logs source, scope, destination, row count and UTC time, and never a credential, token or request header. A request that still fails is recorded, not hidden.
4. **Must:** retrieval is segmented, by day or by month, never one giant request. A failed run keeps the segments it finished and resumes from the first missing one.
5. **Must:** files are written atomically. Write to a temporary file in the same folder, check it (it parses, and its row count and time span are as expected), then rename it into place. The manifest row is written last, so a partial download can never be mistaken for a complete one.
6. **Must:** a raw file is reused only if its SHA-256 matches its manifest row (`DATA_SOURCES.md`, vintage policy). A mismatch raises; it never triggers a silent re-download. A new download is a new vintage, with its own manifest row (`PIPELINE_RULES.md` §7).
7. **Must:** a pull states its scope and size before it starts.
8. **Prefer:** official access (the BMRS API, NESO CKAN, published files) before scrapers or session handling.

## 6. Forbidden

**Must not:** `eval`, `exec`, monkeypatching, dynamic imports, `inplace=True`, or global `numpy.random` calls. Passing a function as an argument is allowed where the design needs it, such as the synthetic declarers, and nowhere else.

## 7. Tests

1. **Must:** pytest, with warnings treated as errors. No test touches the network; external calls are mocked.
2. **Must:** tests cover every pre-registered definition, every check in §3, and every path that produces `excluded(reason)`.
3. **Must:** each data function is tested with valid input, and with empty and malformed input wherever the real source can produce them.
4. **Must:** physics is tested against hand-worked examples, with the working in the test's docstring.
5. **Must:** the known-answer suite runs in CI and fails the build when a band in `PREREGISTRATION.md` §8 is missed (`PIPELINE_RULES.md` §12).
6. **Must:** each new package keeps at least 80% line coverage. This is a floor that flags untested code, not a target; rules 2–4 decide what is tested.

## 8. Tools

The same commands run locally and in CI, and CI fails on any finding:

| Tool | Job | Scope |
|---|---|---|
| `ruff format` | Formatting, black style, 88 characters | Every file not exempt |
| `ruff check` | Lint, import order, common bugs | Every file not exempt |
| `mypy` | Strict type checking | Packages listed under `[tool.mypy] files` in `pyproject.toml`; each new package is added when it is created |
| `pytest` | Tests, warnings as errors, coverage | All tests; coverage for new packages |

## 9. Notebooks

Notebooks explore and illustrate; they never produce a published number. Every published number comes from `src/` against pinned manifests (`PROJECT.md` §3.5).

- **Must:** name notebooks `NN_descriptive_name.ipynb`.
- **Must:** open with objective, inputs and outputs, and close with a summary.
- **Must:** run top to bottom without error (`jupyter nbconvert --to notebook --execute`), and have outputs cleared before committing.
- **Must:** a notebook that shows per-unit results stays out of the repository until right of reply ends (`PROJECT.md` §7a).
- **Prefer:** past about 500 lines, move reusable code into `src/`.

## 10. Figures

1. **Must:** axes and values carry physical units (MWh, MW, minutes) wherever they help a reader.
2. **Must:** no version 1 figure identifies a BM unit, by name, ID or a label that points to one (`PROJECT.md` §7a).
3. **Must:** every saved figure has a caption giving what it shows, the data source with its licence attribution, and the date range.
4. **Must:** palettes are colourblind-safe.
5. **Prefer:** Tufte's principles: maximise the data-ink ratio, label directly, use colour only to encode information, keep axes honest. No 3D, gradients, shadows or decorative legends.

```python
import matplotlib as mpl

mpl.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "font.family": "sans-serif",
        "font.size": 11,
        "legend.frameon": False,
    }
)
```

## 11. Commits

- **Must:** messages take the form `type: short description`, where type is one of `feat`, `fix`, `data`, `docs`, `test`, `refactor` or `chore`. Example: `feat: Claim 1 weekly error ratio (PREREGISTRATION §4)`.
- **Must:** commits are authored "Andy Moran" <andrewgmoran@proton.me>, with no AI co-author or session trailer lines. AI help is disclosed in the README's AI use statement.
- **Must:** stage files by name (`git add <file>`), never with `git add -A` or `git add .`, so nothing enters a commit unreviewed.
- **Must not:** commit secrets, raw data, or per-unit outputs before right of reply.

## Exceptions

A **must** rule is broken only when following it would make the code wrong or clearly worse.

1. **Mark it in the code.** A comment on the line, or above the function: `# CODING-EXCEPTION §3.2: <reason>`. A tool suppression (`# noqa: E501`, `# type: ignore[...]`) carries its reason on the same line.
2. **Approval.** Andy approves every exception, in review, before the commit.
3. **Lasting exceptions are logged.** An exception that covers a whole file or package, or more than one function, also gets a decision-log row in `PROJECT.md` §11.
4. **Temporary exceptions name their end.** The comment states the condition that removes it: `until the scoring-window pull exists`.

## Checklist before commit

```bash
uv run ruff format .
uv run ruff check .
uv run mypy      # checks the packages listed in pyproject.toml
uv run pytest
```

- [ ] Does every new public function have type hints, a docstring and a § reference where one applies?
- [ ] Does it check the contracts that could silently corrupt a result?
- [ ] Is every collection sorted before it is written?
- [ ] Any `while` loop without a cap? Any `except` that hides a failure?
- [ ] Any number in the code that belongs in `config/claims.toml`?
- [ ] Is every exception marked, approved and, if lasting, logged?

## Example

The earlier project's cache rule, as written there:

```python
def load_or_download(cache_path: Path, download_fn):
    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception:
            logger.warning(f"Invalid cache: {cache_path}")
    df = download_fn()
    df.to_parquet(cache_path, index=False)
    return df
```

As this repository writes it:

```python
class ManifestMismatch(Exception):
    """A raw file's bytes do not match its manifest row."""


def load_raw(path: Path, expected_sha256: str) -> bytes:
    """Return a raw file's bytes, checked against its manifest hash.

    DATA_SOURCES.md, vintage policy. A missing file raises FileNotFoundError.
    """
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ManifestMismatch(
            f"{path}: {digest[:12]} != manifest {expected_sha256[:12]}"
        )
    return data
```

The first version catches every exception, logs a warning and downloads again. A corrupted file is silently replaced by a new vintage, and the analysis never learns that its inputs changed. The second version checks the file against the hash recorded when it was downloaded, and stops when they differ. Downloading is a separate, deliberate step that writes its own manifest row.

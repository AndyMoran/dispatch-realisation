# Pipeline Rules

How the code in `src/` is built. Each rule is a lesson learned the hard way on an earlier project, restated for a data pipeline.

For: anyone writing or reviewing code in this repository.

---

## 1. Enforce checks in the pipeline, not in the reading

Any check that matters is an assertion in `src/` that stops the run: units, value ranges, row counts, energy balance, and Gate B's reproduction of NESO's aggregate skip rate. A chart that looks wrong is a prompt to investigate, not a check.

## 2. Fail visibly; define the failure before the success

Before writing a step's happy path, decide what it outputs when it fails. API errors, missing settlement periods and unparseable files produce explicit records with a reason. Nothing is dropped silently. Every run writes a coverage report: what was requested, what arrived, what was excluded and why.

## 3. Excluded is not deleted

A unit that can't be scored stays in the published table as "not scored", with its reason. It never counts in a denominator. Readers can see who is missing and why, which matters for a ranking that names parties.

## 4. Make invalid states unrepresentable

Each record carries exactly the fields its stage has produced:

`raw → validated → reconstructed → scored`, or `excluded(reason)` at any point.

Enforce this with schemas (e.g. pandera or pydantic). A "scored" unit without a mass-balance result fails validation rather than reaching a table.

## 5. Each stage writes a complete output

Every stage's output is a valid end state, not a half-finished one. A rerun resumes from the last complete stage rather than starting over.

## 6. Version every stored format from first use

Output tables, manifests and intermediate files carry an explicit schema version from the first release, with a stub migration path. Keep the version identifiers separate:

| Identifier | Versions |
|---|---|
| Git tag | Code |
| Manifest | Data vintage |
| Schema version | Output table format |
| Zenodo deposit | Pre-registration |

A change to one does not imply a change to the others.

## 7. Never re-derive a number to verify it

Upstream data revises: B1610 settlement runs, BOD, NESO reissues. A fresh pull can legitimately produce a different number. Verify a published figure against its pinned run (manifest + code tag + output hash), not against a new download. A fresh pull is a new version and is reported as one.

## 8. Deterministic by construction

Sort inputs, fix random seeds, pin library versions, and set bins and windows explicitly. The same inputs and code must give byte-identical outputs. CI tests this.

## 9. Check the property, not the label

Identify things from the data, not from names or announcements:
- A unit's adoption date is its first observed MDO submission, not NESO's scheduled date.
- A battery is identified by fuel type and behaviour, not a BMU ID prefix.
- An optimiser is identified from evidence per unit, not assumed from the lead party's name.

## 10. Declare degraded modes in the output

When a planned input is missing (FSoE unpublished, Gale anchor unverified, grace-period date unknown), the output records which mode it ran in, as a field, not a footnote. Leave a component out rather than filling it with a placeholder.

## 11. State what each number shows and doesn't show

Keep a claims map: for each published output, what it supports and what it doesn't. Example: a declaration-quality score shows how well a unit's declarations match its metered physics. It doesn't show optimiser skill, revenue or intent.

## 12. Hard limits fail the build; everything else is monitored

CI fails on schema violations, non-determinism and the Gate B tolerance. It tracks run time and data volume without failing on them.

## 13. Derive, don't maintain in parallel

Field tables in the documentation are generated from the schema code. The published table's format is derived from the internal one. Two hand-maintained copies of a structure drift apart.

## 14. Retiring something means sweeping every reference

A retirement is done when the decision log has an entry *and* a search of all code and documents for the retired term comes back clean.

## 15. Deferred is not cut

Every out-of-scope item is labelled either **deferred** (with what would bring it back) or **cut** (with the reason).

# R10 licence check — result

For: a reviewer checking that the project may publish a per-unit derived table.

Checked 23 October 2026 against the licence pages themselves. This is a reading of the licence terms, not legal advice.

## Finding

**BMRS data: permitted.** Elexon's licence allows a per-unit derived table, including commercial use, provided the table carries Elexon's attribution and does not misrepresent the data or imply endorsement.

**NESO data: permitted.** The Skip Rates dataset, including its In Merit All BM monthly files, is published under the NESO Open Data Licence. The same conditions apply: attribution and no implied endorsement.

**Neither licence settles whether naming units is safe.** They grant copyright and database rights only. The legal review of naming and framing in PROJECT.md §7a still stands.

## BMRS data — Elexon, "Copyright: Licence to use BMRS open data"

Covers every BMRS dataset this project uses: MDO, MDB, MELS, MILS, PN, BOAL/BOALF, BOD, B1610, MID and reference data. Applies to anyone who is not a BSC Party.

- **Grant:** worldwide, royalty-free, perpetual, non-exclusive.
- **Permits:** copying, publishing, distributing, adapting, and commercial use, including in your own product.
- **Unit-level data:** no restriction. The only data-type exclusion is personal data. BM units belong to companies, so it does not apply.
- **Attribution (exact):** "Contains BMRS data © Elexon Limited copyright and database right [year]." Link to the licence where possible.
- **Conditions:** do not imply official status or Elexon endorsement; do not mislead others about, or misrepresent, the data or its source.
- **Breach:** rights end automatically.
- **Versioning:** Elexon may issue new versions, but use may continue under the version licensed. No version number is shown; page dated 20 June 2024.
- **Residual point:** the licence excludes third-party rights Elexon cannot license. MDO/MDB originate with participants and reach BMRS through NESO under P499. Nothing suggests a restriction, but the exclusion exists.

## NESO data — "National Energy SO Open Data Licence v1.0"

- **Basis:** Open Government Licence v3.0, amended for NESO. NESO states it is compatible with CC BY 4.0.
- **Permits:** copying, publishing, adapting, commercial use, combining with other data.
- **Attribution (exact):** "Supported by National Energy SO Open Data"
- **Conditions:** do not imply official status or NESO endorsement.
- **Scope:** applies only to datasets explicitly associated with it.
- **Versioning:** NESO may revise the licence at any time without notice; continued use counts as acceptance.

**Skip-rate datasets:** the Skip Rates dataset page gives its Rights as "NESO Open Data Licence", set at dataset level. No resource carries a different licence, so the monthly In Merit All BM files are covered. Individual file pages do not show the licence; the dataset page does. Confirmed 23 October 2026.

## Consequences for the project

1. **Every published output carries both attribution lines.** Tables and charts as well as the README. Best enforced in code, as a field written into each output (PIPELINE_RULES §10).
2. **Wording must not imply endorsement.** "Reproduces NESO's aggregate skip rate within X%" is a factual claim and fine. "NESO-validated" is not.
3. **The misrepresentation condition backs the claims map.** Derived scores must be labelled as this project's, not as Elexon or NESO data.
4. **Save the licence text at lock.** Both licences can change. Store a dated copy of each page in `docs/licences/` when the pre-registration locks.

## Sources

- Elexon, "Copyright: Licence to use BMRS open data": https://www.elexon.co.uk/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/
- NESO, "National Energy SO Open Data Licence v1.0": https://www.neso.energy/data-portal/neso-open-licence
- NESO, "Skip Rates" dataset page (Rights field): https://www.neso.energy/data-portal/skip-rates

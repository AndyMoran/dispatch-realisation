# Data Sources

All sources are public. Endpoints marked ⚠ are to be confirmed in Week 1.

## Elexon BMRS (Insights Solution API)

Base: `https://data.elexon.co.uk/bmrs/api/v1` — open, no API key.
Docs: https://developer.data.elexon.co.uk/
Licence: BMRS Data Licence Terms.

| Dataset | Use | Granularity | Note |
|---|---|---|---|
| **MDO** — Maximum Delivery Offer | Declared deliverable export energy | Per unit, time profile | From 25 June 2026 (P499). ⚠ confirm endpoint and history depth |
| **MDB** — Maximum Delivery Bid | Declared deliverable import energy | Per unit, time profile | As above |
| MELS / MILS | Power limits (pipe) | Per unit | Pre-GC0166 these carried the 30-minute rule |
| PN | Physical notifications | Per unit, per SP | Baseline position |
| BOAL / BOALF | Accepted bid-offer instructions | Per unit, per acceptance | Timestamp for redeclaration latency |
| BOD | Bid-offer prices and volumes | Per unit, per SP | Vintage-sensitive |
| B1610 | Metered generation | Per unit, per SP | Settlement data; revisions possible |
| MID — Market Index Data | Wholesale reference price for £ margin | Per SP | — |
| Reference: BM units | Lead party, fuel type | Per unit | For optimiser mapping (I4) |
| FSoE | Future State of Energy | — | ⚠ publication unconfirmed (R5) |

## NESO Data Portal

Base: `https://api.neso.energy` (CKAN). Portal: https://www.neso.energy/data-portal/skip-rates
Licence: NESO Open Data Licence.

| Dataset | Use | Note |
|---|---|---|
| Skip Rates summary | Validation target (Gate B) | Per 30 min, by stage |
| In Merit All BM (monthly files) | Unit-level skipped/accepted volume; Gate A2 crude stakes | Fields include bm_unit, fuel, bid_offer, stage, in_merit_volume_MWh, accepted_volume_MWh, skipped_volume_MWh |
| In Merit Post System Action (monthly files) | Alternative skip definition | — |

Methodology: NESO / LCP Delta skip rate methodology (v2.0, May 2025).

## Asset metadata

| Field | Candidate sources | Note |
|---|---|---|
| Node / GSP | BMRS reference data; TEC register | — |
| MW, MWh, duration | Developer disclosures; Ofgem/REPD; TEC register | Usable vs nameplate (P4) |
| Commissioning date | REPD; first BMRS activity | Proxy if missing |
| Optimiser | Press releases; lead party | Low confidence; document per unit |

## Vintage policy

1. Raw files are saved as downloaded to `data/raw/`, never edited.
2. Every pull writes a manifest row to `data/manifests/`: source, endpoint, query parameters, UTC download time, SHA-256, row count.
3. Analyses reference manifests, not "latest".
4. Known reissue: NESO reissued all skip datasets on 18 Nov 2025 to fix a long-notice-unit exclusion bug. Re-pull and compare if NESO announces further reissues.
5. BOD and B1610 are revision-prone; record settlement run where applicable.

## Week 1 checks

- [ ] MDO/MDB production endpoints return data from 25 June 2026 for battery units
- [ ] Count battery BMUs with any MDO submission; derive first-submission (adoption) date per unit
- [ ] FSoE: published or not
- [ ] Lead party → optimiser mapping: share of fleet with confident attribution
- [ ] Count units that changed optimiser since 2024
- [ ] NESO In-Merit files: confirm unit-level fields for the post-June period
- [ ] Switch-date dispersion: number of cohorts, units per cohort, post-period length for the earliest cohort
- [ ] NESO skip methodology: does the volume adjustment cap a unit's in-merit volume using its own MEL/MDO? (M1)
- [ ] Is NESO's migration schedule published? (I7)
- [ ] NESO reserve grace-period end date announced? (R9)
- [ ] BMRS and NESO licence terms permit a per-unit derived table (R10)

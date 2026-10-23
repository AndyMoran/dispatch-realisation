# Assumptions Ledger

Every assumption a result depends on, classified before results are seen.

For: a reviewer checking what this project's findings rest on.

| Category | Meaning |
|---|---|
| **GROUNDED** | Verified against a cited primary source |
| **PROVISIONAL** | Believed true, not yet verified. Names the check that would settle it |
| **DELIBERATE** | A choice made knowingly. Alternatives noted |
| **FORWARD-LOOKING** | Depends on something that hasn't happened yet |
| **OMITTED** | A factor deliberately left out. Expected bias noted |

Rules:
- A PROVISIONAL row names its check and when it runs. It is resolved or downgraded before publication.
- Update the status when evidence changes.
- Never delete a row. Strike it through and give the reason and date.

Last updated: 2026-10-23.

---

## Regulatory and data

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| R1 | GC0166 introduces MDO and MDB as dynamic parameters for limited-duration assets | GROUNDED | NESO, "GC0166 goes live"; Ofgem decision, Oct 2025 | ✓ |
| R2 | **Publication duty:** BSC modification P499 requires NESO to send MDO/MDB to BMRS for publication. Implemented 25 June 2026 | GROUNDED | Elexon P499 page | ✓ Verify production endpoint, Wk 1 |
| R3 | **Compliance duty:** Grid Code GC0166. Ofgem approved it 22 Oct 2025; legally effective 5 Nov 2025; operational from 25 June 2026. All BM units must comply by 5 Nov 2026. NESO schedules migration unit by unit with lead parties | GROUNDED | Ofgem decision; NESO implementation document; NESO reserve monitoring document (Sept 2026) | ✓ |
| R4 | NESO withholds no reserve availability payments for MDO/MDB failures until a grace period ends, no earlier than 5 Nov 2026 | GROUNDED | NESO, *Performance Monitoring of GC0166 for Reserve*, v1.0, Sept 2026 | ✓ End date not yet announced |
| ~~R5~~ | ~~FSoE is published~~ | ~~PROVISIONAL~~ | ~~Ofgem's decision names FSoE; P499's publication scope does not~~ | **Refuted 23 Oct 2026.** See R5a |
| R6 | BMRS archives MDO/MDB from 25 June 2026 and serves the history through its API | GROUNDED | One-hour sample of 1 Jul 2026; smoke test of 25–26 Jun 2026 via `/datasets/MDO/stream` and `/datasets/MDB/stream`, 23 Oct 2026 | ✓ |
| R7 | NESO In-Merit files carry skipped and accepted volume per unit | GROUNDED | NESO data portal field list (`bm_unit`, `skipped_volume_MWh`, …) | ✓ |
| R8 | NESO reissues skip datasets; vintages differ | GROUNDED | NESO reissued all skip datasets on 18 Nov 2025 to fix a long-notice exclusion bug | ✓ Pin hashes |
| R9 | NESO's reserve grace period ends inside the data window | FORWARD-LOOKING | NESO: no earlier than 5 Nov 2026 | Design 3 depends on it |
| R10 | BMRS and NESO licences allow publishing a per-unit derived table | GROUNDED | Elexon BMRS licence; NESO Open Data Licence v1.0; Skip Rates dataset Rights field. Attribution required; no implied endorsement. Licences do not clear naming (§7a). `docs/week1/r10_licence_check.md` | ✓ |
| R11 | The grace period concerns reserve availability payments only, not BM acceptances | GROUNDED | NESO reserve monitoring document (Sept 2026) covers Quick, Slow and Balancing Reserve | ✓ Limits design 3 to reserve-contracted units |
| ~~R12~~ | ~~BMRS serves MDO/MDB one settlement period per request~~ | ~~PROVISIONAL~~ | ~~Seen in a third-party API client's documentation, not Elexon's. If true, a full pull needs ~48 requests per day of data per dataset~~ | **Superseded 23 Oct 2026.** See R12a |
| R5a | FSoE is not published. NESO computes it internally for scheduling | GROUNDED | NESO, Dispatch Transparency webinar, 3 Nov 2025: FSoE data will not be published on the Elexon website | ✓ M2's degraded mode is the only mode |
| R12a | `/datasets/MDO` and `/datasets/MDB` serve one settlement period per request; the `/stream` variants take a `from`/`to` range, inclusive at both ends | GROUNDED | Elexon API spec via `gate_a1 probe`; smoke test found boundary duplicates and no gaps, 23 Oct 2026 | ✓ Pipeline uses `/stream` |
| R13 | NESO publishes ±9999 MWh defaults for units not yet switched to GC0166 | PROVISIONAL | NESO webinar FAQ, 3 Nov 2025; GC0166 Final Modification Report. None appeared in the 1 Jul 2026 sample | Gate A1: count default-valued records |
| R14 | NESO's skip-rate exclusion of units with Quick or Slow Reserve contracts changed in-merit volume for reserve-contracted batteries in summer 2026, on an unpublished date | PROVISIONAL | NESO, *Dispatch Efficiency Beyond Energy* slides, summer 2026. Affects NESO in-merit figures only, now descriptive (M7) | Ask NESO for the date |

## Measurement

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| ~~M1~~ | ~~A unit's in-merit volume in NESO files does not depend on its own MEL or MDO~~ | ~~PROVISIONAL~~ | ~~If false, accepted ÷ in-merit flatters conservative declarers. Read NESO's volume-adjustment method~~ | **Refuted 23 Oct 2026.** NESO feasible volume uses the unit's own MEL/MIL, and GC0166 parameters from 25 Jun 2026. `docs/week1/m1_denominator_check.md`. Outcome replaced: M7 |
| M2 | MDO/MDB plus metered output suffice without FSoE | DELIBERATE | Conservation and mass balance still work. Reconstruction is weaker and ranges wider | — |
| ~~M3~~ | ~~Workstream A takes its outcome directly from NESO's unit-level Tier B files~~ | ~~DELIBERATE~~ | ~~Keeps A independent of B's pipeline. Alternative: wait for B's own measurement (Wk 6)~~ | **Superseded 23 Oct 2026** by M7, after M1 was refuted |
| ~~M4~~ | ~~A unit's adoption date is its first observed MDO submission~~ | ~~DELIBERATE~~ | ~~Measured from data, not announcements (PIPELINE_RULES.md §9). Alternative: NESO's migration schedule, if published (I7)~~ | **Superseded 23 Oct 2026** by M4a: NESO publishes defaults for non-switched units (R13) |
| M5 | Units that can't be scored stay in the published table with a reason and are excluded from every denominator | DELIBERATE | PIPELINE_RULES.md §3 | — |
| M6 | B1610 and BOD values can change between settlement runs, so a rerun can differ from a published figure | PROVISIONAL | Confirm which settlement run BMRS serves and when it updates | Wk 1 |
| M4a | A unit's adoption date is its first non-default MDO/MDB submission (\|MWh\| < 9999), dated by delivery time (`timeFrom`) and binned by ISO week | DELIBERATE | PIPELINE_RULES.md §9. Alternative: date by submission time (`publishTime`), up to a day earlier; rarely changes the ISO week | Confirm before lock |
| M7 | Workstream A's outcome is accepted BM energy per registered MW per unit per week, from BMRS BOALF and PN | DELIBERATE | Declaration-independent denominator, unlike NESO in-merit volume (M1). Does not control for how often the unit was in merit; fixed effects absorb fixed differences. Definition: PREREGISTRATION.md §3 | — |
| M8 | Generation Capacity (GC) in BMRS reference data is a usable registered-MW denominator that does not move with MEL, MDO or MDB | PROVISIONAL | GC is the lead party's seasonal "maximum expected" figure, not an operational declaration. Check: field present and populated for battery units in a pinned snapshot; GC unchanged across each unit's switch date | Wk 1: `python -m src.ingest.reference` |
| M9 | Where a unit-minute has several MDO/MDB submissions, the latest by publish time and serial number is the declaration in force | DELIBERATE | 18% of records in the 25–26 Jun 2026 smoke test were superseded by redeclaration. Adoption dating uses submissions of any vintage | — |

## Economics

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| E1 | ~£12,000/MW/yr per 10-point skip increase (Gale et al.) | PROVISIONAL | Candidate source found 23 Oct 2026: "Balancing with batteries: The impact of revenue stacking and skip rates on battery energy storage profitability in Great Britain", *Journal of Energy Storage*, 2026. Authors and figure unverified: the publisher blocks automated reading | **Wk 1: read the paper in a browser** |
| E2 | E1's units are skip-rate points and convert one-to-one to acceptance points | PROVISIONAL | Check the paper's definition | Wk 1 |
| E3 | Skipped volume is valued at its cost difference from the marginal accepted action | DELIBERATE | Alternative: full LP counterfactual (cut, PROJECT.md §8) | — |
| E4 | £/MW/yr = declaration-attributable Δ accepted MWh × margin ÷ registered MW. Pay-as-bid effects ignored to first order | DELIBERATE | Full definition in PREREGISTRATION.md §4 | Finalise before lock |
| E5 | The Market Index Price is a fair stand-in for a battery's opportunity cost in the margin | PROVISIONAL | A battery's real opportunity cost depends on the price spread across periods, not one period's price. Test sensitivity with a daily-spread margin | Before lock |

## Physics

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| P1 | Honest declarations keep MDO + MDB roughly constant, near usable MWh | DELIBERATE | Energy conservation. Deviations are the signal | — |
| P2 | Round-trip efficiency is constant per unit over the window | DELIBERATE | Alternative: time-varying. Check residuals | — |
| P3 | Metered output (B1610) plus accepted BOA energy reconstructs changes in state of charge, up to an unknown offset | PROVISIONAL | Auxiliary load, ancillary-service delivery and non-BM trading may break this | Test on residuals |
| P4 | Usable MWh comes from developer disclosures; otherwise nameplate × an assumed usable fraction. Degradation not modelled in the base case | PROVISIONAL | Nameplate ≠ usable. Max(MDO + MDB) bounds usable MWh but is circular for the conservation metric, so not used there | Sensitivity analysis; flag units with no disclosed MWh |

## Identification

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| I1 | Within-unit change around the GC0166 switch separates declaration effects from fixed unit characteristics | DELIBERATE | Time-varying confounders remain | — |
| I2 | Adoption timing may be endogenous: better optimisers may have switched first | PROVISIONAL | Reclassified from "GROUNDED (logic)" on 22 Oct 2026; logic is not evidence. Test: compare pre-switch declaration and acceptance metrics across cohorts. Concern strengthened 23 Oct 2026 by I7a | Gate A1 |
| ~~I3~~ | ~~Staggered event study via Callaway–Sant'Anna or Sun–Abraham~~ | ~~DELIBERATE~~ | ~~TWFE biased under staggered timing~~ | **Superseded 22 Oct 2026** by the design hierarchy (I8–I11) |
| I4 | The lead party identifies the optimiser | PROVISIONAL | Often false: owners can be lead party with an optimiser under contract | Wk 1: map and assess |
| I5 | Adjustment set: duration, node, commissioning date, time since adoption | DELIBERATE | Telemetry spec excluded unless shown to be hardware rather than optimiser choice | — |
| I6 | Switch dates are spread out enough for a staggered design | PROVISIONAL | A mandatory deadline may compress adoption; NESO-scheduled migration may spread it | Gate A1 |
| ~~I7~~ | ~~NESO-scheduled migration limits self-selection in adoption timing~~ | ~~PROVISIONAL~~ | ~~Lead parties still agree dates with NESO. Check whether the schedule is published~~ | **Refuted 23 Oct 2026.** See I7a |
| I8 | The headline design is the first in PROJECT.md §5A's ordered hierarchy whose trigger is met, judged on declaration data only | DELIBERATE | Fixes the fallback before outcomes are seen. Lower designs run as secondary analyses only | — |
| I9 | **Design 1:** cohorts would have trended in parallel without the switch, and no other shock coincides with any cohort's switch | PROVISIONAL | Callaway–Sant'Anna or Sun–Abraham; TWFE is biased under staggered timing. Report pre-trends | If design 1 is selected |
| I10 | **Design 2:** changes in declaration quality are uncorrelated with other time-varying changes, such as pricing, given unit and period fixed effects | PROVISIONAL | Weaker than I9. Pricing changes (O1) are the main threat | If design 2 is selected |
| I11 | **Design 3:** units with different pre-shock declaration quality would have trended in parallel without enforcement | PROVISIONAL | Applies to reserve-contracted units only (R11) | If design 3 is selected |
| I7a | NESO publishes no migration schedule. Units switched as their providers became ready, so adoption timing is partly provider-chosen | GROUNDED | NESO GC0166 webinar, 15 Dec 2025: switchover for "providers that are ready"; Balancing Programme webinar, 22 Sep 2026: 39 units transitioned, no list published | ✓ Weakens I9; pre-trend tests carry more weight |

## Omitted

| ID | Factor | Category | Expected bias |
|---|---|---|---|
| O1 | Bid/offer pricing strategy | OMITTED | Biases the cross-sectional declaration effect upward, because good declarers also price well. The within-unit designs reduce this |
| O2 | Control-room operator behaviour | OMITTED | Noise, unless it correlates with particular units. Out of scope |
| O3 | Ancillary-service commitments that reserve energy | OMITTED | Makes declarations look conservative. Flag units with DC, DM, DR or reserve contracts where identifiable |

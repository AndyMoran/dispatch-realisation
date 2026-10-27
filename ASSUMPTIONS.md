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
| R15 | Elexon publishes settlement acceptance volumes (BOAV) by settlement date and period | GROUNDED | Elexon API spec: `/balancing/settlement/acceptance/volumes/all/{bidOffer}/{settlementDate}`, 23 Oct 2026. Revision-prone (M6) | ✓ Used as cross-check only (PREREGISTRATION.md §3) |
| ~~R16~~ | ~~NESO In-Merit monthly files carry Stage 6 for every month from October 2025 to September 2026~~ | ~~PROVISIONAL~~ | ~~NESO announced Stage 6 in Nov 2025 and showed Stage 6 figures for Jan–Sep 2025, but no page states when the files gained it. Fallback fixed in PROJECT.md §5A: Stage 5 for all twelve months~~ | **Refuted 23 Oct 2026.** See R16a |
| R16a | NESO In-Merit monthly files for October 2025 to September 2026 carry Stages 0–5 only. Stage 6 is published as separate datasets | GROUNDED | `gate_a2 schema`, 23 Oct 2026: distinct stage values for all 24 files, read on NESO's server, no volumes fetched | ✓ Gate A2 uses Stage 5 for all months, as the rule's fallback requires |
| R16b | Using Stage 5 instead of Stage 6 can only raise Gate A2's figure | GROUNDED | Stage 6 adds an exclusion (Mandatory Frequency Response) and removes volume; it never adds any. NESO, Dispatch Transparency webinar, 3 Nov 2025 | ✓ Disclose with the A2 result; size for batteries unknown |
| R17 | On a skipped row, NESO's `average_price_per_MWh` is the bid or offer price of that pair | PROVISIONAL | NESO's data dictionary describes the field as the average price for accepted volume; skipped rows carry it too. NESO builds its merit stack from BOD prices. Check after lock: compare a sample of skipped rows with BOD | After lock, before A2 is reported |
| R18 | Elexon's MID dataset gives price and volume per provider per half hour | GROUNDED | One-day sample, 1 Jan 2026, 23 Oct 2026: fields `startTime`, `dataProvider`, `price`, `volume`; providers APXMIDP and N2EXMIDP; `to` boundary inclusive | ✓ |

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
| M8 | Generation Capacity (GC) in BMRS reference data is a usable registered-MW denominator that does not move with MEL, MDO or MDB | PROVISIONAL | GC is the lead party's seasonal "maximum expected" figure, not an operational declaration. Snapshot 23 Oct 2026: GC populated for 3,044 of 3,127 units. Still to check: GC populated for each scored battery (M10), and unchanged across each unit's switch date | After Gate A1 |
| M9 | Where a unit-minute has several MDO/MDB submissions, the latest by publish time and serial number is the declaration in force | DELIBERATE | 18% of records in the 25–26 Jun 2026 smoke test were superseded by redeclaration. Adoption dating uses submissions of any vintage | — |
| M10 | The battery fleet is defined by behaviour: units that submit non-default MDO/MDB, excluding units whose fuel type is pumped storage (`PS`) or hydro (`NPSHYD`). Otherwise fuel type is a secondary check only | DELIBERATE | BMRS reference data has no battery fuel type; batteries sit among `OTHER` (103 units) and blank fuel type (2,537), snapshot 23 Oct 2026. PIPELINE_RULES §9. Units with `OTHER` fuel type and no MDO/MDB by the cut-off are listed for manual review, not dropped | — |
| M11 | Gate A2's denominator is MW-years of exposure: each unit's GC × the share of the window it was present | DELIBERATE | The fleet grew during the window, so dividing by start, end or a simple average moves the result. Sensitivity: September 2026 fleet GC for a full year. Units without GC leave numerator and denominator alike | — |
| M12 | MDO/MDB are net of protected volumes: energy withheld to deliver the FPN or accepted BOAs, awarded reserve volume, and response CREV | GROUNDED | NESO, MDO/MDB Industry Best Practice Guide (v3, read 27 Oct 2026): protected volume "is reflected in submitted MDO/MDB values"; worked example: MDO falls 65 → 50 MWh to protect a 15 MWh PN | ✓ Basis of D^decl and C_t (PREREGISTRATION.md §3) |
| M13 | MDO is export energy and \|MDB\| import energy, both at the meter | PROVISIONAL | The guide is silent on losses. If MDO is stored energy, η̂ enters the formulas differently; mass-balance residuals would show a slope of ~√η | Before lock: ask NESO (box.balancingprogramme@neso.energy); otherwise test the slope after lock and report |
| M14 | BMRS `publishTime` is within one minute of NESO receiving the submission | PROVISIONAL | If BMRS publication lags, metric 3 measures publication latency, not unit behaviour | Before lock: ask Elexon; otherwise report metric 3 as an upper bound |
| M15 | Protection horizon H for PN-protected energy: to the end of the current settlement period plus three | DELIBERATE | NESO, Dispatch Transparency webinar, 3 Nov 2025: BOAs must not leave the unit unable to meet PN "within the BM Window plus the SP after"; slide marks "Current SP + 3 SPs". Sensitivity: H = 6 hours, the guide's submission horizon | — |

## Economics

| ID | Assumption | Category | Source / note | Status |
|---|---|---|---|---|
| E1 | ~£12,000/MW/yr per 10-point skip increase (Gale et al.) | GROUNDED | Gale et al., "Balancing with batteries: The impact of revenue stacking and skip rates on battery energy storage profitability in Great Britain", *Journal of Energy Storage*, 2026, open access (CC BY 4.0). Abstract and §5: revenues fall roughly linearly, ~£12,000/MW/yr (about 7% of profits) per 10% rise in skip rate. A Monte Carlo simulation result, not an estimate from observed dispatch (§3.4). Data: three years to 30 Jun 2023 (§3.1), spanning the 2021–22 price crisis, so the £ level reflects crisis-era revenues. Checked 23 Oct 2026 | ✓ Comparison only: see E2a |
| ~~E2~~ | ~~E1's units are skip-rate points and convert one-to-one to acceptance points~~ | ~~PROVISIONAL~~ | ~~Check the paper's definition~~ | **Refuted 23 Oct 2026.** See E2a |
| E2a | Gale et al.'s skip rate is the share of time a battery is randomly blocked from the BM in simulation. It is neither NESO's volume-based skip rate nor this project's outcome, and converts one-to-one to neither | GROUNDED | Gale et al. (2026) §3.4: participation blocked for 5–95% of periods, chosen at random, 50 runs per step. The authors note that random timing ignores batteries' short dispatches | ✓ No £ conversion via E1; the £ estimate uses the margin in PREREGISTRATION.md §4 |
| E3 | Skipped volume is valued at its cost difference from the marginal accepted action | DELIBERATE | Alternative: full LP counterfactual (cut, PROJECT.md §8) | — |
| E4 | £/MW/yr = declaration-attributable Δ accepted MWh × margin ÷ registered MW. Pay-as-bid effects ignored to first order | DELIBERATE | Full definition in PREREGISTRATION.md §4. Denominator: GC (M7, M8) | ✓ Defined 23 Oct 2026 |
| E5 | The Market Index Price is a fair stand-in for a battery's opportunity cost in the margin | PROVISIONAL | A battery's real opportunity cost depends on the price spread across periods, not one period's price. Pre-specified sensitivity: offers valued against the day's highest MID, bids against its lowest (PREREGISTRATION.md §4) | ✓ Sensitivity fixed 23 Oct 2026 |
| E6 | Gate A2 values skipped volume against same-period MID (§4 margin), not against the marginal accepted action (E3). A2's figure is a stakes gate, not the Workstream B estimate | DELIBERATE | Keeps the gate cheap and its margin consistent with the £ estimate. Stated in PROJECT.md §5A so the two are not quoted against each other | — |

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
| I9 | **Design 1:** cohorts would have trended in parallel without the switch, and no other shock coincides with any cohort's switch | PROVISIONAL | Callaway–Sant'Anna or Sun–Abraham; TWFE is biased under staggered timing. Report pre-trends | Exploratory only: design 1 not triggered at Gate A1 (preview 27 Oct 2026; official run 30 Oct). H2 pre-specified as exploratory, PREREGISTRATION.md §4 |
| I10 | **Design 2:** changes in declaration quality are uncorrelated with other time-varying changes, such as pricing, given unit and period fixed effects | PROVISIONAL | Weaker than I9. Pricing changes (O1) are the main threat | If design 2 is selected |
| I11 | **Design 3:** units with different pre-shock declaration quality would have trended in parallel without enforcement | PROVISIONAL | Applies to reserve-contracted units only (R11) | If design 3 is selected |
| I12 | Metric 2 is normalised by throughput, which rises with accepted volume, so H3 could find a mechanical link between metric 2 and the outcome | PROVISIONAL | Pre-specified check: re-run H3 with metric 2 computed only on settlement periods without BOAs | After lock |
| I7a | NESO publishes no migration schedule. Units switched as their providers became ready, so adoption timing is partly provider-chosen | GROUNDED | NESO GC0166 webinar, 15 Dec 2025: switchover for "providers that are ready"; Balancing Programme webinar, 22 Sep 2026: 39 units transitioned, no list published | ✓ Weakens I9; pre-trend tests carry more weight |

## Omitted

| ID | Factor | Category | Expected bias |
|---|---|---|---|
| O1 | Bid/offer pricing strategy | OMITTED | Biases the cross-sectional declaration effect upward, because good declarers also price well. The within-unit designs reduce this |
| O2 | Control-room operator behaviour | OMITTED | Noise, unless it correlates with particular units. Out of scope |
| O3 | Ancillary-service commitments that reserve energy | OMITTED | Makes declarations look conservative. Flag units with DC, DM, DR or reserve contracts where identifiable |
| O4 | NESO's reserve grace-period enforcement falls outside Gate A2's window | OMITTED | Grace period concerns reserve availability payments, not BM acceptances (R11). Effect on skip value: direction unknown | — |
| O5 | Batteries that left the BM before June 2026 never submitted MDO/MDB, so fall outside the M10 fleet used by Gate A2 | OMITTED | Likely few units. A2 slightly undercounts skipped value from late 2025 | — |

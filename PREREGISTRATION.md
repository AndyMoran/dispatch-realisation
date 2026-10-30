# Pre-registration — A Physics Audit of GB Battery MDO/MDB Declarations

**Status: DRAFT — not locked.**
Version 2: scope narrowed on 30 October 2026 (§0). Lock: before any unit is scored. On lock, this status line is set to LOCKED and the locking commit is tagged `v1.0-lock`; Zenodo archives the tagged release with a DOI and timestamp. The tag identifies the commit, since a commit cannot contain its own hash.

For: a reviewer checking that the audit's methods were fixed before any unit was scored.

After lock, there is one pinned scoring run (§10). Any change to a definition or estimator after that run requires a new lock, and is recorded in §12.

---

## 0. Why it matters, and why this version differs from the last

**Why it matters.** NESO's control room often skips cheaper batteries in favour of gas. NESO's own root-cause review of skip rates rated zonal allocation, mandatory frequency response and reserve services among the strongest causes. That review concluded in April 2026, before batteries' energy declarations (MDO/MDB) were first published, and its published outcomes do not include declaration quality (ASSUMPTIONS.md R23). This audit tests that one hypothesis: whether the declarations are physically consistent with each battery's meter. It cannot apportion skips among causes, and it makes no estimate of their cost or carbon.

**Why this version differs.** 
The study set out to rank battery units on declaration quality and to estimate, in £/MW/yr, whether declaring well pays. Version 2 drops both, and audits whether each unit's declarations are consistent with its own metered physics. Three findings forced the change; each is logged with its date in PROJECT.md §11.

1. **The £ association could not be identified.** Its design compared each unit with itself over a few weeks of one regime change. That cannot exclude other changes over the same weeks, such as a new optimiser or reserve contract (ASSUMPTIONS.md I10). Reviewers on 28–30 October judged it a distraction from the measurement.
2. **A usable-energy figure (U) is missing for most units.** REPD records no MWh. SSEN's Embedded Capacity Register has a storage-MWh column, but it reads "DATA NOT AVAILABLE" for all 28 connected battery sites (November 2025 register). The Capacity Market register gives a duration class, which is a minimum, so U ≥ capacity × class (P4a, R21, R22). Without U, a level comparison cannot be scored for most units, and an adjusted ranking cannot be built on it.
3. **The tests that need no U catch under-declaration. The problem that motivates the study is over-declaration** (NESO's GC0166 proof of concept). Version 2 therefore adds Claim 3, which detects over-declaration from non-delivery, without U.
4. **Per-unit results are disclosed privately in version 1.** The claims establish physical coherence, not misconduct; M13 is unresolved under the primary claims; and the owner gets the same diagnostic from a private pack. Named publication follows only under the conditions in §11.

**Rules adapted after declaration statistics were seen.** Each used declaration or reference data only. Each is listed with what would have differed under the alternative:

| Date | Rule | Seen before it was written | Alternative and its effect |
|---|---|---|---|
| 27 Oct | H2 kept as exploratory | Gate A1 preview: design 1 failed narrowly | H2 not run. Now deferred, so moot |
| 30 Oct | Scored week = complete ISO week after the adoption week | Cohort sizes | Counting partial adoption weeks would add one short week per unit |
| 30 Oct | Registered MW: GC, else \|DC\|, else maximum MEL | 33 of 163 units with GC = 0 | GC-only would drop 23 units from the sample; now used only for one screen (§4) |
| 30 Oct | Secondary units reported separately | 25 of the GC = 0 units are type V | Pooling them would mix possible portfolios with single sites |
| 30 Oct | B1610 from the latest settlement run | The API's `settlementRunType` parameter | A fixed early run would use less-revised meter data |
| 30 Oct | Scope narrowed to this audit | U coverage (SSEN ECR, REPD, CM register) | The ranking and £ association, as in version 1 |
| 30 Oct | Claim 3 built in version 1, by a power bound whose rule was committed before it ran (f25f43a) | MDO declarations and registered MW (§5.8) | Claim 3 specified but unbuilt, as in a slim version 1 |
| 30 Oct | Per-unit results private in version 1 | No data | Named publication after right of reply and legal review |

The Gate A1 design selection (design 2, 30 October) chose a design for the £ association, which is now deferred. It is kept as history; it does not shape this audit.

## 1. Claims

| # | Claim | Tier | Needs U? | Covers |
|---|---|---|---|---|
| 1 | **Mass-balance coherence:** a unit's declarations change as its meter says its stored energy changed | Primary | No | All scored units |
| 2 | **Lower-wall violations:** a unit declares less than the energy its metered history proves it held | Primary | No | All scored units |
| 3 | **Over-declaration from non-delivery:** a unit fails to deliver energy that NESO instructed within its declared MDO | Secondary | No | Units where it is identified (§5.7) |
| 4 | **Upper-wall violations:** a unit declares more than its tank could hold | Illustrative case series | Nameplate MWh | Units with a disclosed nameplate |
| 5 | **Redeclaration latency:** how fast units update MDO/MDB after an instruction | Descriptive, fleet level | No | All units with BOAs |

- **Complementary, not independent.** A unit whose declarations do not track its meter (Claim 1) is more likely to show non-delivery (Claim 3), since both follow from declarations out of step with the battery. No composite score is formed, and no ranking is published.
- **Claims 2 and 3 are the two directions of one level test.** A unit can appear under both; that is informative, not contradictory.
- **Claim 2 detects a provable subset of under-declaration.** A unit that under-declares and also under-uses its tank does not reveal the energy it holds, and will not be flagged.

**How each claim bears on skips.** Each claim tests one way declarations could make batteries less usable to the control room. They are not tested equally well.

| Channel | Claim | How well this version tests it |
|---|---|---|
| Noise: declarations don't track the battery | 1 | Every scored unit |
| Under-declaration: the battery looks emptier than it is | 2 | The provable subset only |
| Over-declaration: the battery can't deliver what it declared | 3 | Weakest. This is the channel most tied to lost trust, and the one this version is least able to quantify. Its identification rate is reported as a result |

**What the audit can conclude.** Where it finds violations, the declarations are physically wrong. Where it finds none, there is no evidence of incoherence in the channels it can see. That is not evidence of compliance: the over-declaration channel stays open wherever Claim 3 lacks power.

**What it cannot conclude.** It measures how common violations are, not whether units with worse declarations are skipped more often; that association is deferred. It is silent on how NESO perceives declarations. Dispatch length limits Claim 3's power (§5.8); it does not confound it.

**Deferred to version 2, each with its reason:**

| Item | Reason |
|---|---|
| £ association (old H3) and £/MW/yr estimate | Not identified from within-unit variation over one regime change (§0) |
| Staggered event study (old H2) | Exploratory only, and depends on the deferred outcome |
| Adjusted ranking and composite score | Needs U for the level gate; U is missing for most units |
| Grace-period analysis (old H4) | Grace-period end not announced |
| Gate A2 (stakes) | Supports none of Claims 1–5; adds unverified assumptions (ASSUMPTIONS.md R16b, R17, O5) |
| Optimiser-level claims | Depends on the ranking; mapping unverified (I4) |
| Named per-unit publication | Conditional on the five conditions in §11 |
| Association between declaration quality and skip rates | Joins to outcomes; needs the deferred identification strategy |

## 2. Data, and what was seen before lock

**Fleet.** BM units that submitted non-default MDO/MDB between 25 June and 29 October 2026, excluding pumped storage and hydro (ASSUMPTIONS.md M10): 163 units, from the official Gate A1 run of 30 October 2026.

**Scoring window.** From each unit's adoption to Sunday 15 November 2026. Units with at least 4 scored weeks (§3) are eligible; 98 units meet that rule (`outputs/lock/lock_counts.json`). An eligible unit can still fail a claim's screens and is then listed as not scored, with the reason. Three eligible units submitted no non-default declarations after their adoption week (`outputs/lock/power_bound.json`), so they cannot be scored; a unit reverting to default values is reported as a data-quality finding. Units with fewer than 4 scored weeks are listed as not scored.

**Sources.**

| Data | Use | Claims |
|---|---|---|
| BMRS MDO, MDB (`/stream` endpoints) | Declarations | 1–5 |
| BMRS B1610, latest settlement run at the scoring run, run type recorded per period | Metered export and import | 1–4 |
| BMRS PN | Protected energy; deviations from PN | 1–3 |
| BMRS BOALF | Accepted instructions and acceptance times | 3, 5 |
| BMRS reference data, snapshot of 23 Oct 2026 (`bmunits__dl20261023T130744.json`, SHA-256 `9245d0cc…`) | Fleet, unit type, registered MW | All |
| Elexon BOAV | Validation of delivered energy | 3 |
| Disclosed nameplate MWh (§6) | Upper bound on U | 4 |

**Seen before lock.** All MDO/MDB declarations, 25 June – 29 October 2026; the reference snapshot; for one settlement period, the list of units with B1610 rows (identifiers only, no values displayed); one day of MID prices, to confirm field names; the field names and stage values of NESO's In-Merit files; and the storage columns of SSEN's Embedded Capacity Register and NESO's Capacity Market register. The Claim 3 power bound (§5.8) was computed from the declarations and the reference snapshot, after its decision rule was committed. **No PN, BOALF, BOD, BOAV or MELS data, no B1610 values and no NESO volumes were examined. No unit has been scored.**

## 3. Common definitions

**Scored week.** A complete ISO week (Monday to Sunday) after the unit's adoption week, within the scoring window, that passes the claim's screens. The adoption week never counts.

**Declarations.** MDO_t ≥ 0 and MDB_t ≤ 0 are the declarations in force at minute *t*: the latest submission for that minute (M9). MDO is a stock: the energy available for offer acceptances at that minute, net of energy protected for the PN, accepted BOAs and reserve and response contracts. NESO's guide: "MDO/MDB reflects the instantaneous energy volume available at a given minute" (M12, M17).

**Meter.** E⁺_h and E⁻_h are metered export and import in settlement period *h*, from B1610, in MWh.

**Protected PN energy.** P^exp_t and P^imp_t are the export and import energy in the unit's PN from *t* to the end of the protection horizon *H* = current settlement period plus three (M15).

**Efficiency.** η̂ = ΣE⁺ / ΣE⁻ over all the unit's complete weeks after its adoption week, before any screen. Units with η̂ outside [0.70, 0.98] are not scored on Claims 1–4, and are listed with that reason.

**Two readings of MDO (M13).** *Branch A:* MDO is export energy at the meter. *Branch B:* MDO is stored energy, so deliverable export energy is √η̂ × MDO, and import headroom at the meter is |MDB| ÷ √η̂. Every result is computed under both branches. A flag is published only if it holds under both (§9).

**Declared deliverable energy.** D^decl_t = MDO_t + P^exp_t (Branch A; under B, √η̂ × MDO_t + P^exp_t). This is the energy the unit says it could export if fully discharged, protection included.

**Reconstruction ("tank walls").** Exporting *y* MWh lowers deliverable energy by *y*; importing *x* MWh raises it by η̂·*x*. Within week *w*, K_t = Σ_{h<t} (η̂·E⁻_h − E⁺_h), the cumulative change since the week began. The tank holds D_0 + K_t for an unknown starting level D_0 ≥ 0, and D_0 + K_t ≥ 0 at every *t*. So at every *t* it holds at least **L_t = K_t − min K**, the lower wall. The lower wall uses metered energy only, never declarations, and needs no U.

**Registered MW.** GC if positive, else |DC|, else the unit's maximum MEL over the window (M16). Used only for the idle-week screen (§4).

**Secondary units** (BMRS type V, registered by Virtual Lead Parties) may cover one site or several. They are scored, but reported in a separate table marked "secondary unit: may be aggregated" (R19, R20).

**Sign and protection conventions.** Accepted energy and delivered energy are both measured as deviations from PN. *E*_available, MDO and D^decl are all net of protection. No ratio mixes the two conventions.

## 4. Claims 1 and 2 (primary)

**Claim 1: mass-balance coherence.** For each settlement period *h*: r_h = ΔD^decl_h − (η̂·E⁻_h − E⁺_h), with ΔD^decl_h taken from the start of *h* to the start of *h*+1. Following a PN, delivering a BOA, charging and resubmitting a PN all change both terms alike, so honest declarations give r_h ≈ 0.

- **Weekly score:** the error ratio Σ_h |r_h| / Σ_h (E⁺_h + E⁻_h). *Secondary:* the signed ratio Σ_h r_h / Σ_h (E⁺_h + E⁻_h); positive means declarations rose faster than the physics allows.
- **Screens.** A week with any settlement period missing B1610 is unscored. Weeks with throughput below registered MW × 1 hour are unscored as idle. Periods in which an identified reserve or response contract starts or ends are excluded (I13).
- **What else enters r_h:** changes in unobserved reserve or response protection (O3); a unit protecting PN energy beyond *H* (sensitivity *H* = 6 hours); auxiliary load, which η̂ absorbs on average but not in timing (P3). None of these is an error by the unit, and all three push Claim 1 towards incoherence.
- **Level-blind by construction (I14).** A constant error in level cancels out of r_h. Levels are tested by Claims 2–4.

**Claim 2: lower-wall violations.** At the start of each settlement period, a violation occurs when D^decl_t < L_t − τ_w, where τ_w = 0.02 × (max K − min K) for the week, a tolerance for metering error. The unit has declared less than the energy its meter proves it held.

- **Weekly score:** the share of settlement periods in violation.

**Unit scores.** The median of the unit's scored weeks, with a 95% interval from resampling its days (1,000 draws).

**Flag categories** (thresholds fixed here; sensitivity in §9):

| Claim | Category | Rule on the 95% interval of the unit's score |
|---|---|---|
| 1 | Coherent | Upper bound ≤ 0.05 |
| 1 | Incoherent | Lower bound ≥ 0.15 |
| 1 | Indeterminate | Otherwise |
| 2 | Provable under-declaration | Lower bound ≥ 0.05 |
| 2 | None detected | Otherwise |

**Reliability.** For Claims 1 and 2, each unit's score is computed separately on odd and even calendar days. The Spearman correlation of the two across units, stepped up by the Spearman–Brown formula, is the claim's reliability. If its 95% interval (unit bootstrap) lies wholly below 0.5, the claim's flags are reported as unreliable and not given per unit, in private packs or later. If the interval straddles 0.5, flags are given with that stated.

## 5. Claim 3 (secondary): over-declaration from non-delivery

**The physics.** If NESO accepts an offer within a unit's declared MDO and the unit runs out of energy partway through, it delivers what it actually had: delivered = min(accepted, *E*_available). An honest unit delivers in full up to the MDO it declared. An over-declaring unit falls short once the instruction exceeds what it really held.

**Instruction sizing.** NESO states that since GC0166 "MDO/MDB Data is used to calculate what BOA volume can be issued", and that it "will utilize these values to determine the volume of Offers or Bids that can be dispatched within the BM window" (M18). Instructions are therefore sized up to the declared MDO, which is the regime in which Claim 3 has power.

**Regime.** Every instruction Claim 3 scores falls after the unit's adoption week, so under GC0166 for that unit. Instructions under the 15- or 30-minute rule are never scored, because the unit then had no MDO to test against (ASSUMPTIONS.md R25).

### 5.1 Quantities, per instruction

- **Accepted energy *A*:** over the instruction's settlement periods, the integral of (BOALF level − PN).
- **Delivered energy *D*:** over the same periods, Σ (metered − PN), minus the unit's frequency-response baseline (§5.3).
- **r = *A* ÷ MDO in force at the acceptance time.** Under Branch B, MDO is replaced by √η̂ × MDO.
- **Delivery ratio ρ = *D* ÷ *A*.**

Offers use MDO and export. Bids are mirrored with |MDB| and import, and reported separately.

### 5.2 Screens

- Only instructions whose settlement periods hold no other BOA for the unit, because B1610 is half-hourly.
- Only instructions with *A* ≥ 1 MWh, where ρ is well defined.
- **r > 1 is classified, not fitted.** Instructions sized to MDO cannot produce r > 1 unless MDO changed between issue and acceptance, which is a redeclaration-timing effect. Its frequency is reported per unit and compared with Claim 5.

### 5.3 Frequency-response baseline

Batteries delivering frequency response deviate from PN without any BOA. For each instruction, the baseline is the unit's median (metered − PN) in settlement periods without a BOA, in the same ISO week and at the same settlement period of the day, scaled to the instruction's duration.

### 5.4 Two models, fitted per unit

*E*_available is the energy actually deliverable at acceptance, net of protection. Over-declaration is either proportional or additive:

- **Proportional:** *E*_available = (1 − *f*) × MDO, so ρ = min(1, (1 − *f*)/r). *f* is the fraction of declared MDO that was not deliverable.
- **Additive:** *E*_available = MDO − Δ, so ρ = min(1, (MDO − Δ)/*A*). Δ is a constant over-declaration in MWh.

Each model is fitted by least squares over a grid (*f* in [0, 0.9] in steps of 0.01; Δ from 0 to the unit's median MDO in steps of 0.1 MWh), with a 95% interval from resampling instructions within the unit (999 draws). The piecewise-linear breakpoint of ρ against r is reported alongside, as a check that the result is not an artefact of the functional form.

### 5.5 Specification checks

- **Slope check.** Beyond the fitted kink, log ρ against log r should fall with slope about −1. A unit whose slope lies outside [−1.5, −0.5] is reported as "model rejected", without an estimate.
- **Separability.** The two models differ only if MDO varies across the unit's instructions. Where the interquartile range of MDO at acceptance is below 25% of its median, the models are reported as "not separately identified", and the flag rests on the proportional fit and the slope check alone.
- **Transition width.** The spread of r over which ρ falls from 0.95 to 0.75, reported as a diagnostic. A wide transition suggests over-declaration varies between instructions.

### 5.6 Placebo

Where the lower wall proves the tank held at least the accepted energy (L_t ≥ *A* at acceptance), a shortfall cannot be over-declaration. It must come from frequency response, a ramp limit or a trip. These instructions form a **placebo set**, available for every unit, since the lower wall needs no U. Each unit's models are also fitted on its placebo set alone.

### 5.7 Identification and flags

**Identified:** at least 15 eligible instructions with r ≥ 0.5, and the slope check passes. **The identification rate**, identified ÷ scored units, is a first-class result, reported with Claim 3's findings.

**Flagged as over-declaring** only if all four hold:

1. The unit is identified.
2. Both models' 95% intervals exclude zero; or, where they are not separately identified, the proportional fit's interval does.
3. The placebo fit's interval for *f* includes zero.
4. The flag holds under both M13 branches.

Reported per unit: *f̂* and Δ̂ with intervals, the identification diagnostics, the placebo fit, and the frequency of r > 1.

### 5.8 Power, selection and scope

r approaches 1 only when the declared stock is small relative to what one instruction can draw: in practice, near-empty states. How often a unit is near-empty depends on its own state-of-charge management, which may relate to declaration quality.

**Power bound, computed before lock** (`src/ingest/power_bound.py`; rule committed in f25f43a before the first run). A unit is *potentially identifiable* if at least 10% of its declaration-minutes after its adoption week satisfy 1 MWh ≤ MDO ≤ 2 × MW × 60 min, so that a one-hour full-power instruction could reach r ≥ 0.5. Claim 3 is built in version 1 if at least 30 of the 98 eligible units are potentially identifiable. **Result: 71 of 98; 67 of 73 non-secondary units** (ASSUMPTIONS.md R26).

- The bound is a necessary-condition screen on effort, not a test of validity. It bounds the r that instructions could reach, not the r they reached. The realised distribution is a scoring-run output and can be worse, if NESO rarely issues instructions near a small MDO. Since NESO sizes instructions from MDO (M18), it should track the bound where the bound is met. The identified set can be no larger than the potential set.
- The result barely varies across T = 30–90 minutes and K = 1–2. It rules out a Claim 3 that is thin by construction; it says little about how thin it will be in practice.
- 21 of 25 secondary units have no registered MW and counted as not identifiable. Claim 3's evidence on secondary units will be thin.

**Power derating near empty.** Batteries usually cannot deliver full power at low state of charge (P6). An honest unit can then fall short for want of power, not energy, which mimics the kink. The placebo set (§5.6) catches this only where the lower wall is tight near empty, so the known-answer suite includes a derating battery (§8).

**Composition of the identified set.** Reported beside the identification rate: by duration proxy (median MDO + |MDB| ÷ registered MW), by unit type, and by Claim 1 score against all scored units. Short-duration units and deeply depleted states are expected to dominate. This skew and the selection concern below are the same phenomenon seen from two sides (I16).

- **Scope of the claim:** over-declaration that shows when the declared stock is close to what one instruction can draw. Not over-declaration in general.
- **Selection check:** the Claim 1 scores of identified units are compared with those of all scored units. A difference is reported as evidence of selection.
- **Reported by r:** *f̂* within bands of r, so a reader can see where the evidence comes from.

### 5.9 Validation against BOAV

Delivered energy *D* is compared with Elexon's settlement acceptance volumes (BOAV) for the same instructions, where available. The agreement is reported. *D* stays as defined whatever the comparison shows.

### 5.10 Promotion to primary in version 2

Claim 3 may be promoted only if all of these hold, judged on version 1's pinned run:

1. The identification rate is at least 30% of scored units.
2. No flagged unit shows a kink in its own placebo set, and the fleet's placebo shortfall rate (placebo instructions with ρ < 0.9) is at most 10%.
3. Where Claims 3 and 4 can both be estimated for the same unit, their over-declaration estimates agree within their intervals for at least two-thirds of such units, with at least 3 units compared.
4. Every Claim 3 band in the known-answer suite (§8) is met.

Statistical significance alone never promotes Claim 3. Promotion does not depend on how many units are flagged, so it cannot reward finding over-declaration.

## 6. Claim 4 (illustrative case series): upper-wall violations

**Why nameplate.** Usable energy cannot exceed nameplate energy, so a disclosed nameplate *N* is an upper bound on U. The tank then holds at most *N* − (max K − K_t) at time *t*. A unit declaring more than that over-declares, provably.

- **Violation:** D^decl_t > *N* − (max K − K_t) + 0.02 × *N*, at the start of a settlement period. Weekly score: the share of periods in violation, with the size of the excess in MWh.
- **Physics-inconsistent week:** max K − min K > 1.02 × *N*. Reported, and the unit's other results are marked "check nameplate".

**Search protocol, time-boxed to two working days.** For each scored unit: the owner's or developer's press releases and annual reports, and planning documents that state MWh. Matched by site name and GSP group. Each match records the source URL, its date and the matching evidence. Units are searched in descending order of registered MW; the order and the stopping point are reported.

**Use.** Claim 4 validates Claim 3 on units where both can be estimated (§5.10, item 3). It is not a fleet result. Units that disclose a nameplate may differ from those that do not, in a direction that is unknown; the case series says so.

## 7. Claim 5 (descriptive): redeclaration latency

For each BOA, L = minutes from the BOALF acceptance time to the unit's first MDO or MDB submission with publishTime at or after acceptance (M14). Censored at the unit's next acceptance or 30 minutes, whichever comes first.

- **Reported at fleet level:** the distribution of L, and the share of BOAs with L ≤ 1 minute, NESO's benchmark.
- **Per unit:** only in each lead party's private pack, and not published in version 2 either, because publishTime may record BMRS publication rather than receipt (M14).
- **Cross-check:** units that redeclare slowly should show more r > 1 instructions (§5.2). Agreement is reported; disagreement means one of the two measures something else.

## 8. Known-answer tests

Synthetic batteries with planted faults run in CI before any real unit is scored. Each must land in its band, or the build fails. Common settings: U = 100 MWh, η = 0.88, two cycles a day, PN-following with BOAs. Claim 3 runs under three instruction-sizing regimes: (i) sized to MDO; (ii) sized to MEL × duration; (iii) sized to PN deviation only.

| Synthetic unit | Claim 1 | Claim 2 | Claim 3, regime (i) | Claim 3, regimes (ii), (iii) |
|---|---|---|---|---|
| Honest | Coherent | None detected | Not flagged | Not flagged |
| Honest, with frequency-response noise | Coherent | None detected | Not flagged | Not flagged |
| Honest, ramp-limited | Coherent | None detected | Not flagged | Not flagged |
| Constant over-declaration, Δ = 10 MWh | Coherent (level-blind) | None detected | Flagged; Δ̂ in [7, 13] MWh | Detection rate reported |
| Proportional over-declaration: declares 1.25 × available (*f* = 0.2) | Incoherent | None detected | Flagged; *f̂* in [0.15, 0.25] | Detection rate reported |
| Static profile copied from maximum | Incoherent | None detected | Flagged, or not identified | Reported |
| Redeclares 5 minutes after each BOA | Coherent or indeterminate | None detected | Not flagged; r > 1 frequency raised | Reported |
| PN protection ignored | Incoherent | None detected | Reported | Reported |
| Constant under-declaration, 20 MWh | Coherent (level-blind) | Provable under-declaration | Not flagged | Not flagged |
| Honest, power derates linearly to 50% below 20% state of charge | Coherent | None detected | Not flagged | Not flagged |

Across 100 simulated runs of each, the four honest batteries are flagged by Claim 3 at most 5% of the time under any regime. Under regime (i), the two over-declarers are flagged at least 80% of the time. If the suite cannot meet these bands, Claim 3 is dropped from version 1, and the report says so.

Bands are fixed here. The scoring code is written after lock, so a band or a definition may be revised only before the first real unit is scored. Each revision is logged in §12 with its date, the diff and a certification that no score for any real unit had been computed or seen. After the first real unit is scored, bands are frozen.

## 9. Sensitivity

Each published flag is recomputed under:

- M13 Branch A and Branch B;
- *H* = current period + 3, and *H* = 6 hours;
- η̂ bounds [0.70, 0.98] and [0.65, 0.99];
- Claim 1 thresholds at ±50% (0.025 and 0.075; 0.075 and 0.225); Claim 2 threshold at 0.025 and 0.10;
- Claim 3's identification minimum at 10 and 25 instructions.

A sensitivity table is published with the flags. **A flag that changes under either M13 branch or either *H* is published as "not robust", not as a finding.** Changes under the threshold variants are shown in the table.

## 10. Scoring discipline

- One pinned scoring run after lock: data manifests, code tag and output hashes recorded. Lead parties receive results from that run, and their responses are recorded against it.
- Past declarations cannot change. What can change is data, through B1610 revisions, NESO reissues or a demonstrated error. Later revisions are not re-scored, except to fix a demonstrated error, which restarts the reply clock.
- Claim 3 runs as a separate module from Claims 1 and 2. If Claim 3 fails its own tests, Claims 1 and 2 stand unchanged.

## 11. Publication commitments

- Results are published whether they show problems or not.
- **Published openly in version 1:** fleet-level results for every claim, the known-answer and reliability results, Claim 3's identification rate and diagnostics, the sensitivity table at fleet level, the method and the open pipeline, so any operator can run the checks on its own units.
- **Disclosed privately in version 1:** each lead party receives, for its own units only, the flags, Claim 1 score and interval, lower-wall status, Claim 3 results where identified, latency, and the method. No unit is named publicly in version 1.
- **Named publication, in version 2 only, requires all five:** (i) M13 resolved in writing; (ii) one clean pinned scoring run with no estimator changes; (iii) Claim 3's promotion outcome recorded (§5.10); (iv) right of reply completed for every named unit, with at least 10 working days; (v) legal review cleared. Until all five hold, per-unit results go to the lead party only.
- The claim attached to each unit, privately or publicly, is "its declarations are, or are not, physically consistent with its meter", not "this unit is a poor declarer". Flags are sorted by Claim 1 but not called a ranking.
- The data-quality findings are published in their own right: in SSEN's November 2025 register, the storage-MWh field read "DATA NOT AVAILABLE" for all 28 connected battery sites; REPD records no storage MWh; the Capacity Market register gives minimum durations, without BM unit identifiers.

## 12. Deviations log

| Date | Deviation | Reason |
|---|---|---|
| | | |

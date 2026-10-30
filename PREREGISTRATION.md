# Pre-registration — A Physics Audit of GB Battery MDO/MDB Declarations

**Status: DRAFT — not locked.**
Revision 2 of this pre-registration: scope narrowed on 30 October 2026 (§0). The audit it governs is release version 1; the locking commit is tagged `v1.0-lock`, and Zenodo archives the tagged release with a DOI and timestamp. The tag identifies the commit, since a commit cannot contain its own hash. Lock: 5 November 2026 (6 November if the contract-coverage mapping overruns) — after `outputs/lock/contract_coverage.json` exists, and before any unit is scored. On lock, this status line is set to LOCKED.

For: a reviewer checking that the audit's methods were fixed before any unit was scored.

After lock, there is one pinned scoring run (§10). Any change to a definition or estimator after that run requires a new lock, and is recorded in §12.

---

## 0. Why it matters, and why this revision differs from the last

**Why it matters.** NESO's control room often skips cheaper batteries in favour of gas. NESO's own root-cause review of skip rates rated zonal allocation, mandatory frequency response and reserve services among the strongest causes. That review concluded in April 2026, before batteries' energy declarations (MDO/MDB) were first published, and its published outcomes do not include declaration quality (ASSUMPTIONS.md R23). This audit tests that one hypothesis: whether the declarations are physically consistent with each battery's meter. It cannot apportion skips among causes, and it makes no estimate of their cost or carbon.

**Why this revision differs.** The study set out to rank battery units on declaration quality and to estimate, in £/MW/yr, whether declaring well pays. Revision 2 drops both, and audits whether each unit's declarations are consistent with its own metered physics. Three findings forced the change, and one disclosure decision shaped it; each is logged with its date in PROJECT.md §11.

1. **The £ association could not be identified.** Its design compared each unit with itself over a few weeks of one regime change. That cannot exclude other changes over the same weeks, such as a new optimiser or reserve contract (ASSUMPTIONS.md I10). Reviewers on 28–30 October judged it a distraction from the measurement.
2. **A usable-energy figure (U) is missing for most units.** REPD records no MWh. SSEN's Embedded Capacity Register has a storage-MWh column, but it reads "DATA NOT AVAILABLE" for all 28 connected battery sites (November 2025 register). The Capacity Market register gives a duration class, which is a minimum, so U ≥ capacity × class (P4a, R21, R22). Without U, a level comparison cannot be scored for most units, and an adjusted ranking cannot be built on it.
3. **The tests that need no U catch under-declaration. The problem that motivates the study is over-declaration** (NESO's GC0166 proof of concept). Revision 2 therefore adds Claim 3, which detects over-declaration from non-delivery, without U; it is built for release version 1 (§5.8).
4. **Per-unit results are disclosed privately in version 1.** The claims establish physical coherence, not misconduct; M13 is unresolved under the primary claims; and the owner gets the same diagnostic from a private pack. Named publication follows only under the conditions in §11.

**Rules adapted after declaration statistics were seen.** Each used declaration or reference data only. Each is listed with what would have differed under the alternative:

| Date | Rule | Seen before it was written | Alternative and its effect |
|---|---|---|---|
| 27 Oct | H2 kept as exploratory | Gate A1 preview: design 1 failed narrowly | H2 not run. Now deferred, so moot |
| 30 Oct | Scored week = complete ISO week after the adoption week | Cohort sizes | Counting partial adoption weeks would add one short week per unit |
| 30 Oct | Registered MW: GC, else \|DC\| | 33 of 163 units with GC = 0 | GC-only would drop 23 of the 98 eligible units (33 of the 163-unit fleet have GC = 0); the rule feeds screens and bounds (§3), never a claim's statistic |
| 30 Oct | Secondary units reported separately | 25 of the GC = 0 units are type V | Pooling them would mix possible portfolios with single sites |
| 30 Oct | Claim 2 scored only on certified contract-free unit-weeks (§4); coverage rule committed before it runs | I13 check: response auction results identify units by `auctionUnit`, not by BM unit ID | Subtract-where-mapped on identified contracts would leave contract periods in the denominator, biasing contracted units towards "none detected" |
| 30 Oct | B1610 from the latest settlement run | The API's `settlementRunType` parameter | A fixed early run would use less-revised meter data |
| 30 Oct | Scope narrowed to this audit | U coverage (SSEN ECR, REPD, CM register) | The ranking and £ association, as in version 1 |
| 30 Oct | Claim 3 built in version 1, by a power bound whose rule was committed before it ran (f25f43a) | MDO declarations and registered MW (§5.8) | Claim 3 specified but unbuilt, as in a slim version 1 |
| 30 Oct | Per-unit results private in version 1 | No data | Named publication after right of reply and legal review |

The Gate A1 design selection (design 2, 30 October) chose a design for the £ association, which is now deferred. It is kept as history; it does not shape this audit.

## 1. Claims

| # | Claim | Tier | Needs U? | Covers |
|---|---|---|---|---|
| 1 | **Mass-balance coherence:** a unit's declarations change as its meter says its stored energy changed | Primary | No | All scored units |
| 2 | **Lower-wall violations:** a unit declares less than the energy its metered history proves it held | Primary | No | All scored units; hard flag on contract-free weeks only (§4) |
| 3 | **Over-declaration from non-delivery:** a unit fails to deliver energy that NESO instructed within its declared MDO | Secondary | No | Units where it is identified (§5.7) |
| 4 | **Upper-wall violations:** a unit declares more than its tank could hold | Illustrative case series | Nameplate MWh | Units with a disclosed nameplate |
| 5 | **Redeclaration latency:** how fast units update MDO/MDB after an instruction | Descriptive, fleet level | No | All units with BOAs |

- **Complementary, not independent.** A unit whose declarations do not track its meter (Claim 1) is more likely to show non-delivery (Claim 3), since both follow from declarations out of step with the battery. No composite score is formed, and no ranking is published.
- **Claims 2 and 3 are the two directions of one level test.** A unit can appear under both; that is informative, not contradictory.
- **Claim 2 detects a provable subset of under-declaration.** A unit that under-declares and also under-uses its tank does not reveal the energy it holds, and will not be flagged; weeks with contract time are excluded (§4).

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

**Scoring window.** From each unit's adoption to Sunday 15 November 2026. Units with at least 4 scored weeks (§3) are eligible; 98 units met the rule at the Gate A1 run (`outputs/lock/lock_counts.json`). Eligibility depends only on the adoption week: a unit needs 4 complete weeks by 15 November, so it must have adopted by ISO week 42 (12–18 October). Every such unit is in the Gate A1 data, so the 98 is final. 95 of the 98 can be scored: three eligible units submitted no non-default declarations after their adoption week (`outputs/lock/power_bound.json`); a unit reverting to default values is reported as a data-quality finding. An eligible unit can still fail a claim's screens and is then listed as not scored, with the reason. Units with fewer than 4 scored weeks are listed as not scored. The Claim 2 contract-coverage decision (§4) is made at the lock run and not revisited.

**Eligible-set breakdown** (`outputs/lock/lock_counts.json`, `outputs/lock/power_bound.json`): 163 fleet units; 98 eligible = 73 non-secondary + 25 secondary; 95 scoreable; 71 of 98 potentially identifiable for Claim 3 (67 of 73 non-secondary); 23 eligible units have no registered MW (21 of the 25 secondary units, plus 2 others); 33 of the 163-unit fleet have GC = 0, of which 23 are among the 98 eligible. These are the same 23 units: no eligible unit with GC = 0 has a DC value.

**Sources.**

| Data | Use | Claims |
|---|---|---|
| BMRS MDO, MDB (`/stream` endpoints) | Declarations | 1–5 |
| BMRS B1610, latest settlement run at the scoring run, run type recorded per period | Metered export and import | 1–4 |
| BMRS PN | Protected energy; deviations from PN | 1–4 |
| BMRS BOALF | Accepted instructions, acceptance times, B^exp add-back (§3) | 1–5 |
| NESO response and reserve auction results | Contract mapping for Claim 1's and Claim 2's screens (§4); protection volumes where given (§9) | 1, 2 |
| BMRS reference data, snapshot of 23 Oct 2026 (`bmunits__dl20261023T130744.json`, SHA-256 `9245d0cc…`) | Fleet, unit type, registered MW (GC and DC), lead parties | All |
| Elexon BOAV | Validation of delivered energy | 3 |
| Disclosed nameplate MWh (§6) | Upper bound on U | 4 |

**Seen before lock.** All MDO/MDB declarations, 25 June – 29 October 2026; the reference snapshot; for one settlement period, the list of units with B1610 rows (identifiers only, no values displayed); one day of MID prices, to confirm field names; the field names and stage values of NESO's In-Merit files; and the storage columns of SSEN's Embedded Capacity Register and NESO's Capacity Market register — the last three consulted for the deferred work, not for any claim here. The Claim 3 power bound (§5.8) was computed from the declarations and the reference snapshot, after its decision rule was committed. The response and reserve auction results are read at the coverage run (§4), before the lock. **No PN, BOALF, BOD, BOAV or MELS data, no B1610 values and no NESO skip or in-merit volumes were examined. No unit has been scored.**

## 3. Common definitions

**Adoption week.** The ISO week containing the unit's first non-default MDO/MDB submission, dated by delivery time (`timeFrom`) (M4a).

**Scored week.** A complete ISO week (Monday to Sunday) after the unit's adoption week, within the scoring window, that passes the claim's screens. The adoption week never counts.

**Declarations.** MDO_t ≥ 0 and MDB_t ≤ 0 are the declarations in force at minute *t*: the latest submission for that minute (M9). Claim 3 is the one exception: it uses MDO as published before each acceptance (§5.1). MDO is a stock: the energy available for offer acceptances at that minute, net of energy protected for the PN, accepted BOAs and reserve and response contracts. NESO's guide: "MDO/MDB reflects the instantaneous energy volume available at a given minute" (M12, M17).

**Meter.** E⁺_h and E⁻_h are metered export and import in settlement period *h*, from B1610, in MWh.

**Protected PN energy.** P^exp_t and P^imp_t are the export and import energy in the unit's PN from *t* to the end of the protection horizon *H* = current settlement period plus three (M15).

**Efficiency.** η̂ = ΣE⁺ / ΣE⁻ over all the unit's complete weeks after its adoption week, before any screen. Units with η̂ outside [0.70, 0.98] are not scored on Claims 1–4, and are listed with that reason.

**Two readings of MDO (M13).** *Branch A:* MDO is export energy at the meter. *Branch B:* MDO is stored energy, so deliverable export energy is √η̂ × MDO, and import headroom at the meter is |MDB| ÷ √η̂. Every result is computed under both branches. A flag is published only if it holds under both (§9).

**Declared deliverable energy.** D^decl_t = MDO_t + P^exp_t + B^exp_t, where B^exp_t is the export energy of accepted BOAs above PN still to be delivered from *t* to the end of *H*, from BOALF (Branch A; under B, √η̂ × MDO_t + P^exp_t + B^exp_t). This is the energy the unit says it could export if fully discharged, with PN and accepted-BOA protection added back.

**Reconstruction ("tank walls").** Exporting *y* MWh lowers deliverable energy by *y*; importing *x* MWh raises it by η̂·*x*. Within week *w*, K_t = Σ_{h<t} (η̂·E⁻_h − E⁺_h), the cumulative change since the week began. The tank holds D_0 + K_t for an unknown starting level D_0 ≥ 0, and D_0 + K_t ≥ 0 at every *t*. So at every *t* it holds at least **L_t = K_t − min K**, the lower wall. The lower wall uses metered energy only, never declarations, and needs no U.

**Registered MW.** GC if positive, else |DC| (M16). Used for the idle-week screen (§4), the Claim 3 power bound and composition (§5.8), and the Claim 4 search order (§6); it never enters a claim's statistic directly. The 23 eligible units with neither have no registered MW: the idle screen uses a 1 MWh throughput floor, they count as not identifiable in the power bound (as it was run), and their duration proxy is reported as unavailable.

**Secondary units** (BMRS type V, registered by Virtual Lead Parties) may cover one site or several. They are scored, but reported in a separate table marked "secondary unit: may be aggregated" (R19, R20).

**Sign and protection conventions.** Accepted energy and delivered energy are both measured as deviations from PN. *E*_available and MDO are net of protection; D^decl adds PN and accepted-BOA protection back explicitly, and remains net of reserve and response protection. No ratio mixes the two conventions.

## 4. Claims 1 and 2 (primary)

**Claim 1: mass-balance coherence.** For each settlement period *h*: r_h = ΔD^decl_h − (η̂·E⁻_h − E⁺_h), with ΔD^decl_h taken from the start of *h* to the start of *h*+1. With B^exp included, following a PN, accepting and delivering a BOA, charging and resubmitting a PN all change both terms alike, so honest declarations give r_h ≈ 0.

- **Weekly score:** the error ratio Σ_h |r_h| / Σ_h (E⁺_h + E⁻_h). *Signed ratio:* Σ_h r_h / Σ_h (E⁺_h + E⁻_h); positive means declarations rose faster than the physics allows.
- **Screens.** A week with any settlement period missing B1610 is unscored. Weeks with throughput below registered MW × 1 hour are unscored as idle; for units with no registered MW, §3's 1 MWh floor applies. Periods in which a mapped reserve or response contract starts, ends or changes volume are excluded (I13; mapped as under Claim 2 below).
- **What else enters r_h:** changes in unobserved reserve or response protection (O3); a unit protecting PN energy beyond *H* (sensitivity *H* = 6 hours); auxiliary load, which η̂ absorbs on average but not in timing (P3). None of these is an error by the unit, and all three push Claim 1 towards incoherence.
- **Level-blind by construction (I14).** A constant error in level cancels out of r_h. Levels are tested by Claims 2–4.

**Claim 2: lower-wall violations.** At the start of each settlement period, a violation occurs when D^decl_t < L_t − τ_w, where τ_w = 0.02 × (max K − min K) for the week, a tolerance for metering error. The unit has declared less than the energy its meter proves it held.

- **Weekly score:** the share of settlement periods in violation.
- **Screens — whole unit-weeks, by contract status.** Claim 2 inherits Claim 1's missing-B1610 screen; idle weeks are scored (L_t ≈ 0, so idleness cannot manufacture a violation). Reserve and response protection enters MDO but not the meter (§3), so it lowers D^decl for every period a contract spans — a level shift, not the flow break that Claim 1's period-level exclusion handles. Whole unit-weeks are therefore classified, not single periods. A unit-week is **contract-free** only if it contains no mapped reserve or response contract time (I13) and the unit's lead party holds no unmappable battery auction unit with award time in that week. Only contract-free weeks enter the Claim 2 score and the "provable under-declaration" flag (the hard flag). Every other week is *contract-exposed* or *contract status unknown* — not scored on the hard flag: it is reported, at fleet level and in private packs, with its violation share.
- **Mapping (I13), committed before it runs.** Every battery auction unit in the response and reserve auction results for the window is mapped to a BM unit — by a site-name alias table and lead party — or marked unmappable. The alias table, with each match's evidence and every adjudication, is committed before the coverage counts are computed; building it uses the auction results and reference data only. An auction unit whose technology the results do not identify counts as battery; large mixed-portfolio aggregators can therefore mark whole lead parties status unknown, and thin coverage is the expected case. The expected products are Dynamic Containment, Moderation and Regulation; Quick, Slow and Balancing Reserve; and STOR — if any of these results cannot be loaded for the window, every week counts as contract status unknown. Whether mandatory frequency response belongs on the list is provisional (I13) and is settled before the rule is committed. A contract held by a party other than the unit's lead party is caught only if its auction unit maps to the unit.
- **Coverage, decided once at the lock.** Coverage is computed before lock (`src/ingest/contract_coverage.py`; rule committed before the script's first run; fleet counts only, to `outputs/lock/contract_coverage.json`). Weeks after the unit's adoption week and within the data at the lock run enter the count; the B1610 screen is not applied before lock, so the counts are upper bounds on contract-free scored weeks. If fewer than 30 eligible units have at least 2 contract-free weeks at the lock run, the hard flag is reported as a case series, not a fleet result, and Claim 2's fleet-level result is the violation share over all scored weeks, labelled "possibly reflecting reserve or response protection". The decision is made from the lock-run coverage only, and is not revisited as more weeks accrue to 15 November. Units with fewer than 2 contract-free scored weeks are listed as not scored on the hard flag, with that reason.

**Unit scores.** The median of the unit's scored weeks — for Claim 2, of its contract-free scored weeks — with a 95% interval from resampling its days (1,000 draws).

**Flag categories** (thresholds fixed here; sensitivity in §9):

| Claim | Category | Rule on the 95% interval of the unit's score |
|---|---|---|
| 1 | Coherent | Upper bound ≤ 0.05 |
| 1 | Incoherent | Lower bound ≥ 0.15 |
| 1 | Indeterminate | Otherwise |
| 2 | Provable under-declaration | Lower bound ≥ 0.05 |
| 2 | None detected | Otherwise |

Claim 2's categories use contract-free weeks only; contract-exposed and unknown-status weeks are reported separately (above) and never enter the flag.

**Reliability.** For Claims 1 and 2, each unit's score is computed separately on odd and even calendar days. The Spearman correlation of the two across units, stepped up by the Spearman–Brown formula, is the claim's reliability. If its 95% interval (unit bootstrap) lies wholly below 0.5, the claim's flags are reported as unreliable and not given per unit, in private packs or later. If the interval straddles 0.5, flags are given with that stated.

## 5. Claim 3 (secondary): over-declaration from non-delivery

**The physics.** If NESO accepts an offer within a unit's declared MDO and the unit runs out of energy partway through, it delivers what it actually had: delivered = min(accepted, *E*_available). An honest unit delivers in full up to the MDO it declared. An over-declaring unit falls short once the instruction exceeds what it really held.

**Instruction sizing.** NESO states that since GC0166 "MDO/MDB Data is used to calculate what BOA volume can be issued", and that it "will utilize these values to determine the volume of Offers or Bids that can be dispatched within the BM window" (M18). Instructions are therefore sized up to the declared MDO, which is the regime in which Claim 3 has power.

**Regime.** Every instruction Claim 3 scores falls after the unit's adoption week, so under GC0166 for that unit. Instructions under the 15- or 30-minute rule are never scored, because the unit then had no MDO to test against (ASSUMPTIONS.md R25).

### 5.1 Quantities, per instruction

- **Accepted energy *A*:** over the instruction's settlement periods, the integral of (BOALF level − PN).
- **Delivered energy *D*:** over the same periods, Σ (metered − PN), minus the unit's frequency-response baseline (§5.3).
- **r = *A* ÷ MDO as published before acceptance:** the latest submission for the acceptance minute with publishTime before the BOALF acceptance time, which is what NESO could see. Under Branch B, MDO is replaced by √η̂ × MDO.
- **Delivery ratio ρ = *D* ÷ *A*.**

Offers use MDO and export. Bids are mirrored with |MDB| and import, and reported separately.

### 5.2 Screens

- Only instructions whose settlement periods hold no other BOA for the unit, because B1610 is half-hourly.
- Only instructions with *A* ≥ 1 MWh — a noise floor, not a definitional bound; ρ is defined for any *A* > 0.
- **r > 1 is classified, not fitted.** With MDO as published before acceptance, r > 1 means NESO issued more than the published MDO: through a value not yet on BMRS (M14) or sizing beyond MDO. Its frequency is reported per unit and at fleet level. No direction is predicted.

### 5.3 Frequency-response baseline

Batteries delivering frequency response deviate from PN without any BOA. For each instruction, the baseline is the unit's median (metered − PN) in settlement periods without a BOA, in the same ISO week and at the same settlement period of the day, scaled to the instruction's duration; multi-period instructions sum the per-period scaled medians.

### 5.4 Two models, fitted per unit

Throughout §5, MDO means MDO as published before acceptance. *E*_available is the energy actually deliverable at acceptance, net of protection. Over-declaration is either proportional or additive:

- **Proportional:** *E*_available = (1 − *f*) × MDO, so ρ = min(1, (1 − *f*)/r). *f* is the fraction of declared MDO that was not deliverable.
- **Additive:** *E*_available = MDO − Δ, so ρ = min(1, (MDO − Δ)/*A*). Δ is a constant over-declaration in MWh.

Each model is fitted by least squares over a grid (*f* in [0, 0.9] in steps of 0.01; Δ from 0 to the unit's median MDO in steps of 0.1 MWh), with a 95% interval from resampling instructions within the unit (1,000 draws). The piecewise-linear breakpoint of ρ against r is reported alongside, as a check that the result is not an artefact of the functional form.

### 5.5 Specification checks

- **Slope check.** Beyond the fitted kink, log ρ against log r should fall with slope about −1. A unit whose slope lies outside [−1.5, −0.5] is reported as "model rejected", without an estimate.
- **Separability.** The two models differ only if MDO varies across the unit's instructions. Where the interquartile range of MDO as published before acceptance is below 25% of its median, the models are reported as "not separately identified", and the flag rests on the proportional fit and the slope check alone.
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

**Power bound, computed before lock** (`src/ingest/power_bound.py`; rule committed in f25f43a before the first run). A unit is *potentially identifiable* if at least 10% of its declaration-minutes after its adoption week satisfy 1 MWh ≤ MDO ≤ 2 × MW × 1 h (MWh), so that a one-hour full-power instruction could reach r ≥ 0.5. Claim 3 is built in version 1 if at least 30 of the 98 eligible units are potentially identifiable — the build-gate uses eligible units, while the identification rate and §5.10's threshold use the realised scored count. **Result: 71 of 98; 67 of 73 non-secondary units** (ASSUMPTIONS.md R26).

- The bound is a necessary-condition screen on effort, not a test of validity. It bounds the r that instructions could reach, not the r they reached. The realised distribution is a scoring-run output and can be worse, if NESO rarely issues instructions near a small MDO. Since NESO sizes instructions from MDO (M18), it should track the bound where the bound is met. The identified set can be no larger than the potential set.
- The result barely varies across T = 30–90 minutes and K = 1–2. It rules out a Claim 3 that is thin by construction; it says little about how thin it will be in practice.
- 23 eligible units have no registered MW — 21 of the 25 secondary units, plus 2 non-secondary — and counted as not identifiable. Claim 3's evidence on secondary units will be thin.

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
3. Where Claims 3 and 4 can both be estimated for the same unit, their over-declaration estimates — Claim 3's *f̂* × MDO and Claim 4's excess, both in MWh at the matched settlement periods — agree within their intervals for at least two-thirds of such units, with at least 3 units compared.
4. Every Claim 3 band in the known-answer suite (§8) is met.

Statistical significance alone never promotes Claim 3. Promotion does not depend on how many units are flagged, so it cannot reward finding over-declaration.

## 6. Claim 4 (illustrative case series): upper-wall violations

**Why nameplate.** Usable energy cannot exceed nameplate energy, so a disclosed nameplate *N* is an upper bound on U. The tank then holds at most *N* − (max K − K_t) at time *t*. A unit declaring more than that over-declares, provably.

- **Violation:** D^decl_t > *N* − (max K − K_t) + 0.02 × *N*, at the start of a settlement period. Weekly score: the share of periods in violation, with the size of the excess in MWh.
- **Physics-inconsistent week:** max K − min K > 1.02 × *N*. Reported, and the unit's other results are marked "check nameplate".
- **Contracts.** Claim 4 needs no contract exclusion. The wall is built from the meter and the nameplate only, and an honest unit's stock cannot exceed it; unmapped reserve or response protection lowers D^decl (§3), which sits further below the wall for every period a contract spans and returns when the contract ends. Unmapped protection therefore costs Claim 4 power, not validity — the safe direction for a test of over-declaration. Claim 4 inherits the accepted-BOA add-back (B^exp, §3), which adds back only energy the tank is committed to deliver, so an honest unit still cannot spuriously violate the wall. No contract exclusion is applied; the conservativeness is disclosed with the results.

**Search protocol, time-boxed to two working days.** For each scored unit: the owner's or developer's press releases and annual reports, and planning documents that state MWh. Matched by site name and GSP group. Each match records the source URL, its date and the matching evidence. Units are searched in descending order of registered MW; the order and the stopping point are reported.

**Use.** Claim 4 validates Claim 3 on units where both can be estimated (§5.10, item 3). It is not a fleet result. Units that disclose a nameplate may differ from those that do not, in a direction that is unknown; the case series says so.

## 7. Claim 5 (descriptive): redeclaration latency

For each BOA, L = minutes from the BOALF acceptance time to the unit's first MDO or MDB submission with publishTime at or after acceptance (M14). Censored at the unit's next acceptance or 30 minutes, whichever comes first.

- **Reported at fleet level:** the distribution of L, and the share of BOAs with L ≤ 1 minute, NESO's benchmark.
- **Per unit:** only in each lead party's private pack, and not published in version 2 either, because publishTime may record BMRS publication rather than receipt (M14).
- **Cross-check:** latency and the r > 1 frequency are reported side by side at fleet level. If r > 1 is common, M14's publication lag is the first explanation checked.

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
| Redeclares 5 minutes after each BOA | Coherent or indeterminate | None detected | Not flagged; r > 1 not raised | Reported |
| Honest, redeclares 25 minutes after each BOA (slow) | Coherent or indeterminate | None detected | Detection rate reported; expected high; not a pass/fail band | Reported |
| PN protection ignored | Incoherent | None detected | Reported | Reported |
| Constant under-declaration, 20 MWh | Coherent (level-blind) | Provable under-declaration | Not flagged | Not flagged |
| Honest, power derates linearly to 50% below 20% state of charge | Coherent | None detected | Not flagged | Not flagged |

Across 100 simulated runs of each, the four plain honest batteries are flagged by Claim 3 at most 5% of the time under any regime. Under regime (i), the two over-declarers are flagged at least 80% of the time. The slow redeclarer's row is a detection-rate report, not a pass/fail band: it is flagged only through consecutive BOAs in adjacent periods inside its 25-minute lag, so the rate depends on how often the simulation issues BOAs. Its declarations really were stale, so being flagged is the correct outcome, not a cost, and it does not enter the four-battery band. If the suite cannot meet these bands, Claim 3 is dropped from version 1, and the report says so.

Two tests exercise Claim 2's contract screens: a unit-week containing mapped contract time is excluded from the hard flag and reported as contract-exposed with its violation share; and an auction-results file that is empty or unreadable forces every week to contract status unknown, demoting the hard flag to the case-series form (§4). The honest batteries' BOAs include instructions spanning settlement-period boundaries.

Bands are fixed here. The scoring code is written after lock, so a band or a definition may be revised only before the first real unit is scored. Each revision is logged in §12 with its date, the diff and a certification that no score for any real unit had been computed or seen, and the locking tag is incremented (`v1.0.1-lock`, `v1.0.2-lock`, …) so the Zenodo DOI chain shows every method state. After the first real unit is scored, bands are frozen.

## 9. Sensitivity

Each published flag is recomputed under:

- M13 Branch A and Branch B;
- *H* = current period + 3, and *H* = 6 hours;
- η̂ bounds [0.70, 0.98] and [0.65, 0.99];
- Claim 1 thresholds at ±50% (0.025 and 0.075; 0.075 and 0.225); Claim 2 threshold at 0.025 and 0.10;
- Claim 3's identification minimum at 10 and 25 instructions;
- Claim 2 with protection add-back, where the auction results give protection volumes rather than dates only.

A sensitivity table is published with the flags. **A flag that changes under either M13 branch or either *H* is published as "not robust", not as a finding.** Changes under the threshold variants are shown in the table.

## 10. Scoring discipline

- One pinned scoring run after lock: data manifests, code tag and output hashes recorded. Lead parties receive results from that run, and their responses are recorded against it.
- Before the lock, exactly two computations touch the scoring window, each with its rule committed before it runs and reporting fleet counts only: the Claim 3 power bound (§5.8; declarations and the reference snapshot) and the Claim 2 contract-coverage mapping (§4; auction results only). Neither reads B1610, PN, BOALF, BOAV or MELS; eligibility needs no recount (§2). No violation, score or per-unit result is computed before the lock.
- The lock follows the coverage run: rule committed, script run, `outputs/lock/contract_coverage.json` written, then lock — on 5 November 2026, or 6 November if the mapping overruns, and in any case before scoring starts in the week of 16 November.
- Past declarations cannot change. What can change is data, through B1610 revisions, NESO reissues or a demonstrated error. Later revisions are not re-scored, except to fix a demonstrated error, which restarts the reply clock.
- Claim 3 runs as a separate module from Claims 1 and 2. If Claim 3 fails its own tests, Claims 1 and 2 stand unchanged.

## 11. Publication commitments

- Results are published whether they show problems or not.
- **Published openly in version 1:** fleet-level results for every claim, the known-answer and reliability results, Claim 3's identification rate and diagnostics, the sensitivity table at fleet level, the method and the open pipeline, so any operator can run the checks on its own units.
- **Disclosed privately in version 1:** each lead party receives, for its own units only, the flags, Claim 1 score and interval, lower-wall status including contract-exposed and unknown-status shares (§4), Claim 3 results where identified, latency, and the method. No unit is named publicly in version 1.
- **Named publication, in version 2 only, requires all five:** (i) M13 resolved in writing; (ii) one clean pinned scoring run with no estimator changes; (iii) Claim 3's promotion outcome recorded (§5.10); (iv) right of reply completed for every named unit, with at least 10 working days; (v) legal review cleared. Until all five hold, per-unit results go to the lead party only.
- The claim attached to each unit, privately or publicly, is "its declarations are, or are not, physically consistent with its meter", not "this unit is a poor declarer". Flags are sorted by Claim 1 but not called a ranking.
- The data-quality findings are published in their own right: in SSEN's November 2025 register, the storage-MWh field read "DATA NOT AVAILABLE" for all 28 connected battery sites; REPD records no storage MWh; the Capacity Market register gives minimum durations, without BM unit identifiers.

## 12. Deviations log

For: a reader checking whether the audit was run as registered.

Every departure from this document after lock is recorded here, before results that depend on it are released. An empty log means no deviation. Changes made before lock are not deviations; they are recorded in §0 and in PROJECT.md §11.

**What is recorded:**

- A known-answer band or definition revised after lock but before the first real unit is scored (§8), with the diff, the certification that no score for any real unit had been computed or seen, and the incremented lock tag.
- A demonstrated data or method error fixed after the pinned scoring run (§10): the error, the fix, which results changed, and whether the lead-party clock restarted.
- A data source that changed or failed: a B1610 revision, a NESO reissue, an endpoint withdrawn, with its effect.
- A screen, threshold or procedure that could not be applied as written, and what was done instead.

**Rules:** entries are never deleted or edited; a correction is a new entry. Any change to a definition or estimator after the pinned scoring run requires a new lock (§10), recorded here with its tag.

| Date | Section | Deviation | Reason | Diff and tag | Certification |
|---|---|---|---|---|---|
| | | | | | |

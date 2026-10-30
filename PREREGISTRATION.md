# Pre-registration — Declaration Quality and Battery Dispatch in GB

**Status: DRAFT — not locked.**
Lock target: start of Week 2, after Gate A1 (which uses declaration data only) and before any outcome data is examined, including the Gate A2 stakes calculation.
On lock: tag a release, deposit on Zenodo (public timestamp), and record the commit hash here: *[hash]*.

Any deviation after lock is recorded in §9 with date and reason.

---

## 1. Questions

- **H1 (primary, descriptive):** Declaration quality, measured against physics by the four metrics in §3, varies across GB battery BM units after adjusting for duration, node, commissioning date and time since GC0166 adoption. H1 is the study's main contribution: a standard, with per-unit uncertainty, reliability and known-answer checks.
- **H2 (exploratory, within-unit):** A unit's accepted Balancing Mechanism volume per registered MW rises after it switches to MDO/MDB declarations.
- **H3 (secondary or exploratory, by the rule in §4):** Improvements in a unit's declaration-quality metrics are associated with higher accepted volume per registered MW, and with a higher BM premium.
- **H4 (enforcement):** Declaration quality improves fleet-wide after NESO's grace period ends. *(FORWARD-LOOKING; run only if the end date falls within the data window.)*

## 2. Data

Sources, endpoints and manifests: see `DATA_SOURCES.md`. Outcome data window: ISO weeks from Monday 25 May to Sunday 15 November 2026. That gives 4 pre-weeks before the earliest adoption week (w/c 22 June) and ends before estimation starts (w/c 16 November). Declaration data starts 25 June 2026, when MDO/MDB publication began. Ranking sample (H1): battery BM units with at least 4 weeks of non-default MDO/MDB data. Units with less are listed as not scored, with the reason.

## 3. Variables

**Outcome:** accepted Balancing Mechanism energy per registered MW, per unit per ISO week (MWh/MW).

- **Accepted energy:** the energy a unit delivered against accepted bid-offer instructions, relative to its Physical Notification. Computed from BMRS BOALF acceptance levels and PN, integrated over the week. Offers and bids are summed as absolute volumes for the primary outcome and reported separately as secondary outcomes. System-flagged acceptances are included in the primary outcome.
- **Cross-check:** Elexon's settlement acceptance volumes (BOAV, `/balancing/settlement/acceptance/volumes/`), compared with BOALF − PN after lock, for every unit-week where a settlement run is available. The settlement run used is recorded. The agreement is reported. BOALF − PN remains the outcome whatever the comparison shows, so the choice of outcome cannot follow the results.
- **Registered MW:** one constant per unit, from the first source in this order that is positive (M16):
  1. Generation Capacity (GC) from the BMRS BM unit reference data, in one snapshot pinned in `data/manifests/reference_manifest.csv` before lock: *[snapshot date, SHA-256]*.
  2. |Demand Capacity (DC)| from the same snapshot.
  3. The unit's maximum MEL over the outcome window: one value per unit, from BMRS MELS.

  GC and DC are seasonal registration values. MEL is a declaration, but the maximum over the whole window is a single constant, so it cannot change at the treatment date (the problem with NESO's in-merit volume, M1); raising it would lower the unit's own outcome. The source used is recorded per unit. *Robustness:* H3 on units with GC only. In the lock-time snapshot, 33 of 163 adopted units had GC = 0, 29 of them with DC = 0 as well; most were secondary BM units (type V), and most adopted in October.
- **Why not accepted ÷ in-merit volume:** NESO's in-merit volume depends on the unit's own MEL/MIL, and from 25 June 2026 on its GC0166 parameters, so its definition changes at the treatment date. Assumption M1, refuted 23 October 2026 (`docs/week1/m1_denominator_check.md`).
- **What the outcome does not control for:** how often the unit was in merit. Unit and week fixed effects absorb fixed unit differences and fleet-wide demand for balancing. Pricing changes remain a threat (ASSUMPTIONS.md O1, I10).

**Declaration-quality metrics.** Computed per unit per ISO week. A unit's score on each metric is the median of its scored weeks. A *scored week* is a complete ISO week (Monday to Sunday) after the unit's adoption week and within the outcome window, which passes that metric's screens below. The adoption week never counts, because it holds declarations for only part of the week.

*Notation.* For unit *i*: MDO_t ≥ 0 and MDB_t ≤ 0 are the declarations in force at minute *t* (latest submission, M9), in MWh. E⁺_h and E⁻_h are metered export and import in settlement period *h* (B1610), in MWh. PN-protected energy: P^exp_t and P^imp_t are the export and import energy in the unit's PN from *t* to the end of the protection horizon *H* (M15). Declarations are net of PN, reserve and response protection (M12). MDO is read as export energy at the meter and |MDB| as import energy at the meter (M13).

*Efficiency.* η̂ = ΣE⁺ / ΣE⁻ over the unit's scored weeks: export out over import in. The unit's start and end state of energy differ by at most U, so the error is at most U / ΣE⁻. Units with η̂ outside [0.70, 0.98] are flagged and not scored on metrics 1, 2 and 4.

*Declared deliverable energy* (export MWh if fully discharged, protection included): D^decl_t = MDO_t + P^exp_t.

*Reconstruction ("tank walls").* Exporting *y* MWh lowers deliverable energy by *y*; importing *x* MWh raises it by η̂·*x*. Within week *w*, let K_t = Σ_{h<t} (η̂·E⁻_h − E⁺_h), the cumulative change since the week began. Then D^rec_t = D_0 + K_t for an unknown starting level D_0. The tank cannot hold less than nothing or more than its usable export energy U (P4), so 0 ≤ D_0 + K_t ≤ U at every *t*. Hence D_0 ∈ [−min K, U − max K]. The week is *identified* when this interval is at most 0.2·U wide, and *physics-inconsistent* when max K − min K > 1.02·U (U or η̂ is wrong). D^rec_t uses the interval's midpoint; the interval is carried into the metric's uncertainty. The reconstruction uses metered energy only, never declarations.

1. **Conservation (stability).** C_t = MDO_t + P^exp_t + η̂·(|MDB_t| + P^imp_t), evaluated at the start of each settlement period. With honest declarations and fixed protections, C_t is constant at U minus reserve and response protection. Weekly metric: coefficient of variation of C_t. Needs no U. *Secondary:* |median C_t − U| / U, for units with disclosed U; reserve and response protection make this read low (O3).
2. **Mass balance.** For each settlement period *h*: r_h = ΔD^decl_h − (η̂·E⁻_h − E⁺_h), with ΔD^decl_h taken from the start of *h* to the start of *h*+1. Following the PN, delivering a BOA, charging and resubmitting a PN all change both terms alike, so honest declarations give r_h ≈ 0. Three things also enter r_h and are not errors by the unit: changes in reserve or response protection, which are unobserved (O3); a unit protecting PN energy further ahead than H (sensitivity H = 6 hours, §6); and auxiliary load, which η̂ absorbs on average but not in timing (P3). Weekly metric: Σ_h |r_h| / Σ_h (E⁺_h + E⁻_h), the mass-balance error ratio. *Secondary:* the signed ratio Σ_h r_h / Σ_h (E⁺_h + E⁻_h), where positive means declarations rose faster than the physics allows. Settlement periods in which an identified reserve or response contract starts or ends are excluded (I13). A steady level of protection cancels out of r_h; changes in it do not. Weeks with throughput below 0.5·U, or with any settlement period missing B1610, are not scored. Needs no U except for that idle screen; units without U use the fleet median MWh-per-MW times their GC.
3. **Redeclaration latency.** For each BOA (BOALF acceptance time *a*), L = minutes from *a* to the unit's first MDO or MDB submission with publishTime ≥ *a* (M14). Censored at the unit's next acceptance or *a* + 30 minutes, whichever is first. Weekly metric: share of BOAs with L ≤ 1 minute, NESO's reserve benchmark. *Secondary:* median L, censored values at 30. Weeks with fewer than 5 BOAs are not scored.
4. **Conservatism.** At the start of each settlement period in identified weeks: Q_t = D^decl_t / D^rec_t, excluding periods with D^rec_t < 0.05·U. Weekly metric: median Q_t. Values below 1 mean under-declaring, above 1 over-declaring. Unobserved reserve and response protection push Q below 1 (O3), so reserve-contracted units are reported separately where identifiable. Q compares declared energy with the energy the tank physically held, reconstructed from metered flows. It does not compare with energy delivered or accepted, so a unit constrained off or not dispatched is not scored as conservative for that reason. *Secondary, needing no U:* the share of settlement periods in which D^decl_t falls below the lower wall, K_t − min K, the least energy the metered history proves the tank held. That is provable under-declaration.

Units without disclosed U are not scored on metric 4 or on metric 1's secondary, and are listed with that reason.

*Secondary BM units* (BMRS `bmUnitType` V, registered by Virtual Lead Parties) may cover one site or several. The tank model assumes one store of energy, so for these units: they are scored if B1610 metered data exist for them; they enter the adjusted ranking only if none of their scored weeks is physics-inconsistent; and they are reported as a separate group, marked "secondary unit: may be aggregated", in every table. A secondary unit without B1610 data is listed as not scored, with that reason (R19).

*What the metrics measure.* They score declarations against physics, not against the best declaration achievable given the unit's contracts. A unit holding reserve as contracted can score as conservative; the claims map says so. Mass balance (metric 2) tests whether declarations *change* as the physics does. It cannot see a constant error in *level*: a unit that always over-declares by the same amount passes it. Levels are tested by metric 4, against the tank walls.

**Per-unit uncertainty.** Each unit's score on each metric carries a 95% interval from resampling its own days (1,000 draws). Ranks are published with intervals derived from the same draws, so units whose intervals overlap are not presented as different. Units with 4–7 scored weeks are marked "short record".

**Reliability.** *Primary:* split-half by day. For each metric, each unit's score is computed separately on odd and even calendar days over its scored weeks; the Spearman correlation of the two across units, stepped up to full length by the Spearman–Brown formula, is the metric's reliability. Days, not settlement periods, because adjacent periods are correlated and would inflate it. Rule: if the 95% interval (unit bootstrap) lies wholly below 0.5, the metric is reported as unreliable and left out of the adjusted ranking, with the exclusion declared; if the interval straddles 0.5, the metric is ranked with a flag. *Descriptive:* week-to-week rank correlation, reported with its interval but never used to exclude, because units can genuinely change, for instance with a new optimiser.

**Known-answer tests.** Synthetic batteries with planted faults, run in CI before any real unit is scored. Each must land in its band, or the build fails:

| Synthetic unit (U = 100 MWh, η = 0.88, two cycles a day, PN-following with BOAs) | Metric 1 (CV) | Metric 2 (error ratio) | Metric 3 (share ≤ 1 min) | Metric 4 (median Q) | Ranking gate |
|---|---|---|---|---|---|
| Honest declarations | ≤ 0.02 | ≤ 0.02 | ≥ 0.95 | 0.97–1.03 | passes |
| Constant over-declaration by 10 MWh | ≤ 0.02 | ≤ 0.02 (level-blind, by design) | ≥ 0.95 | ≥ 1.08 | barred from top quartile |
| Static profile copied from maximum | ≥ 0.10 | ≥ 0.30 | ≤ 0.05 | — | — |
| Redeclares 5 minutes after each BOA | ≤ 0.02 | ≤ 0.05 | ≤ 0.05 | 0.97–1.03 | passes |
| PN protection ignored (MDO not reduced before PN delivery) | ≥ 0.05 | ≥ 0.05 | ≥ 0.95 | — | — |
| Declares 30% below proven minimum | ≤ 0.02 | ≤ 0.02 | ≥ 0.95 | ≤ 0.75 | barred (lower wall) |

Bands are fixed here. The metric code is written after lock, so a band or a metric definition may be revised only before the first real unit is scored. Each revision is logged in §9 with its date, the diff, and a certification that no score for any real unit had been computed or seen at the time. After the first real unit is scored, bands are frozen.

**Incumbent comparison.** What an owner already sees is the unit's skip rate. For each metric, the Spearman rank correlation ρ between the unit's adjusted score (better declarations score higher) and its NESO Stage 5 All-BM skip rate over the same weeks, offers and bids combined, with a 95% interval from a unit bootstrap. Interpretation, fixed in advance, using |ρ|: lower bound ≥ 0.7 → the metric largely restates skip rates; upper bound ≤ 0.3 → it measures something skip rates do not, whether added information or something orthogonal, which this test cannot separate; otherwise inconclusive. NESO's skip rates use the unit's own declarations (M1), so some correlation is built in.

**Confounds.** Each threat to H3, and what is done about it:

| Confound | Adjusted in the primary | Adjusted in a named robustness run (§6) | Left in the residual: likely effect |
|---|---|---|---|
| Fixed unit traits: hardware, location, contracts held throughout | Unit fixed effects | — | — |
| Fleet-wide shocks: balancing demand, prices, season | Week fixed effects | — | — |
| Regional constraint exposure changing over time | — | GSP group × week fixed effects | Constraints within a GSP group; sign unknown |
| Reserve and response contracts changing over time | — | Weekly contracted MW, where mapped (I13); reserve-free subsample | Unmapped contracts move declarations and acceptances together; likely overstates the effect |
| MEL/MIL changes | — | Weekly mean MEL and MIL as controls. MEL is itself a declaration and may carry part of the effect, so this run is a sensitivity, not a correction | — |
| Pricing strategy | — | Offer price relative to fleet median (O1) | Likely overstates the effect |
| Protection horizon mismatch | — | H = 6 hours (M15) | — |
| Steady reserve protection | Cancels in metric 2 by construction | — | Biases metric 4 low (O3) |
| Over-declaration changing over time, alongside changes in coherence | — | Weekly median Q (metric 4) as a control, units with U | Units without U; likely overstates the effect, since higher declared availability invites dispatch |

**Treatment (H2):** first non-default MDO/MDB submission per unit, dated by delivery time (`timeFrom`), binned by ISO week. Values with |MWh| ≥ 9999 are NESO defaults, not submissions. This is when the control room stops applying the 30-minute rule to the unit, whatever the quality of its declarations.

**Sensitivity treatment (H2):** dynamic onset, the first day of the first 7-day window in which the unit's MDO ranges by at least 0.5 MWh on 4 or more days (`config/gate_a1.toml`, `[sensitivity]`). A unit that declares a static profile is treated from its first submission in the primary analysis; it is a poor declarer, which H3 measures, not an untreated unit. Gate A1 reports, without unit IDs, how many units began with static declarations and for how long.

**Adjustment set:** duration, node (or zone), commissioning date, time since adoption.

## 4. Estimation

- H1: for each metric, OLS of the unit's mean over its scored weeks on the adjustment set (§3). The adjusted ranking orders units by residual. The lead table ranks by metric 2, with a qualification gate, because mass balance cannot see level errors: a unit cannot be placed in the top quartile if its median Q (metric 4) exceeds 1.05, which means over-declaring, or if more than 10% of its settlement periods fall below the lower wall, which means provably under-declaring. Units without U are ranked but marked "level not verified". The other metrics' rankings are published alongside. Rank uncertainty comes from the per-unit intervals (§3) and is published with the ranks, so near-ties are not read as differences. The raw ranking is published alongside; the adjusted ranking leads.
- Design selection: by the ordered design hierarchy and triggers in `PROJECT.md` §5A (single source; not restated here). The selected design and its trigger statistics, as recorded in the PROJECT.md decision log at Gate A1: **design 2 (within-unit metric variation)**, official run 30 October 2026, config SHA-256 `ed7dcdc1…`, unchanged since commit 9f0ca5e. Design 1 not triggered: 7 estimable cohorts of at least 6 units, but the earliest (2026-W36) had 8.4 weeks of post-period against a required 8.8. Design 2 triggered: 13 units with at least 8.8 weeks of declarations, against a required 11; median within-unit CV 0.414, against 0.055. Design 3 not triggered: no grace-period end announced. 163 units adopted; the last cohort (2026-W44, 52 units) has no comparison group. The CV proxy is moved by PN protection as well as declaration quality (ASSUMPTIONS.md I15), so its margin over the threshold overstates variation in quality.
- H2 (**exploratory**): staggered-adoption event study. Design 1's trigger was not met at Gate A1, so H2 cannot be the lead design or a secondary analysis (PROJECT.md §5A). It is pre-specified here so that it can be reported at all, and is reported whatever it shows.
  - *Estimator:* Callaway–Sant'Anna, not-yet-treated controls, event window −4 to +8 weeks around each unit's adoption week (§3, primary treatment).
  - *Cohorts:* ISO adoption weeks that meet Gate A1's per-cohort minimum, as recorded in the official Gate A1 report. The last cohort has no comparison group and is dropped. Cohorts below the minimum are excluded and counted.
  - *Reporting:* all four pre-period coefficients and a joint pre-trend test. Event times reached by fewer than two cohorts are not reported. Cohorts with fewer than 8 post-weeks contribute to the event times they reach.
  - *Limits:* no Holm adjustment, no £ conversion, and no use in H3's lead estimate. Every table and chart carries the label "exploratory". If its sign or size differs from H3's lead estimate, both are reported and the difference is discussed, not resolved in H2's favour.
  - *Sensitivity:* dynamic onset as treatment (§3).
- H3: weekly outcome on each declaration metric in turn, with unit and week fixed effects.
  - **Outcomes:** *primary:* accepted BM energy per registered MW (§3), the declaration → acceptance channel. *Secondary:* BM premium per registered MW, Σ accepted volume × margin (§4 margin), which measures value. The two are linked by construction, since premium is volume weighted by margin; premium also carries the unit's own pricing choices, which unit fixed effects do not absorb when they change. Read together: volume and premium both up → declaring well pays; volume up, premium down → more volume at worse prices; volume flat, premium up → a pricing change, not a declaration effect.
  - **Label, set by the procedure:** if the MDE for the lead metric (§5) is at most £5,000/MW/yr, H3 is reported as secondary; otherwise as exploratory, with the pre-written sentence. The label is decided before any coefficient is displayed.
  - **Sample:** units with at least 4 scored weeks. This maximises the number of units; it does not by itself maximise precision, which with unit fixed effects depends on how much each unit's metric varies. The MDE (§5) is computed on this sample. *Robustness:* units with at least 8 scored weeks, with its own MDE; if its MDE is smaller, that is reported as a finding. At lock, the adoption weeks of the two samples are compared from the official Gate A1 table, since 4-week units are likely late adopters near the 5 November deadline; any difference is stated as a limitation before results are seen.
  - **Interpretation, fixed in advance:** metric 2 cannot see a constant error in level, and unit fixed effects absorb any constant over-declaration. The lead estimate is therefore the association of more coherent declarations with acceptances, net of each unit's usual level. It does not exclude a unit that becomes more coherent and starts over-declaring at the same time; the weekly-Q robustness run (§6) addresses that for units with U.
  - **Lead estimate:** metric 2, the mass-balance error ratio (absolute). Scaled so its coefficient reads as the change in outcome for a 10-percentage-point reduction in the ratio. Mass balance cannot see a constant error in level (§3), but unit fixed effects would absorb such an error anyway, so it does not bias H3; it matters for the ranking, which has its own gate (H1).
  - **Degeneracy rule**, applied after lock, on the metric data alone, before any H3 coefficient is displayed: if the median within-unit standard deviation of the lead metric's weekly values is below 0.01, a tenth of the 10-point contrast, the contrast would extrapolate far beyond the data. The lead estimate then passes to the next metric in the order 4, 1, 3 that clears the same test. A metric cannot be chosen because it is more dispersed than another, only rejected because it barely varies.
  - **Secondaries, each also in £ with the same 10-point contrast:** metrics 1, 3 and 4; the signed version of metric 2, to show any mechanical "declare more, accept more" component; and, where the effect differs by sign, over- and under-declaration reported separately rather than averaged.
- **£/MW/yr definition** (for H3's association, not a measure of stakes):
  - Numerator: the H3 coefficient for a 10-percentage-point reduction in the lead metric, as accepted MWh per MW per week, annualised (× 52), × margin.
  - Margin (primary): the BM premium over wholesale in the same settlement period. Offers: accepted offer price − Market Index Price (MID). Bids: MID − accepted bid price. Both positive when the BM pays better than wholesale.
  - Margin (pre-specified sensitivity, E5): a battery's alternative is to trade at another hour of the same day. Offers are valued against the day's highest MID; bids against the day's lowest. This gives a conservative premium.
  - Comparison only, not a conversion: Gale et al. (2026) simulate about £12,000/MW/yr lost per 10% of time a battery is blocked from the BM. Their skip rate is a simulated share of blocked time, not NESO's volume-based rate nor this project's outcome (E1, E2a).
  - Denominator: registered MW (GC), as for the outcome in §3. Not max MEL: MEL is a declaration. Per MWh usable reported as secondary.
  - Caveat: the BM is pay-as-bid. Better declarations may change which offers are accepted and at what price, so volume × margin is a first-order approximation.

## 5. Inference

Intervals: 95%, with standard errors clustered by unit. With fewer than 50 units, cluster-robust errors understate uncertainty, so H3's primary inference uses the wild cluster bootstrap (Webb weights, 9,999 replications, clustered by unit); conventional clustered errors are shown alongside. The £/MW/yr figure is always reported with its interval, never as a point estimate alone: the H3 interval scaled by the same contrast and mean margin.

**Minimum detectable effect.** Computed after lock and before any H3 coefficient is displayed, separately for the primary sample, the reserve-free subsample and the contracted-MW run. Method: 999 placebo runs, each shifting every unit's metric series in time by a random whole number of weeks, keeping its own weeks but breaking its link with the outcome. MDE = 2.8 × the standard deviation of the placebo coefficients (80% power, 5% two-sided), converted to £/MW/yr as above. The threshold is £5,000/MW/yr, Gate A2's low threshold (PROJECT.md §5A): a round-number convention, set on 22 October 2026 before any data were pulled, for the stakes below which the benchmark is not worth an owner's attention. It was tied to this label on 28 October 2026, before any MDE had been computed. If the MDE exceeds it, the result is reported with this sentence: "At this sample size the design cannot reliably detect effects smaller than £[MDE]/MW/yr, above the £5,000/MW/yr at which the result would change an owner's decision. The estimate is reported as an estimate only; a null result here is not evidence of no effect." A null in an underpowered subsample is reported against that subsample's own MDE.

 For Callaway–Sant'Anna, the estimator's multiplier bootstrap, clustered by unit. Multiple comparisons: any claim about the four declaration-quality metrics (H1, H3) uses Holm–Bonferroni adjustment across the four. H3's lead £/MW/yr estimate is a single pre-specified quantity and is not adjusted; secondaries are adjusted across the four metrics as above. Interval method validated by simulation before use (lesson from credit-impulse project: block bootstrap undercovers in short samples).

## 6. Robustness (pre-specified)

- Protection horizon H = 6 hours instead of the current settlement period plus three (M15)
- Metric 2 computed only on settlement periods without BOAs (I12)
- Offers and bids as separate outcomes
- Excluding system-flagged acceptances
- NESO Tier B accepted ÷ in-merit volume, reported descriptively only, with the M1 caveat stated
- Adding the unit's offer price relative to the fleet median (from BOD) as a control, to probe the pricing threat (O1)
- GSP group × week fixed effects (regional constraint exposure). Estimated on units in GSP groups with at least two scored units. The number of such units under each sample rule is counted at lock from the official Gate A1 table and the reference snapshot; if fewer than 10 units contribute, the run is reported as not estimable rather than dropped silently
- Units with at least 8 scored weeks (sample robustness; §4)
- Weekly contracted reserve and response MW as a control, where auction units map cleanly to BM units (I13)
- Reserve-free subsample: units with no identified contract in the window
- Weekly mean MEL and MIL as controls (sensitivity only; see §3)
- Weekly median Q (metric 4) as a control in H3, on units with U (time-varying over-declaration; §3)
- Alternative usable-MWh assumptions (P4)
- Dropping the first 2 weeks after each unit's adoption (learning period)

## 7. What would change our conclusions

- Pre-trends in H2 → report as descriptive only.
- Mass-balance residuals too large to interpret → drop metric 2; report why.
- No design trigger met at Gate A1 → design note only (PROJECT.md §5A).
- H3's MDE above £5,000/MW/yr → H3 reported as exploratory, with the pre-written sentence in §5.

## 8. Publication commitments

- Results published whether strong, weak or null.
- Ranking published raw and adjusted; adjusted leads.
- Each lead party receives its own result and the method ≥ 10 working days before publication; replies published alongside (PROJECT.md §7a).
- Scored snapshot: results come from one pinned scoring run (data manifests, code tag, output hashes). Lead parties see results from that run, and replies are published against it. Past declarations cannot change; what can change is data, through B1610 revisions, NESO reissues or a demonstrated error. Later data revisions are not re-scored, except to fix a demonstrated error, which restarts the reply clock.

## 9. Deviations log

| Date | Deviation | Reason |
|---|---|---|
| | | |

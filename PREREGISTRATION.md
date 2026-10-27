# Pre-registration — Declaration Quality and Battery Dispatch in GB

**Status: DRAFT — not locked.**
Lock target: start of Week 2, after Gate A1 (which uses declaration data only) and before any outcome data is examined, including the Gate A2 stakes calculation.
On lock: tag a release, deposit on Zenodo (public timestamp), and record the commit hash here: *[hash]*.

Any deviation after lock is recorded in §9 with date and reason.

---

## 1. Questions

- **H1 (descriptive):** Declaration quality varies across GB battery BM units after adjusting for duration, node, commissioning date and time since GC0166 adoption.
- **H2 (within-unit):** A unit's accepted Balancing Mechanism volume per registered MW rises after it switches to MDO/MDB declarations.
- **H3 (within-unit):** Improvements in a unit's declaration-quality metrics are associated with higher accepted volume per registered MW.
- **H4 (enforcement):** Declaration quality improves fleet-wide after NESO's grace period ends. *(FORWARD-LOOKING; run only if the end date falls within the data window.)*

## 2. Data

Sources, endpoints and manifests: see `DATA_SOURCES.md`. Outcome data window: ISO weeks from Monday 25 May to Sunday 15 November 2026. That gives 4 pre-weeks before the earliest adoption week (w/c 22 June) and ends before estimation starts (w/c 16 November). Declaration data starts 25 June 2026, when MDO/MDB publication began. Ranking sample (H1): battery BM units with at least 4 weeks of non-default MDO/MDB data. Units with less are listed as not scored, with the reason.

## 3. Variables

**Outcome:** accepted Balancing Mechanism energy per registered MW, per unit per ISO week (MWh/MW).

- **Accepted energy:** the energy a unit delivered against accepted bid-offer instructions, relative to its Physical Notification. Computed from BMRS BOALF acceptance levels and PN, integrated over the week. Offers and bids are summed as absolute volumes for the headline outcome and reported separately as secondary outcomes. System-flagged acceptances are included in the headline.
- **Cross-check:** Elexon's settlement acceptance volumes (BOAV, `/balancing/settlement/acceptance/volumes/`), compared with BOALF − PN after lock, for every unit-week where a settlement run is available. The settlement run used is recorded. The agreement is reported. BOALF − PN remains the outcome whatever the comparison shows, so the choice of outcome cannot follow the results.
- **Registered MW:** Generation Capacity (GC) from the BMRS BM unit reference data, taken from one snapshot pinned in `data/manifests/reference_manifest.csv` before lock: *[snapshot date, SHA-256]*. GC is a seasonal registration value, not an operational declaration, so it does not move with MEL, MDO or MDB. A unit with missing or zero GC is not scored, and is listed with that reason.
- **Why not accepted ÷ in-merit volume:** NESO's in-merit volume depends on the unit's own MEL/MIL, and from 25 June 2026 on its GC0166 parameters, so its definition changes at the treatment date. Assumption M1, refuted 23 October 2026 (`docs/week1/m1_denominator_check.md`).
- **What the outcome does not control for:** how often the unit was in merit. Unit and week fixed effects absorb fixed unit differences and fleet-wide demand for balancing. Pricing changes remain a threat (ASSUMPTIONS.md O1, I10).

**Declaration-quality metrics.** Computed per unit per ISO week. A unit's score on each metric is the median of its scored weeks.

*Notation.* For unit *i*: MDO_t ≥ 0 and MDB_t ≤ 0 are the declarations in force at minute *t* (latest submission, M9), in MWh. E⁺_h and E⁻_h are metered export and import in settlement period *h* (B1610), in MWh. PN-protected energy: P^exp_t and P^imp_t are the export and import energy in the unit's PN from *t* to the end of the protection horizon *H* (M15). Declarations are net of PN, reserve and response protection (M12). MDO is read as export energy at the meter and |MDB| as import energy at the meter (M13).

*Efficiency.* η̂ = ΣE⁺ / ΣE⁻ over the unit's scored weeks: export out over import in. The unit's start and end state of energy differ by at most U, so the error is at most U / ΣE⁻. Units with η̂ outside [0.70, 0.98] are flagged and not scored on metrics 1, 2 and 4.

*Declared deliverable energy* (export MWh if fully discharged, protection included): D^decl_t = MDO_t + P^exp_t.

*Reconstruction ("tank walls").* Exporting *y* MWh lowers deliverable energy by *y*; importing *x* MWh raises it by η̂·*x*. Within week *w*, let K_t = Σ_{h<t} (η̂·E⁻_h − E⁺_h), the cumulative change since the week began. Then D^rec_t = D_0 + K_t for an unknown starting level D_0. The tank cannot hold less than nothing or more than its usable export energy U (P4), so 0 ≤ D_0 + K_t ≤ U at every *t*. Hence D_0 ∈ [−min K, U − max K]. The week is *identified* when this interval is at most 0.2·U wide, and *physics-inconsistent* when max K − min K > 1.02·U (U or η̂ is wrong). D^rec_t uses the interval's midpoint; the interval is carried into the metric's uncertainty. The reconstruction uses metered energy only, never declarations.

1. **Conservation (stability).** C_t = MDO_t + P^exp_t + η̂·(|MDB_t| + P^imp_t), evaluated at the start of each settlement period. With honest declarations and fixed protections, C_t is constant at U minus reserve and response protection. Weekly metric: coefficient of variation of C_t. Needs no U. *Secondary:* |median C_t − U| / U, for units with disclosed U; reserve and response protection make this read low (O3).
2. **Mass balance.** For each settlement period *h*: r_h = ΔD^decl_h − (η̂·E⁻_h − E⁺_h), with ΔD^decl_h taken from the start of *h* to the start of *h*+1. Following the PN, delivering a BOA, charging and resubmitting a PN all change both terms alike, so honest declarations give r_h ≈ 0. Three things also enter r_h and are not errors by the unit: changes in reserve or response protection, which are unobserved (O3); a unit protecting PN energy further ahead than H (sensitivity H = 6 hours, §6); and auxiliary load, which η̂ absorbs on average but not in timing (P3). Weekly metric: Σ_h |r_h| / Σ_h (E⁺_h + E⁻_h). Weeks with throughput below 0.5·U, or with any settlement period missing B1610, are not scored. Needs no U except for that idle screen; units without U use the fleet median MWh-per-MW times their GC.
3. **Redeclaration latency.** For each BOA (BOALF acceptance time *a*), L = minutes from *a* to the unit's first MDO or MDB submission with publishTime ≥ *a* (M14). Censored at the unit's next acceptance or *a* + 30 minutes, whichever is first. Weekly metric: share of BOAs with L ≤ 1 minute, NESO's reserve benchmark. *Secondary:* median L, censored values at 30. Weeks with fewer than 5 BOAs are not scored.
4. **Conservatism.** At the start of each settlement period in identified weeks: Q_t = D^decl_t / D^rec_t, excluding periods with D^rec_t < 0.05·U. Weekly metric: median Q_t. Values below 1 mean under-declaring, above 1 over-declaring. Unobserved reserve and response protection push Q below 1 (O3), so reserve-contracted units are reported separately where identifiable.

Units without disclosed U are not scored on metric 4 or on metric 1's secondary, and are listed with that reason.

**Treatment (H2):** first non-default MDO/MDB submission per unit, dated by delivery time (`timeFrom`), binned by ISO week. Values with |MWh| ≥ 9999 are NESO defaults, not submissions. This is when the control room stops applying the 30-minute rule to the unit, whatever the quality of its declarations.

**Sensitivity treatment (H2):** dynamic onset, the first day of the first 7-day window in which the unit's MDO ranges by at least 0.5 MWh on 4 or more days (`config/gate_a1.toml`, `[sensitivity]`). A unit that declares a static profile is treated from its first submission in the primary analysis; it is a poor declarer, which H3 measures, not an untreated unit. Gate A1 reports, without unit IDs, how many units began with static declarations and for how long.

**Adjustment set:** duration, node (or zone), commissioning date, time since adoption.

## 4. Estimation

- H1: for each metric, OLS of the unit's mean over its scored weeks on the adjustment set (§3). The adjusted ranking orders units by residual. Rank uncertainty comes from a unit-level bootstrap and is published with the ranks, so near-ties are not read as differences. The raw ranking is published alongside; the adjusted ranking leads.
- Design selection: by the ordered design hierarchy and triggers in `PROJECT.md` §5A (single source; not restated here). The selected design and its trigger statistics, as recorded in the PROJECT.md decision log at Gate A1, are copied here at lock: *[design, statistics, date]*.
- H2 (**exploratory**): staggered-adoption event study. Design 1's trigger was not met at Gate A1, so H2 cannot be the headline or a secondary analysis (PROJECT.md §5A). It is pre-specified here so that it can be reported at all, and is reported whatever it shows.
  - *Estimator:* Callaway–Sant'Anna, not-yet-treated controls, event window −4 to +8 weeks around each unit's adoption week (§3, primary treatment).
  - *Cohorts:* ISO adoption weeks that meet Gate A1's per-cohort minimum, as recorded in the official Gate A1 report. The last cohort has no comparison group and is dropped. Cohorts below the minimum are excluded and counted.
  - *Reporting:* all four pre-period coefficients and a joint pre-trend test. Event times reached by fewer than two cohorts are not reported. Cohorts with fewer than 8 post-weeks contribute to the event times they reach.
  - *Limits:* no Holm adjustment, no £ conversion, and no use in the headline estimate. Every table and chart carries the label "exploratory". If its sign or size differs from the headline, both are reported and the difference is discussed, not resolved in H2's favour.
  - *Sensitivity:* dynamic onset as treatment (§3).
- H3: unit fixed effects, time fixed effects; standard errors clustered by unit.
- **£/MW/yr definition:**
  - Numerator: declaration-attributable Δ accepted MWh per year × margin.
  - Margin (headline): the BM premium over wholesale in the same settlement period. Offers: accepted offer price − Market Index Price (MID). Bids: MID − accepted bid price. Both positive when the BM pays better than wholesale.
  - Margin (pre-specified sensitivity, E5): a battery's alternative is to trade at another hour of the same day. Offers are valued against the day's highest MID; bids against the day's lowest. This gives a conservative premium.
  - Comparison only, not a conversion: Gale et al. (2026) simulate about £12,000/MW/yr lost per 10% of time a battery is blocked from the BM. Their skip rate is a simulated share of blocked time, not NESO's volume-based rate nor this project's outcome (E1, E2a).
  - Denominator: registered MW (GC), as for the outcome in §3. Not max MEL: MEL is a declaration. Per MWh usable reported as secondary.
  - Caveat: the BM is pay-as-bid. Better declarations may change which offers are accepted and at what price, so volume × margin is a first-order approximation.

## 5. Inference

Intervals: 95%, with standard errors clustered by unit. For Callaway–Sant'Anna, the estimator's multiplier bootstrap, clustered by unit. Multiple comparisons: any claim about the four declaration-quality metrics (H1, H3) uses Holm–Bonferroni adjustment across the four. The headline £/MW/yr estimate is a single pre-specified quantity and is not adjusted. Interval method validated by simulation before use (lesson from credit-impulse project: block bootstrap undercovers in short samples).

## 6. Robustness (pre-specified)

- Protection horizon H = 6 hours instead of the current settlement period plus three (M15)
- Metric 2 computed only on settlement periods without BOAs (I12)
- Offers and bids as separate outcomes
- Excluding system-flagged acceptances
- NESO Tier B accepted ÷ in-merit volume, reported descriptively only, with the M1 caveat stated
- Adding the unit's offer price relative to the fleet median (from BOD) as a control, to probe the pricing threat (O1)
- Excluding units with known ancillary-service energy reservations
- Alternative usable-MWh assumptions (P4)
- Dropping the first 2 weeks after each unit's adoption (learning period)

## 7. What would change our conclusions

- Pre-trends in H2 → report as descriptive only.
- Mass-balance residuals too large to interpret → drop metric 2; report why.
- No design trigger met at Gate A1 → design note only (PROJECT.md §5A).

## 8. Publication commitments

- Results published whether strong, weak or null.
- Ranking published raw and adjusted; adjusted leads.
- Each lead party receives its own result and the method ≥ 10 working days before publication; replies published alongside (PROJECT.md §7a).

## 9. Deviations log

| Date | Deviation | Reason |
|---|---|---|
| | | |

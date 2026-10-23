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

- **Accepted energy:** the energy a unit delivered against accepted bid-offer instructions, relative to its Physical Notification. Computed from BMRS BOALF acceptance levels and PN, integrated over the week. Offers and bids are summed as absolute volumes for the headline outcome and reported separately as secondary outcomes. System-flagged acceptances are included in the headline. *[Implementation check, Wk 1: whether Elexon publishes per-unit acceptance volumes that match this calculation; if so, use them and record the reconciliation.]*
- **Registered MW:** Generation Capacity (GC) from the BMRS BM unit reference data, taken from one snapshot pinned in `data/manifests/reference_manifest.csv` before lock: *[snapshot date, SHA-256]*. GC is a seasonal registration value, not an operational declaration, so it does not move with MEL, MDO or MDB. A unit with missing or zero GC is not scored, and is listed with that reason.
- **Why not accepted ÷ in-merit volume:** NESO's in-merit volume depends on the unit's own MEL/MIL, and from 25 June 2026 on its GC0166 parameters, so its definition changes at the treatment date. Assumption M1, refuted 23 October 2026 (`docs/week1/m1_denominator_check.md`).
- **What the outcome does not control for:** how often the unit was in merit. Unit and week fixed effects absorb fixed unit differences and fleet-wide demand for balancing. Pricing changes remain a threat (ASSUMPTIONS.md O1, I10).

**Declaration-quality metrics** (definitions to finalise, with formulas):
1. Conservation error: |MDO + MDB − usable MWh| / usable MWh
2. Mass-balance error: |ΔMDO − (−∫ metered export + BOA energy, efficiency-adjusted)|
3. Redeclaration latency: minutes from BOA timestamp to next MDO/MDB update
4. Conservatism: declared MDO ÷ reconstructed deliverable energy

**Treatment (H2):** first non-default MDO/MDB submission per unit, dated by delivery time (`timeFrom`), binned by ISO week. Values with |MWh| ≥ 9999 are NESO defaults, not submissions.

**Adjustment set:** duration, node (or zone), commissioning date, time since adoption.

## 4. Estimation

- H1: for each metric, OLS of the unit's mean over its scored weeks on the adjustment set (§3). The adjusted ranking orders units by residual. Rank uncertainty comes from a unit-level bootstrap and is published with the ranks, so near-ties are not read as differences. The raw ranking is published alongside; the adjusted ranking leads.
- Design selection: by the ordered design hierarchy and triggers in `PROJECT.md` §5A (single source; not restated here). The selected design and its trigger statistics, as recorded in the PROJECT.md decision log at Gate A1, are copied here at lock: *[design, statistics, date]*.
- H2: staggered-adoption event study, Callaway–Sant'Anna estimator, not-yet-treated controls, event window −4 to +8 weeks around each unit's adoption week. Report all four pre-period coefficients and a joint pre-trend test. Cohorts with fewer than 8 post-weeks contribute to the event times they reach.
- H3: unit fixed effects, time fixed effects; standard errors clustered by unit.
- **£/MW/yr definition:**
  - Numerator: declaration-attributable Δ accepted MWh per year × margin.
  - Margin (headline): the BM premium over wholesale in the same settlement period. Offers: accepted offer price − Market Index Price (MID). Bids: MID − accepted bid price. Both positive when the BM pays better than wholesale.
  - Margin (pre-specified sensitivity, E5): a battery's alternative is to trade at another hour of the same day. Offers are valued against the day's highest MID; bids against the day's lowest. This gives a conservative premium.
  - Other alternatives reported only if verified: Gale et al.'s profit measure (E1, E2).
  - Denominator: registered MW (GC), as for the outcome in §3. Not max MEL: MEL is a declaration. Per MWh usable reported as secondary.
  - Caveat: the BM is pay-as-bid. Better declarations may change which offers are accepted and at what price, so volume × margin is a first-order approximation.

## 5. Inference

Intervals: 95%, with standard errors clustered by unit. For Callaway–Sant'Anna, the estimator's multiplier bootstrap, clustered by unit. Multiple comparisons: any claim about the four declaration-quality metrics (H1, H3) uses Holm–Bonferroni adjustment across the four. The headline £/MW/yr estimate is a single pre-specified quantity and is not adjusted. Interval method validated by simulation before use (lesson from credit-impulse project: block bootstrap undercovers in short samples).

## 6. Robustness (pre-specified)

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

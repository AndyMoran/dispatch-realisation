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

Sources, endpoints and manifests: see `DATA_SOURCES.md`. Data window: *[to fill]*. Sample: battery BM units with ≥ *[N]* settlement periods of MDO/MDB data.

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

- H1: *[regression of metrics on adjustment set; ranking on residuals]*
- Design selection: by the ordered design hierarchy and triggers in `PROJECT.md` §5A (single source; not restated here). The selected design and its trigger statistics, as recorded in the PROJECT.md decision log at Gate A1, are copied here at lock: *[design, statistics, date]*.
- H2: staggered-adoption event study, *[Callaway–Sant'Anna / Sun–Abraham]*, not-yet-treated controls, event window *[−k, +k]* weeks. Report pre-trends.
- H3: unit fixed effects, time fixed effects; standard errors clustered by unit.
- **£/MW/yr definition:**
  - Numerator: declaration-attributable Δ accepted MWh per year × margin.
  - Margin: *[proposed: accepted offer price − Market Index Price for that settlement period; mirror for bids, sign conventions stated]*, i.e. the BM premium over wholesale. Alternatives: system price; Gale et al.'s profit measure if verified (E1, E2).
  - Denominator: registered MW (GC), as for the outcome in §3. Not max MEL: MEL is a declaration. Per MWh usable reported as secondary.
  - Caveat: the BM is pay-as-bid. Better declarations may change which offers are accepted and at what price, so volume × margin is a first-order approximation.

## 5. Inference

Significance level / interval coverage: *[fill]*. Multiple comparisons across four metrics: *[fill]*. Interval method validated by simulation before use (lesson from credit-impulse project: block bootstrap undercovers in short samples).

## 6. Robustness (pre-specified)

- Offers and bids as separate outcomes
- Excluding system-flagged acceptances
- NESO Tier B accepted ÷ in-merit volume, reported descriptively only, with the M1 caveat stated
- Adding the unit's offer price relative to the fleet median (from BOD) as a control, to probe the pricing threat (O1)
- Excluding units with known ancillary-service energy reservations
- Alternative usable-MWh assumptions (P4)
- Dropping the first *[n]* weeks after each unit's adoption (learning period)

## 7. What would change our conclusions

- Pre-trends in H2 → report as descriptive only.
- Mass-balance residuals too large to interpret → drop metric 2; report why.
- Fewer than *[N]* adopters → design note only.

## 8. Publication commitments

- Results published whether strong, weak or null.
- Ranking published raw and adjusted; adjusted leads.
- Each lead party receives its own result and the method ≥ 10 working days before publication; replies published alongside (PROJECT.md §7a).

## 9. Deviations log

| Date | Deviation | Reason |
|---|---|---|
| | | |

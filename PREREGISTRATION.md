# Pre-registration — Declaration Quality and Battery Dispatch in GB

**Status: DRAFT — not locked.**
Lock target: start of Week 2, after Gate A1 (which uses declaration data only) and before any outcome data is examined, including the Gate A2 stakes calculation.
On lock: tag a release, deposit on Zenodo (public timestamp), and record the commit hash here: *[hash]*.

Any deviation after lock is recorded in §9 with date and reason.

---

## 1. Questions

- **H1 (descriptive):** Declaration quality varies across GB battery BM units after adjusting for duration, node, commissioning date and time since GC0166 adoption.
- **H2 (within-unit):** A unit's share of in-merit volume accepted rises after it switches to MDO/MDB declarations.
- **H3 (within-unit):** Improvements in a unit's declaration-quality metrics are associated with higher accepted share of in-merit volume.
- **H4 (enforcement):** Declaration quality improves fleet-wide after NESO's grace period ends. *(FORWARD-LOOKING; run only if the end date falls within the data window.)*

## 2. Data

Sources, endpoints and manifests: see `DATA_SOURCES.md`. Data window: *[to fill]*. Sample: battery BM units with ≥ *[N]* settlement periods of MDO/MDB data.

## 3. Variables

**Outcome:** accepted volume ÷ in-merit volume, per unit per *[day / week]*, NESO Tier B (stage exclusions applied). If NESO caps a unit's in-merit volume by its own MEL/MDO (assumption M1 fails), use instead: *[accepted MWh per MW registered / accepted ÷ physically feasible volume]*.

**Declaration-quality metrics** (definitions to finalise, with formulas):
1. Conservation error: |MDO + MDB − usable MWh| / usable MWh
2. Mass-balance error: |ΔMDO − (−∫ metered export + BOA energy, efficiency-adjusted)|
3. Redeclaration latency: minutes from BOA timestamp to next MDO/MDB update
4. Conservatism: declared MDO ÷ reconstructed deliverable energy

**Treatment (H2):** first MDO/MDB submission date per unit.

**Adjustment set:** duration, node (or zone), commissioning date, time since adoption.

## 4. Estimation

- H1: *[regression of metrics on adjustment set; ranking on residuals]*
- Design selection: by the ordered design hierarchy and triggers in `PROJECT.md` §5A (single source; not restated here). The selected design and its trigger statistics, as recorded in the PROJECT.md decision log at Gate A1, are copied here at lock: *[design, statistics, date]*.
- H2: staggered-adoption event study, *[Callaway–Sant'Anna / Sun–Abraham]*, not-yet-treated controls, event window *[−k, +k]* weeks. Report pre-trends.
- H3: unit fixed effects, time fixed effects; standard errors clustered by unit.
- **£/MW/yr definition:**
  - Numerator: declaration-attributable Δ accepted MWh per year × margin.
  - Margin: *[proposed: accepted offer price − Market Index Price for that settlement period; mirror for bids, sign conventions stated]*, i.e. the BM premium over wholesale. Alternatives: system price; Gale et al.'s profit measure if verified (E1, E2).
  - Denominator: *[proposed: registered MW (max MEL over window)]*. Per MWh usable reported as secondary.
  - Caveat: the BM is pay-as-bid. Better declarations may change which offers are accepted and at what price, so volume × margin is a first-order approximation.

## 5. Inference

Significance level / interval coverage: *[fill]*. Multiple comparisons across four metrics: *[fill]*. Interval method validated by simulation before use (lesson from credit-impulse project: block bootstrap undercovers in short samples).

## 6. Robustness (pre-specified)

- Tier A and Tier C outcomes alongside Tier B
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

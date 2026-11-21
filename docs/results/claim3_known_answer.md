# Claim 3 known-answer result: dropped from version 1

*For a reviewer checking the method.*

Claim 3 is not part of version 1. Its known-answer suite (PREREGISTRATION §8) missed its bands at both run lengths, 4 and 20 scored weeks. §8 states the consequence: "If the suite cannot meet these bands, Claim 3 is dropped from version 1, and the report says so." No real unit has been scored, and none will be scored on Claim 3 in this version.

The over-declarers were not missed for want of an estimate. Both batteries' estimates landed near the faults planted in them. The flags failed on the control condition: their placebo sets showed the same shortfalls, so the placebo intervals excluded zero. In these runs the lower-wall criterion did not establish that the accepted energy was deliverable.

## What the suite tested

The suite ran each battery in §8's table 100 times at each length, under §8's three instruction-sizing regimes:

- **(i) sized to MDO:** *u* × the MDO published before acceptance, with *u* drawn from [0.2, 1].
- **(ii) sized to MEL × duration:** the instruction runs at MEL less the battery's contracted response, so that its power plus response stays within 50 MW.
- **(iii) sized to PN deviation only:** a turn-down of the flow PN schedules, at *u* × the smallest |PN| over the instruction.

Each battery ran twice: as an **A-declarer**, whose declarations follow Branch A (MDO as energy at the meter), and as a **B-declarer**, whose declarations follow Branch B (MDO as stored energy). Each declarer's declarations were scored under both branches. A run is **flagged** only if all four conditions of §5.7 hold under both scoring branches. The pass rules, the sizing rules and the delivery model were fixed before the run (PROJECT.md §11, 21 November 2026). The code is at `9bf6ed1`.

## Results

Every judged cell passed except two groups. Each row gives the runs in band out of 100, for the A-declarer and the B-declarer, at each length. What "in band" means depends on the cell:

- **Not flagged** (honest, under-declaration, fast redeclarer): the run was scored under both branches and not flagged. The fast redeclarer's run must also have no instruction with *r* > 1 in its matched scoring (A-declarer under A, B-declarer under B).
- **Flagged, with the estimate in band** (the two over-declarers): the run was flagged, and its matched estimate lay in §8's band: Δ̂ in [7, 13] MWh, or *f̂* in [0.15, 0.25].
- **Flagged, or not identified** (static profile): the run was flagged, or was not identified under at least one scoring branch.

Unscored runs count as out of band. The table groups some batteries and regimes; [`outputs/known_answer/claim3.json`](../../outputs/known_answer/claim3.json) holds every cell, including the report-only ones.

| Battery | Regime | Required | 4 weeks (A, B) | 20 weeks (A, B) | Result |
|---|---|---|---|---|---|
| Honest; frequency response; ramp-limited; derating | (i), (ii), (iii) | 95 | 99–100 | 99–100 | Pass |
| Constant under-declaration, 20 MWh | (i), (ii), (iii) | 95 | 100, 100 | 100, 100 | Pass |
| Static profile copied from maximum | (i) | 95 | 100, 100 | 100, 100 | Pass |
| Constant over-declaration, Δ = 10 MWh | (i) | 80 | 10, 11 | 1, 0 | **Miss** |
| Proportional over-declaration, *f* = 0.2 | (i) | 80 | 9, 13 | 5, 6 | **Miss** |
| Redeclares 5 minutes after each BOA | (i) | 95 | 100, 14 | 100, 0 | **Miss** (B-declarer) |

The four plain honest batteries were flagged once in 4,800 declarer-runs: 48 cells of 100 runs across regimes, lengths and declarers.

The static profile's band allows either outcome. Every run landed in one or the other: no run was identified under both branches and left unflagged.

| Static profile, regime (i) | Flagged | Not identified under at least one branch | In band |
|---|---|---|---|
| 4 weeks, A-declarer | 1 | 99 | 100 |
| 4 weeks, B-declarer | 1 | 99 | 100 |
| 20 weeks, A-declarer | 63 | 37 | 100 |
| 20 weeks, B-declarer | 66 | 34 | 100 |

## Why the over-declarers were not flagged

The estimates were right; the control condition failed. For the proportional battery, the median *f̂* was 0.19–0.20 against a planted 0.2, and the battery was identified under both branches in 69–97 runs. For the constant battery, the median Δ̂ was 10.7–11.6 MWh against a planted 10 MWh.

The placebo set is a control group, chosen by a computed criterion. It includes the fitted offers for which the protocol's computed lower-wall value, at the start of the acceptance's period, is at least *A* (§5.6). §5.6 reasons that a shortfall there cannot be over-declaration, so a unit's placebo fit should find no kink. The over-declarers' placebo fits did find one.

A diagnostic rerun checked this for runs 0–9 at 20 weeks: regime (i), the A-declarer, scored under Branch A only. It used the suite's seeds and rebuilt the scoring code's own placebo set, whose wall uses that scoring's η̂ ([`src/synthetic/claim3_diagnosis.py`](../../src/synthetic/claim3_diagnosis.py); output in [`outputs/known_answer/claim3_diagnosis.json`](../../outputs/known_answer/claim3_diagnosis.json)). Placebo *f̂* was 0.04–0.19 for the proportional battery and 0.31–0.44 for the constant battery. In most runs the placebo interval excluded zero, so §5.7's third condition failed.

The simulation's ground truth shows why. The table gives the diagnostic aggregate over those ten runs. It sorts each placebo offer that fell short into one of two mutually exclusive classes, by whether the battery's simulated true stock (√η × stored energy at acceptance) was at least *A*.

| Battery (A-declarer, A-scored, runs 0–9) | Placebo offers | Fell short | True stock ≥ *A*: stopped by protection | True stock < *A*: wall above true stock |
|---|---|---|---|---|
| Proportional, *f* = 0.2 | 1,638 | 93 | 64 | 29 |
| Constant, Δ = 10 MWh | 1,578 | 253 | 215 | 38 |
| Honest | 1,921 | 0 | 0 | 0 |

- **True stock ≥ *A*: stopped by protection.** The battery held at least *A*, but its deliverable energy after protecting scheduled PN, known instructions and contracts was smaller, and it stopped there. In every such case the protected energy was positive. The lower wall counts stored energy and cannot see protection.
- **True stock < *A*: wall above true stock.** The battery held less than *A*, but the computed lower wall was at least *A*. The wall depends on η̂, and an error in η̂ displaces it, as with Claim 2's wall (ASSUMPTIONS P11).

The totals add up: 93 = 64 + 29, and 253 = 215 + 38. Protection and η̂ error broke the link between a wall at or above *A* and energy deliverable after protection. This is recorded in ASSUMPTIONS P12. It shows what the criterion failed to establish in these runs, not that the physical reasoning fails in general. The diagnosis explains the miss; it does not change the gate.

## The expected miss

The fast redeclarer's B-declarer missed, as predicted before the run (PROJECT.md §11, 21 November 2026). Under regime (i), NESO sizes an offer at *u* × the published MDO. A B-declarer publishes stored energy, and Branch B scoring reads its deliverable energy as √η̂ × MDO, so *r* = *u*/√η̂. Any offer with *u* above √η̂, about 8% of them, has *r* > 1. The band allows none.

## What this means for version 1

Version 1 reports Claim 3 as dropped under §8, with this result and its diagnosis. No corrected placebo is used to reinstate it.

No claim in version 1 now gives a per-unit finding of over- or under-declaration. Claim 1's per-unit flags are reportable at no tested length, and Claim 2's hard flag is not reported (PREREGISTRATION §12, deviation 2). Claim 4's case series and the fleet-level results remain.

## Conditions for any future test

A later deviation (PREREGISTRATION §12) could test a corrected placebo. It must be specified in full before any rerun:

1. **What the placebo must establish.** The battery had enough deliverable energy after PN protection to meet the instruction, at acceptance and throughout it. It also had enough power after its ramp, derating, response and other commitments. Both must be shown independently of the declaration and of the observed shortfall.
2. **How, in each setting.** In the synthetic suite, the simulated ground truth establishes it. For real units, the lower wall cannot establish it alone; the deviation must name independent evidence or a conservative bound.
3. **Rules fixed in advance.** The placebo selection rule and its minimum sample requirements are defined before the rerun.
4. **The same test.** The full relevant suite reruns against the unchanged bands.
5. **The record stands.** The version 1 result stays as reported here. If the corrected suite still misses, Claim 3 remains out.

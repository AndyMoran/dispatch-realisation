# Claim 4 synthetic check: rule

*For a reviewer checking that Claim 4's known-answer gate was fixed before it ran. Approved by Andy on 21 November 2026 as deviation 3 (PREREGISTRATION §12, tag `v1.0.3-lock`). No Claim 4 result for any battery, synthetic or real, existed when it was approved.*

**The rule in one sentence.** Before any nameplate is searched for, honest synthetic batteries are scored on Claim 4 against a ceiling set at the most energy each could actually have delivered; if any of them shows an upper-wall violation in more than 5 of 100 runs, for either declarer, at either 4 or 20 weeks, Claim 4 is not run on real units in version 1.

## Why the check is needed

Claim 4's upper wall is *N* − (max K − K_t) (PREREGISTRATION §6). Its K is the same week's cumulative change that builds Claim 2's lower wall, using η̂ (§3). An error in η̂ displaces K by about |η̂ − η| × the energy imported between two times in the week. In the first Claims 1–2 run, η̂ ranged 0.863–0.901 at 4 weeks around a true 0.88, and that displacement made Claim 2 flag honest batteries (ASSUMPTIONS P11). Claim 4's tolerance is 0.02 × *N*. §8 sets no known-answer band for Claim 4, so nothing yet shows that an honest unit cannot cross its wall. §6 states that "an honest unit still cannot spuriously violate the wall"; that holds with the true η, and is untested with η̂.

## What runs

- **Gating batteries:** the four plain honest batteries (honest, frequency response, ramp-limited, derating) and the constant 20 MWh under-declarer, which cannot over-declare.
- **Reported only:** the constant over-declarer (Δ = 10 MWh) and the proportional over-declarer (*f* = 0.2), as detection rates.
- **Simulations:** the Claims 1–2 batteries as built (`src/synthetic/battery.py`), with the suite's seeds, 100 runs each, at 4 and at 20 scored weeks. No new simulation rule.
- **Declarers:** each battery declares under Branch A and, separately, under Branch B, as on 18 November. The gate is judged on the matched scoring (A-declarer under A, B-declarer under B). The cross pairs are reported.
- **η̂:** from each run's own meter over its window, as for a real unit (§3).
- **Scoring:** Claim 4 exactly as §6 defines it. A period is in violation only where D^decl_t > *N* − (max K − K_t) + 0.02 × *N* at its start, with K built within each ISO week. The inequality is strict, as §6 writes it: equality with the ceiling, or any excess within the tolerance, is not a violation. Physics-inconsistent weeks, where max K − min K > 1.02 × *N*, are counted and reported. The code is written and committed, with hand-worked tests, before the check runs.

## The ceiling *N*, on the declaration's energy basis

§6 compares D^decl with the wall. D^decl is energy deliverable at the meter: under Branch A, MDO plus the PN and accepted-BOA protection added back; under Branch B, √η̂ × MDO plus the same (§3). K is a change in that same meter-side energy. So *N* must be the most energy the battery could have delivered at the meter, with protection added back, not its raw stored energy.

- **Gate: *N* = √η × S_max**, where S_max is the highest true stored energy the battery reaches in the run and η = 0.88 is its true efficiency. This is the most the battery could ever have delivered at the meter. Under Branch A an honest unit's D^decl can reach it but never exceed it; under Branch B it can differ from it by the η̂ error, which is part of what the check measures. It is the honest worst case on the declaration's basis.
- **Reported: *N* = S_max**, the same ceiling stated in stored energy, as a real nameplate is stated. It leaves the honest battery about 6% of S_max of room on top of the tolerance (1 − √η = 0.062).
- **Reported: *N* = U = 100 MWh**, §8's common setting. The synthetic battery's windows aim at 15% and 85% of U (`config/synthetic.toml`), so this leaves about 20 MWh of room. A pass here would flatter Claim 4.

The gate is deliberately at least as strict as Claim 4's use on real units, whose nameplates are stated in stored energy.

## The gate

- **False-flag rate:** for each gating battery, declarer and length, the share of runs in which at least one settlement period of any scored week is in violation, under the matched scoring with the gating ceiling.
- **Threshold:** at most 5 of 100 runs; that is, at least 95 runs with no violation. This is `bands.min_share` (`config/synthetic.toml`) and §8's "at most 5% of the time" for honest batteries.
- **Unscored runs:** a run left unscored (for example, η̂ out of bounds) counts against the battery, as on 18 November.
- **Separate gates:** 4 weeks and 20 weeks are separate required gates, as for Claim 3. Passing at one does not make up for missing at the other.

## What follows

- **Pass, for every gating battery, declarer and length:** the nameplate search proceeds (§6, two working days). Claim 4 is reported publicly only in aggregate (PROJECT.md §7a), beside this check's result.
- **Any miss:** no nameplate search. Claim 4 is not run on real units in version 1. The check's result is published with the other known-answer results, as a limit set by efficiency, like Claim 2's (P11).
- **Either way:** the reported ceilings, the cross pairs, the over-declarers' detection rates and the counts of physics-inconsistent weeks are published. No battery, ceiling, threshold or rule changes after the run.

## Order of work

1. This rule, the §12 entry and the decision-log row are committed, and `v1.0.3-lock` is tagged and archived, before any Claim 4 code runs on any battery.
2. Claim 4 code with hand-worked tests and planted bugs, and the check runner, are committed.
3. The check runs once; its results are committed; the outcome follows the rule above.

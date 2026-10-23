# I4 optimiser map — method

For: a reviewer checking how this project links BM units to the companies that optimise them.

Written 23 October 2026, before any unit was classified.

## The point

The benchmark publishes by BM unit. It names an optimiser only where public evidence ties that optimiser to that unit. The lead party alone is not evidence: an owner, a utility or a route-to-market provider can be lead party while another company optimises the unit (ASSUMPTIONS.md I4).

## Steps

1. **Fleet.** The battery fleet is the set of units that submit non-default MDO/MDB, excluding pumped storage and hydro (ASSUMPTIONS.md M10). Reference data has no battery fuel type, so fuel type is a secondary check only. Units with `OTHER` fuel type and no MDO/MDB are listed for manual review, not dropped.
2. **Lead party.** Record each unit's lead party from the same snapshot.
3. **Classify the lead party** as optimiser, owner, utility or route-to-market provider, from the company's own description of its business. Record the source.
4. **Find unit-level evidence** linking an optimiser to the site: the optimiser's or owner's press release naming the site, a regulatory filing, or the owner's annual report. Third-party commentary alone is not enough.
5. **Grade each unit:**

| Grade | Meaning | Use |
|---|---|---|
| A | A primary source names the optimiser for this site | Optimiser-level claims allowed |
| B | Lead party is an optimiser and no contrary evidence found | Reported, not used for optimiser-level claims |
| C | Unknown or conflicting | Unit-level results only |

6. **Date the evidence.** Optimiser contracts change. Each grade records the date of its source and the period it covers.
7. **Count before promising.** PROJECT.md §5A allows optimiser-level claims only if the mapping is clean. Report the share of units and of MW at grade A. Report separately the units with evidence of an optimiser change since 2024; these give the strongest variation.

## What this map does not show

It shows who optimised a unit, on stated evidence, at stated dates. It does not show who controls declarations day to day, nor contract terms.

## Inputs still needed

- The reference snapshot: run `python -m src.ingest.reference`.
- Threshold for "clean", decided 23 October 2026: optimiser-level claims only if grade A covers at least half the scored fleet by MW.

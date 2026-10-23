# M1 denominator check — result

For: a reviewer checking why Workstream A's outcome changed before the pre-registration locked.

Checked 23 October 2026 against NESO primary documents. No outcome data was examined.

## Finding

**M1 is false.** NESO's in-merit volume for a unit depends on that unit's own declarations, and the declaration it depends on changes at the unit's GC0166 switch. Accepted ÷ in-merit volume therefore cannot be Workstream A's outcome.

## Evidence

1. **Before GC0166, a unit's own MEL/MIL caps its feasible volume.** NESO computes each unit's feasible volume per 5-minute period from its average PN, maximum MEL and minimum MIL. The in-merit stack is built from these feasible volumes. Since v2.0 (16 May 2025) NESO also caps accepted volume at MEL/MIL. Source: NESO, *Skip Rate Methodology & Implementation Guide* v2.0, "Preparation of Data" and change log V2.
2. **From 25 June 2026, storage declarations enter available volume.** NESO's Summer 2026 slides list four methodology changes. The first: GC0166 storage parameters are used to calculate available volume in the skip rate calculation, from 25 June. Source: NESO, *Dispatch Efficiency Beyond Energy* slides, slide 6.
3. **The guide does not yet describe the new rule.** The published guide is still v2.0 (May 2025), which says battery state of charge is not considered. No later version was found. The exact formula NESO now uses is unpublished.

## Why it matters

The denominator is not just declaration-dependent. Its *definition* changes on the unit's switch date: MEL-based before, MDO/MDB-based after. That date is the treatment in design 1. A before/after change in accepted ÷ in-merit would mix the real effect with a change in how NESO counts. The two cannot be separated.

## Other findings from the same documents

- **Default values mark non-adopters.** Units not yet on GC0166 have ±9999 MWh published as MDO/MDB (NESO webinar, 3 Nov 2025, FAQ; GC0166 Final Modification Report). Adoption date must be the first *non-default* submission, not the first record. Refines M4.
- **A second methodology change hits batteries in summer 2026.** NESO excludes units with Quick or Slow Reserve contracts in the direction of the contract, from "Summer" 2026 (same slide). This changes in-merit volume for reserve-contracted batteries at an unpublished date. It is a coincident measurement shock for any design that uses NESO in-merit volume, including design 3.
- **NESO restates history after methodology changes.** It republished all skip datasets in November 2025 (stage 5 bug). Expect further vintages (R8).

## Consequence

Switch the outcome to **accepted MWh per MW registered**, per PROJECT.md §5A's pre-written fallback. Registered MW must come from a source fixed in advance, not from MEL, or the declaration dependence returns by another route. NESO In-Merit files remain usable for Workstream B and for descriptive context, not as A's outcome.

## Sources

- NESO, *Skip Rate Methodology & Implementation Guide* v2.0, 16 May 2025: https://www.neso.energy/document/350061/download
- NESO, *Dispatch Efficiency Beyond Energy* slides, summer 2026: https://www.neso.energy/document/384271/download
- NESO, *Dispatch Transparency webinar*, 3 Nov 2025: https://www.neso.energy/document/371216/download
- NESO, *GC0166 Draft Final Modification Report*: https://www.neso.energy/document/362881/download

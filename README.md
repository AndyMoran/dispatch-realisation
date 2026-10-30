# Dispatch Realisation of GB Batteries

Do GB battery storage units tell the control room the truth about how much energy they hold? This project checks each unit's declarations against its own meter.

**Status:** pre-registration drafted (October 2026); nothing has been scored. Nothing here is a result yet.

---

## In plain terms

The electricity control room constantly buys small adjustments: a bit more power here, a bit less there. Batteries are often the cheapest seller. But a battery is a tank with a pipe: it can push hard (power, MW), but only for so long (energy, MWh).

Since 2026, Grid Code modification **GC0166** has required batteries to declare what is in the tank, through two parameters: **Maximum Delivery Offer (MDO)** and **Maximum Delivery Bid (MDB)**. Elexon has published them per unit on BMRS since 25 June 2026, under BSC modification P499. The control room sizes its instructions from them. NESO's own trial found that submitted values overstated what batteries could deliver.

Yet the control room often skips cheaper batteries and runs gas instead. NESO's own review of why rated zonal allocation, frequency response and reserve services among the strongest causes. It finished in April 2026, before declarations were published, so it could not test them. This project tests that one hypothesis.

So the question is simple: **are the declarations physically true?** A battery's meter records every MWh that goes in and out. If its declarations say the tank held more, or less, than the meter allows, the declarations are wrong. This project audits that, for every battery unit, from public data only. It publishes fleet-level results and the method, and sends each lead party its own units' results privately.

## In detail

Five claims, defined in [`PREREGISTRATION.md`](PREREGISTRATION.md):

1. **Mass-balance coherence (primary):** declarations should change as the meter says stored energy changed.
2. **Lower-wall violations (primary):** a unit should never declare less than the energy its meter proves it held.
3. **Non-delivery (secondary):** if NESO instructs energy within a unit's declared MDO and the unit runs out early, it over-declared.
4. **Upper-wall violations (case series):** where a nameplate MWh is disclosed, a unit should never declare more than its tank could hold.
5. **Redeclaration latency (fleet level):** how quickly units update their declarations after an instruction.

The result is a **flag table**, not a ranking: for each unit, whether its declarations are physically consistent with its meter, with uncertainty and with each limit stated. In this version the table goes privately to each lead party, for its own units; what is published is the fleet-level picture. Units may be named in a later version, but only once five written conditions are met (see [`PREREGISTRATION.md`](PREREGISTRATION.md) §11).

The claims do not test every channel equally. Over-declaration, the one most tied to lost trust, is the one this version is least able to measure. Finding no violations is not evidence of compliance.

A first finding came out of the design work: public registers do not record how much energy GB batteries hold. REPD records power only. In SSEN's Embedded Capacity Register the storage-MWh field read "DATA NOT AVAILABLE" for every connected battery site. That is why the audit uses tests that need no capacity figure.

See [`PROJECT.md`](PROJECT.md) for scope and timeline, [`ASSUMPTIONS.md`](ASSUMPTIONS.md) for the assumptions ledger, and [`DATA_SOURCES.md`](DATA_SOURCES.md) for datasets and vintage policy.

## What this is not

- Not a verdict on any operator or optimiser. It tests declarations against physics, not commercial skill or intent.
- Not a ranking. Units are flagged, with uncertainty, not placed in order.
- Not a revenue estimate. Whether declaring well pays is deferred to a later version; this one could not identify it.
- Not tied to a positive result. If declarations turn out to be physically consistent, that is the finding.
- Not an explanation of skip rates. It tests one hypothesis, and cannot say how much each cause contributes.
- Not an association between declaration quality and skips. It measures how common violations are, not whether worse declarers are skipped more.
- Not a measure of how NESO perceives declarations, and not an estimate of the carbon or cost of skips.

## Repository layout (proposed)

```
├── README.md
├── PROJECT.md              scope, gates, timeline, decision log
├── ASSUMPTIONS.md          assumptions ledger
├── DATA_SOURCES.md         datasets, endpoints, vintage policy
├── PREREGISTRATION.md      locked before any unit is scored
├── PIPELINE_RULES.md       how the code is built
├── WRITING.md              documentation standard
├── data/
│   ├── raw/                as downloaded; never edited (gitignored)
│   ├── interim/            (gitignored)
│   └── manifests/          download dates + hashes (committed)
├── src/
│   ├── ingest/             BMRS, NESO pulls
│   ├── physics/            energy balance, SoC reconstruction
│   ├── claims/             Claims 1–5 (Claim 3 a separate module)
│   └── synthetic/          known-answer batteries
├── notebooks/              exploration only; results come from src/
├── outputs/                figures, tables
└── docs/                   papers, posts, notes
```

## Reproducing

To follow. Every published number will regenerate from `src/` against pinned data manifests.

## Licence

Code: [MIT](LICENSE). Text, figures and derived tables: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source data remain under their own licences; see Data attribution.

## Data attribution

Contains BMRS data © Elexon Limited copyright and database right 2026. Used under Elexon's [licence to use BMRS open data](https://www.elexon.co.uk/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/).

Supported by National Energy SO Open Data. Used under the [NESO Open Data Licence v1.0](https://www.neso.energy/data-portal/neso-open-licence).

Neither Elexon nor NESO endorses this project. Scores, flags and estimates here are this project's derived results, not Elexon or NESO data.

## Citation

*To follow (Zenodo DOI on first release).*

## AI use statement

*To write.*

## Author

Andy Moran — Heaviside Analytics
GitHub: [AndyMoran](https://github.com/AndyMoran)

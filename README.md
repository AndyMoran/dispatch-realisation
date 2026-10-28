# Dispatch Realisation of GB Batteries

How well do GB battery storage units tell the control room what they can do, and what does it cost when they're passed over?

**Status:** scoping (October 2026). Nothing here is a result yet.

---

## In plain terms

The electricity control room constantly buys small adjustments: a bit more power here, a bit less there. Sellers queue up with prices. A **skip** is when the control room passes over a cheaper seller and pays a dearer one.

Batteries are often the cheapest seller. But a battery is a tank with a pipe: it can push hard (power, MW), but only for so long (energy, MWh). Until 2026 a battery could declare its power but not its available energy. A control room that can't see the tank is cautious, and caution means picking something else.

In 2026, Grid Code modification **GC0166** let batteries declare the tank directly, through two new parameters: **Maximum Delivery Offer (MDO)** and **Maximum Delivery Bid (MDB)**. These have been published per unit on BMRS since 25 June 2026, under BSC modification P499. A third parameter, Future State of Energy (FSoE), is not confirmed as published; the method works without it, with wider uncertainty.

This project's main contribution is a standard: **how good are those declarations?** It measures whether each battery's declarations match the physics of what it actually did, and publishes the result per unit, with a right of reply. No such standard exists yet, and it needs no assumptions about the control room.

A second, harder question follows: **does declaring well pay?** That one is answered as far as the data allow, with its limits stated in advance.

## In detail

**Declaration quality** is measured from public data only, using energy balance:

- **Conservation:** the energy a unit declares it can export and import, plus what it holds back for its own schedule, should stay steady.
- **Mass balance:** changes in declared energy should match metered energy in and out, allowing for efficiency losses.
- **Redeclaration latency:** how quickly a unit updates MDO/MDB after an instruction.
- **Conservatism:** declared deliverable energy vs the energy reconstructed from metered output alone.

**Rankings** are published per BM unit, both raw and adjusted for duration, network location, commissioning date and time since GC0166 adoption. The adjusted ranking leads, because raw declaration quality mostly reflects hardware and location. Lead party is shown for context only: lead party, operator and owner are often different companies. Each lead party sees its results and the method at least 10 working days before publication.

**Whether declaring well pays** is tested from change within each unit over time. That design cannot rule out other changes happening at the same time, such as a new optimiser or reserve contract, so the result is reported as an association. Whether it counts as secondary or exploratory depends on how small an effect the data could detect, under a rule fixed in advance (PREREGISTRATION.md §4). The scale of what is at stake comes separately, from the value of battery skips (PROJECT.md §5A, Gate A2).

**Skip measurement** follows NESO's published methodology (stage exclusions), reproduced and validated against NESO's aggregate figures, with a £ layer: skipped volume × cost difference vs the marginal accepted action.

See [`PROJECT.md`](PROJECT.md) for scope, gates and timeline, [`ASSUMPTIONS.md`](ASSUMPTIONS.md) for the assumptions ledger, [`DATA_SOURCES.md`](DATA_SOURCES.md) for datasets and vintage policy, and [`PREREGISTRATION.md`](PREREGISTRATION.md) for pre-registered analyses.

## What this is not

- Not a verdict on any operator. It is a measurement, with stated uncertainty and stated limits.
- Not causal without conditions. The within-unit design identifies an effect only under stated assumptions (parallel trends, no coincident shocks); pre-trends are reported.
- Not tied to a positive result. A null is a valid outcome: if declaration quality doesn't predict acceptance, that is the finding.
- Not a revenue forecast or siting tool.

## Repository layout (proposed)

```
├── README.md
├── PROJECT.md              scope, gates, timeline, decision log
├── ASSUMPTIONS.md          assumptions ledger
├── DATA_SOURCES.md         datasets, endpoints, vintage policy
├── PREREGISTRATION.md      locked before outcome data is examined
├── PIPELINE_RULES.md       how the code is built
├── WRITING.md              documentation standard
├── data/
│   ├── raw/                as downloaded; never edited (gitignored)
│   ├── interim/            (gitignored)
│   └── manifests/          download dates + hashes (committed)
├── src/
│   ├── ingest/             BMRS, NESO pulls
│   ├── physics/            energy balance, SoC reconstruction
│   ├── metrics/            declaration quality
│   ├── skips/              skip measurement layer
│   └── estimate/           ranking, event study
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

Neither Elexon nor NESO endorses this project. Scores, rankings and estimates here are this project's derived results, not Elexon or NESO data.

## Citation

*To follow (Zenodo DOI on first release).*

## AI use statement

*To write.*

## Author

Andy Moran — Heaviside Analytics
GitHub: [AndyMoran](https://github.com/AndyMoran)

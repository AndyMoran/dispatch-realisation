# Can GB Battery Declarations Be Audited From Public Data?

*Partly — and the two gaps that stop the rest.* (Repository: Dispatch Realisation of GB Batteries.)

NESO can see which batteries hold contracts that lawfully lower their declarations. Nobody outside NESO can. So the declarations the control room now relies on cannot be checked independently from published data.

Version 1 delivers a preregistered auditability assessment of GB public balancing data for verifying battery declarations. It documents two key data gaps, tests the proposed checks against synthetic batteries with known ground truth, and measures where those checks work, where they fail, and why. It reports the fleet-level findings and data limitations, but makes no per-unit finding of over- or under-declaration. The open, tested pipeline provides a basis for future work with better data or revised methods.

**Status:** pre-registration locked on 18 November 2026 ([DOI](https://doi.org/10.5281/zenodo.24343931)), with four deviations recorded before scoring (§12): nested resampling ([DOI](https://doi.org/10.5281/zenodo.24354704)), and, after the first known-answer run failed at 4 weeks, Claim 1 reported only at lengths where its tests pass and Claim 2's wall reported as failing ([DOI](https://doi.org/10.5281/zenodo.24416574)). Two more followed the known-answer results: a known-answer gate for Claim 4, with version 1 bounded as an auditability assessment ([DOI](https://doi.org/10.5281/zenodo.24439737)), and a rule for releasing Claim 4 results without identifying any unit ([DOI](https://doi.org/10.5281/zenodo.24439749)). Claim 3 is dropped from version 1: its known-answer suite missed its bands, as §8 provides ([result](docs/results/claim3_known_answer.md)). Claim 4's synthetic check missed its gate: honest batteries crossed the upper wall in most runs, so Claim 4 is not run on real units in version 1 (deviation 3). No real unit has been scored.

---

## In plain terms

The electricity control room constantly buys small adjustments: a bit more power here, a bit less there. Batteries are often the cheapest seller. But a battery is a tank with a pipe: it can push hard (power, MW), but only for so long (energy, MWh).

Since 2026, Grid Code modification **GC0166** has required batteries to declare what is in the tank, through two parameters: **Maximum Delivery Offer (MDO)** and **Maximum Delivery Bid (MDB)**. Elexon has published them per unit on BMRS since 25 June 2026, under BSC modification P499. The control room sizes its instructions from them. NESO's own trial found that submitted values overstated what batteries could deliver.

Yet the control room often skips cheaper batteries and runs gas instead. NESO's own review of why rated zonal allocation, frequency response and reserve services among the strongest causes. It finished in April 2026, before declarations were published, so it could not test them. This project tests that one hypothesis.

So the question is simple: **are the declarations physically true?** A battery's meter records every MWh that goes in and out. If its declarations say the tank held more, or less, than the meter allows, the declarations are wrong. This project tests how far public data can answer that, for every battery unit. It publishes fleet-level results and the method, and sends each lead party its own units' descriptive results privately.

The answer so far is "partly". GB's published data serve settlement first and audit second. Two gaps stop a complete audit: no register records how much energy each battery holds, and NESO's auction results do not say which BM unit holds each contract. Neither needs new measurement: the auction mapping needs publishing; the energy register needs an existing field filled and sites keyed to BM units.

## In detail

Five claims, defined in [`PREREGISTRATION.md`](PREREGISTRATION.md):

1. **Mass-balance coherence (primary):** declarations should change as the meter says stored energy changed.
2. **Lower-wall violations (primary):** a unit should never declare less than the energy its meter proves it held.
3. **Non-delivery (secondary):** if NESO instructs energy within a unit's declared MDO and the unit runs out early, it over-declared.
4. **Upper-wall violations (case series):** where a nameplate MWh is disclosed, a unit should never declare more than its tank could hold.
5. **Redeclaration latency (fleet level):** how quickly units update their declarations after an instruction.

Version 1 makes no per-unit finding of over- or under-declaration. Claim 1's known-answer suite failed its reporting gate at every tested length, so no per-unit Claim 1 flags are reported ([`PREREGISTRATION.md`](PREREGISTRATION.md) §12). Claim 2's wall failed its known-answer band under the available efficiency uncertainty (§12). Claim 3 was dropped under §8 after missing its required bands; its over-declarers also failed the placebo control condition ([Claim 3 result](docs/results/claim3_known_answer.md)). Claim 4 failed its synthetic check, so no nameplate is searched for and Claim 4 is not run on real units. Version 1 publishes the fleet-level results still in scope, the known-answer results, and the limitations the published data place on verification. Each lead party receives a private pack for its own units, containing the Claim 1 score and interval without a Claim 1 flag, Claim 2 lower-wall status and its contract-exposed and unknown-status shares, Claim 5 latency, and the method. The packs contain no Claim 1–3 over- or under-declaration flags or Claim 3 per-unit results. No unit is named publicly in version 1. Unit-level findings may be considered in a later version only after the five conditions in §11 are met.

The claims do not test every channel equally. A unit shown coherent has declarations that track its meter; a unit not shown coherent may have bad declarations or contracts we cannot see. Claim 3, non-delivery, was designed as the test least affected by unseen contracts, but version 1 does not report it ([result](docs/results/claim3_known_answer.md)). Finding no violations is not evidence of compliance.

A first finding came out of the design work: public registers do not record how much energy GB batteries hold. REPD records power only. In SSEN's Embedded Capacity Register the storage-MWh field read "DATA NOT AVAILABLE" for every connected battery site. That is why the audit uses tests that need no capacity figure. A second followed: NESO's reserve and response auction results do not identify BM units, so no battery's week could be certified free of contracts that lawfully lower its declarations. The audit therefore cannot call any unit's under-declaration provable in this version.

See [`PROJECT.md`](PROJECT.md) for scope and timeline, [`ASSUMPTIONS.md`](ASSUMPTIONS.md) for the assumptions ledger, and [`DATA_SOURCES.md`](DATA_SOURCES.md) for datasets and vintage policy.

## What this is not

- Not a verdict on any operator or optimiser. It tests declarations against physics, not commercial skill or intent.
- Not a ranking. No unit is placed in order, or flagged, in this version.
- Not a revenue estimate. Whether declaring well pays is deferred to a later version; this one could not identify it.
- Not tied to a positive result. If declarations turn out to be physically consistent, that is the finding.
- Not an explanation of skip rates. It tests one hypothesis, and cannot say how much each cause contributes.
- Not an association between declaration quality and skips. It measures how common violations are, not whether worse declarers are skipped more.
- Not a measure of how NESO perceives declarations, and not an estimate of the carbon or cost of skips.

## Repository layout

`src/model/` holds the input types shared by real and synthetic data, `src/physics/` the §3 physics, and `src/claims/` Claims 1, 2 and 4 with their scoring. `src/claims/unit.py` scores one unit, real or synthetic, from its inputs to its flags. `src/synthetic/` holds the known-answer batteries: their settings, frequency input, the honest and planted-fault batteries, the Claims 1–2 band runner (`src/synthetic/bands.py`), Claim 3's instruction-sizing regimes (`src/synthetic/regimes.py`) and its band runner (`src/synthetic/claim3_bands.py`), and the Claim 4 synthetic check (`src/synthetic/claim4_check.py`). `src/claim3/` holds Claim 3's scoring, kept for the record and for any later deviation; version 1 does not report it.

```
├── README.md
├── PROJECT.md              scope, gates, timeline, decision log
├── ASSUMPTIONS.md          assumptions ledger
├── DATA_SOURCES.md         datasets, endpoints, vintage policy
├── PREREGISTRATION.md      locked before any unit is scored
├── PIPELINE_RULES.md       what the pipeline must do
├── CODING.md               how the code is written
├── WRITING.md              documentation standard
├── config/                 thresholds and settings, each with its source
├── data/
│   ├── raw/                as downloaded; never edited (gitignored)
│   ├── interim/            (gitignored)
│   ├── derived/            small files built from raw data, with hashes (committed)
│   └── manifests/          download dates + hashes (committed)
├── src/
│   ├── model/              input types shared by real and synthetic data; thresholds
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

Cite the latest lock. Each is archived on Zenodo:

- Deviation 4 (Claim 4 release rule; `PREREGISTRATION.md` §12): Moran, A. (2026). *Can GB Battery Declarations Be Audited From Public Data?* Heaviside Analytics. https://doi.org/10.5281/zenodo.24439749 (tag `v1.0.4-lock`, commit 5e4689e).
- Deviation 3 (Claim 4 known-answer gate; version 1 as an auditability assessment; `PREREGISTRATION.md` §12): Moran, A. (2026). *Can GB Battery Declarations Be Audited From Public Data?* Heaviside Analytics. https://doi.org/10.5281/zenodo.24439737 (tag `v1.0.3-lock`, commit d730c86).
- Deviation 2 (Claim 1 reported by length; Claim 2 reported as failing its band; `PREREGISTRATION.md` §12): Moran, A. (2026). *Can GB Battery Declarations Be Audited From Public Data?* Heaviside Analytics. https://doi.org/10.5281/zenodo.24416574 (tag `v1.0.2-lock`, commit 34d9626).
- Deviation 1 (nested resampling of unit-score intervals; `PREREGISTRATION.md` §12): Moran, A. (2026). *Can GB Battery Declarations Be Audited From Public Data?* Heaviside Analytics. https://doi.org/10.5281/zenodo.24354704 (tag `v1.0.1-lock`, commit c933d76).
- Pre-registration lock, version 1: https://doi.org/10.5281/zenodo.24343931 (tag `v1.0-lock`, commit 4395934).

Citation metadata: [`CITATION.cff`](CITATION.cff). Its licence field names the code licence only, because Zenodo cannot read a list of licences from it; the text licence is stated above.

## AI use statement

*To write.*

## Author

Andy Moran — Heaviside Analytics
GitHub: [AndyMoran](https://github.com/AndyMoran)

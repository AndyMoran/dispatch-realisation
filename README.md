# Can GB Battery Declarations Be Audited From Public Data?

*Partly — and the two gaps that stop the rest.* (Repository: Dispatch Realisation of GB Batteries.)

NESO can see which batteries hold contracts that lawfully lower their declarations. Nobody outside NESO can. So the declarations the control room now relies on cannot be checked independently from published data.

Version 1 delivers a preregistered auditability assessment of GB public balancing data for verifying battery declarations. It documents two key data gaps, tests the proposed checks against synthetic batteries with known ground truth, and measures where those checks work, where they fail, and why. It reports the fleet-level findings and data limitations, but makes no per-unit finding of over- or under-declaration. The open, tested pipeline provides a basis for future work with better data or revised methods.

## Status

Pre-registration locked on 18 November 2026 ([zenodo.24343931](https://doi.org/10.5281/zenodo.24343931)). Five deviations were recorded before any real unit was scored (`PREREGISTRATION.md` §12):

1. Nested resampling of unit-score intervals ([zenodo.24354704](https://doi.org/10.5281/zenodo.24354704)).
2. After the first known-answer run failed at 4 weeks of scored data, Claim 1 is reported only at window lengths where its tests pass, and Claim 2's wall is reported as failing its known-answer band ([zenodo.24416574](https://doi.org/10.5281/zenodo.24416574)).
3. Claim 4 gained a known-answer gate, and version 1 is bounded as an auditability assessment ([zenodo.24439737](https://doi.org/10.5281/zenodo.24439737)).
4. Claim 4 results may be released only without identifying any unit ([zenodo.24439749](https://doi.org/10.5281/zenodo.24439749)).
5. Declared energy rebuilt during instructions was corrected: an instruction accepted after the declaration in force was published is no longer added back, which had counted its energy twice ([zenodo.24473559](https://doi.org/10.5281/zenodo.24473559)).

Two claims did not reach the reporting stage. Claim 3 was dropped after its known-answer suite missed its bands (§8; [result](docs/results/claim3_known_answer.md)). Claim 4 failed its synthetic check: honest batteries crossed the upper wall in most runs, so it is not run on real units in version 1 (deviation 3).

No real unit has been scored.

---

## In plain terms

The electricity control room constantly buys small adjustments: a bit more power here, a bit less there. Batteries are often the cheapest seller. But a battery is a tank with a pipe: it can push hard (power, MW), but only for so long (energy, MWh).

Since 2026, Grid Code modification **GC0166** has required batteries to declare what is in the tank, through two parameters: **Maximum Delivery Offer (MDO)** and **Maximum Delivery Bid (MDB)**. Elexon has published them per unit on BMRS since 25 June 2026, under BSC modification P499. The control room sizes its instructions from them. NESO's own trial found that submitted values overstated what batteries could deliver.

Yet the control room often skips cheaper batteries and runs gas instead. NESO's own review of why batteries are skipped rated zonal allocation, frequency response and reserve services among the strongest causes. It finished in April 2026, before declarations were published, so it could not test them. This project tests that one hypothesis.

So the question is simple: **are the declarations physically true?** A battery's meter records every MWh that goes in and out. If its declarations say the tank held more, or less, than the meter allows, the declarations are wrong. This project tests how far public data can answer that, for every battery unit. It publishes fleet-level results and the method, and sends each lead party its own units' descriptive results privately.

The answer so far is "partly". GB's published data serve settlement first and audit second. Two gaps stop a complete audit: no register records how much energy each battery holds, and NESO's auction results do not say which BM unit holds each contract. Neither needs new measurement: the auction mapping needs publishing; the energy register needs an existing field filled and sites keyed to BM units.

## In detail

Five claims, defined in [`PREREGISTRATION.md`](PREREGISTRATION.md):

1. **Mass-balance coherence (primary):** declarations should change as the meter says stored energy changed.
2. **Lower-wall violations (primary):** a unit should never declare less than the energy its meter proves it held.
3. **Non-delivery (secondary):** if NESO instructs energy within a unit's declared MDO and the unit runs out early, it over-declared.
4. **Upper-wall violations (case series):** where a nameplate MWh is disclosed, a unit should never declare more than its tank could hold.
5. **Redeclaration latency (fleet level):** how quickly units update their declarations after an instruction.

### What version 1 reports

Version 1 publishes the fleet-level results still in scope, the known-answer results, and the limits the published data place on verification. By claim:

- **Claim 1:** the known-answer suite failed its reporting gate at every tested window length, so no per-unit flags are reported. After deviation 5, the only band still missed is a planted under-declarer whose declarations sit at zero, a limit of the test rather than of the data.
- **Claim 2:** the wall failed its known-answer band under the available efficiency uncertainty (§12).
- **Claim 3:** dropped under §8; its over-declarers also failed the placebo control condition ([result](docs/results/claim3_known_answer.md)).
- **Claim 4:** failed its synthetic check, so no nameplate is searched for and it is not run on real units.
- **Claim 5:** reported publicly at fleet level; each unit's latency goes only to its own lead party.

Version 1 makes no per-unit finding of over- or under-declaration, and no unit is named publicly. Unit-level findings may be considered in a later version only after the five conditions in §11 are met.

Each lead party receives a private pack for its own units, with the method and descriptive results only: the Claim 1 score and interval, the Claim 2 lower-wall status over weeks not certified contract-free (version 1 cannot separate contract-exposed weeks from those of unknown status), and Claim 5 latency. A score describes how closely a unit's declarations tracked its meter; a flag would call that an over- or under-declaration. The packs carry scores but no flags, and no Claim 3 results.

### How to read the results

The claims do not test every channel equally. A unit shown coherent has declarations that track its meter; a unit not shown coherent may have bad declarations or contracts we cannot see. Claim 3, non-delivery, was designed as the test least affected by unseen contracts, but version 1 does not report it. Finding no violations is not evidence of compliance.

### Two data gaps found during design

Public registers do not record how much energy GB batteries hold: REPD records power only, and in SSEN's Embedded Capacity Register the storage-MWh field read "DATA NOT AVAILABLE" for every connected battery site. That is why the audit uses tests that need no capacity figure. Separately, NESO's reserve and response auction results do not identify BM units, so no battery's week can be certified free of contracts that lawfully lower its declarations. The audit therefore cannot call any unit's under-declaration provable in this version. What would close each gap is set out under *In plain terms*.

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

`src/model/` holds the input types shared by real and synthetic data, and `src/physics/` the §3 physics. `src/claims/` holds Claims 1, 2, 4 and 5 with their scoring; `src/claims/unit.py` scores one unit, real or synthetic, from its inputs to its Claims 1–2 results. `src/claim3/` holds Claim 3's scoring, kept for the record and for any later deviation; version 1 does not report it. `src/synthetic/` holds the known-answer batteries and their runners: the Claims 1–2 bands (`bands.py`), Claim 3's sizing regimes and bands (`regimes.py`, `claim3_bands.py`), the Claim 4 check and its diagnostics (`claim4_check.py`), and the Claim 5 report (`claim5_report.py`).

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
│   ├── claims/             Claims 1, 2, 4 and 5
│   ├── claim3/             Claim 3 scoring (kept; not reported in version 1)
│   └── synthetic/          known-answer batteries
├── notebooks/              exploration only; results come from src/
├── outputs/                figures, tables, known-answer results
└── docs/
    ├── results/            known-answer write-ups
    └── rules/              rules approved before the runs they govern
```

## Reproducing

*To follow.* Every published number will regenerate from `src/` against pinned data manifests.

## Licence

Code: [MIT](LICENSE). Text, figures and derived tables: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Source data remain under their own licences; see Data attribution.

## Data attribution

Contains BMRS data © Elexon Limited copyright and database right 2026. Used under Elexon's [licence to use BMRS open data](https://www.elexon.co.uk/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/).

Supported by National Energy SO Open Data. (NESO's licence requires this attribution statement word for word.) Used under the [NESO Open Data Licence v1.0](https://www.neso.energy/data-portal/neso-open-licence).

Neither Elexon nor NESO endorses this project. Scores, flags and estimates here are this project's derived results, not Elexon or NESO data.

## Citation

Cite the latest lock:

> Moran, A. (2026). *Can GB Battery Declarations Be Audited From Public Data?* Heaviside Analytics. https://doi.org/10.5281/zenodo.24473559 (tag `v1.0.5-lock`, commit 7b65082).

Every lock is archived on Zenodo:

| Tag | What it locked | Zenodo |
|---|---|---|
| `v1.0.5-lock` | Deviation 5: accepted-BOA add-back corrected | [zenodo.24473559](https://doi.org/10.5281/zenodo.24473559) |
| `v1.0.4-lock` | Deviation 4: Claim 4 release rule | [zenodo.24439749](https://doi.org/10.5281/zenodo.24439749) |
| `v1.0.3-lock` | Deviation 3: Claim 4 known-answer gate; version 1 as an auditability assessment | [zenodo.24439737](https://doi.org/10.5281/zenodo.24439737) |
| `v1.0.2-lock` | Deviation 2: Claim 1 reported by window length; Claim 2 reported as failing | [zenodo.24416574](https://doi.org/10.5281/zenodo.24416574) |
| `v1.0.1-lock` | Deviation 1: nested resampling of unit-score intervals | [zenodo.24354704](https://doi.org/10.5281/zenodo.24354704) |
| `v1.0-lock` | The pre-registration | [zenodo.24343931](https://doi.org/10.5281/zenodo.24343931) |

Citation metadata: [`CITATION.cff`](CITATION.cff). Its licence field names the code licence only, because Zenodo cannot read a list of licences from it; the text licence is stated above.

## AI use statement

*To write.*

## Author

Andy Moran — Heaviside Analytics
GitHub: [AndyMoran](https://github.com/AndyMoran)

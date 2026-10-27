# PROJECT — Dispatch Realisation of GB Batteries

*Artifacts, not a programme.*

Owner: Andy Moran (Heaviside Analytics)
Start: w/c 26 October 2026 · Horizon: ~12 weeks (to mid-January 2027)
Status: **Week 0 — scoping**

---

## 1. Objective

Produce a few finished, named, public artifacts, with minimal selling. The aim: people describe me as "the person who measures how well GB batteries are declared and dispatched, in £".

No service business. No siting engine. No LP counterfactual.

## 2. The decision test

Every artifact must change a decision someone with an asset makes. The levers an owner controls:

| Lever | Who decides | Addressed by |
|---|---|---|
| Declared capability (MEL/MIL, MDO/MDB) | Optimiser | **A** |
| Choice of optimiser (hire / fire / renegotiate) | Owner | **A** (published benchmark) |
| Bid/offer pricing | Optimiser | Out of scope (confounder in A) |
| Location of future sites | Developer / investor | B (supporting only) |

Everything else (control-room behaviour, constraint management, dispatch tooling) is NESO's, and is context, not product.

## 3. Philosophy and approach

### 3.1 Test and use tools before opinion

A question that a query, an API call, a primary document or a short script can settle gets settled that way before it is argued about.

- **Cheap check first.** If a check takes under an hour, run it before debating the answer. Example: whether MDO/MDB were public decided the shape of Workstream A, and one look at the P499 page answered it.
- **Opinions are hypotheses.** A view from me, a reviewer or an AI tool enters the plan either after a check or as a PROVISIONAL row in `ASSUMPTIONS.md`. Never as settled fact.
- **Feedback is checked, not adopted.** Each review point is tested against sources and the code before it changes a document. Points that fail the check are recorded with the reason.
- **Every factual claim is traceable.** It is either GROUNDED with a citation or labelled PROVISIONAL with the check that would settle it.
- **Prefer the measurement to the model.** Where data can show what happened, use it before reasoning about what should have happened.

### 3.2 Decide before looking

- Pre-register anything with a coefficient. Lock before outcome data is examined.
- Fallbacks are written down in order, with the condition that triggers each (§5A design hierarchy), before the data that decides between them is seen.
- Thresholds are filled in before gates are evaluated.
- Every decision goes in the decision log (§11) with its date and reason.

### 3.3 Physics before economics

Energy balance before acceptance rates. If a declaration can't be reconciled with what the battery physically did, no economic result built on it is trusted.

### 3.4 Measurement, not verdict

- Every published number carries its uncertainty and its limits.
- A null result is a valid result.
- Named parties see their results first and their replies are published (§7a).

### 3.5 One source of truth

- Each rule, definition or table lives in one file; others link to it rather than restate it. Copies drift.
- Code is the source of truth for every number; prose explains code. Published numbers regenerate from `src/` against pinned manifests.

### 3.6 Adversarial self-review

Own work is held to the same standard as external critique. That includes checking documents against their own rules: if two files disagree, or a file breaks a principle it states, that is a defect.

### 3.7 Small, finished, named

Every artifact has a user and a £ number. Outreach is 10–15 people, not a market.

### 3.8 Pipeline rules

All code follows `PIPELINE_RULES.md`: checks enforced in code, visible failure, excluded units kept and labelled, versioned formats, deterministic outputs.

### 3.9 Plain writing

All documentation follows `WRITING.md` (Strunk and White; Zinsser): point first, needless words cut, one idea per sentence, every claim specific and sourced.

## 4. Research questions

**RQ1 (feasibility).** Are MDO/MDB declarations published per BM unit, with enough adopters and history to measure declaration quality? *(MDO/MDB: confirmed public via BMRS since P499, 25 June 2026. FSoE: unconfirmed.)*

**RQ2 (descriptive).** How does declaration quality vary across the battery fleet, raw and after adjusting for duration, node, commissioning date and time since GC0166 adoption?

**RQ3 (stakes).** What is the declaration-attributable difference in accepted Balancing Mechanism volume, expressed in £/MW/yr? Identified from **within-unit** variation (switch date, end of NESO grace period, changes in redeclaration latency), not from cross-sectional comparison alone. Denominator, price and pay-as-bid caveat defined in `PREREGISTRATION.md` §4 before lock.

**RQ4 (context).** Where in the network, and in which system states, are battery skips most costly? (Measurement layer for RQ3; standalone output downgraded.)

## 5. Workstreams

### A — Declaration-quality benchmark (headline) · Weeks 1–8

**Why first.** GC0166 compliance deadline is 5 November 2026. Migration is staggered unit by unit, which gives within-unit before/after variation. Relevance is time-limited; the data is not (BMRS archives it).

**Data.** BMRS MDO, MDB, MELS, MILS, PN, BOAL/BOALF, BOD, B1610; BMRS BM unit reference data (lead party); NESO In-Merit All BM and PSA files; asset metadata (node, MW, MWh, commissioning date).

**Outcome (A does not wait for B).** Accepted Balancing Mechanism energy per registered MW, per unit per week, from BMRS data. Definition: `PREREGISTRATION.md` §3. NESO's accepted ÷ in-merit ratio is not used, because its denominator depends on the unit's own declarations (ASSUMPTIONS.md M1, refuted 23 Oct 2026). B adds the skip measurement and £ layer afterwards.

**Declaration-quality metrics (physics-first, no private data):**
1. *Conservation:* stability of declared export and import energy, plus PN-protected energy.
2. *Mass balance:* change in declared deliverable energy vs metered energy in and out, up to round-trip efficiency.
3. *Redeclaration latency:* time from BOA to updated MDO/MDB (NESO's reserve benchmark: within 1 minute).
4. *Conservatism:* declared deliverable energy vs energy reconstructed from metered output alone.

Formulas: `PREREGISTRATION.md` §3 (single source).

**Outputs.**
- Fleet-wide ranking by unit, **raw and adjusted**. Lead with adjusted. Units not scored are listed with the reason.
- Claims map: what each published number shows and doesn't show.
- Declaration-attributable £/MW/yr estimate as the lead number, with range.
- Methods paper (~3,000–5,000 words), one chart, open pipeline.
- Right of reply and naming policy: see §7a.

**Identification.**
- Cross-section → published ranking (descriptive, adjusted).
- Within-unit → £ estimate, using the design hierarchy below.
- Claim language: each design identifies an effect only under its stated assumptions. Pre-trends are reported. Adoption timing may be endogenous, though NESO schedules migrations with lead parties, which may limit self-selection.

**Design hierarchy (pre-specified fallbacks).**

The headline design is the first one, in this order, whose trigger is met. Triggers are evaluated at Gate A1 on **declaration data only** (MDO/MDB submissions and dates; no acceptances, skips or prices). The triggering statistics and the selected design are recorded in the decision log, with date, before the pre-registration locks. A reader can therefore verify the fallback was chosen before any outcome was seen.

| Order | Design | Trigger (all conditions must hold) | Identifying assumption | Estimator |
|---|---|---|---|---|
| 1 (primary) | **Staggered adoption** | ≥3 distinct adoption cohorts, each ≥ *N* units and each with a not-yet-treated comparison group; earliest of these cohorts ≥8 weeks of post-period. The last cohort has no comparison group: it is dropped from estimation and does not count towards the 3 | Parallel trends within cohort; no shock coinciding with any cohort's switch | Callaway–Sant'Anna or Sun–Abraham (not TWFE); event window *[−k, +k]* weeks |
| 2 | **Within-unit metric variation** (H3) | Design 1 trigger fails; ≥ *N* units with ≥ *M* weeks of MDO/MDB data; within-unit SD of at least one declaration metric above *[threshold]* | Time-varying confounders (e.g. pricing changes) uncorrelated with changes in declaration quality, conditional on unit and period FE | Unit + period fixed effects; SEs clustered by unit |
| 3 | **Grace-period dose-response** (H4) | Designs 1 and 2 fail; NESO has announced the grace-period end; it falls ≥ *k* weeks before the data cut-off; ≥ *N* reserve-contracted units with pre-shock MDO/MDB data | Units with different pre-shock declaration quality would have trended in parallel absent enforcement | DiD with pre-shock declaration quality as continuous intensity; reserve-contracted units only |
| — | **Design note only** | No trigger met | — | Descriptive ranking (H1) and preliminary evidence; no £ estimate |

Rules:
- Lower-ranked designs whose triggers are also met run as **pre-specified secondary analyses** and are reported in full, but never replace the headline. This blocks choosing the design with the most favourable result.
- A higher-ranked design whose trigger fails may run only as an **exploratory** analysis, and only if `PREREGISTRATION.md` specifies it before the lock. It is labelled exploratory wherever it appears, is reported whatever it shows, and never feeds the headline or the £ estimate.
- Thresholds (*N*, *M*, *k*, SD threshold) are filled in before Gate A1 is evaluated, not after. Their values live in `config/gate_a1.toml`, and the code refuses to run while any is blank.
- If a trigger statistic is borderline (within 10% of its threshold), the lower-ranked design is used.
- Optimiser-level claims only if the lead party → optimiser mapping is clean. Units that changed optimiser are the strongest variation; count them before promising anything.

**Gate A1 (end Wk 1), on declaration data only:**
- Evaluate the design hierarchy triggers in order; record the statistics and the selected design in the decision log.
- Denominator check: done 23 Oct 2026; outcome switched (M1, M7).
- Too few adopters for any design → design note + preliminary evidence.

**Pre-registration lock (start Wk 2):** after A1, before any outcome data is examined. Deposited on Zenodo with commit hash.

**Gate A2 (end Wk 2): stakes.** A crude estimate of what battery skips are worth, run after the lock so it cannot shape the specification. A2 decides how A ships, not whether it is built.

*Decision rule (v1, fixed before lock):*
- **Metric:** value of skipped battery volume per MW-year of registered capacity.
- **Data:** NESO In-Merit All BM and Post System Action monthly files, **October 2025 to September 2026** inclusive, Stage 6. If any of these months lacks Stage 6, Stage 5 is used for all twelve, and the report says so.
- **Fleet:** ASSUMPTIONS.md M10, mapped from Elexon to National Grid unit IDs through the pinned reference snapshot. Unmapped units are counted in the report.
- **Value:** skipped bid or offer volume × the margin in `PREREGISTRATION.md` §4. Price: the file's `average_price_per_MWh`, which NESO derives from BOD. MID: volume-weighted across providers with volume above zero, per half hour; half hours without MID are excluded and counted. The conservative margin uses the UK local day.
- **Denominator:** MW-years of exposure: each unit's GC × the share of the window it was present (first to last month in the files). A unit without GC in the pinned reference snapshot is left out of numerator and denominator, and counted in the report. Sensitivity: GC of units present in September 2026, for a full year.
- **Range:** low = Post-System-Action skips × the conservative daily margin; point = All-BM skips × the headline margin.
- **Low:** low end < £5,000/MW/yr → reputation project: no product packaging, no press push, light outreach.
- **High:** point > £10,000/MW/yr → product-grade: benchmark as lead artifact, targeted owner outreach, press.
- **Middle:** A proceeds unchanged; packaging decided at Gate B. This includes the case where the low end is below £5,000 and the point is above £10,000: the range is too wide to decide.
- **All branches:** right of reply and legal review per §7a.
- No re-specification after the number is seen. Code: `src/ingest/gate_a2.py`, settings `config/gate_a2.toml`. The code refuses to run until PREREGISTRATION.md is locked.

A2 is a stakes gate. It values skips against wholesale (§4 margin), not against the marginal accepted action, as Workstream B does (ASSUMPTIONS.md E3). Its number is not the B-layer estimate and is not quoted as one. Context only, not a gate: the A2 figure may be shown as a share of a stated, sourced revenue assumption.

### B — Skip measurement layer (supporting) · Weeks 3–10

Method behind the benchmark, not a standalone product. Modo already tracks per-battery skip rates; our edge is £-weighting and an open, auditable method.

**Method.** Accepted-volume share conditional on in-merit feasible offer, by node, duration, system state (short/long, price percentile, ramp, instruction density) and vintage. Tier A (raw), Tier B (NESO stage exclusions), Tier C (own SoC screen); lead with Tier B. £ layer: skipped volume × cost difference vs marginal accepted action.

**Gate B (Wk 6):** reproduce NESO's published aggregate skip rate within stated tolerance, or document the divergence.

**Output.** "The method behind the benchmark" paper + node map + pipeline.

### C — February skip-day post · Weeks 2–3

~600 words. One day, one method demonstration. Lead magnet. Not a paper; do not expand. Every number must regenerate from the pipeline.

### D — Methods note from the credit project · Weeks 1–3 (parallel, low effort)

~2,000 words, generalised away from credit: (1) Gaussian-path simulation overstates power when the sample has one dominant episode; (2) block-bootstrap intervals undercover. Reach and rigour, honestly labelled.

## 6. Timeline

| Wk | w/c | A: Benchmark | B: Measurement | C: Post | D: Note | E: Outreach |
|---|---|---|---|---|---|---|
| 1 | 26 Oct | Pull MDO/MDB; adoption dates and dispersion; denominator check; lead-party map. **Gate A1** | — | Draft | Draft | Build list |
| 2 | 2 Nov | **Lock pre-registration** (Zenodo); then crude stakes. **Gate A2**. 5 Nov deadline | — | Draft | Draft | — |
| 3 | 9 Nov | Metrics build | Data acquisition | Publish | Publish | First 5 (with C; method ask) |
| 4 | 16 Nov | Within-unit estimation (design chosen at A1) | Pipeline build | — | — | — |
| 5 | 23 Nov | Adjusted ranking; right of reply sent (≥10 working days) | Pipeline build | — | — | — |
| 6 | 30 Nov | Corrections; legal and licence check | **Gate B** | — | — | — |
| 7–8 | 7 Dec | Publish benchmark with replies attached; post-grace update if available | £ layer, node map | — | — | Second 5 (with A) |
| 9–10 | 21 Dec | — | Write-up | — | — | — |
| 11–12 | 4 Jan | — | Publish | — | — | Third 5 (with B) |

## 7. Outreach (E)

Rules: one narrow ask; offer before asking; email the first author, not the last; one follow-up after two weeks; expect silence.

- 4 operational: NESO dispatch/markets staff; BESS optimisation leads.
- **3 asset owners with multi-asset portfolios and more than one optimiser** — they hold the hire/fire/renegotiate decision.
- 3 commercial: consultancy analysts whose clients ask about skip rates.
- 2–3 academic: Gale (first author) and others working on GB flexibility.

Ask before A publishes (Wks 1–6): "I'm measuring declaration quality across the GB battery fleet and I'd value your reaction to the approach." After publication: "I've measured … and I'd value your reaction." Not a sale, not a job request.

## 7a. Publication policy for named units

- **Unit of publication:** BM Unit ID. Lead party shown for context only; lead party ≠ operator ≠ owner.
- **Right of reply:** each lead party receives its unit's numbers and the full method at least 10 working days before publication.
- **Errors:** a demonstrated data or method error is fixed before publication. If the fix changes results materially, the reply clock restarts. I adjudicate; every correction is logged publicly with its reason.
- **Disputes that aren't errors:** publish with the lead party's reply attached. Do not withhold.
- **Before publishing:** legal review of naming and framing. The BMRS and NESO licences permit a per-unit derived table (ASSUMPTIONS.md R10), but they grant copyright and database rights only; they do not clear naming units.

## 8. Out of scope

- **Cut:** LP merit-order counterfactual. It is the weakest link, and the simpler valuation (ASSUMPTIONS.md E3) is enough.
- **Cut:** Siting/sizing engine. It is reflexive and leads to a service business.
- **Cut:** Behavioural/cognitive modelling of the control room. Acceptances can't identify it.
- **Deferred:** Per-asset audit product. The published ranking does this job. Revisit if inbound requests ask for it.
- **Cut:** Bid/offer pricing optimisation. It is the optimiser's job, not the measurer's.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Too few GC0166 adopters / short histories | Gate A1; design note + preliminary evidence |
| Ranking reflects hardware/location, not practice | Adjusted ranking leads; controls for duration, node, vintage, time since adoption |
| Declaration quality proxies for overall optimiser skill | £ estimate from within-unit variation only |
| Lead party ≠ optimiser | Publish by unit; optimiser claims only where mapping is clean |
| Named parties dispute results | Right of reply; uncertainty and limits stated up front |
| Gale anchor wrong or misapplied | Checked 23 Oct 2026: the figure is from a simulation with a different skip-rate definition. Used for order-of-magnitude comparison only (E1, E2a) |
| BOD / NESO file vintages | Record download dates and hashes; NESO reissued datasets Nov 2025 |
| Switch dates compressed near the deadline | Gate A1 dispersion test; designs 2 and 3 pre-specified |
| Outcome denominator depends on the unit's own declarations | Realised (M1). Outcome now per registered MW (GC), a seasonal registration value (M7, M8) |
| A's outcome depends on B | A's outcome comes from BMRS directly; £ layer from B later |
| Grace period ends late or is extended | Design 3 dropped; check NESO's stated date in Wk 1 |
| Naming parties: legal or reputational | §7a policy; legal review before publication |
| Licence for a per-unit derived table | Checked 23 Oct 2026: permitted with attribution (R10) |
| Practice converges quickly | Publish fast; this is an artifact, not a business |

## 10. Definition of done

- Published declaration-quality benchmark (raw + adjusted) with a £/MW/yr estimate and range.
- Published measurement-method paper with open pipeline.
- Published skip-day post and methods note.
- 10–15 people have seen the work and some have replied.

## 11. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-10-22 | A promoted to headline; B downgraded to measurement layer | Decision test: only declarations are an owner-controlled lever |
| 2026-10-22 | Publish ranking openly rather than sell per-asset audit | Resolves sales-burden tension; artifact does the selling |
| 2026-10-22 | Adjusted ranking leads; raw shown alongside | Raw ranking mostly ranks hardware and location |
| 2026-10-22 | £ estimate from within-unit variation | Cross-sectional link bundles declaration with pricing skill |
| 2026-10-22 | Stakes gate at end Wk 2 using NESO unit-level files | Own pipeline not ready until Wk 6 |
| 2026-10-22 | Within-unit design chosen at Gate A1; two fallbacks pre-specified | Mandatory deadline may compress adoption dates |
| 2026-10-22 | Pre-registration locks before Gate A2 | A2 touches outcome data |
| 2026-10-22 | Named-unit publication policy (§7a); benchmark moves to Wks 7–8 | 10 working days' reply plus corrections |
| 2026-10-22 | Design hierarchy written as ordered fallbacks with explicit triggers; lower designs run as secondary only | Fallback choice provably made before outcomes are seen |
| 2026-10-23 | A's outcome switched from NESO accepted ÷ in-merit volume to accepted BM energy per registered MW | M1 refuted: NESO in-merit volume uses the unit's own MEL/MIL, and GC0166 parameters from 25 Jun 2026, so the denominator changes at the treatment date |
| 2026-10-23 | Adoption date = first non-default MDO/MDB submission, dated by delivery time | NESO publishes ±9999 defaults for units not yet switched (M4a, R13) |
| 2026-10-23 | Design-1 trigger: last cohort dropped from estimation and not counted towards the 3-cohort minimum | Under a mandatory deadline the last cohort has no not-yet-treated comparison group |
| 2026-10-23 | Gate A1 thresholds fixed at commit 85aac7d: N = 5 per cohort; design 2 ≥ 10 units, ≥ 8 weeks, CV ≥ 0.05; k = 4; cut-off 29 Oct 2026 | Set before any declaration data was pulled (§3.2) |
| 2026-10-23 | Gate A1 runs on 30 Oct with the 29 Oct cut-off, not earlier | Late adopters before 5 Nov form the cohorts design 1 depends on |
| 2026-10-23 | Python environment managed with uv; versions pinned in uv.lock; CI runs tests on every push | Deterministic by construction (PIPELINE_RULES §8, §12) |
| 2026-10-23 | Repository public at github.com/AndyMoran/dispatch-realisation from Week 1 | Public commit history timestamps decisions made before outcome data is seen |
| 2026-10-23 | Registered MW = Generation Capacity (GC) from a pinned BMRS reference snapshot | GC is a seasonal registration value, not an operational declaration (M8) |
| 2026-10-23 | Battery fleet: non-default MDO/MDB submitters, excluding pumped storage and hydro; Gate A1 code updated before the run | BMRS reference data has no battery fuel type; PS units can also submit MDO/MDB (M10) |
| 2026-10-23 | Outcome stays BOALF − PN; Elexon BOAV is a post-lock cross-check | Settlement data revises and lags; the outcome must not depend on the comparison (R15) |
| 2026-10-23 | Optimiser-level claims only if grade-A evidence covers ≥ 50% of scored fleet MW | Lead party is not evidence of the optimiser (I4); method in docs/week1/i4_optimiser_map_method.md |
| 2026-10-23 | Design 1 estimator: Callaway–Sant'Anna, not-yet-treated controls, window −4 to +8 weeks | Matches §5A's comparison group; +8 matches the post-period trigger |
| 2026-10-23 | 95% intervals clustered by unit; Holm–Bonferroni across the four metrics | Four uncorrected metrics invite one false positive in four |
| 2026-10-23 | Outcome window 25 May – 15 Nov 2026; ranking needs ≥ 4 weeks of declarations; learning period 2 weeks | 4 pre-weeks for the earliest cohort; window ends before estimation |
| 2026-10-23 | Margin: BM premium over same-period MID; day's best-alternative MID as sensitivity | Standard headline, with a conservative check on battery opportunity cost (E5) |
| 2026-10-23 | Gale et al. (2026) used for comparison only, not to convert effects to £ | Its skip rate is simulated blocked time, not NESO's rate or this outcome; data end June 2023 (E1, E2a) |
| 2026-10-23 | Gate A2 keeps £5k/£10k, not share of revenue | Low threshold carries the decision; no checkable public revenue base; a vendor base adds attack surface; lowering now would look like tuning |
| 2026-10-23 | A2 compares the scenario low end with £5k and the point estimate with £10k; middle zone defers packaging to Gate B | Replaces "plausibly" with named statistics |
| 2026-10-23 | A2 window Oct 2025 – Sep 2026 at Stage 6, with a Stage 5 fallback for all months if any lacks Stage 6 | A dated window cannot drift; a named stage cannot be redefined (R16) |
| 2026-10-23 | A2 denominator: MW-years of exposure from GC | The fleet grew in the window; start, end and simple averages give different answers (M11) |
| 2026-10-23 | A2 uses the §4 margin and is not the Workstream B estimate; right of reply and legal review apply in every A2 branch | Keeps the gate cheap and the numbers unconfusable (E6); naming risk does not scale with £ stakes (§7a) |
| 2026-10-23 | Licence: MIT for code; CC BY 4.0 for text and figures | Standard pairing; CC BY matches the NESO licence's stated compatibility |
| *[Gate A1 date]* | *Selected design: [ ]. Trigger statistics: cohorts [ ], units per cohort [ ], earliest post-period [ ] wks, …* | *Recorded before pre-registration lock* |

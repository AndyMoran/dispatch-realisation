# PROJECT — Dispatch Realisation of GB Batteries

*Artifacts, not a programme.*

Owner: Andy Moran (Heaviside Analytics)
Start: w/c 26 October 2026 · Horizon: ~12 weeks (to mid-January 2027)
Status: **Week 1 — pre-registration redrafted (version 2, 30 Oct 2026)**

---

## 1. Objective

Produce a few finished, public artifacts, with minimal selling. The aim: people describe me as "the person who checks whether GB batteries' declarations are physically true".

No service business. No siting engine. No LP counterfactual.

## 2. The user and the decision

The audit is for anyone who relies on a battery's MDO/MDB and cannot check it: an owner checking its optimiser's declarations, a lender or investor assessing an asset, and NESO, whose control room sizes instructions from them. The decision it informs is whether a unit's declarations can be trusted, and where they fail.

| Question a user asks | Answered by |
|---|---|
| Do this unit's declarations move with its meter? | Claim 1 |
| Does it declare less energy than it provably holds? | Claim 2 |
| Does it fail to deliver energy it declared? | Claim 3 |
| Does it declare more than its tank can hold? | Claim 4, where a nameplate is disclosed |
| How fast do units redeclare after an instruction? | Claim 5, fleet level |

Whether better declarations earn more is a different question, deferred to version 2 (§8). Control-room behaviour, constraint management and dispatch tooling are NESO's, and are context, not product.

## 3. Philosophy and approach

### 3.1 Test and use tools before opinion

A question that a query, an API call, a primary document or a short script can settle gets settled that way before it is argued about.

- **Cheap check first.** If a check takes under an hour, run it before debating the answer. Example: whether MDO/MDB were public decided the shape of Workstream A, and one look at the P499 page answered it.
- **Opinions are hypotheses.** A view from me, a reviewer or an AI tool enters the plan either after a check or as a PROVISIONAL row in `ASSUMPTIONS.md`. Never as settled fact.
- **Feedback is checked, not adopted.** Each review point is tested against sources and the code before it changes a document. Points that fail the check are recorded with the reason.
- **Every factual claim is traceable.** It is either GROUNDED with a citation or labelled PROVISIONAL with the check that would settle it.
- **Prefer the measurement to the model.** Where data can show what happened, use it before reasoning about what should have happened.

### 3.2 Decide before looking

- Pre-register every claim. Lock before any unit is scored.
- Fallbacks are written down in order, with the condition that triggers each, before the data that decides between them is seen.
- Thresholds are filled in before gates are evaluated.
- Every decision goes in the decision log (§11) with its date and reason.

### 3.3 Physics before economics

Energy balance before acceptance rates. If a declaration can't be reconciled with what the battery physically did, no economic result built on it is trusted.

### 3.4 Measurement, not verdict

- Every published number carries its uncertainty and its limits.
- A null result is a valid result.
- Lead parties see their own units' results privately; no unit is named in version 1 (§7a).

### 3.5 One source of truth

- Each rule, definition or table lives in one file; others link to it rather than restate it. Copies drift.
- Code is the source of truth for every number; prose explains code. Published numbers regenerate from `src/` against pinned manifests.

### 3.6 Adversarial self-review

Own work is held to the same standard as external critique. That includes checking documents against their own rules: if two files disagree, or a file breaks a principle it states, that is a defect.

### 3.7 Small, finished, named

Every artifact has a user and a decision it informs. Outreach is 10–15 people, not a market.

### 3.8 Pipeline rules

All code follows `PIPELINE_RULES.md`: checks enforced in code, visible failure, excluded units kept and labelled, versioned formats, deterministic outputs.

### 3.9 Plain writing

All documentation follows `WRITING.md` (Strunk and White; Zinsser): point first, needless words cut, one idea per sentence, every claim specific and sourced.

## 4. Research questions

**RQ1 (feasibility).** Are MDO/MDB declarations published per BM unit, with enough adopters and history to audit? *Answered: yes. 163 units adopted by 29 Oct 2026; 98 have at least 4 scored weeks by 15 Nov (Gate A1, lock counts).*

**RQ2 (primary).** Are battery units' MDO/MDB declarations consistent with their own metered physics? Answered by Claims 1 and 2, which need no usable-energy figure, for every scored unit. Definitions: `PREREGISTRATION.md` (single source).

**RQ3 (secondary).** Do units fail to deliver energy within their declared MDO, indicating over-declaration? Claim 3, with its identification rate reported as a result in its own right; Claim 4 validates it where a nameplate is disclosed.

**RQ4 (data quality).** Do public registers record how much energy GB batteries hold? *Answered: no. REPD records MW only; SSEN's register shows "DATA NOT AVAILABLE" for all 28 connected battery sites; the Capacity Market register gives minimum durations only (ASSUMPTIONS.md P4a, R21, R22).*

## 5. Workstreams

### A — Physics audit of MDO/MDB declarations (primary) · Weeks 1–8

**Why now.** GC0166 compliance was due by 5 November 2026, and the control room now sizes instructions from MDO/MDB. Relevance is time-limited; the data is not, because BMRS archives it.

**Data.** BMRS MDO, MDB, PN, B1610, BOALF and reference data; Elexon BOAV for validation; disclosed nameplate MWh for the case series. Details: `PREREGISTRATION.md` §2.

**Claims.** Five, in three tiers: Claims 1–2 primary, Claim 3 secondary, Claim 4 an illustrative case series, Claim 5 descriptive. Definitions, screens, known-answer tests and the Claim 3 promotion rule: `PREREGISTRATION.md` (single source).

**Outputs.**
- Fleet-level results for every claim, with a sensitivity table. Units not scored are counted with the reason; secondary units are shown separately.
- A private pack per lead party: its units' flags with intervals, sorted but not ranked, and the method (§7a).
- Known-answer and reliability results, so readers can see the tests measure what they claim.
- Claim 3's identification rate and diagnostics.
- The data-quality finding (RQ4).
- Claims map: what each published number shows and doesn't show.
- Methods paper (~3,000–5,000 words), one chart, open pipeline.
- Disclosure and naming policy: see §7a.

**Gates.**
- **Pre-registration lock:** before any unit is scored. Tagged `v1.0-lock`; Zenodo DOI.
- **Known-answer gate:** the synthetic suite passes before any real unit is scored. If Claim 3's bands fail, Claim 3 is dropped from version 1.
- **Reliability gate:** a claim whose split-half reliability lies wholly below 0.5 is not reported per unit, privately or publicly.

**History, kept for the record.** Version 1 (to 30 Oct 2026) aimed to rank units and estimate, in £/MW/yr, whether declaring well pays. Gate A1 (official run, 30 Oct 2026) selected design 2 for that estimate; Gate A2 was to measure stakes. Both belong to the deferred analysis, and neither shapes the audit. Their code and outputs stay in the repository: `src/ingest/gate_a1.py`, `src/ingest/gate_a2.py`, `outputs/gate_a1/`. The decision log (§11) records each step.

### B — Skip measurement layer · deferred to version 2

Supported the deferred £ analysis. Revisit with version 2.

### C — February skip-day post · Weeks 2–3

~600 words. One day, one method demonstration. Lead magnet. Not a paper; do not expand. Every number must regenerate from the pipeline.

### D — Methods note from the credit project · Weeks 1–3 (parallel, low effort)

~2,000 words, generalised away from credit: (1) Gaussian-path simulation overstates power when the sample has one dominant episode; (2) block-bootstrap intervals undercover. Reach and rigour, honestly labelled.

## 6. Timeline

| Wk | w/c | A: Audit | C: Post | D: Note | E: Outreach |
|---|---|---|---|---|---|
| 1 | 26 Oct | Gate A1; lock counts; U-source search; scope narrowed; pre-registration redrafted | Draft | Draft | Build list |
| 2 | 2 Nov | Lock pre-registration (Zenodo); synthetic suite and scoring code. 5 Nov compliance deadline | Draft | Draft | — |
| 3 | 9 Nov | Known-answer gate; data pull (PN, B1610, BOALF); case-series search (2 days) | Publish | Publish | First 5 (with C; method ask) |
| 4 | 16 Nov | Pinned scoring run (window closes 15 Nov); reliability gate | — | — | — |
| 5 | 23 Nov | Fleet results; private packs sent to lead parties (≥ 10 working days before fleet publication) | — | — | — |
| 6 | 30 Nov | Corrections from lead-party responses | — | — | — |
| 7–8 | 7 Dec | Publish audit (fleet level), methods paper and pipeline | — | — | Second 5 (with A) |

## 7. Outreach (E)

Rules: one narrow ask; offer before asking; email the first author, not the last; one follow-up after two weeks; expect silence.

- 4 operational: NESO dispatch/markets staff; BESS optimisation leads.
- **3 asset owners with multi-asset portfolios**, who rely on their optimisers' declarations.
- 3 commercial: consultancy analysts whose clients ask about skip rates.
- 2–3 academic: Gale (first author) and others working on GB flexibility.

Ask before A publishes (Wks 1–6): "I'm auditing GB battery MDO/MDB declarations against metered physics and I'd value your reaction to the approach." After publication: "I've measured … and I'd value your reaction." Not a sale, not a job request.

## 7a. Disclosure policy for per-unit results

**Version 1: private.** Per-unit results go only to the lead party, for its own units. Fleet-level results and the method are published. Reasons:
- The claims establish physical coherence, not misconduct. Attached to a named company they read as the latter, and a published reply does not undo that.
- M13 is unresolved and sits under the primary claims. A private disclosure on a branch that later moves can be corrected; a public one cannot.
- The provisional physics (*H*, η̂ bounds, settlement-period resolution) is harmless at fleet level and contestable per named unit.
- The owner gets the same diagnostic privately. Naming adds audience, not analysis.

**Private packs:** BM Unit ID; flags, Claim 1 score and interval, lower-wall status, Claim 3 results where identified, latency; the full method. Sent at least 10 working days before fleet publication. Lead party ≠ operator ≠ owner.

**Errors:** a demonstrated data or method error is fixed before fleet publication. If the fix changes fleet results materially, the clock restarts. I adjudicate; every correction is logged publicly with its reason, without naming the unit.

**Version 2: named, only if all five hold** (PREREGISTRATION §11): (i) M13 resolved in writing; (ii) one clean pinned scoring run with no estimator changes; (iii) Claim 3's promotion outcome recorded; (iv) right of reply completed for every named unit, at least 10 working days; (v) legal review cleared. Disputes that aren't errors are then published with the reply attached.

**Licences:** the BMRS and NESO licences permit a per-unit derived table (ASSUMPTIONS.md R10), but they grant copyright and database rights only; they do not clear naming units

## 8. Out of scope

- **Deferred to version 2:** the £ association (old H3) and £/MW/yr estimate; the staggered event study (old H2); the adjusted ranking and composite score; the grace-period analysis (old H4); Gate A2; Workstream B; optimiser-level claims. Reasons: `PREREGISTRATION.md` §1. Version 2 would need an identification strategy for the £ question and usable-energy figures for the ranking.
- **Cut:** LP merit-order counterfactual. It is the weakest link.
- **Cut:** Siting/sizing engine. It is reflexive and leads to a service business.
- **Cut:** Behavioural/cognitive modelling of the control room. Acceptances can't identify it.
- **Cut:** Bid/offer pricing optimisation. It is the optimiser's job, not the measurer's.

## 9. Risks

| Risk | Mitigation |
|---|---|
| MDO is stored, not metered, energy (M13) | Every flag computed under both readings; published only if robust to both |
| Protection horizon *H* wrong (M15) | Every flag computed at *H* = SP + 3 and 6 hours; published only if robust to both |
| Half-hourly metering against per-minute declarations | Claim 1 at settlement-period boundaries; Claim 3 on single-BOA periods only |
| Claim 3 has little power (few near-empty instructions) | Identification rate reported as a result; known-answer gate; Claim 3 secondary, with a promotion rule |
| Claim 3 fires on frequency response or ramp limits | Per-unit baseline; U-free placebo set; ramp-limited synthetic battery |
| Secondary units are portfolios | Reported separately, marked "may be aggregated" |
| Tests don't measure what they claim | Known-answer suite with fixed bands; reliability gate |
| Lead parties dispute private results | Error-correction process before fleet publication; uncertainty and limits stated up front |
| Naming units in version 2: legal or reputational | Five written conditions (§7a), including M13 resolved and legal review; claim limited to physical consistency |
| Honest units fall short near empty (power derating) | Synthetic derating battery must not be flagged; placebo set (P6) |
| BOD / NESO / B1610 vintages | Record download dates and hashes; one pinned scoring run |
| Practice converges quickly | Publish fast; this is an artifact, not a business |

## 10. Definition of done

- Published audit: fleet-level results with sensitivity, known-answer and reliability results, and the data-quality finding.
- Private packs sent to every lead party with a scored unit.
- Published methods paper with open pipeline.
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
| 2026-10-27 | No ML reconstruction of state of charge; physics bounds ("tank walls") instead. No skip-prediction model | A reconstruction learned from declarations cannot test them; NESO skips depend on declarations by construction (M1) |
| 2026-10-27 | Primary adoption stays first non-default submission; dynamic onset added as H2 sensitivity and static-start count at commit 9f0ca5e, before the official Gate A1 run | Static declarers are treated by NESO; they are poor declarers (H3), not untreated units |
| 2026-10-27 | Metric formulas fixed in PREREGISTRATION §3; conservation measured as stability | MDO is net of protected volumes (M12); unobserved reserve protection biases a level comparison |
| 2026-10-27 | Gate A1 was run early on incomplete data (27–29 Oct missing) and recorded as a preview; guard added so it cannot run before the cut-off ends. No thresholds or rules changed | The code did not check that the cut-off had passed |
| 2026-10-27 | H2 staggered event study pre-specified as exploratory; general rule for failed higher-ranked designs | Design 1 missed its trigger narrowly, but 7 usable cohorts exist; specifying before lock lets H2 be reported without becoming a choice made after outcomes |
| 2026-10-28 | The declaration-quality standard is the primary contribution; RQ3 becomes an association, labelled secondary if its MDE is at most £5,000/MW/yr, otherwise exploratory | The standard needs no causal identification and is what an owner can act on; within-unit variation cannot exclude changes over time |
| 2026-10-28 | RQ3 outcomes: volume primary, BM premium secondary, read jointly; lead estimate on mass balance per 10-point reduction, with a degeneracy rule that can reject but not select a metric | Premium adds the unit's own pricing changes to the outcome; most units and least attenuation |
| 2026-10-28 | RQ3 interpreted as the association of coherence with acceptances, net of each unit's level; weekly-Q control on units with U as robustness | Mass balance cannot see over-declaration; unit FE absorb a constant level |
| 2026-10-28 | Lead ranking by mass balance with a level gate (median Q > 1.05 or > 10% below the lower wall bars the top quartile); per-unit intervals from resampling each unit's days | Mass balance cannot see constant level errors; ranks within noise must not be presented as different |
| 2026-10-28 | Reliability by split-half days, metric excluded only if its interval lies wholly below 0.5; known-answer tests with fixed bands, revisable only before the first real unit is scored, each revision certified clean | Adjacent settlement periods inflate agreement; tests must be able to fail; metric code is written after lock |
| 2026-10-28 | H3 sample ≥ 4 scored weeks, ≥ 8 as robustness; MDE by placebo time-shifts after lock, before any coefficient; wild cluster bootstrap; confound table with primary, robustness and residual columns | Maximises units; precision depends on within-unit variation; too few units for conventional clustered errors |
| 2026-10-30 | **Gate A1 (official): design 2 selected.** Design 1 not triggered (earliest estimable cohort W36: 8.4 post-weeks vs 8.8). Design 2: 13 units with ≥ 8.8 weeks vs 11; median CV 0.414 vs 0.055. Design 3: grace-period end not announced. 163 units adopted. Config SHA-256 ed7dcdc1… (commit 9f0ca5e); report and coverage committed with this row | Recorded before the pre-registration lock; matches the 27 Oct preview apart from 31 late adopters |
| 2026-10-30 | A scored week is a complete ISO week after the unit's adoption week | The adoption week holds declarations for only part of the week; needed to apply the ≥ 4 and ≥ 8 week rules |
| 2026-10-30 | Registered MW: GC if positive, else \|DC\|, else maximum MEL over the window; one constant per unit; robustness on GC-only units. H3 primary sample 98 units (75 with GC only) | GC = 0 for 33 of 163 adopted units, 25 of them secondary units; a constant denominator cannot change at the treatment date (M1, M16) |
| 2026-10-30 | Secondary BM units scored if metered, ranked only if physics-consistent, reported as a separate group; robustness H3 without them | They may be aggregated portfolios; B1610 covers all 31 (R19) |
| 2026-10-30 | B1610 from the latest settlement run available at the scoring run, run type recorded per period | Elexon serves several settlement runs; the run must be fixed before results (M6) |
| 2026-10-30 | **Scope narrowed to a physics audit (version 2 of the pre-registration).** Claims 1–2 primary, Claim 3 secondary, Claim 4 case series, Claim 5 fleet-level descriptive. Output is a flag table, not a ranking | No outcome design identifies a declaration effect on revenue with this fleet and window; physical consistency is answerable from public data for every unit |
| 2026-10-30 | Deferred to version 2: £ association and £/MW/yr (old H3), event study (old H2), adjusted ranking and composite, grace-period analysis (old H4), Gate A2, Workstream B, optimiser claims | Each needs an identification strategy or usable-MWh figures this version lacks (PREREGISTRATION §1) |
| 2026-10-30 | Usable MWh is unavailable for most units; overstatement against capacity is a case series only (Claim 4) | REPD has MW only; CM register gives minimum durations without unit IDs; SSEN ECR has no MWh for 28 of 28 connected battery sites (P4a, R21, R22) |
| 2026-10-30 | Claim 3 (non-delivery) specified: two models with a conjunction rule, frequency-response baseline, U-free placebo, identification rate, r > 1 classified against latency, separate scoring module, written promotion rule | Gives U-free over-declaration detection; the promotion rule stops significance alone from promoting it (M19, M20, I16) |
| 2026-10-30 | Known-answer suite of 9 synthetic batteries, with fixed bands, must pass before any real unit is scored; bands may be revised only before then | Tests must be shown to measure what they claim before they touch real units |
| 2026-10-30 | Lock moves from "before outcome data" to "before any unit is scored". One pinned scoring run; any estimator change needs a new lock | No outcome variable remains in version 1; scoring is the step that must not inform the method |
| 2026-10-30 | **Claim 3 build decided by a pre-lock power bound, rule fixed before first run** (`src/ingest/power_bound.py`). A unit is potentially identifiable if ≥ 10% of its declaration-minutes after its adoption week (latest submission per minute, defaults excluded) satisfy 1 MWh ≤ MDO ≤ 2 × MW × 60 min. Build Claim 3 in version 1 if ≥ 30 of the 98 scored units are potentially identifiable; otherwise keep its specification, unbuilt, for version 2. MW per M16 (GC, else \|DC\|, marked indicative); units with neither count as not identifiable. T = 30/90, r ≈ 1, 5%/20% shares, MDB and the 98/73 split by unit type are reported, not deciding; if the result passes only because of secondary units, that is recorded here | Decides effort, not validity: Claim 3 stays secondary in either branch and its promotion rule is unchanged. The bound is a necessary condition; the identified set will be no larger than the potential set |
| 2026-10-30 | **Power bound run (rule committed in f25f43a before the run): Claim 3 built in version 1.** 71 of 98 eligible units potentially identifiable (threshold 30); 67 of 73 non-secondary. Not dependent on secondary units: 21 of 25 have no MW and count as not identifiable. Result nearly flat across T = 30–90 and K = 1–2, so it rules out thinness by construction only. 3 eligible units have no non-default declarations after their adoption week | Pre-registered rule met. Decides effort only: Claim 3 stays secondary under its promotion rule (R26; `outputs/lock/power_bound.json`) |
| 2026-10-30 | **Per-unit results private in version 1; named only in version 2, once five conditions hold:** M13 resolved in writing; a clean pinned run with no estimator changes; Claim 3's promotion outcome recorded; right of reply completed; legal review cleared. Legal review drops out of version 1 | The claims prove coherence, not misconduct; M13 is unresolved under the primary claims; owners get the same diagnostic privately; version 1 should be unattackable on process (§7a) |
| 2026-10-30 | Framed as testing one hypothesis for battery skips, declaration quality, which NESO's root-cause review could not test because MDO/MDB were unpublished when it concluded. Coverage stated per channel; over-declaration named as the weakest-tested; prevalence, not association with skips | Places the audit on NESO's own list of causes and states what it settles and leaves open (R23) |
| 2026-10-30 | No carbon or £ figure anywhere in version 1, including the motivation | An unverified figure is a lock risk; any figure would need the counterfactual cut in §8 |
| 2026-10-30 | Synthetic battery #10 (honest, derates at low charge) added; §5 states that all scored instructions fall under GC0166 | Derating mimics over-declaration (P6); the 15- and 30-minute rules never govern scored data (R25) |

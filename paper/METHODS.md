# Can GB Battery Declarations Be Audited From Public Data?

*Partly. A preregistered test of what public balancing data can verify, and the two gaps that stop the rest.*

Andy Moran, Heaviside Analytics. Draft 3, 25 November 2026: sections 1–4 and 7. Sections 5, 6, 8 and 9 follow.

For: an analyst at NESO, Ofgem or a battery owner who was not part of this project. It sets out what can be checked, how the checks were tested, and what would close the gaps.

Sources: the method is fixed in [`PREREGISTRATION.md`](../PREREGISTRATION.md), locked as `v1.0-lock` ([10.5281/zenodo.24343931](https://doi.org/10.5281/zenodo.24343931)). It was changed nine times, each change locked before the run it governed; the latest lock is `v1.0.7-lock` ([10.5281/zenodo.24484015](https://doi.org/10.5281/zenodo.24484015)). Every decision and its reason is in [`PROJECT.md`](../PROJECT.md) §11. Every assumption and its evidence is in [`ASSUMPTIONS.md`](../ASSUMPTIONS.md), cited here by ID, such as P11.

---

## 1. Summary

**The question.** GB's Balancing Mechanism is the market in which NESO, the system operator, buys last-minute changes in output. Since Grid Code modification GC0166, batteries and other units that can run only for a limited time declare how much energy they can deliver and absorb. The two figures are Maximum Delivery Offer (MDO) and Maximum Delivery Bid (MDB). NESO sizes its instructions from them, and Elexon publishes them for each unit. Batteries began submitting on 25 June 2026, one unit at a time, and all were due to comply by 5 November 2026 (R3). We studied the 162 battery units that had started by 29 October. Can anyone outside NESO check their declarations from public data?

**The answer: partly.** Each battery's settlement meter records every MWh it exports and imports. From the meter alone, we can rebuild how much energy the battery could deliver at each moment, up to an unknown starting level. We can then test whether its declarations moved as the meter says they should. Two gaps stop a complete audit:

1. **We found no public register that records how much energy each battery holds.** REPD, the government's planning database for renewable and storage projects, records power only. SSEN's Embedded Capacity Register has a storage-MWh field, but it is empty for all 28 battery sites. The Capacity Market register gives minimum durations, without unit IDs (P4a, R21, R22).
2. **NESO's reserve and response auction results do not say which unit holds each contract.** These contracts lawfully lower a battery's declarations. Without the link, no unit's week can be shown to be free of them. None of the 98 eligible units had such a week (R27).

**What we did.** We fixed five checks in advance. We then tested each on simulated batteries whose true behaviour we knew: some honest, some with a planted fault. A check that could not tell them apart was not used on real units.

**What the tests showed.** No check can support a finding that a particular unit over- or under-declares:

- **Claim 1, mass balance,** separates honest from faulty batteries cleanly. But one preregistered test failed at every window length, so no unit gets a verdict.
- **Claim 2, the lower wall,** wrongly flags 17–20 honest batteries in 100 over four weeks. The cause is the battery's efficiency, which has to be estimated from the same meter.
- **Claim 3, non-delivery,** estimated planted over-declaration well. Its control failed, so it was dropped.
- **Claim 4, the upper wall,** was crossed by honest batteries in most runs, so it was not used on real units.
- **Claim 5, response time,** can be measured only as an upper bound, and cannot tell a response from a routine update.

The estimated efficiency lies behind three of these limits. That is a gap in the data, not in the physics.

**What would close the gaps.** Two things published, and one shared under control (section 7): a register of storage energy for each unit; auction results that can be joined to units; and controlled access to efficiencies and committed energy, which public data cannot show.

**What this paper does not do.** It names no unit and makes no finding about any company. It reports results for the fleet as a whole (section 5). Each company receives its own units' results privately.

## 2. What MDO and MDB are, and what public data shows

### 2.1 A tank with a pipe

A battery is a tank with a pipe. The pipe sets how fast energy can move: power, in MW. The tank sets how much can move before it is full or empty: energy, in MWh. Before 2026 the control room saw only the pipe. It had to guess the tank, so to be safe it limited batteries to short instructions: 15 minutes, then 30 minutes from March 2024 (R25).

GC0166 shows the control room the tank. Each unit now declares two figures (R1):

- **MDO:** the most energy NESO may take from it through offers, at that minute.
- **MDB:** the most energy NESO may put into it through bids, at that minute.

Both are amounts of energy, not rates: "the instantaneous energy volume available at a given minute" (M17). Both leave out energy the unit has already committed. That includes its own schedule (its Physical Notification, or PN), instructions already accepted, and reserve and response contracts (M12). NESO keeps its instructions within them (M18). Since 25 June 2026, under rule change P499, Elexon has published them for each unit on its public data service, BMRS (R2, R6).

MDO and MDB are therefore limits declared for dispatch, not measurements of the tank. But a limit must be physically possible: a unit cannot honestly offer energy it does not hold. The meter records what went through the pipe. The question is whether the declared limits fit that record.

### 2.2 What is published, and what is not

| Published for each unit | What it gives us |
|---|---|
| MDO and MDB, each with its publish time | The declarations under test |
| B1610: metered energy, one net figure per half-hour | What went in and out |
| PN: the unit's own schedule | Energy the declaration should set aside |
| BOALF: each accepted instruction, with its time | Energy NESO took, and when |

| Not published for each unit | Why it matters |
|---|---|
| Storage capacity in MWh | No declaration can be checked against the size of the tank (P4a). Published capacities are for sites. A secondary unit, registered by a third party, may group several sites, which join and leave over time |
| Which reserve and response contracts a unit holds | Contracts lawfully lower MDO; unseen, they look like errors (R27) |
| Round-trip efficiency | Must be estimated from the meter; the estimate's error moves every wall (P11) |
| Export and import separately within a half-hour | The meter gives only the net, so flow both ways within a period is hidden (P7) |

### 2.3 Tank walls

The meter gives no starting level, but it gives every change. Export 10 MWh and the unit can deliver 10 MWh less. Import 10 MWh and it can deliver about 8.8 MWh more, if its round-trip efficiency is 88%. Add up the changes through a week and you have the path of deliverable energy, shifted by an unknown constant.

That path sets a floor. A tank never falls below empty, so at its lowest point the path is at least zero. At every other moment, the tank held at least its height above that lowest point. This is the **lower wall**: energy the meter proves was there, whatever the starting level. Where a published nameplate capacity caps the tank, the same path gives an **upper wall** below it.

An honest declaration sits between the walls and moves with the path. Figure 1 shows one honest simulated week.

> **Figure 1 (to build).** One scored week of the honest simulated battery (4-week run, seed 0, Branch A): declared deliverable energy at each half-hour boundary, with the lower wall built from the true efficiency and from the estimated one. Simulated data only; no real unit. Script and caption follow `CODING.md` §10.

**Why round-trip efficiency is enough.** The walls measure energy the unit could deliver at the meter, not energy in its cells. In those terms the only figure needed is round-trip efficiency, η. How the losses split between charging and discharging never enters. Think of a bank that charges one fee on deposits and another on withdrawals. If you count your balance as what you could withdraw today, you need only the two fees combined.

**The equations.** For a week starting at half-hour 0, with E⁺ and E⁻ the metered export and import in each half-hour:

> K_t = Σ_{h<t} (η̂ · E⁻_h − E⁺_h)  (change in deliverable energy since the week began)
>
> L_t = K_t − min K  (the lower wall)

η̂ is the estimated efficiency: total export divided by total import, over every complete week after the unit's first (`PREREGISTRATION.md` §3). Each declaration is turned into declared deliverable energy, with the energy it sets aside added back. NESO has not said whether MDO counts energy at the meter or energy in the cells (M13), so every result is computed both ways:

> **Branch A** (MDO is energy at the meter): D^decl_t = MDO_t + P^exp_t + B^exp_t
>
> **Branch B** (MDO is energy in the cells): D^decl_t = √η̂ · MDO_t + P^exp_t + B^exp_t

P^exp and B^exp are the energy still to be exported for the unit's schedule and for instructions already accepted, within the protection horizon: the current half-hour and the next three. The walls are the same under both branches; only the conversion of MDO differs. Branch B assumes charging and discharging are equally efficient, so that each is √η. Public data give only the round trip, so this split cannot be tested; it is recorded as a choice, with its alternative (M26). Under Branch B, MDB is likewise divided by √η̂.

**The weak point is the efficiency.** The wall rises by η̂ times each import, and η̂ comes from the same meter. Over a short window it can be a few points out. A few points of a week's imports move the wall by more than the allowed tolerance. Section 4 shows the effect.

**Three simplifications,** each with a known direction:

- **Standing losses** are not modelled separately. η̂ absorbs them on average, but not their timing (P3).
- **Flow both ways within a half-hour** is hidden, because B1610 gives one net figure. The rebuilt path then overstates deliverable energy, by (1 − η) times the smaller of the hidden import and export, and η̂ is biased low (P7).
- **Time resolution.** Declarations can change every minute; the meter is half-hourly. Claims 1 and 2 are scored only at half-hour boundaries, using the declaration in force at that minute (M9). A declaration that changes and changes back within a half-hour is invisible to them. Claim 5 uses minute timestamps.

## 3. The design

### 3.1 Decide before looking

Every check was written down, and the document locked with a public timestamp, before any real unit was scored. There are five, called claims:

| # | Claim | Question it asks |
|---|---|---|
| 1 | Mass balance | Do declarations change as the meter says deliverable energy changed? |
| 2 | Lower wall | Does a unit declare less than its meter proves it held? |
| 3 | Non-delivery | Does a unit fail to deliver energy NESO took within its declared MDO? |
| 4 | Upper wall | Where nameplate capacity is published, does a unit declare more than its tank could hold? |
| 5 | Response time | How fast do declarations update after an instruction? |

Definitions are in `PREREGISTRATION.md` §3–§7. A **flag** is a verdict on one unit, such as "provable under-declaration". Each claim's flags have thresholds fixed in advance.

### 3.2 Test the tests

A check is worth running on real units only if it gets the right answer when the answer is known. So before any real unit was scored, each claim ran on simulated batteries: 100 runs each, over 4 and 20 scored weeks. Those are the shortest and longest histories in the real fleet.

The simulated batteries follow a schedule, take instructions and hold frequency response driven by GB's measured grid frequency. They report only what B1610 would show: one net figure per half-hour, with metering noise. Some are honest. Each of the others carries one planted fault: declaring 10 MWh too much, declaring a quarter more than it holds, copying a fixed maximum, ignoring its own schedule, or declaring 20 MWh too little.

Each claim had **pass bands** fixed in advance, such as "an honest battery is flagged in at most 5 of 100 runs". A claim that missed a band was not used on real units, or only for what its tests supported.

**What the simulation assumes.** Every simulated battery holds 100 MWh, has a round-trip efficiency of 88% and a power limit of 50 MW. It charges twice and discharges twice a day, aiming at 15% and 85% full. Instructions arrive at random, four a day, each 30–90 minutes long. Metering noise is 0.05 MWh per half-hour. Frequency response follows the Dynamic Containment curve in NESO's Response Services Service Terms v6, Schedule 2, driven by GB grid frequency from 1 June to 25 October 2026. Standing losses are not simulated. Every setting, its source and the random seeds are in `config/synthetic.toml`, committed and hashed before the first run.

The tests therefore show how the claims behave for batteries like these: one efficiency and one way of operating. They say nothing about how common such batteries, or such faults, are in the real fleet. Catching a planted fault is a result about the simulation, not evidence that any real unit misdeclares.

**Reading the counts.** "k of 100" is a count over 100 runs, and has sampling error. As a guide, the 95% intervals (Wilson) are: 0 of 100, 0–4%; 5, 2–11%; 17, 11–26%; 80, 71–87%; 95, 89–98%. Each combination of battery, window length, claim and branch had to pass on its own. The more combinations judged, the more likely an honest claim fails somewhere by chance. Judging every one therefore errs towards failing a claim, not passing it.

**Reused seeds.** Deviation 2 changed a reporting rule after the first run, and later runs reused that run's seeds. A rule tested on the run that prompted it is not independently confirmed. Here this matters little: no claim passed its test on the reused seeds, so no result rests on such a rule.

### 3.3 Changes to the method

The locked method was changed nine times, all before any real unit was scored. Each change, called a deviation, was locked under a new tag, with a statement of what had been seen when it was written (`PREREGISTRATION.md` §12). Three matter here:

- **Deviation 2** responded to the first test run. It limited Claim 1 to window lengths where its tests pass, and recorded Claim 2 as failing. The first run's failure stays in the record.
- **Deviation 5** fixed a fault in rebuilding declared energy. While an older declaration stayed in force after a new instruction, the instruction's energy was counted twice. A diagnostic, specified before it ran, found the fault, and every affected test was rerun. Earlier results stay in the record, marked as preceding the fix.
- **Deviation 9** corrected the fleet from 163 entries to 162 units. One entry was a set of records with no unit ID.

### 3.4 The fleet and the data

The fleet is every unit that submitted a genuine MDO or MDB between 25 June and 29 October 2026. Placeholder defaults do not count, and pumped storage and hydro are left out. That cut-off fell a week before the compliance deadline, so units that started in the last week are left out. Of the 162 units, 31 are secondary units that may group several sites (M10, R19). A unit needs four complete weeks after its first genuine declaration to be scored by 15 November 2026. Ninety-eight qualify. Ninety-five can be scored: three sent no genuine declaration after their first week.

Meter data are used only once the Initial Settlement run (SF) has been made, or a later run. SF is not final. Reconciliation runs (R1, R2, R3 and RF) follow over the next months, and any can revise a figure (M6, R28). Each half-hour's run type is recorded, and each download's date is in its manifest. Results stand on the runs retrieved; later revisions are not rescored unless they expose a proven error (`PREREGISTRATION.md` §10). Every input is fixed by its hash, and the scoring run happens once.

### 3.5 Disclosure

The claims test physical consistency, not conduct, and one of their premises (M13) is unresolved. So this version publishes results for the fleet only, and no figure drawn from fewer than five units. Each company responsible for a unit (its lead party) receives that unit's results privately, at least ten working days before publication. Naming units would need five written conditions, none yet met (`PREREGISTRATION.md` §11).

## 4. What the known-answer tests showed

This section holds the paper's main result. For each claim, it gives what the tests found and why. It also says whether the limit is a **data gap**, closed by publishing or sharing something, or a **method problem**, closed only by a better test. Results for Claims 1, 2 and 4 come from the runs after deviation 5. That fix does not affect Claim 3, and Claim 5 was built after it. Earlier runs are in `outputs/known_answer/`.

### 4.1 Claim 1, mass balance: works, but gives no unit a verdict

Mass balance asks whether each half-hour's change in declared energy matches the change the meter implies. It separates honest from faulty batteries cleanly:

- Every honest battery landed in its pass band in 100 of 100 runs, at every length from 4 to 20 weeks. The plain honest battery was scored "coherent" every time.
- The batteries that over-declare by a proportion, copy a fixed maximum or ignore their schedule were "not shown coherent" in 100 of 100 runs, at every length.

By design, it cannot see an error that stays constant: a fixed offset cancels out of every change (I14). Claims 2–4 were meant to cover that.

The preregistered test still fails. The battery declaring 20 MWh too little was expected to score "coherent", because its error is constant. It scored "indeterminate" almost every time, landing in its band in 0 of 100 runs at every length. Its declarations cannot fall below zero, and about two-fifths of them sat at zero, so its error was not constant after all. This flaw was in the test's own specification and was logged before the run. The band was not adjusted. Under deviation 2's rule, one missed band means Claim 1 gives no unit a verdict, at any length.

**Kind of limit: method.** The data supported the claim; one test's specification did not. A later version could fix that test in advance and rerun it.

### 4.2 Claim 2, the lower wall: wrongly flags honest batteries over short windows

The lower wall should catch a battery that declares less than its meter proves it held. It does: the battery declaring 20 MWh too little was flagged in 100 of 100 runs at both lengths. But it also flags honest batteries:

| Scored weeks | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | 20 |
|---|---|---|---|---|---|---|---|---|---|
| Honest battery flagged, of 100 (Branch A; Branch B) | 17; 20 | 14; 14 | 6; 7 | 4; 5 | 8; 7 | 0; 0 | 0; 0 | 0; 0 | 0; 0 |

At four weeks, 17 of 100 has a 95% interval of 11–26%. From ten weeks, 0 of 100 means a rate below about 4%.

The cause is the estimated efficiency. Over four weeks, the honest battery's estimate ranged from 0.863 to 0.901, around a true 0.88. An error that size, times a week's imports, moves the wall by up to about 20 MWh, against a tolerance of about 2 MWh. With the true efficiency, the false flags almost vanish (P11).

A second limit applies even then. Reserve and response contracts lawfully lower a declaration, so a declaration below the wall may reflect a contract, not an error. No real unit had a week that could be shown to be contract-free (R27). Even with a perfect efficiency, the wall could not prove under-declaration for any unit in this fleet.

**Kind of limit: data, twice.** An independent efficiency figure, or export and import reported separately within each half-hour, would remove the first. Auction results that can be joined to units would remove the second.

### 4.3 Claim 3, non-delivery: right estimate, failed control

Claim 3 is the only check aimed at over-declaration that does not need the tank's size. If NESO takes energy within a declared MDO and the battery runs out early, it held less than it declared. Fitting where deliveries start to fall short estimates by how much.

The estimates were right. For the battery declaring a quarter more than it held, the median estimate was 0.19–0.20, against a planted 0.20. For the one declaring 10 MWh too much, it was 10.7–11.6 MWh.

But a flag also needs a control: instructions where the lower wall proves the battery held enough, so a shortfall cannot be over-declaration. On the faulty batteries, the control showed shortfalls too, so their flags failed. Counting only runs that were flagged with an estimate close to the planted fault, the over-declarers passed in 9–13 of 100 runs at four weeks and 0–6 at twenty. The required number was 80. Under the locked rule, Claim 3 was dropped.

The simulation shows why the control failed. A diagnostic over ten runs traced most failed control instructions to batteries that did hold enough energy. They had committed part of it to their own schedule, which the wall cannot see. The rest came from efficiency error, which put the wall above the true energy held (P12; [`docs/results/claim3_known_answer.md`](../docs/results/claim3_known_answer.md)).

**Kind of limit: both.** The energy committed behind each declaration is a data gap. A control that does not rely on the lower wall is a method problem. A new control may be tested only as a new deviation, fully specified before any rerun.

### 4.4 Claim 4, the upper wall: honest batteries cross it

Where nameplate capacity is published, it caps the tank. Allowing for what the meter shows has since left, a battery should never declare more than that. A test added before any Claim 4 code (deviation 3) asked whether honest batteries stay below that wall. Their ceiling was set generously, at each battery's own highest true energy during the run.

They did not stay below it. After deviation 5, the plain honest battery crossed the wall in 67–69 of 100 runs at both lengths; at most 5 were allowed. Of the batteries the test was judged on, only the one holding frequency response passed, and only at 20 weeks. Even with the ceiling at the full 100 MWh, about 20 MWh above anything the honest battery reached, it crossed in 17 of 100 runs at four weeks. Claim 4 is not used on real units in this version, and no nameplate capacity was looked up.

Two diagnostics, each specified before it ran, traced the cause. Most crossings came from efficiency error, which builds up through the week. The largest came from the double counting fixed in deviation 5: that is how the fault was found.

**Kind of limit: data.** The same estimated efficiency drives this wall. A published efficiency, or a cautious bound on it, would change the result. The test does not show that public data can never bound stored energy.

### 4.5 Claim 5, response time: an upper bound that cannot see intent

Response time is the time from an instruction to the unit's next declaration. NESO's benchmark is one minute. On simulated batteries with known delays:

| True delay | Median measured | Within 1 minute | First record was a routine update |
|---|---|---|---|
| 1 minute | 1 minute | 100% | 3% |
| 5 minutes | 5 minutes | 7% | 17% |
| 25 minutes | 15 minutes | 7% | 84% |

Short delays are measured correctly. Long ones are understated, because a battery that also sends a routine update every half-hour often sends one before it responds. Public data cannot tell the two apart. And BMRS's publish time may lag NESO's receipt; no one has confirmed it does not (M14). So every measured response time is an upper bound.

**Kind of limit: data.** NESO's receipt time, and a flag marking a record as a response to an instruction, would close both gaps.

### 4.6 What the tests add up to

| Claim | Tells honest from faulty? | What prevents a verdict on a unit | Kind |
|---|---|---|---|
| 1 Mass balance | Yes, for errors that change over time | One test misspecified | Method |
| 2 Lower wall | Catches under-declaration; flags honest batteries over short windows | Estimated efficiency; unseen contracts | Data |
| 3 Non-delivery | Estimates right; control fails | Unseen committed energy; estimated efficiency; control design | Both |
| 4 Upper wall | No: honest batteries cross it | Estimated efficiency | Data |
| 5 Response time | Measures short delays | Routine updates; publish-time lag | Data |

One estimate, efficiency, lies under three of the five rows. One missing link, from auction results to units, lies under two. The tests did not find that the physics fails. For batteries like the simulated ones, they found that public data leave out figures the physics needs.

## 5. Fleet results

*After the scoring run. How each figure will be read is fixed in advance: `PROJECT.md` §11, row of [date].*

## 6. Data-quality findings

*To draft: contract coverage (0 of 98); the record set with no unit ID; B1610 serving only the latest settlement run; the sign check's mixed result, settled instead by the BSC; the publish-time caveat (M14).*

## 7. Recommendations

The gaps in section 4 are of two kinds, and so are the fixes. Some information can be published without harm. Some cannot be published safely, but can be checked by a body with a duty to check it.

### 7.1 Why this is a public matter

Consumers pay for balancing. Since April 2023, the charges that recover NESO's balancing costs (BSUoS) have been levied on final demand only (PROVISIONAL: confirm against CMP308 and NESO's charging statement). Capacity Market payments are recovered from electricity suppliers (PROVISIONAL: confirm against the Electricity Settlements Company's charging). When a declaration is wrong, NESO may skip a battery and buy something dearer, or count on energy that is not there. Either way, consumers pay. That gives the public an interest in declarations being right.

This is not a call for a compliance audit. NESO already receives the declarations and can check them. The question is whether anyone else can.

### 7.2 Track 1: publish

None of these needs new measurement. None risks identifying a unit, because BMRS already names every unit they concern.

1. **A register of storage energy for each unit.** Usable and nameplate MWh, with the dates they apply from, for every unit that declares MDO and MDB. SSEN's register has the field, but it is empty (R22). Linking each site to its unit is new work, and the larger task. A secondary unit may group several sites, which join and leave over time, so the register needs the sites behind each unit and their dates, not a single figure.
2. **Auction results that can be joined to units.** A dated table linking each auction unit to the assets behind it and their Balancing Mechanism units. An auction unit is not a Balancing Mechanism unit and may group several assets, so the link needs dates as well as IDs. NESO probably holds it already, because it withholds reserve payments when declarations fail (R4). That is an inference, not yet confirmed (R29). Mandatory frequency response should be covered too: it has no results by unit at all.
3. **A written definition of what MDO counts.** Whether it is energy at the meter or energy in the cells (M13). One sentence from NESO would remove a branch from every result here.
4. **Better timestamps and flags on declarations.** NESO's receipt time beside BMRS's publish time (M14), a flag on placeholder defaults, and a flag marking a record as a response to a named instruction.
5. **Settlement runs that can be cited.** BMRS's B1610 data return the latest settlement run by default (M6), so the same figure, downloaded on different dates, can differ. Archived runs that can be cited would let anyone reproduce a published figure.

Publishing data for each unit is already the norm. BMRS names every unit's schedule, instructions, metered energy and declarations. These items extend that norm.

### 7.3 Track 2: verify under control

Two figures would close most of what remains: each unit's round-trip efficiency, and the energy it commits to contracts in each half-hour. Neither should simply be published, for two reasons:

- **Removing names does not protect them.** BMRS names each unit's metered energy. An unnamed efficiency or commitment series could be matched to its unit by comparing it with those named series. Re-identification here is a demonstrated risk, not a hypothetical one (PROVISIONAL: cite the demonstration, or show it, before publication).
- **They are commercially sensitive.** Efficiency reflects equipment and operation; commitments reveal contract positions.

So the second track is controlled access. NESO, or a body it appoints, would check declarations against efficiency and commitment data, under need-to-know terms, and publish only fleet results and the method. Much of the input already reaches NESO, which sizes its instructions from what each unit declares. The step is to use it to verify as well as to dispatch (PROVISIONAL: confirm which GC0166 submissions include efficiency or commitment data).

### 7.4 What each fix would unlock

| Fix | Track | What it would unlock |
|---|---|---|
| Storage register for each unit | Public | Claim 4 for every unit, not a handful |
| Link from auction units to units | Public | Claim 2's contract screen; part of Claim 3's committed energy |
| What MDO counts (M13) | Public | Removes a branch from every claim |
| Receipt time and response flag | Public | Claim 5 as a measurement, not a bound |
| Efficiency for each unit | Controlled | Claims 2 and 4: removes the main cause of false flags |
| Committed energy | Controlled | Claim 1's ambiguity; Claim 3's control |

The method problems in section 4 need better tests, not better data. Claim 1's flawed test and Claim 3's control are both of this kind. Each can be fixed only by a new test, specified before it runs.

## 8. Limits, and what version 2 needs

*To draft.*

## 9. Reproducibility

*To draft: DOIs, pipeline, licences, data attribution and the AI use statement.*

# Formal rules on the road: what four papers give the road family (architect's research note, 2026-11-05)

The user (2026-11-05): "we are quite advanced on road subject last month but from experienced driver pov we not
nearly there. research other people's attempts to formalize rules in logic, mostly STL, for productive ideas." Four
sources were read in full: Hekmatnejad et al. 2019 (RSS in STL, MEMOCODE), Shea-Blymyer and Abbas 2021 (RSS in
deontic logic, ACM TCPS 5(4):38, arXiv 2105.02851), An et al. 2026 (ontology + SWRL rules + PDDL + factor graph,
Sensors 26:5973), Bhuiyan, Governatori et al. 2023 (Queensland overtaking rules in defeasible deontic logic, Rev.
Socionetwork Strategies 17:233, the user's "ontology but honest attempt"). The road family as it stands: metis-catalog `domains/road` at the pin (responder, planner with
`change.llp`, signals; `capacity.llp` roles; the situation layer in `libs/semantic-world`; the restrictor and the
projection in `road/world`), the patterns in metis-loop `skills/metis-loop/patterns/8-road.md` and CHECKS.md.

## 1. The four formalizations in one look

| | Hekmatnejad 2019 (STL) | Shea-Blymyer 2021 (deontic DAU) | An 2026 (ontology + SWRL) | Bhuiyan 2023 (defeasible deontic) | the road family (LLP) |
|---|---|---|---|---|---|
| what a rule is | an assume-guarantee STL formula over sampled signals: antecedent = the sample where safe turns dangerous, consequent = the response, held by non-strict Release until safe again | an obligation: `ought [α sees to it that A]`, A a CTL* formula; permission its dual; conditional on a context; agency, ability and necessity distinct | a Horn rule over boolean predicates to a directive (requiresStopFor, shouldYieldTo, prefersLane); no number in a rule | a defeasible rule `atoms ⇒ [O|F|P] action` from one article of the code (QLD rules 140–145), with defeaters for its "unless" clauses and a superiority relation between rules | a linear rule over the host's classes, in a stage, in a member; the response is the fold's verdict read per tick |
| numbers | in the predicates (RSS Defs 1–10, ρ, accelerations), robustness = signed distance to violation | none: the dynamics are below the logic | at the perception interface only: nested TTC bands critical ⊂ imminent ⊂ approaching, K-frame debounce | in SPARQL queries behind the vague atoms ("safe to do so" = Rizaldi's safe distance + Pek's safe lane change), hand-written per atom | rule 2: in the host and the projection's parameters, never in a rule |
| time | discrete STL with Next, Until, Release; the response starts the sample after t_b | branching time; obligations change moment to moment (propagation theorems) | per cycle, replan on semantic events only | one time slot at a time (0.05 s), no temporal operator: the verdict is a snapshot | ticks per member (responder every step, planner every tenth), the protocol's ρ |
| exceptions | none: a violation is counted; sensitivity to ρ and the accelerations is a table | an obligation that cannot be met drops (∀¬A ⇒ ¬ought A); a refrain form that holds anyway | optional rules on a switch (conservative / permissive) | the point of the logic: the "unless" is a defeater, the rule it defeats is named, superiority decides a conflict | the amber's can_stop, the red's can_halt, inside: clear never hold, the yielder's inch; unit choice (spec/18) |
| priorities | none | utility over histories; optimal = undominated; obligations are what every optimal history guarantees | rule order by directive strength, hazards as preconditions of `drive` | the superiority relation, written per article (Fig. 2's ordering) | stages (safety before progress), the tree's priority (responder > signals > planner), `@w` |
| checked against | 29 CommonRoad scenarios of real highway traffic: 5.9% of pairs violate (12.3% with the ¬lat∧¬lon rule); which predicate dominated the violation | a highway controller's weighted automaton: model checking whether the controller HAS the obligation | Busan recorded drive, CARLA closed loop, nuPlan CLS-NR 0.686 vs 0.447 | 40 simulator manoeuvres (8 scenarios × 5: 2 clear, 3 borderline) judged by 32 licensed drivers, 8 of them driving instructors: agreement 84–86% on clear, 59% on borderline | the exerciser, SUMO Town01/02, the chair's scenes; rulecheck's classes; the loop's packs |

What each paper found that bears on us:

- **STL paper.** RSS rules are monitors, not control logic (Remark 3.4); the response must be released only when BOTH
  lateral and longitudinal are safe again, else double counting (Remark 3.2, 3.3); human drivers on real highways
  violate RSS in 5.9% of monitored pairs, so an RSS-faithful ego is more defensive than a human driver; the
  violation count moves from 20 to 902 with ρ and the accelerations alone (Table 5): the parameters are the law,
  not the rules; the robustness value names the predicate that dominated the violation (A_r,minBr at t 6.4).
- **Deontic paper.** Formalizing obligation as necessity is wrong (ought p does not give p); RSS1 as `ought no
  rear-end collision` CEASES when the collision is inevitable, the refrain form `ought not to see to it that a
  collision happens` holds anyway; RSS3 "right of way is given, not taken" written as an obligation on the taker
  makes a car that cannot stop obliged to make everybody grant it the way (Prop. 3.1), so the passive form is the
  right one: `ought [if not granted, do not proceed]` PLUS a group obligation that SOMEBODY is granted it, or
  traffic stands still; RSS6 assertiveness is a conditional PERMISSION not to wait for the perfect gap; RSS's star
  calculations (only my own pairs matter) let a car facilitate an accident between two others, a chain of brakes
  being the example; obligations propagate: what I fail to do now I still owe next, under conditions (Lemma 4.1).
- **Ontology paper.** Thresholds out of the rules make a fired rule explainable by which booleans held; the bands
  nest so the stop band sits inside the yield band; a predicate becomes true only after K frames (debounce) and a
  directive grounds as a time-extended deceleration so a misfire is a bounded brake, not phantom braking; hazards
  are preconditions of `drive`, never goals, so no plan can skip one; the graded response to a slow lead is in-lane
  lateral avoidance, then deceleration, then a lane change by routing cost; the semantic layer raises no-at-fault
  collision, drivable area and time-to-collision by 1.3–1.6× on nuPlan, comfort and progress fall.
- **Defeasible paper (the honest one).** Every step of the formalization is manual (atoms by a sentence
  pattern, norms, if–then, DDL), and the authors say so; the vague terms of the code ("safe to do so", "clear view
  of approaching traffic") are NOT in the logic: each is an atom answered by a hand-written query over the
  simulator's data with a borrowed threshold, which is our rule 2 arrived at from the legal side; the exceptions
  are what the logic is for: an "unless" clause is a defeater of the rule it names, and a conflict between two
  applicable rules is settled by a declared superiority, never by rule order; the verdict per time slot is one of
  [O], [F], [P] with the rule that produced it (Table 3: forbidden to overtake right because no atom says "clear
  view of approaching traffic"; permitted once it does); the evaluation is the one we lack: manoeuvres built at
  parameters far from the threshold (clear) and next to it (borderline), judged by drivers and instructors, the
  method agreeing 84–86% on the clear ones and 59% on the borderline ones, where 50% means "truly ambiguous";
  stated limits: not real time, one scenario family (overtaking), participants' own readings of the rules differ,
  video judging is hard.

## 2. Where the road family already is (confirmed, no action)

- Rule 2 (geometry in the host, classes in the rules) is the ontology paper's central decision and the STL paper's
  predicate layer. Keep. The nested bands exist for the zone (`zclass` far/near/at/in) and the target family.
- The responder's `busy` with `stand_down` on `resp_lon(none) ∧ resp_lat_*(none)` IS the STL non-strict Release
  with the Remark 3.2 correction (released only when every component is safe). Keep.
- The safety stage before `decide` IS "hazards as preconditions of drive": progress needs `go`, and `go` comes only
  when no yield fired. Keep.
- Derivation by unit choice (spec/18) IS their optional-rules switch, done properly. Keep.
- Excuses exist and are named: `can_stop` (amber), `can_halt` (red), `unseen_other_duty`, "inside: clear, never
  hold". They are the deontic paper's "an obligation that cannot be met" made concrete, before the paper's authors
  gave up on RSS4 and RSS5 as too vague. Keep; §3 item 4 generalizes them.
- Blame at the onset (Def 18) and rulecheck's five classes ARE the robustness attribution, in classes rather than
  a number. Keep.

## 3. The experienced driver's gaps, ranked, each with the borrowed idea and its LLP shape

**1. Assertiveness: the permission not to wait for the perfect gap (RSS6, the deontic paper §3.2).** The car's
`change` rule needs `safe_long(F) ∧ safe_lat(F)` of the target lane's follower: the conservative χ of the paper,
"wait until the other car, already in the lane, gives α the right of way". An experienced driver changes lanes into
a gap the follower can close politely. The shape: a host class per side, `follower_can_yield(D)`: the follower's
proper response to the ego's arrival would be `brake_min_correct` (the gentle one) and never `brake_min`, computed
by the situation layer as the RSS response of the hypothetical pair (the library has `dynamics_for`; no new
geometry). Then `change` reads `$safe_long(F) ∨ $follower_can_yield(D)` as two rules of one choice site (⊕), the
assertive one weighted below the safe one. The same class at the merge: `yield_merge` keeps its turn logic, but
`wait_turn` ends when the other lane's car can yield gently. The responder stays over it: an assertive change that
turns dangerous is stopped by `stop_lat_*` as today. Measure: Town01/02 arrival times and the count of changes
asked and refused (`change_reason` without `change`).

**2. Somebody must be given the way (RSS3's positive half, the group obligation).** Our `yields_to(same)` makes
the ego yield at equal priority; two such cars stand, and the library's both-standing branch resolves it ("the
side inside first"). The paper names the missing law: at equal priority the GROUP owes a grant to one member, and
the law that says whom is right-before-left (StVO 8(1), Vienna Convention Art. 18(4)): the host resolves `same`
into `ego` or `obj` by the side the other comes from, and `same` remains only for the true tie (two cars each on
the other's right, the four-way case), which the both-standing branch still breaks. One projection change, no
rule change, one accounting row (`granted_by_rule` vs `granted_by_stand`).

**3. Anticipation as a margin band: robustness quantized (the STL paper §4, the ontology paper's bands).** The
planner reads `safe_long` as a boolean and the responder reads `dangerous`; nothing between. An experienced
driver eases off while still safe. The shape: a three-member family on the lead pair, `margin (wide tight none)`,
= the signed robustness of Def 1 quantized by the projection's parameters (tight = the RSS minimum plus a comfort
band), host-published, exclusive. `brake_follow` reads `tight` with `soft(R)` (the planner's gentle brake, as
today's `keep_no`), and a new progress rule `keep_margin` keeps speed at `tight` rather than accelerating. The
comfort headway (the ontology paper's F9, τ = 2 s, ISO 15622) is the band's price, a port. The pattern "Steady
reading" says the band needs hysteresis: the debounce K is a projection parameter per class, declared beside the
thresholds (new line in `8-road.md`: a class that flickers is debounced at the interface, never in a rule).

**4. Every yield carries its excuse (the deontic paper's dropped obligation, made accountable).** Today the
excuses are scattered: `can_stop`, `can_halt`, the inside clause, `unseen_other_duty` is a checker class. The
experienced driver knows when a rule does not apply and can say why. The shape: for each obligation the planner
or the signals member holds, a status atom with a lifecycle in the member's own state, `obl(Z, due | met |
excused(E) | missed)`, the excuse E a value of a closed type (`late`, `cannot_halt`, `inside`, `hidden`,
`others_duty`), written by the rule that declines the obligation, read by rulecheck as the member's OWN account
instead of the checker's guess. This turns rulecheck's classes 3–5 into facts the trace carries, and the pattern
"Fact against truth" gets its second half (the member's claim against the truth rows). Lint L11 keeps
`invariant obl(Z, …) : 1` per zone.

**5. The evasion response (RSS5 "avoid an accident without causing another", which the deontic paper left as
too vague and we have not written).** The responder brakes and stops lateral moves; it never steers. An
experienced driver swerves into a free lane or the shoulder when braking will not do, and nudges within the lane
past a wobbling truck or a cyclist (the ontology paper's F8 lateral avoidance, the first stage of its graded
response). The shape: a restrictor command kind `offset(side)` (in-lane, bounded by the lane's width minus the
margin) and a responder rule `evade [dyn] : $busy * $grant * $resp_lon(brake_min) * $cannot_stop_short * $side_free(D)
* now -o ()` reading two new host classes (`cannot_stop_short`: the longitudinal response alone does not avoid
the collision; `side_free(D)`: the side's pair is safe laterally and longitudinally after the move). The free-space
`drive_away` is this response's unstructured cousin; the lane version needs the library to evaluate the moved pair,
which `dynamics_for` can do. This is the one item that needs new geometry; it comes last.

**6. The chain (the deontic paper's star-calculations critique).** RSS makes only the ego's own pairs its concern;
the paper shows that lets the ego facilitate a collision between two others, a chain of brakes being the case. Our
`undue_brakes` check is the planner's half. The missing class is the follower's: `follower_tight` (the follower is
inside the ego's margin band), read by the planner's brake rules to choose `brake_min_correct` over a harder
soft brake and to begin earlier (item 3's band makes this a weight, not a new rule). Accounting: a brake with the
follower tight is a NOTE row.

**8. The overtaking law is not written (the defeasible paper's whole subject).** `change.llp` changes lanes past a
slow lead; nothing in the family says when overtaking is forbidden or must end: not on the left on a single
carriageway, not across a solid line, not past a "do not overtake turning vehicle" sign, only with a clear view of
approaching traffic, return to the lane without cutting in (QLD 140–145; StVO 5; Vienna Art. 11). The paper's
38 atoms for five articles are a vocabulary we can read straight into host classes (`clear_view_ahead`,
`oncoming_room`, `solid_line(left|right)`, `lead_turning(D)`, `lead_signals(D)`) and an `overtake.llp` unit of the
car (spec/18: a unit of its own, the chair never includes it) with the rules in the family's form: the
prohibitions as the safety stage's holds, the permission as the progress rule under `change`, the "unless" clauses
as the exception members of the classes' families (the LLP has no negation and no defeater: an exception is the
complementary reading the rule reads, the Complementary readings pattern), the superiority as stage order.
The paper's superiority relation is worth one lint: two rules of one stage with a shared premise and opposite
commands with no family member between them is a conflict the sampler would settle by weight, which the law
never allows (an extension of L3 `rules-twin-body`).

**7. Intent shown before the move.** The responder reads `signalled(obj, side)`; the ego shows nothing. Right of way
is given on a signal: an experienced driver indicates, waits a beat, then moves. The shape: `change_reason(D)` →
`indicate(D)` as a planner command one beat before `change`, and the host's `settled(D)` extended with "indicated for
one beat". The deontic reading: the grant is elicited, not assumed; the follower's `follower_can_yield(D)` (item 1)
is read only after the indication.

## 4. A benchmark the family does not have: the human driver as the oracle

The STL paper's result that matters most to the user's complaint is numerical: on real highway traffic the RSS
rules are violated in 5.9% of monitored pairs, and the count is set by ρ and the accelerations, not by the rules.
The road family has no recorded human traffic; it has SUMO's drivers and the exerciser. The proposal: a
MONITOR-ONLY world, `metis-worlds commonroad/`, over CommonRoad's scenarios (XML, open, real highway recordings,
the format of the STL paper's case study): replay the recorded cars, bind the ego's roles on one recorded car,
run the projection and the responder and the planner in observe mode (no command reaches the world: the chair's
stand-in recorder pattern), and count per tick (a) a response our fold demanded that the human did not make,
(b) a yield our planner would have fired where the human went, (c) a lane change the human made that `change`
would have refused (item 1's number), (d) the dominating predicate per disagreement (the robustness attribution).
The sensitivity table (ρ, accelerations, the margin band) comes for free by re-projection without recompilation
(the framework's rule 3). This gives the distance between the family and experienced driving as rows before any
sim, at 0 USD, and it gives the loop surprises with a human trace behind each. The STL paper's numbers (Tables 2–5)
are the comparator.

## 4b. The cheap benchmark: judged manoeuvres, clear and borderline (the defeasible paper's method)

Before any recorded corpus, the paper's evaluation can be run on the exerciser and SUMO at no cost: for each law
the family holds (the yields, the lights, the lane change, later overtaking), build five manoeuvres per
scenario, two at parameters far from the threshold (10 m safe distance → 1 m and 20 m) and three next to it
(9 m, 11 m), let the user, the experienced driver, judge each as right or wrong with the reason, and compare with
the members' verdict (rulecheck's class and the member's own excuse atom of §3 item 4). The clear cases must
agree near 100%: a disagreement there is a surprise record with the user's words, the loop's input. The
borderline cases are expected near 50% and say where the threshold sits for THIS driver: the port is tuned there,
never the rule (Steady reading). This is the user's "experienced driver pov" as a table, with the reasons, and it
is the method the loop already runs one surprise at a time, made systematic.

## 5. Borrowed principles to add to the patterns (no code)

- "A threshold is the host's" (Steady reading) gains the debounce line and the nested-bands line from the ontology
  paper, and the sensitivity line from the STL paper: a parameter the law does not fix is reported with its
  sweep.
- A new pattern, "An obligation with its excuse" (3-protocol or 8-road): the rule that declines a duty says why in
  an atom the checker reads; a checker class that the member cannot state is a missing excuse.
- A new pattern, "Given, not taken, and given to someone": a yield at equal priority needs the law that grants, or
  the stand; the stand is a surprise, never the design.
- A new pattern, "Permission, not obligation": an assertive rule is a second body at a choice site under the safe
  one, never a rewrite of the safe rule; the responder's shield is what makes the permission safe to grant.

## 6. References worth following (from the two papers' lists)

- Rizaldi, Althoff 2015, Formalising traffic rules for accountability of autonomous vehicles (ITSC): the Vienna
  convention's rules in Isabelle/HOL, the one closest to our "law in the catalog" aim; their follow-ups (Rizaldi et
  al. 2017, overtaking in Isabelle) carry the lane-change law we lack.
- Censi et al. 2019, Liability, ethics and culture-aware behavior specification using rulebooks (ICRA): a pre-order
  over rules with violation metrics; the formal frame for "stages, then weights" and for what a pack may reorder.
- Broersen, Brunel 2008, "What I fail to do today, I have to do tomorrow" (CLIMA): obligation propagation, the
  theory behind "inside: clear, never hold" and a missed yield's residue.
- Shalev-Shwartz, Shammah, Shashua 2017, On a formal model of safe and scalable self-driving cars (arXiv
  1708.06374): the source Defs; §3's "an agile policy rather than an overly defensive one" is RSS6.
- Kulicki, Trypuz, Musielewicz 2018, Towards a formal ethics for autonomous cars (DEON); Benzmüller, Farjami,
  Parent 2018, A dyadic deontic logic in HOL: the mechanized side, if a Lean note on the family's obligations is
  ever wanted.
- Huang et al. 2019, Ontology-based driving scene modeling, situation assessment and decision making (ACIRS);
  Armand et al. 2014, Ontology-based context awareness for driving assistance (IV): the ontology line's rule sets,
  for vocabulary only.
- CommonRoad (Althoff et al. 2017, IV): the scenario corpus of §4.
- Bhuiyan, Governatori, Islam, Bond, Rakotonirainy 2020, Traffic rules encoding using defeasible deontic logic
  (JURIX); Bhuiyan, Governatori, Bond, Rakotonirainy 2023, Traffic rules compliance checking of automated
  vehicle maneuvers (AI and Law): the same line as a checker, the nearest cousin of rulecheck; Governatori et
  al. 2013, Computing strong and weak permissions in defeasible logic (J. Phil. Logic): the permission theory
  behind item 1; the 2025 chapter "Formalise regulations for autonomous vehicles with right-open temporal deontic
  defeasible logic" (Springer) adds the temporal side the 2023 paper lacks.
- Prakken 2017, On the problem of making autonomous vehicles conform to traffic law (AI and Law): the legal
  reasoning view of exceptions and vagueness, the frame for §3 item 4.
- Pek, Zahn, Althoff 2017, Verifying the safety of lane change maneuvers of self-driving vehicles based on
  formalized traffic rules (IV); Rizaldi, Immler, Althoff 2016, A formally verified checker of the safe distance
  traffic rules (NFM): the two thresholds the defeasible paper borrowed for its vague atoms.
- Hekmatnejad et al. 2019 itself for the STL encodings of Defs 1–10 (Lemmas 3.1–3.3): if the family ever states a
  responder obligation as a formula for the chair's certification, this is the form.

## 7. What to do with it (proposals, not opened)

1. **road-judged s-?: the judged manoeuvres (§4b)**, pascal, 0 USD: the manoeuvre sets per law on the exerciser
   and SUMO, the user's judgments with reasons, the agreement table clear / borderline, the surprises from the
   clear disagreements. The number the user asked for comes from here first.
1b. **road-human s-?: the CommonRoad monitor world (§4)**, pascal or opus, 0 USD: the world plug, the four counts,
   the sensitivity sweep, the first surprises with human traces. The same number against recorded human driving.
2. **road-assert s-?: items 1, 2, 7** through the pi loop on traces (the user's rule: behaviour rules by the loop,
   projection and vocabulary by pascal): `follower_can_yield(D)`, right-before-left in the host, `indicate(D)`.
3. **road-margin s-?: items 3 and 6**: the margin family and the debounce parameter in the projection, the two
   planner rules, the port for τ; the chair takes the band as its own comfort margin by pin.
4. **road-excuse s-?: item 4**: the obligation lifecycle atoms and rulecheck reading them; a spec/15 or spec/18
   paragraph first (the architect's), since it touches the protocol's accounting.
5. **road-overtake s-?: item 8**: the overtaking unit of the car from the defeasible paper's atom list and StVO 5,
   through the loop; the conflict lint as its check.
6. **road-evade**: item 5 last, after the monitor world shows how often a human swerved where we would only brake.

Order by the user's complaint: 1 measures it, 2 and 3 are what the experienced driver does differently, 4 is
how the car explains itself, 5 is the one new response.

# Level-k at the zone: the game-theoretic augment of the road law (design, the architect, 2026-11-06)

**Status: DESIGN, the user's word (2026-11-06): "we can put this work in main road catalog, because this kind of conflict resolution will augment nicely our strict rules and basically optimize our go-no-go strategy." Source of the idea: the TUM-2024 CommonRoad planner's interactive module (the competition report, arXiv 2512.19564 §4.3) on Li, Kolmanovsky, Girard and Yildiz 2018, "Game theoretic modeling of vehicle interactions at unsignalized intersections". Ideas only; no code of theirs is read into ours. 0 USD.**

## 0. The claim

Level-k is bounded recursive reasoning, not a Nash equilibrium: level 0 is the myopic move, level k is the best reply to a level-(k−1) other, the recursion stops at 2, and the other's level is a belief. A fixed point over strategies is beyond linear logic; a recursion of depth two is a conjunction of two best-reply premises, which the law states in three rules. The numeric game (scoring moves over a horizon with a kinematic model and a reward) is the semantic world's; the levels and the decision are the law's; the belief over the other's level is spec 16's categorical port with its Bayesian update. The shield (the responder's rule 5 bounds, the restrictor) is unchanged: the game decides assertiveness inside the law's safe set, never the response.

## 1. Where the game applies

At a zone (`nextzone`) with a crosser O bound to a role, in one of three readings the host states exclusively (`family zone_game (by_rule by_game)`, stated where a zone exists):
- `by_rule(nextzone)`: a sign, a light or right-before-left settles the priority and the other is seen to follow it: the law as today (`yield_zone`, `brake_cross`, `brake_cross_late`, rule 5).
- `by_game(nextzone)`: the rule is silent (simultaneous arrival at an all-way crossing, a merge, a narrow passage, a priority the other does not take) OR the other's moves contradict the rule's prediction (the holder hesitates, the yielder keeps coming): the game's rules decide the planner's commitment; the responder's bounds still cap it.
The host decides `by_game` from the rule's prediction against the observed moves over the last ticks (the same belief that the levels use: a rule-follower is a level the belief tracks, see §4).

## 2. The host's contract (semantic_world/levelk.py; the exerciser and SUMO hosts call it per tick for each crosser at a by_game zone)

Moves on lanes are longitudinal: `type move {go hold yield}` (go: accelerate or keep toward the zone; hold: keep the present speed short of committing; yield: brake to stop before the line). A lane change is the law's own decision, not a move of the game. The host scores each pair of moves over a horizon H (3 s, dt 0.1) with a kinematic rollout and the reward R = w_c·collision + w_s·safe_distance (the RSS distance of the pair, the fold's) + w_p·progress + w_l·lane; the weights are rates in the sense of spec 19 (constants of the host, fit by notching from the catalog later, never tuned in a rule). From the scores the host states, per crosser O:

```
pred crosser(zone, obj) : planner.       % O approaches the zone on a crossing or merging lane, not yet inside: the game's partner (holder names the one inside)
pred myopic(obj, move) : planner.        % O's level-0 move: its best move with the ego STANDING (Li et al.'s level 0: others as static obstacles)
pred ego_myopic(obj, move) : planner.    % ego_myopic(O, E): the ego's level-0 move against O alone (the game is pairwise)
pred reply(obj, move, move) : planner.   % reply(O, E, M): O's best move M if the ego plays E (one step)
pred ego_reply(obj, move, move) : planner.   % ego_reply(O, M, E): the ego's best move E if O plays M (one step)
pred level_belief(obj, klevel, blevel) : planner.   % the belief that O reasons at level k, quantised (spec 16 level port)
pred believed(obj, klevel) : planner.    % the argmax level (one per crosser)
pred by_rule(zone) : planner.
pred by_game(zone) : planner.
family zone_game (by_rule by_game).      % per zone, where a zone is
```
`type klevel {l0 l1 l2}`, `type blevel {low mid high}` (the family's belief levels). The zone's reading `by_rule(nextzone)` is stated EVERY tick wherever a zone is, the game on or off (off = always by_rule): `yield_zone` and `keep_cross` read it since the unit exists. The tables are tiny (3×3 per crosser) and the rollout is the semantic world's existing prediction kernel over the pair's lane geometry; the host never states a trajectory, only moves.

## 3. The law: the levels as premise chains (the unit `levelk.llp`, the car's and the chair's)

Level k of the other is a chain of k+1 reads over the host's tables; the bindings flow through the `$` premises as `change.llp` binds `K` through `$lane_kind(D, K) * off_route(K)`:

```
% O at level 0 plays M:          $myopic(O, M)
% O at level 1 plays M:          $ego_myopic(O, E0) * $reply(O, E0, M)
% O at level 2 plays M:          $myopic(O, M0) * $ego_reply(O, M0, E1) * $reply(O, E1, M)
```
The decision reads the believed level and the move it predicts, in the planner's two stages:

```
stage safety {
  %% The zone is nobody's by rule, a car comes, and at the level I believe it is, it keeps coming: I yield.
  yield_game_l0 [dyn] : $busy * $tick__grant(planner, controls) * $by_game(nextzone) * $zone_at(nextzone, C) * $closing_in(C) * $crosser(nextzone, O) * $believed(O, l0) * $myopic(O, go) * now -o ().
  yield_game_l1 [dyn] : ... * $believed(O, l1) * $ego_myopic(O, E0) * $reply(O, E0, go) * now -o ().
  yield_game_l2 [dyn] : ... * $believed(O, l2) * $myopic(O, M0) * $ego_reply(O, M0, E1) * $reply(O, E1, go) * now -o ().
}
stage progress {
  %% The zone is nobody's by rule, and at the level I believe it is, the car yields to me: I go on.
  go_game_l0 [dyn] : $busy * $tick__grant(planner, controls) * $by_game(nextzone) * $crosser(nextzone, O) * $believed(O, l0) * $myopic(O, yield) * $below_target * $lead_ok * $accel_ok * go -o ().
  go_game_l1 / go_game_l2 : the same with the level-1 / level-2 chains ending in yield.
  %% ... it holds: I keep my speed and watch (the present-only bounds keep the stop available).
  keep_game_* : the chains ending in hold, the command keep.
}
```
Nine rules, three per predicted move, the `%%` lines a person reads. Today's `yield_zone` and `keep_cross` gain `$by_rule(nextzone)` (the base change, the family evolving; derivation by GATING, spec 18), so the rule's reading and the game's never fire together. Two crossers are two chains: a yield in the safety stage wins over any go; two progress reads compete for the one `go` until the weight form orders them. The unit includes nothing: the member's program brings `planner_domain.llp` (the car through `change.llp`, a chair directly) and `levelk.llp` after it. Step 1 landed as metis-catalog road-levelk 937b79b: 18 cases (nine rules; by_rule ignores the tables ×3; the believed level selects the chain ×3; the l2 chain binds its moves; two crossers ×2), 64 planner cases pass. Where the belief is spread (no level above `mid`), the law's default is the rule's: `by_game` is not stated and today's law holds. A second form, when the levels' weights should draw the decision instead of the argmax: the three `go_game_*` rules carry weight ports reading `level_belief` (spec 16 §2, spec 19 §7.3), and the sampler draws proceed/yield in proportion: the expected-reward choice in the mass-action semantics. The first form ships; the second is one manifest change.

## 4. The belief and its update (spec 16)

Per crosser, a categorical belief over {l0, l1, l2} (prior 0.2 / 0.6 / 0.2 as the source; a constant of the host). Each tick the host observes O's move (quantised from its acceleration against its myopic/reply predictions) and updates the posterior with a likelihood P(observed move | level) that is a softmax of the level's predicted move with a temperature (the user's improvement A over the source's L1 nearest-model pick): smooth, and a driver that changes behaviour moves the belief within a few ticks. `believed(O, K)` is the argmax; `level_belief(O, K, L)` the quantisation, both stated by the host this round; the spec 16 manifest form (`beliefs:` over a weight port, `levels:` from it) lands with the weight form. Step 2 (nina, road-levelk-host): on the two-car left turn every pairing clears except l0×l0 and l2×l0 (contact) and l1×l1 (the level-k deadlock); the believing ego clears against l0, l1 and l2. Behaviour types beyond depth (cooperative, assertive, aggressive: the source's improvement B) are a second categorical port later, separate from the level, as the user's note says.

## 5. The small world: metis-worlds road/intersection

A world under the exerciser (no SUMO): two or three roads crossing at one unsignalised zone, no signs; the ego and one or two other cars whose drivers ARE level-k agents of the host's own game at a fixed or drawn level (so the world and the law share one game, and a level-2 ego meets level-0/1/2 others). Cards (v2, source `ours`, tags `junction-priority`, `right-before-left` where it applies): the unprotected left against oncoming; the four-way simultaneous arrival; the crossing gap; each with the other's level as a `params` entry (range l0..l2, the variants). Measures: collisions (the shield's test), deadlock (both hold or both yield beyond T), delay to clear the zone, and the belief's convergence (ticks until `believed` matches the other's true level), read with behavioural equivalence (step 4's ruling): a driver is `identified` by `level` when it converges and by `behaviour` when the believed level predicted the true level's move on every tick of its game (an l2 that moves as l0 or l1 in every state of a card). Later the same cards on SUMO with the others driven by SUMO's model (level 0 in effect) and on CommonRoad's recorded crossers (a recording is a level-0 driver that never reacts: the belief must find l0 fast).

## 5b. The waiver: a holder that stands has given the way (the architect's WAIVER RULINGS 1 and 2, levelk step 3)

The game can say go against a level-1 holder that waits; the shield (rule 5's yielder bound) is what held the ego, and it stays belief-free. RSS reads right of way as GIVEN, not taken: a priority holder that stands while the ego visibly enters has given it; its proper response from then on is to keep standing, and a contact after that is the holder's violation. `semantic_world/situation.py` releases the yielder (a crossing where the ego yields, `xing_obj_prio`; never a walker or cyclist, never an occluded holder) on a holder that has stood a beat (`WAIVER_STOOD`) by two rules, either sufficient:

- **The geometric window** (`waiver_window`): the holder reaches the zone no earlier than its response time plus its run from standstill at its top acceleration; when the ego, from its present speed at its own acceleration, has its rear past the zone plus its floor before that, entering is RSS-proper whatever the holder intends. It needs no trust in the holder, and it closes against a holder standing at its line while the ego is slow or far.
- **The two phases** (`waiver_phase`): (1) APPROACH: the bound keeps the ego's stop short of the holder's path available one cycle on, at a speed no higher than the CRAWL that makes its visible approach last `WAIVER_RHO` (2 s, one rho for all) before the commitment point; the both-standing "stay" is lifted, the planner's game rule moves the ego. A holder that moves in this phase is today's moving holder (the ego stops short of its path). (2) COMMITMENT: at the last point where the stop short is still available, the bound becomes none iff the holder still stands and the ego has been seen moving (above `WAIVER_V`) toward it for `WAIVER_RHO`: the holder had its response time to object and did not. Committed, the bound stays none until the ego has cleared.

**The world rule**: a holder that starts after the ego committed restarts after its waiver; a contact with it is attributed to the holder (`collisions_partner` in the intersection world's summary, kept in the row), not the ego's fail (`collisions_own`).

**Measured** (road-waiver-2, the exerciser, the family at pin 915eae9): ix-left-turn and ix-crossing-gap, deadlocked against level-1 holders before (29.5 s, 42.5 s), now clear with no contact (delays 8.9 s and 17.1 s). On both it is the approach that unblocks them: once the ego creeps in and gains speed, the geometric window opens (10.7 s; 16.3 s and 16.8 s) before the commitment point; the commitment and the restart's attribution are the tests' (a slow ego, a forced restart). This is also the game's own answer: a standing holder contradicts level 0's go, the belief moves to level 1, `go_game_l1` fires; the shield was the blocker, not the game.

## 6. For the chair

The same unit and host contract at a pedestrian crossing or a corridor: moves go / hold / yield, the host's scoring with the chair's dynamics and the people's model; `by_game` where no rule settles who passes first. Nothing in the unit names a car.

## 7. Steps (subject levelk-intersection, on the user's word)

1. The architect: this design; the unit `levelk.llp` in metis-catalog domains/road with its vocabulary and the nine rules; `by_rule` gating on `yield_zone`; cases for each level and move (18) through the judge; the belief port in the manifest.
2. nina: `semantic_world/levelk.py` (the moves' rollout and reward, the reply tables, the belief with its softmax likelihood, tests on the source's two-car example: the left turn against oncoming, each level pairing) and the projection in both hosts.
3. opus: `road/intersection/` (the world, the level-k driver agents, the cards, the measures) under the exerciser; the runner plays them; the three cards into the catalog with verdicts.
4. The architect (DONE 2026-11-07, the STEP 4 RULING on s-5be9291b and §8 below): the ruling on the first table (collisions 0 at every pairing; deadlocks resolved; belief convergence) and the paper note (the formalisation: levels as premise chains, the belief as a port, the shield as the safety argument).

## 8. Paper note: the formalisation (the architect, step 4, 2026-11-07)

What the unit shows, stated for the catalog paper's road section; the measurements are the three cards' at road-waiver-2 (law 915eae9).

**Levels as premise chains.** Level-k reasoning of depth k is k+1 reads over the host's two reply tables, and nothing else: `myopic(O, M)` is depth 0; `ego_myopic(O, E0) * reply(O, E0, M)` depth 1; `myopic(O, M0) * ego_reply(O, M0, E1) * reply(O, E1, M)` depth 2. The recursion is bounded by construction (a rule has finitely many premises), so no fixed point over strategies is asked of the logic, which linear logic could not state; the numeric game (rollout, reward, best reply) stays in the host and enters the law only as the tables' facts. Nine rules, three per predicted move of the other, make the decision; `by_rule(zone)` gates today's rules so that the rule's reading and the game's never fire together (derivation by gating, spec 18). The chair's unit is the same file: nothing in it names a car.

**The belief as a port.** The other's level is a categorical belief over {l0, l1, l2} in spec 16's form: a prior (0.2 / 0.6 / 0.2), a softmax likelihood of the observed move under each level's prediction, the argmax stated as `believed(O, K)`, the quantised mass as `level_belief(O, K, L)`. Measured: l1 identified in 9 to 127 ticks; l2 often never. The second is behavioural equivalence, not a defect of the update: in nearly every state of these cards a level-1 and a level-2 other predict the same move (both yield to a going ego, both go against a standing one), the likelihoods tie and the posterior stays where the prior put it. The decision does not depend on the tie, since the l1 and l2 chains end in the same move there. The convergence measure therefore reads identified either when the argmax matches the true level or when the believed level predicts the true level's move on every tick of the run (a later item in the world).

**The shield as the safety argument.** The game decides assertiveness; the response (the responder's rule 5 bounds, the restrictor) is untouched and is the argument: collisions by the ego 0 at every level pairing on the three cards, with and without the waiver. The level-k deadlock (both at level 1, each believing the other level 0, each yielding) is not the game's to solve: the belief leaves it in a few ticks (standing contradicts level 0's go, so the posterior moves to level 1 and `go_game_l1` fires); the shield held the ego, because its bound read the standing holder as a worst case that may start now at full acceleration. The waiver (§5b) is the formalisation of RSS's reading that right of way is given, not taken, in two phases: the geometric window (the ego clears before the holder could arrive from standstill after rho) needs no trust and is a sufficient condition; the commitment (the holder still stands after rho of the ego's visible approach, the ego past the last point where its stop short of the holder's path is available) makes the holder's proper response from then on to keep standing, and a contact after it is the holder's violation, attributed in the world. Measured: the approach phase alone resolves both level-1 cards (29.5 s to 8.9 s; 42.5 s to 17.1 s); the committed bound is reached by the tests only (a slow ego, a forced restart), which is the property of the design, not a gap: the commitment is the argument for the case the geometry does not reach.

**What is not claimed.** No equilibrium, no optimality of the reward, no identification of level 2 beyond behavioural equivalence, no claim at SUMO or CommonRoad crossers yet (a recording is a level-0 driver; the belief must find l0 fast: the next round's card). The weight form (the three go rules drawing from `level_belief`) is one manifest change and unmeasured.

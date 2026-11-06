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
pred myopic(obj, move) : planner.        % O's level-0 move: its best move ignoring the ego's reaction
pred ego_myopic(move) : planner.         % the ego's level-0 move
pred reply(obj, move, move) : planner.   % reply(O, E, M): O's best move M if the ego plays E (one step)
pred ego_reply(move, move) : planner.    % ego_reply(M, E): the ego's best move E if O plays M (one step)
pred level_belief(obj, klevel, blevel) : planner.   % the belief that O reasons at level k, quantised (spec 16 level port)
pred believed(obj, klevel) : planner.    % the argmax level (one per crosser)
pred by_rule(zone) : planner.
pred by_game(zone) : planner.
family zone_game (by_rule by_game).      % per zone, where a zone is
```
`type klevel {l0 l1 l2}`, `type blevel {low mid high}` (the family's belief levels). The tables are tiny (3×3 per crosser) and the rollout is the semantic world's existing prediction kernel over the pair's lane geometry; the host never states a trajectory, only moves.

## 3. The law: the levels as premise chains (the unit `levelk.llp`, the car's and the chair's)

Level k of the other is a chain of k+1 reads over the host's tables; the bindings flow through the `$` premises as `change.llp` binds `K` through `$lane_kind(D, K) * off_route(K)`:

```
% O at level 0 plays M:          $myopic(O, M)
% O at level 1 plays M:          $ego_myopic(E0) * $reply(O, E0, M)
% O at level 2 plays M:          $myopic(O, M0) * $ego_reply(M0, E1) * $reply(O, E1, M)
```
The decision reads the believed level and the move it predicts, in the planner's two stages:

```
stage safety {
  %% The zone is nobody's by rule, a car comes, and at the level I believe it is, it keeps coming: I yield.
  yield_game_l0 [dyn] : $busy * $tick__grant(planner, controls) * $by_game(nextzone) * $zone_at(nextzone, C) * $closing_in(C) * $holder(nextzone, O) * $believed(O, l0) * $myopic(O, go) * now -o ().
  yield_game_l1 [dyn] : ... * $believed(O, l1) * $ego_myopic(E0) * $reply(O, E0, go) * now -o ().
  yield_game_l2 [dyn] : ... * $believed(O, l2) * $myopic(O, M0) * $ego_reply(M0, E1) * $reply(O, E1, go) * now -o ().
}
stage progress {
  %% The zone is nobody's by rule, and at the level I believe it is, the car yields to me: I go on.
  go_game_l0 [dyn] : $busy * $tick__grant(planner, controls) * $by_game(nextzone) * $holder(nextzone, O) * $believed(O, l0) * $myopic(O, yield) * $below_target * $lead_ok * $accel_ok * go -o ().
  go_game_l1 / go_game_l2 : the same with the level-1 / level-2 chains ending in yield.
  %% ... it holds: I keep my speed and watch (the present-only bounds keep the stop available).
  keep_game_* : the chains ending in hold, the command keep.
}
```
Nine rules, three per predicted move, the `%%` lines a person reads. The `yields_to(same)` case of today's `yield_zone` is gated by `by_rule`: the base rule gains `$by_rule(nextzone)` (one base change, the family evolving; derivation by GATING, spec 18), so the two units never fire together. Where the belief is spread (no level above `mid`), the law's default is the rule's: `by_game` is not stated and today's law holds. A second form, when the levels' weights should draw the decision instead of the argmax: the three `go_game_*` rules carry weight ports reading `level_belief` (spec 16 §2, spec 19 §7.3), and the sampler draws proceed/yield in proportion: the expected-reward choice in the mass-action semantics. The first form ships; the second is one manifest change.

## 4. The belief and its update (spec 16)

Per crosser, a categorical belief over {l0, l1, l2} (prior 0.2 / 0.6 / 0.2 as the source; a constant of the host). Each tick the host observes O's move (quantised from its acceleration against its myopic/reply predictions) and updates the posterior with a likelihood P(observed move | level) that is a softmax of the level's predicted move with a temperature (the user's improvement A over the source's L1 nearest-model pick): smooth, and a driver that changes behaviour moves the belief within a few ticks. `believed(O, K)` is the argmax; `level_belief(O, K, L)` the quantisation. Behaviour types beyond depth (cooperative, assertive, aggressive: the source's improvement B) are a second categorical port later, separate from the level, as the user's note says.

## 5. The small world: metis-worlds road/intersection

A world under the exerciser (no SUMO): two or three roads crossing at one unsignalised zone, no signs; the ego and one or two other cars whose drivers ARE level-k agents of the host's own game at a fixed or drawn level (so the world and the law share one game, and a level-2 ego meets level-0/1/2 others). Cards (v2, source `ours`, tags `junction-priority`, `right-before-left` where it applies): the unprotected left against oncoming; the four-way simultaneous arrival; the crossing gap; each with the other's level as a `params` entry (range l0..l2, the variants). Measures: collisions (the shield's test), deadlock (both hold or both yield beyond T), delay to clear the zone, and the belief's convergence (ticks until `believed` matches the other's true level). Later the same cards on SUMO with the others driven by SUMO's model (level 0 in effect) and on CommonRoad's recorded crossers (a recording is a level-0 driver that never reacts: the belief must find l0 fast).

## 6. For the chair

The same unit and host contract at a pedestrian crossing or a corridor: moves go / hold / yield, the host's scoring with the chair's dynamics and the people's model; `by_game` where no rule settles who passes first. Nothing in the unit names a car.

## 7. Steps (subject levelk-intersection, on the user's word)

1. The architect: this design; the unit `levelk.llp` in metis-catalog domains/road with its vocabulary and the nine rules; `by_rule` gating on `yield_zone`; cases for each level and move (18) through the judge; the belief port in the manifest.
2. nina: `semantic_world/levelk.py` (the moves' rollout and reward, the reply tables, the belief with its softmax likelihood, tests on the source's two-car example: the left turn against oncoming, each level pairing) and the projection in both hosts.
3. opus: `road/intersection/` (the world, the level-k driver agents, the cards, the measures) under the exerciser; the runner plays them; the three cards into the catalog with verdicts.
4. The architect: the ruling on the first table (collisions 0 at every pairing; deadlocks resolved; belief convergence) and the paper note (the formalisation: levels as premise chains, the belief as a port, the shield as the safety argument).

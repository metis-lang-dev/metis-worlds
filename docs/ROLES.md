# Roles (the user's word, 2026-11-07)

Four seats, four roles. A branch advances on the TEST BENCH's local run, not on GitHub's CI, which stays as the record and the nightly but never gates a hand-over (its runs are not cascading and take half an hour each; waiting on them idled every seat).

| role | seat | does | does not |
|---|---|---|---|
| **architect** | taycann (architect) | designs from the user's proposals or its own; briefs; rules on escalations (a decision the local context cannot make: vocabulary, a principle, a law gap's reading); the paper notes | control the development process: no merging, no CI watching, no queue |
| **coder** | opus | every coding task, one at a time, on a branch; asks the test bench for a run; asks the architect only when the brief does not decide | merge; wait for GitHub |
| **test bench** | george (panzer) | runs a branch's tests, the catalog check and the SUMO cards locally on panzer at the coder's or the integrator's request, and answers "ok at <sha>" or the failing rows; keeps the harvest and the law-change reruns | fix the code (a failing row goes back to the coder) |
| **integrator** | nina | the merge queue: order, rebases, ff-only merges into the mains, the pins; dispatches and reads GitHub's CI as the record; tells the coder when main moved under a branch | wait for a run before merging what the test bench passed |

## The hand-over
1. The coder pushes a branch and tells the test bench the sha and what to run.
2. The test bench runs it on panzer (the suites, `scenario_run.py check` on the exerciser, the SUMO cards the change touches) and answers the coder AND the integrator: ok at the sha, or the rows.
3. The integrator merges ff-only (a throwaway worktree with `-b`, `push HEAD:main` verified by `git rev-parse origin/main` after) in the queue's order; GitHub's CI runs on main as the record; a red main is the integrator's to read and route back to the coder.
4. The architect is asked, not waited for: a question goes by message with the context; work continues on what the question does not block.

## Still in force
Never `commit -a` in the shared checkout; one file per agent on a subject; law only through the judge and the cases; nothing stored without its notice; 0 USD unless briefed; the user's gates; panzer runs the tests, taycann refines.

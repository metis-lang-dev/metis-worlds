# road/tools

`rulecheck.py LOG NET` is the road's accounting on a run's log (`.metis/road/log.jsonl`, one line of counts per run). It checks the ego against a short list of European road rules, with the article of the Vienna Convention on Road Traffic (1968) where one applies:

- red and amber light entries (Art. 5, 18), from the net's light programs, not read from SUMO
- minor links entered, with the speed at each (Art. 18): no threshold, that speed is ours and not the law's, and the log has no one to yield to yet
- speed over the lane's limit (Art. 13), apart from speed over a junction lane's limit, which is netconvert's `limitTurnSpeed` and no legal limit
- lane change inside a junction or within 30 m of the stop line (Art. 11(8), 14(1)): neither the Convention nor the German StVO bans a lane change in a junction as such
- standing inside a junction, and all standing by lane (Art. 18(5)); speed lost faster than a brake could; ticks on a parking lane

It is an account, not a judge: no rule of the domains reads it. Its counts are the surprises the loop gets later.

`rulecheck.py --sort TRACE_DIR [--cases DIR] LOG` takes the run's RSS violations, as `sumo_host.account` counts them, and sorts each by why it is one, from the log's row and the responder's facts on the trace: checker, projection, competing rules, responder, gap. One JSON row per violation, then the counts; `--cases` writes a surprise case for each (`metis.trace.case`, the responder's `brake_lon*` asked at the tick). Class 2 (projection) is the sorter's call on the truth rows: it says what the belief lacked, not why. `road/tests/sort_seed2.jsonl` holds Town01 seed 2's verdicts as they were before the settled fix, all class 2; those violations were the host's bug, so they are regression data for the host and no case of a package.

A violation the truth asks for and the ego could not know is its own class, "unseen, the other's duty": every dangerous pair one the ego has the way over, its other not seen. By the ruling it is the yielder's. `sumo_host.account` counts it apart (`unseen_other_duty`, beside `violations`), and it is listed, never dropped.

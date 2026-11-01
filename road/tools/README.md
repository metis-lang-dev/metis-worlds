# road/tools

`rulecheck.py LOG NET` is the road's accounting on a run's log (`.metis/road/log.jsonl`, one line of counts per run). It checks the ego against a short list of European road rules, with the article of the Vienna Convention on Road Traffic (1968) where one applies:

- red and amber light entries (Art. 5, 18), from the net's light programs, not read from SUMO
- minor links entered, with the speed at each (Art. 18): no threshold, that speed is ours and not the law's, and the log has no one to yield to yet
- speed over the lane's limit (Art. 13), apart from speed over a junction lane's limit, which is netconvert's `limitTurnSpeed` and no legal limit
- lane change inside a junction or within 30 m of the stop line (Art. 11(8), 14(1)): neither the Convention nor the German StVO bans a lane change in a junction as such
- standing inside a junction, and all standing by lane (Art. 18(5)); speed lost faster than a brake could; ticks on a parking lane

It is an account, not a judge: no rule of the domains reads it. Its counts are the surprises the loop gets later.

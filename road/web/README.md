# road/web — the road's own page

`../demo.sh` serves it under metis-agent's service. `world.html` and `world.js` are metis-worlds `web/`'s template, the worlds' common page, changed here alone. `road.js` stands where `map.js` does, `dash.js` is the dashboard under the view; `client.html` and `client-shim.js` hold the 3D view. `vendor/` holds the same copies of fsttm-web and the consoles' shell as the other worlds' pages, never edited here.

`client/` is sumo-web3d's built client (Sidewalk Labs), a copy kept here and changed for this page, under the Eclipse Public License 2.0, not the Apache License of metis-worlds: `client/NOTICE` says what changed. Licensing is per world. `client-shim.js` is ours: it answers the client's socket and fetches from the road's frames, so its backend and its SUMO are never started. sumo-dashboard's analyses are ideas here, no code of it.

The Traffic dock is sumo-gui's live controls over TraCI (scale, stop, remove, close a lane, lights), and adding cars, which sumo-gui does not offer (road_host.py `traffic`). The towns are `../maps`, CARLA's, converted by `../maps/build.sh`; its 3 big towns are not tracked.

## Marking a problem

The top bar's **mark event N** button: press it when you see a problem, and again (**end event N**, red) when it is over. Events count 1..N over the demo, across runs; a reload keeps the count, a new demo starts it again. Starting a new run ends an open event.

Each edge goes in the journal as a world line, `mark:N:start:TICK` or `mark:N:stop:TICK` (the JOURNAL dock's save has them), and in the run's `log.jsonl` as a row with the car's place: `{"mark": N, "edge": "start", "at_tick": ..., "scenario": ..., "seed": ..., "lane": ..., "s": ..., "v": ...}`.

## The loop dock, the events, the tools (loop-road-ui s-0314a8ee)

The page is for road and regulation testers. **TOOLS** is one dock of cards (Drive, Cars, Traffic), folded like the DIALOG's sections; RUN stays its own.

**EVENTS** lists the run's events, newest first. A *mark* is a window you open and close: the top bar's button, or by voice "mark" … "end mark, WORDS". A *surprise* is a one-off event the page makes itself when the run's collisions or violations rise (a rise within 2 s of the last is the same one). With "stop on a surprise" ticked, the run pauses on it until you continue ("continue the run", the play button, or "continue"). Each event goes to the host as `mark:N:start|stop`, `mark:N:once:KIND` or `mark:N:move:K0:K1`. In the run's `marks.jsonl` it has its window in the trace's k (`at_k`), and the last start/stop pair is the window. The list is kept in the browser per trace.

The **dashboard** shows the last 6000 ticks, 10 minutes (`dash.js` WINDOW; the trace's ring keeps the same). The events are drawn on every chart: a mark as a band, a surprise as a red line. Click one to select it, and drag an ended mark's edge to move it. The axis holds still while the pointer is over the charts. The glyphs at its right act on the selected event: **¶ narrate** sends `/mark TRACE:MEMBER K0..K1 WORDS` for the planner and the responder (the rules' own words and what was one fact short, free). **? explain** asks pi in words why the car acted so (paid). In EVENTS, **⇢** also sends it to the loop: `/disagree M WORDS` (a confusion record) then `/take`. Pi proposes a correction, and you confirm or refuse it at the gate.

**LOOP** is the pi loop's CHAT: an iframe of the loop console (`metis-loop/run.sh` started in `metis-worlds/road`, port 8770, or `?loop=URL`) with `?panels=chat&embed=<this page's origin>`, never a copy of its code. The two talk by `postMessage`, origin-checked on both sides (metis-loop console/lib/embed.js). The loop's rows are spoken through this page's one voice as announcements. The gate is asked as the agent's question: confirm or refuse, by chip or by voice. The TALK line routes by `loopgrammar.js` (a keyword table, no model). The loop's and the events' lines go there, and TALK marks them `you → loop` or `you → events`. Everything else ("stop", "go right", the questions) stays the road agent's.

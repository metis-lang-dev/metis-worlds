# road/web — the road's own page

`../demo.sh` serves it under metis-agent's service. `world.html` and `world.js` are metis-worlds `web/`'s template, the worlds' common page, changed here alone. `road.js` stands where `map.js` does, `dash.js` is the dashboard under the view; `client.html` and `client-shim.js` hold the 3D view. `vendor/` holds the same copies of fsttm-web and the consoles' shell as the other worlds' pages, never edited here.

`client/` is sumo-web3d's built client (Sidewalk Labs), a copy kept here and changed for this page, under the Eclipse Public License 2.0, not the Apache License of metis-worlds: `client/NOTICE` says what changed. Licensing is per world. `client-shim.js` is ours: it answers the client's socket and fetches from the road's frames, so its backend and its SUMO are never started. sumo-dashboard's analyses are ideas here, no code of it.

The Traffic dock is sumo-gui's live controls over TraCI (scale, stop, remove, close a lane, lights), and adding cars, which sumo-gui does not offer (road_host.py `traffic`). The towns are `../maps`, CARLA's, converted by `../maps/build.sh`; its 3 big towns are not tracked.

## Marking a problem

The top bar's **mark event N** button: press it when you see a problem, and again (**end event N**, red) when it is over. Events count 1..N over the demo, across runs; a reload keeps the count, a new demo starts it again. Starting a new run ends an open event.

Each edge goes in the journal as a world line, `mark:N:start:TICK` or `mark:N:stop:TICK` (the JOURNAL dock's save has them), and in the run's `log.jsonl` as a row with the car's place: `{"mark": N, "edge": "start", "at_tick": ..., "scenario": ..., "seed": ..., "lane": ..., "s": ..., "v": ...}`.

## The events, the tools, Metis (loop-road-ui s-0314a8ee; metis-plugin s-df4ff191 step 4)

The page is for road and regulation testers. **TOOLS** is one dock of cards (Scenarios, Drive, Run, Cars, Traffic), folded like the DIALOG's sections.

**Scenarios** is the scenario catalog as a tree: Towns (CARLA's towns and the plain roads), OpenSCENARIO (CARLA ScenarioRunner), CommonRoad, Ours. Inside a source the cards are filed by the situation they exercise (their most specific tag), and a search filters them. One click shows the card in WORLD CARD: what it checks, its situations, how it stands, and its sites as run chips. A double click runs it, at its first site. A town's click shows the world's own card. The host serves the rows (`catalog` → world/catalog) and a card whole (`scard:NAME` → world/scard), road_host.catalog_tree / scenario_card.

**EVENTS** lists the run's events, newest first. A *mark* is a window you open and close: the top bar's button, or by voice "mark" … "end mark, WORDS". A *surprise* is a one-off event the page makes itself when the run's collisions or violations rise (a rise within 2 s of the last is the same one). With "stop on a surprise" ticked, the run pauses on it until you continue ("continue the run", the play button, or "continue"). Each event goes to the host as `mark:N:start|stop`, `mark:N:once:KIND` or `mark:N:move:K0:K1`. In the run's `marks.jsonl` it has its window in the trace's k (`at_k`), and the last start/stop pair is the window. The list is kept in the browser per trace.

The **dashboard** shows the last 6000 ticks, 10 minutes (`dash.js` WINDOW; the trace's ring keeps the same). The events are drawn on every chart: a mark as a band, a surprise as a red line. Click one to select it, and drag an ended mark's edge to move it. The axis holds still while the pointer is over the charts. An event's glyphs (in EVENTS, and at the dashboard's right for the selected one):

- **¶ narrate**: the road's own host tells the window in every member's rules' own `%%` words (`narrate:N:RUN:K0:K1` → world/narration, `world/road_narrate.py`, free), said in TALK.
- **? explain**: a question to the attached Claude Code (the surprise interface's `explain.request`); its answer comes back, said in TALK and kept on the event.
- **⇢ send**: the event to Metis: the service keeps the window of this page's own trace in the workspace and drops a surprise with your words, then tells the attached Claude Code. Its work comes back on the event: taken, ruled VERDICT, applied.

**Claude Code, through the surprise interface** (metis-plugin s-df4ff191, metis-agent `plugin/docs/SURPRISE-INTERFACE.md` v1.1): the page talks only to its own backend, the road service. The service is the `/metis-ui` client of a Claude Code session with the Metis plugin started in this workspace: it finds the plugin's lockfile (`.metis/ui/<pid>.json`, again after a plugin restart), says hello, and relays the plugin's signals to the page (`world/metis`). A sent event is WRITTEN by the service first (metis-agent `metis_agent/runtime/ui_client.py`, the generic UI-backend client: the window kept under the finding's key through `Workspace.drop_window`, one finding one surprise), then signalled (`surprise.new`); with no Claude Code attached it is still in the workspace and the page says so. Explain is a request the attached plugin answers; with none attached it is refused in words. EVENTS' header says `Claude: attached | not attached`. The page never holds the plugin's URL or token.

**The catalog changed: reload.** The road host watches the road's domains and the family they include (METIS_HOME) by content (not their cases or generated intent files). When Claude Code changes the catalog, the top bar says *the catalog changed (N files)* and offers **reload**: the service reloads every member from the changed sources (a failure keeps the old rules running and says why), then the host takes that state as the new base (`catalog:seen`). The bridge's feed says the same when it is on.

The pi LOOP dock that stood here (the loop console's chat in an iframe) is gone: Claude Code is the brain now, through the Metis plugin.

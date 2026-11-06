# road/catalog: the scenario catalog (scenario-catalog s-92e0b650; the card: road/docs/SCENARIO-CARD.md)

`<source>/<id>.yaml` is a card; `<source>/<id>/` beside it holds what it plays on (a stored net, the converter's data, `NOTICE`
with the source's license). The runner: `road/tools/scenario_run.py` (run / check / verdict / batch / index). The ten CARLA
cards are still in `road/scenarios/` (step 4 moves them here).

    road/tools/scenario_run.py check road/catalog road/scenarios      # every card against its verdict; exit 1 on a move
    road/tools/scenario_run.py verdict road/catalog/commonroad/X.yaml  # measure and write the card's verdict (since: worlds, catalog)

The first three CommonRoad cards are hand-made from the harvest's clusters (george, step 2): the run-end rule
(ZAM_Tjunction-1_310_T-1, pass), the interactive traffic SUMO drives (DEU_Frankfurt-74_11_I-1, fail: a contact), a start
inside a junction (USA_Lanker-1_2_I-1-1, world: the initial state is in contact).

## The CommonRoad set (2026-11-06)

192 cards under `commonroad/`: george's three hand-made ones and 189 imported by `road/tools/cr_import.py` from the FINAL harvest round (worlds 13b7dac / catalog ef793dc, panzer): one card per mechanism cluster of the triage plus a stratified sample over country and map type; stored net, trajectories and NOTICE per card; SUMO verdicts as measured (73 pass, 57 soft, 15 fail, 47 world); `set: regression` 73, `working` 116 (SCENARIO-CARD.md §6c). The exerciser cannot play a stored net: these cards run in the nightly only.

# trajplan vs ours over subset.txt at metis-worlds 739ce92 (planner cr-server c6f57bc), host pascal, 2026-11-16

metis-plugin s-df4ff191 step 5. The SAME behaviour level (the road family's command per beat, road_tree --world crnative over the lanelets' LaneMap); only the trajectory level differs:
- **ours** (the current path): reference.py + ocp.py (SB-2023's one-shot OCP over the remaining window, re-solved at a new command or every 1 s); no obstacle term.
- **trajplan**: perotheia-packages/planner's C++ trajplan::Planner via cr_plan_server (its lane plan over tools/cr_lanes.py's lane map, its IDM / stop / G2 gap floors against the recorded obstacles, its OCP 5 s at 0.1 s), re-planned every step.
Both on SB's vehicle; the oracle is cr_bench's (CommonRoad's checkers). ours@ea232a8 = the table of record from the planner-loop subject (other host); ours here re-run on pascal at 739ce92 reproduces every outcome of it. *: the two reactive-planner examples are not under $COMMONROAD_ROOT on pascal: run separately from the reactive planner's GitHub HEAD files (example_scenarios/, last changed 088e1e9; the pin 34ee3594 is not in the GitHub history), PLANNER_EXAMPLES.

**Summary (25):** ours goal 10, collision 7, offroad 2, window 6; trajplan goal 11, collision 7, offroad 1, window 6.

**Plan time per cycle (23 rows):** ours median 340 ms (max 5726); trajplan median 5.7 ms (max 11.3). Feasible (KS reconstruction): ours 17/23, trajplan 16/23.

| id | goal kind | ours@ea232a8 | ours | trajplan | ms ours | ms trajplan | feasible ours | feasible trajplan | note |
|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | region | window | window | window | 1909.7 | 4.8 | yes | yes |  |
| ZAM_Over-1_1 | — | collision | collision* | window* | 126.5 | 7.0 | yes | no (1/30 bad) |  |
| DEU_Test-1_1_T-1 | — | collision | collision* | collision* | 121.7 | 3.9 | yes | yes | stops behind the static blocker (the family never commands a change); rear-ended by recorded car 6 |
| USA_US101-2_1_T-1 | region | collision | collision | collision | 517.4 | 5.5 | yes | no (2/104 bad) |  |
| ITA_Siderno-4_5_T-1 | time-only | collision | collision | collision | 175.2 | 0.3 | yes | no (11/33 bad) |  |
| HRV_Pula-8_3_T-1 | time-only | collision | collision | collision | 1163.3 | 3.6 | yes | yes |  |
| BEL_Zwevegem-1_7_T-1 | time-only | goal | goal | goal | 186.6 | 2.0 | yes | yes |  |
| ZAM_Ramp-1_1-T-1 | region | offroad | offroad | offroad | 246.1 | 6.6 | yes | no (1/94 bad) |  |
| BEL_Putte-14_1_I-1-1 | time-only | goal | goal | goal | 2601.5 | 8.7 | no (1/33 bad) | no (1/33 bad) |  |
| USA_Lanker-2_24_T-1 | region | window | window | window | 669.9 | 2.5 | no (1/70 bad) | yes |  |
| DEU_B471-1_1_T-1 | region | window | window | window | 309.7 | 8.0 | yes | yes |  |
| ZAM_Urban-3_3 | region | window | window | window | 183.6 | 5.6 | yes | yes |  |
| ZAM_Zip-1_30_T-1 | region | window | window | window | 405.1 | 5.3 | yes | yes |  |
| DEU_Ibbenbueren-16_1_T-1 | time-only | goal | goal | collision | 3112.5 | 7.8 | no (2/33 bad) | no (1/33 bad) | rear-ended by recorded car 329 (13 m/s) while following a slow lead (IDM, ~4 m/s) |
| ARG_Carcarana-6_2_T-1 | time-only | collision | collision | goal | 259.2 | 6.3 | no (3/33 bad) | no (1/33 bad) | ours collides; trajplan keeps its floors |
| DEU_Backnang-3_4_T-1 | time-only | goal | goal | goal | 240.8 | 7.1 | yes | yes |  |
| USA_Lanker-1_3_T-1 | region | window | window | goal | 245.7 | 8.5 | yes | yes | reaches the region in the window |
| ESP_Toledo-11_4_T-1 | time-only | goal | goal | collision | 277.7 | 11.3 | yes | yes | rear-ended by recorded car 320 while G2 holds the start for crossing cars 338/342 |
| ITA_CarpiCentro-5_3_T-1 | time-only | collision | collision | collision | 1069.6 | 6.6 | no (1/33 bad) | yes |  |
| ESP_Cambre-5_3_I-1-1 | time-only | goal | goal | goal | 339.8 | 6.8 | yes | yes |  |
| ZAM_Tjunction-1_185_T-1 | region | goal | goal | goal | 417.5 | 5.7 | yes | yes |  |
| ZAM_Zip-1_11_T-1 | region | goal | goal | goal | 792.4 | 5.0 | yes | yes |  |
| USA_US101-3_5_T-1 | region | goal | goal | goal | 157.0 | 5.8 | yes | yes |  |
| USA_Lanker-2_26_T-1 | region | goal | goal | goal | 184.8 | 5.2 | yes | yes |  |
| DEU_Lohmar-33_1_T-1 | region | offroad | offroad | goal | 5725.9 | 4.8 | no (16/100 bad) | no (6/99 bad) | stays on the lanelets (ours: offroad) |

Other columns on this set (their tables): baseline (reactive) goal 11; sb2023 goal 15; sb2023-vlim goal 16; ours-parity goal 15 (SB's own reference into our Python OCP).

Reading: every trajplan collision is a REAR-END by recorded (non-reactive) traffic while the ego is slower than the recording (a G2 hold, a lead, a static blocker the family does not pass); the gains are a collision avoided (Carcarana), a window met (Lanker-1_3) and an offroad avoided (Lohmar). The behaviour level is unchanged: passing the DEU_Test blocker is the family's (a change / carry command), the planner executes it when asked.

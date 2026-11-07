# ours over subset.txt at metis-worlds ea232a8

25 scenarios: goal 10, collision 7, offroad 2, window 6.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. OUR planner: the road family's command per beat (road_tree --world crnative over the LaneMap from the scenario's lanelets, no SUMO) → the reference (reference.py: the lane the command names, the target speed, stops, the window-fitted arrival) → OUR OCP (ocp.py = SB's, parity proven), re-solved over the remaining window at a new command or every 1 s; the restrictor's cap clips the executed speed; SB's vehicle.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | window | region | recorded | no | no | no | yes | 14.7 | 1038.7 | 59 | 147 | 146–147 |  |
| ZAM_Over-1_1 | collision | region | none | no | yes | no | yes | 3.0 | 98.6 | 30 | 30 | 0–30 |  |
| DEU_Test-1_1_T-1 | collision | region | recorded | no | yes | no | yes | 4.0 | 93.4 | 32 | 40 | 35–40 |  |
| USA_US101-2_1_T-1 | collision | region | recorded | no | yes | no | yes | 10.4 | 286.7 | 37 | 104 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 99.5 | 33 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 612.6 | 8 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 103.3 | 23 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | offroad | region | recorded | yes | no | yes | yes | 9.5 | 137.0 | 10 | 95 | 0–100 |  |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 1326.3 | 5 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | window | region | recorded | no | no | no | no (1/70 bad) | 7.0 | 360.1 | 41 | 70 | 70–70 |  |
| DEU_B471-1_1_T-1 | window | region | recorded | no | no | no | yes | 5.0 | 167.9 | 41 | 50 | 0–50 |  |
| ZAM_Urban-3_3 | window | region | none | no | no | no | yes | 4.0 | 97.5 | 19 | 40 | 30–40 |  |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 230.5 | 17 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 1641.2 | 22 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | collision | time-only | recorded | yes | yes | no | no (3/33 bad) | 3.3 | 138.3 | 31 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 133.8 | 14 | 33 | 33–33 |  |
| USA_Lanker-1_3_T-1 | window | region | recorded | no | no | no | yes | 3.0 | 143.5 | 3 | 30 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 150.8 | 10 | 33 | 33–33 |  |
| ITA_CarpiCentro-5_3_T-1 | collision | time-only | recorded | yes | yes | no | no (1/33 bad) | 3.3 | 563.2 | 4 | 33 | 33–33 |  |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 194.8 | 6 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | goal | region | recorded | yes | no | no | yes | 14.6 | 240.8 | 25 | 146 | 146–147 |  |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 431.8 | 17 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | yes | 3.0 | 91.6 | 18 | 30 | 30–31 |  |
| USA_Lanker-2_26_T-1 | goal | region | recorded | yes | no | no | yes | 7.0 | 109.6 | 33 | 70 | 70–70 |  |
| DEU_Lohmar-33_1_T-1 | offroad | region | recorded | no | no | yes | no (16/100 bad) | 10.0 | 3931.9 | 54 | 100 | 99–100 |  |

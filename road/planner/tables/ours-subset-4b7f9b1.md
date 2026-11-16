# ours over subset.txt at metis-worlds 4b7f9b1

25 scenarios: goal 10, collision 7, offroad 2, window 6.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. OUR planner: the road family's command per beat (road_tree --world crnative over the LaneMap from the scenario's lanelets, no SUMO) → the reference (reference.py: the lane the command names, the target speed, stops, the window-fitted arrival) → OUR OCP (ocp.py = SB's, parity proven), re-solved over the remaining window at a new command or every 1 s; the restrictor's cap clips the executed speed; SB's vehicle.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | window | region | recorded | no | no | no | yes | 14.7 | 1789.5 | 59 | 147 | 146–147 |  |
| ZAM_Over-1_1 | collision | region | none | no | yes | no | yes | 3.0 | 166.7 | 30 | 30 | 0–30 |  |
| DEU_Test-1_1_T-1 | collision | region | recorded | no | yes | no | yes | 4.0 | 155.8 | 32 | 40 | 35–40 |  |
| USA_US101-2_1_T-1 | collision | region | recorded | no | yes | no | yes | 10.4 | 498.9 | 37 | 104 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 165.4 | 33 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 1083.1 | 8 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 182.5 | 23 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | offroad | region | recorded | yes | no | yes | yes | 9.5 | 229.8 | 10 | 95 | 0–100 |  |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 2374.7 | 5 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | window | region | recorded | no | no | no | no (1/70 bad) | 7.0 | 601.3 | 41 | 70 | 70–70 |  |
| DEU_B471-1_1_T-1 | window | region | recorded | no | no | no | yes | 5.0 | 269.3 | 41 | 50 | 0–50 |  |
| ZAM_Urban-3_3 | window | region | none | no | no | no | yes | 4.0 | 162.1 | 19 | 40 | 30–40 |  |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 382.7 | 17 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 2965.8 | 22 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | collision | time-only | recorded | yes | yes | no | no (3/33 bad) | 3.3 | 239.4 | 31 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 242.9 | 14 | 33 | 33–33 |  |
| USA_Lanker-1_3_T-1 | window | region | recorded | no | no | no | yes | 3.0 | 284.1 | 3 | 30 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 265.9 | 10 | 33 | 33–33 |  |
| ITA_CarpiCentro-5_3_T-1 | collision | time-only | recorded | yes | yes | no | no (1/33 bad) | 3.3 | 982.3 | 4 | 33 | 33–33 |  |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 349.3 | 6 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | goal | region | recorded | yes | no | no | yes | 14.6 | 422.0 | 25 | 146 | 146–147 |  |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 735.7 | 17 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | yes | 3.0 | 175.0 | 18 | 30 | 30–31 |  |
| USA_Lanker-2_26_T-1 | goal | region | recorded | yes | no | no | yes | 7.0 | 202.6 | 33 | 70 | 70–70 |  |
| DEU_Lohmar-33_1_T-1 | offroad | region | recorded | no | no | yes | no (16/100 bad) | 10.0 | 6491.1 | 54 | 100 | 99–100 |  |

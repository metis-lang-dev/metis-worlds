# sb2023 over subset.txt at metis-worlds 06b50cb

25 scenarios: goal 15, offroad 2, infeasible 6, window 2.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. SB-2023 @ 5434d05 as its main.py calls it: its own decision module (desired_velocity='init'), the Optimization planner at its defaults, ONE SHOT over the goal window, collision_avoidance off; ms/cycle = decision + low level; the solution's vehicle FORD_ESCORT (the nearest CommonRoad type to SB's 4.3 x 1.7 m, wheelbase 2.3). KS feasibility as measured; footnote: no steering-rate bound, zero input weights.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | goal | region | recorded | yes | no | no | no (8/146 bad) | 14.6 | 3240.0 | 1 | 146 | 146–147 |  |
| ZAM_Over-1_1 | infeasible | region | none | — | — | — | — | — | 28.0 | 1 | -1 | 0–30 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| DEU_Test-1_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 474.0 | 1 | -1 | 35–40 | SB decision raised Exception: Reference trajectory generation failed! (highLevelPlanner.py:2674 correct_orientation) |
| USA_US101-2_1_T-1 | window | region | recorded | no | no | no | no (10/100 bad) | 10.0 | 8820.0 | 1 | 100 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (6/33 bad) | 3.3 | 379.0 | 1 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | offroad | time-only | recorded | yes | no | yes | no (11/33 bad) | 3.3 | 719.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 301.0 | 1 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | infeasible | region | recorded | — | — | — | — | — | 52.0 | 1 | -1 | 0–100 | SB decision raised Exception: Goal set is not reachable! (highLevelPlanner.py:443 velocity_profile) |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 410.0 | 1 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | offroad | region | recorded | no | no | yes | no (22/70 bad) | 7.0 | 3521.0 | 1 | 70 | 70–70 |  |
| DEU_B471-1_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 21.0 | 1 | -1 | 0–50 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| ZAM_Urban-3_3 | infeasible | region | none | — | — | — | — | — | 56.0 | 1 | -1 | 30–40 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | no (5/85 bad) | 8.5 | 2777.0 | 1 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 796.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 573.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 484.0 | 1 | 33 | 33–33 |  |
| USA_Lanker-1_3_T-1 | goal | region | recorded | yes | no | no | no (3/30 bad) | 3.0 | 797.0 | 1 | 30 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 328.0 | 1 | 33 | 33–33 |  |
| ITA_CarpiCentro-5_3_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 346.0 | 1 | 33 | 33–33 |  |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 495.0 | 1 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | goal | region | recorded | yes | no | no | no (8/146 bad) | 14.6 | 3005.0 | 1 | 146 | 146–147 |  |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 383.0 | 1 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | no (1/31 bad) | 3.1 | 312.0 | 1 | 31 | 30–31 |  |
| USA_Lanker-2_26_T-1 | goal | region | recorded | yes | no | no | yes | 7.0 | 1445.0 | 1 | 70 | 70–70 |  |
| DEU_Lohmar-33_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 33274.0 | 1 | -1 | 99–100 | SB low_level: IPOPT Maximum_Iterations_Exceeded |

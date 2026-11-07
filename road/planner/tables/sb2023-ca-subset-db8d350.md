# sb2023-ca over subset.txt at metis-worlds db8d350

25 scenarios: goal 9, infeasible 13, window 3.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. SB-2023 @ 5434d05 as its main.py calls it: its own decision module (desired_velocity='init'), the Optimization planner at its defaults, ONE SHOT over the goal window, collision_avoidance ON (the one flag); ms/cycle = decision + low level; the solution's vehicle FORD_ESCORT (the nearest CommonRoad type to SB's 4.3 x 1.7 m, wheelbase 2.3). Its OCP has no steering-rate bound and zero input weights: the KS check rejects the chatter.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | infeasible | region | recorded | — | — | — | — | — | 7663.0 | 1 | -1 | 146–147 | SB low_level: IPOPT Infeasible_Problem_Detected |
| ZAM_Over-1_1 | infeasible | region | none | — | — | — | — | — | 29.0 | 1 | -1 | 0–30 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| DEU_Test-1_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 462.0 | 1 | -1 | 35–40 | SB decision raised Exception: Reference trajectory generation failed! (highLevelPlanner.py:2674 correct_orientation) |
| USA_US101-2_1_T-1 | window | region | recorded | no | no | no | no (15/100 bad) | 10.0 | 13909.0 | 1 | 100 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 1495.0 | 1 | -1 | 33–33 | SB low_level: IPOPT Infeasible_Problem_Detected |
| HRV_Pula-8_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 1153.0 | 1 | -1 | 33–33 | SB low_level: IPOPT Infeasible_Problem_Detected |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 411.0 | 1 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | infeasible | region | recorded | — | — | — | — | — | 54.0 | 1 | -1 | 0–100 | SB decision raised Exception: Goal set is not reachable! (highLevelPlanner.py:443 velocity_profile) |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 1021.0 | 1 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | infeasible | region | recorded | — | — | — | — | — | 11350.0 | 1 | -1 | 70–70 | SB low_level: IPOPT Infeasible_Problem_Detected |
| DEU_B471-1_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 22.0 | 1 | -1 | 0–50 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| ZAM_Urban-3_3 | infeasible | region | none | — | — | — | — | — | 58.0 | 1 | -1 | 30–40 | SB decision raised Exception: Failed to find a feasible solution! (highLevelPlanner.py:1304 best_lanelet_sequence) |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | no (6/85 bad) | 8.5 | 1370.0 | 1 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 944.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 1538.0 | 1 | -1 | 33–33 | SB low_level: IPOPT Infeasible_Problem_Detected |
| DEU_Backnang-3_4_T-1 | goal | time-only | recorded | yes | no | no | no (22/33 bad) | 3.3 | 527.0 | 1 | 33 | 33–33 |  |
| USA_Lanker-1_3_T-1 | window | region | recorded | no | no | no | no (2/30 bad) | 3.0 | 958.0 | 1 | 30 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 506.0 | 1 | 33 | 33–33 |  |
| ITA_CarpiCentro-5_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 3562.0 | 1 | -1 | 33–33 | SB low_level: IPOPT Infeasible_Problem_Detected |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 628.0 | 1 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | infeasible | region | recorded | — | — | — | — | — | 47669.0 | 1 | -1 | 146–147 | SB low_level: IPOPT Infeasible_Problem_Detected |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 523.0 | 1 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | no (1/31 bad) | 3.1 | 488.0 | 1 | 31 | 30–31 |  |
| USA_Lanker-2_26_T-1 | goal | region | recorded | yes | no | no | no (1/70 bad) | 7.0 | 1528.0 | 1 | 70 | 70–70 |  |
| DEU_Lohmar-33_1_T-1 | infeasible | region | recorded | — | — | — | — | — | 7224.0 | 1 | -1 | 99–100 | SB low_level: IPOPT Infeasible_Problem_Detected |

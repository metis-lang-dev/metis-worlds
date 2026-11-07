# reactive over subset.txt at metis-worlds ae83b2a

25 scenarios: goal 11, offroad 1, infeasible 7, window 6.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. The reference path: the package's create_initial_ref_path (route planner's shortest route), extended 20 m back and 150 m past its end, smoothed by create_coordinate_system; the feasibility count depends on it (the 20 m back extension moved DEU_BadEssen-1_3_T-1 from 17 to 1 bad transitions).

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | goal | region | recorded | yes | no | no | no (16/146 bad) | 14.6 | 107.3 | 49 | 146 | 146–147 |  |
| ZAM_Over-1_1 | window | region | none | no | no | no | yes | 3.0 | 392.7 | 10 | 30 | 0–30 |  |
| DEU_Test-1_1_T-1 | window | region | recorded | no | no | no | yes | 4.0 | 120.2 | 14 | 40 | 35–40 |  |
| USA_US101-2_1_T-1 | window | region | recorded | no | no | no | yes | 10.4 | 134.5 | 35 | 104 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 74.9 | 11 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 328.3 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 80.7 | 11 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | offroad | region | recorded | yes | no | yes | yes | 4.7 | 117.4 | 16 | 47 | 0–100 |  |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 126.7 | 11 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | infeasible | region | recorded | no | no | no | no (1/39 bad) | 3.9 | 76.9 | 14 | 39 | 70–70 | no feasible sample at step 39 (cycle 14): 0 of 360 kinematic [kappa_dot 248, kappa 33, yaw_rate 18], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_B471-1_1_T-1 | window | region | recorded | no | no | no | yes | 5.0 | 144.6 | 17 | 50 | 0–50 |  |
| ZAM_Urban-3_3 | window | region | none | no | no | no | yes | 4.0 | 114.0 | 14 | 40 | 30–40 |  |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 114.6 | 29 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 165.5 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | goal | time-only | recorded | yes | no | no | no (17/33 bad) | 3.3 | 137.5 | 11 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 6206.8 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7266 of 8874 kinematic [kappa_dot 6777, kappa 328, acceleration 126, yaw_rate 35], 1608 collision |
| USA_Lanker-1_3_T-1 | goal | region | recorded | yes | no | no | yes | 3.3 | 121.1 | 11 | 33 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | infeasible | time-only | recorded | no | no | no | no (1/6 bad) | 0.6 | 3800.3 | 3 | 6 | 33–33 | no feasible sample at step 6 (cycle 3): 6239 of 8874 kinematic [kappa_dot 4884, kappa 1191, yaw_rate 164], 2635 collision |
| ITA_CarpiCentro-5_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 17423.0 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 2958 of 8874 kinematic [kappa_dot 2560, acceleration 398], 5916 collision |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.0 | 11 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | infeasible | region | recorded | no | no | no | no (8/141 bad) | 14.1 | 129.5 | 48 | 141 | 146–147 | no feasible sample at step 141 (cycle 48): 8874 of 8874 kinematic [kappa_dot 7817, kappa 895, yaw_rate 90, acceleration 72], 0 collision |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 110.5 | 28 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | yes | 3.0 | 105.6 | 10 | 30 | 30–31 |  |
| USA_Lanker-2_26_T-1 | infeasible | region | recorded | no | no | no | yes | 2.7 | 562.5 | 10 | 27 | 70–70 | no feasible sample at step 27 (cycle 10): 8874 of 8874 kinematic [kappa_dot 7805, kappa 912, yaw_rate 121, acceleration 36], 0 collision |
| DEU_Lohmar-33_1_T-1 | infeasible | region | recorded | no | no | no | yes | 3.0 | 1156.9 | 11 | 30 | 99–100 | no feasible sample at step 30 (cycle 11): 8874 of 8874 kinematic [kappa 8838, acceleration 36], 0 collision |

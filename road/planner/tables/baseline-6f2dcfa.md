# reactive planner baseline over subset.txt at metis-worlds 6f2dcfa

25 scenarios: goal 14, offroad 1, infeasible 4, window 6.

| id | outcome | goal | collision | offroad | feasible | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | goal | yes | no | no | no (16/146 bad) | 14.6 | 100.1 | 49 | 146 | 146–147 |  |
| ZAM_Over-1_1 | window | no | no | no | yes | 3.0 | 377.7 | 10 | 30 | 0–30 |  |
| DEU_Test-1_1_T-1 | window | no | no | no | yes | 4.0 | 112.6 | 14 | 40 | 35–40 |  |
| USA_US101-2_1_T-1 | window | no | no | no | yes | 10.4 | 127.7 | 35 | 104 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | goal | yes | no | no | no (1/33 bad) | 3.3 | 73.9 | 11 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | goal | yes | no | no | yes | 3.3 | 403.7 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | yes | no | no | yes | 3.3 | 78.8 | 11 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | offroad | yes | no | yes | yes | 4.7 | 116.6 | 16 | 47 | 0–100 |  |
| BEL_Putte-14_1_I-1-1 | goal | yes | no | no | yes | 3.3 | 117.1 | 11 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | infeasible | no | no | no | no (1/39 bad) | 3.9 | 74.1 | 14 | 39 | 70–70 | no feasible sample at step 39 (cycle 14): 0 of 360 kinematic [kappa_dot 248, kappa 33, yaw_rate 18], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_B471-1_1_T-1 | window | no | no | no | yes | 5.0 | 138.0 | 17 | 50 | 0–50 |  |
| ZAM_Urban-3_3 | window | no | no | no | yes | 4.0 | 107.5 | 14 | 40 | 30–40 |  |
| ZAM_Zip-1_30_T-1 | window | no | no | no | yes | 8.5 | 110.3 | 29 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | goal | yes | no | no | no (1/33 bad) | 3.3 | 154.9 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | goal | yes | no | no | no (17/33 bad) | 3.3 | 127.7 | 11 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | infeasible | — | — | — | — | — | 5923.4 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7266 of 8874 kinematic [kappa_dot 6777, kappa 328, acceleration 126, yaw_rate 35], 1608 collision |
| USA_Lanker-1_3_T-1 | goal | yes | no | no | yes | 3.3 | 118.6 | 11 | 33 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | infeasible | no | no | no | no (1/6 bad) | 0.6 | 3728.8 | 3 | 6 | 33–33 | no feasible sample at step 6 (cycle 3): 6239 of 8874 kinematic [kappa_dot 4884, kappa 1191, yaw_rate 164], 2635 collision |
| ITA_CarpiCentro-5_3_T-1 | infeasible | — | — | — | — | — | 17506.9 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 2958 of 8874 kinematic [kappa_dot 2560, acceleration 398], 5916 collision |
| ESP_Cambre-5_3_I-1-1 | goal | yes | no | no | yes | 3.3 | 117.4 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-3_2_T-1 | goal | yes | no | no | yes | 3.3 | 257.9 | 11 | 33 | 33–33 |  |
| BEL_Wervik-4_1_T-1 | goal | yes | no | no | no (11/33 bad) | 3.3 | 248.3 | 11 | 33 | 33–33 |  |
| DEU_BadEssen-1_3_T-1 | goal | yes | no | no | no (1/33 bad) | 3.3 | 118.1 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-14_1_T-1 | goal | yes | no | no | no (17/33 bad) | 3.3 | 104.5 | 11 | 33 | 33–33 |  |
| DEU_Meckenheim-3_1_T-1 | goal | yes | no | no | yes | 3.3 | 119.2 | 11 | 33 | 33–33 |  |

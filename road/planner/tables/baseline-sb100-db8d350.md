# reactive over sb100.txt at metis-worlds db8d350

100 scenarios: goal 73, infeasible 20, window 3, error 4.
Goal kinds: region 14, time-only 85, — 1; traffic: recorded 99, — 1. The planner is deterministic: one run per row. The reference path: the package's create_initial_ref_path (route planner's shortest route), extended 20 m back and 150 m past its end, smoothed by create_coordinate_system; the feasibility count depends on it (the 20 m back extension moved DEU_BadEssen-1_3_T-1 from 17 to 1 bad transitions).

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARG_Carcarana-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 88.1 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-3_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 137.9 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-5_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 405.3 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-11_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 80.0 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 117.5 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 595.8 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 8464, acceleration 216, kappa 166, yaw_rate 28], 0 collision |
| BEL_Aarschot-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 79.2 | 11 | 33 | 33–33 |  |
| BEL_Beringen-1_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 11991.7 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 5525 of 8874 kinematic [kappa_dot 4394, kappa 982, yaw_rate 131, acceleration 18], 3349 collision |
| BEL_Nivelles-10_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 73.7 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 126.4 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.3 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-19_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 3356.5 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7561 of 8874 kinematic [kappa_dot 6580, kappa 800, yaw_rate 127, acceleration 54], 1313 collision |
| BEL_Nivelles-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 36, acceleration 26], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| BEL_Nivelles-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 124.3 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-9_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 84.5 | 11 | 33 | 33–33 |  |
| BEL_Putte-10_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 573.9 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8866 of 8874 kinematic [kappa_dot 8459, acceleration 407], 8 collision |
| BEL_Putte-11_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 68.5 | 11 | 33 | 33–33 |  |
| BEL_Putte-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 177.7 | 11 | 33 | 33–33 |  |
| BEL_Putte-3_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 77.7 | 11 | 33 | 33–33 |  |
| BEL_Putte-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 195.4 | 11 | 33 | 33–33 |  |
| BEL_Putte-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 125.1 | 11 | 33 | 33–33 |  |
| BEL_Wervik-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 108.8 | 11 | 33 | 33–33 |  |
| BEL_Zaventem-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 717.5 | 11 | 33 | 33–33 |  |
| BEL_Zaventem-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 658.3 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 7858, kappa 860, yaw_rate 120, acceleration 36], 0 collision |
| BEL_Zaventem-4_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 94, acceleration 18, yaw_rate 6, kappa 4], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| BEL_Zaventem-5_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 132.6 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 673.4 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 7815, kappa 907, yaw_rate 116, acceleration 36], 0 collision |
| BEL_Zwevegem-3_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 111.5 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (13/33 bad) | 3.3 | 104.4 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-8_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 81.1 | 11 | 33 | 33–33 |  |
| DEU_Backnang-1_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 67808.0 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 2393 of 8874 kinematic [kappa_dot 1995, acceleration 398], 6481 collision |
| DEU_Backnang-4_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 124.4 | 11 | 33 | 33–33 |  |
| DEU_Backnang-5_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 174, kappa 49, yaw_rate 8, acceleration 1], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_Backnang-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 897.4 | 11 | 33 | 33–33 |  |
| DEU_Backnang-9_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 111.7 | 11 | 33 | 33–33 |  |
| DEU_BadEssen-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 60.7 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 86.7 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 77.3 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 102.7 | 11 | 33 | 33–33 |  |
| DEU_Bilderstoeckchen-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 86, acceleration 12, kappa 8, yaw_rate 3], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_Flensburg-10_1_T-1 | window | region | recorded | no | no | no | no (14/100 bad) | 10.0 | 151.5 | 34 | 100 | 99–100 |  |
| DEU_Flensburg-14_1_T-1 | infeasible | region | recorded | no | no | no | yes | 7.2 | 177.2 | 25 | 72 | 99–100 | no feasible sample at step 72 (cycle 25): 8858 of 8874 kinematic [kappa_dot 8408, acceleration 450], 16 collision |
| DEU_Guetersloh-10_5_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 9680.8 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7182 of 8874 kinematic [kappa_dot 5401, kappa 1613, yaw_rate 114, acceleration 54], 1692 collision |
| DEU_Guetersloh-11_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 186.6 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-12_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 102.2 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-14_2_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 136.4 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-15_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 763.6 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-16_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 0 kinematic [], 0 collision; raised Exception: Initial state or reference incorrect! Curvilinear velocity is negativ |
| DEU_Guetersloh-17_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 94.4 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.3 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 123.2 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-6_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 90.4 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-7_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 12072.7 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7309 of 8874 kinematic [kappa_dot 5459, kappa 1702, yaw_rate 92, acceleration 56], 1565 collision |
| DEU_Guetersloh-8_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 78.0 | 11 | 33 | 33–33 |  |
| DEU_Hennigsdorf-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 121.7 | 11 | 33 | 33–33 |  |
| DEU_Ibbenbueren-2_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 106.4 | 11 | 33 | 33–33 |  |
| DEU_Moelln-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (12/33 bad) | 3.3 | 102.5 | 11 | 33 | 33–33 |  |
| DEU_Muehlhausen-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 127.0 | 11 | 33 | 33–33 |  |
| DEU_Rheinbach-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 123.9 | 11 | 33 | 33–33 |  |
| DEU_Speyer-2_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 309.8 | 11 | 33 | 33–33 |  |
| ESP_Almansa-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 115.8 | 11 | 33 | 33–33 |  |
| ESP_Ceuta-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 95.3 | 11 | 33 | 33–33 |  |
| ESP_Inca-7_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.2 | 11 | 33 | 33–33 |  |
| ESP_Monzon-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 175.0 | 11 | 33 | 33–33 |  |
| ESP_Monzon-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 1345.2 | 11 | 33 | 33–33 |  |
| ESP_Monzon-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 105.6 | 11 | 33 | 33–33 |  |
| ESP_Monzon-9_1_T-1 | error | time-only | recorded | — | — | — | — | — | — | 0 | 0 | 33–33 | AssertionError: Reference path orientations should be in [-2pi, 2pi] |
| ESP_PriegodeCordoba-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 18000.1 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 6275 of 8874 kinematic [kappa_dot 5143, kappa 951, yaw_rate 162, acceleration 19], 2599 collision |
| FRA_Sete-1_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 373.1 | 11 | 33 | 33–33 |  |
| GRC_Perama-3_2_T-1 | error | time-only | recorded | — | — | — | — | — | — | 0 | 0 | 33–33 | AssertionError: Reference path orientations should be in [-2pi, 2pi] |
| HRV_Pula-19_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 122.3 | 11 | 33 | 33–33 |  |
| HRV_Pula-5_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 84, acceleration 12, kappa 6], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| ITA_CarpiCentro-1_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 84.9 | 11 | 33 | 33–33 |  |
| ITA_Empoli-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 124.8 | 11 | 33 | 33–33 |  |
| ITA_SanGiorgioaCremano-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 97.8 | 11 | 33 | 33–33 |  |
| ITA_Segrate-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (16/33 bad) | 3.3 | 224.4 | 11 | 33 | 33–33 |  |
| ITA_Siderno-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 117.3 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 90.2 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 144, kappa 35, yaw_rate 13, acceleration 6], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| PRI_Barceloneta-4_3_T-1 | goal | time-only | recorded | yes | no | no | no (14/33 bad) | 3.3 | 132.3 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 735.9 | 11 | 33 | 33–33 |  |
| RUS_Bicycle-10_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 117.6 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-12_1_T-1 | error | region | recorded | — | — | — | — | — | — | 0 | 0 | 20–31 | ValueError: Planner <commonroad_route_planner.planners.networkx.NetworkxRoutePlanner object at 0x765ed761f6d0> could not |
| RUS_Bicycle-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 127.8 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-2_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 116.9 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-5_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 124.8 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-8_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 126.8 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-9_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 126.3 | 7 | 20 | 20–31 |  |
| USA_Lanker-1_8_T-1 | infeasible | region | recorded | no | no | no | no (2/6 bad) | 0.6 | 300.1 | 3 | 6 | 11–15 | no feasible sample at step 6 (cycle 3): 8874 of 8874 kinematic [kappa_dot 7476, kappa 1233, yaw_rate 111, acceleration 54], 0 collision |
| USA_US101-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 128.6 | 27 | 80 | 80–80 |  |
| USA_US101-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 129.0 | 27 | 80 | 80–80 |  |
| USA_US101-20_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 137.0 | 27 | 80 | 80–80 |  |
| USA_US101-26_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 132.4 | 27 | 80 | 80–80 |  |
| USA_US101-6_2_T-1 | window | region | recorded | no | no | no | yes | 3.1 | 126.9 | 11 | 31 | 30–31 |  |
| USA_US101-8_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 7.5 | 124.1 | 25 | 75 | 75–75 |  |
| ZAM_ACC-1_2_S-1 | goal | time-only | recorded | yes | no | no | yes | 2.9 | 120.3 | 10 | 29 | 29–30 |  |
| ZAM_HW-1_1_S-1 | error | — | — | — | — | — | — | — | — | 0 | 0 | — | exit -11, no row (see run.log) |
| ZAM_Tjunction-1_238_T-1 | infeasible | region | recorded | no | no | no | no (12/141 bad) | 14.1 | 123.5 | 48 | 141 | 146–147 | no feasible sample at step 141 (cycle 48): 8874 of 8874 kinematic [kappa_dot 7805, kappa 906, yaw_rate 91, acceleration 72], 0 collision |
| ZAM_Tutorial-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 3.5 | 109.3 | 12 | 35 | 35–40 |  |
| ZAM_Zip-1_19_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 117.3 | 29 | 85 | 84–85 |  |

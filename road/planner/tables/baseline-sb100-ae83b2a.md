# reactive over sb100.txt at metis-worlds ae83b2a

100 scenarios: goal 73, infeasible 20, window 3, error 4.
Goal kinds: region 14, time-only 85, — 1; traffic: recorded 99, — 1. The planner is deterministic: one run per row. The reference path: the package's create_initial_ref_path (route planner's shortest route), extended 20 m back and 150 m past its end, smoothed by create_coordinate_system; the feasibility count depends on it (the 20 m back extension moved DEU_BadEssen-1_3_T-1 from 17 to 1 bad transitions).

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARG_Carcarana-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 88.7 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-3_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 135.2 | 11 | 33 | 33–33 |  |
| ARG_Carcarana-5_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 399.6 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-11_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 82.2 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 117.5 | 11 | 33 | 33–33 |  |
| BEL_Aarschot-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 578.4 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 8464, acceleration 216, kappa 166, yaw_rate 28], 0 collision |
| BEL_Aarschot-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 77.9 | 11 | 33 | 33–33 |  |
| BEL_Beringen-1_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 11977.9 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 5525 of 8874 kinematic [kappa_dot 4394, kappa 982, yaw_rate 131, acceleration 18], 3349 collision |
| BEL_Nivelles-10_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 74.2 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 125.8 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 118.3 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-19_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 3364.5 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7561 of 8874 kinematic [kappa_dot 6580, kappa 800, yaw_rate 127, acceleration 54], 1313 collision |
| BEL_Nivelles-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 36, acceleration 26], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| BEL_Nivelles-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 122.7 | 11 | 33 | 33–33 |  |
| BEL_Nivelles-9_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 82.8 | 11 | 33 | 33–33 |  |
| BEL_Putte-10_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 574.0 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8866 of 8874 kinematic [kappa_dot 8459, acceleration 407], 8 collision |
| BEL_Putte-11_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 66.0 | 11 | 33 | 33–33 |  |
| BEL_Putte-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 176.8 | 11 | 33 | 33–33 |  |
| BEL_Putte-3_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 79.1 | 11 | 33 | 33–33 |  |
| BEL_Putte-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 197.0 | 11 | 33 | 33–33 |  |
| BEL_Putte-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 127.5 | 11 | 33 | 33–33 |  |
| BEL_Wervik-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 114.8 | 11 | 33 | 33–33 |  |
| BEL_Zaventem-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 720.5 | 11 | 33 | 33–33 |  |
| BEL_Zaventem-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 671.8 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 7858, kappa 860, yaw_rate 120, acceleration 36], 0 collision |
| BEL_Zaventem-4_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 94, acceleration 18, yaw_rate 6, kappa 4], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| BEL_Zaventem-5_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 124.8 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 647.4 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 8874 of 8874 kinematic [kappa_dot 7815, kappa 907, yaw_rate 116, acceleration 36], 0 collision |
| BEL_Zwevegem-3_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 115.6 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (13/33 bad) | 3.3 | 106.3 | 11 | 33 | 33–33 |  |
| BEL_Zwevegem-8_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 83.0 | 11 | 33 | 33–33 |  |
| DEU_Backnang-1_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 69693.0 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 2393 of 8874 kinematic [kappa_dot 1995, acceleration 398], 6481 collision |
| DEU_Backnang-4_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.9 | 11 | 33 | 33–33 |  |
| DEU_Backnang-5_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 174, kappa 49, yaw_rate 8, acceleration 1], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_Backnang-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 889.2 | 11 | 33 | 33–33 |  |
| DEU_Backnang-9_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 114.9 | 11 | 33 | 33–33 |  |
| DEU_BadEssen-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 59.9 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 88.5 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 75.3 | 11 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 103.1 | 11 | 33 | 33–33 |  |
| DEU_Bilderstoeckchen-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 86, acceleration 12, kappa 8, yaw_rate 3], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| DEU_Flensburg-10_1_T-1 | window | region | recorded | no | no | no | no (14/100 bad) | 10.0 | 153.8 | 34 | 100 | 99–100 |  |
| DEU_Flensburg-14_1_T-1 | infeasible | region | recorded | no | no | no | yes | 7.2 | 173.8 | 25 | 72 | 99–100 | no feasible sample at step 72 (cycle 25): 8858 of 8874 kinematic [kappa_dot 8408, acceleration 450], 16 collision |
| DEU_Guetersloh-10_5_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 9442.0 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7182 of 8874 kinematic [kappa_dot 5401, kappa 1613, yaw_rate 114, acceleration 54], 1692 collision |
| DEU_Guetersloh-11_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 185.8 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-12_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 103.5 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-14_2_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 136.4 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-15_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 765.1 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-16_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 0 kinematic [], 0 collision; raised Exception: Initial state or reference incorrect! Curvilinear velocity is negativ |
| DEU_Guetersloh-17_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 94.1 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 121.3 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 122.8 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-6_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 87.5 | 11 | 33 | 33–33 |  |
| DEU_Guetersloh-7_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 12220.2 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 7309 of 8874 kinematic [kappa_dot 5459, kappa 1702, yaw_rate 92, acceleration 56], 1565 collision |
| DEU_Guetersloh-8_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 76.4 | 11 | 33 | 33–33 |  |
| DEU_Hennigsdorf-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 117.8 | 11 | 33 | 33–33 |  |
| DEU_Ibbenbueren-2_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 106.6 | 11 | 33 | 33–33 |  |
| DEU_Moelln-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (12/33 bad) | 3.3 | 99.4 | 11 | 33 | 33–33 |  |
| DEU_Muehlhausen-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 118.2 | 11 | 33 | 33–33 |  |
| DEU_Rheinbach-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 118.5 | 11 | 33 | 33–33 |  |
| DEU_Speyer-2_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 315.4 | 11 | 33 | 33–33 |  |
| ESP_Almansa-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 105.6 | 11 | 33 | 33–33 |  |
| ESP_Ceuta-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 96.5 | 11 | 33 | 33–33 |  |
| ESP_Inca-7_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 119.2 | 11 | 33 | 33–33 |  |
| ESP_Monzon-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 164.9 | 11 | 33 | 33–33 |  |
| ESP_Monzon-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 1339.2 | 11 | 33 | 33–33 |  |
| ESP_Monzon-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 105.2 | 11 | 33 | 33–33 |  |
| ESP_Monzon-9_1_T-1 | error | time-only | recorded | — | — | — | — | — | — | 0 | 0 | 33–33 | AssertionError: Reference path orientations should be in [-2pi, 2pi] |
| ESP_PriegodeCordoba-2_3_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 17771.4 | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 6275 of 8874 kinematic [kappa_dot 5143, kappa 951, yaw_rate 162, acceleration 19], 2599 collision |
| FRA_Sete-1_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 376.1 | 11 | 33 | 33–33 |  |
| GRC_Perama-3_2_T-1 | error | time-only | recorded | — | — | — | — | — | — | 0 | 0 | 33–33 | AssertionError: Reference path orientations should be in [-2pi, 2pi] |
| HRV_Pula-19_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 122.3 | 11 | 33 | 33–33 |  |
| HRV_Pula-5_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 84, acceleration 12, kappa 6], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| ITA_CarpiCentro-1_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 85.6 | 11 | 33 | 33–33 |  |
| ITA_Empoli-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 124.8 | 11 | 33 | 33–33 |  |
| ITA_SanGiorgioaCremano-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 95.8 | 11 | 33 | 33–33 |  |
| ITA_Segrate-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (16/33 bad) | 3.3 | 226.5 | 11 | 33 | 33–33 |  |
| ITA_Siderno-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 117.3 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 89.3 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-3_1_T-1 | infeasible | time-only | recorded | — | — | — | — | — | — | 1 | 0 | 33–33 | no feasible sample at step 0 (cycle 1): 0 of 360 kinematic [kappa_dot 144, kappa 35, yaw_rate 13, acceleration 6], 0 collision; raised CurvilinearProjectionDomainLateralError: Lateral coordinate outside of curviline |
| PRI_Barceloneta-4_3_T-1 | goal | time-only | recorded | yes | no | no | no (14/33 bad) | 3.3 | 134.2 | 11 | 33 | 33–33 |  |
| PRI_Barceloneta-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 735.2 | 11 | 33 | 33–33 |  |
| RUS_Bicycle-10_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 115.7 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-12_1_T-1 | error | region | recorded | — | — | — | — | — | — | 0 | 0 | 20–31 | ValueError: Planner <commonroad_route_planner.planners.networkx.NetworkxRoutePlanner object at 0x789f01bf9c10> could not |
| RUS_Bicycle-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 121.6 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-2_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 111.2 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-5_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 122.3 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-8_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 121.3 | 7 | 20 | 20–31 |  |
| RUS_Bicycle-9_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 122.0 | 7 | 20 | 20–31 |  |
| USA_Lanker-1_8_T-1 | infeasible | region | recorded | no | no | no | no (2/6 bad) | 0.6 | 313.9 | 3 | 6 | 11–15 | no feasible sample at step 6 (cycle 3): 8874 of 8874 kinematic [kappa_dot 7476, kappa 1233, yaw_rate 111, acceleration 54], 0 collision |
| USA_US101-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 131.2 | 27 | 80 | 80–80 |  |
| USA_US101-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 133.2 | 27 | 80 | 80–80 |  |
| USA_US101-20_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 127.5 | 27 | 80 | 80–80 |  |
| USA_US101-26_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 126.4 | 27 | 80 | 80–80 |  |
| USA_US101-6_2_T-1 | window | region | recorded | no | no | no | yes | 3.1 | 126.5 | 11 | 31 | 30–31 |  |
| USA_US101-8_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 7.5 | 129.9 | 25 | 75 | 75–75 |  |
| ZAM_ACC-1_2_S-1 | goal | time-only | recorded | yes | no | no | yes | 2.9 | 125.7 | 10 | 29 | 29–30 |  |
| ZAM_HW-1_1_S-1 | error:world | — | — | — | — | — | — | — | — | 0 | 0 | — | world: set-based predictions: oracle crash |
| ZAM_Tjunction-1_238_T-1 | infeasible | region | recorded | no | no | no | no (12/141 bad) | 14.1 | 118.4 | 48 | 141 | 146–147 | no feasible sample at step 141 (cycle 48): 8874 of 8874 kinematic [kappa_dot 7805, kappa 906, yaw_rate 91, acceleration 72], 0 collision |
| ZAM_Tutorial-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 3.5 | 106.1 | 12 | 35 | 35–40 |  |
| ZAM_Zip-1_19_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 117.0 | 29 | 85 | 84–85 |  |

# sb2023-vlim over sb100.txt at metis-worlds ae83b2a

100 scenarios: goal 77, collision 2, offroad 12, infeasible 5, window 3, error 1.
Goal kinds: region 14, time-only 85, — 1; traffic: recorded 99, — 1. The planner is deterministic: one run per row. SB-2023 @ 5434d05 with the decision module's own default: its own decision module (desired_velocity='speed_limit', the family's target), the Optimization planner at its defaults, ONE SHOT over the goal window, collision_avoidance off; ms/cycle = decision + low level; the solution's vehicle FORD_ESCORT (the nearest CommonRoad type to SB's 4.3 x 1.7 m, wheelbase 2.3). KS feasibility as measured; footnote: no steering-rate bound, zero input weights.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARG_Carcarana-2_3_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 459.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-3_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 559.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-5_2_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 416.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-11_1_T-1 | offroad | time-only | recorded | yes | no | yes | no (13/33 bad) | 3.3 | 389.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (25/33 bad) | 3.3 | 359.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (27/33 bad) | 3.3 | 473.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 676.0 | 1 | 33 | 33–33 |  |
| BEL_Beringen-1_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 560.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-10_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 256.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-16_2_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 297.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-18_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 4640.0 | 1 | -1 | 33–33 | SB low_level: IPOPT Infeasible_Problem_Detected |
| BEL_Nivelles-19_1_T-1 | goal | time-only | recorded | yes | no | no | no (14/33 bad) | 3.3 | 335.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (19/33 bad) | 3.3 | 400.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (17/33 bad) | 3.3 | 281.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-9_2_T-1 | goal | time-only | recorded | yes | no | no | no (21/33 bad) | 3.3 | 878.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-10_2_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 480.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-11_2_T-1 | offroad | time-only | recorded | yes | no | yes | no (24/33 bad) | 3.3 | 760.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 286.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-3_1_T-1 | offroad | time-only | recorded | yes | no | yes | no (17/33 bad) | 3.3 | 330.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-4_2_T-1 | offroad | time-only | recorded | yes | no | yes | no (32/33 bad) | 3.3 | 290.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-6_1_T-1 | offroad | time-only | recorded | yes | no | yes | no (14/33 bad) | 3.3 | 268.0 | 1 | 33 | 33–33 |  |
| BEL_Wervik-1_4_T-1 | offroad | time-only | recorded | yes | no | yes | no (21/33 bad) | 3.3 | 332.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (7/33 bad) | 3.3 | 2154.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 700.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 387.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-5_3_T-1 | goal | time-only | recorded | yes | no | no | no (16/33 bad) | 3.3 | 377.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 315.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 1150.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (20/33 bad) | 3.3 | 294.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-8_1_T-1 | collision | time-only | recorded | yes | yes | no | no (3/33 bad) | 3.3 | 310.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (18/33 bad) | 3.3 | 643.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (17/33 bad) | 3.3 | 381.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-5_1_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 384.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (7/33 bad) | 3.3 | 442.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-9_1_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 383.0 | 1 | 33 | 33–33 |  |
| DEU_BadEssen-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 171.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 420.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_2_T-1 | offroad | time-only | recorded | yes | no | yes | no (16/33 bad) | 3.3 | 427.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 477.0 | 1 | 33 | 33–33 |  |
| DEU_Bilderstoeckchen-2_3_T-1 | goal | time-only | recorded | yes | no | no | no (16/33 bad) | 3.3 | 630.0 | 1 | 33 | 33–33 |  |
| DEU_Flensburg-10_1_T-1 | goal | region | recorded | yes | no | no | no (12/100 bad) | 10.0 | 5101.0 | 1 | 100 | 99–100 |  |
| DEU_Flensburg-14_1_T-1 | goal | region | recorded | yes | no | no | yes | 9.9 | 3200.0 | 1 | 99 | 99–100 |  |
| DEU_Guetersloh-10_5_T-1 | offroad | time-only | recorded | yes | no | yes | no (19/33 bad) | 3.3 | 802.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-11_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 316.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-12_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 289.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-14_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 748.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-15_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 860.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-16_2_T-1 | offroad | time-only | recorded | yes | no | yes | no (10/33 bad) | 3.3 | 674.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-17_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 1114.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-18_2_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 484.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (11/33 bad) | 3.3 | 481.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-6_3_T-1 | goal | time-only | recorded | yes | no | no | no (13/33 bad) | 3.3 | 618.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 368.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-8_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 277.0 | 1 | 33 | 33–33 |  |
| DEU_Hennigsdorf-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (19/33 bad) | 3.3 | 397.0 | 1 | 33 | 33–33 |  |
| DEU_Ibbenbueren-2_2_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 515.0 | 1 | 33 | 33–33 |  |
| DEU_Moelln-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (19/33 bad) | 3.3 | 323.0 | 1 | 33 | 33–33 |  |
| DEU_Muehlhausen-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (26/33 bad) | 3.3 | 462.0 | 1 | 33 | 33–33 |  |
| DEU_Rheinbach-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 876.0 | 1 | 33 | 33–33 |  |
| DEU_Speyer-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (17/33 bad) | 3.3 | 638.0 | 1 | 33 | 33–33 |  |
| ESP_Almansa-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (19/33 bad) | 3.3 | 877.0 | 1 | 33 | 33–33 |  |
| ESP_Ceuta-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (7/33 bad) | 3.3 | 492.0 | 1 | 33 | 33–33 |  |
| ESP_Inca-7_1_T-1 | goal | time-only | recorded | yes | no | no | no (12/33 bad) | 3.3 | 3330.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 511.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-5_1_T-1 | offroad | time-only | recorded | yes | no | yes | no (17/33 bad) | 3.3 | 1262.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 549.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-9_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 511.0 | 1 | 33 | 33–33 |  |
| ESP_PriegodeCordoba-2_3_T-1 | offroad | time-only | recorded | yes | no | yes | no (27/33 bad) | 3.3 | 333.0 | 1 | 33 | 33–33 |  |
| FRA_Sete-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 492.0 | 1 | 33 | 33–33 |  |
| GRC_Perama-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 827.0 | 1 | 33 | 33–33 |  |
| HRV_Pula-19_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 265.0 | 1 | 33 | 33–33 |  |
| HRV_Pula-5_2_T-1 | goal | time-only | recorded | yes | no | no | no (16/33 bad) | 3.3 | 598.0 | 1 | 33 | 33–33 |  |
| ITA_CarpiCentro-1_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 298.0 | 1 | 33 | 33–33 |  |
| ITA_Empoli-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 1270.0 | 1 | 33 | 33–33 |  |
| ITA_SanGiorgioaCremano-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 478.0 | 1 | 33 | 33–33 |  |
| ITA_Segrate-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (15/33 bad) | 3.3 | 1849.0 | 1 | 33 | 33–33 |  |
| ITA_Siderno-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 524.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-2_1_T-1 | collision | time-only | recorded | yes | yes | no | no (2/33 bad) | 3.3 | 369.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 530.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-4_3_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 891.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (26/33 bad) | 3.3 | 395.0 | 1 | 33 | 33–33 |  |
| RUS_Bicycle-10_1_T-1 | goal | region | recorded | yes | no | no | no (2/23 bad) | 2.3 | 396.0 | 1 | 23 | 20–31 |  |
| RUS_Bicycle-12_1_T-1 | offroad | region | recorded | yes | no | yes | no (10/27 bad) | 2.7 | 322.0 | 1 | 27 | 20–31 |  |
| RUS_Bicycle-1_1_T-1 | goal | region | recorded | yes | no | no | no (2/25 bad) | 2.5 | 1011.0 | 1 | 25 | 20–31 |  |
| RUS_Bicycle-2_1_T-1 | goal | region | recorded | yes | no | no | no (2/20 bad) | 2.0 | 163.0 | 1 | 20 | 20–31 |  |
| RUS_Bicycle-5_1_T-1 | goal | region | recorded | yes | no | no | no (2/20 bad) | 2.0 | 347.0 | 1 | 20 | 20–31 |  |
| RUS_Bicycle-8_1_T-1 | goal | region | recorded | yes | no | no | no (2/21 bad) | 2.1 | 201.0 | 1 | 21 | 20–31 |  |
| RUS_Bicycle-9_1_T-1 | goal | region | recorded | yes | no | no | no (5/20 bad) | 2.0 | 517.0 | 1 | 20 | 20–31 |  |
| USA_Lanker-1_8_T-1 | window | region | recorded | no | no | no | no (11/12 bad) | 1.2 | 180.0 | 1 | 12 | 11–15 |  |
| USA_US101-16_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 22022.0 | 1 | -1 | 80–80 | SB low_level: IPOPT Restoration_Failed |
| USA_US101-18_2_T-1 | goal | time-only | recorded | yes | no | no | no (4/80 bad) | 8.0 | 3886.0 | 1 | 80 | 80–80 |  |
| USA_US101-20_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 24066.0 | 1 | -1 | 80–80 | SB low_level: IPOPT Restoration_Failed |
| USA_US101-26_2_T-1 | infeasible | time-only | recorded | — | — | — | — | — | 1282.0 | 1 | -1 | 80–80 | SB decision raised Exception: Reference trajectory generation failed! (highLevelPlanner.py:2674 correct_orientation) |
| USA_US101-6_2_T-1 | window | region | recorded | no | no | no | no (17/30 bad) | 3.0 | 695.0 | 1 | 30 | 30–31 |  |
| USA_US101-8_4_T-1 | goal | time-only | recorded | yes | no | no | no (19/75 bad) | 7.5 | 2720.0 | 1 | 75 | 75–75 |  |
| ZAM_ACC-1_2_S-1 | goal | time-only | recorded | yes | no | no | yes | 2.9 | 465.0 | 1 | 29 | 29–30 |  |
| ZAM_HW-1_1_S-1 | error:world | — | — | — | — | — | — | — | — | 0 | 0 | — | world: set-based predictions: oracle crash |
| ZAM_Tjunction-1_238_T-1 | window | region | recorded | no | no | no | no (20/146 bad) | 14.6 | 3458.0 | 1 | 146 | 146–147 |  |
| ZAM_Tutorial-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 3.5 | 263.0 | 1 | 35 | 35–40 |  |
| ZAM_Zip-1_19_T-1 | infeasible | region | recorded | — | — | — | — | — | 25226.0 | 1 | -1 | 84–85 | SB low_level: IPOPT Infeasible_Problem_Detected |

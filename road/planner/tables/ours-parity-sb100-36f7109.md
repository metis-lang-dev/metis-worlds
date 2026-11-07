# ours-parity over sb100.txt at metis-worlds 36f7109

100 scenarios: goal 94, offroad 4, window 1, error 1.
Goal kinds: region 14, time-only 85, — 1; traffic: recorded 99, — 1. The planner is deterministic: one run per row. OUR OCP (ocp.py: SB's low-level optimisation from its equations, every addition off) on SB's OWN reference (the sb2023 column's record), one shot, SB's vehicle: the parity proof of M2.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARG_Carcarana-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 61.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-3_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 54.0 | 1 | 33 | 33–33 |  |
| ARG_Carcarana-5_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 114.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-11_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 134.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 98.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (23/33 bad) | 3.3 | 186.0 | 1 | 33 | 33–33 |  |
| BEL_Aarschot-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 142.0 | 1 | 33 | 33–33 |  |
| BEL_Beringen-1_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 149.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-10_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 66.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 75.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-18_2_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 454.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-19_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 187.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 459.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 522.0 | 1 | 33 | 33–33 |  |
| BEL_Nivelles-9_2_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 125.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-10_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 86.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-11_2_T-1 | offroad | time-only | recorded | yes | no | yes | no (13/33 bad) | 3.3 | 761.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 100.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-3_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 65.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-4_2_T-1 | goal | time-only | recorded | yes | no | no | no (23/33 bad) | 3.3 | 113.0 | 1 | 33 | 33–33 |  |
| BEL_Putte-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 201.0 | 1 | 33 | 33–33 |  |
| BEL_Wervik-1_4_T-1 | offroad | time-only | recorded | yes | no | yes | no (10/33 bad) | 3.3 | 417.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (7/33 bad) | 3.3 | 647.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 352.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-4_1_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 143.0 | 1 | 33 | 33–33 |  |
| BEL_Zaventem-5_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 510.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 517.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 484.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (7/33 bad) | 3.3 | 243.0 | 1 | 33 | 33–33 |  |
| BEL_Zwevegem-8_1_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 120.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 128.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-4_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 270.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 107.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-6_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 610.0 | 1 | 33 | 33–33 |  |
| DEU_Backnang-9_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 171.0 | 1 | 33 | 33–33 |  |
| DEU_BadEssen-4_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 60.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 139.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 69.0 | 1 | 33 | 33–33 |  |
| DEU_BadWaldsee-4_5_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 202.0 | 1 | 33 | 33–33 |  |
| DEU_Bilderstoeckchen-2_3_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 324.0 | 1 | 33 | 33–33 |  |
| DEU_Flensburg-10_1_T-1 | goal | region | recorded | yes | no | no | no (7/100 bad) | 10.0 | 3618.0 | 1 | 100 | 99–100 |  |
| DEU_Flensburg-14_1_T-1 | goal | region | recorded | yes | no | no | yes | 9.9 | 684.0 | 1 | 99 | 99–100 |  |
| DEU_Guetersloh-10_5_T-1 | offroad | time-only | recorded | yes | no | yes | no (13/33 bad) | 3.3 | 497.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-11_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 125.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-12_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 86.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-14_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 307.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-15_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 1712.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-16_2_T-1 | goal | time-only | recorded | yes | no | no | no (6/33 bad) | 3.3 | 511.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-17_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 289.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-18_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 303.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 201.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-6_3_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 196.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-7_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 104.0 | 1 | 33 | 33–33 |  |
| DEU_Guetersloh-8_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 65.0 | 1 | 33 | 33–33 |  |
| DEU_Hennigsdorf-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 217.0 | 1 | 33 | 33–33 |  |
| DEU_Ibbenbueren-2_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 467.0 | 1 | 33 | 33–33 |  |
| DEU_Moelln-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 286.0 | 1 | 33 | 33–33 |  |
| DEU_Muehlhausen-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (10/33 bad) | 3.3 | 208.0 | 1 | 33 | 33–33 |  |
| DEU_Rheinbach-1_4_T-1 | goal | time-only | recorded | yes | no | no | no (8/33 bad) | 3.3 | 133.0 | 1 | 33 | 33–33 |  |
| DEU_Speyer-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (14/33 bad) | 3.3 | 513.0 | 1 | 33 | 33–33 |  |
| ESP_Almansa-1_1_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 241.0 | 1 | 33 | 33–33 |  |
| ESP_Ceuta-1_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 199.0 | 1 | 33 | 33–33 |  |
| ESP_Inca-7_1_T-1 | goal | time-only | recorded | yes | no | no | no (5/33 bad) | 3.3 | 3084.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 1148.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-5_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 706.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-7_2_T-1 | goal | time-only | recorded | yes | no | no | no (4/33 bad) | 3.3 | 321.0 | 1 | 33 | 33–33 |  |
| ESP_Monzon-9_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 259.0 | 1 | 33 | 33–33 |  |
| ESP_PriegodeCordoba-2_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 221.0 | 1 | 33 | 33–33 |  |
| FRA_Sete-1_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 140.0 | 1 | 33 | 33–33 |  |
| GRC_Perama-3_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 539.0 | 1 | 33 | 33–33 |  |
| HRV_Pula-19_1_T-1 | goal | time-only | recorded | yes | no | no | no (14/33 bad) | 3.3 | 251.0 | 1 | 33 | 33–33 |  |
| HRV_Pula-5_2_T-1 | goal | time-only | recorded | yes | no | no | no (2/33 bad) | 3.3 | 281.0 | 1 | 33 | 33–33 |  |
| ITA_CarpiCentro-1_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 55.0 | 1 | 33 | 33–33 |  |
| ITA_Empoli-2_4_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 454.0 | 1 | 33 | 33–33 |  |
| ITA_SanGiorgioaCremano-2_1_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 231.0 | 1 | 33 | 33–33 |  |
| ITA_Segrate-1_2_T-1 | goal | time-only | recorded | yes | no | no | no (13/33 bad) | 3.3 | 873.0 | 1 | 33 | 33–33 |  |
| ITA_Siderno-2_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 53.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-2_1_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 73.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-3_1_T-1 | goal | time-only | recorded | yes | no | no | no (3/33 bad) | 3.3 | 194.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-4_3_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 495.0 | 1 | 33 | 33–33 |  |
| PRI_Barceloneta-4_5_T-1 | goal | time-only | recorded | yes | no | no | no (9/33 bad) | 3.3 | 456.0 | 1 | 33 | 33–33 |  |
| RUS_Bicycle-10_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.3 | 82.0 | 1 | 23 | 20–31 |  |
| RUS_Bicycle-12_1_T-1 | offroad | region | recorded | yes | no | yes | no (4/27 bad) | 2.7 | 175.0 | 1 | 27 | 20–31 |  |
| RUS_Bicycle-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.5 | 276.0 | 1 | 25 | 20–31 |  |
| RUS_Bicycle-2_1_T-1 | goal | region | recorded | yes | no | no | no (1/20 bad) | 2.0 | 44.0 | 1 | 20 | 20–31 |  |
| RUS_Bicycle-5_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.0 | 339.0 | 1 | 20 | 20–31 |  |
| RUS_Bicycle-8_1_T-1 | goal | region | recorded | yes | no | no | yes | 2.3 | 292.0 | 1 | 23 | 20–31 |  |
| RUS_Bicycle-9_1_T-1 | goal | region | recorded | yes | no | no | no (3/20 bad) | 2.0 | 711.0 | 1 | 20 | 20–31 |  |
| USA_Lanker-1_8_T-1 | window | region | recorded | no | no | no | no (7/13 bad) | 1.3 | 109.0 | 1 | 13 | 11–15 |  |
| USA_US101-16_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 4309.0 | 1 | 80 | 80–80 |  |
| USA_US101-18_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 1879.0 | 1 | 80 | 80–80 |  |
| USA_US101-20_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 2281.0 | 1 | 80 | 80–80 |  |
| USA_US101-26_2_T-1 | goal | time-only | recorded | yes | no | no | yes | 8.0 | 1979.0 | 1 | 80 | 80–80 |  |
| USA_US101-6_2_T-1 | goal | region | recorded | yes | no | no | yes | 3.0 | 156.0 | 1 | 30 | 30–31 |  |
| USA_US101-8_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 7.5 | 1780.0 | 1 | 75 | 75–75 |  |
| ZAM_ACC-1_2_S-1 | goal | time-only | recorded | yes | no | no | yes | 2.9 | 43.0 | 1 | 29 | 29–30 |  |
| ZAM_HW-1_1_S-1 | error:world | — | — | — | — | — | — | — | — | 0 | 0 | — | world: set-based predictions: oracle crash |
| ZAM_Tjunction-1_238_T-1 | goal | region | recorded | yes | no | no | no (8/146 bad) | 14.6 | 1797.0 | 1 | 146 | 146–147 |  |
| ZAM_Tutorial-1_1_T-1 | goal | region | recorded | yes | no | no | yes | 3.5 | 48.0 | 1 | 35 | 35–40 |  |
| ZAM_Zip-1_19_T-1 | goal | region | recorded | yes | no | no | no (9/84 bad) | 8.4 | 9929.0 | 1 | 84 | 84–85 |  |

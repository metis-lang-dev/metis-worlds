# trajplan over subset.txt at metis-worlds 4b7f9b1

25 scenarios: goal 11, collision 7, offroad 1, window 6.
Goal kinds: region 15, time-only 10; traffic: none 2, recorded 23. The planner is deterministic: one run per row. perotheia-packages/planner's C++ planner: the road family's command per beat (road_tree --world crnative over the LaneMap from the lanelets, as `ours`) → its BehaviourCmd (keep at the target, window-fitted; stop_at; change_left/right; pass_opposite) → trajplan::Planner (its lane plan over the lanelets the family's LaneMap written as the planner's lane map (trajplan.lanes_file), its IDM / stop / gap floors against the recorded obstacles, its OCP: 5 s at 0.1 s), re-planned EVERY step in process (libtrajplan_c.so through ctypes); the restrictor's cap clips the executed speed; SB's vehicle.

| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) | ms/cycle | cycles | steps | window | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZAM_Tjunction-1_42_T-1 | window | region | recorded | no | no | no | yes | 14.7 | 3.9 | 147 | 147 | 146–147 |  |
| ZAM_Over-1_1 | window | region | none | no | no | no | no (1/30 bad) | 3.0 | 7.1 | 30 | 30 | 0–30 |  |
| DEU_Test-1_1_T-1 | collision | region | recorded | no | yes | no | yes | 4.0 | 4.2 | 40 | 40 | 35–40 |  |
| USA_US101-2_1_T-1 | collision | region | recorded | no | yes | no | no (2/104 bad) | 10.4 | 4.7 | 104 | 104 | 94–104 |  |
| ITA_Siderno-4_5_T-1 | collision | time-only | recorded | yes | yes | no | no (11/33 bad) | 3.3 | 0.3 | 33 | 33 | 33–33 |  |
| HRV_Pula-8_3_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 3.2 | 33 | 33 | 33–33 |  |
| BEL_Zwevegem-1_7_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 1.6 | 33 | 33 | 33–33 |  |
| ZAM_Ramp-1_1-T-1 | offroad | region | recorded | yes | no | yes | no (1/94 bad) | 9.4 | 5.3 | 94 | 94 | 0–100 |  |
| BEL_Putte-14_1_I-1-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 7.1 | 33 | 33 | 33–33 |  |
| USA_Lanker-2_24_T-1 | window | region | recorded | no | no | no | yes | 7.0 | 1.8 | 70 | 70 | 70–70 |  |
| DEU_B471-1_1_T-1 | window | region | recorded | no | no | no | yes | 5.0 | 6.4 | 50 | 50 | 0–50 |  |
| ZAM_Urban-3_3 | window | region | none | no | no | no | no (5/40 bad) | 4.0 | 5.5 | 40 | 40 | 30–40 |  |
| ZAM_Zip-1_30_T-1 | window | region | recorded | no | no | no | yes | 8.5 | 4.6 | 85 | 85 | 84–85 |  |
| DEU_Ibbenbueren-16_1_T-1 | collision | time-only | recorded | yes | yes | no | no (1/33 bad) | 3.3 | 7.9 | 33 | 33 | 33–33 |  |
| ARG_Carcarana-6_2_T-1 | goal | time-only | recorded | yes | no | no | no (1/33 bad) | 3.3 | 5.7 | 33 | 33 | 33–33 |  |
| DEU_Backnang-3_4_T-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 6.6 | 33 | 33 | 33–33 |  |
| USA_Lanker-1_3_T-1 | goal | region | recorded | yes | no | no | yes | 3.9 | 7.8 | 39 | 39 | 30–40 |  |
| ESP_Toledo-11_4_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 9.3 | 33 | 33 | 33–33 |  |
| ITA_CarpiCentro-5_3_T-1 | collision | time-only | recorded | yes | yes | no | yes | 3.3 | 6.1 | 33 | 33 | 33–33 |  |
| ESP_Cambre-5_3_I-1-1 | goal | time-only | recorded | yes | no | no | yes | 3.3 | 6.8 | 33 | 33 | 33–33 |  |
| ZAM_Tjunction-1_185_T-1 | goal | region | recorded | yes | no | no | yes | 14.6 | 5.4 | 146 | 146 | 146–147 |  |
| ZAM_Zip-1_11_T-1 | goal | region | recorded | yes | no | no | yes | 8.4 | 4.4 | 84 | 84 | 84–85 |  |
| USA_US101-3_5_T-1 | goal | region | recorded | yes | no | no | yes | 3.0 | 5.0 | 30 | 30 | 30–31 |  |
| USA_Lanker-2_26_T-1 | goal | region | recorded | yes | no | no | yes | 7.0 | 3.9 | 70 | 70 | 70–70 |  |
| DEU_Lohmar-33_1_T-1 | goal | region | recorded | yes | no | no | no (6/99 bad) | 9.9 | 4.6 | 99 | 99 | 99–100 |  |

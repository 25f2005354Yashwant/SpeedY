# EXPERIMENT LOG

Conventions: tune seeds = 1,000,000+i, final seeds = 900,000,000+i (disjoint). All comparisons use common random
numbers (same seeds for every candidate). CIs are Wilson 95 %. H1 = `t_aggr`, H2 = `t_patient` (our stand-ins).

## E0 — engine timing (27 Nov 18:10)
- cmd: ad-hoc `run_battle(examples/best_team.json, seed 0..29, public)`; stock engine.
- result: 0.35 s/battle; 82 % of time in `ai_core.expected_damage` (32 `calculate_damage` calls each).
- after `harness.fast.install()`: 0.035 s/battle single core (60 battles in 2.2 s).

## E1 — bit-identical proof (27 Nov 18:35)
- cmd: `python -m harness.prove_identical 10` (4 teams incl. multi-hit/recoil/drain/OHKO moves x 8 configs
  [public, offensive, defensive, speed, status, policy, policy+best_policy.py, policy+example_policy.py] x seeds 7000..7009)
- result: **320 battles compared, 0 mismatches** (SHA-256 of full debug log + result). `results/prove_identical.txt`.

## E3 — policy v0 smoke tests (27 Nov 19:05) — n=30 only, NOT conclusions, just direction
- cmd: `python -m tools_ours.test_policy damage 20000` -> **20000 cases, 0 damage mismatches, 0 expected-damage mismatches**
- cmd: `python -m tools_ours.test_policy predict results/search/to_pdf_s1/best_r0.json <opp> 30` (seeds 1,000,000..29)
- team = first search checkpoint (baseline policy scores ~50 % with it).
| opp | wins/30 | Cynthia-action prediction accuracy |
|---|---|---|
| public | 26 | 100.0 % |
| t_aggr | 26 | 99.8 % |
| t_patient | 30 | 99.2 % |
| defensive | 29 | 99.6 % |
| offensive | 26 | 99.8 % |
| speed | 28 | 99.8 % |
| policy (boss) | 13 | 100 % |
- mean latency ~25 ms/turn, max ~120 ms (in-process, 3 other cores busy).

## E4 — policy v0 + team_v0 (first team-only checkpoint), n=200, seeds 1,000,000..199 (27 Nov 19:16)
- cmd: `python -m harness.evaluate --team results/team_v0.json --policy policy_src/build/policy.py --n 200 --set tune`
- policy(boss) 25.5 [20.0,32.0] | public 90.0 [85.1,93.4] | t_aggr 84.0 | t_patient 98.5 | offensive 85.0 |
  defensive 97.5 | speed 91.0 | status 94.5 | wide tune mean 55.1 (t_fastphys 7.0, t_boss 16.0, t_icerock 23.0 worst)
- 0 fallbacks, max latency 273 ms (6 procs on 4 cores).
- zip objective with boss swap 68.9; without swap (public slot) ~90.8.
- team-only search to_pdf_s1 stopped at 19:17 (pdf objective 0.562, baseline policy) -> `results/team_only_ckpt1.json`.

## E5 — rollout budget sensitivity (27 Nov 19:24), team_v0, n=100 per opp, seeds 1,000,000..99, paired
- cmd: `HARNESS_PROCS=1 python -m tools_ours.cmp 100 policy,t_aggr team_v0:policy_v1 team_v0:policy_search_fast team_v0:p_heavy`
| policy build | rollouts (R1/R2/top) | boss | t_aggr | mean | mean latency |
|---|---|---|---|---|---|
| v1 | 4 / 12 / 3 | 29.0 | 84.0 | 56.5 | 27 ms |
| fast | 2 / 6 / 2 | 33.0 | 85.0 | 59.0 | 12 ms |
| heavy | 8 / 24 / 3 | 38.0 | 89.0 | 63.5 | 50 ms |
- heavy − v1 = +7.0 pts (z = 1.83), fast − v1 = +2.5 (z = 0.67, noise). More rollouts look useful; n too small to conclude.

## E6 — policy-aware team search wp_zip_s1 (started 19:17)
- cmd: `python -m tools_ours.search --tag wp_zip_s1 --objective zip_policy --policy policy_src/build/policy_search_fast.py
  --start results/team_only_ckpt1.json --minutes 100 --seed 11 --stages 30,120,400,1000`
- objective = 0.34 boss(`policy`) + 0.33 t_aggr + 0.33 t_patient, tune seeds. Log: `results/search/wp_zip_s1/log.txt`.

## E7 — policy v1 vs v2 vs v2-heavy (27 Nov 19:39), team_v1, n=150 per opp, paired, seeds 1,000,000..149
- cmd: `HARNESS_PROCS=1 python -m tools_ours.cmp 150 policy,t_aggr team_v1:policy_v1 team_v1:policy_v2 team_v1:policy_v2h`
| build | boss | t_aggr | mean | latency mean/max |
|---|---|---|---|---|
| v1 (4/12/top3) | 46.0 [38,54] | 98.7 | 72.3 | 27 / 143 ms |
| v2 (CRN streams, halving 4/8/20) | 50.7 [43,59] | 98.0 | 74.3 | 41 / 193 ms |
| v2h (6/14/40) | 60.7 [53,68] | 100.0 | 80.3 | 71 / 321 ms |
- v2h − v1 = +8.0 pts (z = 3.52): rollout count is worth real points on the boss.

## E8 — wp_zip_s1 stopped at 19:45 after 4 accepts (0.587 -> 0.794 with the light v1 policy); too slow (~2 candidates/min).
- best: delibird / zigzagoon / slaking / shinx / scizor / weavile -> `results/team_v2.json`

## E9 — fast simulator fidelity (27 Nov 19:50): same greedy player in the real engine vs in the L0 simulator
- cmd: `python -m tools_ours.fastsim check results/team_v2.json <opp> 300` (real: seeds 1,000,000..299; L0: 4000 sims)
| opp | real engine + greedy (n=300) | L0 sim (n=4000) |
|---|---|---|
| public | 76.3 | 74.2 |
| policy (boss) | 31.7 | 31.0 |
| t_aggr | 92.0 | 91.4 |
| t_patient | 76.0 | 76.3 |
| t_sinnoh | 85.3 | 87.1 |
- L0 costs ~0.6 ms per battle vs ~0.5–1 s for engine + rollout policy.

## E10 — v2h vs v4 (27 Nov 20:01), team_v2 (shinx/double-hit version), n=150 per opp, paired
- cmd: `HARNESS_PROCS=1 python -m tools_ours.cmp 150 policy,t_sinnoh team_v2:policy_v2h team_v2:policy_v4`
- v2h: boss 60.7 [53,68], t_sinnoh 90.7, latency 75/364 ms | v4: boss 49.3 [41,57], t_sinnoh 91.3, latency 109/541 ms
- v4 − v2h = −5.3 pts (z = −3.11). v4 added fast paths + adaptive allocation with early stop when the leader is
  ahead by 0.3 after 6 rollouts. Early stop is the suspect -> removed in v6 (only the optional extra stage is gated).

## E11 — default-player research in the L0 simulator (27 Nov 19:55–20:05), 3000 sims per (team, opp)
- "aim at Cynthia's predicted switch-in": mean greedy win rate 56.9->62.0 (team_v0), 52.3->63.9 (team_v2), 38.2->48.4 (A team)
- + duel-based forced replacement: 62.0->70.0, 63.9->69.6, 48.4->53.6. Both adopted (v5).
- pivot-out-when-losing rule: −7.2, −3.9, +18.4 -> team dependent, NOT adopted.

## E12 — v2h vs v6 (27 Nov 20:12), team_v2, boss only, n=150 paired, seeds 1,000,000..149
- cmd: `HARNESS_PROCS=1 python -m tools_ours.cmp 150 policy team_v2:policy_v2h team_v2:policy_v6`
- v2h 60.0 | v6 63.3 [55,71], latency 94/395 ms (4+ procs on 4 cores). v6 − v2h = +3.3 pts (z = 0.93, not significant).
- v6 = v5 default player (aim at predicted switch-in, duel-based replacement) + halving 6/14/40 + optional +40 when
  the top two are within 0.08. Working policy = v6.

## E13 — baseline-policy clone for the fast simulator (27 Nov 20:10)
- `python -m tools_ours.basecheck <team> <opp> 25`: clone vs real baseline decisions: 442/442 and 421/421 identical
  (after modelling the quirk that position_value reads the opponent's HP as 0 when our hit never lands).
- `python -m tools_ours.basesim check <team> <opp> 300` real (n=300) vs clone L0 (n=3000):

## E14 — L0 policy-track search run1 (19:48–20:33, 3 chains, greedy default of v4, objective W in l0search.py)
- cmd: `python -m tools_ours.l0search --tag run1 --minutes 45 --chains 3 --seed 1 --start results/team_v2.json`
- `python -m tools_ours.l0top top1 9 run1` (re-scored on fresh L0 seeds 500,000+): best 0.863
  marill/ralts/weavile/slaking/sneasel/ambipom (L0 boss 69 %, t_aggr 99.9, t_patient 97.6, t_mixed 76).
- next: real-battle ranking with policy_v6_light, n=80 x 5 opps (`results/l0/top1_real80.json`).

## E15 — real-battle ranking of L0 candidates (27 Nov 21:02), policy_v6_light, n=80 per opp, seeds 1,000,000..79
- cmd: `HARNESS_PROCS=2 python -m tools_ours.realrank results/l0/top1.json policy_src/build/policy_v6_light.py 80 policy,t_aggr,t_patient,t_sinnoh,t_mixed`
| team | boss | t_aggr | t_patient | t_sinnoh | t_mixed | mean |
|---|---|---|---|---|---|---|
| **team_v3** marill/ralts/weavile/slaking/sneasel/ambipom | 78.7 | 100 | 100 | 100 | 85.0 | 92.8 |
| team_v3b slaking/alakazam/starly/ralts/tauros/primeape | 75.0 | 97.5 | 98.8 | 92.5 | 86.3 | 90.0 |
| sunkern/slaking/swinub/weavile/sneasel/lopunny | 76.2 | 100 | 100 | 98.8 | 72.5 | 89.5 |
| team_v2 (previous) | 72.5 | 100 | 100 | 95.0 | 56.2 | 84.8 |
- team_v3 installed in submission/with_policy with policy_v6 (finalize: 0 fallbacks, sha1 team f75cf8ce…, policy 6c7eed07…).

## E16 — confirmation team_v3 vs team_v3b, full policy_v6, n=300 per opp, paired, seeds 1,000,000..299 (21:27)
- cmd: `HARNESS_PROCS=2 python -m tools_ours.cmp 300 policy,public,t_aggr,t_patient team_v3:policy_v6 team_v3b:policy_v6`
- team_v3: boss 78.3 [73,83], public 99.7 [98,100], t_aggr 99.7, t_patient 100.0; turns in wins ~13.1; 0 fallbacks;
  latency mean ~75 ms, max 449 ms (3 procs busy). team_v3b: boss 68.3, mean 90.9. Δ = −3.5 pts (z = −5.70).

## E18 — team-only fast search tb1 (baseline clone, 20:13–21:28) + real ranking (21:45)
- cmd: `python -m tools_ours.l0search --mode base --tag tb1 --minutes 75 --chains 1 --seed 5 --start results/team_only_ckpt1.json`;
  `python -m tools_ours.l0top tb1top 8 tb1 --base`; `python -m tools_ours.realrank results/l0/tb1top.json baseline 300 public,t_aggr,t_patient`
- **team_only_v2** snover/ambipom/slaking/weavile/zubat/diglett, REAL baseline policy, n=300 tune seeds:
  public 97.0, t_aggr 98.7, t_patient 97.7 (mean 97.8) vs previous ckpt1 56.7.

## E19 — team_only_v2 robustness, REAL baseline policy, FINAL seeds 900,000,000..499, n=500 per opp (21:55)
- cmd: `HARNESS_PROCS=1 python -m harness.evaluate --team results/team_only_v2.json --n 500 --final --set all`
- public 97.4 [95.6,98.5] | t_aggr 98.2 | t_patient 99.0 | offensive 98.0 | defensive 95.0 | speed 98.4 | status 93.2
- held-out Cynthia-team variants: h_aggr2 98.2, h_patient2 94.2, h_altmoves 94.6, h_altmoves_patient 99.6
- different-team stand-ins weak: h_fire 2.6, h_legends 0.0, h_steel 11.0, t_fastphys 5.8, t_icerock 16.8, h_elecpsy 21.4
- pdf objective 98.20, wide mean (all 36) 59.56. Installed in submission/team_only (sha1 fabb715c…).

## E20 — team_v3 vs team_only_v2, both with policy_v6, n=200 per opp, paired, tune seeds (22:00)
- team_v3: boss 80.0, public 100, t_aggr 99.5, t_patient 100 (mean 94.9) | team_only_v2: boss 75.5, public 100,
  t_aggr 100, t_patient 100 (mean 93.9); Δ = −1.0 (z = −1.71). Policy track keeps team_v3.


# Doom Warriors — Cynthia's Gauntlet submission

IIT Madras × Custodia × WiTS Pokémon data-science hackathon (24–28 Nov 2026).

## Files

| Path | Purpose |
|---|---|
| `team.json` | **Submitted team** (6 Pokémon, 40/40 points, validator-clean) |
| `policy.py` | **Submitted battle policy** (pure Python, no imports, < 31 KB, passes `python -m engine.policy --check`) — present only if we submit the "team + policy" entry |
| `submission/team_only/team.json` | Team tuned for the organisers' **default (baseline) policy** |
| `submission/with_policy/{team.json,policy.py}` | Team co-tuned with **our policy** |
| `policy_src/template.py` | Readable policy source; `tools_ours/build_policy.py` packs the public data tables into it and minifies it into `policy.py` |
| `harness/` | Parallel evaluation harness around the organisers' **unmodified** engine; stand-in opponents in `harness/standins/` |
| `tools_ours/` | Candidate pool, stand-in generator, team searches, fast simulators, policy tests, finalisation |
| `results/` | Search logs, checkpoints, ranking tables |
| `RULES_DECISION.md` | Rules we verified in the engine source (with file:line) |
| `EXPERIMENT_LOG.md` | Every experiment: command, seeds, n, result, CI |
| `PROGRESS.md` | Timeline of the work |

The organisers' engine and data are **not** in this repository. To reproduce, copy our folders into the extracted
`CynthiaXCustodia.zip` and run from its root (Python 3.10+, standard library only):

```bash
python -m tools_ours.build_policy                                 # build policy_src/build/{policy,policy_dev}.py
python -m engine.policy --check policy.py                         # policy validation (sandboxed)
python -m harness.prove_identical 10                              # memoised harness == stock engine (320 battles)
python -m tools_ours.test_policy damage 20000                     # policy damage model == engine (0 mismatches)
python -m harness.evaluate --team team.json --policy policy.py --n 1000 --final --set all
python -m harness.evaluate --team submission/team_only/team.json --n 1000 --final --set all
```

## Key facts we verified in the engine (see `RULES_DECISION.md`)

- Battles are a **pure damage race**: no status, stat stages, flinch, confusion or healing are ever applied
  (`engine/battle.py`, `_execute_move`). What matters: damage, accuracy, crits, multi-hit, drain/recoil, priority, speed, PP.
- Cynthia is a **deterministic public script** (`engine/cynthia.py`, `engine/ai_core.py`).
- The observation's `battle_history` contains every damage event with `hp_after`, so her exact HP is recoverable.
- Locally, an entry **with** a policy faces the `policy` variant (Giratina instead of Spiritomb, plus a "boss mode"
  on 30 % of seeds: her damage ×1.15, ours ×0.85) instead of `public` (`engine/runner.py:81-82`, `ui/server.py:550,596`).

## What the policy does

1. **Exact Gen-4 damage tables** — integer formula identical to the engine (checked on 20,000 random cases,
   0 mismatches; expected damage also identical).
2. **Opponent model** — replays `battle_history` to track Cynthia's HP, PP, revealed moves and switch cooldown;
   predicts her next action with a clone of her public scripted move/switch rule (100 % agreement on the public
   variant, ~99 % on other personalities). It keeps a few hypotheses about her personality parameters
   (switch thresholds, aggression, priority weight) and uses the one that best explains her observed choices.
   Detects the boss damage modifier from exact damage numbers.
3. **Monte-Carlo rollouts** — every legal action (each move, each switch) is scored by simulating the rest of the
   battle many times (accuracy, crits, damage rolls, multi-hit, drain/recoil, priority, speed ties) with
   *common random numbers* across actions; sequential halving spends the budget on the leading actions.
   The rollout default player aims at Cynthia's predicted switch-in and picks replacements by 1v1 race outcome.
4. **Safety** — deterministic, no imports, no file/network access, uses only `state`. Falls back to a max-power legal
   move on any internal error; the search lightens itself after many calls so the sandbox's cumulative time cap
   (600 s per process) cannot be reached. Typical latency 60–90 ms/turn, max < 0.5 s; **0 fallbacks** observed.

## How the teams were chosen

1. **Candidate pool** (`tools_ours/pool.py`): all 443 legal species with ≥ 4 supported damaging moves; 2–4 movesets
   each from a damage-race rule (coverage against Cynthia's Pokémon and against a broad pool, plus priority variants).
2. **Fast simulators**: the policy's own exact simulator with a greedy player (`tools_ours/fastsim.py`) and an exact
   clone of the organisers' baseline policy (`tools_ours/basesim.py`, 863/863 identical decisions vs the real
   baseline). ~1000× cheaper than engine battles, used **only to propose** teams.
3. **Search** (`tools_ours/l0search.py`, `tools_ours/search.py`): mutations = swap one/two species under the 40-point
   cap, change moveset, change one move, reorder moves/team; hill-climbing with racing and paired tests.
4. **Real-battle re-ranking** (`tools_ours/realrank.py`, `tools_ours/cmp.py`): the best proposals are re-ranked with
   real engine battles on identical seeds (common random numbers), Wilson 95 % CIs, paired z-tests.
5. Tuning seeds (1,000,000+i) and final-test seeds (900,000,000+i) are disjoint; `h_*` held-out stand-ins were never
   used during search.

## Evaluation

Opponents: `public` and `policy` (boss) are the organisers' variants; `t_aggr` / `t_patient` are our stand-ins for
the hidden *aggressive* / *patient* variants, written from the public description only. Wider stand-ins (other
teams, other movesets) are in `harness/standins/` (`t_*` tune, `h_*` held-out).

**Team + policy** (`submission/with_policy`, our policy; tune seeds, n = 200–300 per opponent, Wilson 95 % CI):

| Opponent | Win % | 95 % CI | Avg turns in wins |
|---|---|---|---|
| `public` | 99.7 | [98, 100] | 13.0 |
| boss `policy` (Giratina + boss mode) | 78.3 | [73, 83] | 13.3 |
| aggressive stand-in | 99.7 | [98, 100] | 13.1 |
| patient stand-in | 100.0 | [99, 100] | 13.2 |

**Team only, organisers' baseline policy** (`submission/team_only`; **final-test seeds** 900,000,000+i, n = 500 per opponent):

| Opponent | Win % | 95 % CI | Avg turns in wins |
|---|---|---|---|
| `public` | 97.4 | [95.6, 98.5] | 12.2 |
| aggressive stand-in | 98.2 | [96.6, 99.1] | 11.8 |
| patient stand-in | 99.0 | [97.7, 99.6] | 12.5 |
| `offensive` / `defensive` / `speed` / `status` (public personality files) | 98.0 / 95.0 / 98.4 / 93.2 | ±2–3 | 12–13 |
| held-out behaviour / moveset variants of Cynthia's team | 94.2 – 99.6 | ±1–3 | 12–14 |
| **official-style objective** mean(public, aggressive, patient) | **98.2** | | |

For reference, the organisers' `examples/best_team.json` scores 4.8 % on the same objective with the baseline policy.

**Known weakness:** both teams are tuned against Cynthia's roster. Against stand-ins with an entirely different
team (e.g. all-fire, all-steel, legendary-heavy) the team-only entry drops sharply (2–11 % on some), so a hidden
variant with a completely different team is our main risk.

## Fair play

- **Hidden variants were never accessed.** The distributed zip contains a `variants_private/` folder; it was never
  opened, read, hashed, imported or loaded, and our harness refuses to resolve those names. We did not run the
  organisers' test-suite (it would load those files). Stand-ins were written from the public docs' description only.
- **No code, team or moveset was copied** from anyone; all code, teams and movesets are our own work.
- The organisers' engine, validator, runner and data were **not modified**. `harness/fast.py` memoises pure engine
  functions at run time and is proven bit-identical to the stock engine on 320 battles.

## Team: Doom Warriors

| Role | Name | Contribution |
|---|---|---|
| Lead | _Name_ | _e.g. strategy, team search, policy, evaluation_ |
| Member | _Name_ | _e.g. testing, analysis, documentation_ |

## Credits

- Simulator, data and rules: Custodia × WiTS, IIT Madras (*Cynthia's Gauntlet* package).
- Pokémon data: PokéAPI (BSD-3-Clause). Pokémon and Pokémon character names are trademarks of Nintendo /
  Game Freak / The Pokémon Company; this project is not affiliated with them.
- Python standard library only.
- Ideas: Wilson score interval; common random numbers and paired tests; successive halving / racing;
  Monte-Carlo rollout (one-step lookahead policy improvement); simulated annealing / hill-climbing.

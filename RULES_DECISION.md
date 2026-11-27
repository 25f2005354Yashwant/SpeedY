# Rules decision (Phase 0) — 27 Nov 2026

## Which rule set do the files in this folder describe?

The **"zip" rule set**. `docs/rulebook.txt` (= `docs/RULEBOOK.md`, byte-identical), `docs/NOTE_TO_PARTICIPANTS.md`
and `docs/SIMULATOR_SPEC.md` all say:

- `team.json` required, `policy.py` **optional** (baseline plays if absent) — rulebook §8.
- **100 battles on hidden seeds**, split 34 / 33 / 33 over public + two hidden variants — NOTE "How You'll Be Judged".
- Hidden variants are named `aggressive` ("never switches, favours big hits") and `patient` ("switches readily,
  favours status"), "optionally a different team" — SIMULATOR_SPEC §3, §9.
- Tie-break: lower average turns in won battles. 200-turn limit = loss.
- README + GitHub repo, made public after submitting.

The 25-Nov PDF (team.json only, 1000 battles x 3) is not in this folder, so I cannot check it. **Owner decision
(27 Nov): keep both tracks valid and decide when the organisers answer.**

## What is submitted

| Track | Files | Local opponent for the "public" slot |
|---|---|---|
| team-only | `team.json` | `public` (Spiritomb lead team), baseline policy plays |
| team + policy | `team.json` + `policy.py` | **`policy` boss variant** if the official runner behaves like `engine/runner.py` |

## Verified claims (file:line)

| | Claim | Verdict | Evidence |
|---|---|---|---|
| a | No status / stat-stage / flinch / confusion / healing effects | **True** | `engine/battle.py:549-830` (`_execute_move`): accuracy, multi-hit, crit, damage, drain/recoil only. `status` and `stat_stages` are initialised (`battle.py:151-160`) and never written. Validator bans all `status`-category moves anyway (README "Banned moves"). |
| b | Runner swaps `public` -> `policy` when a policy is supplied | **True** | `engine/runner.py:81-82`; also the CLI default at `runner.py:~395`. `variants/policy.json`: Giratina-Altered (Shadow Force/Dragon Claw/Aura Sphere/Earth Power) replaces Spiritomb. Boss mode: `battle.py:207-218`, `crc32(str(seed)) % 10 < 3` => **30 %** of seeds, Cynthia damage x1.15, ours x0.85 (the code comment says 60 %, the code says 30 %). |
| c | Baseline lookahead treats every opponent as 100 HP | **True** | `engine/ai_search.py:290` (`opp_act.get("current_hp", 100)`) and `:60` (`max_hp` default 100); the observation's `opponent_active` has only `hp_percent` (`battle.py:1121-1128`). |
| d | Sandbox runs `python -I -c <source>` | **True** | `engine/policy.py:293-294`. Windows command lines cap at ~32,767 chars, so keep `policy.py` < 31,000 bytes. |
| e | Data quirks | **True** | Extreme Speed priority **+2** (`cynthia_data/moves.csv:246`), so it out-prioritises every +1 move. Giratina's Shadow Force is in `config/unsupported_moves.json:196` yet is used as a plain 120-BP one-turn hit; Roserade's Extrasensory and Giratina's Shadow Force are absent from `learnsets.csv`. |

## Other things found

- `variants_private/` exists in the zip and holds 2 files. **Never opened.** `CynthiaBot("aggressive"|"patient")`
  and the organisers' `pytest` suite would load them, so neither is ever run; `harness/` refuses those names/paths.
- `variants/{offensive,defensive,speed,status}.json` are public, documented in the README, and all use the *same
  team* as `public` with different AI parameters. Owner approved using them as stand-ins.
- Cynthia uses `search_depth 0`: tactical switch test, else greedy `score_legal_move` (`engine/cynthia.py:434-520`).
- `opponent_active` never reveals Cynthia's exact HP, but `battle_history` (full event log incl. damage amounts and
  `hp_after`) is in the observation, so a policy can reconstruct it exactly.

## Open question for the organisers (blocks the policy-vs-no-policy decision)

> "In the official evaluation, does an entry that includes `policy.py` face the `policy` variant (Giratina team +
> boss mode) in place of `public`, as `engine/runner.py:81` does locally, or the same three variants as a
> team-only entry?"

Until answered, policy entries are scored under the worst case (they face the boss variant).

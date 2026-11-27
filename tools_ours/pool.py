"""Phase 3.1/3.2 — candidate pool + cheap analytic 1v1 screen.

For every legal species build 2-4 damage-race movesets and score it against Cynthia's known Pokemon
(public team + Giratina) and against a broad pool of fully evolved species (robustness).
The screen is used ONLY to prune; ranking is done by simulation.

usage: python -m tools_ours.pool            -> results/pool.json
"""
import itertools
import json
import math

from harness import core

core._init()
D = core._state["data"]
from engine.ai_core import expected_damage  # noqa: E402  (memoised by harness.fast)
from engine.stats import calc_stats  # noqa: E402

PRIORITY = {"ice-shard", "shadow-sneak", "aqua-jet", "bullet-punch", "mach-punch", "quick-attack", "extreme-speed",
            "vacuum-wave"}


def legal_species():
    out = []
    for p in D.pokemon.values():
        if not p.is_default_form or p.is_legendary or p.is_mythical or p.generation > 4:
            continue
        mv = [m for m in D.learnsets.get(p.identifier, ()) if D.is_move_supported(m) and (D.moves[m].power or 0) > 0
              or m in ("seismic-toss", "night-shade", "dragon-rage", "sonic-boom")]
        mv = [m for m in mv if D.is_move_supported(m)]
        if len(mv) >= 4:
            out.append((p.identifier, sorted(mv)))
    return out


def cynthia_targets():
    t = {}
    for v in ("public", "policy"):
        for mon in json.load(open(f"variants/{v}.json"))["team"]:
            t[mon["species"]] = mon["moves"]
    return t


def hp(s):
    return calc_stats(D.pokemon[s])["hp"]


def spe(s):
    return calc_stats(D.pokemon[s])["spe"]


def dmg(a, m, d):
    return expected_damage(a, m, d)


def duel(me, my_moves, opp, opp_moves):
    """Value of a full-HP 1v1: >1 if I win (1 + my remaining HP fraction), else fraction of damage dealt."""
    d_me = max(dmg(me, m, opp) for m in my_moves) / hp(opp)
    d_op = max(dmg(opp, m, me) for m in opp_moves) / hp(me)
    if d_me <= 0:
        return 0.0
    t_me = math.ceil(1 / d_me - 1e-9)
    t_op = math.ceil(1 / d_op - 1e-9) if d_op > 0 else 10 ** 6
    s_me, s_op = spe(me), spe(opp)
    first = 1.0 if s_me > s_op else (0.5 if s_me == s_op else 0.0)
    # priority finisher: counts as moving first on the last hit if a priority move alone does the last chunk
    if first < 1.0:
        pr = [m for m in my_moves if m in PRIORITY and (m != "extreme-speed" or True)]
        if pr and "extreme-speed" not in opp_moves:
            d_pr = max(dmg(me, m, opp) for m in pr) / hp(opp)
            if d_pr > 0 and (t_me - 1) * d_me + d_pr >= 1.0:
                first = 1.0
    if t_me < t_op or (t_me == t_op and first >= 1.0):
        hits_taken = t_me - (1 if first >= 1.0 else 0)
        return 1.0 + max(0.0, 1.0 - hits_taken * d_op)
    if t_me == t_op and first == 0.5:
        return 0.5 * (1.0 + max(0.0, 1.0 - (t_me - 1) * d_op)) + 0.5 * min(1.0, (t_op - 1) * d_me)
    turns_i_get = t_op - (0 if first >= 1.0 else 1)
    return min(0.999, turns_i_get * d_me)


def best_set(sp, moves, targets, force=None, k=12):
    """4 moves maximising sum over targets of best expected damage fraction (exhaustive over top-k moves)."""
    tl = list(targets)
    val = {m: [dmg(sp, m, t) / hp(t) for t in tl] for m in moves}
    ranked = sorted(moves, key=lambda m: -sum(val[m]))
    # keep top-k by total plus any move that is the single best vs some target
    keep = list(ranked[:k])
    for i in range(len(tl)):
        b = max(moves, key=lambda m: val[m][i])
        if b not in keep:
            keep.append(b)
    force = [f for f in (force or []) if f in moves]
    for f in force:
        if f not in keep:
            keep.append(f)
    best, bs = None, -1
    for combo in itertools.combinations(keep, 4):
        if any(f not in combo for f in force):
            continue
        s = sum(min(1.0, max(val[m][i] for m in combo)) for i in range(len(tl)))
        s += 1e-3 * sum(sum(val[m]) for m in combo)  # tie-break: generally stronger moves
        if s > bs:
            best, bs = combo, s
    # order: strongest total first (the baseline breaks >=100-damage ties by lowest index)
    return sorted(best, key=lambda m: -sum(val[m]))


def main():
    cyn = cynthia_targets()
    species = legal_species()
    broad = [s for s, _ in species if D.pokemon[s].fully_evolved and D.costs[s] >= 7]
    pool = {}
    for sp, moves in species:
        sets = []
        a = best_set(sp, moves, cyn)
        sets.append(a)
        b = best_set(sp, moves, broad)
        if set(b) != set(a):
            sets.append(b)
        pr = [m for m in moves if m in PRIORITY]
        if pr:
            bp = max(pr, key=lambda m: (D.moves[m].type in D.pokemon[sp].types, D.moves[m].power))
            for base in (cyn, broad):
                c = best_set(sp, moves, base, force=[bp])
                if all(set(c) != set(x) for x in sets):
                    sets.append(c)
        sc = [sum(duel(sp, s, t, tm) for t, tm in cyn.items()) for s in sets]
        gen = [sum(max(dmg(sp, m, t) for m in s) / hp(t) for t in broad) / len(broad) for s in sets]
        pool[sp] = {"cost": D.costs[sp], "sets": sets, "duel_vs_cynthia": [round(x, 3) for x in sc],
                    "mean_dmg_frac_broad": [round(x, 3) for x in gen], "spe": spe(sp), "hp": hp(sp),
                    "priority": pr}
    json.dump(pool, open("results/pool.json", "w"), indent=1)
    rank = sorted(pool, key=lambda s: -max(pool[s]["duel_vs_cynthia"]))
    print("species:", len(pool))
    for s in rank[:45]:
        p = pool[s]
        print(f"{s:12s} cost {p['cost']:2d} duel {max(p['duel_vs_cynthia']):5.2f} gen {max(p['mean_dmg_frac_broad']):.2f} {p['sets'][0]}")
    print("--- best per cost (duel/cost) ---")
    for c in range(1, 8):
        r = sorted((s for s in pool if pool[s]["cost"] == c), key=lambda s: -max(pool[s]["duel_vs_cynthia"]))[:8]
        print(c, [(s, round(max(pool[s]["duel_vs_cynthia"]), 2)) for s in r])


if __name__ == "__main__":
    main()

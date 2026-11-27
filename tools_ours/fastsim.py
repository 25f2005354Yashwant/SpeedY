"""L0 fast team screen: whole battles inside the policy's own simulator (exact damage tables + Cynthia clone)
with a greedy player (the rollout default policy).  ~1000x cheaper than engine + rollout policy.
Used only to propose candidate teams; ranking is always done with real engine battles.

  python -m tools_ours.fastsim check TEAM OPP N      compare L0 with the real engine (same greedy player)
  python -m tools_ours.fastsim eval TEAM [N]         L0 win rates vs the main opponents
"""
import json
import sys
import time

from harness import core
from tools_ours.test_policy import load_dev

import os
DEV = os.environ.get("FASTSIM_DEV", "policy_src/build/policy_dev.py")
_P = None


def P():
    global _P
    if _P is None:
        core._init()
        _P = load_dev(DEV)
    return _P


def my_state(team, her_lead_species):
    D = core._state["data"]
    from engine.stats import calc_stats
    mons = []
    for i, m in enumerate(team):
        p = D.pokemon[m["species"]]
        st = calc_stats(p)
        mons.append({"index": i, "species": m["species"], "types": list(p.types), "stats": st, "current_hp": st["hp"],
                     "max_hp": st["hp"], "fainted": False,
                     "moves": [{"identifier": x, "pp": D.moves[x].pp, "power": D.moves[x].power,
                                "accuracy": D.moves[x].accuracy, "type": D.moves[x].type,
                                "category": D.moves[x].category} for x in m["moves"]]})
    hp = D.pokemon[her_lead_species]
    return {"turn": 1, "active_pokemon": mons[0], "bench": mons[1:],
            "opponent_active": {"species": her_lead_species, "types": list(hp.types), "hp_percent": 100.0,
                                "known_moves": []},
            "opponent_remaining_count": 6, "legal_actions": [], "battle_history": []}


_cfg_cache = {}


def opp_cfg(opp):
    if opp not in _cfg_cache:
        _cfg_cache[opp] = json.load(open(core.opp_path(opp)))
    return _cfg_cache[opp]


def build(team, opp):
    """Tables for my team vs the opponent config; returns (B, mh, oh, rv, pp)."""
    p = P()
    D = core._state["data"]
    cfg = opp_cfg(opp)
    her = cfg["team"]
    st = my_state(team, her[0]["species"])
    p._parse(st)
    p.G["her"] = {m["species"]: {"hp": None, "mv": list(m["moves"]),
                                 "pp": {x: D.moves[x].pp for x in m["moves"]}} for m in her}
    p.G["order"] = []
    B, mh, oh, ma, oa, rv, pp = p._setup(st)
    style = cfg.get("style", "balanced")
    dg = float(cfg.get("danger_threshold", 0.6))
    if style == "aggressive":
        dg = 9.0
    elif style == "patient":
        dg -= 0.15
    B["dg"], B["wk"], B["cm"] = dg, float(cfg.get("weak_offense_threshold", 0.4)), int(cfg.get("switch_cooldown", 3))
    B["mh"] = (float(cfg.get("aggression", 1.0)), 0.15 if style == "aggressive" else 0.0,
               float(cfg.get("priority_weight", 1.0)))
    clo = cfg.get("closer_species", "garchomp")
    B["clo"] = [m["species"] == clo for m in her]
    return B, mh, oh, rv, pp


def l0(team, opp, n, seed0=1):
    """Greedy-vs-clone win rate over n simulated battles (her lead uniform; boss mode on 30% for `policy`)."""
    p = P()
    B, mh, oh, rv, pp = build(team, opp)
    wins = 0
    turns = 0
    for s in range(seed0, seed0 + n):
        oa = (s * 2654435761 >> 7) % 6
        B["boss"] = (opp == "policy") and ((s * 40503 >> 3) % 10 < 3)
        a0 = (0, p._mine(B, 0, oa, oh[oa], mh[0]))
        v = p._roll(B, mh, oh, 0, oa, 0, rv, pp, 1, a0, s)
        if v > 0.5:
            wins += 1
    return wins / n


def greedy_policy():
    """Real-engine policy = the simulator's default player (for the fidelity check)."""
    p = P()

    def pol(state):
        legal = state["legal_actions"]
        p._parse(state)
        B, mh, oh, ma, oa, rv, pp = p._setup(state)
        if mh[ma] <= 0:
            c = p._myrep(B, mh, oa, max(1, oh[oa]))
            return {"action": "switch", "index": c}
        if any(a["action"] == "struggle" for a in legal):
            return {"action": "struggle"}
        k = p._mine(B, ma, oa, oh[oa], mh[ma])
        a = {"action": "move", "index": k}
        return a if a in legal else [x for x in legal if x["action"] == "move"][0]
    return pol


def main():
    cmd = sys.argv[1]
    team = core.load_team(sys.argv[2])
    if cmd == "check":
        opp, n = sys.argv[3], int(sys.argv[4])
        pol = greedy_policy()
        t = time.time()
        w = sum(core.play(team, opp, core.TUNE_BASE + s, pol)["win"] for s in range(n))
        t1 = time.time() - t
        t = time.time()
        r = l0(team, opp, 4000)
        print(f"{opp}: real engine + greedy {100 * w / n:.1f}% (n={n}, {t1:.0f}s) | L0 sim {100 * r:.1f}% "
              f"(n=4000, {time.time() - t:.1f}s)")
    else:
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
        t = time.time()
        res = {o: l0(team, o, n) for o in ("policy", "public", "t_aggr", "t_patient", "t_sinnoh", "t_mixed")}
        print({o: round(100 * v, 1) for o, v in res.items()}, f"{time.time() - t:.1f}s")


if __name__ == "__main__":
    main()

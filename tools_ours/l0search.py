"""Large-scale team search in the L0 fast simulator (greedy player vs exact Cynthia clone).
Produces candidate teams only; every candidate is re-ranked with real engine battles afterwards.

usage: python -m tools_ours.l0search --tag NAME --minutes 40 --chains 3 [--seed 1] [--start team.json]
output: results/l0/NAME/chain_<k>.jsonl  (one line per accepted team: objective + per-opponent rates + team)
"""
import argparse
import json
import multiprocessing as mp
import random
import time
from pathlib import Path

from harness import core

WB = {"public": 1 / 3, "t_aggr": 1 / 3, "t_patient": 1 / 3}  # team-only track (baseline clone)
# team-only, robust: 75 % Cynthia-team variants, 25 % different-team TUNE stand-ins (held-out h_* never used)
WBR = {"public": 0.25, "t_aggr": 0.25, "t_patient": 0.25, "t_fastphys": 0.05, "t_icerock": 0.05, "t_water": 0.04,
       "t_mixed": 0.04, "t_bulky": 0.04, "t_boss": 0.03}
W = {"policy": 0.35, "t_aggr": 0.20, "t_patient": 0.15, "t_sinnoh": 0.10, "t_mixed": 0.10, "t_altmoves": 0.10}
N1, N2 = 150, 600


def chain(args):
    k, seed, minutes, tag, start, mode = args
    from tools_ours import fastsim, basesim
    sim = basesim.l0 if mode in ('base', 'baser') else fastsim.l0
    W = {'base': WB, 'baser': WBR}.get(mode, globals()['W'])
    N1, N2 = (100, 400) if mode == 'base' else ((80, 320) if mode == 'baser' else (150, 600))
    from tools_ours.search import Mutator
    rng = random.Random(seed * 7919 + k)
    mut = Mutator(rng, top=170)
    out = open(Path("results/l0") / tag / f"chain_{k}.jsonl", "a")
    cache = {}

    def ev(team, n):
        key = (json.dumps(team, sort_keys=True), n)
        if key not in cache:
            d = {o: sim(team, o, n) for o in W}
            cache[key] = (sum(W[o] * d[o] for o in W), d)
            if len(cache) > 4000:
                for kk in list(cache)[:2000]:
                    del cache[kk]
        return cache[key]

    deadline = time.time() + minutes * 60
    restart = 0
    while time.time() < deadline:
        cur = core.load_team(start) if (start and restart == 0 and k == 0) else mut.random_team()
        restart += 1
        stale = 0
        tries = 0
        temp = 0.004
        while time.time() < deadline and stale < 500:
            cand, desc = mut.mutate(cur)
            if cand is None or not core.validate(cand)[0]:
                continue
            tries += 1
            c1, _ = ev(cand, N1)
            b1, _ = ev(cur, N1)
            if c1 < b1 - 0.012:
                stale += 1
                continue
            c2, d2 = ev(cand, N2)
            b2, _ = ev(cur, N2)
            # accept clear improvements; small annealing temperature lets neutral moves through occasionally
            if c2 > b2 + 0.003 or (c2 > b2 - temp and rng.random() < 0.15):
                if c2 > b2 + 0.003:
                    stale = 0
                cur = cand
                out.write(json.dumps({"obj": round(c2, 4), "d": {o: round(v, 3) for o, v in d2.items()},
                                      "cost": mut.tcost(cur), "restart": restart, "tries": tries, "desc": desc,
                                      "t": time.strftime("%H:%M:%S"), "team": cur}) + "\n")
                out.flush()
            else:
                stale += 1
    return k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--chains", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--start", default=None)
    ap.add_argument("--mode", default="greedy", choices=["greedy", "base", "baser"])
    a = ap.parse_args()
    (Path("results/l0") / a.tag).mkdir(parents=True, exist_ok=True)
    with mp.get_context("fork").Pool(a.chains) as pool:
        pool.map(chain, [(k, a.seed, a.minutes, a.tag, a.start, a.mode) for k in range(a.chains)])
    print("done")


if __name__ == "__main__":
    main()

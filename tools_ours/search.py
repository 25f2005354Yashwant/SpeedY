"""Phase 3.3 — simulation-driven team search (stochastic hill-climb with racing + paired CRN tests).

Every candidate is compared with the incumbent on the SAME seeds (common random numbers).  Racing:
  stage 1  n=40   continue if paired mean diff > -0.01
  stage 2  n=160  continue if z > 0.8
  stage 3  n=600  accept if z > 1.96 (95% paired CI excludes 0); if 1.0 < z <= 1.96 go to stage 4
  stage 4  n=1500 accept if z > 1.96
Checkpoints the incumbent after every accepted change; appends to a log file.

usage:
  python -m tools_ours.search --tag NAME --objective pdf|robust [--policy P.py] [--start team.json]
                              [--minutes 60] [--seed 1] [--restarts 1]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path

from harness import core

OBJ = {
    "pdf": {"public": 1 / 3, "t_aggr": 1 / 3, "t_patient": 1 / 3},
    "robust": {"public": 0.25, "t_aggr": 0.25, "t_patient": 0.25,
               "t_altmoves": 0.0625, "t_sinnoh": 0.0625, "t_boss": 0.0625, "t_mixed": 0.0625},
    # policy entries: the "public" slot is assumed to be the boss `policy` variant (worst case, see RULES_DECISION)
    "zip_policy": {"policy": 0.34, "t_aggr": 0.33, "t_patient": 0.33},
    "pol3": {"policy": 0.3, "public": 0.2, "t_aggr": 0.3, "t_patient": 0.2},
    # policy track, robust: boss + behaviour stand-ins + two different-team tune stand-ins
    "pol5": {"policy": 0.30, "t_aggr": 0.25, "t_patient": 0.15, "t_sinnoh": 0.15, "t_mixed": 0.15},
    "robust_policy": {"policy": 0.17, "public": 0.13, "t_aggr": 0.225, "t_patient": 0.225,
                      "t_altmoves": 0.0625, "t_sinnoh": 0.0625, "t_boss": 0.0625, "t_mixed": 0.0625},
}
STAGES = [40, 160, 600, 1500]


class Evaluator:
    def __init__(self, weights, policy=None, base=core.TUNE_BASE):
        self.w = weights
        self.opps = list(weights)
        self.policy = policy
        self.base = base
        self.cache = {}
        self.battles = 0

    @staticmethod
    def key(team):
        return json.dumps(team, sort_keys=True)

    def rows(self, team, n):
        """per-opponent list of win flags for seeds base..base+n-1 (extends cached prefix)."""
        k = self.key(team)
        cur = self.cache.setdefault(k, {o: [] for o in self.opps})
        have = len(cur[self.opps[0]])
        if have < n:
            seeds = range(self.base + have, self.base + n)
            res = core.run_jobs([(team, o, seeds, self.policy) for o in self.opps])
            for o, r in zip(self.opps, res):
                cur[o].extend((x[0], x[1]) for x in r)
            self.battles += (n - have) * len(self.opps)
        return cur

    def vec(self, team, n):
        cur = self.rows(team, n)
        return [sum(self.w[o] * cur[o][i][0] for o in self.opps) for i in range(n)]

    def mean(self, team, n):
        v = self.vec(team, n)
        return sum(v) / n

    def detail(self, team, n):
        cur = self.rows(team, n)
        return {o: sum(x[0] for x in cur[o][:n]) / n for o in self.opps}

    def turns(self, team, n):
        cur = self.rows(team, n)
        t = [x[1] for o in self.opps for x in cur[o][:n] if x[0]]
        return sum(t) / len(t) if t else 0.0

    def forget(self, team):
        self.cache.pop(self.key(team), None)


def paired(a, b):
    n = len(a)
    d = [x - y for x, y in zip(a, b)]
    m = sum(d) / n
    var = sum((x - m) ** 2 for x in d) / max(1, n - 1)
    se = math.sqrt(var / n)
    return m, (m / se if se > 0 else (0.0 if m == 0 else math.copysign(99.0, m)))


class Mutator:
    def __init__(self, rng, pool_path="results/pool.json", top=150):
        core._init()
        self.D = core._state["data"]
        self.rng = rng
        self.pool = json.load(open(pool_path))
        rank = sorted(self.pool, key=lambda s: -max(self.pool[s]["duel_vs_cynthia"]))
        keep = set(rank[:top])
        # make sure cheap fillers exist: best 10 of each cost 1..5
        for c in range(1, 6):
            keep.update([s for s in rank if self.pool[s]["cost"] == c][:10])
        self.species = sorted(keep)
        self.weight = {s: 1.0 + 3.0 * (1 - rank.index(s) / len(rank)) ** 2 for s in self.species}
        self.cost = self.D.costs
        self.moves_of = {}
        for s in self.species:
            mv = [m for m in self.D.learnsets[s] if self.D.is_move_supported(m)]
            p = self.D.pokemon[s]

            def val(m):
                x = self.D.moves[m]
                if x.identifier in ("fissure", "sheer-cold", "guillotine", "horn-drill"):
                    return 40.0 * max(p.attack, p.sp_atk)
                pw = (x.power or 0) * (3 if (x.max_hits or 1) > 1 else 1)
                st = p.attack if x.category == "physical" else p.sp_atk
                return pw * ((x.accuracy or 100) / 100) * st * (1.5 if x.type in p.types else 1) + (
                    2000 if x.priority > 0 else 0)
            self.moves_of[s] = sorted(mv, key=lambda m: -val(m))[:16]

    def tcost(self, team):
        return sum(self.cost[m["species"]] for m in team)

    def pick_species(self, exclude, max_cost, min_cost=1):
        c = [s for s in self.species if s not in exclude and min_cost <= self.cost[s] <= max_cost]
        if not c:
            return None
        return self.rng.choices(c, weights=[self.weight[s] for s in c])[0]

    def mon(self, s):
        return {"species": s, "moves": list(self.rng.choice(self.pool[s]["sets"]))}

    def random_team(self):
        for _ in range(1000):
            team, used, budget = [], set(), 40
            for i in range(6):
                left = 5 - i
                s = self.pick_species(used, budget - left)  # keep >=1 point per remaining slot
                if s is None:
                    break
                team.append(self.mon(s))
                used.add(s)
                budget -= self.cost[s]
            if len(team) == 6 and self.tcost(team) >= 36:
                self.rng.shuffle(team)
                return team
        raise RuntimeError("no random team")

    def mutate(self, team):
        t = [{"species": m["species"], "moves": list(m["moves"])} for m in team]
        r = self.rng.random()
        used = {m["species"] for m in t}
        spare = 40 - self.tcost(t)
        if r < 0.30:  # swap one species
            i = self.rng.randrange(6)
            s = self.pick_species(used, self.cost[t[i]["species"]] + spare)
            if s is None:
                return None, ""
            t[i] = self.mon(s)
            return t, f"species[{i}] {team[i]['species']}->{s}"
        if r < 0.45:  # swap two species (lets the cost split move)
            i, j = self.rng.sample(range(6), 2)
            budget = self.cost[t[i]["species"]] + self.cost[t[j]["species"]] + spare
            s1 = self.pick_species(used, budget - 1)
            if s1 is None:
                return None, ""
            rem = budget - self.cost[s1]
            s2 = self.pick_species(used | {s1}, rem, min_cost=max(1, rem - 2))
            if s2 is None:
                return None, ""
            t[i], t[j] = self.mon(s1), self.mon(s2)
            return t, f"species2 {team[i]['species']},{team[j]['species']}->{s1},{s2}"
        if r < 0.55:  # other pool moveset
            i = self.rng.randrange(6)
            sets = [s for s in self.pool[t[i]["species"]]["sets"] if set(s) != set(t[i]["moves"])]
            if not sets:
                return None, ""
            t[i]["moves"] = list(self.rng.choice(sets))
            return t, f"set[{t[i]['species']}]"
        if r < 0.80:  # one move
            i = self.rng.randrange(6)
            s = t[i]["species"]
            cand = [m for m in self.moves_of.get(s, []) if m not in t[i]["moves"]]
            if not cand:
                return None, ""
            j = self.rng.randrange(4)
            new = self.rng.choice(cand)
            old = t[i]["moves"][j]
            t[i]["moves"][j] = new
            return t, f"move[{s}] {old}->{new}"
        if r < 0.88:  # move order (the baseline breaks ties by lowest index)
            i = self.rng.randrange(6)
            a, b = self.rng.sample(range(4), 2)
            mv = t[i]["moves"]
            mv[a], mv[b] = mv[b], mv[a]
            return t, f"moveorder[{t[i]['species']}] {a}<->{b}"
        a, b = self.rng.sample(range(6), 2)  # team order / lead
        t[a], t[b] = t[b], t[a]
        return t, f"order {a}<->{b}"


def climb(ev, mut, team, log, ckpt, deadline, rng):
    cur = team
    ok, errs = core.validate(cur)
    assert ok, errs
    n_acc = n_try = 0
    log(f"START cost={mut.tcost(cur)} obj@160={ev.mean(cur, 160):.4f} {json.dumps(cur)}")
    seen = set()
    while time.time() < deadline:
        cand, desc = mut.mutate(cur)
        if cand is None:
            continue
        k = ev.key(cand)
        if k in seen:
            continue
        seen.add(k)
        if not core.validate(cand)[0]:
            continue
        n_try += 1
        accepted = False
        for si, n in enumerate(STAGES):
            m, z = paired(ev.vec(cand, n), ev.vec(cur, n))
            if si == 0 and m <= -0.01:
                break
            if si == 1 and z <= 0.8:
                break
            if si == 2:
                if z > 1.96:
                    accepted = True
                    break
                if z <= 1.0:
                    break
            if si == 3:
                accepted = z > 1.96
        if accepted:
            n_acc += 1
            ev.forget(cur) if n_acc % 5 == 0 else None
            cur = cand
            nn = len(ev.rows(cur, 0)[ev.opps[0]])
            log(f"ACCEPT #{n_acc} (try {n_try}, n={n}, d={m:+.4f}, z={z:.2f}) {desc} | obj@{nn}={ev.mean(cur, nn):.4f} "
                f"{ {o: round(v, 3) for o, v in ev.detail(cur, nn).items()} } cost={mut.tcost(cur)} "
                f"battles={ev.battles}")
            log("TEAM " + json.dumps(cur))
            Path(ckpt).write_text(json.dumps({"pokemon": cur}, indent=1))
        else:
            ev.forget(cand)
        if n_try % 50 == 0:
            log(f".. tries={n_try} accepts={n_acc} battles={ev.battles}")
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--objective", default="pdf", choices=list(OBJ))
    ap.add_argument("--policy", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--restarts", type=int, default=1)
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--stages", default="40,160,600,1500")
    a = ap.parse_args()

    global STAGES
    STAGES = [int(x) for x in a.stages.split(",")]
    assert len(STAGES) == 4 and all(x % 10 == 0 for x in STAGES)
    out = Path("results/search") / a.tag
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "log.txt", "a")

    def log(s):
        logf.write(time.strftime("%H:%M:%S ") + s + "\n")
        logf.flush()

    log(f"=== search tag={a.tag} objective={a.objective} policy={a.policy} seed={a.seed} minutes={a.minutes} "
        f"restarts={a.restarts} procs={core.N_PROCS}")
    for r in range(a.restarts):
        rng = random.Random(a.seed * 1000 + r)
        mut = Mutator(rng, top=a.top)
        ev = Evaluator(OBJ[a.objective], policy=a.policy)
        team = core.load_team(a.start) if (a.start and r == 0) else mut.random_team()
        ck = out / f"best_r{r}.json"
        log(f"--- restart {r}")
        best = climb(ev, mut, team, log, ck, time.time() + a.minutes * 60, rng)
        ck.write_text(json.dumps({"pokemon": best}, indent=1))
        nn = STAGES[2]
        log(f"END restart {r} obj@{nn}={ev.mean(best, nn):.4f} turns={ev.turns(best, nn):.2f} {json.dumps(best)}")


if __name__ == "__main__":
    main()

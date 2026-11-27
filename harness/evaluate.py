"""CLI evaluation with common random numbers.

  python -m harness.evaluate --team T.json [--policy P.py] --objective pdf|zip|robust --n 1000 [--final] [--set tune|heldout|all]

Objectives (H1/H2 = our stand-ins for the hidden aggressive/patient variants, `t_aggr` / `t_patient`):
  pdf    : mean(public, H1, H2)                     team-only, baseline policy
  zip    : 0.34*P + 0.33*H1 + 0.33*H2               P = `policy` boss variant if a policy is given, else `public`
  robust : 0.5*zip-style objective + 0.5*mean(wide stand-ins of the chosen set)
"""
from __future__ import annotations

import argparse
import json
import time

from harness import core

H1, H2 = "t_aggr", "t_patient"
SAME_TEAM = ["offensive", "defensive", "speed", "status"]


def standin_sets():
    s = json.load(open(core.STANDIN_DIR / "_sets.json"))
    tune = [x for x in s["tune"] if x not in (H1, H2)]
    return tune, s["heldout"]


def official_opps(with_policy: bool, assume_swap: bool = True):
    return ["policy" if (with_policy and assume_swap) else "public", H1, H2]


def score(res, objective: str, with_policy: bool, wide=(), assume_swap: bool = True):
    p, a, b = official_opps(with_policy, assume_swap)
    if objective == "pdf":
        base = (res[p]["wr"] + res[a]["wr"] + res[b]["wr"]) / 3
    else:
        base = 0.34 * res[p]["wr"] + 0.33 * res[a]["wr"] + 0.33 * res[b]["wr"]
    if objective == "robust" and wide:
        return 0.5 * base + 0.5 * sum(res[w]["wr"] for w in wide) / len(wide)
    return base


def table(res, order=None):
    lines = [f"{'opponent':20s} {'n':>5s} {'win%':>6s} {'95% CI':>15s} {'turns(win)':>10s} {'TL':>3s} {'fb':>3s} {'maxlat':>7s}"]
    for o in (order or res):
        r = res[o]
        lines.append(f"{o:20s} {r['n']:5d} {100 * r['wr']:6.1f} [{100 * r['lo']:5.1f},{100 * r['hi']:5.1f}] "
                     f"{r['turns_in_wins']:10.2f} {r['turn_limit_losses']:3d} {r['fallbacks']:3d} {r['max_lat_ms']:6.0f}ms")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--objective", default="pdf", choices=["pdf", "zip", "robust"])
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--final", action="store_true", help="use the final-test seed block (900,000,000+i)")
    ap.add_argument("--set", default="tune", choices=["tune", "heldout", "all", "none"])
    ap.add_argument("--no-swap", action="store_true", help="policy entries face `public`, not the boss variant")
    ap.add_argument("--extra", default="", help="comma list of extra opponents")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    team = core.load_team(a.team)
    ok, errs = core.validate(team)
    if not ok:
        raise SystemExit(f"ILLEGAL TEAM: {errs}")
    tune, held = standin_sets()
    wide = {"tune": tune, "heldout": held, "all": tune + held, "none": []}[a.set]
    opps = official_opps(bool(a.policy), not a.no_swap)
    extra = [x for x in a.extra.split(",") if x]
    allopps = list(dict.fromkeys(opps + (["public", "policy"] if a.policy else []) + SAME_TEAM + wide + extra))
    base = core.FINAL_BASE if a.final else core.TUNE_BASE
    t0 = time.time()
    res = core.evaluate(team, allopps, a.n, base=base, policy_path=a.policy)
    print(f"team={a.team} cost={core.team_cost(team)} policy={a.policy} seeds={base}..{base + a.n - 1} "
          f"({time.time() - t0:.0f}s)")
    print(table(res, allopps))
    for obj in ("pdf", "zip", "robust"):
        print(f"objective {obj:6s}: {100 * score(res, obj, bool(a.policy), wide, not a.no_swap):.2f}")
    if wide:
        print(f"wide mean ({a.set}): {100 * sum(res[w]['wr'] for w in wide) / len(wide):.2f}")
    if a.json:
        for r in res.values():
            r.pop("rows", None)
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()

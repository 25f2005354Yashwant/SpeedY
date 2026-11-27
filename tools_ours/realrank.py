"""Rank candidate teams (results/l0/<file>.json) with REAL engine battles + a policy, common seeds.
usage: python -m tools_ours.realrank results/l0/top.json POLICY N [opp,opp,...] [first:last]"""
import json, sys
from harness import core

def main():
    cands = json.load(open(sys.argv[1])); pol = sys.argv[2]; n = int(sys.argv[3])
    opps = sys.argv[4].split(",") if len(sys.argv) > 4 else ["policy", "t_aggr", "t_patient", "t_sinnoh"]
    if len(sys.argv) > 5:
        a, b = sys.argv[5].split(":"); cands = cands[int(a):int(b)]
    seeds = range(core.TUNE_BASE, core.TUNE_BASE + n)
    jobs = [(c["team"], o, seeds, pol if pol != "baseline" else None) for c in cands for o in opps]
    res = core.run_jobs(jobs)
    k = 0; rows = []
    for c in cands:
        d = {}
        for o in opps:
            d[o] = core.summarise(res[k])["wr"]; k += 1
        c["real"] = {o: round(v, 3) for o, v in d.items()}
        c["real_mean"] = round(sum(d.values()) / len(d), 4)
        rows.append(c)
    rows.sort(key=lambda c: -c["real_mean"])
    for c in rows:
        print(c["real_mean"], c["real"], "L0", c.get("l0"), [m["species"] for m in c["team"]], flush=True)
    json.dump(rows, open(sys.argv[1].replace(".json", f"_real{n}.json"), "w"), indent=1)

if __name__ == "__main__":
    main()

"""Collect the best L0 teams of one or more runs, re-score them on fresh L0 seeds, write results/l0/<out>.json.
usage: python -m tools_ours.l0top OUT K run1 [run2 ...]"""
import glob, json, sys
from harness import core
from tools_ours import fastsim
from tools_ours.l0search import W

def main():
    global W
    base = "--base" in sys.argv or "--baser" in sys.argv
    args = [x for x in sys.argv[1:] if x not in ("--base", "--baser")]
    out, K, runs = args[0], int(args[1]), args[2:]
    sim = fastsim.l0
    if base:
        from tools_ours import basesim
        from tools_ours.l0search import WB, WBR
        W = WBR if "--baser" in sys.argv else WB
        sim = basesim.l0
    cands = []
    for r in runs:
        for f in sorted(glob.glob(f"results/l0/{r}/chain_*.jsonl")):
            seen = {}
            for line in open(f):
                d = json.loads(line)
                k = json.dumps(sorted(d["team"], key=lambda m: m["species"]), sort_keys=True)
                if k not in seen or d["obj"] > seen[k]["obj"]:
                    seen[k] = d
            cands += sorted(seen.values(), key=lambda d: -d["obj"])[:12]  # best per chain
    res = []
    for d in cands:
        dd = {o: sim(d["team"], o, 2000, seed0=500000) for o in W}
        res.append({"l0": round(sum(W[o] * dd[o] for o in W), 4), "d": {o: round(v, 3) for o, v in dd.items()},
                    "search_obj": d["obj"], "team": d["team"]})
    res.sort(key=lambda d: -d["l0"])
    # keep diverse teams: skip teams sharing >= 5 species with an already kept, better team
    kept = []
    for d in res:
        sp = {m["species"] for m in d["team"]}
        if all(sp != {m["species"] for m in k["team"]} for k in kept):
            kept.append(d)
        if len(kept) >= K:
            break
    json.dump(kept, open(f"results/l0/{out}.json", "w"), indent=1)
    for i, d in enumerate(kept):
        print(i, d["l0"], d["search_obj"], d["d"], [m["species"] for m in d["team"]])

if __name__ == "__main__":
    main()

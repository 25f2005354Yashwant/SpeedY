"""Paired comparison of (team, policy) entries on identical seeds.
usage: python -m tools_ours.cmp N OPP1,OPP2 team1[:policy1] team2[:policy2] ... [--final]"""
import sys
from harness import core
from tools_ours.search import paired

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]); opps = args[1].split(","); entries = [a.split(":") + [None] for a in args[2:]]
    base = core.FINAL_BASE if "--final" in sys.argv else core.TUNE_BASE
    seeds = range(base, base + n)
    jobs = [(e[0], o, seeds, e[1]) for e in entries for o in opps]
    res = core.run_jobs(jobs)
    k = 0; vecs = []
    for e in entries:
        v = [0.0] * n; line = []
        for o in opps:
            s = core.summarise(res[k]); k += 1
            line.append(f"{o} {100*s['wr']:.1f} [{100*s['lo']:.0f},{100*s['hi']:.0f}] t={s['turns_in_wins']:.1f} lat={s['mean_lat_ms']:.0f}/{s['max_lat_ms']:.0f}ms fb={s['fallbacks']}")
            for i, r in enumerate(res[k-1]): v[i] += r[0] / len(opps)
        vecs.append(v)
        print(f"{e[0]} | {e[1]}\n   mean {100*sum(v)/n:.1f} | " + " | ".join(line), flush=True)
    for i in range(1, len(entries)):
        m, z = paired(vecs[i], vecs[0])
        print(f"entry{i} - entry0: {100*m:+.2f} pts  z={z:.2f}")

if __name__ == "__main__":
    main()

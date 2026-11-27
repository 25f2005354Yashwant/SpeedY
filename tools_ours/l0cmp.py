"""Compare default-player variants in the L0 simulator: python -m tools_ours.l0cmp DEV1 DEV2 ... -- team1 team2 ..."""
import os, subprocess, sys, json
if len(sys.argv) > 1 and sys.argv[1] == "_one":
    from tools_ours import fastsim
    from harness import core
    opps = ["policy", "public", "t_aggr", "t_patient", "defensive", "t_sinnoh", "t_mixed"]
    out = {}
    for t in sys.argv[2:]:
        team = core.load_team(t)
        out[t] = [round(100 * fastsim.l0(team, o, 3000), 1) for o in opps]
    print(json.dumps(out))
else:
    i = sys.argv.index("--")
    devs, teams = sys.argv[1:i], sys.argv[i + 1:]
    print("opps: policy public t_aggr t_patient defensive t_sinnoh t_mixed")
    for d in devs:
        r = subprocess.run([sys.executable, "-m", "tools_ours.l0cmp", "_one"] + teams, env=dict(os.environ, FASTSIM_DEV=d),
                           capture_output=True, text=True)
        res = json.loads(r.stdout.strip().splitlines()[-1])
        print(d)
        for t, v in res.items():
            print(f"   {t:40s} {v}  mean {sum(v)/len(v):.1f}")

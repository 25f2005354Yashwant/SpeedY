"""Prove the memoised harness is bit-identical to the stock engine.

Reference = organisers' `engine.runner.run_battle(debug=True)` in a process WITHOUT harness.fast.
Candidate = `harness.core.play(debug=True)` WITH harness.fast, in a different process.
Compares SHA-256 of the full JSON debug log + result for every battle.

usage: python -m harness.prove_identical [n_per_config]
"""
import hashlib
import json
import subprocess
import sys

TEAMS = {
    "best": "examples/best_team.json",
    "example": "examples/team_example.json",
    "eval1000": [
        {"species": "weavile", "moves": ["ice-punch", "night-slash", "brick-break", "aerial-ace"]},
        {"species": "starmie", "moves": ["surf", "thunderbolt", "ice-beam", "psychic"]},
        {"species": "gengar", "moves": ["shadow-ball", "thunderbolt", "energy-ball", "focus-blast"]},
        {"species": "gyarados", "moves": ["waterfall", "ice-fang", "earthquake", "bite"]},
        {"species": "swinub", "moves": ["ice-shard", "earthquake", "ice-beam", "take-down"]},
        {"species": "pichu", "moves": ["thunderbolt", "iron-tail", "shock-wave", "charge-beam"]},
    ],
    "multihit_recoil": [
        {"species": "cloyster", "moves": ["spike-cannon", "surf", "ice-beam", "aurora-beam"]},
        {"species": "staraptor", "moves": ["brave-bird", "take-down", "aerial-ace", "quick-attack"]},
        {"species": "breloom", "moves": ["bullet-seed", "drain-punch", "giga-drain", "mach-punch"]},
        {"species": "heracross", "moves": ["fury-attack", "megahorn", "brick-break", "night-slash"]},
        {"species": "pichu", "moves": ["volt-tackle", "thunderbolt", "thunder", "thunder-punch"]},
        {"species": "swinub", "moves": ["ice-shard", "earthquake", "fissure", "icicle-spear"]},
    ],
}
# (variant, policy file or None).  run_battle swaps public->policy itself when a policy is given.
CONFIGS = [("public", None), ("offensive", None), ("defensive", None), ("speed", None), ("status", None),
           ("policy", None), ("policy", "examples/best_policy.py"), ("policy", "examples/example_policy.py")]


def digest(mode, n):
    out = {}
    if mode == "stock":
        from engine.runner import run_battle
        from engine.policy import load_policy_from_source
        for tname, team in TEAMS.items():
            if isinstance(team, str):
                team = json.load(open(team))
            for var, pol in CONFIGS:
                fn = load_policy_from_source(open(pol).read(), sandbox=False) if pol else None
                for s in range(n):
                    r = run_battle(team, seed=7000 + s, variant=var, policy=fn, debug=True)
                    blob = json.dumps([r["result"], r["turns"], r["end_reason"], r["log"]], sort_keys=True)
                    out[f"{tname}|{var}|{pol}|{s}"] = hashlib.sha256(blob.encode()).hexdigest()
    else:
        from harness import core
        for tname, team in TEAMS.items():
            team = core.load_team(team)
            ok, err = core.validate(team)
            assert ok, err
            for var, pol in CONFIGS:
                fn = core.get_policy(pol)
                for s in range(n):
                    r = core.play(team, var, 7000 + s, fn, debug=True)
                    blob = json.dumps(["win" if r["win"] else "loss", r["turns"], r["end_reason"], r["log"]],
                                      sort_keys=True)
                    out[f"{tname}|{var}|{pol}|{s}"] = hashlib.sha256(blob.encode()).hexdigest()
    return out


if __name__ == "__main__":
    if len(sys.argv) > 2:
        print(json.dumps(digest(sys.argv[1], int(sys.argv[2]))))
        sys.exit(0)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    procs = [subprocess.Popen([sys.executable, "-m", "harness.prove_identical", m, str(n)], stdout=subprocess.PIPE,
                              text=True) for m in ("stock", "fast")]
    a, b = [json.loads(p.communicate()[0]) for p in procs]
    assert a.keys() == b.keys()
    bad = [k for k in a if a[k] != b[k]]
    print(f"battles compared: {len(a)}  mismatches: {len(bad)}")
    for k in bad[:10]:
        print("  MISMATCH", k)
    sys.exit(1 if bad else 0)

"""Install a candidate into submission/<track>/ after validating it.

usage:
  python -m tools_ours.finalize team_only  path/to/team.json
  python -m tools_ours.finalize with_policy path/to/team.json path/to/policy.py
Checks: validator (6 distinct species, 4 legal supported moves, cost <= 40, no legendary/mythical, base forms),
policy `--check` in the real subprocess sandbox, policy size < 31,000 bytes, a few sandboxed battles with 0 fallbacks.
"""
import json
import shutil
import sys
from pathlib import Path

from harness import core


def main():
    track = sys.argv[1]
    assert track in ("team_only", "with_policy")
    team = core.load_team(sys.argv[2])
    ok, errs = core.validate(team)
    if not ok:
        raise SystemExit(f"ILLEGAL TEAM: {errs}")
    D = core._state["data"]
    assert len({m["species"] for m in team}) == 6
    for m in team:
        p = D.pokemon[m["species"]]
        assert p.is_default_form and not p.is_legendary and not p.is_mythical and p.generation <= 4, m
        assert len(m["moves"]) == 4 and len(set(m["moves"])) == 4
        for mv in m["moves"]:
            assert mv in D.learnsets[m["species"]] and D.is_move_supported(mv), (m["species"], mv)
    out = Path("submission") / track
    out.mkdir(parents=True, exist_ok=True)
    name = "Doom Warriors"
    (out / "team.json").write_text(json.dumps({"team_name": name, "pokemon": team}, indent=2) + "\n")
    print(f"[{track}] team OK  cost={core.team_cost(team)}/40")
    for m in team:
        print(f"   {m['species']:12s} ({D.costs[m['species']]:2d})  {', '.join(m['moves'])}")
    print(f"   team.json sha1 = {core.sha1(out / 'team.json')}")
    if track == "with_policy":
        src = Path(sys.argv[3])
        size = len(src.read_bytes())
        assert size < 31000, f"policy too big: {size}"
        shutil.copyfile(src, out / "policy.py")
        from engine.policy import check_policy_file, load_policy_callable
        from engine.runner import run_battle
        chk = check_policy_file(out / "policy.py")
        print(f"   policy.py {size} bytes  check={chk}")
        assert chk["valid"], chk
        pol = load_policy_callable(out / "policy.py", sandbox=True)
        fb = 0
        wins = 0
        try:
            for s in range(6):
                r = run_battle(team, seed=4242 + s, variant="public", policy=pol)
                fb += len(r["policy_fallbacks"])
                wins += r["result"] == "win"
            print(f"   6 sandboxed battles via engine.runner (boss variant): wins={wins} fallbacks={fb} "
                  f"cumulative policy time={pol._total_elapsed:.1f}s")
        finally:
            pol.close()
        assert fb == 0
        print(f"   policy.py sha1 = {core.sha1(out / 'policy.py')}")
    else:
        stale = out / "policy.py"
        if stale.exists():
            stale.unlink()


if __name__ == "__main__":
    main()

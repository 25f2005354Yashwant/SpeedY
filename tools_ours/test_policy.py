"""Policy unit checks.
  python -m tools_ours.test_policy damage [N]     exact damage model vs engine on N random cases (assert 0 mismatches)
  python -m tools_ours.test_policy predict TEAM OPP N   accuracy of the Cynthia-move prediction in real battles
"""
import importlib.util
import random
import sys
import time

from harness import core


def load_dev(path="policy_src/build/policy_dev.py"):
    spec = importlib.util.spec_from_file_location("policy_dev", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_damage(n=20000):
    core._init()
    D = core._state["data"]
    from engine.damage import calculate_damage
    from engine.ai_core import expected_damage
    from engine.stats import calc_stats
    P = load_dev()
    rng = random.Random(5)
    species = [p for p in D.pokemon.values() if P.PK.get(P._h(p.identifier, P.KP))]
    moves = [m for m in D.moves.values() if P.MV.get(P._h(m.identifier, P.KM))]
    assert len(species) > 250 and len(moves) > 190, (len(species), len(moves))
    bad = 0
    ebad = 0
    for it in range(n):
        a, d, m = rng.choice(species), rng.choice(species), rng.choice(moves)
        A = P._her(a.identifier, None)
        Dd = P._her(d.identifier, None)
        sa, sd = calc_stats(a), calc_stats(d)
        assert A[1:] == (sa["atk"], sa["def"], sa["spa"], sa["spd"], sa["spe"], sa["hp"]) or a.identifier == "shedinja", a
        assert A[0] == tuple(P.TI[t] for t in a.types)
        e = P._ent(A, P._mv(m.identifier), Dd)
        roll = rng.randint(85, 100)
        crit = rng.random() < 0.3
        ref = calculate_damage(a, d, m, D.type_chart, is_crit=crit, roll=roll)
        got = (e[3] if crit else e[2])[roll - 85]
        if ref != got:
            bad += 1
            if bad < 5:
                print("DMG MISMATCH", a.identifier, m.identifier, d.identifier, roll, crit, ref, got)
        ed = expected_damage(a, m, d)
        if abs(ed - e[0]) > 1e-9:
            ebad += 1
            if ebad < 5:
                print("E MISMATCH", a.identifier, m.identifier, d.identifier, ed, e[0])
    print(f"damage cases: {n}  mismatches: {bad}  expected-damage mismatches: {ebad}")
    assert bad == 0 and ebad == 0


def test_predict(team, opp, n, base=core.TUNE_BASE):
    """Play real battles with the dev policy; compare its prediction of Cynthia's action with her real action."""
    core._init()
    P = load_dev()
    team = core.load_team(team)
    Battle, CynthiaBot = core._state["Battle"], core._state["CynthiaBot"]
    tot = ok = sw_real = sw_pred = sw_ok = wins = 0
    lat = []
    for s in range(base, base + n):
        path = core.opp_path(opp)
        cyn = CynthiaBot(variant=path.stem, config_path=path)
        b = Battle(team_a=team, team_b=cyn.team_for_seed(s), seed=s, data=core._state["data"],
                   variant=("policy" if opp == "policy" else "public"))
        while not b.is_over:
            if b.needs_replacement("a"):
                o = b.observation("a")
                a = P.choose_move(o)
                b.replace("a", a["index"])
            if b.needs_replacement("b"):
                o = b.observation("b")
                a = cyn.choose_move(o)
                b.replace("b", a["index"])
            if b.is_over:
                break
            oa, ob = b.observation("a"), b.observation("b")
            t0 = time.perf_counter()
            aa = P.choose_move(oa)
            lat.append(time.perf_counter() - t0)
            ab = cyn.choose_move(ob)
            pr = P.G.get("pred")
            if pr:
                tot += 1
                real_sw = ab.get("action") == "switch"
                sw_real += real_sw
                sw_pred += pr[1]
                if real_sw and pr[1]:
                    sw_ok += 1
                    ok += 1
                elif not real_sw and not pr[1]:
                    act = b.active_mon("b")
                    names = [m.identifier for m in act.moves]
                    # predicted index refers to the policy's own move ordering for her mon
                    exp = P.RO.get(act.species)
                    pm = exp[pr[2]] if exp and 0 <= pr[2] < len(exp) else None
                    if ab.get("action") == "move" and pm == names[ab["index"]]:
                        ok += 1
            b.step(aa, ab)
        wins += b.winner == "a"
    lat.sort()
    print(f"{opp}: battles {n} wins {wins} ({100*wins/n:.1f}%)  predictions {tot} correct {ok} ({100*ok/max(1,tot):.2f}%) "
          f"real switches {sw_real} predicted {sw_pred} both {sw_ok} | latency mean {1000*sum(lat)/len(lat):.1f}ms "
          f"p95 {1000*lat[int(.95*len(lat))]:.1f}ms max {1000*lat[-1]:.1f}ms")


if __name__ == "__main__":
    if sys.argv[1] == "damage":
        test_damage(int(sys.argv[2]) if len(sys.argv) > 2 else 20000)
    else:
        test_predict(sys.argv[2], sys.argv[3], int(sys.argv[4]))

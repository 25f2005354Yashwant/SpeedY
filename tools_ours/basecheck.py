"""Action-level check of the baseline clone: python -m tools_ours.basecheck TEAM OPP N"""
import sys, collections
from harness import core
from tools_ours import fastsim, basesim

def main():
    team = core.load_team(sys.argv[1]); opp = sys.argv[2]; n = int(sys.argv[3])
    core._init(); p = fastsim.P(); base = core._state["baseline"]
    D = core._state["data"]
    stats = collections.Counter(); shown = 0
    def pol(obs):
        nonlocal shown
        real = base(obs)
        try:
            p._parse(obs)
            B, mh, oh, ma, oa, rv, pp = p._setup(obs)
            osp = obs["opponent_active"]["species"]
            HERj = p._her(osp, None)
            n_ = len(B["MY"])
            X = {"TK": [[0.0]*n_ for _ in range(6)], "A0": [[0.0]*n_ for _ in range(6)],
                 "gar": [m == "garchomp" for m in [None]*n_], "mpp": [[1]*4 for _ in range(n_)]}
            mons = {b["index"]: b for b in obs["bench"]}; mons[ma] = obs["active_pokemon"]
            for i in range(n_):
                X["gar"][i] = mons[i]["species"] == "garchomp"
                X["mpp"][i] = [m["pp"] for m in mons[i]["moves"]]
                X["TK"][oa][i] = p._ent(HERj, basesim.TACKLE, B["MY"][i])[0]
                X["A0"][oa][i] = max([p._ent(HERj, (t, 1 if t in p.SPC else 0, 90, 100, 0, 0, 1, 0), B["MY"][i])[0] for t in HERj[0]] or [0.0])
            hn = p.G["hn"][oa]
            kh = [hn.index(m) for m in obs["opponent_active"]["known_moves"] if m in hn]
            nopp = obs["opponent_remaining_count"]
            if mh[ma] <= 0:
                c = basesim.base_replace(B, X, mh, oa, max(1, oh[oa]), kh, nopp); mine = {"action": "switch", "index": c}; kind = "forced"
            else:
                ms, mi = basesim.base_choose(B, X, ma, mh, oa, oh[oa], kh, X["mpp"], nopp, obs["turn"])
                mine = {"action": "switch" if ms else "move", "index": mi}; kind = "turn"
            ok = mine == real
            stats[(kind, ok)] += 1
            if not ok and shown < 12:
                shown += 1
                print("MISMATCH", kind, "turn", obs["turn"], "me", obs["active_pokemon"]["species"], obs["active_pokemon"]["current_hp"],
                      "vs", osp, obs["opponent_active"]["hp_percent"], "known", obs["opponent_active"]["known_moves"], "real", real, "clone", mine)
        except Exception as ex:
            stats[("err", repr(ex)[:60])] += 1
        return real
    for s in range(n):
        core.play(team, opp, core.TUNE_BASE + s, pol)
    print(dict(stats))

if __name__ == "__main__":
    main()

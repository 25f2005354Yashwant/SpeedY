"""L0 simulator for the TEAM-ONLY track: a clone of the organisers' baseline policy (depth-1 minimax on
`position_value`, including its quirks: opponent treated as 100 HP, double decrement of the remaining count,
lowest-index tie-break) playing against the exact Cynthia clone, on the policy's damage tables.

Used only to propose teams quickly; every proposal is re-ranked with real engine battles.

  python -m tools_ours.basesim check TEAM OPP N     fidelity vs the real engine + real baseline policy
  python -m tools_ours.basesim eval TEAM [N]
"""
import sys
import time

from harness import core
from tools_ours import fastsim

TACKLE = (0, 0, 35, 95, 0, 0, 1, 0)


def build(team, opp):
    p = fastsim.P()
    D = core._state["data"]
    B, mh, oh, rv, pp = fastsim.build(team, opp)
    her = fastsim.opp_cfg(opp)["team"]
    HER = [p._her(m["species"], None) for m in her]
    MY = B["MY"]
    n = len(MY)
    X = {
        "TK": [[p._ent(HER[j], TACKLE, MY[i])[0] for i in range(n)] for j in range(6)],
        "A0": [[max([p._ent(HER[j], (t, 1 if t in p.SPC else 0, 90, 100, 0, 0, 1, 0), MY[i])[0] for t in HER[j][0]]
                    or [0.0]) for i in range(n)] for j in range(6)],
        "gar": [m["species"] == "garchomp" for m in team],
        "mpp": [[D.moves[x].pp for x in m["moves"]] for m in team],
    }
    return B, X, mh, oh, rv, pp


def _pv(B, X, act, act_hp, opp_cur, rem, pp_total, bench, j, turn):
    MM = B["MM"]
    own_frac = act_hp / MM[act] if act_hp > 0 else 0.0
    opp_frac = opp_cur / 100.0 if opp_cur > 0 else 0.0
    own_alive = 1 if own_frac > 0 else 0
    bsum = 0.0
    closer = 0.0
    gar = X["gar"]
    for c, h in bench:
        own_alive += 1
        f = h / MM[c]
        bsum += f
        if gar[c]:
            closer += 0.5 * f
    opp_alive = rem
    if opp_frac == 0.0 and opp_alive > 0:
        opp_alive -= 1
    if opp_alive == 0 and opp_frac == 0:
        return 100.0
    if own_alive == 0 and own_frac == 0:
        return -100.0
    hp_diff = (own_frac * 1.5 + bsum) - (opp_frac * 1.5 + (opp_alive - 1) * 0.8)
    alive_diff = (own_alive - opp_alive) * 1.5
    sm, so = B["MS"][act], B["OS"][j]
    tempo = 0.25 if sm > so else (-0.25 if so > sm else 0.0)
    ppp = 0.0
    if own_frac > 0:
        if pp_total == 0:
            ppp = -15.0
        elif pp_total <= 2:
            ppp = -3.0
    stall = 0.0
    if turn + 1 > 60:
        stall = -((turn + 1 - 60) * 0.05) * 0.5
    end = 0.5 * own_frac if (own_alive == 1 and gar[act]) else 0.0
    return hp_diff * 1.0 + alive_diff + tempo + 0.0 + closer + ppp + stall + end


def _threat(B, X, j, c, kh):
    tb = B["TB"][j][c]
    if kh:
        return max(tb[m][0] for m in kh)
    return X["A0"][j][c]


def _swscore(B, X, j, c, hc, ohj, kh, nopp):
    ct = _threat(B, X, j, c, kh) / max(1, hc)
    sc = min(B["BA"][c][j], ohj) / ohj - ct
    if B["MS"][c] > B["OS"][j]:
        sc += 0.2
    if X["gar"][c] and nopp >= 3 and ct > 0.25:
        sc -= 0.4
    if ct >= 0.85:
        sc -= 2.0
    return sc, ct


def base_replace(B, X, mh, j, ohj, kh, nopp):
    best = None
    for c in range(len(mh)):
        if mh[c] <= 0:
            continue
        sc, _ = _swscore(B, X, j, c, mh[c], ohj, kh, nopp)
        if best is None or sc > best[0]:
            best = (sc, c)
    return best[1]


def base_choose(B, X, i, mh, j, ohj, kh, mpp, nopp, turn):
    """Returns (is_switch, index) or (0, -1) for struggle."""
    hi = mh[i]
    TA = B["TA"][i][j]
    moves = [k for k in range(len(TA)) if mpp[i][k] > 0]
    if not moves:
        return (0, -1)
    bench = [(c, mh[c]) for c in range(len(mh)) if c != i and mh[c] > 0]
    tac = None
    if bench:
        thr = _threat(B, X, j, i, kh) / max(1, hi)
        off = min(B["BA"][i][j], ohj) / ohj
        d = 0.6 + (min(0.35, (turn - 50) * 0.01) if turn > 50 else 0.0)
        if not (thr < d or off >= 0.4) and not any(e[1] >= ohj for e in TA):
            cands = []
            for c, hc in bench:
                sc, ct = _swscore(B, X, j, c, hc, ohj, kh, nopp)
                if ct < 0.40:
                    cands.append((-sc, c))
            if cands:
                tac = min(cands)[1]
    tbj = B["TB"][j]
    if kh:
        opp_moves = [(tbj[i][m][0], tbj[i][m][5], m) for m in kh]
    else:
        opp_moves = [(X["TK"][j][i], 0, -1)]
    MS, OS = B["MS"], B["OS"]
    pp_total = sum(mpp[i])
    best = None
    for k in moves:
        e = TA[k]
        Em = e[0]
        worst = 1e18
        for Eh, ph, _m in opp_moves:
            if e[5] != ph:
                mf = e[5] > ph
            else:
                mf = MS[i] >= OS[j]
            opp_cur = 0  # quirk: if my hit never lands, position_value reads the opponent's HP as 0
            me_cur = hi
            rem = nopp
            if mf:
                opp_cur = max(0, int(100 - Em))
                if opp_cur <= 0:
                    rem = max(0, rem - 1)
                else:
                    me_cur = max(0, int(hi - Eh))
            else:
                me_cur = max(0, int(hi - Eh))
                if me_cur > 0:
                    opp_cur = max(0, int(100 - Em))
                    if opp_cur <= 0:
                        rem = max(0, rem - 1)
            v = _pv(B, X, i, me_cur, opp_cur, rem, pp_total - 1, bench, j, turn)
            if v < worst:
                worst = v
        key = (-worst, 0, k)
        if best is None or key < best[0]:
            best = (key, (0, k))
    if tac is not None:
        c = tac
        nb = [(x, h) for x, h in bench if x != c] + [(i, hi)]
        ppc = sum(mpp[c])
        worst = 1e18
        if kh:
            om = [tbj[c][m][0] for m in kh]
        else:
            om = [X["TK"][j][c]]
        for Eh in om:
            c_cur = max(0, int(mh[c] - Eh))
            v = _pv(B, X, c, c_cur, 0, nopp, ppc, nb, j, turn)
            if v < worst:
                worst = v
        key = (-worst, 1, c)
        if key < best[0]:
            best = (key, (1, c))
    return best[1]


def sim(B, X, mh, oh, rv, pp, oa, seed):
    """One battle: baseline clone (me) vs Cynthia clone. Returns (win, turns)."""
    p = fastsim.P()
    mh = mh[:]
    oh = oh[:]
    rv = rv[:]
    pp = [x[:] for x in pp]
    mpp = [x[:] for x in X["mpp"]]
    kh = [[] for _ in range(6)]
    TA, TB, MS, OS = B["TA"], B["TB"], B["MS"], B["OS"]
    boss = B["boss"]
    sd = seed * 15485863
    s = (seed * 7919 + 104729) & 2147483647
    ma = 0
    cd = 0
    turn = 1
    nmy = sum(1 for x in mh if x > 0)
    nop = 6
    while nmy > 0 and nop > 0 and turn <= 200:
        if mh[ma] <= 0:
            ma = base_replace(B, X, mh, oa, max(1, oh[oa]), kh[oa], nop)
        if oh[oa] <= 0:
            oa = p._cyn(B, oa, ma, mh[ma], oh, cd, rv[ma], pp, nmy, turn, True)[1]
        hs, hi, cd = p._cyn(B, oa, ma, mh[ma], oh, cd, rv[ma], pp, nmy, turn, False)
        ms, mi = base_choose(B, X, ma, mh, oa, oh[oa], kh[oa], mpp, nop, turn)
        if ms:
            ma = mi
        if hs:
            oa = hi
        em = None if (ms or mi < 0) else TA[ma][oa][mi]
        eh = None if (hs or hi < 0) else TB[oa][ma][hi]
        if em is not None:
            if mi not in rv[ma]:
                rv[ma] = rv[ma] + (mi,)
            mpp[ma][mi] -= 1
        if eh is not None:
            pp[oa][hi] -= 1
            if hi not in kh[oa]:
                kh[oa].append(hi)
        mf = True
        if em is not None and eh is not None:
            if em[5] != eh[5]:
                mf = em[5] > eh[5]
            elif MS[ma] != OS[oa]:
                mf = MS[ma] > OS[oa]
            else:
                s = ((sd + turn * 7919) * 1103515245 + 12345) & 2147483647
                mf = (s >> 16) & 1 == 1
        for step in (0, 1):
            mine = mf if step == 0 else not mf
            if mh[ma] <= 0 or oh[oa] <= 0:
                break
            s = ((sd + turn * 104729 + (611953 if mine else 0)) * 1103515245 + 12345) & 2147483647
            e = em if mine else eh
            if e is None:
                continue
            if e[4] <= 100:
                s = (s * 1103515245 + 12345) & 2147483647
                if (s >> 8) % 100 >= e[4]:
                    continue
            n = e[7]
            if n == 0:
                s = (s * 1103515245 + 12345) & 2147483647
                n = (2, 2, 2, 3, 3, 3, 4, 5)[(s >> 8) & 7]
            tot = 0
            tgt = oh[oa] if mine else mh[ma]
            for _ in range(n):
                s = (s * 1103515245 + 12345) & 2147483647
                r = s >> 8
                d = (e[3] if (r >> 4) % 16 < e[8] else e[2])[r % 16]
                if boss and d > 0:
                    d = max(1, int(d * 0.85)) if mine else int(d * 1.15)
                if d >= tgt:
                    tot += tgt
                    tgt = 0
                    break
                tgt -= d
                tot += d
            if mine:
                oh[oa] = tgt
                if tgt <= 0:
                    nop -= 1
            else:
                mh[ma] = tgt
                if tgt <= 0:
                    nmy -= 1
            dr = e[6]
            if dr and tot > 0:
                if dr > 0:
                    h = max(1, tot * dr // 100)
                    if mine:
                        mh[ma] = min(B["MM"][ma], mh[ma] + h)
                    else:
                        oh[oa] = min(B["OM"][oa], oh[oa] + h)
                elif (nop > 0) if mine else (nmy > 0):
                    h = max(1, tot * -dr // 100)
                    if mine:
                        mh[ma] = max(0, mh[ma] - h)
                        if mh[ma] <= 0:
                            nmy -= 1
                    else:
                        oh[oa] = max(0, oh[oa] - h)
                        if oh[oa] <= 0:
                            nop -= 1
        turn += 1
    return (nop <= 0 and nmy > 0), turn - 1


def l0(team, opp, n, seed0=1):
    B, X, mh, oh, rv, pp = build(team, opp)
    wins = 0
    for s in range(seed0, seed0 + n):
        oa = (s * 2654435761 >> 7) % 6
        B["boss"] = (opp == "policy") and ((s * 40503 >> 3) % 10 < 3)
        if sim(B, X, mh, oh, rv, pp, oa, s)[0]:
            wins += 1
    return wins / n


def main():
    cmd = sys.argv[1]
    team = core.load_team(sys.argv[2])
    if cmd == "check":
        opp, n = sys.argv[3], int(sys.argv[4])
        t = time.time()
        res = core.evaluate(team, [opp], n)[opp]
        t1 = time.time() - t
        t = time.time()
        r = l0(team, opp, 3000)
        print(f"{opp}: real engine + real baseline {100 * res['wr']:.1f}% [{100*res['lo']:.0f},{100*res['hi']:.0f}] "
              f"(n={n}, {t1:.0f}s) | baseline-clone L0 {100 * r:.1f}% (n=3000, {time.time() - t:.1f}s)", flush=True)
    else:
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
        t = time.time()
        res = {o: l0(team, o, n) for o in ("public", "t_aggr", "t_patient", "offensive", "defensive")}
        print({o: round(100 * v, 1) for o, v in res.items()}, f"{time.time() - t:.1f}s")


if __name__ == "__main__":
    main()

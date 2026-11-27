# Cynthia's Gauntlet battle policy.  Pure Python, no imports.  Built by tools_ours/build_policy.py.
# Idea: exact Gen-4 damage tables + a clone of Cynthia's public scripted move/switch rule + Monte-Carlo
# rollouts of the damage race (common random numbers) to pick the action with the best win value.
_PK = "@PK@"
_MV = "@MV@"
_TC = "@TC@"
_RO = "@RO@"
KP = @KP@
KM = @KM@
R1 = 6
R2 = 14
R3 = 40
R4 = 40
GAP = 0.08
WORK = 14000
TMAX = 90
TY = ['normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting', 'poison', 'ground', 'flying', 'psychic',
      'bug', 'rock', 'ghost', 'dragon', 'dark', 'steel']
TI = {t: i for i, t in enumerate(TY)}
SPC = (1, 2, 3, 4, 5, 10, 14, 15)
Z16 = [0] * 16


def _h(s, k):
    h = 0
    for c in s:
        h = (h * k + ord(c)) % 1048573
    return h


PK = {}
for _i in range(0, len(_PK), 19):
    _r = _PK[_i:_i + 19]
    PK[int(_r[:5], 16)] = (tuple(ord(c) - 97 for c in _r[5:7] if c != 'z'),
                           [int(_r[7 + 2 * j:9 + 2 * j], 16) for j in range(6)])
MV = {}
for _i in range(0, len(_MV), 15):
    _r = _MV[_i:_i + 15]
    # (type, cat, power, acc, prio, drain, hits, crit/fixed)
    MV[int(_r[:5], 16)] = (ord(_r[5]) - 97, 0 if _r[6] == 'p' else 1, int(_r[7:9], 16), int(_r[9:11], 16) or 101,
                           int(_r[11]), {'0': 0, 'h': 50, 'q': -25, 't': -33, 'f': -50}[_r[12]],
                           0 if _r[13] == 'm' else int(_r[13]), 2 if _r[14] == 'x' else int(_r[14]))
CH = [[(0.0, 0.5, 1.0, 2.0)[int(_TC[a * 17 + d])] for d in range(17)] + [1.0] for a in range(17)] + [[1.0] * 18]
RO = {}
for _r in _RO.split(';'):
    _a, _b = _r.split(':')
    RO[_a] = _b.split(',')
ROSTER = ['spiritomb', 'roserade', 'gastrodon', 'lucario', 'milotic', 'garchomp']
G = {'n': -1}
NC = [0, 0]
C = {}
# Hypotheses about Cynthia's switching parameters (danger_threshold, weak_offense_threshold, cooldown).
# First = public variant; the others cover the published personality files and never-/often-switching styles.
HY = ((0.6, 0.4, 3), (0.85, 0.2, 6), (0.45, 0.6, 2), (0.5, 0.4, 4), (0.55, 0.45, 3), (9.0, 0.0, 3),
      (0.3, 0.6, 2), (0.35, 0.6, 1), (0.45, 0.7, 2), (0.3, 0.4, 3), (0.45, 0.45, 1))
MISS = [0.0] * len(HY)
# Hypotheses about her move scoring: (aggression, bonus for her highest-power move, priority_weight)
MH = ((1.0, 0.0, 1.0), (1.8, 0.15, 1.3), (1.5, 0.15, 1.8), (1.0, 0.15, 1.0), (1.8, 0.0, 1.3), (0.65, 0.0, 0.9),
      (1.3, 0.0, 1.8), (0.8, 0.0, 1.0), (0.65, 0.15, 1.0))
MISM = [0.0] * len(MH)


def _mv(name, d=None):
    m = MV.get(_h(name, KM))
    if m:
        return m
    if d:
        return (TI.get(d.get('type'), 17), 0 if d.get('category') == 'physical' else 1, d.get('power') or 0,
                d.get('accuracy') or 101, 0, 0, 1, 0)
    return (0, 0, 80, 100, 0, 0, 1, 0)


def _ent(A, m, D):
    """Damage table entry: (E, min, noncrit[16], crit[16], acc, prio, drain, hits, critN)."""
    pw = m[2]
    e = 1.0
    for t in D[0]:
        e *= CH[m[0]][t]
    acc = m[3]
    if not pw or e == 0:
        return (0.0, 0, Z16, Z16, acc, m[4], m[5], 1, 1)
    if m[7] == 2:
        nc = cr = [pw] * 16
        return (pw * (1.0 if acc > 100 else acc / 100.0), pw, nc, cr, acc, m[4], 0, 1, 1)
    if m[1] == 0:
        a, d = A[1], D[2]
    else:
        a, d = A[3], D[4]
    s = (22 * pw * a // d) // 50 + 2
    st = m[0] in A[0]
    nc = []
    cr = []
    cn = 2 if m[7] == 1 else 1
    cp = cn / 16.0
    tot = 0.0
    for r in range(85, 101):
        x = s * r // 100
        y = 2 * s * r // 100
        if st:
            x = x * 3 // 2
            y = y * 3 // 2
        x = int(x * e)
        y = int(y * e)
        nc.append(x)
        cr.append(y)
        tot += (1.0 - cp) * x + cp * y
    h = m[6]
    eh = 3.0 if h == 0 else float(h)
    ea = 1.0 if acc > 100 else acc / 100.0
    return (ea * eh * (tot / 16), nc[0] * (2 if h != 1 else 1), nc, cr, acc, m[4], m[5], h, cn)


def _her(sp, types):
    """static for one of her species: (types, atk, def, spa, spd, spe, hp)"""
    p = PK.get(_h(sp, KP))
    if p:
        b = p[1]
        return (p[0] if types is None else types, b[1] + 20, b[2] + 20, b[3] + 20, b[4] + 20, b[5] + 20, b[0] + 75)
    return (types or (), 100, 100, 100, 100, 100, 155)


def _parse(state):
    """Incrementally replay battle_history into G (her HP/PP/moves, cooldown, my revealed moves, boss flag)."""
    hist = state.get('battle_history') or []
    if len(hist) < G['n'] or G['n'] < 0 or state.get('turn', 1) <= 1 and not hist:
        G.clear()
        G.update(n=0, her={}, order=[], ts=99, rev={}, boss=False, pred=None, intu=False, last=None, swt=-1)
        for i in range(len(MISS)):
            MISS[i] *= 0.5
        for i in range(len(MISM)):
            MISM[i] *= 0.5
    her = G['her']
    for ev in hist[G['n']:]:
        t = ev.get('type')
        sd = ev.get('side')
        if t == 'turn_start':
            G['ts'] += 1
            G['intu'] = True
        elif t == 'switch':
            if sd == 'b':
                if G['intu']:
                    G['ts'] = 0
                    G['swt'] = ev.get('turn')
        elif t == 'move_used' or t == 'struggle':
            G['intu'] = False
            sp = ev.get('pokemon')
            mv = ev.get('move')
            G['last'] = (sd, sp, mv)
            if mv:
                if sd == 'a':
                    r = G['rev'].setdefault(sp, [])
                    if mv not in r:
                        r.append(mv)
                else:
                    h = her.setdefault(sp, {'hp': None, 'mv': [], 'pp': {}})
                    if mv not in h['mv']:
                        h['mv'].append(mv)
                    h['pp'][mv] = ev.get('pp_left', 9)
                    G['hmv'] = (ev.get('turn'), mv)
        elif 'hp_after' in ev and sd == 'b':
            sp = ev.get('pokemon')
            h = her.setdefault(sp, {'hp': None, 'mv': [], 'pp': {}})
            h['hp'] = ev['hp_after']
            L = G['last']
            if t == 'damage' and L and L[0] == 'a' and ev['hp_after'] > 0 and not G['boss']:
                G.setdefault('chk', []).append((L[1], L[2], sp, ev.get('amount')))
    G['n'] = len(hist)
    p = G['pred']
    if p and p[0] < state.get('turn', 1):
        sw = G['swt'] == p[0]
        for i in range(len(HY)):
            if p[3][i] != sw:
                MISS[i] += 1.0
        hm = G.get('hmv')
        if hm and hm[0] == p[0]:
            for i in range(len(MH)):
                if p[4][i] != hm[1]:
                    MISM[i] += 1.0
    G['pred'] = None


def _setup(state):
    act = state['active_pokemon']
    bench = state.get('bench') or []
    used = set(b.get('index') for b in bench)
    ma = 0
    while ma in used:
        ma += 1
    mons = [None] * (max([ma] + [b.get('index', 0) for b in bench]) + 1)
    mons[ma] = act
    for b in bench:
        mons[b.get('index', 0)] = b
    MY = []
    MYM = []
    mh = []
    names = []
    rv = []
    for m in mons:
        if not m:
            MY.append(((), 100, 100, 100, 100, 100, 155))
            MYM.append([])
            mh.append(0)
            names.append('')
            rv.append(())
            continue
        st = m.get('stats') or {}
        MY.append((tuple(TI[t] for t in m.get('types', []) if t in TI), st.get('atk', 100), st.get('def', 100),
                   st.get('spa', 100), st.get('spd', 100), st.get('spe', 100), m.get('max_hp') or st.get('hp', 155)))
        mvs = m.get('moves') or []
        MYM.append([(x.get('identifier', ''), _mv(x.get('identifier', ''), x), x.get('pp', 1)) for x in mvs])
        mh.append(0 if m.get('fainted') else m.get('current_hp', 0))
        sp = m.get('species', '')
        names.append(sp)
        r = G['rev'].get(sp, [])
        rv.append(tuple(k for k, x in enumerate(mvs) if x.get('identifier') in r))
    # her side
    opp = state['opponent_active']
    osp = opp.get('species', '')
    her = G['her']
    if osp not in her:
        her[osp] = {'hp': None, 'mv': [], 'pp': {}}
    if 'ty' not in her[osp]:
        her[osp]['ty'] = tuple(TI[t] for t in opp.get('types', []) if t in TI)
    order = G['order']
    for sp in her:
        if sp not in order:
            order.append(sp)
    known = all(s in RO for s in order)
    team = list(order)
    if known:
        gi = G['boss'] or 'giratina-altered' in team
        for s in ROSTER:
            if s == 'spiritomb' and gi:
                s = 'giratina-altered'
            if len(team) < 6 and s not in team:
                team.append(s)
    while len(team) < 6:
        team.append('?')
    HER = []
    HM = []
    oh = []
    pp = []
    for sp in team:
        h = her.get(sp)
        if sp == '?':
            st = ((), 100, 100, 100, 100, 100, 155)
        else:
            st = _her(sp, h.get('ty') if h else None)
        seen = h['mv'] if h else []
        if sp in RO and all(x in RO[sp] for x in seen):
            names_m = RO[sp]
        else:
            names_m = list(seen)
        ms = [(x, _mv(x)) for x in names_m]
        if len(ms) < 4 and sp not in RO:
            for t in (st[0] or (17,)):
                ms.append(('~', (t, 1 if t in SPC else 0, 90, 100, 0, 0, 1, 0)))
        HER.append(st)
        HM.append(ms[:6])
        pp.append([(h['pp'].get(x[0], 9) if h else 9) for x in ms[:6]])
        hp = st[6]
        if h and h['hp'] is not None:
            hp = h['hp']
        oh.append(hp)
    oa = team.index(osp)
    pct = opp.get('hp_percent', 100.0)
    if her[osp]['hp'] is None:
        oh[oa] = max(1, int(HER[oa][6] * pct / 100.0 + 0.5))
    # alive bookkeeping: unseen mons beyond opponent_remaining_count are impossible; trust counts
    rem = state.get('opponent_remaining_count', 6)
    alive = [j for j in range(6) if oh[j] > 0]
    while len(alive) > rem and len(alive) > 1:
        j = alive.pop()
        if j == oa:
            alive.insert(0, j)
            j = alive.pop()
        oh[j] = 0
    # tables
    TA = []
    T0 = []
    for i in range(len(MY)):
        ra = []
        r0 = []
        for j in range(6):
            key = (names[i], tuple([m[0] for m in MYM[i]]), team[j], HER[j][0])
            c = C.get(key)
            if c is None:
                c = ([_ent(MY[i], m[1], HER[j]) for m in MYM[i]],
                     max([_ent(MY[i], (t, 1 if t in SPC else 0, 90, 100, 0, 0, 1, 0), HER[j])[0] for t in MY[i][0]]
                         or [0.0]))
                C[key] = c
            ra.append(c[0])
            r0.append(c[1])
        TA.append(ra)
        T0.append(r0)
    TB = []
    for j in range(6):
        rb = []
        for i in range(len(MY)):
            key = (team[j], tuple(x[0] for x in HM[j]), names[i], HER[j][0])
            c = C.get(key)
            if c is None:
                c = [_ent(HER[j], m[1], MY[i]) for m in HM[j]]
                C[key] = c
            rb.append(c)
        TB.append(rb)
    if G.get('chk'):
        for (a, mvn, d, amt) in G['chk']:
            if a in names and d in team:
                i = names.index(a)
                ks = [k for k, x in enumerate(MYM[i]) if x[0] == mvn]
                if ks:
                    e = TA[i][team.index(d)][ks[0]]
                    if amt not in e[2] and amt not in e[3] and e[7] == 1:
                        G['boss'] = True
        G['chk'] = []
    G['hn'] = [[x[0] for x in ms] for ms in HM]
    # fast paths: when the defender's HP is above every move's min/expected damage (no KO possible) and the
    # attacker has no priority/drain/recoil move, the scripted choice is HP-independent -> precompute it.
    FP = []
    for j in range(6):
        row = []
        for i in range(len(MY)):
            kb = 0
            bv = -1.0
            th = 0.0
            for k, e in enumerate(TB[j][i]):
                v = e[0] * (1.0 if e[4] > 100 else e[4] / 100.0)
                if v > bv:
                    bv = v
                    kb = k
                th = max(th, e[0], e[1])
                if e[5] or e[6]:
                    th = 1e9
            row.append((kb, th))
        FP.append(row)
    MP = []
    for i in range(len(MY)):
        row = []
        for j in range(6):
            kb = 0
            bv = -1.0
            th = 0.0
            for k, e in enumerate(TA[i][j]):
                if e[0] > bv:
                    bv = e[0]
                    kb = k
                th = max(th, e[0], e[1])
            row.append((kb, th))
        MP.append(row)
    B = {'FP': FP, 'MP': MP, 'MY': MY, 'TA': TA, 'T0': T0, 'TB': TB, 'MS': [m[5] for m in MY], 'OS': [m[5] for m in HER],
         'MM': [m[6] for m in MY], 'OM': [m[6] for m in HER], 'HP': [[m[1][2] for m in ms] for ms in HM],
         'clo': [s == 'garchomp' for s in team], 'boss': G['boss'],
         'BB': [[max([e[0] for e in TB[j][i]] or [0.0]) for i in range(len(MY))] for j in range(6)],
         'BA': [[max([e[0] for e in TA[i][j]] or [0.0]) for j in range(6)] for i in range(len(MY))]}
    return B, mh, oh, ma, oa, rv, pp


def _cyn(B, j, i, hpi, oh, cd, rvi, pp, nmy, turn, forced):
    """Clone of Cynthia's scripted choice. Returns (is_switch, index, cooldown)."""
    TAi = B['TA'][i]
    T0i = B['T0'][i]
    BB = B['BB']
    OS = B['OS']
    msi = B['MS'][i]
    if forced or cd <= 1:
        if not forced and cd > 0:
            cd -= 1
        go = forced
        if not forced and BB[j][i] < B['wk'] * hpi:
            e = TAi[j]
            th = (max([e[k][0] for k in rvi]) if rvi else T0i[j]) / oh[j]
            d = B['dg'] + (min(0.35, (turn - 50) * 0.01) if turn > 50 else 0.0)
            if th >= d and min(BB[j][i], hpi) / hpi < B['wk']:
                go = True
                for e2 in B['TB'][j][i]:
                    if e2[1] >= hpi:
                        go = False
                        break
        if go:
            best = None
            bs = -1e9
            clo = B['clo']
            for c in range(6):
                if c == j or oh[c] <= 0:
                    continue
                e = TAi[c]
                th = (max([e[k][0] for k in rvi]) if rvi else T0i[c]) / oh[c]
                if not forced and th >= 0.4:
                    continue
                sc = min(BB[c][i], hpi) / hpi - th
                if OS[c] > msi:
                    sc += 0.2
                if clo[c] and nmy >= 3 and th > 0.25:
                    sc -= 0.4
                if th >= 0.85:
                    sc -= 2.0
                if sc > bs:
                    bs = sc
                    best = c
            if best is not None:
                return (1, best, cd if forced else B['cm'])
            if forced:
                return (1, j, cd)
    elif cd > 0:
        cd -= 1
    f = B['FP'][j][i]
    if hpi > f[1] and not B['mh'][1] and min(pp[j]) > 2:
        return (0, f[0], cd)
    ohj = oh[j]
    faster = OS[j] > msi
    slower = OS[j] < msi
    dang = ohj <= B['OM'][j] * 0.25
    if not dang:
        e = TAi[j]
        for k in rvi:
            if e[k][1] >= ohj:
                dang = True
                break
    ppj = pp[j]
    tb = B['TB'][j][i]
    tp = 0
    for p in ppj:
        tp += p
    if tp <= 0:
        return (0, -1, cd)
    best = 0
    bs = -1e9
    hpw = B['HP'][j]
    ag, sb, pw = B['mh']
    mxp = max(hpw) if sb else 0
    for k in range(len(tb)):
        p = ppj[k]
        if p <= 0:
            continue
        e = tb[k]
        E = e[0]
        acc = e[4]
        ea = 1.0 if acc > 100 else acc / 100.0
        pr = e[5]
        sure = e[1] >= hpi
        if sure:
            s = 2.0 + ea
            if pr > 0 or faster:
                s += 0.5
            if slower and dang and pr > 0:
                s += 2.0 * pw
            if e[6] < 0:
                s -= 0.3
        elif E >= hpi:
            s = 1.2 + 0.6 * ea
            if pr > 0 and slower and dang:
                s += 1.5 * pw
        else:
            s = E / hpi * ag * ea
            if pr > 0:
                s += (0.5 if (slower and dang) else 0.05) * pw
        dr = e[6]
        if dr > 0:
            s += 0.15 * (min(E * dr / 100.0, B['OM'][j] - ohj) / B['OM'][j])
        elif dr < 0 and not sure:
            s -= 0.1 * (E * -dr / 100.0 / ohj)
        if p <= 2:
            s -= 0.05
            if not sure:
                for q in range(len(tb)):
                    if q != k and ppj[q] >= 5 and hpw[q] >= 50:
                        s -= 0.15
                        break
        if tp <= 3:
            s += 0.2
        if nmy <= 1:
            s += 0.15 * ag
        if sb and hpw[k] == mxp:
            s += sb
        if s > bs:
            bs = s
            best = k
    return (0, best, cd)


def _mine(B, i, j, hpj, hpi):
    """Default (rollout) move choice for my mon i vs her mon j."""
    f = B['MP'][i][j]
    if hpj > f[1]:
        return f[0]
    ta = B['TA'][i][j]
    best = 0
    bs = -1.0
    for k in range(len(ta)):
        e = ta[k]
        E = e[0]
        if e[1] >= hpj:
            s = 2.0 + (1.0 if e[4] > 100 else e[4] / 100.0) + e[5]
        elif E >= hpj:
            s = 1.0 + (1.0 if e[4] > 100 else e[4] / 100.0) * 0.5
        else:
            s = E / hpj
        if s > bs:
            bs = s
            best = k
    return best


def _myrep(B, mh, j, ohj):
    """Default forced replacement: the mon with the best 1v1 race vs her mon j (expected-damage turns to KO)."""
    best = -1
    bs = -1e9
    BA = B['BA']
    BB = B['BB'][j]
    MS = B['MS']
    osj = B['OS'][j]
    for c in range(len(mh)):
        h = mh[c]
        if h <= 0:
            continue
        dm = BA[c][j]
        dh = BB[c]
        tm = -(-ohj // dm) if dm > 0 else 99
        th = -(-h // dh) if dh > 0 else 99
        f = MS[c] > osj
        if tm < th or (tm == th and f):
            s = 2.0 + max(0.0, 1.0 - (tm - (1 if f else 0)) * dh / h)
        else:
            s = min(1.0, (th - (0 if f else 1)) * dm / ohj)
        if s > bs:
            bs = s
            best = c
    return best


def _roll(B, mh, oh, ma, oa, cd, rv, pp, turn, a0, seed):
    mh = mh[:]
    oh = oh[:]
    rv = rv[:]
    pp = [p[:] for p in pp]
    TA = B['TA']
    TB = B['TB']
    MS = B['MS']
    OS = B['OS']
    boss = B['boss']
    s = (seed * 7919 + 104729) & 2147483647
    sd = seed * 15485863
    first = True
    t0 = turn
    nmy = 0
    for x in mh:
        if x > 0:
            nmy += 1
    nop = 0
    for x in oh:
        if x > 0:
            nop += 1
    while nmy > 0 and nop > 0 and turn < t0 + TMAX:
        # forced replacements (mine first, then hers)
        if mh[ma] <= 0:
            if first and a0[0] == 1:
                ma = a0[1]
                first = False
            else:
                ma = _myrep(B, mh, oa, max(1, oh[oa]))
        if oh[oa] <= 0:
            oa = _cyn(B, oa, ma, mh[ma], oh, cd, rv[ma], pp, nmy, turn, True)[1]
        hs, hi, cd = _cyn(B, oa, ma, mh[ma], oh, cd, rv[ma], pp, nmy, turn, False)
        if first:
            first = False
            ms = a0[0]
            mi = a0[1]
        else:
            # default player: her scripted action is predictable, so aim at whoever will be in front of us
            ms = 0
            jj = hi if hs else oa
            mi = _mine(B, ma, jj, oh[jj], mh[ma])
        if ms:
            ma = mi
        if hs:
            oa = hi
        em = None if ms else TA[ma][oa][mi]
        eh = None if (hs or hi < 0) else TB[oa][ma][hi]
        if not ms and mi not in rv[ma]:
            rv[ma] = rv[ma] + (mi,)
        if not hs and hi >= 0:
            pp[oa][hi] -= 1
        # order
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
            if mine:
                e = em
            else:
                e = eh
                if e is None and not hs and hi < 0:
                    # her struggle: 50-power typeless hit, 25% recoil (approximate)
                    d = 30
                    mh[ma] = max(0, mh[ma] - d)
                    oh[oa] = max(0, oh[oa] - B['OM'][oa] // 4)
                    continue
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
                        mh[ma] = min(B['MM'][ma], mh[ma] + h)
                    else:
                        oh[oa] = min(B['OM'][oa], oh[oa] + h)
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
    NC[1] += turn - t0
    a = 0.0
    for i in range(len(mh)):
        a += mh[i] / B['MM'][i]
    b = 0.0
    for j in range(6):
        b += oh[j] / B['OM'][j]
    if nop <= 0 and nmy > 0:
        v = 1.0
    elif nmy <= 0:
        v = 0.0
    else:
        v = 0.3
    return v + 0.02 * (a - b) - 0.0015 * (turn - t0)


def _choose(state):
    legal = state.get('legal_actions') or []
    if len(legal) <= 1:
        return legal[0] if legal else {'action': 'struggle'}
    for a in legal:
        if a.get('action') == 'struggle':
            return a
    _parse(state)
    B, mh, oh, ma, oa, rv, pp = _setup(state)
    B['mh'] = MH[0]
    turn = state.get('turn', 1)
    hb = 0
    for i in range(len(HY)):
        if MISS[i] < MISS[hb]:
            hb = i
    B['dg'], B['wk'], B['cm'] = HY[hb]
    mb = 0
    for i in range(len(MH)):
        if MISM[i] < MISM[mb]:
            mb = i
    B['mh'] = MH[mb]
    cd = max(0, HY[hb][2] - G['ts'])
    acts = []
    for a in legal:
        k = a.get('action')
        if k == 'move':
            acts.append((0, a['index'], a))
        elif k == 'switch':
            acts.append((1, a['index'], a))
    if not acts:
        return legal[0]
    forced = mh[ma] <= 0
    if not forced:
        nmy = sum(1 for x in mh if x > 0)
        pd = _cyn(B, oa, ma, mh[ma], oh, cd, rv[ma], pp, nmy, turn, False)
        ph = []
        for h in HY:
            B['dg'], B['wk'], B['cm'] = h
            ph.append(_cyn(B, oa, ma, mh[ma], oh, max(0, h[2] - G['ts']), rv[ma], pp, nmy, turn, False)[0] == 1)
        B['dg'], B['wk'], B['cm'] = 9.0, 0.0, 3
        pm = []
        hn = G['hn'][oa]
        for h in MH:
            B['mh'] = h
            k = _cyn(B, oa, ma, mh[ma], oh, 9, rv[ma], pp, nmy, turn, False)[1]
            pm.append(hn[k] if 0 <= k < len(hn) else '')
        B['mh'] = MH[mb]
        B['dg'], B['wk'], B['cm'] = HY[hb]
        G['pred'] = (turn, pd[0] == 1, pd[1], ph, pm)
    # Sequential halving: R1 rollouts for every action, +R2 for the best half (max 4), +R3 for the best two.
    # WORK caps the simulated turns per decision; the sandbox also caps cumulative time per process, so after
    # many calls the search gets lighter.
    NC[0] += 1
    NC[1] = 0
    plan = (R1, R2, R3, R4)
    work = WORK
    if NC[0] > 2500:
        plan = (2, 4, 0, 0) if NC[0] < 8000 else (2, 0, 0, 0)
    sc = [[0.0, 0, a] for a in acts]
    top = sc
    for st in range(4):
        if st == 1:
            top = top[:max(2, min(4, (len(top) + 1) // 2))]
        elif st >= 2:
            top = top[:2]
        if st and (len(top) < 2 or top[0][0] / max(1, top[0][1]) - top[1][0] / max(1, top[1][1]) > (9, 9, 9, GAP)[st]):
            break
        for x in top:
            for r in range(x[1], x[1] + plan[st]):
                if NC[1] > work:
                    break
                x[0] += _roll(B, mh, oh, ma, oa, cd, rv, pp, turn, x[2], r + 1)
                x[1] += 1
        top.sort(key=lambda x: -x[0] / max(1, x[1]))
        if NC[1] > work:
            break
    return top[0][2][2]


def _safe(state):
    legal = state.get('legal_actions') or [{'action': 'struggle'}]
    try:
        mv = state['active_pokemon']['moves']
        best = None
        bp = -1
        for a in legal:
            if a.get('action') == 'move':
                p = (mv[a['index']].get('power') or 0) * (mv[a['index']].get('accuracy') or 100)
                if p > bp:
                    bp = p
                    best = a
        if best:
            return best
    except Exception:
        pass
    return legal[0]


def choose_move(state):
    try:
        return _choose(state)
    except Exception:
        return _safe(state)

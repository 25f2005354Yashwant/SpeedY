"""Runtime memoisation of the organisers' engine (no engine file is modified).

`install()` replaces a few *pure* functions with cached wrappers by rebinding module
attributes at run time.  Battle logs are proven bit-identical to the stock engine by
`harness/prove_identical.py`; do not use this module before that proof passes.
"""
from __future__ import annotations

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    import engine.ai_core as ai_core
    import engine.ai_search as ai_search
    import engine.battle as battle
    import engine.cynthia as cynthia
    import engine.damage as damage
    import engine.stats as stats
    from engine.config import get_mechanics
    from engine.data import Move, Pokemon, load_all

    DATA = ai_core._get_data()
    # every module keeps its own lazily loaded GameData; share one instance so identity checks work
    ai_core._DATA = DATA
    cynthia._DATA = DATA
    import engine.baseline_policy as bp
    import engine.runner as runner
    bp._DATA = DATA
    runner._DATA = DATA
    CFG = get_mechanics()
    POK = DATA.pokemon
    MOV = DATA.moves

    # ---- key helpers -------------------------------------------------------------------
    def pk(p):
        tp = type(p)
        if tp is Pokemon:
            return p.identifier if POK.get(p.identifier) is p else None
        if tp is dict:
            s = p.get("species") or p.get("identifier") or p.get("pokemon") or ""
        elif tp is str:
            s = p
        else:
            return None
        s = s.strip().lower()
        return s if s in POK else None

    def mk(m):
        tm = type(m)
        if tm is Move:
            return m.identifier if MOV.get(m.identifier) is m else None
        if tm is str:
            s = m.strip().lower()
            return s if s in MOV else None
        if tm is dict:
            mid = m.get("identifier") or m.get("name") or ""
            if mid:
                s = mid.strip().lower()
                if s in MOV:
                    return s
            return ("syn", mid, m.get("type", "normal"), m.get("category", "physical"), m.get("power"),
                    m.get("accuracy", 100), m.get("priority", 0), m.get("drain", 0), m.get("crit_rate", 0))
        return None

    def sk(st):
        if st is None:
            return None
        return tuple(st.items())

    # ---- expected_damage ---------------------------------------------------------------
    orig_ed = ai_core.expected_damage
    ed_cache = {}

    def expected_damage(attacker, move, defender, data=None, config=None, attacker_stages=None,
                        defender_stages=None, attacker_burned=False, attacker_crit_stage=0, level=50):
        if (data is None or data is DATA) and (config is None or config is CFG):
            ka = pk(attacker)
            kd = pk(defender)
            km = mk(move)
            if ka is not None and kd is not None and km is not None:
                key = (ka, km, kd, sk(attacker_stages), sk(defender_stages), attacker_burned,
                       attacker_crit_stage, level)
                try:
                    return ed_cache[key]
                except KeyError:
                    v = orig_ed(attacker, move, defender, data=data, config=config,
                                attacker_stages=attacker_stages, defender_stages=defender_stages,
                                attacker_burned=attacker_burned, attacker_crit_stage=attacker_crit_stage,
                                level=level)
                    ed_cache[key] = v
                    return v
        return orig_ed(attacker, move, defender, data=data, config=config, attacker_stages=attacker_stages,
                       defender_stages=defender_stages, attacker_burned=attacker_burned,
                       attacker_crit_stage=attacker_crit_stage, level=level)

    ai_core.expected_damage = expected_damage
    ai_search.expected_damage = expected_damage

    # ---- can_ko ------------------------------------------------------------------------
    orig_ko = ai_core.can_ko
    ko_cache = {}

    def can_ko(attacker, move, defender, defender_current_hp, data=None, config=None, min_roll=85,
               attacker_stages=None, defender_stages=None, attacker_burned=False, level=50):
        if (data is None or data is DATA) and (config is None or config is CFG):
            ka = pk(attacker)
            kd = pk(defender)
            km = mk(move)
            if ka is not None and kd is not None and km is not None:
                # min damage does not depend on HP; cache it and compare
                key = (ka, km, kd, min_roll, sk(attacker_stages), sk(defender_stages), attacker_burned, level,
                       defender_current_hp)
                try:
                    return ko_cache[key]
                except KeyError:
                    v = orig_ko(attacker, move, defender, defender_current_hp, data=data, config=config,
                                min_roll=min_roll, attacker_stages=attacker_stages,
                                defender_stages=defender_stages, attacker_burned=attacker_burned, level=level)
                    ko_cache[key] = v
                    return v
        return orig_ko(attacker, move, defender, defender_current_hp, data=data, config=config,
                       min_roll=min_roll, attacker_stages=attacker_stages, defender_stages=defender_stages,
                       attacker_burned=attacker_burned, level=level)

    ai_core.can_ko = can_ko
    ai_search.can_ko = can_ko

    # ---- calculate_damage (battle engine + cynthia.est_damage) ---------------------------
    orig_cd = damage.calculate_damage
    cd_cache = {}

    def calculate_damage(attacker, defender, move, type_chart, attacker_stages=None, defender_stages=None,
                         attacker_burned=False, is_crit=False, roll=100, level=50, config=None):
        if type_chart is DATA.type_chart and (config is None or config is CFG) and type(move) is Move \
                and type(attacker) is Pokemon and type(defender) is Pokemon \
                and POK.get(attacker.identifier) is attacker and POK.get(defender.identifier) is defender \
                and MOV.get(move.identifier) is move:
            key = (attacker.identifier, defender.identifier, move.identifier, sk(attacker_stages), sk(defender_stages),
                   attacker_burned, is_crit, roll, level)
            try:
                return cd_cache[key]
            except KeyError:
                v = orig_cd(attacker, defender, move, type_chart, attacker_stages=attacker_stages,
                            defender_stages=defender_stages, attacker_burned=attacker_burned, is_crit=is_crit,
                            roll=roll, level=level, config=config)
                cd_cache[key] = v
                return v
        return orig_cd(attacker, defender, move, type_chart, attacker_stages=attacker_stages,
                       defender_stages=defender_stages, attacker_burned=attacker_burned, is_crit=is_crit,
                       roll=roll, level=level, config=config)

    battle.calculate_damage = calculate_damage

    # ---- deepcopy of JSON-like observation fragments in ai_search -----------------------
    def jcopy(o):
        t = type(o)
        if t is dict:
            r = {}
            for k, v in o.items():
                tv = type(v)
                r[k] = jcopy(v) if (tv is dict or tv is list) else v
            return r
        if t is list:
            return [jcopy(v) if (type(v) is dict or type(v) is list) else v for v in o]
        return o

    class _Copy:
        deepcopy = staticmethod(jcopy)

    ai_search.copy = _Copy

    # ---- calc_stats (returns a fresh dict each call, like the original) ------------------
    orig_cs = stats.calc_stats
    cs_cache = {}

    def calc_stats(pokemon, level=50, iv=31, ev=0):
        if type(pokemon) is Pokemon and POK.get(pokemon.identifier) is pokemon:
            key = (pokemon.identifier, level, iv, ev)
            v = cs_cache.get(key)
            if v is None:
                v = cs_cache[key] = orig_cs(pokemon, level=level, iv=iv, ev=ev)
            return dict(v)
        return orig_cs(pokemon, level=level, iv=iv, ev=ev)

    for mod in (ai_core, cynthia, damage, battle):
        if hasattr(mod, "calc_stats"):
            mod.calc_stats = calc_stats

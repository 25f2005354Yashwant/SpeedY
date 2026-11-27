"""Phase 2 — stand-in opponents for the hidden variants, built from PUBLIC information only:
the docs' description of `aggressive` / `patient`, the public variant files, and public learnsets.

Naming:  t_* = tune set,  h_* = held-out set (never used for search/tuning).
usage: python -m tools_ours.make_standins
"""
import json
import random
from pathlib import Path

from harness import core

core._init()
D = core._state["data"]
OUT = Path("harness/standins")
OUT.mkdir(parents=True, exist_ok=True)
PUBLIC = json.load(open("variants/public.json"))

BASE = {k: v for k, v in PUBLIC.items() if k not in ("variant", "team", "lead_order")}

# Behaviour presets. `aggressive`/`patient` follow SIMULATOR_SPEC §9 ("never switches, favours big hits" /
# "switches readily, favours status") using the public style hooks in engine/ai_core.py.
STYLES = {
    "balanced": {},
    "aggressive": {"style": "aggressive", "aggression": 1.8, "switch_threshold": 9.0, "switch_cooldown": 99,
                   "danger_threshold": 0.95, "weak_offense_threshold": 0.1, "priority_weight": 1.3},
    "patient": {"style": "patient", "aggression": 0.65, "switch_threshold": 1.2, "switch_cooldown": 1,
                "danger_threshold": 0.5, "weak_offense_threshold": 0.6, "status_weight": 1.8,
                "endgame_closer_weight": 1.5},
    "patient2": {"style": "patient", "aggression": 0.8, "switch_threshold": 1.5, "switch_cooldown": 2,
                 "danger_threshold": 0.6, "weak_offense_threshold": 0.7, "status_weight": 1.5},
    "aggressive2": {"style": "aggressive", "aggression": 1.5, "switch_cooldown": 6, "priority_weight": 1.8},
}

SPECIAL = None


def usable(sp):
    return sorted(m for m in D.learnsets.get(sp, ()) if D.is_move_supported(m) and (D.moves[m].power or 0) > 0
                  and (D.moves[m].max_hits or 1) == 1 and D.moves[m].identifier not in
                  ("guillotine", "horn-drill", "fissure", "sheer-cold"))


def heuristic_set(sp):
    """Best STAB per own type + best coverage by distinct type; favours the stronger attacking stat."""
    p = D.pokemon[sp]
    best = {}
    for m in usable(sp):
        mv = D.moves[m]
        stat = p.attack if mv.category == "physical" else p.sp_atk
        s = mv.power * ((mv.accuracy or 100) / 100.0) * stat * (1.5 if mv.type in p.types else 1.0)
        if mv.drain < 0:
            s *= 0.9
        if mv.type not in best or s > best[mv.type][0]:
            best[mv.type] = (s, m)
    ranked = sorted(best.values(), reverse=True)
    out = [m for _, m in ranked[:4]]
    pool = [m for m in usable(sp) if m not in out]
    while len(out) < 4 and pool:
        out.append(pool.pop(0))
    return out


def random_set(sp, rng):
    mv = usable(sp)
    strong = [m for m in mv if D.moves[m].power >= 60]
    src = strong if len(strong) >= 4 else mv
    return rng.sample(src, 4)


TEAMS = {
    # tune
    "t_sinnoh": ["spiritomb", "roserade", "togekiss", "lucario", "milotic", "garchomp"],
    "t_water": ["milotic", "gyarados", "swampert", "starmie", "lapras", "empoleon"],
    "t_icerock": ["mamoswine", "weavile", "tyranitar", "rhyperior", "froslass", "abomasnow"],
    "t_bulky": ["snorlax", "blissey", "hippowdon", "milotic", "dusknoir", "tangrowth"],
    "t_fastphys": ["weavile", "garchomp", "infernape", "staraptor", "aerodactyl", "floatzel"],
    "t_boss": ["giratina-altered", "garchomp", "lucario", "milotic", "togekiss", "roserade"],
    "t_mixed": ["tyranitar", "salamence", "metagross", "gengar", "swampert", "electivire"],
    # held-out
    "h_dragons": ["garchomp", "dragonite", "salamence", "kingdra", "flygon", "altaria"],
    "h_fire": ["infernape", "arcanine", "charizard", "houndoom", "magmortar", "blaziken"],
    "h_steel": ["metagross", "lucario", "scizor", "magnezone", "empoleon", "bronzong"],
    "h_special": ["alakazam", "gengar", "porygon-z", "togekiss", "magnezone", "starmie"],
    "h_legends": ["dialga", "palkia", "giratina-altered", "cresselia", "heatran", "garchomp"],
    "h_poison": ["roserade", "venusaur", "toxicroak", "drapion", "crobat", "tentacruel"],
    "h_elecpsy": ["electivire", "jolteon", "raichu", "gardevoir", "gallade", "espeon"],
}
STYLE_OF = {"t_sinnoh": "balanced", "t_water": "patient", "t_icerock": "aggressive", "t_bulky": "patient",
            "t_fastphys": "aggressive", "t_boss": "balanced", "t_mixed": "balanced",
            "h_dragons": "aggressive2", "h_fire": "aggressive", "h_steel": "patient2", "h_special": "balanced",
            "h_legends": "balanced", "h_poison": "patient", "h_elecpsy": "aggressive2"}


def write(name, team, style, lead=None):
    cfg = dict(BASE)
    cfg.update(STYLES[style])
    cfg["variant"] = name
    cfg["team"] = team
    cfg["lead_order"] = lead or [0, 1, 2, 3, 4, 5]
    cfg["closer_species"] = team[-1]["species"] if name[2:] not in ("aggr", "patient") else "garchomp"
    (OUT / f"{name}.json").write_text(json.dumps(cfg, indent=1))


def main():
    names = []
    pub = PUBLIC["team"]
    # --- behaviour variants of the public team -------------------------------------------------
    write("t_aggr", pub, "aggressive")
    write("t_patient", pub, "patient")
    write("h_aggr2", pub, "aggressive2", lead=[5, 3, 1, 0, 2, 4])
    write("h_patient2", pub, "patient2", lead=[0, 2, 4, 1, 3, 5])
    names += ["t_aggr", "t_patient", "h_aggr2", "h_patient2"]
    # --- alternative movesets on the public species -------------------------------------------
    for nm, seed, style in (("t_altmoves", 11, "balanced"), ("t_altmoves_aggr", 12, "aggressive"),
                            ("h_altmoves", 21, "balanced"), ("h_altmoves_patient", 22, "patient")):
        rng = random.Random(seed)
        team = []
        for mon in pub:
            sp = mon["species"]
            ms = heuristic_set(sp) if rng.random() < 0.5 else random_set(sp, rng)
            team.append({"species": sp, "moves": ms})
        write(nm, team, style)
        names.append(nm)
    # --- different teams: heuristic movesets and random movesets ------------------------------
    for nm, sps in TEAMS.items():
        write(nm, [{"species": s, "moves": heuristic_set(s)} for s in sps], STYLE_OF[nm])
        rng = random.Random(nm)
        write(nm + "_r", [{"species": s, "moves": random_set(s, rng)} for s in sps], "balanced")
        names += [nm, nm + "_r"]
    print(len(names), "stand-ins written")
    for n in names:
        cfg = json.load(open(OUT / f"{n}.json"))
        for mon in cfg["team"]:
            assert mon["species"] in D.pokemon and all(m in D.moves for m in mon["moves"]) and len(mon["moves"]) == 4, mon
        print(n, cfg["style"], [(m["species"], m["moves"]) for m in cfg["team"]][:2], "...")
    json.dump({"tune": sorted(n for n in names if n.startswith("t_")),
               "heldout": sorted(n for n in names if n.startswith("h_"))}, open(OUT / "_sets.json", "w"), indent=1)


if __name__ == "__main__":
    main()

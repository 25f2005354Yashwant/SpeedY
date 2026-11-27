"""Parallel battle harness for Cynthia's Gauntlet.

Calls the organisers' engine unchanged.  Differences from `engine.runner.run_battle`:
  * the opponent is always the one requested (no silent public -> policy swap);
  * policy latency, fallbacks and turn-limit losses are recorded;
  * opponents may be public variants or our own stand-in JSON files (harness/standins/).

Hidden variants are never touched: any name/path pointing at `variants_private` is refused.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # engine loads "cynthia_data" relative to cwd

PUBLIC_VARIANTS = ("public", "policy", "offensive", "defensive", "speed", "status")
STANDIN_DIR = ROOT / "harness" / "standins"
FORBIDDEN_NAMES = {"aggressive", "patient"}  # names of the hidden files; never resolve these via the engine

TUNE_BASE = 1_000_000
FINAL_BASE = 900_000_000

_FAST = os.environ.get("HARNESS_STOCK", "0") != "1"
_state: Dict[str, Any] = {}


def _init():
    if _state:
        return
    if _FAST:
        from harness import fast
        fast.install()
    import engine.ai_core as ai_core
    from engine.baseline_policy import choose_move as baseline
    from engine.battle import Battle
    from engine.cynthia import CynthiaBot
    from engine.validator import validate_team
    _state.update(data=ai_core._get_data(), baseline=baseline, Battle=Battle, CynthiaBot=CynthiaBot,
                  validate=validate_team, policies={}, bots={})


def opp_path(opp: str) -> Path:
    """Resolve an opponent name to a config file we are allowed to read."""
    if opp in PUBLIC_VARIANTS:
        p = ROOT / "variants" / f"{opp}.json"
    else:
        if opp in FORBIDDEN_NAMES or "variants_private" in opp:
            raise PermissionError(f"refusing hidden variant reference: {opp}")
        p = Path(opp)
        if not p.is_file():
            p = STANDIN_DIR / f"{opp}.json"
    p = p.resolve()
    if "variants_private" in p.parts or not p.is_file():
        raise PermissionError(f"opponent config not allowed / not found: {opp}")
    return p


def load_team(team: Any) -> List[Dict[str, Any]]:
    if isinstance(team, (str, Path)):
        s = str(team)
        team = json.loads(Path(s).read_text()) if not s.lstrip().startswith(("[", "{")) else json.loads(s)
    if isinstance(team, dict):
        team = team["pokemon"]
    return [{"species": (m.get("species") or m.get("pokemon")), "moves": list(m["moves"])} for m in team]


def validate(team: Any) -> Tuple[bool, List[str]]:
    _init()
    return _state["validate"](load_team(team), data=_state["data"])


def team_cost(team: Any) -> int:
    _init()
    return sum(_state["data"].costs[m["species"]] for m in load_team(team))


def get_policy(path: Optional[str]) -> Optional[Callable]:
    if not path:
        return None
    _init()
    key = (path, os.path.getmtime(path))
    pol = _state["policies"].get(key)
    if pol is None:
        from engine.policy import load_policy_from_source
        pol = load_policy_from_source(Path(path).read_text(encoding="utf-8"), sandbox=False)
        _state["policies"][key] = pol
    return pol


def play(team: List[Dict[str, Any]], opp: str, seed: int, policy: Optional[Callable] = None,
         debug: bool = False, boss: Optional[bool] = None) -> Dict[str, Any]:
    """One battle. Mirrors engine/runner.py:run_battle's loop exactly (minus validation and the swap).

    boss: None -> engine default (boss mode only for the `policy` variant on ~30% of seeds).
    """
    _init()
    Battle, CynthiaBot, baseline = _state["Battle"], _state["CynthiaBot"], _state["baseline"]
    path = opp_path(opp)
    cynthia = CynthiaBot(variant=path.stem, config_path=path)
    engine_variant = "policy" if opp == "policy" else ("public" if opp == "public" else cynthia.variant)
    if engine_variant == "policy" and opp != "policy":
        engine_variant = "standin"
    battle = Battle(team_a=team, team_b=cynthia.team_for_seed(seed), seed=seed, data=_state["data"],
                    debug=debug, variant=engine_variant)
    pol = policy if policy is not None else baseline
    fallbacks = 0
    max_lat = 0.0
    tot_lat = 0.0
    calls = 0

    def call(obs, forced):
        nonlocal fallbacks, max_lat, tot_lat, calls
        if policy is None:
            return baseline(obs)
        if hasattr(pol, "last_fallback_reason"):
            pol.last_fallback_reason = None
        t0 = time.perf_counter()
        act = pol(obs)
        dt = time.perf_counter() - t0
        calls += 1
        tot_lat += dt
        if dt > max_lat:
            max_lat = dt
        if getattr(pol, "last_fallback_reason", None):
            fallbacks += 1
            return act
        if forced:
            legal = [a["index"] for a in obs.get("legal_actions", []) if a.get("action") == "switch"]
            if not isinstance(act, dict) or act.get("action") != "switch" or act.get("index") not in legal:
                fallbacks += 1
                return baseline(obs)
        elif not battle._is_legal("a", act):
            fallbacks += 1
            return baseline(obs)
        return act

    while not battle.is_over:
        if battle.needs_replacement("a"):
            obs_a = battle.observation("a")
            action_a = call(obs_a, True)
            legal_a = [a["index"] for a in obs_a.get("legal_actions", []) if a.get("action") == "switch"]
            idx_a = action_a.get("index") if action_a.get("action") == "switch" else None
            if idx_a not in legal_a:
                idx_a = legal_a[0] if legal_a else 0
            battle.replace("a", idx_a)
        if battle.needs_replacement("b"):
            obs_b = battle.observation("b")
            action_b = cynthia.choose_move(obs_b)
            legal_b = [a["index"] for a in obs_b.get("legal_actions", []) if a.get("action") == "switch"]
            idx_b = action_b.get("index") if action_b.get("action") == "switch" else None
            if idx_b not in legal_b:
                idx_b = legal_b[0] if legal_b else 0
            battle.replace("b", idx_b)
        if battle.is_over:
            break
        if not battle.needs_replacement("a") and not battle.needs_replacement("b"):
            obs_a = battle.observation("a")
            obs_b = battle.observation("b")
            act_a = call(obs_a, False)
            act_b = cynthia.choose_move(obs_b)
            battle.step(act_a, act_b)

    return {
        "win": battle.winner == "a", "turns": battle.turn, "end_reason": battle.end_reason,
        "fallbacks": fallbacks, "max_lat": max_lat, "tot_lat": tot_lat, "calls": calls,
        "log": battle.log if debug else None,
        "alive_a": sum(1 for p in battle.teams["a"] if not p.fainted),
        "alive_b": sum(1 for p in battle.teams["b"] if not p.fainted),
    }


# ----------------------------------------------------------------------------------------------
# parallel evaluation
# ----------------------------------------------------------------------------------------------
def _work(args):
    team, opp, seeds, policy_path = args
    if policy_path:
        # fresh policy module per chunk: results must not depend on which worker ran which chunk before
        _state["policies"].clear()
    pol = get_policy(policy_path)
    out = []
    for s in seeds:
        r = play(team, opp, s, pol)
        out.append((1 if r["win"] else 0, r["turns"], 1 if r["end_reason"] == "turn_limit_reached" else 0,
                    r["fallbacks"], r["max_lat"], r["tot_lat"], r["calls"]))
    return out


_pool = None
N_PROCS = int(os.environ.get("HARNESS_PROCS", 0)) or max(1, (os.cpu_count() or 2) - 1)


def pool():
    global _pool
    if _pool is None:
        import multiprocessing as mp
        _pool = mp.get_context("fork").Pool(N_PROCS, initializer=_init)
    return _pool


def wilson(w: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def run_jobs(jobs: Sequence[Tuple[Any, str, Sequence[int], Optional[str]]], chunk: int = 10) -> List[List[tuple]]:
    """jobs: (team, opp, seeds, policy_path). Returns per-job list of per-seed tuples (seed order)."""
    tasks = []
    index = []
    for j, (team, opp, seeds, pp) in enumerate(jobs):
        team = load_team(team)
        opp_path(opp)
        seeds = list(seeds)
        for i in range(0, len(seeds), chunk):
            tasks.append((team, opp, seeds[i:i + chunk], pp))
            index.append(j)
    res: List[List[tuple]] = [[] for _ in jobs]
    if N_PROCS == 1 or len(tasks) == 1:
        _init()
        outs = map(_work, tasks)
    else:
        outs = pool().imap(_work, tasks, chunksize=1)
    for j, out in zip(index, outs):
        res[j].extend(out)
    return res


def summarise(rows: Sequence[tuple]) -> Dict[str, Any]:
    n = len(rows)
    w = sum(r[0] for r in rows)
    wt = [r[1] for r in rows if r[0]]
    lo, hi = wilson(w, n)
    calls = sum(r[6] for r in rows)
    return {
        "n": n, "wins": w, "wr": w / n if n else 0.0, "lo": lo, "hi": hi,
        "turns_in_wins": (sum(wt) / len(wt)) if wt else 0.0,
        "turn_limit_losses": sum(r[2] for r in rows),
        "fallbacks": sum(r[3] for r in rows),
        "max_lat_ms": 1000 * max((r[4] for r in rows), default=0.0),
        "mean_lat_ms": 1000 * sum(r[5] for r in rows) / calls if calls else 0.0,
    }


def evaluate(team: Any, opps: Sequence[str], n: int, base: int = TUNE_BASE,
             policy_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Common random numbers: every team/opponent uses seeds base..base+n-1."""
    seeds = range(base, base + n)
    res = run_jobs([(team, o, seeds, policy_path) for o in opps])
    out = {}
    for o, rows in zip(opps, res):
        s = summarise(rows)
        s["rows"] = rows
        out[o] = s
    return out


def sha1(path: str) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()

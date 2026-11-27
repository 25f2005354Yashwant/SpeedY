"""Build `policy.py` from `policy_src/template.py`: pack public game data into strings, minify, size-check.

usage: python -m tools_ours.build_policy [--out submission/with_policy/policy.py] [--set NAME=VALUE ...]
Data sources: cynthia_data/*.csv (public), variants/public.json + variants/policy.json (public rosters).
"""
import argparse
import io
import json
import re
import tokenize
from pathlib import Path

from harness import core

TY = ['normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting', 'poison', 'ground', 'flying', 'psychic',
      'bug', 'rock', 'ghost', 'dragon', 'dark', 'steel']
MOD = 1048573


def h(s, k):
    x = 0
    for c in s:
        x = (x * k + ord(c)) % MOD
    return x


def find_k(names):
    for k in range(131, 5000):
        if len({h(n, k) for n in names}) == len(names):
            return k
    raise RuntimeError("no collision-free multiplier")


def pack():
    core._init()
    D = core._state["data"]
    kp = find_k(list(D.pokemon))
    km = find_k(list(D.moves))
    pk = []
    for p in D.pokemon.values():
        if not (p.fully_evolved or p.is_legendary or p.is_mythical):
            continue
        t = "".join(chr(97 + TY.index(x)) for x in p.types).ljust(2, "z")
        pk.append("%05x" % h(p.identifier, kp) + t + "".join("%02x" % v for v in
                  (p.hp, p.attack, p.defense, p.sp_atk, p.sp_def, p.speed)))
    mv = []
    drain = {0: "0", 50: "h", -25: "q", -33: "t", -50: "f"}
    fixed = {"sonic-boom": 20, "dragon-rage": 40, "seismic-toss": 50, "night-shade": 50}
    for m in D.moves.values():
        if m.category == "status":
            continue
        if not (m.power or m.identifier in fixed):
            continue
        used_by_cynthia = m.identifier in ("shadow-force",)
        if not (D.is_move_supported(m.identifier) or used_by_cynthia):
            continue
        hits = "1" if not m.max_hits else ("2" if m.min_hits == m.max_hits else "m")
        pw = m.power or 0
        fx = "x" if m.identifier in fixed else ("1" if m.crit_rate else "0")
        if m.identifier in fixed:
            pw = fixed[m.identifier]
        mv.append("%05x" % h(m.identifier, km) + chr(97 + TY.index(m.type)) + ("p" if m.category == "physical" else "s")
                  + "%02x" % pw + "%02x" % (m.accuracy or 0) + str(m.priority if m.priority > 0 else 0)
                  + drain[m.drain] + hits + fx)
    tc = "".join({0.0: "0", 0.5: "1", 1.0: "2", 2.0: "3"}[D.type_chart.effectiveness(a, d)] for a in TY for d in TY)
    ro = {}
    for v in ("public", "policy"):
        for mon in json.load(open(f"variants/{v}.json"))["team"]:
            ro[mon["species"]] = mon["moves"]
    ros = ";".join(s + ":" + ",".join(ms) for s, ms in ro.items())
    return {"PK": "".join(pk), "MV": "".join(mv), "TC": tc, "RO": ros, "KP": str(kp), "KM": str(km)}


def minify(src):
    """Drop comments/docstrings/blank lines and shrink indentation to 1 space per level."""
    out = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    drop = set()
    for i, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            drop.add(i)
        if t.type == tokenize.STRING and i > 0 and toks[i - 1].type in (tokenize.INDENT, tokenize.NEWLINE, tokenize.NL) \
                and i + 1 < len(toks) and toks[i + 1].type == tokenize.NEWLINE and t.string.startswith(('"""', "'''")):
            drop.add(i)
    lines = src.split("\n")
    kill = {}
    for i in drop:
        t = toks[i]
        (r1, c1), (r2, c2) = t.start, t.end
        if r1 == r2:
            kill.setdefault(r1, []).append((c1, c2))
        else:
            for r in range(r1, r2 + 1):
                kill.setdefault(r, []).append((0 if r > r1 else c1, len(lines[r - 1]) if r < r2 else c2))
    res = []
    for n, line in enumerate(lines, 1):
        for c1, c2 in sorted(kill.get(n, []), reverse=True):
            line = line[:c1] + line[c2:]
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip(" "))
        res.append(" " * (ind // 4) + line.strip())
    return "\n".join(res) + "\n"


def build(out, sets=None, dev=None):
    src = Path("policy_src/template.py").read_text()
    data = pack()
    for k, v in data.items():
        assert f"@{k}@" in src, k
        src = src.replace(f"@{k}@", v)
    for kv in (sets or []):
        k, v = kv.split("=", 1)
        src, n = re.subn(rf"(?m)^{k} *=.*$", f"{k} = {v}", src)
        assert n == 1, f"constant {k} not found exactly once"
    if dev:
        Path(dev).write_text(src)
    mini = minify(src)
    compile(mini, "policy.py", "exec")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(mini)
    size = len(mini.encode("utf-8"))
    return size


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="policy_src/build/policy.py")
    ap.add_argument("--dev", default="policy_src/build/policy_dev.py")
    ap.add_argument("--set", action="append", default=[])
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    size = build(a.out, a.set, a.dev)
    print(f"{a.out}: {size} bytes ({'OK' if size < 31000 else 'TOO BIG'}; limit 31000)")
    from engine.policy import check_policy_file
    print("check:", check_policy_file(Path(a.out)))

"""SRAM Vmin Studio — entry point (run from anywhere; paths resolve from this file).

    .venv/bin/python service/main.py serve [--port 8765] [--no-browser] [--source auto|source|bundle]
    .venv/bin/python service/main.py run service/scenarios/paper/fig11_bounded_levers.json [...]
    .venv/bin/python service/main.py verify [preset ...]   # presets with an "expect" block
    .venv/bin/python service/main.py list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vmin.config import CFG, RUNS  # noqa: E402


def _engine(source: str | None):
    from vmin.engine import Engine
    t = time.time()
    e = Engine.load(source)
    print(f"models loaded in {time.time() - t:.0f} s  ({', '.join(f'{m}: {mm.source}' for m, mm in e.modes.items())})")
    return e


def _print_result(r: dict) -> None:
    print(f"\n== {r['title']}  [{r['status']}]  {r.get('elapsed_s', 0):.1f} s  -> {RUNS / r['id']}")
    if r["status"] != "done":
        print("   ERROR:", r.get("error"))
        return
    for c in r["summary"]:
        print(f"   {c['label']}: {c['value']}" + (f"   ({c['hint']})" if c.get("hint") else ""))
    for n in r["notes"]:
        print("   note:", n)
    for v in r.get("verification") or []:
        print(f"   {'PASS' if v['ok'] else 'FAIL'}  {v['ledger']:<6} {v['path']} = {v['actual']}"
              f"  (expected {v['expected']} ± {v['tol']})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default=CFG["service"]["host"])
    s.add_argument("--port", type=int, default=CFG["service"]["port"])
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--source", choices=["auto", "source", "bundle"])
    r = sub.add_parser("run")
    r.add_argument("specs", nargs="+", type=Path)
    r.add_argument("--source", choices=["auto", "source", "bundle"])
    v = sub.add_parser("verify")
    v.add_argument("names", nargs="*")
    v.add_argument("--source", choices=["auto", "source", "bundle"])
    sub.add_parser("list")
    a = ap.parse_args()

    from vmin import server

    if a.cmd == "list":
        for p in server.presets():
            print(f"{p['name']:<40} {p['kind']:<12} {p['title']}" + (f"   [expect {p['expect']}]" if p["expect"] else ""))
        return 0
    if a.cmd == "serve":
        server.serve(_engine(a.source), a.host, a.port, not a.no_browser)
        return 0
    engine = _engine(a.source)
    engine.selfcheck()          # fills the saved §V-D table the point analysis compares against
    if a.cmd == "run":
        bad = 0
        for p in a.specs:
            res = server.execute(engine, json.loads(p.read_text(encoding="utf-8")), progress=lambda m: print("  ..", m))
            _print_result(res)
            bad += res["status"] != "done" or not all(x["ok"] for x in res.get("verification") or [])
        return int(bad > 0)
    names = a.names or [p["name"] for p in server.presets() if p["expect"]]
    fails = 0
    for name in names:
        spec = server.preset(name) | {"_preset": name}
        res = server.execute(engine, spec, progress=lambda m: print("  ..", m))
        _print_result(res)
        fails += res["status"] != "done" or not all(x["ok"] for x in res.get("verification") or [])
    print(f"\nverify: {len(names) - fails}/{len(names)} presets reproduce their expected values")
    return int(fails > 0)


if __name__ == "__main__":
    raise SystemExit(main())

"""One-shot: renumber references into IEEE order of first citation.

    .venv/bin/python manuscript/code/renumber_refs.py [--apply]

IEEE numbers references by first appearance in the text. This bibliography grew section
by section, so the list order drifted from the citation order. The script derives the map
from the English body, asserts the Korean body has the same order, then rewrites both
bodies and re-sorts both reference lists.

Kept in code/ because it is the only record of the old -> new map; older notes in
DECISIONS.md and LEDGER.md still name references by the old numbers.
"""
import argparse
import re
import sys

import _paths  # noqa: F401
from _paths import MANUSCRIPT

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true", help="write the files; otherwise dry-run")
args = ap.parse_args()

FILES = {"paper_en.md": "## References", "paper_kr.md": "## 참고문헌"}


def citation_order(body):
    """First-appearance order, expanding [a]-[b] ranges to a..b."""
    order, seen = [], set()
    for m in re.finditer(r"\[(\d+)\](?:\s*[–-]\s*\[(\d+)\])?", body):
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        for n in range(lo, hi + 1):
            if n not in seen:
                seen.add(n)
                order.append(n)
    return order


def split_entries(refs):
    """-> {number: full entry text}. An entry runs until the next one starts."""
    parts = re.split(r"\n(?=\[\d+\] )", refs.strip())
    out = {}
    for part in parts:
        m = re.match(r"\[(\d+)\] ", part)
        assert m, f"unparsed reference block: {part[:60]!r}"
        out[int(m.group(1))] = part.rstrip()
    return out


texts = {f: (MANUSCRIPT / f).read_text() for f in FILES}
orders = {f: citation_order(t.split(FILES[f], 1)[0]) for f, t in texts.items()}
assert len(set(map(tuple, orders.values()))) == 1, f"languages disagree: {orders}"

MAP = {old: new for new, old in enumerate(orders["paper_en.md"], start=1)}
print("map:", "  ".join(f"{o}→{MAP[o]}" for o in sorted(MAP)))

for f in FILES:
    body = texts[f].split(FILES[f], 1)[0]
    # a citation range must stay contiguous, or "[22]-[24]" turns into nonsense
    for lo, hi in re.findall(r"\[(\d+)\]\s*[–-]\s*\[(\d+)\]", body):
        span = sorted(MAP[n] for n in range(int(lo), int(hi) + 1))
        assert span == list(range(span[0], span[-1] + 1)), f"{f}: range [{lo}]-[{hi}] breaks"

for f, head in FILES.items():
    body, refs = texts[f].split(head, 1)
    # double brackets as a scratch marker: the source contains none, so no collision
    body = re.sub(r"\[(\d+)\]", lambda m: f"[[{MAP[int(m.group(1))]}]]", body)
    body = body.replace("[[", "[").replace("]]", "]")

    entries = split_entries(refs)
    assert set(entries) == set(MAP), f"{f}: list {sorted(entries)} != cited {sorted(MAP)}"
    renumbered = {}
    for old, text in entries.items():
        renumbered[MAP[old]] = re.sub(r"^\[\d+\]", f"[{MAP[old]}]", text)
    refs_out = "\n\n".join(renumbered[n] for n in sorted(renumbered))
    texts[f] = body + head + "\n\n" + refs_out + "\n"
    print(f"{f}: {len(entries)} entries renumbered and re-sorted")

if not args.apply:
    print("\ndry run -- nothing written (pass --apply)")
    sys.exit(0)

for f, t in texts.items():
    (MANUSCRIPT / f).write_text(t)
    print("wrote", f)

"""QC round 2 -- the two language versions must be the same paper.

    .venv/bin/python manuscript/code/qc_parity.py [-v]

Splits both files at the `## ` section headers (which appear in the same order in both)
and compares, per section: the multiset of numbers, the count of tables, figures,
citations and blockquote paragraphs. A number present in one language and not the other
is the failure mode this catches -- it is how a caveat silently goes missing from one
version during editing.

Numbers are compared as printed strings, because that is what a reader sees. Section and
table numerals (I, II, ... XVIII), reference markers and the roman numerals inside
`Sec. V-B` / `제5절 B항` are stripped first, since those are language-specific by design.
"""
import argparse
import re
import sys
from collections import Counter

import _paths  # noqa: F401
from _paths import MANUSCRIPT

ap = argparse.ArgumentParser()
ap.add_argument("-v", action="store_true", help="list every difference, not the first 5")
args = ap.parse_args()

KR = (MANUSCRIPT / "paper_kr.md").read_text()
EN = (MANUSCRIPT / "paper_en.md").read_text()

# Text that is language-specific by construction and must not enter the comparison.
DROP = [
    r"\[\d+\]",                       # citation markers
    r"(?:TABLE|표) [IVX]+\.",         # table numerals
    r"(?:Fig\.|그림) \d+",            # figure numbers
    r"Sections? [IVX]+(?:-[A-Z])?",   # English section refs (IEEE spells "Section" out)
    r"제\d+절(?: [A-Z]항)?",          # Korean section refs
    r"Appendix [A-C]", r"부록 [A-C]",
    r"[DNOFT]-\d+",                   # ledger / decision IDs
]
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?(?:\s*×\s*10⁻?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)?")


def sections(text):
    """-> [(title, body)] split at '## ' headers, header line excluded from the body."""
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    return [(p.split("\n", 1)[0].strip(), p.split("\n", 1)[1] if "\n" in p else "")
            for p in parts]


def numbers(body):
    for pat in DROP:
        body = re.sub(pat, " ", body)
    out = Counter()
    for raw in NUM.findall(body):
        n = raw.replace(",", "").rstrip(".")
        # Bare small integers are counted words: English spells "nine axes", Korean
        # writes "9개 축". Comparing them produces only noise. Measured quantities --
        # anything with a decimal point or of order 100+ -- are what must match.
        if "." in n or "×" in n or float(re.sub(r"\s*×.*", "", n) or 0) >= 100:
            out[n] += 1
    return out


kr, en = sections(KR), sections(EN)
fails = []

if len(kr) != len(en):
    fails.append(f"STRUCT section count: KR {len(kr)}, EN {len(en)}")
    print(f"KR sections: {[t for t, _ in kr]}")
    print(f"EN sections: {[t for t, _ in en]}")
else:
    for (kt, kb), (et, eb) in zip(kr, en):
        # distinct values, not counts: one language repeating "z(0.625 V)" twice while
        # the other says it once is phrasing, not drift. A value present on one side only
        # is drift.
        kn, en_ = set(numbers(kb)), set(numbers(eb))
        only_kr, only_en = kn - en_, en_ - kn
        if only_kr or only_en:
            fails.append(f"NUMBERS  {et}\n"
                         f"    KR only: {sorted(only_kr)}\n"
                         f"    EN only: {sorted(only_en)}")
        for label, pat_kr, pat_en in (
                ("tables", r"\*\*표 [IVX]+\.", r"\*\*TABLE [IVX]+\."),
                ("figures", r"\*\*그림 \d", r"\*\*Fig\. \d"),
                ("citations", r"\[\d+\]", r"\[\d+\]")):
            a = len(re.findall(pat_kr, kb, re.M))
            b = len(re.findall(pat_en, eb, re.M))
            if a != b:
                fails.append(f"COUNT    {et}: {label} KR {a} vs EN {b}")
        # blockquotes carry the caveats, so a missing one is a missing hedge. Count
        # blocks, not lines -- the same paragraph wraps to fewer lines in Korean.
        a, b = (sum(1 for i, ln in enumerate(body.split("\n"))
                    if ln.startswith(">") and not body.split("\n")[i - 1].startswith(">"))
                for body in (kb, eb))
        if a != b:
            fails.append(f"COUNT    {et}: blockquote blocks KR {a} vs EN {b}")

for f in fails:
    print("FAIL " + f)
print(f"\n{len(kr)} sections compared, {len(fails)} problems")
sys.exit(1 if fails else 0)

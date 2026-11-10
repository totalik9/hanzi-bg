"""Validate pinyin_utils tone conversion against the full CC-CEDICT syllable set.

CC-CEDICT stores numeric pinyin only. The check is a round-trip: convert the
numeric syllable to a tone-marked one and back, and confirm the letters and the
tone number survive unchanged. CC-CEDICT spells the umlaut as "u:" (or "v"),
so those spellings are compared against each other.

Entries whose pinyin is not plain lowercase Mandarin (e.g. "Qu1", "11", "C")
are counted separately: they are proper nouns / symbols in the dictionary and
are not tone-bearing pinyin, so they are excluded from the strict round-trip.
"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import pinyin_number_to_tones, tone_marked_to_number  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEDICT = os.path.join(ROOT, "data", "raw", "cedict_1_0_ts_utf-8_mdbg.txt")

MARKED = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü")
MACRONS = set("̄́̌̀")
LOWER = set("abcdefghijklmnopqrstuvwxyz")

bad = []
total = 0
skipped = Counter()
syls = Counter()
with open(CEDICT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            continue
        m = re.match(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]", line)
        if not m:
            continue
        for tok in m.group(3).split():
            total += 1
            syls[tok] += 1
            letters = tok.rstrip("0123456789")
            tone = tok[len(letters):]
            if not letters or not set(letters) <= LOWER:
                skipped["non-standard-token"] += 1
                continue
            if tone not in ("1", "2", "3", "4", "5", ""):
                skipped["bad-tone"] += 1
                continue
            out = pinyin_number_to_tones(tok)
            if not set(out) <= (LOWER | MARKED | MACRONS):
                bad.append((tok, out, "illegal-chars"))
                continue
            back = tone_marked_to_number(out)
            # A source token with no tone digit is a neutral tone; the reverse
            # conversion writes it explicitly as "5", so compare on that basis.
            expected = tok.replace("v", "u:")
            if not tone:
                expected += "5"
            if back.replace("ü", "u:") != expected:
                bad.append((tok, out, back))

print("total pinyin tokens in CC-CEDICT:", total, "| unique:", len(syls))
print("skipped non-standard tokens:", sum(skipped.values()), dict(skipped))
print("strict round-trip mismatches:", len(bad))
for b in bad[:25]:
    print("   ", b)

print("\nsample conversions:")
for tok in ["ni3", "hao3", "zhong1", "lv4", "nv3", "liu2", "gui4", "xue2", "jun1",
            "quan2", "er2", "e4", "lve4", "shei4", "duo1", "zhuang1"]:
    print(f"   {tok:8s} -> {pinyin_number_to_tones(tok)}")
sys.exit(1 if bad else 0)

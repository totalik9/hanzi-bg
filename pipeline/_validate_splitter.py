"""Validate the character-constrained pinyin splitter.

The HSK CSVs give run-together pinyin; phrase-pinyin-data gives the same
words space-separated. Splitting the HSK form with the character constraint
and comparing against the phrase reference is an end-to-end check.

Only the letters are compared (not the tones): the two sources legitimately
differ on tone sandhi ("bùkèqi" vs "bú kè qì") and on erhua spelling
("nàr" vs "nà ér").
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import (  # noqa: E402
    split_pinyin_by_chars,
    split_pinyin_syllables,
    strip_tones,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

char_readings = json.load(open(os.path.join(RAW, "char_readings.json"), encoding="utf-8"))

phrase_ref = {}
for line in open(os.path.join(RAW, "phrase_pinyin.txt"), encoding="utf-8"):
    line = line.rstrip("\n")
    if not line or line.startswith("#") or ": " not in line:
        continue
    w, py = line.split(": ", 1)
    phrase_ref[w] = py.strip()

total = ok = 0
bad = []
for f in sorted(os.listdir(RAW)):
    if not f.startswith("hsk_3_0_level_"):
        continue
    for row in csv.DictReader(open(os.path.join(RAW, f), encoding="utf-8-sig", newline="")):
        w = (row.get("simplified") or "").strip()
        py = (row.get("pinyin") or "").strip()
        ref = phrase_ref.get(w)
        if not py or not ref or " " not in ref or len(w) < 2:
            continue
        total += 1
        got = split_pinyin_by_chars(py, w, char_readings)
        if got is None:
            got = split_pinyin_syllables(py, n_syllables=len(w))
        want = ref.split()
        if strip_tones("".join(got)) == strip_tones("".join(want)):
            ok += 1
        elif len(bad) < 15:
            bad.append((w, py, got, want))

print(f"HSK multi-char words with a phrase-pinyin reference: {total}")
print(f"letter-level agreement: {ok}/{total} ({ok/total*100:.2f}%)")
print("mismatch examples:")
for b in bad:
    print("   ", b)

# also check the plain DP splitter (no character constraint) for comparison
total2 = ok2 = 0
for f in sorted(os.listdir(RAW)):
    if not f.startswith("hsk_3_0_level_"):
        continue
    for row in csv.DictReader(open(os.path.join(RAW, f), encoding="utf-8-sig", newline="")):
        w = (row.get("simplified") or "").strip()
        py = (row.get("pinyin") or "").strip()
        ref = phrase_ref.get(w)
        if not py or not ref or " " not in ref or len(w) < 2:
            continue
        total2 += 1
        got = split_pinyin_syllables(py, n_syllables=len(w))
        want = ref.split()
        if strip_tones("".join(got)) == strip_tones("".join(want)):
            ok2 += 1
print(f"\nwithout the character constraint: {ok2}/{total2} ({ok2/total2*100:.2f}%)")

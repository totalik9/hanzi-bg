"""Compare the HSK-CSV pinyin (split) against CC-CEDICT's space-separated pinyin.

CC-CEDICT covers 100% of HSK words with space-separated pinyin, so it is the
reference. This decides which source the vocab builder should trust.
"""
import csv, json, os, sqlite3, sys
sys.path.insert(0, r"C:/Users/IPP/projects/hanzi-bg/pipeline")
from pinyin_utils import split_pinyin_by_chars, split_pinyin_syllables, strip_tones

ROOT = r"C:/Users/IPP/projects/hanzi-bg"
RAW = os.path.join(ROOT, "data", "raw")
char_readings = json.load(open(os.path.join(RAW, "char_readings.json"), encoding="utf-8"))
conn = sqlite3.connect(os.path.join(ROOT, "data", "hanzi.db"))

ced = {}
for s, py in conn.execute("SELECT simplified, pinyin_with_tones FROM dict"):
    ced.setdefault(s, py)

hsk = {}
for f in sorted(os.listdir(RAW)):
    if f.startswith("hsk_3_0_level_"):
        for row in csv.DictReader(open(os.path.join(RAW, f), encoding="utf-8-sig", newline="")):
            w = (row.get("simplified") or "").strip()
            if w and w not in hsk:
                hsk[w] = (row.get("pinyin") or "").strip()

same = diff = 0
multi_same = multi_diff = 0
single_same = single_diff = 0
ex_multi = []
ex_single = []
for w, py in hsk.items():
    c = ced.get(w)
    if not c or not py:
        continue
    if len(w) == 1:
        got = split_pinyin_syllables(py)
    else:
        got = split_pinyin_by_chars(py, w, char_readings)
        if got is None:
            got = split_pinyin_syllables(py, n_syllables=len(w))
    if strip_tones("".join(got)) == strip_tones(c.replace(" ", "")):
        same += 1
        if len(w) == 1: single_same += 1
        else: multi_same += 1
    else:
        diff += 1
        if len(w) == 1:
            single_diff += 1
            if len(ex_single) < 10: ex_single.append((w, py, got, c))
        else:
            multi_diff += 1
            if len(ex_multi) < 10: ex_multi.append((w, py, got, c))

print(f"HSK csv pinyin vs CC-CEDICT: same={same} diff={diff}")
print(f"  single char: same={single_same} diff={single_diff}")
print(f"  multi char:  same={multi_same} diff={multi_diff}")
print("\nsingle-char differences:")
for e in ex_single: print("   ", e)
print("\nmulti-char differences:")
for e in ex_multi: print("   ", e)

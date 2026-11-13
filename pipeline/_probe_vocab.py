import csv, json, os, re, sqlite3, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from pinyin_utils import tone_marked_to_number  # noqa: E402

conn = sqlite3.connect(os.path.join(ROOT, "data", "hanzi.db"))
conn.row_factory = sqlite3.Row

# what do CC-CEDICT definition segments look like?
seg_pos = Counter()
all_segs = Counter()
for row in conn.execute("SELECT definition FROM dict LIMIT 40000"):
    for seg in row["definition"].split("/"):
        if seg:
            all_segs[seg] += 1

print("=== most common definition segments ===")
for s, c in all_segs.most_common(40):
    print(f"  {c:>7} {s!r}")

# how often does a POS-like segment appear?
POS_SET = {"n.", "v.", "vt.", "vi.", "adj.", "adv.", "pron.", "prep.", "conj.",
           "num.", "int.", "aux.", "art.", "abbr.", "modal v", "r", "s", "cl",
           "mf", "int", "n", "v"}
hits = 0
multi = 0
for row in conn.execute("SELECT definition FROM dict LIMIT 20000"):
    segs = [s for s in row["definition"].split("/") if s]
    pos_segs = [s for s in segs if s in POS_SET]
    if pos_segs:
        hits += 1
    if len(pos_segs) > 1:
        multi += 1
print(f"\nentries with >=1 POS segment (of 20000): {hits}, with >1: {multi}")

# how many HSK words have a POS marker?
words = {}
for lv, f in [("1","hsk_3_0_level_1.csv"),("2","hsk_3_0_level_2.csv"),
              ("3","hsk_3_0_level_3.csv"),("4","hsk_3_0_level_4.csv"),
              ("5","hsk_3_0_level_5.csv"),("6","hsk_3_0_level_6.csv"),
              ("7-9","hsk_3_0_level_7_9.csv")]:
    with open(os.path.join(ROOT, "data", "raw", f), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            h = (r.get("simplified") or "").strip()
            if h and h not in words:
                words[h] = (lv, (r.get("pinyin") or "").strip())

ced = {}
for row in conn.execute("SELECT simplified, pinyin_number, pinyin_with_tones, definition FROM dict"):
    ced.setdefault(row["simplified"], []).append(
        (row["pinyin_number"], row["pinyin_with_tones"], row["definition"]))

hsk_pos = 0
hsk_nopy = 0
space_diff = 0
same = 0
diff = 0
examples = []
for w, (lv, hskpy) in words.items():
    cands = ced.get(w)
    if not cands:
        continue
    num, marked, d = cands[0]
    segs = [s for s in d.split("/") if s]
    if any(s in POS_SET for s in segs):
        hsk_pos += 1
    else:
        hsk_nopy += 1
    # compare HSK pinyin (tone marks) vs CC-CEDICT marked pinyin
    if hskpy and marked:
        if hskpy.replace(" ", "") == marked.replace(" ", ""):
            same += 1
        else:
            diff += 1
            if len(examples) < 12:
                examples.append((w, hskpy, marked, num))
    if hskpy and " " not in hskpy and len(w) > 1:
        space_diff += 1

print(f"\nHSK words with a CC-CEDICT POS marker: {hsk_pos}; without: {hsk_nopy}")
print(f"pinyin identical (ignoring spaces): {same}; different: {diff}")
print(f"multi-char HSK words whose pinyin has no space: {space_diff}")
print("\npinyin differences (hsk_csv vs cedict):")
for e in examples:
    print("   ", e)

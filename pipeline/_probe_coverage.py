import csv, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import split_pinyin_syllables, tone_marked_to_number

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
conn = sqlite3.connect(os.path.join(ROOT, "data", "hanzi.db"))

# HSK words
hsk = {}
for f in sorted(os.listdir(RAW)):
    if f.startswith("hsk_3_0_level_"):
        for row in csv.DictReader(open(os.path.join(RAW, f), encoding="utf-8-sig", newline="")):
            w = (row.get("simplified") or "").strip()
            if w and w not in hsk:
                hsk[w] = (row.get("pinyin") or "").strip()

# phrase pinyin
phrase = {}
for line in open(os.path.join(RAW, "phrase_pinyin.txt"), encoding="utf-8"):
    if line.startswith("#") or ": " not in line: continue
    w, py = line.rstrip("\n").split(": ", 1)
    phrase[w] = py.strip()

# cedict
ced = {}
for s, py in conn.execute("SELECT simplified, pinyin_with_tones FROM dict"):
    ced.setdefault(s, py)

in_phrase = sum(1 for w in hsk if w in phrase)
in_ced = sum(1 for w in hsk if w in ced)
both = sum(1 for w in hsk if w in phrase and w in ced)
either = sum(1 for w in hsk if w in phrase or w in ced)
print(f"HSK words: {len(hsk)}")
print(f"  in phrase-pinyin-data: {in_phrase} ({in_phrase/len(hsk)*100:.1f}%)")
print(f"  in CC-CEDICT:           {in_ced} ({in_ced/len(hsk)*100:.1f}%)")
print(f"  in either:              {either} ({either/len(hsk)*100:.1f}%)")
print(f"  in both:                {both}")

missing = [w for w in hsk if w not in phrase and w not in ced]
print(f"\nmissing from both: {len(missing)}  e.g. {missing[:20]}")

# For words in phrase-pinyin, how does the HSK csv pinyin compare?
same = diff = 0
examples = []
for w, (hskpy) in hsk.items():
    if w in phrase and hskpy and " " not in phrase[w]:
        pass
    if w in phrase and hskpy:
        # compare ignoring spaces and case
        a = "".join(split_pinyin_syllables(hskpy, n_syllables=len(w))).lower()
        b = "".join(phrase[w].split()).lower()
        if a == b: same += 1
        else:
            diff += 1
            if len(examples) < 10: examples.append((w, hskpy, phrase[w]))
print(f"\nHSK csv pinyin vs phrase-pinyin (letters only): same={same} diff={diff}")
for e in examples: print("   ", e)

# how often do the TONES differ between HSK csv and phrase-pinyin?
tone_same = tone_diff = 0
tex = []
for w, (hskpy) in hsk.items():
    if w in phrase and hskpy and len(w) > 1:
        want = phrase[w].split()
        got = split_pinyin_syllables(hskpy, n_syllables=len(w))
        if len(got) == len(want):
            g = [tone_marked_to_number(x) for x in got]
            if g == want: tone_same += 1
            else:
                tone_diff += 1
                if len(tex) < 8: tex.append((w, got, want))
print(f"\ntone agreement (multi-char, phrase-pinyin): same={tone_same} diff={tone_diff}")
for e in tex: print("   ", e)

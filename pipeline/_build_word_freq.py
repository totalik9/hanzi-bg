"""Build a word frequency ranking from the Tatoeba Chinese corpus.

Counts how often each word appears in data/raw/cmn_sentences.tsv and writes
the words in descending frequency order to data/raw/word_freq.json:

    {"<word>": <rank>, ...}      # rank 1 = most frequent

The ranking is a real corpus frequency for Chinese (Tatoeba, CC BY 2.0 FR),
not an estimate. Words are counted by matching the longest HSK word first, so
multi-character words are not double-counted as their characters.
"""
import csv
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import RAW  # noqa: E402

SENTENCES = os.path.join(RAW, "cmn_sentences.tsv")
OUT = os.path.join(RAW, "word_freq.json")

LEVEL_FILES = [
    "hsk_3_0_level_1.csv", "hsk_3_0_level_2.csv", "hsk_3_0_level_3.csv",
    "hsk_3_0_level_4.csv", "hsk_3_0_level_5.csv", "hsk_3_0_level_6.csv",
    "hsk_3_0_level_7_9.csv",
]


def main() -> int:
    words: set[str] = set()
    for fname in LEVEL_FILES:
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                w = (row.get("simplified") or "").strip()
                if w:
                    words.add(w)

    # longest first so that "北京大学" wins over "北京"
    vocab = sorted(words, key=len, reverse=True)
    counts: Counter = Counter()
    n_lines = 0
    with open(SENTENCES, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            text = parts[2]
            n_lines += 1
            for w in vocab:
                if w in text:
                    counts[w] += 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    freq = {w: i + 1 for i, (w, _c) in enumerate(ranked)}

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(freq, fh, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"sentences scanned: {n_lines:,}")
    print(f"words with at least one occurrence: {len(freq):,} of {len(words):,}")
    print("top 25 by frequency:")
    for w, _c in ranked[:25]:
        print(f"   {w}  {counts[w]}")
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

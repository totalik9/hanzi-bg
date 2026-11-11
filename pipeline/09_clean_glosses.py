"""Clean the English glosses before they are translated.

CC-CEDICT is a dictionary for native speakers, not for learners, and a
few of its entries carry material that makes no sense once it is
translated:

  - cross-references: "used in 傢伙|家伙[jia1 huo5]", "also pr. [shui2]",
    "short name for Guizhou 貴州|贵州[Gui4 zhou1]"
  - an embedded reading: "eldest (as in 大姐[da4 jie3])"
  - a classifier the learner has no use for: "CL:個|个[ge4]"

Translated, these produce glosses like "Също така pr. [shui2]" and
"Кратко наименование за Гуичжоу 貴州" -- a learner sees Chinese
characters and a pinyin reading inside a Bulgarian definition, which
teaches nothing.

This script rewrites data/vocab_hsk.json so that every word carries a
gloss_en that is worth translating. It changes nothing else in the file:
the pinyin, the level and the tags stay as 03_build_vocab.py wrote them.

Where a word has no usable sense left, the meaning from the HSK word
list is used instead -- the HSK list is written for learners, so its
meanings are exactly what belongs in a flashcard.

The script is idempotent: running it twice changes nothing the second
time.

Usage:
    python pipeline/09_clean_glosses.py
    python pipeline/09_clean_glosses.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW  # noqa: E402

VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
HSK_CSV = [
    "hsk_3_0_level_1.csv",
    "hsk_3_0_level_2.csv",
    "hsk_3_0_level_3.csv",
    "hsk_3_0_level_4.csv",
    "hsk_3_0_level_5.csv",
    "hsk_3_0_level_6.csv",
    "hsk_3_0_level_7_9.csv",
]

# A sense that starts with one of these is not a meaning at all -- it
# points at another character, gives a pronunciation note, or names a
# classifier ("CL:個|个[ge4]") that the learner has no use for.
PURE_CROSS_REFERENCE = re.compile(
    r"^(?:also pr\.|pr\.|colloquial pr\.|Taiwan pr\.|used in |short name for |"
    r"see also |abbr\. for |abbr\. to |variant of |old variant of |"
    r"erhua (?:form|variant) of |surname |CL:)",
    re.IGNORECASE,
)

# A reading in square brackets: "[shui2]", "[Gui4 zhou1]".
READING = re.compile(r"\[[^\]]*\]")

# Chinese characters inside an English gloss. They only ever appear in a
# cross-reference ("short name for Guizhou 貴州").
HANZI = re.compile(r"[一-鿿]+")

# A parenthetical that only carries a cross-reference or an example.
PARENTHETICAL = re.compile(
    r"\s*\((?:as in|as in:|e\.g\.|cf\.|i\.e\.|see also)\s*[^)]*\)",
    re.IGNORECASE,
)


def clean_sense(sense: str) -> str | None:
    """Clean one English sense, or return None when it carries no meaning.

    >>> clean_sense("to know; to become aware of")
    'to know; to become aware of'
    >>> clean_sense("also pr. [shui2]") is None
    True
    >>> clean_sense("eldest (as in 大姐[da4 jie3])")
    'eldest'
    >>> clean_sense("short name for Guizhou 貴州|贵州[Gui4 zhou1]") is None
    True
    >>> clean_sense("friend/CL:個|个[ge4],位[wei4]".split("/")[0])
    'friend'
    """
    s = (sense or "").strip()
    if not s:
        return None
    if PURE_CROSS_REFERENCE.match(s):
        return None
    s = PARENTHETICAL.sub("", s)
    s = READING.sub("", s)
    s = HANZI.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,;/|")
    if not s:
        return None
    # The cleanup can expose a cross-reference that was hidden behind a
    # bracket: "you (courteous, as opposed to informal 你[ni3])" becomes
    # "you (courteous, as opposed to informal)".
    if PURE_CROSS_REFERENCE.match(s):
        return None
    return s


def load_hsk_meanings() -> dict[str, str]:
    """Read the English meaning of every HSK word from the HSK CSV lists.

    These meanings are written for learners, so they are the fallback
    when CC-CEDICT has nothing but a cross-reference to offer.
    """
    out: dict[str, str] = {}
    for name in HSK_CSV:
        path = os.path.join(RAW, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                meaning = (row.get("meaning") or "").strip()
                if meaning:
                    out.setdefault(row["simplified"], meaning)
    return out


def clean_definition(definition: str) -> str:
    """Clean a whole CC-CEDICT definition, sense by sense.

    The senses are separated by "/", which is also how CC-CEDICT writes
    them. A sense that turns out to be a cross-reference is dropped; the
    rest are joined back together.

    >>> clean_definition("friend/CL:個|个[ge4],位[wei4]")
    'friend'
    >>> clean_definition("to know; to become aware of/also pr. [zhi1dao5]")
    'to know; to become aware of'
    >>> clean_definition("who/also pr. [shui2]")
    'who'
    """
    parts = [p.strip() for p in (definition or "").split("/")]
    kept = [c for c in (clean_sense(p) for p in parts) if c]
    return "/".join(kept)


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean the English glosses")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the changes without writing the file")
    args = ap.parse_args()

    if not os.path.exists(VOCAB_JSON):
        print(f"ERROR: missing {VOCAB_JSON} - run 03_build_vocab.py first")
        return 1

    with open(VOCAB_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    words = data["words"] if isinstance(data, dict) else data

    hsk_meanings = load_hsk_meanings()
    print(f"HSK meanings available: {len(hsk_meanings):,}")

    changed = 0
    fell_back = 0
    dropped_senses = 0
    for w in words:
        hanzi = w.get("hanzi")
        original = w.get("gloss_en") or ""
        cleaned = clean_definition(original)
        if cleaned == original:
            continue
        if not cleaned:
            # Nothing survived. The HSK list's meaning is written for
            # learners, so it belongs in the flashcard.
            fallback = hsk_meanings.get(hanzi, "")
            if fallback:
                cleaned = clean_definition(fallback) or fallback
                fell_back += 1
        if not cleaned:
            # Neither source has anything. Leave the word alone rather
            # than inventing a gloss.
            print(f"  WARNING: no usable gloss for {hanzi} - left as is")
            continue
        w["gloss_en"] = cleaned
        changed += 1

    print(f"words whose English gloss changed: {changed:,}")
    print(f"  of those, taken from the HSK list: {fell_back:,}")

    if args.dry_run:
        print("dry run - nothing written")
        return 0

    with open(VOCAB_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"written: {VOCAB_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

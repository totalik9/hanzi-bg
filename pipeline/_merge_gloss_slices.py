"""Merge the gloss slices into the gloss patch of the HSK 2-4 path.

    python pipeline/_merge_gloss_slices.py

The slices are written by hand, one per group of lessons, and they are
merged into ONE file: `curriculum/21_glosses_hsk2to4.json`. The file is
the patch the content database is built from, so it has to hold every
word of the path file `12_hsk2to4.json` — and nothing else.

The merge is a MERGE, not a concat: a word that two slices both name
is a word two people wrote down differently, and that is a question
about the word, not about the merge. So the script says so and stops.

    python pipeline/_merge_gloss_slices.py     # write the file
    python pipeline/_merge_gloss_slices.py --check   # only report

WHY A SEPARATE FILE AND NOT A MERGE INTO 20_glosses_hsk1.json

The HSK-1 glosses are 300 words that are already shipped and already
reviewed. The HSK 2-4 glosses are 1678 new ones. Keeping them apart
means a change to the new ones cannot disturb the shipped ones, and
the two can be reviewed by different hands.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.environ.get("TMPDIR", ROOT)

PATH_FILE = os.path.join(ROOT, "curriculum", "12_hsk2to4.json")
OUT_FILE = os.path.join(ROOT, "curriculum", "21_glosses_hsk2to4.json")

#: The slices, in order. A slice is a group of whole lessons.
SLICE_COUNT = 17


def slice_path(index: int) -> str:
    return os.path.join(TMP, f"gloss_slice_{index:02d}.json")


def gloss_path(index: int) -> str:
    return os.path.join(TMP, f"glosses_{index:02d}.json")


def load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    check_only = "--check" in sys.argv

    path = load_json(PATH_FILE)
    path_words: list[str] = []
    for unit in path["units"]:
        for lesson in unit["lessons"]:
            path_words.extend(lesson.get("words") or [])

    merged: dict[str, str] = {}
    order: list[str] = []
    conflicts: list[str] = []
    missing_slices: list[int] = []

    for index in range(1, SLICE_COUNT + 1):
        gpath = gloss_path(index)
        if not os.path.exists(gpath):
            missing_slices.append(index)
            continue
        glosses = load_json(gpath)
        for hanzi, gloss in glosses.items():
            if hanzi in merged and merged[hanzi] != gloss:
                conflicts.append(
                    f"{hanzi}: '{merged[hanzi]}' in one slice and "
                    f"'{gloss}' in another")
                continue
            if hanzi not in merged:
                order.append(hanzi)
            merged[hanzi] = gloss

    if missing_slices:
        print(f"ERROR: {len(missing_slices)} slices are not written yet: "
              f"{', '.join(str(i) for i in missing_slices)}")
        return 1
    if conflicts:
        print(f"ERROR: {len(conflicts)} words are glossed differently in "
              f"two slices:")
        for conflict in conflicts:
            print(f"   ::error::{conflict}")
        return 1

    missing = [w for w in path_words if w not in merged]
    extra = sorted(set(merged) - set(path_words))
    if missing:
        print(f"ERROR: {len(missing)} words of the path have no gloss: "
              f"{' '.join(missing[:20])}")
        return 1
    if extra:
        print(f"ERROR: {len(extra)} glosses are for words that are not on "
              f"the path: {' '.join(extra[:20])}")
        return 1

    print(f"the path file: {len(path_words)} words")
    print(f"the glosses:   {len(merged)}")
    if check_only:
        print("OK (not written: --check)")
        return 0

    # The order of the file is the order of the path: the word is
    # written next to the lesson that teaches it, so a reader can find
    # it.
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump({w: merged[w] for w in path_words}, fh,
                  ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"written {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

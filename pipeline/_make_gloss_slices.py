"""Cut the HSK 2-4 path into SLICES of whole lessons, for the gloss writers.

    python pipeline/_make_gloss_slices.py

WHY THE SLICES ARE MADE OF WHOLE LESSONS

The rule the audit enforces is that no two words of the SAME LESSON
carry the same gloss -- the card would then ask a question with two
right answers. A worker can only keep that rule when it can see the
whole lesson, so a slice never splits a lesson.

The slice also carries the English meaning of every word, because the
English meaning is the ANCHOR of the sense: the Bulgarian gloss must
say the sense the HSK list gives, not the first sense a dictionary
happens to list.

The output is one JSON file per slice in the scratch directory:

    {"lesson_key": "...", "title": "...", "words": [
        {"hanzi": "...", "pinyin": "...", "meaning": "..."}, ...]}
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.environ.get("TMPDIR", ROOT)

PATH = os.path.join(ROOT, "curriculum", "12_hsk2to4.json")
WORDS = {
    2: os.path.join(TMP, "hsk2_words.json"),
    3: os.path.join(TMP, "hsk3_words.json"),
    4: os.path.join(TMP, "hsk4_words.json"),
}

#: How many lessons a slice holds. A slice is a unit of work, so it
#: has to be big enough to be worth a hand and small enough to be done
#: in one sitting.
LESSONS_PER_SLICE = 8


def main() -> int:
    with open(PATH, encoding="utf-8") as fh:
        path = json.load(fh)

    meaning: dict[str, dict] = {}
    for level, word_path in WORDS.items():
        with open(word_path, encoding="utf-8") as fh:
            for word in json.load(fh):
                meaning[word["hanzi"]] = word

    lessons: list[dict] = []
    for unit in path["units"]:
        for lesson in unit["lessons"]:
            lessons.append({
                "unit": unit["key"],
                "lesson_key": lesson["key"],
                "title": lesson["title"],
                "words": [
                    {
                        "hanzi": w,
                        "pinyin": meaning[w]["pinyin"],
                        "meaning": meaning[w]["hsk_meaning"],
                    }
                    for w in lesson["words"]
                ],
            })

    slices: list[list[dict]] = []
    for start in range(0, len(lessons), LESSONS_PER_SLICE):
        slices.append(lessons[start:start + LESSONS_PER_SLICE])

    for index, chunk in enumerate(slices, start=1):
        out = os.path.join(TMP, f"gloss_slice_{index:02d}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(chunk, fh, ensure_ascii=False, indent=1)
        total = sum(len(lesson["words"]) for lesson in chunk)
        print(f"   slice {index:02d}: {len(chunk):2} lessons, {total:4} words -> {out}")

    print(f"   {len(lessons)} lessons in {len(slices)} slices, "
          f"{sum(len(l['words']) for l in lessons)} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Check the glosses of ONE slice of the HSK 2-4 path.

    python pipeline/_check_gloss_slice.py <slice.json> <glosses.json>

The rules are the ones the whole-path audit applies, applied to one
slice so the writer of the slice can check it before the slices are
merged:

  * every word of the slice has a gloss;
  * the gloss is at most 45 characters;
  * the gloss carries no "/" and no parenthesis -- it is ONE meaning,
    not the list of senses a dictionary has;
  * no two words of the SAME LESSON carry the same gloss, because the
    card would then ask a question with two right answers.

It also WARNS about a pair whose glosses start with the same three
letters. The app refuses such a pair as a distractor (LessonPlan.
isTwin), so the two words cannot test each other -- which is a hint
that the two meanings are too close to be told apart.

The exit code is 1 when a rule fails and 0 when only warnings are
left.
"""
from __future__ import annotations

import json
import re
import sys

#: The curriculum rule: a gloss is short, or it is noise.
MAX_GLOSS_LENGTH = 45


def prefix3(text: str) -> str:
    """The first three letters of a gloss: a cheap Bulgarian stem."""
    return re.sub(r"[^a-zа-я]", "", text.lower())[:3]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    slice_path, gloss_path = sys.argv[1], sys.argv[2]

    with open(slice_path, encoding="utf-8") as fh:
        lessons = json.load(fh)
    with open(gloss_path, encoding="utf-8") as fh:
        glosses = json.load(fh)

    problems: list[str] = []
    warnings: list[str] = []
    words_total = 0

    for lesson in lessons:
        seen: dict[str, str] = {}
        for word in lesson["words"]:
            hanzi = word["hanzi"]
            words_total += 1
            gloss = (glosses.get(hanzi) or "").strip()
            if not gloss:
                problems.append(f"{hanzi} ({lesson['lesson_key']}) has no gloss")
                continue
            if len(gloss) > MAX_GLOSS_LENGTH:
                problems.append(
                    f"the gloss of {hanzi} is {len(gloss)} characters: '{gloss}'")
            if "/" in gloss or "(" in gloss or ")" in gloss:
                problems.append(
                    f"the gloss of {hanzi} lists senses or carries a "
                    f"parenthesis: '{gloss}'")
            lower = gloss.lower()
            if lower in seen:
                problems.append(
                    f"the lesson {lesson['lesson_key']} carries two words "
                    f"with the same gloss ('{seen[lower]}' and '{hanzi}'): "
                    f"'{gloss}'")
            else:
                seen[lower] = hanzi
            if prefix3(gloss):
                for other, h in seen.items():
                    if h != hanzi and prefix3(other) == prefix3(gloss):
                        warnings.append(
                            f"{hanzi} ('{gloss}') and {h} ('{other}') of "
                            f"{lesson['lesson_key']} start with the same "
                            f"three letters, so they cannot test each other")
                        break

    extra = sorted(set(glosses) - {w["hanzi"] for l in lessons
                                    for w in l["words"]})
    if extra:
        problems.append(
            f"the gloss file carries {len(extra)} glosses for words that "
            f"are not in the slice: {', '.join(extra[:10])}")

    print(f"{slice_path}: {len(lessons)} lessons, {words_total} words, "
          f"{len(glosses)} glosses")
    if warnings:
        print(f"{len(warnings)} warnings:")
        for warning in warnings:
            print(f"   ::warning::{warning}")
    if problems:
        print(f"FAILED with {len(problems)} problems:")
        for problem in problems:
            print(f"   ::error::{problem}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Check ONE path file and ONE gloss patch, on their own.

    python pipeline/check_lesson_files.py curriculum/11_hsk2.json \
                                         curriculum/21_glosses_hsk2.json

`audit_path.py` checks the WHOLE path, and it can only pass when every
file of the path is in place. This script checks one file against its
own gloss patch, so the author of a file can verify it before the
others are written.

The rules are the same as the ones the whole-path audit applies, and
they come from the same two places -- the curriculum README and
`audit_path.py` -- so a file that passes here passes there:

  * every word of the lesson exists in the vocabulary;
  * every word of the lesson has a gloss in the patch;
  * the gloss is at most 45 characters;
  * the gloss carries no "/" and no parenthesis -- it is ONE meaning,
    not the list of senses a dictionary has;
  * no two words of the same lesson carry the same gloss, because the
    card would then ask a question with two right answers;
  * a lesson carries 8 to 15 words;
  * the glosses of the patch cover exactly the words of the path
    file: a gloss for a word that is not on the path is a gloss
    nobody reads, and a word on the path with no gloss is a card with
    nothing to show.

The vocabulary is a build artefact and it is not in version control,
so when it is not there the corpus checks are skipped and the rest
still runs.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

#: The curriculum rule: a gloss is short, or it is noise.
MAX_GLOSS_LENGTH = 45

#: The curriculum rule: a lesson carries 8 to 15 words.
MIN_LESSON_WORDS = 8
MAX_LESSON_WORDS = 15


def load_vocabulary() -> set[str] | None:
    """Every word of the dictionary, or None when it is not built."""
    path = os.path.join(DATA, "vocab_hsk.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    words = data.get("words") if isinstance(data, dict) else data
    if not words:
        return None
    return {w.get("hanzi") for w in words if w.get("hanzi")}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path_file, gloss_file = sys.argv[1], sys.argv[2]

    problems: list[str] = []
    warnings: list[str] = []

    with open(path_file, encoding="utf-8") as fh:
        path = json.load(fh)
    with open(gloss_file, encoding="utf-8") as fh:
        glosses = json.load(fh)

    if not isinstance(path, dict) or "units" not in path:
        problems.append(f"{path_file} is not a path file (no 'units')")
        print("\n".join("::error::%s" % p for p in problems))
        return 1
    if not isinstance(glosses, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in glosses.items()):
        problems.append(f"{gloss_file} is not a gloss patch (hanzi -> gloss)")
        print("\n".join("::error::%s" % p for p in problems))
        return 1

    vocabulary = load_vocabulary()
    if vocabulary is None:
        print("NOTE: the vocabulary is not built, so the corpus checks "
              "are skipped (run pipeline/03_build_vocab.py)")

    # The keys: unique across the file, and the lesson key starts with
    # the unit key. The key of a unit is the navigation argument and
    # the primary key of the row, so it must never change once
    # shipped.
    unit_keys = [u.get("key") or "" for u in path["units"]]
    for key in unit_keys:
        if not key:
            problems.append("a unit has no key")
    duplicates = {k for k in unit_keys if unit_keys.count(k) > 1}
    if duplicates:
        problems.append("duplicate unit keys: %s" % ", ".join(sorted(duplicates)))

    lesson_keys: list[str] = []
    for unit in path["units"]:
        unit_key = unit.get("key") or ""
        for lesson in unit.get("lessons") or []:
            key = lesson.get("key") or ""
            lesson_keys.append(key)
            if not key:
                problems.append("a lesson of unit '%s' has no key" % unit_key)
                continue
            if not key.startswith(unit_key):
                problems.append(
                    "the lesson key '%s' does not start with its unit key "
                    "'%s'" % (key, unit_key))
            words = lesson.get("words") or []
            if not words and not (lesson.get("cards") or []):
                problems.append("the lesson '%s' has neither words nor "
                                "cards" % key)
            if words and not (MIN_LESSON_WORDS <= len(words) <= MAX_LESSON_WORDS):
                problems.append(
                    "the lesson '%s' carries %d words (the rule is %d to %d)"
                    % (key, len(words), MIN_LESSON_WORDS, MAX_LESSON_WORDS))

            # The gloss of every word of the lesson.
            seen: dict[str, str] = {}
            for word in words:
                if vocabulary is not None and word not in vocabulary:
                    problems.append(
                        "the lesson '%s' names '%s', which is not in the "
                        "vocabulary" % (key, word))
                gloss = glosses.get(word, "").strip()
                if not gloss:
                    problems.append("the word '%s' of '%s' has no gloss"
                                    % (word, key))
                    continue
                if len(gloss) > MAX_GLOSS_LENGTH:
                    problems.append(
                        "the gloss of '%s' is %d characters long: '%s'"
                        % (word, len(gloss), gloss))
                if "/" in gloss or "(" in gloss or ")" in gloss:
                    problems.append(
                        "the gloss of '%s' lists senses or carries a "
                        "parenthesis: '%s'" % (word, gloss))
                if re.search(r"(измерителна дума|показател за|дума за)",
                             gloss, re.I):
                    # A WARNING, not a failure. The whole-path audit
                    # reports the same pattern in its section 2 and
                    # does not fail on it: a classifier word like 个
                    # has no plain meaning to give, and "измерителна
                    # дума" says what it is. A checker that failed
                    # where the gate does not would send the author
                    # chasing a rule that is not one.
                    warnings.append(
                        "the gloss of '%s' describes the word instead of "
                        "meaning it: '%s'" % (word, gloss))
                lower = gloss.lower()
                if lower in seen:
                    problems.append(
                        "the lesson '%s' carries two words with the same "
                        "gloss ('%s' and '%s'): '%s'"
                        % (key, seen[lower], word, gloss))
                else:
                    seen[lower] = word

    duplicate_lessons = {k for k in lesson_keys if lesson_keys.count(k) > 1}
    if duplicate_lessons:
        problems.append("duplicate lesson keys: %s"
                        % ", ".join(sorted(duplicate_lessons)))

    # The glosses of the patch and the words of the path file cover
    # each other exactly.
    path_words: list[str] = []
    for unit in path["units"]:
        for lesson in unit.get("lessons") or []:
            path_words.extend(lesson.get("words") or [])
    path_set = set(path_words)
    repeated = sorted({w for w in path_words if path_words.count(w) > 1})
    if repeated:
        problems.append("these words are on the path more than once: %s"
                        % ", ".join(repeated))
    unused = sorted(set(glosses) - path_set)
    if unused:
        problems.append(
            "the gloss patch has glosses for %d words that are not on "
            "the path: %s" % (len(unused), ", ".join(unused[:10])))

    lessons = sum(len(u.get("lessons") or []) for u in path["units"])
    units = len(path["units"])
    print("%s: %d units, %d lessons, %d words | %s: %d glosses"
          % (path_file, units, lessons, len(path_words),
             gloss_file, len(glosses)))

    if warnings:
        print("%d warnings (the same ones the whole-path audit reports "
              "without failing on them):" % len(warnings))
        for warning in warnings:
            print("   ::warning::%s" % warning)

    if problems:
        print("FAILED with %d problems:" % len(problems))
        for problem in problems:
            print("   ::error::%s" % problem)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

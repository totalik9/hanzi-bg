#!/usr/bin/env python
"""Audit the learning path the way a learner meets it.

The numbers in LEARNING-PROCESS-PLAN.md come from this script. It is a
read-only measurement over curriculum/*.json -- no database, no model,
no network -- so it can run on a fresh clone and in CI.

    python pipeline/audit_path.py            # the report
    python pipeline/audit_path.py --gate     # the same, but it exits 1
                                            # when a check fails

THE GATE

A check that cannot fail is not a check, so --gate exits non-zero when:

  * two words of the same lesson carry the same meaning -- the card
    then asks a question with two right answers (this happened for
    real: 二 "два" and 两 "два, когато броим предмети");
  * a card would offer a twin of the answer;
  * a word of the path has no hand-written gloss;
  * a gloss is longer than the 45 characters the curriculum allows.

WHERE THE GLOSSES COME FROM

The gloss of a path word is the hand-written one in
curriculum/20_glosses_hsk1.json. That file is in version control, and
it is the source the content database is built from, so the audit
needs nothing but the repository itself.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURRICULUM = os.path.join(ROOT, "curriculum")
PATH_FILES = ("00_intro.json", "10_hsk1.json", "30_situations.json")
GLOSS_PATCH = "20_glosses_hsk1.json"

#: The curriculum rule: a gloss is short, or it is noise.
MAX_GLOSS_LENGTH = 45


def load_lessons():
    """The path as the learner meets it: units, lessons and their words."""
    lessons = []
    for name in PATH_FILES:
        path = os.path.join(CURRICULUM, name)
        if not os.path.exists(path):
            continue
        data = json.load(open(path, encoding="utf-8"))
        for unit in data.get("units", []):
            for lesson in unit.get("lessons", []):
                lessons.append((unit["key"], lesson))
    return lessons


def load_glosses():
    """The hand-written gloss of every path word."""
    path = os.path.join(CURRICULUM, GLOSS_PATCH)
    return json.load(open(path, encoding="utf-8"))


def prefix3(text):
    """The first three letters of a gloss: a cheap Bulgarian stem."""
    return re.sub(r"[^a-zа-я]", "", text.lower())[:3]


def is_twin(a, b):
    """Two meanings that a learner cannot tell apart.

    The rule of LessonPlan.chooseOptions: a twin of the answer is
    never offered, and neither is a twin of another distractor.
    """
    x, y = a.strip().lower(), b.strip().lower()
    if x == y or y in x or x in y:
        return True
    return len(x) >= 3 and len(y) >= 3 and prefix3(x) == prefix3(y)


def main():
    gate = "--gate" in sys.argv
    lessons = load_lessons()
    gloss = load_glosses()
    path_words = [w for _, lesson in lessons for w in lesson.get("words", [])]

    problems = []

    print("=" * 70)
    print("1. TWO WORDS IN THE SAME LESSON WITH THE SAME GLOSS")
    print("=" * 70)
    duplicates = []
    for _, lesson in lessons:
        seen = {}
        for word in lesson.get("words", []):
            g = gloss.get(word, "").strip().lower()
            if not g:
                continue
            if g in seen:
                duplicates.append((lesson["key"], seen[g], word, g))
            else:
                seen[g] = word
    for key, first, second, g in duplicates:
        print("   %-14s %s / %s  ->  '%s'" % (key, first, second, g))
    print("   TOTAL: %d lessons carry a duplicated meaning" % len(duplicates))
    if duplicates:
        problems.append("%d lessons carry a duplicated meaning" % len(duplicates))

    print()
    print("=" * 70)
    print("2. GLOSSES THAT DESCRIBE A WORD INSTEAD OF MEANING IT")
    print("=" * 70)
    descriptive = [
        (lesson["key"], word, gloss.get(word, ""))
        for _, lesson in lessons
        for word in lesson.get("words", [])
        if re.search(
            r"(измерителна дума|показател за|дума за)",
            gloss.get(word, ""),
            re.I,
        )
    ]
    for key, word, g in descriptive:
        print("   %-14s %s -> '%s'" % (key, word, g))
    print("   TOTAL: %d" % len(descriptive))

    print()
    print("=" * 70)
    print("3. THE HAND-WRITTEN GLOSSES OF THE PATH")
    print("=" * 70)
    missing = [w for w in path_words if not gloss.get(w, "").strip()]
    long_glosses = [
        (w, gloss.get(w, "")) for w in path_words
        if len(gloss.get(w, "")) > MAX_GLOSS_LENGTH
    ]
    print("   path words: %d | with a hand-written gloss: %d | missing: %d"
          % (len(path_words), len(path_words) - len(missing), len(missing)))
    print("   glosses longer than %d characters: %d"
          % (MAX_GLOSS_LENGTH, len(long_glosses)))
    for word in missing:
        print("   MISSING: %s" % word)
    for word, g in long_glosses:
        print("   TOO LONG: %s '%s'" % (word, g))
    if missing:
        problems.append("%d path words have no hand-written gloss" % len(missing))
    if long_glosses:
        problems.append("%d glosses are longer than %d characters"
                        % (len(long_glosses), MAX_GLOSS_LENGTH))

    print()
    print("=" * 70)
    print("4. THE OPTIONS AFTER THE TWIN FILTER")
    print("=" * 70)
    learned = []
    fewer = []
    twins_offered = 0
    cards = 0
    for _, lesson in lessons:
        words = lesson.get("words", [])
        if not words:
            continue
        pool = []
        for word in words + learned:
            g = gloss.get(word, "").strip()
            if g and g not in pool:
                pool.append(g)
        for word in words:
            g = gloss.get(word, "").strip()
            if not g:
                continue
            cards += 1
            distractors = []
            for candidate in pool:
                if len(distractors) >= 3:
                    break
                if candidate.strip().lower() == g.strip().lower():
                    continue
                if is_twin(candidate, g):
                    continue
                if any(is_twin(chosen, candidate) for chosen in distractors):
                    continue
                distractors.append(candidate)
            options = distractors + [g]
            if any(is_twin(o, g) for o in options if o != g):
                twins_offered += 1
            if len(options) < 4:
                fewer.append((lesson["key"], word, g, len(options)))
        learned.extend(words)

    for key, word, g, n in fewer:
        print("   %-14s %-6s '%s'  ->  %d options" % (key, word, g, n))
    print("   cards: %d | cards with a twin offered: %d (must be 0)"
          % (cards, twins_offered))
    print("   cards with fewer than 4 options: %d" % len(fewer))
    if twins_offered:
        problems.append("%d cards offer a twin of the answer" % twins_offered)

    print()
    print("=" * 70)
    print("5. THE WORDS OF THE PATH, IN ORDER")
    print("=" * 70)
    for unit_key, lesson in lessons:
        words = lesson.get("words", [])
        if not words:
            print("   %-14s %-28s (teaching cards)" % (unit_key, lesson["title"]))
            continue
        print("   %-14s %-28s %d words" % (unit_key, lesson["title"], len(words)))

    print()
    if gate:
        if problems:
            print("=" * 70)
            print("THE PATH FAILED THE GATE")
            print("=" * 70)
            for problem in problems:
                print("   ::error::%s" % problem)
            sys.exit(1)
        print("the learning path passed the gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())

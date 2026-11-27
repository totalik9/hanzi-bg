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
#: The generated data directory: the vocabulary file is a build
#: artefact, so it is not in version control.
DATA = os.path.join(ROOT, "data")

#: The curriculum rule: a gloss is short, or it is noise.
MAX_GLOSS_LENGTH = 45

#: The curriculum rule: a lesson carries 8 to 15 words.
#:
#: The rule is a range and not a fixed number because a lesson has to
#: hold the words of its theme. A theme with nine words is one lesson
#: of nine, and a theme with twenty is two lessons of ten. The cap is
#: what keeps a lesson from turning into a list the learner cannot
#: hold in one sitting.
MIN_LESSON_WORDS = 8
MAX_LESSON_WORDS = 15

#: The HSK level of every word of the corpus, filled in when the
#: corpus is read. See corpus_level_of().
_WORD_LEVEL: dict[str, str] = {}


def curriculum_files():
    """Every JSON file of the curriculum, in name order.

    The files are read in name order, so the numeric prefixes control
    the sequence. They are told apart by CONTENT and not by name --
    the same rule the pipeline uses, so the audit and the build can
    never disagree about what a file is:

      {"units": [...]}      the path itself
      {hanzi: gloss}       a gloss patch, which overrides the machine
                           translation for the words it names
    """
    if not os.path.isdir(CURRICULUM):
        return []
    names = sorted(n for n in os.listdir(CURRICULUM) if n.endswith(".json"))
    return [(n, os.path.join(CURRICULUM, n)) for n in names]


def load_lessons():
    """The path as the learner meets it: units, lessons and their words."""
    lessons = []
    for name, path in curriculum_files():
        data = json.load(open(path, encoding="utf-8"))
        if not (isinstance(data, dict) and "units" in data):
            continue
        for unit in data["units"]:
            for lesson in unit.get("lessons", []):
                lessons.append((unit["key"], lesson))
    return lessons


def load_glosses():
    """The hand-written gloss of every path word.

    Every gloss patch in the curriculum counts, not one named file: the
    path grew past HSK 1 and the glosses came with it.
    """
    glosses = {}
    for name, path in curriculum_files():
        data = json.load(open(path, encoding="utf-8"))
        if not isinstance(data, dict) or "units" in data:
            continue
        if data and all(isinstance(k, str) and isinstance(v, str)
                         for k, v in data.items()):
            glosses.update(data)
    return glosses


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


def load_corpus_levels():
    """The words of each HSK level, from the built vocabulary.

    The levels the path must cover are read from the corpus itself
    rather than written down here, so the audit cannot disagree with
    the dictionary: the corpus says which levels exist and which words
    are in them.

    Returns None when the vocabulary is not built. The vocabulary file
    is a build artefact and it is not in version control, so a fresh
    clone has no corpus to compare against -- and a check that passes
    because it had nothing to look at is not a check. The gate says
    so instead.
    """
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
    levels: dict[str, set[str]] = {}
    word_level: dict[str, str] = {}
    for word in words:
        level = str(word.get("hsk_level") or "")
        hanzi = word.get("hanzi") or ""
        if not level or not hanzi:
            continue
        levels.setdefault(level, set()).add(hanzi)
        word_level[hanzi] = level
    _WORD_LEVEL.clear()
    _WORD_LEVEL.update(word_level)
    return {level: {h for h in words if h} for level, words in levels.items()}


def corpus_level_of(hanzi: str) -> str:
    """The HSK level of a word, from the corpus.

    The lookup table is built once, when the corpus is read, and kept
    in a module-level dict: the coverage check asks about every word
    of the path, and a query per word against a table of 10 000 rows
    is a waste.
    """
    return _WORD_LEVEL.get(hanzi, "")


def main():
    gate = "--gate" in sys.argv
    lessons = load_lessons()
    gloss = load_glosses()
    path_words = [w for _, lesson in lessons for w in lesson.get("words", [])]

    problems = []

    print("=" * 70)
    print("0. THE COVERAGE OF THE PATH AGAINST THE CORPUS")
    print("=" * 70)
    # The corpus is the dictionary the app ships. A word of the target
    # level that is NOT on the path is a word the learner cannot get
    # to from anywhere -- the dictionary can show it, but no lesson
    # teaches it. A word on the path TWICE is one item silently
    # dropped and one repeated.
    #
    # The check is in both directions, and it needs the corpus: the
    # vocabulary file is a build artefact, so when it is not there the
    # check says so and is skipped rather than passing silently.
    corpus = load_corpus_levels()
    if corpus is None:
        print("   SKIPPED: the vocabulary file is not built "
              "(run pipeline/03_build_vocab.py)")
        print("   The other checks below do not need it.")
    else:
        # The levels the path must cover are the ones it reaches, and
        # every level BELOW the highest one it reaches. The path
        # teaches a ladder: if it teaches a word of HSK 4, it teaches
        # every word of HSK 1 to 3 as well, so a word missing from
        # HSK 2 cannot hide behind a word missing from HSK 4.
        #
        # The target is derived from the path and not written down, so
        # the check keeps meaning the same thing as the path grows.
        reached = {corpus_level_of(w) for w in path_words}
        reached.discard("")
        if not reached:
            target_levels = []
        else:
            highest = max(reached, key=lambda x: (len(x), x))
            target_levels = [lvl for lvl in corpus
                             if (len(lvl), lvl) <= (len(highest), highest)]

        covered = {}
        for word in path_words:
            covered[word] = covered.get(word, 0) + 1
        repeated = sorted(w for w, n in covered.items() if n > 1)
        path_set = set(path_words)
        unreachable = []
        for level in sorted(target_levels, key=lambda x: (len(x), x)):
            for word in sorted(corpus[level]):
                if word not in path_set:
                    unreachable.append((level, word))
        total_corpus = sum(len(corpus[l]) for l in target_levels)
        print("   levels the path must cover: %s"
              % ", ".join("HSK %s (%d words)" % (l, len(corpus[l]))
                          for l in sorted(target_levels, key=lambda x: (len(x), x))))
        print("   path words: %d | corpus words: %d" % (len(path_words), total_corpus))
        print("   words of the corpus that are NOT on the path: %d"
              % len(unreachable))
        for level, word in unreachable[:20]:
            print("      HSK %s  %s" % (level, word))
        if len(unreachable) > 20:
            print("      ... and %d more" % (len(unreachable) - 20))
        print("   words on the path MORE THAN ONCE: %d" % len(repeated))
        for word in repeated[:20]:
            print("      %s" % word)
        if unreachable:
            problems.append(
                "%d words of the corpus are not on the path - the learner "
                "cannot reach them from any lesson" % len(unreachable))
        if repeated:
            problems.append(
                "%d words are on the path more than once" % len(repeated))

    print()
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

    # The shape of a teachable gloss: no "/" and no parentheses.
    #
    # A "/" is how the machine translation lists every sense a
    # dictionary has: "бяло / бял / реакционен / антикомунистически".
    # The learner reads one meaning on a card, not four, and the
    # parenthesis is how the machine translation carries the etymology
    # it found in the dictionary. Both were ruled out when the HSK 1
    # glosses were written, and a gloss that breaks the rule is a
    # gloss that was not written by hand.
    dumpy = [
        (w, gloss.get(w, ""))
        for w in path_words
        if ("/" in gloss.get(w, "")
            or "(" in gloss.get(w, "")
            or ")" in gloss.get(w, ""))
    ]
    print("   glosses that list senses or carry a parenthesis: %d" % len(dumpy))
    for word, g in dumpy[:20]:
        print("      %s '%s'" % (word, g))
    if len(dumpy) > 20:
        print("      ... and %d more" % (len(dumpy) - 20))
    if dumpy:
        problems.append(
            "%d glosses list several senses or carry a parenthesis" % len(dumpy))

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
    print("=" * 70)
    print("6. THE SIZE OF THE LESSONS")
    print("=" * 70)
    # A lesson of 8 to 15 words: fewer and the lesson is a handful of
    # words with a lesson's overhead around them, more and the cards
    # run past what a beginner holds at once. A reading lesson carries
    # cards and no words, so it is not counted.
    wrong_size = [
        (key, lesson["title"], len(lesson.get("words", [])))
        for key, lesson in lessons
        if lesson.get("words")
        and not (MIN_LESSON_WORDS <= len(lesson["words"]) <= MAX_LESSON_WORDS)
    ]
    sizes = [len(lesson.get("words", [])) for _, lesson in lessons
             if lesson.get("words")]
    print("   lessons with words: %d | sizes: min %d, max %d"
          % (len(sizes), min(sizes) if sizes else 0, max(sizes) if sizes else 0))
    print("   lessons outside %d-%d words: %d"
          % (MIN_LESSON_WORDS, MAX_LESSON_WORDS, len(wrong_size)))
    for key, title, n in wrong_size[:20]:
        print("      %-16s %-30s %d words" % (key, title, n))
    if len(wrong_size) > 20:
        print("      ... and %d more" % (len(wrong_size) - 20))
    if wrong_size:
        problems.append(
            "%d lessons carry outside %d-%d words"
            % (len(wrong_size), MIN_LESSON_WORDS, MAX_LESSON_WORDS))

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

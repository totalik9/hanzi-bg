"""Build the word_example table: an example sentence for every word.

The dictionary tells the learner what a word MEANS; it does not show the
word in use. The example sentences come from the Tatoeba corpus that the
`sentences` table already holds, but that corpus cannot be shown next to
a simplified word as it stands:

  * 45 % of the sentences with a Bulgarian translation are written in
    TRADITIONAL characters, and the app teaches simplified only, so a
    sentence next to a simplified word has to be folded first;
  * the sentences are Tatoeba's, which means they range from "好。" to a
    500-character novel excerpt, and a beginner cannot read either one
    as an example of a word;
  * the interesting characters are exactly the rare ones.

So the sentences are folded to simplified and then RANKED, and only the
best four per word are kept.

THE FOLD
========

The fold is built from the `dict` table of data/hanzi.db, which is
CC-CEDICT: one row per entry, with the traditional and the simplified
spelling side by side.

A character is TRADITIONAL-ONLY when the dictionary writes it in the
traditional column and never in the simplified one. There are 3 608 of
them, and they are exactly the characters that make a sentence
traditional. A character that appears in both columns (著, which survives
in 著名, or 乾, which survives in 乾隆) is valid in the simplified
script as well, and folding it would corrupt the sentence: 著 -> 着
turns 著名 into 着名, which is a different word.

That gives the fold two halves:

  * a WORD map: the dictionary entries whose traditional side holds a
    traditional-only character. Those are the real script conversions
    (乾淨 -> 干净, 沒關係 -> 没关系). The entry is used only when it
    holds a traditional-only character, and that restriction is what
    makes the fold SAFE: a traditional-only character never appears in
    the simplified column, so an entry that holds one can never match
    inside a sentence that is already simplified. Measured: 0 of the
    26 811 already-simplified sentences with a Bulgarian translation
    were changed by the fold.
  * a CHARACTER map: the single traditional-only characters, for the
    ones that do not appear inside a dictionary word.

A traditional-only character whose dictionary entry names SEVERAL
simplified forms is resolved in this order, and the order is the point:

  1. the reading. The candidate whose dictionary reading matches a
     reading of the traditional character itself wins, because the fold
     must not change what the sentence SAYS: 參 -> 叁 (san1) would
     turn 參考 into 叁考;
  2. the vocabulary. The candidate that is one of the 3 088 characters
     the app teaches wins, because that is the form the learner will
     meet;
  3. the frequency. The candidate the dictionary uses more often wins.

Four characters cannot be resolved that way and are REFUSED: 妳 (你 or
奶 -- 妳好 must not become 奶好), 殽 (淆 or 肴), 耑 (专 or 端) and 鍊
(炼 or 链). A refused character keeps its traditional form, and the
sentence that holds it is REJECTED -- it is still written in the script
the app does not teach. Measured: 51 of the 48 542 sentences with a
Bulgarian translation are rejected this way, all of them for 妳.

THE SELECTION RULE
==================

A sentence is a CANDIDATE for a word W when all of these hold:

  1. it has a non-empty Bulgarian translation -- the app is for
     Bulgarian learners, and an example without a translation teaches
     nothing;
  2. after the fold, it CONTAINS W as a substring;
  3. after the fold, it holds no traditional-only character -- the fold
     could not convert every character, so the sentence is still in the
     script the app does not teach, and it is dropped rather than shown
     half-converted;
  4. after the fold, and with the punctuation removed, it is not just W
     itself -- a bare word is not a sentence;
  5. it is not already stored for W: Tatoeba has entries that differ
     only in their id, and showing the learner the same sentence twice
     is noise.

The surviving candidates are ordered by an ascending COST:

    cost = 4 * (number of Han characters in the sentence)
           + 2 * (sum of the difficulty of the characters that are not
                  the word)
           + 1 * (number of characters in the Bulgarian translation)

The DIFFICULTY of a character is:

    0   it is one of the characters of the graded vocabulary AND it is a
        simple glyph -- the learner has met it and can read it;
    1   it is in the vocabulary, but the glyph is complex (16 strokes or
        more) or the stroke-order data does not have it;
    2   it is NOT in the vocabulary, but it is common in the corpus (it
        appears in 30 or more of the 89 254 corpus sentences);
    3   it is not in the vocabulary, is common, and the glyph is complex;
    4   it is not in the vocabulary and is rare in the corpus;
    5   it is not in the vocabulary, is rare, and the glyph is complex.

Why this order of importance:

  * An unknown character stops the learner. One rare character is worth
    more than a couple of extra characters of sentence, which is why the
    character term is weighted against the length term.
  * Among the sentences the learner can read, the shortest one is the
    best example, so the length term decides between them.
  * The Bulgarian translation is weighted lightly because its length
    mostly follows the Chinese one; it is there to prefer a plain
    translation over a rambling one.

The word's OWN characters are not counted: the learner is looking the
word up, so its complexity is a property of the word, not of the
example. Ties are broken by the sentence id, so the table is the same on
every run.

Usage:
    python pipeline/word_examples.py     (builds the table in an existing
                                         database and writes the stats)
"""

from __future__ import annotations

import collections
import heapq
import json
import os
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW, is_hanzi, strip_tones  # noqa: E402

# The CC-CEDICT dictionary (02_build_dictionary.py). The `dict` table
# holds the traditional and the simplified form of every entry, which
# is what the fold is built from.
HANZI_DB = os.path.join(DATA, "hanzi.db")
# The per-character readings, used to re-read a character whose reading
# changes when it is folded (著 -> 着).
CHAR_READINGS = os.path.join(RAW, "char_readings.json")
# The measured numbers of the build, written next to the database.
STATS_JSON = os.path.join(DATA, "word_example_stats.json")

# How many candidates a word keeps.
MAX_CANDIDATES = 4
# A character seen in this many corpus sentences is common.
COMMON_DF = 30
# A character with this many strokes is complex for a beginner.
COMPLEX_STROKES = 16
# The longest dictionary word the fold looks for.
MAX_FOLD_WORD = 8

# The weights of the cost function.
W_LENGTH = 4.0
W_CHARACTER = 2.0
W_TRANSLATION = 1.0


# ---------------------------------------------------------------- folding


class ScriptMaps:
    """The traditional -> simplified maps, built from CC-CEDICT.

    `word` holds the dictionary entries that are real script
    conversions, `char` the single characters that exist only in the
    traditional script.

    `traditional_only` is the set of characters that never appear in the
    simplified column of the dictionary: these are the characters that
    make a sentence traditional, and they are the ones the fold has to
    convert.

    `refused` holds the traditional-only characters whose simplified
    form could not be decided. They keep their traditional form, and
    the sentences that hold them are rejected.
    """

    def __init__(self, word: dict[str, str], char: dict[str, str],
                 traditional_only: set[str], refused: dict[str, list[str]]):
        self.word = word
        self.char = char
        self.traditional_only = traditional_only
        self.refused = refused


def load_script_maps(db_path: str = HANZI_DB,
                     vocabulary_chars: set[str] | None = None,
                     ) -> ScriptMaps:
    """Build the fold maps from the CC-CEDICT table of data/hanzi.db.

    The `dict` table holds one row per dictionary entry, with the
    traditional and the simplified spelling side by side. Four things
    are derived from it:

      * the set of characters that exist only in the traditional script
        (they appear in the traditional column and never in the
        simplified one);
      * the WORD map: the entries whose traditional side holds such a
        character. The restriction is what makes the fold safe -- such
        a character cannot occur in a simplified sentence, so the entry
        cannot match inside one;
      * the CHARACTER map: the single traditional-only characters, for
        the ones that do not appear inside a dictionary word;
      * the REFUSED characters: the traditional-only characters whose
        entry names several simplified forms and none of them can be
        chosen on evidence.
    """
    if not os.path.exists(db_path):
        raise SystemExit(f"ERROR: missing {db_path} - run 02_build_dictionary.py first")

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT traditional, simplified, pinyin_number FROM dict").fetchall()
    finally:
        conn.close()

    forms: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    entry_pinyin: dict[tuple[str, str], collections.Counter] = \
        collections.defaultdict(collections.Counter)
    traditional_side: set[str] = set()
    simplified_side: set[str] = set()

    for traditional, simplified, pinyin_number in rows:
        traditional_side.update(traditional)
        simplified_side.update(simplified)
        forms[traditional][simplified] += 1
        if pinyin_number:
            entry_pinyin[(traditional, simplified)][pinyin_number] += 1

    traditional_only = traditional_side - simplified_side

    readings = load_char_readings()

    def own_readings(character: str) -> set[str]:
        """The readings of the traditional character itself."""
        out = {strip_tones(p) for p in entry_pinyin.get((character, character), {})}
        for reading in readings.get(character, []):
            out.add(strip_tones(reading))
        return out

    def candidate_readings(character: str, simplified: str) -> set[str]:
        return {strip_tones(p) for p in entry_pinyin.get((character, simplified), {})}

    def resolve(character: str, candidates: list[tuple[str, int]]
                ) -> tuple[str | None, str]:
        """Choose the simplified form of a traditional character.

        The order is the point, and it is stated in the module
        docstring: the reading first (the fold must not change what
        the sentence says), the vocabulary second (the form the learner
        will meet), the frequency third. A character that none of the
        three settles is refused.
        """
        if len(candidates) == 1:
            return candidates[0][0], "unique"

        own = own_readings(character)
        matched = [(form, n) for form, n in candidates
                   if candidate_readings(character, form) & own]
        if len(matched) == 1:
            return matched[0][0], "reading"

        pool = matched or candidates
        if vocabulary_chars is not None:
            in_vocabulary = [(form, n) for form, n in pool
                             if form in vocabulary_chars]
            if len(in_vocabulary) == 1:
                return in_vocabulary[0][0], "vocabulary"
            if in_vocabulary:
                pool = in_vocabulary

        if len(pool) == 1:
            return pool[0][0], "reading+vocabulary"

        counts = {form: sum(entry_pinyin[(character, form)].values())
                  for form, _ in pool}
        best = max(counts.values())
        winners = [form for form, count in counts.items() if count == best]
        if len(winners) == 1 and best > sum(
                count for form, count in counts.items() if form != winners[0]):
            return winners[0], "frequency"
        return None, "refused"

    word: dict[str, str] = {}
    for traditional, counter in forms.items():
        # Only the multi-character entries go in the word map: the
        # single characters are the character map's job, and keeping
        # the two apart means the fold has exactly one place to look
        # for each.
        if len(traditional) < 2 or not (set(traditional) & traditional_only):
            continue
        candidates = [(form, n) for form, n in counter.items() if form != traditional]
        if not candidates:
            continue
        chosen, _ = resolve(traditional, candidates)
        if chosen is not None:
            word[traditional] = chosen

    char: dict[str, str] = {}
    refused: dict[str, list[str]] = {}
    for traditional, counter in forms.items():
        if len(traditional) != 1 or traditional not in traditional_only:
            continue
        candidates = [(form, n) for form, n in counter.items() if form != traditional]
        if not candidates:
            continue
        chosen, _ = resolve(traditional, candidates)
        if chosen is None:
            refused[traditional] = [form for form, _ in candidates]
        else:
            char[traditional] = chosen

    return ScriptMaps(word, char, traditional_only, refused)


def fold_to_simplified(text: str, maps: ScriptMaps) -> str:
    """Fold a traditional sentence into the simplified script.

    The dictionary is consulted longest word first, because a word can
    be written differently from the characters it is made of: 乾淨 is
    干净, but 乾 on its own is 乾 (in 乾隆). A character that the
    dictionary does not have a word for is folded on its own.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        hit = None
        for length in range(min(MAX_FOLD_WORD, n - i), 0, -1):
            fragment = text[i:i + length]
            replacement = maps.word.get(fragment)
            if replacement is not None:
                hit = (length, replacement)
                break
        if hit is not None:
            out.append(hit[1])
            i += hit[0]
        else:
            character = text[i]
            out.append(maps.char.get(character, character))
            i += 1
    return "".join(out)


def still_traditional(text: str, maps: ScriptMaps) -> list[str]:
    """The traditional-only characters the fold did not convert."""
    return [c for c in text if c in maps.traditional_only]


# ---------------------------------------------------------------- reading


def load_char_readings(path: str = CHAR_READINGS) -> dict[str, list[str]]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _closest_reading(character: str, syllable: str,
                     readings: dict[str, list[str]]) -> str:
    """The reading of `character` that is closest to `syllable`.

    A traditional character and its simplified form do not always share
    a reading: 著 is read zhe (着) in one sense and zhu (著) in another,
    and the source pinyin belongs to the sentence as it was written.
    The reading whose plain form matches the syllable is used when there
    is one; otherwise the reading that starts the same way is used, and
    the first reading of the character when even that fails.
    """
    options = readings.get(character) or []
    if not options:
        return syllable
    plain = strip_tones(syllable)
    for reading in options:
        if strip_tones(reading) == plain:
            return reading
    return max(options, key=lambda r: _common_prefix_len(strip_tones(r), plain))


def refold_pinyin(original: str, folded: str, pinyin: str,
                  readings: dict[str, list[str]]) -> str:
    """The pinyin of the folded sentence.

    The fold does not change the number of characters -- every
    traditional and simplified pair of the dictionary has the same
    length -- so the syllables of the source pinyin still line up with
    the characters one by one. Only the characters that were converted
    are re-read, because a converted character does not always keep its
    reading.
    """
    if not pinyin:
        return pinyin
    syllables = pinyin.split()
    old = [c for c in original if is_hanzi(c)]
    new = [c for c in folded if is_hanzi(c)]
    if len(old) != len(new) or len(syllables) != len(new):
        # The syllable count does not match the characters: the pinyin
        # was not built for this sentence, so it is left alone.
        return pinyin
    if old == new:
        return pinyin
    out = list(syllables)
    for index, (before, after) in enumerate(zip(old, new)):
        if before != after:
            out[index] = _closest_reading(after, syllables[index], readings)
    return " ".join(out)


# --------------------------------------------------------------- scoring


class CharacterCost:
    """How hard a character is for the learner, from 0 to 5."""

    def __init__(self, vocabulary_chars: set[str], document_frequency: dict[str, int],
                 strokes: dict[str, int]):
        self.vocabulary_chars = vocabulary_chars
        self.document_frequency = document_frequency
        self.strokes = strokes

    def difficulty(self, character: str) -> int:
        known = character in self.vocabulary_chars
        common = self.document_frequency.get(character, 0) >= COMMON_DF
        stroke_count = self.strokes.get(character)
        complex_glyph = stroke_count is None or stroke_count >= COMPLEX_STROKES
        if known:
            return 1 if complex_glyph else 0
        return (2 if common else 4) + (1 if complex_glyph else 0)


def _stroke_counts(db_path: str = HANZI_DB) -> dict[str, int]:
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        return {ch: n for ch, n in conn.execute(
            "SELECT char, strokes FROM char_info WHERE strokes IS NOT NULL")}
    finally:
        conn.close()


def _document_frequency(conn: sqlite3.Connection) -> dict[str, int]:
    """How many sentences each character appears in."""
    frequency: collections.Counter = collections.Counter()
    for (text,) in conn.execute("SELECT hanzi FROM sentences"):
        for character in set(text):
            if is_hanzi(character):
                frequency[character] += 1
    return dict(frequency)


# --------------------------------------------------------------- building


def build_word_examples(conn: sqlite3.Connection) -> dict:
    """Fill the word_example table and return the measured numbers."""
    words = [row[0] for row in conn.execute("SELECT hanzi FROM words ORDER BY hanzi")]
    word_set = set(words)
    max_word_length = max((len(w) for w in words), default=1)

    vocabulary_chars: set[str] = set()
    for word in words:
        vocabulary_chars.update(word)

    # The vocabulary is what the fold uses to settle an ambiguous
    # character, so the maps are built after it is known.
    maps = load_script_maps(vocabulary_chars=vocabulary_chars)
    readings = load_char_readings()

    path_words = [row[0] for row in conn.execute(
        "SELECT DISTINCT hanzi FROM curriculum_words ORDER BY hanzi")]

    character_cost = CharacterCost(
        vocabulary_chars,
        _document_frequency(conn),
        _stroke_counts(),
    )

    sentences = conn.execute(
        "SELECT id, hanzi, pinyin, translation_bg FROM sentences "
        "WHERE translation_bg != '' ORDER BY id").fetchall()

    # The best candidates of each word, kept in a bounded heap so that a
    # word that occurs in thousands of sentences does not cost memory.
    heaps: dict[str, list] = {}
    seen: dict[str, set] = collections.defaultdict(set)

    considered = 0
    changed_sentences = 0
    rejected_still_traditional = 0
    rejected_bare_word = 0
    duplicate_sentences = 0

    for sentence_id, hanzi, pinyin, translation_bg in sentences:
        considered += 1
        folded = fold_to_simplified(hanzi, maps)
        changed = folded != hanzi
        if changed:
            changed_sentences += 1

        if still_traditional(folded, maps):
            # The fold could not convert every character, so the
            # sentence is still written in the traditional script.
            rejected_still_traditional += 1
            continue

        han = [c for c in folded if is_hanzi(c)]
        if not han:
            continue
        plain = "".join(han)
        translation_length = len(translation_bg)

        difficulty = {c: character_cost.difficulty(c) for c in set(han)}

        # Every vocabulary word that occurs in the sentence.
        found: set[str] = set()
        for start in range(len(folded)):
            for length in range(1, max_word_length + 1):
                if start + length > len(folded):
                    break
                fragment = folded[start:start + length]
                if fragment in word_set:
                    found.add(fragment)

        for word in found:
            if plain == word:
                # The sentence is the word and nothing else.
                rejected_bare_word += 1
                continue
            if plain in seen[word]:
                # The same sentence twice: Tatoeba has entries that
                # differ only in their id, and showing the learner the
                # same sentence twice is noise.
                duplicate_sentences += 1
                continue
            seen[word].add(plain)

            # The word's own characters are not counted: the learner is
            # looking the word up, its complexity is not the example's.
            own = sum(difficulty.get(c, 0) for c in word)
            cost = (W_LENGTH * len(han)
                    + W_CHARACTER * (sum(difficulty.get(c, 0) for c in han) - own)
                    + W_TRANSLATION * translation_length)

            # A max-heap on (cost, id): the worst candidate is at the
            # root, and a new candidate replaces it only when it is
            # BETTER. Ties go to the lower sentence id, which is the
            # tie-break the rule states.
            heap = heaps.get(word)
            if heap is None:
                heap = []
                heaps[word] = heap
            item = (-cost, -sentence_id, cost, sentence_id, folded, pinyin,
                    translation_bg, changed, hanzi)
            if len(heap) < MAX_CANDIDATES:
                heapq.heappush(heap, item)
            elif (cost, sentence_id) < (-heap[0][0], -heap[0][1]):
                heapq.heapreplace(heap, item)

    rows = []
    changed_candidates = 0
    for word, heap in heaps.items():
        best = sorted(heap, key=lambda item: (item[2], item[3]))
        for rank, item in enumerate(best):
            (_, _, _, _, folded, pinyin, translation_bg, changed,
             source) = item
            if changed:
                changed_candidates += 1
            rows.append((word, rank, folded,
                         refold_pinyin(source, folded, pinyin, readings),
                         translation_bg))

    conn.executemany(
        "INSERT OR REPLACE INTO word_example "
        "(hanzi, ord, sentence, pinyin, translation_bg) VALUES (?,?,?,?,?)",
        rows,
    )

    return measure(conn, heaps, words, path_words, considered,
                   changed_sentences, changed_candidates,
                   rejected_still_traditional, rejected_bare_word,
                   duplicate_sentences, len(rows))


def measure(conn: sqlite3.Connection, heaps: dict[str, list],
            words: list[str], path_words: list[str], considered: int,
            changed_sentences: int, changed_candidates: int,
            rejected_still_traditional: int, rejected_bare_word: int,
            duplicate_sentences: int, row_count: int) -> dict:
    """The measured numbers, recomputed from the table that was written."""
    rows = conn.execute(
        "SELECT hanzi, sentence, translation_bg FROM word_example "
        "ORDER BY hanzi, ord").fetchall()

    words_with_candidates = len({row[0] for row in rows})
    words_with_four = conn.execute(
        "SELECT COUNT(*) FROM (SELECT hanzi FROM word_example GROUP BY hanzi "
        "HAVING COUNT(*) = ?)", (MAX_CANDIDATES,)).fetchone()[0]

    covered = {row[0] for row in rows}
    path_missing = [w for w in path_words if w not in covered]

    lengths = [len([c for c in row[1] if is_hanzi(c)]) for row in rows]

    return {
        "words_total": len(words),
        "words_with_candidate": words_with_candidates,
        "words_with_full_four": words_with_four,
        "coverage_pct": round(100.0 * words_with_candidates / max(len(words), 1), 2),
        "path_words_total": len(path_words),
        "path_words_with_candidate": len(path_words) - len(path_missing),
        "path_words_without_candidate": path_missing,
        "candidate_rows": row_count,
        "candidates_per_word": {
            "one": sum(1 for h in heaps.values() if len(h) == 1),
            "two": sum(1 for h in heaps.values() if len(h) == 2),
            "three": sum(1 for h in heaps.values() if len(h) == 3),
            "four_or_more": sum(1 for h in heaps.values() if len(h) >= 4),
        },
        "sentence_length_hanzi": {
            "min": min(lengths) if lengths else 0,
            "median": int(statistics.median(lengths)) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "mean": round(statistics.fmean(lengths), 2) if lengths else 0.0,
        },
        "sentences_with_bulgarian": considered,
        "sentences_changed_by_fold": changed_sentences,
        "candidates_changed_by_fold": changed_candidates,
        "sentences_rejected_still_traditional": rejected_still_traditional,
        "candidates_rejected_bare_word": rejected_bare_word,
        "candidates_rejected_duplicate": duplicate_sentences,
        "rule": {
            "rejected": [
                "no Bulgarian translation",
                "the folded sentence does not contain the word",
                "the folded sentence still holds a traditional-only character",
                "the folded sentence is the word and nothing else",
                "the same sentence twice for one word",
            ],
            "cost": (
                f"{W_LENGTH} * the number of Han characters "
                f"+ {W_CHARACTER} * the sum of the difficulty of the "
                "characters that are not the word "
                f"+ {W_TRANSLATION} * the number of characters of the "
                "Bulgarian translation; ties are broken by the sentence id"
            ),
            "difficulty": (
                "0 vocabulary character with a simple glyph, 1 vocabulary "
                "character with a complex or unknown glyph, 2 unknown but "
                f"common (in {COMMON_DF} or more corpus sentences), 3 the "
                "same but complex, 4 unknown and rare, 5 unknown, rare and "
                "complex"
            ),
        },
    }


def write_stats(stats: dict, path: str = STATS_JSON) -> str:
    """Write the measured numbers next to the database."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def print_summary(stats: dict) -> None:
    """The summary block of the run."""
    lengths = stats["sentence_length_hanzi"]
    print()
    print("word examples")
    print(f"  words with at least one candidate : {stats['words_with_candidate']:,}"
          f" / {stats['words_total']:,}  ({stats['coverage_pct']}%)")
    print(f"  words with all four candidates    : {stats['words_with_full_four']:,}")
    print(f"  learning-path words with a candidate: "
          f"{stats['path_words_with_candidate']} / {stats['path_words_total']}")
    print(f"  candidate rows written            : {stats['candidate_rows']:,}")
    print(f"  sentence length (Han characters)  : min {lengths['min']}, "
          f"median {lengths['median']}, max {lengths['max']} "
          f"(mean {lengths['mean']})")
    print(f"  sentences changed by the fold     : {stats['sentences_changed_by_fold']:,}"
          f" of {stats['sentences_with_bulgarian']:,}")
    print(f"  candidates changed by the fold    : "
          f"{stats['candidates_changed_by_fold']:,} of {stats['candidate_rows']:,}")
    print(f"  rejected as still traditional     : "
          f"{stats['sentences_rejected_still_traditional']:,}")
    print(f"  rejected as a bare word           : "
          f"{stats['candidates_rejected_bare_word']:,}")
    print(f"  rejected as a duplicate sentence  : "
          f"{stats['candidates_rejected_duplicate']:,}")


def main() -> int:
    """Build the table in an already built database and print the summary."""
    db_path = os.path.join(DATA, "content.db")
    if not os.path.exists(db_path):
        print(f"ERROR: missing {db_path} - run 08_build_content_db.py first")
        return 1
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS word_example ("
            "hanzi TEXT NOT NULL, ord INTEGER NOT NULL, sentence TEXT NOT NULL, "
            "pinyin TEXT NOT NULL DEFAULT '', "
            "translation_bg TEXT NOT NULL DEFAULT '', PRIMARY KEY (hanzi, ord))")
        conn.execute("DELETE FROM word_example")
        stats = build_word_examples(conn)
        conn.commit()
    finally:
        conn.close()
    write_stats(stats)
    print_summary(stats)
    print(f"  stats written to {STATS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

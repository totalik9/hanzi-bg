"""Build the fixture content database for the instrumented tests.

Output:
    android/app/src/androidTest/assets/content/content.db

The instrumented tests run against a small database with a handful of
words, not the 19.7 MB one that ships in the APK: the tests assert on
what the screens show, and a fixture that holds 好, 你好 and 水 says
everything they need to.

The fixture is a real SQLite database with the same schema as
data/content.db, so the app code under test cannot tell the difference.

Usage:
    python pipeline/make_test_fixture.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from importlib import import_module  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, ROOT  # noqa: E402

OUT = os.path.join(
    ROOT, "android", "app", "src", "androidTest", "assets", "content",
    "content.db",
)

# The schema is the one the real database is built with, imported rather
# than copied.
#
# The fixture used to carry its own copy of the schema, and the two drifted
# apart: the app gained the column `gloss_bg_lc` (the lowercased Bulgarian
# gloss, which the dictionary search matches against) and the fixture did
# not. Every instrumented test then died with a SQLiteException instead of
# a failure, because the app code caught only IllegalStateException.
#
# A copy of a schema is a promise to keep it in step. Importing the real
# one makes the fixture follow the database by construction: a new column
# in 08_build_content_db.py is in the fixture on the next run.
SCHEMA = import_module("08_build_content_db").SCHEMA


# The words the tests use. They cover the five practice modes:
# a single-character word (writing), a two-character word (production),
# a word with an audio clip (listening), and a verb.
WORDS = [
    # hanzi, pinyin, tones, plain, pos, en, bg, level, is_verb, freq, audio
    ("好", "hǎo", "hao3", "hao", "adj.", "good", "добър", "1", 0, 10, ""),
    ("你好", "nǐ hǎo", "ni3 hao3", "ni hao", "int.", "hello", "здравей", "1", 0, 5, ""),
    ("水", "shuǐ", "shui3", "shui", "n.", "water", "вода", "1", 0, 20, ""),
    ("人", "rén", "ren2", "ren", "n.", "person", "човек", "1", 0, 15, ""),
    ("吃", "chī", "chi1", "chi", "v.", "to eat", "да яде", "1", 1, 30, ""),
    ("书", "shū", "shu1", "shu", "n.", "book", "книга", "2", 0, 25, ""),
]

GRAMMAR = [
    (
        "Standard negation with \"bu\"",
        "Стандартно отричане с \"бу\"",
        "A1",
        "Grammar",
        "Standard negation uses 不.",
        "Стандартното отричане използва 不.",
        "",
        json.dumps([
            {"zh": "我不喝咖啡", "pinyin": "Wǒ bù hē kāfēi", "en": "I don't drink coffee.",
             "bg": "Не пия кафе."},
            {"zh": "他不是老师", "pinyin": "Tā bù shì lǎoshī", "en": "He is not a teacher.",
             "bg": "Той не е учител."},
            {"zh": "我们不去公园", "pinyin": "Wǒmen bù qù gōngyuán", "en": "We don't go to the park.",
             "bg": "Не отиваме в парка."},
            {"zh": "她不看书", "pinyin": "Tā bù kàn shū", "en": "She doesn't read books.",
             "bg": "Тя не чете книги."},
        ], ensure_ascii=False),
    ),
]

SENTENCES = [
    (1, "我不喝水", "Wǒ bù hē shuǐ", "I don't drink water.", "Не пия вода.", None),
    (2, "你好吗", "Nǐ hǎo ma", "How are you?", "Как си?", None),
    (3, "他看书", "Tā kàn shū", "He reads books.", "Той чете книги.", None),
]

CHARACTERS = [
    # char, strokes, radical, definition, medians
    ("好", 6, "女", "good", "[]"),
    ("水", 4, "水", "water", "[]"),
    ("人", 2, "人", "person", "[]"),
]

MANIFEST = {
    "generated_at": "2026-01-01T00:00:00+0000",
    "word_count": str(len(WORDS)),
    "words_with_bg_gloss": str(len(WORDS)),
    "grammar_count": str(len(GRAMMAR)),
    "sentence_count": str(len(SENTENCES)),
    "sentences_with_bg": str(len(SENTENCES)),
    "lesson_count": "1",
    "character_count": str(len(CHARACTERS)),
    "hsk_levels": "1,2",
}

# The learning path of the fixture: one unit with two lessons. The
# second lesson is LOCKED at the start, because the first one has not
# been passed -- that is the state the Path screen has to show.
CURRICULUM_UNITS = [
    ("fixture", "Тестова тема", 1),
]

CURRICULUM_LESSONS = [
    ("fixture-1", "fixture", "Първи урок", "words", 1),
    ("fixture-2", "fixture", "Втори урок", "words", 2),
]

CURRICULUM_WORDS = [
    ("fixture-1", 0, "好"),
    ("fixture-1", 1, "你好"),
    ("fixture-1", 2, "水"),
    ("fixture-1", 3, "人"),
    ("fixture-1", 4, "吃"),
    ("fixture-2", 0, "书"),
]

# The example sentences of the words: one row per (word, candidate),
# the ord being the rank. The real database holds up to four per word;
# the fixture holds two, which is enough for a screen that shows the
# first example and a "more" button.
WORD_EXAMPLES = [
    # hanzi, ord, sentence, pinyin, translation_bg
    ("好", 0, "好吧。", "Hǎo ba.", "Добре."),
    ("好", 1, "我好胖哦。", "Wǒ hǎo pàng ó.", "Леле, че съм дебел."),
    ("你好", 0, "你好吗？", "Nǐ hǎo ma?", "Как си?"),
    ("你好", 1, "你好，我叫 Nancy。", "Nǐ hǎo, wǒ jiào Nancy.", "Здравейте, аз съм Нанси."),
    ("水", 0, "喝水。", "Hē shuǐ.", "Пий вода."),
    ("水", 1, "没有水。", "Méi yǒu shuǐ.", "Няма вода."),
    ("人", 0, "我是人。", "Wǒ shì rén.", "Аз съм човек."),
    ("人", 1, "人很多。", "Rén hěn duō.", "Хората са много."),
    ("吃", 0, "她吃。", "Tā chī.", "Тя яде."),
    ("吃", 1, "吃饭。", "Chī fàn.", "Яде."),
    ("书", 0, "我看这本书。", "Wǒ kàn zhè běn shū.", "Чета тази книга."),
    ("书", 1, "这是我的书。", "Zhè shì wǒ de shū.", "Това е моята книга."),
]


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)

    conn = sqlite3.connect(OUT)
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT INTO words (hanzi, pinyin, pinyin_tones, pinyin_plain, pos, "
        "gloss_en, gloss_bg, gloss_bg_lc, hsk_level, is_verb, freq, audio, "
        "gloss_source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        # Every fixture gloss was written by a person, so every row is
        # "human" -- and the search filter for human glosses only has to
        # find them. `gloss_bg_lc` is the lowercased copy the dictionary
        # search matches against; SQLite's own lower() folds ASCII only,
        # so it is folded here, in Python, like in the real database.
        [(w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[6].lower(), w[7], w[8],
          w[9], w[10], "human") for w in WORDS],
    )

    conn.executemany(
        "INSERT INTO grammar (title, title_bg, level, category, summary, "
        "summary_bg, body, examples) VALUES (?,?,?,?,?,?,?,?)",
        GRAMMAR,
    )

    conn.executemany(
        "INSERT INTO lessons (title, title_bg, level, ord) VALUES (?,?,?,?)",
        [("HSK 1", "Ниво 1", "1", 1), ("HSK 2", "Ниво 2", "2", 2)],
    )

    conn.executemany(
        "INSERT INTO sentences (id, hanzi, pinyin, translation_en, "
        "translation_bg, audio_path) VALUES (?,?,?,?,?,?)",
        SENTENCES,
    )

    conn.executemany(
        "INSERT INTO characters (char, strokes, radical, definition, medians) "
        "VALUES (?,?,?,?,?)",
        CHARACTERS,
    )

    conn.executemany(
        "INSERT INTO manifest (key, value) VALUES (?,?)",
        list(MANIFEST.items()),
    )

    conn.executemany(
        "INSERT INTO curriculum_units (key, title, ord) VALUES (?,?,?)",
        CURRICULUM_UNITS,
    )

    conn.executemany(
        "INSERT INTO curriculum_lessons (key, unit_key, title, kind, ord) "
        "VALUES (?,?,?,?,?)",
        CURRICULUM_LESSONS,
    )

    conn.executemany(
        "INSERT INTO curriculum_words (lesson_key, ord, hanzi) VALUES (?,?,?)",
        CURRICULUM_WORDS,
    )

    conn.executemany(
        "INSERT INTO word_example (hanzi, ord, sentence, pinyin, "
        "translation_bg) VALUES (?,?,?,?,?)",
        WORD_EXAMPLES,
    )

    # The IME index: one row per syllable of every word.
    ime_rows = []
    for w in WORDS:
        for syllable in w[2].split():
            ime_rows.append((syllable.rstrip("12345"), w[0], w[9]))
    conn.executemany(
        "INSERT OR REPLACE INTO ime (syllable, hanzi, freq) VALUES (?,?,?)",
        ime_rows,
    )

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    size = os.path.getsize(OUT)
    print(f"SUMMARY make_test_fixture: words={len(WORDS)} grammar={len(GRAMMAR)} "
          f"sentences={len(SENTENCES)} characters={len(CHARACTERS)} "
          f"bytes={size:,} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, ROOT  # noqa: E402

OUT = os.path.join(
    ROOT, "android", "app", "src", "androidTest", "assets", "content",
    "content.db",
)

SCHEMA = """
CREATE TABLE words (
    hanzi       TEXT PRIMARY KEY,
    pinyin      TEXT NOT NULL DEFAULT '',
    pinyin_tones TEXT NOT NULL DEFAULT '',
    pinyin_plain TEXT NOT NULL DEFAULT '',
    pos         TEXT NOT NULL DEFAULT '',
    gloss_en    TEXT NOT NULL DEFAULT '',
    gloss_bg    TEXT NOT NULL DEFAULT '',
    hsk_level   TEXT NOT NULL DEFAULT '',
    is_verb     INTEGER NOT NULL DEFAULT 0,
    freq        INTEGER,
    audio       TEXT,
    gloss_source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE grammar (
    id       INTEGER PRIMARY KEY,
    title    TEXT NOT NULL,
    title_bg TEXT NOT NULL DEFAULT '',
    level    TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    summary  TEXT NOT NULL DEFAULT '',
    summary_bg TEXT NOT NULL DEFAULT '',
    body     TEXT NOT NULL DEFAULT '',
    examples TEXT NOT NULL DEFAULT ''
);

CREATE TABLE lessons (
    id       INTEGER PRIMARY KEY,
    title    TEXT NOT NULL,
    title_bg TEXT NOT NULL DEFAULT '',
    level    TEXT NOT NULL DEFAULT '',
    ord      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sentences (
    id             INTEGER PRIMARY KEY,
    hanzi          TEXT NOT NULL,
    pinyin         TEXT NOT NULL DEFAULT '',
    translation_en TEXT NOT NULL DEFAULT '',
    translation_bg TEXT NOT NULL DEFAULT '',
    audio_path     TEXT
);

CREATE TABLE manifest (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE characters (
    char       TEXT PRIMARY KEY,
    strokes    INTEGER NOT NULL DEFAULT 0,
    radical    TEXT NOT NULL DEFAULT '',
    definition TEXT NOT NULL DEFAULT '',
    medians    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE ime (
    syllable TEXT NOT NULL,
    hanzi    TEXT NOT NULL,
    freq     INTEGER,
    PRIMARY KEY (syllable, hanzi)
);

CREATE INDEX idx_words_level ON words(hsk_level);
CREATE INDEX idx_grammar_level ON grammar(level);
CREATE INDEX idx_lessons_level ON lessons(level);
CREATE INDEX idx_ime_syllable ON ime(syllable);
"""

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


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)

    conn = sqlite3.connect(OUT)
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT INTO words (hanzi, pinyin, pinyin_tones, pinyin_plain, pos, "
        "gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[7], w[8], w[9], w[10],
          "human" if w[10] == "" else "human") for w in WORDS],
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

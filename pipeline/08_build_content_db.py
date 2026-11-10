"""Build the read-only content database (data/content.db).

Inputs:
    data/vocab_hsk.json      graded HSK vocabulary   (03_build_vocab.py)
    data/grammar.json        grammar points          (04_build_grammar.py)
    data/sentences.json      Tatoeba sentences       (05_build_sentences.py)
    data/audio/manifest.json text -> audio file map  (06_build_audio.py)
    data/raw/bg_zh_wiktionary.json  human Bulgarian glosses

Output:
    data/content.db

Schema (read by android/.../ContentRepository.kt):

    words(hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg,
          hsk_level, is_verb, freq, audio, gloss_source)
    grammar(id, title, title_bg, level, category, summary, body, examples)
    lessons(id, title, title_bg, level, ord)
    sentences(id, hanzi, pinyin, translation_en, translation_bg, audio_path)
    manifest(key, value)

The database ships inside the APK as an asset and is never mutated at
runtime, so it carries no indexes beyond the ones the app actually uses
and no foreign keys.

Usage:
    python pipeline/08_build_content_db.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW, is_hanzi, strip_tones  # noqa: E402

VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
GRAMMAR_JSON = os.path.join(DATA, "grammar.json")
SENTENCES_JSON = os.path.join(DATA, "sentences.json")
AUDIO_MANIFEST = os.path.join(DATA, "audio", "manifest.json")
BG_GLOSS = os.path.join(RAW, "bg_zh_wiktionary.json")
# The NLLB-200 output (07_translate_bulgarian.py): human glosses first,
# machine glosses for the rest.
BG_TRANSLATIONS = os.path.join(DATA, "bg_translations.json")
RAW_MANIFEST = os.path.join(RAW, "manifest.json")

OUT = os.path.join(DATA, "content.db")

SCHEMA = """
CREATE TABLE words (
    hanzi       TEXT PRIMARY KEY,
    pinyin      TEXT NOT NULL DEFAULT '',
    pinyin_tones TEXT NOT NULL DEFAULT '',
    -- the same pinyin without the tone marks ("hao"), which is what the
    -- IME matches against: the learner types letters, not tones.
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
    -- the stroke centre-lines, as JSON: [[x,y], ...] per stroke.
    -- These are what a stroke-order animation draws.
    medians    TEXT NOT NULL DEFAULT ''
);

-- One row per (word, syllable): the index a pinyin IME searches.
-- A word contributes one row for each of its syllables, so typing
-- "nihao" finds "nihao" (ni+hao) and "nihaoyou" (ni+hao+you).
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


def load_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"  WARNING: cannot read {path}: {exc}")
        return None


def audio_index() -> dict[str, str]:
    """Map a spoken text to its audio file name.

    06_build_audio.py names the files content-addressed, so the mapping
    text -> file name has to be read back from its manifest.
    """
    data = load_json(AUDIO_MANIFEST)
    if not data:
        return {}
    # the manifest is {file name: text}; the database stores the file name
    return {text: name for name, text in data.items() if text}


def build_words(conn: sqlite3.Connection, audio: dict[str, str]) -> tuple[int, int]:
    data = load_json(VOCAB_JSON)
    if not data:
        print(f"ERROR: missing {VOCAB_JSON} - run 03_build_vocab.py first")
        return 0, 0

    words = data["words"] if isinstance(data, dict) else data

    # Human Bulgarian glosses, used when the vocabulary file has none.
    human_bg: dict[str, list[str]] = {}
    bg_data = load_json(BG_GLOSS)
    if bg_data:
        for word, glosses in bg_data.items():
            if isinstance(glosses, list) and glosses:
                human_bg[word] = glosses

    # The NLLB-200 output carries the human glosses and the machine ones,
    # each tagged with its origin. It is the richer source, so it wins
    # over the raw Wiktionary file when it exists.
    machine_bg: dict[str, str] = {}
    translations = load_json(BG_TRANSLATIONS)
    if translations:
        for word, entry in translations.items():
            if isinstance(entry, dict) and entry.get("gloss"):
                if entry.get("source") == "human":
                    human_bg[word] = [entry["gloss"]]
                else:
                    machine_bg[word] = entry["gloss"]
    print(f"  human glosses: {len(human_bg):,}  machine glosses: {len(machine_bg):,}")

    rows = []
    with_bg = 0
    with_machine = 0
    for w in words:
        hanzi = w.get("hanzi")
        if not hanzi:
            continue

        gloss_bg = (w.get("gloss_bg") or "").strip()
        if gloss_bg:
            source = "human"
        else:
            glosses = human_bg.get(hanzi)
            if glosses:
                gloss_bg = glosses[0]
                source = "human"
            elif hanzi in machine_bg:
                gloss_bg = machine_bg[hanzi]
                source = "machine"
            else:
                source = ""
        if gloss_bg:
            with_bg += 1
        if source == "machine":
            with_machine += 1

        # The audio manifest is keyed by the sanitised spoken text.
        audio_file = audio.get(hanzi)

        rows.append((
            hanzi,
            w.get("pinyin") or "",
            w.get("pinyin_number") or "",
            strip_tones(w.get("pinyin") or ""),
            w.get("pos") or "",
            w.get("gloss_en") or "",
            gloss_bg,
            str(w.get("hsk_level") or ""),
            1 if w.get("is_verb") else 0,
            w.get("freq"),
            audio_file,
            source,
        ))

    conn.executemany(
        "INSERT OR REPLACE INTO words "
        "(hanzi, pinyin, pinyin_tones, pinyin_plain, pos, gloss_en, gloss_bg, "
        " hsk_level, is_verb, freq, audio, gloss_source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows), with_bg, with_machine


def build_grammar(conn: sqlite3.Connection) -> int:
    data = load_json(GRAMMAR_JSON)
    if not data:
        print(f"  WARNING: missing {GRAMMAR_JSON} - the grammar screen will be empty")
        return 0

    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        print("  WARNING: grammar.json has no entry list")
        return 0

    rows = []
    for e in entries:
        slug = e.get("slug") or ""
        title = e.get("title") or slug
        # The wiki text is the reference; the summary is the one-line version.
        body = e.get("wiki_text") or ""
        summary = e.get("summary") or ""
        examples = e.get("examples") or []
        rows.append((
            title,
            e.get("title_bg") or "",
            e.get("level") or "",
            e.get("category") or "",
            summary,
            body,
            json.dumps(examples, ensure_ascii=False),
        ))

    conn.executemany(
        "INSERT INTO grammar (title, title_bg, level, category, summary, body, examples) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def build_lessons(conn: sqlite3.Connection, n_words: int) -> int:
    """One lesson per HSK level, in the order the learner meets them."""
    levels = [r[0] for r in conn.execute(
        "SELECT DISTINCT hsk_level FROM words WHERE hsk_level != '' ORDER BY hsk_level"
    )]
    rows = []
    for i, level in enumerate(levels, 1):
        count = conn.execute(
            "SELECT COUNT(*) FROM words WHERE hsk_level = ?", (level,)
        ).fetchone()[0]
        rows.append((
            f"HSK {level}",
            f"Ниво {level}",
            level,
            i,
        ))
        print(f"    level {level}: {count} words")
    conn.executemany(
        "INSERT INTO lessons (title, title_bg, level, ord) VALUES (?,?,?,?)",
        rows,
    )
    return len(rows)


def build_sentences(conn: sqlite3.Connection, audio: dict[str, str]) -> int:
    data = load_json(SENTENCES_JSON)
    if not data:
        print(f"  WARNING: missing {SENTENCES_JSON} - no sentences in the app")
        return 0

    entries = data.get("sentences") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        print("  WARNING: sentences.json has no entry list")
        return 0

    rows = []
    for e in entries:
        hanzi = e.get("zh") or ""
        if not hanzi:
            continue
        en = e.get("translations_en") or []
        bg = e.get("translations_bg") or []
        rows.append((
            e.get("id"),
            hanzi,
            e.get("pinyin") or "",
            en[0] if en else "",
            bg[0] if bg else "",
            audio.get(hanzi),
        ))

    conn.executemany(
        "INSERT OR REPLACE INTO sentences "
        "(id, hanzi, pinyin, translation_en, translation_bg, audio_path) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def build_characters(conn: sqlite3.Connection) -> int:
    """Load the stroke-order data for the characters the app teaches.

    Only the characters that appear in the vocabulary are loaded: the full
    graphics file holds 9 574 characters, most of which the learner will
    never meet, and every one of them costs database space.
    """
    graphics_path = os.path.join(RAW, "mmah_graphics.txt")
    dict_path = os.path.join(RAW, "mmah_dictionary.txt")
    if not os.path.exists(graphics_path):
        print("  WARNING: missing mmah_graphics.txt - no stroke order")
        return 0

    # The characters the learner actually meets.
    wanted = {
        ch
        for (word,) in conn.execute("SELECT hanzi FROM words")
        for ch in word
        if is_hanzi(ch)
    }
    print(f"  characters in the vocabulary: {len(wanted):,}")

    info: dict[str, dict] = {}
    if os.path.exists(dict_path):
        with open(dict_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                char = d.get("character")
                if char in wanted:
                    info[char] = d

    rows = []
    with open(graphics_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            char = d.get("character")
            if char not in wanted:
                continue
            meta = info.get(char, {})
            medians = d.get("medians") or []
            rows.append((
                char,
                len(medians),
                meta.get("radical") or "",
                meta.get("definition") or "",
                json.dumps(medians, separators=(",", ":")),
            ))

    conn.executemany(
        "INSERT OR REPLACE INTO characters (char, strokes, radical, definition, medians) "
        "VALUES (?,?,?,?,?)",
        rows,
    )
    return len(rows)


def build_ime(conn: sqlite3.Connection) -> int:
    """Build the syllable index a pinyin IME searches.

    One row per (syllable, word). A word with several syllables contributes
    a row for each, so a search for "hao" finds "你好" as well as "好".

    The syllable is stored in NUMERIC form without the tone ("hao3" ->
    "hao"), because the learner types letters, not tones.
    """
    rows = []
    for hanzi, pinyin_number, freq in conn.execute(
        "SELECT hanzi, pinyin_tones, freq FROM words WHERE pinyin_tones != ''"
    ):
        for syllable in (pinyin_number or "").split():
            # strip the tone digit: the learner types letters only
            plain = syllable.rstrip("12345").lower()
            if plain:
                rows.append((plain, hanzi, freq))

    conn.executemany(
        "INSERT OR REPLACE INTO ime (syllable, hanzi, freq) VALUES (?,?,?)",
        rows,
    )
    return len(rows)


def build_manifest(conn: sqlite3.Connection) -> dict[str, str]:
    """Provenance and counts, so the app can show what it is carrying."""
    raw_manifest = load_json(RAW_MANIFEST) or {}
    licenses: dict[str, str] = {}
    if isinstance(raw_manifest, dict):
        for name, entry in raw_manifest.items():
            if isinstance(entry, dict) and entry.get("license"):
                licenses[name] = entry["license"]

    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    values = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "word_count": str(count("SELECT COUNT(*) FROM words")),
        "words_with_bg_gloss": str(count(
            "SELECT COUNT(*) FROM words WHERE gloss_bg != ''")),
        "words_with_machine_gloss": str(count(
            "SELECT COUNT(*) FROM words WHERE gloss_source = 'machine'")),
        "grammar_count": str(count("SELECT COUNT(*) FROM grammar")),
        "sentence_count": str(count("SELECT COUNT(*) FROM sentences")),
        "sentences_with_bg": str(count(
            "SELECT COUNT(*) FROM sentences WHERE translation_bg != ''")),
        "lesson_count": str(count("SELECT COUNT(*) FROM lessons")),
        "character_count": str(count("SELECT COUNT(*) FROM characters")),
        "hsk_levels": ",".join(
            r[0] for r in conn.execute(
                "SELECT DISTINCT hsk_level FROM words WHERE hsk_level != '' "
                "ORDER BY hsk_level")),
        # The simulation reads these two keys to report where the content
        # came from.
        "hsk_tagging_confidence": "official",
        "gloss_source": (
            "Chinese Wiktionary (human) + NLLB-200 (machine); "
            "the words.gloss_source column says which is which"
        ),
        "source_licenses": json.dumps(licenses, ensure_ascii=False),
        "gloss_note": (
            "Bulgarian glosses come from Chinese Wiktionary (human) or from "
            "NLLB-200 (machine). The gloss_source column records which."
        ),
    }
    conn.executemany(
        "INSERT OR REPLACE INTO manifest (key, value) VALUES (?,?)",
        list(values.items()),
    )
    return values


def main() -> int:
    if os.path.exists(OUT):
        os.remove(OUT)

    os.makedirs(DATA, exist_ok=True)
    conn = sqlite3.connect(OUT)
    conn.executescript(SCHEMA)

    audio = audio_index()
    print(f"audio files available: {len(audio)}")

    print("building words ...")
    n_words, n_bg, n_machine = build_words(conn, audio)
    print(f"  words: {n_words:,}  with a Bulgarian gloss: {n_bg:,} "
          f"(machine: {n_machine:,})")

    print("building grammar ...")
    n_grammar = build_grammar(conn)
    print(f"  grammar points: {n_grammar:,}")

    print("building lessons ...")
    n_lessons = build_lessons(conn, n_words)
    print(f"  lessons: {n_lessons}")

    print("building sentences ...")
    n_sentences = build_sentences(conn, audio)
    print(f"  sentences: {n_sentences:,}")

    print("building characters (stroke order) ...")
    n_chars = build_characters(conn)
    print(f"  characters with stroke order: {n_chars:,}")

    print("building the pinyin IME index ...")
    n_ime = build_ime(conn)
    print(f"  IME entries: {n_ime:,}")

    print("building manifest ...")
    values = build_manifest(conn)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    size = os.path.getsize(OUT)
    print()
    print(f"SUMMARY 08_build_content_db: words={n_words} grammar={n_grammar} "
          f"lessons={n_lessons} sentences={n_sentences} "
          f"bytes={size:,} -> {OUT}")
    for key in ("word_count", "words_with_bg_gloss", "grammar_count",
                "sentence_count", "sentences_with_bg"):
        print(f"   {key} = {values[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

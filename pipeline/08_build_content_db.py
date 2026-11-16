"""Build the read-only content database (data/content.db).

Inputs:
    data/vocab_hsk.json      graded HSK vocabulary   (03_build_vocab.py)
    data/grammar.json        grammar points          (04_build_grammar.py)
    data/sentences.json      Tatoeba sentences       (05_build_sentences.py)
    data/audio/manifest.json text -> audio file map  (06_build_audio.py)
    data/raw/bg_zh_wiktionary.json  human Bulgarian glosses
    curriculum/*.json        the hand-written learning path

Output:
    data/content.db

Schema (read by android/.../ContentRepository.kt):

    words(hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg,
          hsk_level, is_verb, freq, audio, gloss_source)
    grammar(id, title, title_bg, level, category, summary, body, examples)
    lessons(id, title, title_bg, level, ord)
    sentences(id, hanzi, pinyin, translation_en, translation_bg, audio_path)
    manifest(key, value)

The curriculum is NOT generated. It is hand-written, in curriculum/, and it
decides the order the learner meets the words: units -> lessons -> words.
It lives in the repository (not in data/, which is gitignored) because a
hand-written file that the build overwrites is a file that gets lost.

Two shapes are read from curriculum/:
  - {"units": [...]}  the learning path (00_intro.json, 10_hsk1.json, ...)
  - {hanzi: gloss}    a hand-written Bulgarian gloss patch
                       (20_glosses_hsk1.json) that OVERRIDES the machine
                       translation for the words of the learning path

The gloss patch exists because the machine translations are not fit to
teach: 个 was glossed "(основателна форма на индивидуалността)" and 的
carried a 200-character dump of every sense it has in a dictionary.

The database ships inside the APK as an asset and is never mutated at
runtime, so it carries no indexes beyond the ones the app actually uses
and no foreign keys.

Usage:
    python pipeline/08_build_content_db.py
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW, is_hanzi, sanitize_speech, strip_tones  # noqa: E402

VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
GRAMMAR_JSON = os.path.join(DATA, "grammar.json")
SENTENCES_JSON = os.path.join(DATA, "sentences.json")
AUDIO_MANIFEST = os.path.join(DATA, "audio", "manifest.json")
BG_GLOSS = os.path.join(RAW, "bg_zh_wiktionary.json")
# The NLLB-200 output (07_translate_bulgarian.py): human glosses first,
# machine glosses for the rest.
BG_TRANSLATIONS = os.path.join(DATA, "bg_translations.json")
RAW_MANIFEST = os.path.join(RAW, "manifest.json")
# The machine-readable list of sources and licences. It is tracked in
# the repository root (data/ is not versioned), so the app can show
# where the content came from and which licence covers what.
SOURCES_JSON = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "sources.json")

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
    -- the Bulgarian summary, from 11_translate_grammar.py. The app is
    -- for Bulgarian learners, so the English summary is the fallback
    -- and this is what is shown.
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

-- The learning path. It is hand-written, not derived: the order the
-- learner meets the words is a teaching decision, not a property of the
-- corpus. A unit holds lessons; a lesson holds words.
CREATE TABLE curriculum_units (
    key   TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ord   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE curriculum_lessons (
    key      TEXT PRIMARY KEY,
    unit_key TEXT NOT NULL,
    title    TEXT NOT NULL,
    -- "teach" lessons teach the sound system and carry cards instead of
    -- words; "words" lessons carry the vocabulary.
    kind     TEXT NOT NULL DEFAULT 'words',
    ord      INTEGER NOT NULL DEFAULT 0
);

-- One row per word in a lesson, in the order the learner meets it.
CREATE TABLE curriculum_words (
    lesson_key TEXT NOT NULL,
    ord        INTEGER NOT NULL,
    hanzi      TEXT NOT NULL,
    PRIMARY KEY (lesson_key, ord)
);

-- The teaching cards of a "teach" lesson, as JSON.
CREATE TABLE curriculum_cards (
    lesson_key TEXT NOT NULL,
    ord        INTEGER NOT NULL,
    payload    TEXT NOT NULL,
    PRIMARY KEY (lesson_key, ord)
);

CREATE INDEX idx_words_level ON words(hsk_level);
CREATE INDEX idx_grammar_level ON grammar(level);
CREATE INDEX idx_lessons_level ON lessons(level);
CREATE INDEX idx_ime_syllable ON ime(syllable);
CREATE INDEX idx_curriculum_words_hanzi ON curriculum_words(hanzi);
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


CURRICULUM_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "curriculum")


def load_curriculum() -> tuple[list[dict], dict[str, str]]:
    """Read the hand-written learning path.

    Two shapes live in curriculum/, distinguished by their content and not
    by their name:

      {"units": [...]}  the path itself
      {hanzi: gloss}    a Bulgarian gloss patch, which overrides the
                         machine translation for the words it names

    The files are read in name order, so 00_intro.json comes before
    10_hsk1.json. A file that is neither shape is an error, not a
    warning: a typo in a hand-written file must not silently empty the
    learning path.
    """
    units: list[dict] = []
    glosses: dict[str, str] = {}

    if not os.path.isdir(CURRICULUM_DIR):
        print(f"  WARNING: no curriculum directory at {CURRICULUM_DIR}")
        return units, glosses

    for name in sorted(os.listdir(CURRICULUM_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CURRICULUM_DIR, name)
        data = load_json(path)
        if data is None:
            raise SystemExit(f"ERROR: cannot read {path}")
        if isinstance(data, dict) and "units" in data:
            units.extend(data["units"])
        elif isinstance(data, dict) and data and all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            glosses.update(data)
        else:
            raise SystemExit(
                f"ERROR: {path} is neither a curriculum (an object with "
                f"'units') nor a gloss patch (an object of hanzi -> gloss)"
            )

    return units, glosses


def audio_index() -> dict[str, str]:
    """Map a spoken text to its audio file name.

    06_build_audio.py names the files content-addressed, so the mapping
    text -> file name has to be read back from its manifest.

    The manifest holds the SANITISED text -- the characters the voice
    actually speaks -- while a sentence in the corpus keeps its
    punctuation ("關燈。"). The lookup therefore has to sanitise the
    sentence too, or the clip is never found: without this, 0 of the 396
    sentences with a Bulgarian translation were linked to their audio and
    399 clips (5.8 MB) sat in the APK unreferenced.
    """
    data = load_json(AUDIO_MANIFEST)
    if not data:
        return {}
    # the manifest is {file name: text}; the database stores the file name
    return {text: name for name, text in data.items() if text}


def build_words(
    conn: sqlite3.Connection,
    audio: dict[str, str],
    hand_glosses: dict[str, str],
) -> tuple[int, int, int]:
    data = load_json(VOCAB_JSON)
    if not data:
        print(f"ERROR: missing {VOCAB_JSON} - run 03_build_vocab.py first")
        return 0, 0, 0

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
    #
    # "human+machine" means the human gloss came first and the machine
    # senses that it does not already cover followed it.
    machine_bg: dict[str, str] = {}
    human_bg_combined: dict[str, str] = {}
    translations = load_json(BG_TRANSLATIONS)
    if translations:
        for word, entry in translations.items():
            if isinstance(entry, dict) and entry.get("gloss"):
                if entry.get("source") == "human":
                    human_bg[word] = [entry["gloss"]]
                elif entry.get("source") == "human+machine":
                    human_bg_combined[word] = entry["gloss"]
                else:
                    machine_bg[word] = entry["gloss"]
    print(f"  human glosses: {len(human_bg):,}  machine glosses: {len(machine_bg):,}  "
          f"combined: {len(human_bg_combined):,}")

    rows = []
    with_bg = 0
    with_machine = 0
    for w in words:
        hanzi = w.get("hanzi")
        if not hanzi:
            continue

        # The combined gloss comes first: it already carries the human
        # gloss and the machine senses that it does not cover.
        # The hand-written gloss wins over everything. It was written
        # for a beginner, and the machine translation is not fit to
        # teach: 个 was glossed "(основателна форма на индивидуалността)"
        # and 的 carried a 200-character dump of every dictionary sense.
        # The provenance is "human", so the app's own note about the
        # machine translation does not appear next to it.
        if hanzi in hand_glosses:
            gloss_bg = hand_glosses[hanzi]
            source = "human"
        elif hanzi in human_bg_combined:
            gloss_bg = human_bg_combined[hanzi]
            source = "human+machine"
        else:
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
        audio_file = audio.get(sanitize_speech(hanzi))

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


def build_curriculum(conn: sqlite3.Connection, units: list[dict]) -> tuple[int, int, int]:
    """Load the hand-written learning path.

    The order the learner meets the words in is a teaching decision, so
    it is written by hand and stored as it was written. Nothing here is
    derived from the corpus.

    A word named by a lesson must exist in the words table: a lesson
    that names a word the app cannot show is a broken lesson, and it is
    an error rather than a warning.
    """
    if not units:
        print("  WARNING: the curriculum is empty - no learning path")
        return 0, 0, 0

    unit_rows = []
    lesson_rows = []
    word_rows = []
    card_rows = []

    known = {h for (h,) in conn.execute("SELECT hanzi FROM words")}
    missing: list[str] = []

    unit_ord = 0
    lesson_ord = 0
    for unit in units:
        unit_key = unit.get("key") or ""
        if not unit_key:
            raise SystemExit("ERROR: a curriculum unit has no key")
        unit_rows.append((unit_key, unit.get("title") or unit_key, unit_ord))
        unit_ord += 1

        for lesson in unit.get("lessons") or []:
            lesson_key = lesson.get("key") or ""
            if not lesson_key:
                raise SystemExit(f"ERROR: a lesson in unit '{unit_key}' has no key")
            kind = lesson.get("kind") or "words"
            lesson_rows.append((
                lesson_key,
                unit_key,
                lesson.get("title") or lesson_key,
                kind,
                lesson_ord,
            ))
            lesson_ord += 1

            for i, hanzi in enumerate(lesson.get("words") or []):
                if hanzi not in known:
                    missing.append(f"{lesson_key}: {hanzi}")
                    continue
                word_rows.append((lesson_key, i, hanzi))

            for i, card in enumerate(lesson.get("cards") or []):
                card_rows.append((lesson_key, i, json.dumps(card, ensure_ascii=False)))

    if missing:
        raise SystemExit(
            "ERROR: the curriculum names words that are not in the "
            f"vocabulary ({len(missing)}): " + ", ".join(missing[:10])
        )

    conn.executemany(
        "INSERT OR REPLACE INTO curriculum_units (key, title, ord) VALUES (?,?,?)",
        unit_rows,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO curriculum_lessons (key, unit_key, title, kind, ord) "
        "VALUES (?,?,?,?,?)",
        lesson_rows,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO curriculum_words (lesson_key, ord, hanzi) VALUES (?,?,?)",
        word_rows,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO curriculum_cards (lesson_key, ord, payload) VALUES (?,?,?)",
        card_rows,
    )
    return len(unit_rows), len(lesson_rows), len(word_rows)


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
            e.get("summary_bg") or "",
            body,
            json.dumps(examples, ensure_ascii=False),
        ))

    conn.executemany(
        "INSERT INTO grammar (title, title_bg, level, category, summary, summary_bg, body, examples) "
        "VALUES (?,?,?,?,?,?,?,?)",
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
        # The audio manifest is keyed by the SANITISED text, so the
        # sentence has to be sanitised the same way before the lookup.
        # "關燈。" is spoken as "關燈", and only the second form is in the
        # manifest.
        rows.append((
            e.get("id"),
            hanzi,
            e.get("pinyin") or "",
            en[0] if en else "",
            bg[0] if bg else "",
            audio.get(sanitize_speech(hanzi)),
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
    "hao"), because the learner types letters only.

    The umlaut is stored FOLDED: "lü" becomes "lu". A phone keyboard
    cannot produce "ü", so a learner who types "lu" has to find 绿
    (lǜ). The stored pinyin of the word is folded the same way on the
    app side, so the two match. Without this, 76 words -- every one that
    carries the umlaut -- were unreachable from the production mode.

    The alternative, storing the umlaut as "v" (the other Chinese IME
    convention), is not used here: "v" is folded to "u" on the app side
    too, so both spellings find the word.
    """
    rows = []
    for hanzi, pinyin_number, freq in conn.execute(
        "SELECT hanzi, pinyin_tones, freq FROM words WHERE pinyin_tones != ''"
    ):
        for syllable in (pinyin_number or "").split():
            # strip the tone digit: the learner types letters only
            plain = syllable.rstrip("12345").lower()
            if not plain:
                continue
            # Fold the umlaut to "u". CC-CEDICT writes it as "u:", and
            # the pinyin-data files as "ü"; both name the same syllable.
            plain = plain.replace("ü", "u").replace("u:", "u")
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
        # The full source list with the licences, from sources.json.
        "sources_json": (
            json.dumps(load_json(SOURCES_JSON) or {}, ensure_ascii=False)
            if os.path.exists(SOURCES_JSON) else "{}"
        ),
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


def check_content_quality(conn: sqlite3.Connection) -> list[str]:
    """Check that the database holds the content the app needs.

    A content.db that is missing half its grammar or all of its Bulgarian
    glosses still "builds": the script prints a summary and exits 0, and
    the APK ships with a dictionary that answers in English or not at
    all. The failures this catches are silent, so they are checked here,
    before the file is written, and they stop the run.

    The thresholds are the measured state of a full pipeline run, minus a
    wide margin. They are not aspirations: a build that falls below them
    has lost a step, and the message names the step to re-run.
    """
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    problems: list[str] = []

    grammar = count("SELECT COUNT(*) FROM grammar")
    if grammar < 400:
        problems.append(
            f"grammar: {grammar} points (expected 500+) - "
            f"run pipeline/04_build_grammar.py"
        )

    with_bg = count("SELECT COUNT(*) FROM words WHERE gloss_bg != ''")
    if with_bg < 10000:
        problems.append(
            f"Bulgarian glosses: {with_bg:,} words (expected 10,000+) - "
            f"run pipeline/07_translate_bulgarian.py"
        )

    words = count("SELECT COUNT(*) FROM words")
    if words < 10000:
        problems.append(
            f"vocabulary: {words:,} words (expected 10,000+) - "
            f"run pipeline/03_build_vocab.py"
        )

    # Every word the learner can practise has to be pronounceable, or the
    # listening mode is a button that plays nothing.
    with_audio = count("SELECT COUNT(*) FROM words WHERE audio IS NOT NULL AND audio != ''")
    if with_audio == 0:
        problems.append(
            "audio: no word has a pronunciation clip - "
            "run pipeline/06_build_audio.py"
        )

    sentences = count("SELECT COUNT(*) FROM sentences")
    if sentences < 1000:
        problems.append(
            f"sentences: {sentences:,} (expected 1,000+) - "
            f"run pipeline/05_build_sentences.py"
        )

    ime = count("SELECT COUNT(*) FROM ime")
    if ime == 0:
        problems.append(
            "IME index: empty - run pipeline/03_build_vocab.py"
        )

    # The learning path. An app without it still builds and still shows
    # a dictionary, and the learner is the one who finds out that there
    # is no route from one word to the next. A curriculum with no
    # lessons is the same failure in a different place.
    lessons_in_path = count("SELECT COUNT(*) FROM curriculum_lessons")
    if lessons_in_path == 0:
        problems.append(
            "curriculum: no lessons - the learning path is empty "
            "(curriculum/*.json is missing or has no 'units')"
        )

    words_in_path = count("SELECT COUNT(*) FROM curriculum_words")
    if words_in_path == 0:
        problems.append(
            "curriculum: no words in the learning path - "
            "the lessons name no vocabulary"
        )

    # A duplicated word in the path is a silent loss: one of the two
    # lessons that name it teaches it twice, and the level it belongs
    # to is one word short of what the learner was promised. The
    # curriculum of HSK 1 was written by hand and it DID have a
    # duplicate -- 到 was in two lessons and 再 and 这 were in none.
    # Nothing else in the build noticed.
    duplicated = conn.execute(
        "SELECT hanzi, COUNT(*) FROM curriculum_words "
        "GROUP BY hanzi HAVING COUNT(*) > 1"
    ).fetchall()
    if duplicated:
        listed = ", ".join(f"{h} x{n}" for h, n in duplicated[:10])
        problems.append(
            f"curriculum: {len(duplicated)} words are in the path more than "
            f"once ({listed}) - every word belongs to exactly one lesson"
        )

    # A level that the path touches has to be covered by it. A level
    # where some words are on the path and some are not is a path that
    # stops in the middle without saying so.
    partial = []
    for level, level_words in conn.execute(
        "SELECT hsk_level, COUNT(*) FROM words WHERE hsk_level != '' "
        "GROUP BY hsk_level"
    ):
        covered = conn.execute(
            "SELECT COUNT(DISTINCT w.hanzi) FROM curriculum_words cw "
            "JOIN words w ON w.hanzi = cw.hanzi WHERE w.hsk_level = ?",
            (level,),
        ).fetchone()[0]
        if 0 < covered < level_words:
            partial.append(f"{level}: {covered}/{level_words}")

    if partial:
        problems.append(
            "curriculum: some levels are only partly on the path ("
            + ", ".join(partial)
            + ") - a level that is on the path has to be on it whole"
        )

    return problems


def remove_old_db(path: str) -> None:
    """Delete the database, even when something still holds it open.

    The emulator keeps a copy of content.db open while the app runs, and
    on Windows a file that is open cannot be deleted. Writing to a fresh
    file and moving it into place is not possible either -- the move
    fails for the same reason. So the old file is emptied first and the
    new database is built under a temporary name.

    The alternative -- letting the build fail with PermissionError --
    makes the build depend on whether an emulator happens to be running.
    """
    if not os.path.exists(path):
        return
    try:
        os.remove(path)
        return
    except PermissionError:
        pass
    # Still locked. Try to truncate it; SQLite can open a truncated file
    # and rewrite it from scratch.
    try:
        with open(path, "r+b") as fh:
            fh.truncate(0)
        print(f"  note: {os.path.basename(path)} was locked, emptied in place")
        return
    except PermissionError as exc:
        raise SystemExit(
            f"ERROR: cannot replace {path} -- it is locked by another "
            f"program. Close the emulator (or uninstall the app) and "
            f"run this again. ({exc})"
        )


def install_db(tmp: str, out: str) -> None:
    """Put the freshly built database in place of the old one.

    The new database is built under a temporary name first, so a run that
    fails the quality gate leaves the previous content.db untouched
    instead of replacing a working dictionary with an empty one.

    On Windows a file that another program holds open cannot be replaced,
    so the old one is emptied in place and the new bytes are copied over.
    """
    try:
        os.replace(tmp, out)
        return
    except OSError:
        pass
    remove_old_db(out)
    with open(tmp, "rb") as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    try:
        os.remove(tmp)
    except OSError:
        pass


def main() -> int:
    # The database is built under a temporary name. The quality gate runs
    # on it, and only a database that passes is put in place -- a degraded
    # content.db must never replace a working one.
    tmp_out = OUT + ".building"
    if os.path.exists(tmp_out):
        try:
            os.remove(tmp_out)
        except OSError:
            pass

    os.makedirs(DATA, exist_ok=True)
    conn = sqlite3.connect(tmp_out)
    conn.executescript(SCHEMA)

    audio = audio_index()
    print(f"audio files available: {len(audio)}")

    curriculum_units, hand_glosses = load_curriculum()
    print(f"curriculum: {len(curriculum_units)} units, "
          f"{len(hand_glosses)} hand-written glosses")

    print("building words ...")
    n_words, n_bg, n_machine = build_words(conn, audio, hand_glosses)
    print(f"  words: {n_words:,}  with a Bulgarian gloss: {n_bg:,} "
          f"(machine: {n_machine:,})")

    print("building the curriculum ...")
    n_curriculum_units, n_curriculum_lessons, n_curriculum_words = build_curriculum(
        conn, curriculum_units)
    print(f"  units: {n_curriculum_units}  lessons: {n_curriculum_lessons}  "
          f"words in the path: {n_curriculum_words}")

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

    # The gate runs BEFORE the commit and the VACUUM: a database that
    # fails it is not written, so a degraded content.db can never reach
    # the APK. There is no --allow-degraded escape hatch here on purpose.
    problems = check_content_quality(conn)
    if problems:
        conn.close()
        try:
            os.remove(tmp_out)
        except OSError:
            pass
        print()
        print("ERROR: the content database does not meet the quality bar:")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print("The database was NOT written. The previous one is untouched.")
        print("Re-run the steps above.")
        return 1

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    install_db(tmp_out, OUT)

    size = os.path.getsize(OUT)
    print()
    print(f"SUMMARY 08_build_content_db: words={n_words} grammar={n_grammar} "
          f"lessons={n_lessons} sentences={n_sentences} "
          f"path_units={n_curriculum_units} path_lessons={n_curriculum_lessons} "
          f"path_words={n_curriculum_words} "
          f"bytes={size:,} -> {OUT}")
    for key in ("word_count", "words_with_bg_gloss", "grammar_count",
                "sentence_count", "sentences_with_bg"):
        print(f"   {key} = {values[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

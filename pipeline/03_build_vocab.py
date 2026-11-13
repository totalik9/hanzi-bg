"""Build the graded HSK vocabulary list (data/vocab_hsk.json).

Inputs:
    data/raw/hsk_3_0_level_*.csv   official HSK 3.0 (Nov 2025) word lists
                                    from literatelanguages.com. The `hsk2026_level`
                                    column carries the new-syllabus level of each
                                    word, and the per-level files are cumulative
                                    (level N file = words *new* at level N).
    data/raw/cedict_1_0_ts_utf-8_mdbg.txt   CC-CEDICT for definitions / POS
    data/raw/phrase_pinyin.txt      multi-character word pinyin
    data/raw/pinyin_data.txt        per-character pinyin fallback
    data/hanzi.db                   built by 02_build_dictionary.py

Output:
    data/vocab_hsk.json  a JSON object:
      {
        "meta": {...},
        "words": [ {hanzi, pinyin, pinyin_number, pos, gloss_en,
                    hsk_level, char_count, is_verb, tags[]}, ... ]
      }

The script is safe to re-run; the output file is rewritten each time.

Usage:
    python pipeline/03_build_vocab.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _guards  # noqa: E402
from pinyin_utils import (  # noqa: E402
    DATA,
    RAW,
    canonical_pinyin_number,
    split_pinyin_by_chars,
    split_pinyin_syllables,
    strip_tones,
    tone_marked_to_number,
)

DB_PATH = os.path.join(DATA, "hanzi.db")
OUT = os.path.join(DATA, "vocab_hsk.json")

HSK_FILES = {
    "1": "hsk_3_0_level_1.csv",
    "2": "hsk_3_0_level_2.csv",
    "3": "hsk_3_0_level_3.csv",
    "4": "hsk_3_0_level_4.csv",
    "5": "hsk_3_0_level_5.csv",
    "6": "hsk_3_0_level_6.csv",
    "7-9": "hsk_3_0_level_7_9.csv",
}

# Part-of-speech labels as used by Wiktionary / CC-CEDICT style dictionaries.
# CC-CEDICT definitions are slash-separated sense glosses; a gloss that starts
# with "to " is the canonical verb marker in this dictionary.
VERB_GLOSS_PREFIXES = ("to ", "to be ", "to do ", "to have ")

# Extra verbs that CC-CEDICT glosses without a "to " prefix.
COMMON_VERB_CHARS = set(
    "爱看听说吃喝去来走跑笑哭想做打买卖飞跳唱问回答忘记得懂生气喜欢希望"
    "开始结束使用让给带找到进入离开准备需要可能必须能够应该帮助照顾"
)

# Wiktionary POS names -> short codes used in the output
WIKI_POS_MAP = {
    "noun": "n.",
    "proper noun": "n.",
    "verb": "v.",
    "adjective": "adj.",
    "adverb": "adv.",
    "pronoun": "pron.",
    "preposition": "prep.",
    "postposition": "prep.",
    "conjunction": "conj.",
    "numeral": "num.",
    "classifier": "cl.",
    "interjection": "int.",
    "particle": "part.",
    "onomatopoeia": "onom.",
    "prefix": "pref.",
    "suffix": "suff.",
    "idiom": "idiom.",
    "phrase": "phr.",
    "proverb": "prov.",
    "measure word": "cl.",
}


def parse_pos_from_wiktionary(wiki: dict | None) -> str:
    """Map a Wiktionary record's POS list to a short comma-separated code."""
    if not wiki:
        return ""
    codes = []
    for p in wiki.get("pos") or []:
        code = WIKI_POS_MAP.get(p.lower())
        if code and code not in codes:
            codes.append(code)
    return ",".join(codes)


def is_verb_from_definition(definition: str) -> bool:
    """CC-CEDICT marks verb senses by starting the gloss with "to ".

    >>> is_verb_from_definition("to eat; to consume/to eat at (a cafeteria etc)")
    True
    >>> is_verb_from_definition("side/edge/margin/border/boundary")
    False
    """
    if not definition:
        return False
    for sense in definition.split("/"):
        s = sense.strip().lower()
        if not s:
            continue
        if s.startswith(VERB_GLOSS_PREFIXES):
            return True
    return False


def _usable_definition(definition: str) -> bool:
    """True when a CC-CEDICT gloss carries a meaning worth teaching.

    Rows like "surname Bai" or "variant of 著|着[zhao1]" describe the
    character rather than its meaning, and they are exactly the rows
    that would otherwise be picked first.

    >>> _usable_definition("surname Bai")
    False
    >>> _usable_definition("variant of 著|着[zhao1]")
    False
    >>> _usable_definition("hundred/numerous/all kinds of")
    True
    """
    d = definition.strip()
    if not d:
        return False
    if re.match(r"^(surname|variant of|old variant|erhua|see also|abbr\. for)\b", d, re.I):
        return False
    # a gloss that is only a cross-reference has nothing to translate
    return bool(re.search(r"[a-zA-Z]{2}", d))


def _same_reading(cand_py: str, pinyin_marked: str) -> bool:
    """True when two pinyin strings name the same reading.

    Compares the tone-marked forms after normalising case, spacing and
    the CC-CEDICT capitalisation of surnames (Bai vs bai).

    The erhua apostrophe is normalised away as well: the HSK CSVs write
    "bǎo'ān" while CC-CEDICT writes "bǎo ān", and the two spellings name
    the same reading. Without this the comparison never matched and the
    builder fell back to the FIRST CC-CEDICT row -- which for 保安 is the
    capitalised surname row, so the learner was told that "security guard"
    means "Bonan ethnic group".

    >>> _same_reading("bǎi", "bǎi")
    True
    >>> _same_reading("Bǎi", "bǎi")
    True
    >>> _same_reading("Bǎi", "chē")
    False
    >>> _same_reading("bǎo ān", "bǎo'ān")
    True
    >>> _same_reading("Bǎo ān", "bǎo'ān")
    True
    >>> _same_reading("bǎo ān", "píng'ān")
    False
    """
    a = _reading_key(cand_py)
    b = _reading_key(pinyin_marked)
    return bool(a) and a == b


def _reading_key(text: str) -> str:
    """A comparison key for a pinyin reading.

    The case, the spacing and the erhua apostrophe are normalised away, so
    two spellings of the same reading produce the same key.

    The erhua suffix has three spellings -- "ér" in the HSK CSVs, "er"
    in some rows, and a bare "r" in CC-CEDICT ("nǚ hái r") -- so all three
    are folded into one canonical form.

    The TONES are kept, apart from the erhua suffix. 东西 is taught as
    "dōng xi" (thing, stuff) and also has a CC-CEDICT row "dōng xī" (east
    and west); stripping the tones would make the two readings
    indistinguishable and the learner would be taught the wrong meaning.

    >>> _reading_key("Bǎo ān")
    'bǎo ān'
    >>> _reading_key("bǎo'ān")
    'bǎo ān'
    >>> _reading_key("nǚ hái r")
    'nǚ hái ER'
    >>> _reading_key("nǚ hái ér")
    'nǚ hái ER'
    >>> _reading_key("dōng xī") == _reading_key("dōng xi")
    False
    """
    parts = []
    for token in (text or "").strip().lower().replace("'", " ").replace("’", " ").split():
        plain = strip_tones(token)
        if plain == "r" or plain == "er":
            # The erhua suffix, in any of its spellings.
            parts.append("ER")
        else:
            parts.append(token)
    return " ".join(parts)


def _agreement(definition: str, meaning: str) -> int:
    """How many words a gloss and the HSK meaning share.

    The HSK list is written for learners, so its meaning is the gloss the
    learner is supposed to end up with. When CC-CEDICT holds two rows for
    the SAME reading -- "Bǎo ān" (the Bonan ethnic group) and "bǎo ān"
    (the security guard) -- the one that agrees with the HSK meaning is
    the one to teach.

    Only words of three letters or more are counted, so that a short
    gloss does not match on an article or a preposition.

    >>> _agreement("to ensure public security", "security guard; ensuring safety")
    1
    >>> _agreement("to ensure public security", "to ensure safety")
    1
    >>> _agreement("Bonan ethnic group", "security guard")
    0
    """
    if not definition or not meaning:
        return 0
    words = set(re.findall(r"[a-z]{3,}", definition.lower()))
    truth = set(re.findall(r"[a-z]{3,}", meaning.lower()))
    return len(words & truth)


def _select_definition(
    cands: list[tuple[str, str, str]],
    pinyin_marked: str,
    hanzi: str,
    meaning: str,
) -> str:
    """Pick the CC-CEDICT row that carries the meaning being taught.

    The rows are ranked by how well they agree with the HSK meaning, and
    ties are broken in favour of the lower-case pinyin: CC-CEDICT
    capitalises a surname reading, and the capitalised row is often a
    place name or a family name rather than the word's own meaning.

    >>> rows = [("保安", "Bǎo ān", "Bonan ethnic group"),
    ...         ("保安", "bǎo ān", "to ensure public security")]
    >>> _select_definition(rows, "bǎo ān", "保安", "security guard")
    'to ensure public security'
    """
    best = ""
    best_score = -1
    for _trad, cand_py, d in cands:
        if not d or not _usable_definition(d):
            continue
        if not _same_reading(cand_py, pinyin_marked):
            continue
        score = _agreement(d, meaning)
        if not best:
            best = d
            best_score = score
        if score > best_score:
            best, best_score = d, score
        elif score == best_score and cand_py and cand_py[:1].islower():
            # The same meaning, but the reading a learner is taught.
            best = d
    if best:
        return best
    # No row matches the reading: take the first usable one.
    for _trad, _cand_py, d in cands:
        if d and _usable_definition(d):
            return d
    return ""


def load_hsk_rows() -> tuple[dict[str, dict], Counter]:
    """Read the HSK 3.0 CSVs into {hanzi: record}.

    Level comes from the `hsk2026_level` column (the new November 2025
    syllabus); the file a word appears in is used as a fallback.
    """
    words: dict[str, dict] = {}
    level_counts: Counter = Counter()
    for level, fname in HSK_FILES.items():
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            print(f"  WARNING: missing {fname}")
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                hanzi = (row.get("simplified") or "").strip()
                if not hanzi:
                    continue
                lvl = (row.get("hsk2026_level") or "").strip()
                if lvl not in HSK_FILES:
                    lvl = level
                rec = {
                    "hanzi": hanzi,
                    "traditional": (row.get("traditional") or "").strip(),
                    "pinyin_marked": (row.get("pinyin") or "").strip(),
                    "meaning": (row.get("meaning") or "").strip(),
                    "level": lvl,
                }
                # a word can appear in several files; keep the lowest level
                if hanzi in words:
                    prev = words[hanzi]["level"]
                    try:
                        if int(lvl.split("-")[0]) < int(prev.split("-")[0]):
                            words[hanzi] = rec
                    except ValueError:
                        pass
                    continue
                words[hanzi] = rec
                level_counts[lvl] += 1
    return words, level_counts


def load_phrase_pinyin() -> dict[str, str]:
    """Load phrase-level pinyin (tone-marked) from phrase-pinyin-data."""
    path = os.path.join(RAW, "phrase_pinyin.txt")
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or ": " not in line:
                continue
            word, py = line.split(": ", 1)
            out[word] = py.strip()
    return out


def load_char_pinyin(conn: sqlite3.Connection) -> dict[str, str]:
    """Per-character tone-marked pinyin, preferring pinyin-data over CC-CEDICT.

    pinyin-data's pinyin.txt lists every reading; the first is the most common.
    """
    out: dict[str, str] = {}
    path = os.path.join(RAW, "pinyin_data.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or ":" not in line:
                    continue
                codepoint, rest = line.split(":", 1)
                readings = rest.split("#")[0].strip()
                if not readings:
                    continue
                try:
                    ch = chr(int(codepoint.strip().replace("U+", ""), 16))
                except ValueError:
                    continue
                out[ch] = readings.split(",")[0].strip()
    # fall back to CC-CEDICT for characters pinyin-data does not cover
    for simp, py in conn.execute(
        "SELECT simplified, pinyin_with_tones FROM dict WHERE length(simplified)=1"
    ):
        out.setdefault(simp, py)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the graded HSK vocabulary list")
    ap.add_argument(
        "--allow-degraded",
        action="store_true",
        help="carry on when an input is missing, with a warning "
             "(the output is then NOT fit for the app)",
    )
    args = ap.parse_args()
    if args.allow_degraded:
        _guards.set_allow_degraded()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: missing {DB_PATH} - run 02_build_dictionary.py first")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("reading HSK 3.0 word lists ...")
    hsk_words, level_counts = load_hsk_rows()
    print(f"  unique HSK words: {len(hsk_words):,}")

    print("loading pinyin sources ...")
    phrase_py = load_phrase_pinyin()
    char_py = load_char_pinyin(conn)
    print(f"  phrase pinyin entries: {len(phrase_py):,}  char pinyin entries: {len(char_py):,}")

    # per-character reading lists, used to disambiguate run-together pinyin
    char_readings: dict[str, list[str]] = {}
    cr_path = os.path.join(RAW, "char_readings.json")
    if _guards.require_file(
        cr_path,
        "the per-character reading map",
        "python pipeline/_build_char_readings.py",
    ):
        with open(cr_path, encoding="utf-8") as fh:
            char_readings = json.load(fh)
    print(f"  characters with reading lists: {len(char_readings):,}")

    # Wiktionary part-of-speech labels (CC-CEDICT has none)
    wiki_pos: dict[str, dict] = {}
    wp_path = os.path.join(RAW, "wiktionary_pos.json")
    if os.path.exists(wp_path):
        with open(wp_path, encoding="utf-8") as fh:
            wiki_pos = json.load(fh)
    else:
        print("  WARNING: wiktionary_pos.json missing - POS will be derived from CC-CEDICT only")
    print(f"  wiktionary POS records: {len(wiki_pos):,}")

    # Bulgarian glosses from Chinese Wiktionary (real, human-written)
    bg_glosses: dict[str, list[str]] = {}
    bg_path = os.path.join(RAW, "bg_zh_wiktionary.json")
    if os.path.exists(bg_path):
        with open(bg_path, encoding="utf-8") as fh:
            bg_glosses = json.load(fh)
    print(f"  bulgarian gloss records: {len(bg_glosses):,}")

    # corpus frequency ranks
    freq_rank: dict[str, int] = {}
    fr_path = os.path.join(RAW, "word_freq.json")
    if _guards.require_file(
        fr_path,
        "the corpus frequency ranks",
        "python pipeline/_build_word_freq.py",
    ):
        with open(fr_path, encoding="utf-8") as fh:
            freq_rank = {k: int(v) for k, v in json.load(fh).items()}
    print(f"  words with a corpus frequency rank: {len(freq_rank):,}")

    # CC-CEDICT lookup for definitions, keyed by simplified form
    print("loading CC-CEDICT definitions ...")
    cedict: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute(
        "SELECT simplified, traditional, pinyin_with_tones, definition FROM dict"
    ):
        cedict.setdefault(row["simplified"], []).append(
            (row["traditional"], row["pinyin_with_tones"], row["definition"])
        )

    entries = []
    missing_def = 0
    missing_py = 0
    bg_count = 0
    level_of = Counter()

    for hanzi, rec in hsk_words.items():
        # --- pinyin -----------------------------------------------------
        # The HSK CSV pinyin is the primary source: it gives the reading the
        # learner is expected to know (CC-CEDICT sometimes lists a surname
        # reading first, e.g. 都 "Dū" instead of "dōu"). For multi-character
        # words the CSV writes the syllables run together, so they are split
        # using the known reading of each character.
        pinyin_marked = rec["pinyin_marked"]
        syllables: list[str] = []
        if pinyin_marked:
            if len(hanzi) == 1:
                syllables = split_pinyin_syllables(pinyin_marked)
            else:
                got = split_pinyin_by_chars(pinyin_marked, hanzi, char_readings)
                if got is None:
                    got = split_pinyin_syllables(pinyin_marked, n_syllables=len(hanzi))
                syllables = got
        if not syllables:
            # fall back to phrase-pinyin-data (already space-separated)
            phrase = phrase_py.get(hanzi, "")
            if phrase:
                syllables = phrase.split()
        if not syllables and len(hanzi) == 1:
            cp = char_py.get(hanzi, "")
            if cp:
                syllables = cp.split()
        if not syllables and len(hanzi) > 1:
            # concatenate the per-character readings
            parts = [char_py.get(c, "") for c in hanzi]
            if all(parts):
                syllables = [p for part in parts for p in part.split()]
        if not syllables:
            # last resort: the CC-CEDICT reading
            for _t, py, _d in cedict.get(hanzi, [])[:1]:
                syllables = py.split()
        if not syllables:
            missing_py += 1

        pinyin_marked = " ".join(syllables)
        pinyin_number = tone_marked_to_number(pinyin_marked) if pinyin_marked else ""
        # keep the canonical numeric form used by CC-CEDICT (u: for the umlaut)
        pinyin_number = canonical_pinyin_number(pinyin_number)

        # --- definition / part of speech ---------------------------------
        # CC-CEDICT lists several rows per character, one per reading, and
        # the FIRST one is often the least useful: 百 -> "surname Bai",
        # 车 -> "surname Che", 大学 -> "the Great Learning ... in
        # Confucianism". The reading the learner is actually taught
        # (bǎi, chē, dà xué) sits in a later row. So pick the row whose
        # pinyin matches the one we already resolved, and skip rows that
        # carry no meaning to translate.
        cands = cedict.get(hanzi, [])
        definition = _select_definition(cands, pinyin_marked, hanzi, rec["meaning"])
        if not definition:
            # CC-CEDICT may list only the traditional form
            row = conn.execute(
                "SELECT definition FROM dict WHERE traditional=? LIMIT 1",
                (rec["traditional"] or hanzi,),
            ).fetchone()
            if row and row["definition"]:
                definition = row["definition"]
        if not definition:
            # fall back to the English meaning from the HSK list
            definition = rec["meaning"]
            missing_def += 1

        # Part of speech: CC-CEDICT has no POS markers, so Wiktionary's
        # explicit POS labels are used when available and the verb flag is
        # derived from the "to ..." gloss convention.
        wiki = wiki_pos.get(hanzi)
        pos = parse_pos_from_wiktionary(wiki)
        is_verb = bool(wiki and any(p.lower() == "verb" for p in wiki.get("pos") or []))
        if not is_verb:
            is_verb = is_verb_from_definition(definition)
        if not is_verb and definition.lower().startswith("to "):
            is_verb = True
        if not is_verb and len(hanzi) == 1 and hanzi in COMMON_VERB_CHARS:
            is_verb = True
        if not pos and is_verb:
            pos = "v."

        tags = []
        if rec["level"] == "7-9":
            tags.append("hsk7-9")
        else:
            tags.append(f"hsk{rec['level']}")
        if len(hanzi) == 1:
            tags.append("single_char")
        if is_verb:
            tags.append("verb")
        if len(hanzi) >= 3:
            tags.append("multi_char")
        if rec["meaning"] and definition == rec["meaning"]:
            tags.append("gloss_from_hsk")
        else:
            tags.append("gloss_from_cedict")

        # --- Bulgarian gloss --------------------------------------------
        # Only genuine Bulgarian translations are used; there is no Bulgarian
        # corpus for the rest of the vocabulary, so those stay empty rather
        # than being machine-translated.
        bg_list = bg_glosses.get(hanzi)
        bg_gloss = "; ".join(bg_list) if bg_list else ""
        if bg_gloss:
            bg_count += 1

        entries.append({
            "hanzi": hanzi,
            "pinyin": pinyin_marked,
            "pinyin_number": pinyin_number,
            "pos": pos,
            "gloss_en": definition,
            "gloss_bg": bg_gloss,
            "hsk_level": rec["level"],
            "char_count": len(hanzi),
            "is_verb": bool(is_verb),
            "freq": freq_rank.get(hanzi),
            "tags": tags,
        })
        level_of[rec["level"]] += 1

    # sort by level then by pinyin so the file is stable across runs
    def level_key(e):
        lv = e["hsk_level"]
        try:
            return (0, int(lv.split("-")[0]), e["pinyin"], e["hanzi"])
        except ValueError:
            return (1, 0, e["pinyin"], e["hanzi"])

    entries.sort(key=level_key)

    meta = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hsk_source": "literatelanguages.com HSK 3.0 word lists (column hsk2026_level)",
        "hsk_tagging_confidence": "official",
        "hsk_note": (
            "Levels come from the hsk2026_level column of the HSK 3.0 (November 2025 "
            "syllabus) CSV lists. Cumulative totals: "
            + ", ".join(
                f"level {lv}: {sum(1 for e in entries if e['hsk_level'] == lv)}"
                for lv in sorted(level_of, key=lambda s: (0, int(s.split('-')[0])) if s.split('-')[0].isdigit() else (1, 0))
            )
        ),
        "word_count": len(entries),
        "missing_pinyin": missing_py,
        "gloss_from_hsk_only": missing_def,
        "levels": dict(sorted(level_of.items())),
        "is_verb_count": sum(1 for e in entries if e["is_verb"]),
        "gloss_bg_count": bg_count,
        "gloss_bg_source": "Chinese Wiktionary (kaikki.org zh extract), CC BY-SA 4.0",
        "pos_source": (
            "Wiktionary POS labels where available, otherwise derived from the "
            "CC-CEDICT 'to ...' gloss convention"
        ),
        "freq_source": "Tatoeba Chinese (cmn) corpus frequency, CC BY 2.0 FR",
        "licenses": {
            "definitions": "CC-CEDICT, CC BY-SA 4.0",
            "hsk_lists": "literatelanguages.com HSK 3.0 word lists",
            "pinyin": "mozillazg/pinyin-data + mozillazg/phrase-pinyin-data, MIT",
            "pos_and_bulgarian_glosses": "Wiktionary via kaikki.org, CC BY-SA 4.0",
            "frequency": "Tatoeba, CC BY 2.0 FR",
        },
    }

    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "words": entries}, fh, ensure_ascii=False, indent=1)

    print()
    print("sample entries:")
    for e in entries[:6]:
        print("   ", json.dumps(e, ensure_ascii=False))
    verbs = [e for e in entries if e["is_verb"]][:6]
    print("sample verbs:")
    for e in verbs:
        print("   ", json.dumps(e, ensure_ascii=False))

    conn.close()
    print()
    print(f"SUMMARY 03_build_vocab: words={len(entries):,} out={OUT}")
    print("   per level:", dict(sorted(level_of.items(), key=lambda kv: (0, int(kv[0].split('-')[0])) if kv[0].split('-')[0].isdigit() else (1, 0))))
    print(f"   is_verb={meta['is_verb_count']:,}  missing_pinyin={missing_py}  gloss_from_hsk_only={missing_def}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

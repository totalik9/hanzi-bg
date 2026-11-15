"""Translate the vocabulary into Bulgarian with a local model (no API).

Input:
    data/vocab_hsk.json       the graded HSK vocabulary
    data/raw/bg_zh_wiktionary.json  human Bulgarian glosses

Output:
    data/bg_translations.json  {hanzi: {"gloss": "...", "source": "machine"}}

Two things decide the quality of a Bulgarian gloss:

1. WHAT is translated. Translating the bare Chinese character gives a
   single arbitrary sense ("边" -> "Вън"). Translating the ENGLISH gloss
   that CC-CEDICT already provides gives the full meaning, because the
   English gloss has the senses separated by slashes.

2. HOW it is translated. Translating the whole gloss at once produces
   duplicated senses ("side/edge/margin/border/boundary" -> "странична/
   крайна/маржинална/гранична/гранична"). Translating one sense at a
   time and then de-duplicating gives a clean list.

The human glosses from Chinese Wiktionary always win: they are written by
people and are the reference. The model fills the gap for the words that
have no human gloss, and every machine translation is marked as such so
the app can tell the learner which is which.

The model is chosen with --model. The default is facebook/m2m100_418M,
which is licensed MIT. The licence matters more than it looks: the
Bulgarian glosses are baked into the APK and shipped to whoever
installs the app, so a non-commercial licence on the model would be a
non-commercial licence on the app. The old default,
facebook/nllb-200-distilled-600M, is CC-BY-NC-4.0 and is still
selectable -- but it must not be used for a release that is sold.

Usage:
    python pipeline/07_translate_bulgarian.py
    python pipeline/07_translate_bulgarian.py --level 1        # one level first
    python pipeline/07_translate_bulgarian.py --limit 200
    python pipeline/07_translate_bulgarian.py --model m2m100_418M
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW  # noqa: E402
from importlib import import_module  # noqa: E402
from _guards import set_allow_degraded  # noqa: E402
from _translation_model import (  # noqa: E402
    Translator,
    cache_path,
    load_or_migrate_cache,
    record_provenance,
    resolve_model,
    save_cache,
)

# The cleaning of the English senses lives in 09_clean_glosses.py and is
# used from here too: the translation must not see a sense the cleaning
# has already thrown away, or one it has already tidied up.
clean_sense = import_module("09_clean_glosses").clean_sense

VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
BG_GLOSS = os.path.join(RAW, "bg_zh_wiktionary.json")
OUT = os.path.join(DATA, "bg_translations.json")
# The cache belongs to the model that wrote it, so the file name carries
# the model name: data/bg_sense_cache.m2m100_418M.json. Two models must
# not share a cache -- the cached translations are the model's own
# output, and mixing two translation styles in one word list is worse
# than having no cache at all.
CACHE_BASE = os.path.join(DATA, "bg_sense_cache.json")
CONTENT_DB = os.path.join(DATA, "content.db")

# How many senses a Bulgarian gloss carries. Three is enough to recognise
# a word; more turns the card into a dictionary entry.
MAX_SENSES = 3


def load_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"  WARNING: cannot read {path}: {exc}")
        return None


def split_senses(gloss_en: str) -> list[str]:
    """Split a CC-CEDICT gloss into its individual senses.

    The cleaning is the one from 09_clean_glosses.py, and that is not an
    accident: two copies of the same rules drift apart, and then the
    translation translates senses the cleaning never saw. The result was
    "(CL: )" and "Fig. " reaching the learner in Bulgarian.

    >>> split_senses("leaf (CL: )/(slang) marijuana")
    ['leaf', '(slang) marijuana']
    >>> split_senses("Taiwan (abbr.)")
    ['Taiwan']
    """
    if not gloss_en:
        return []
    out: list[str] = []
    for part in gloss_en.split("/"):
        cleaned = clean_sense(part.strip())
        if not cleaned or len(cleaned) > 60:
            continue
        if not re.search(r"[a-zA-Z]", cleaned):
            continue
        out.append(cleaned)
    return out[:MAX_SENSES]


def clean_translation(text: str) -> str:
    """Trim the model's output down to a usable gloss.

    The model sometimes returns the same alternative twice: "to speak;
    to talk; to say" comes back as "да говоря; да говоря; да казва". The
    alternatives are separated by ";" or ",", and a gloss that says the
    same thing twice looks broken to a learner, so the repeats go.

    >>> clean_translation("да говоря; да говоря; да казва")
    'да говоря; да казва'
    >>> clean_translation("вода")
    'вода'

    The English source with something stuck to it is not Bulgarian
    either:

    >>> clean_translation("Wording →")
    ''
    >>> clean_translation("5")
    '5'
    """
    text = text.strip()
    text = text.rstrip(" .")
    text = " ".join(text.split())
    # The model sometimes returns the source text unchanged.
    if re.fullmatch(r"[A-Za-z\s\-']+", text):
        return ""

    # The model sometimes returns the English source with something
    # stuck to it -- "Wording ->" for 字眼 -- so the check above, which
    # only accepts a whole string of English, misses it. A Bulgarian
    # gloss has to contain Bulgarian letters: Latin letters without a
    # single Cyrillic one means the model handed back the English.
    #
    # A gloss that is only a number ("5" for 五) is left alone: it has
    # no Latin letters either, and it is a correct answer.
    if re.search(r"[A-Za-z]", text) and not re.search(r"[\u0400-\u04ff]", text):
        return ""

    # The model sometimes starts the answer with a dash: "- Не", "- Татко".
    # It is not a definition.
    text = re.sub(r"^[-–—]+\s*", "", text)

    # Collapse a part that is one word said over and over.
    parts = [p.strip() for p in re.split(r"\s*[;,]\s*", text) if p.strip()]
    parts = [_collapse_repeated_words(p) for p in parts]

    # Drop an alternative that repeats an earlier one.
    if len(parts) > 1:
        seen: set[str] = set()
        kept: list[str] = []
        for part in parts:
            key = _duplicate_key(part)
            if key in seen:
                continue
            seen.add(key)
            kept.append(part)
        parts = kept
    text = "; ".join(parts)
    return text


def _collapse_repeated_words(part: str) -> str:
    """Collapse a part that is one word said over and over.

    "съдебно съдебно съдебно съдебно" is what the model returns when
    it loops on a single word, and "Много много" is the same fault
    with one repeat. The learner sees a broken card.

    The loop also cuts the last word in half: "съдебно съдебно съ" --
    the generation hit its token limit mid-word. A trailing fragment
    that is a prefix of the repeated word is that cut, and it goes too.

    >>> _collapse_repeated_words("съдебно съдебно съдебно")
    'съдебно'
    >>> _collapse_repeated_words("Много много")
    'Много'
    >>> _collapse_repeated_words("да не е така")
    'да не е така'
    >>> _collapse_repeated_words("съдебно съдебно съ")
    'съдебно'
    >>> _collapse_repeated_words("тегло равно на 500 g")
    'тегло равно на 500 g'
    >>> _collapse_repeated_words("Слизай с")
    'Слизай с'
    """
    words = part.split()
    if len(words) < 2:
        return part

    # The generation was cut mid-word at the end of a repeated run:
    # "съдебно съдебно съ" -- drop the fragment. It is a strict prefix
    # of the repeated word before it, and it is short.
    #
    # The run matters: without it, "Слизай с" would lose the "с" that
    # means "with".
    if len(words) >= 3:
        last, prev, before = words[-1], words[-2], words[-3]
        if (
            prev.lower() == before.lower()
            and len(last) <= 3
            and len(last) < len(prev)
            and prev.lower().startswith(last.lower())
        ):
            words = words[:-1]

    # Collapse every run of the same word.
    collapsed: list[str] = []
    for word in words:
        if collapsed and collapsed[-1].lower() == word.lower():
            continue
        collapsed.append(word)

    return " ".join(collapsed)


def _strip_stress(text: str) -> str:
    """Remove the stress mark from a Bulgarian word.

    The human glosses from Wiktionary carry the stress: "се́дмица". The
    model does not: "седмица". They are the same word, and a gloss that
    lists both teaches the learner that they are two.

    >>> _strip_stress("се́дмица")
    'седмица'
    >>> _strip_stress("седмица")
    'седмица'
    """
    return "".join(ch for ch in text if not (0x300 <= ord(ch) <= 0x36F))


def _duplicate_key(part: str) -> str:
    """The key under which two alternatives count as the same.

    "(идиом) непроменлив" and "непроменлив" are the same word, and
    "Много много" is one word said twice. "бяло" and "бял" are the
    same word too -- Bulgarian marks the definite article on the
    adjective, so the machine writes it both ways.

    >>> _duplicate_key("(идиом) непроменлив")
    'непроменлив'
    >>> _duplicate_key("Добре")
    'добре'
    >>> _duplicate_key("бяло")
    'бял'
    """
    s = re.sub(r"^\((?:идиом|idiom|разг|книж|сленг|жарг)\)\s*", "", part.strip().lower())
    s = re.sub(r"[^\w\s]", "", s)
    s = " ".join(s.split())
    # "Много много" -> "много"
    words = s.split()
    if len(words) == 2 and words[0] == words[1]:
        s = words[0]
    # "бяло" and "бял" are the same word.
    if len(s) > 3 and s.endswith("о") and s[:-1].endswith("л"):
        s = s[:-1]
    return s


# The cache helpers are shared with the other translation steps, so
# every step treats a cache the same way: a killed run never leaves a
# half-written cache behind, and a re-run only translates what is new.


def seed_cache_from_previous_run(
    cache: dict[str, str],
    db_path: str,
    translations_path: str,
) -> tuple[int, int]:
    """Recover the sense cache from a previous run's two output files.

    The previous run stored one Bulgarian gloss per WORD, joined with
    " / ". The cache needs one translation per English SENSE. The two can
    be lined up exactly when the word's gloss has as many parts as the
    word has senses, because the assembler only drops a part when the
    model returned nothing or a duplicate -- and then the counts differ.

    The English senses come from content.db, which still holds the
    gloss_en the previous run translated. So this has to run BEFORE
    content.db is rebuilt.

    Returns (seeded senses, words that could not be lined up).

    >>> import json, sqlite3, tempfile, os
    >>> tmp = tempfile.mkdtemp()
    >>> db = os.path.join(tmp, "content.db")
    >>> conn = sqlite3.connect(db)
    >>> _ = conn.execute("CREATE TABLE words (hanzi TEXT, gloss_en TEXT, gloss_source TEXT)")
    >>> _ = conn.execute("INSERT INTO words VALUES ('水', 'water/liquid', 'machine')")
    >>> _ = conn.execute("INSERT INTO words VALUES ('错', 'wrong; mistake', 'machine')")
    >>> conn.commit()
    >>> conn.close()
    >>> out = os.path.join(tmp, "bg.json")
    >>> _ = json.dump({"水": {"gloss": "вода / течност", "source": "machine"}},
    ...              open(out, "w", encoding="utf-8"))
    >>> cache = {}
    >>> seed_cache_from_previous_run(cache, db, out)
    (2, 0)
    >>> cache["water"]
    'вода'
    """
    if not os.path.exists(db_path):
        return 0, 0
    translations = load_json(translations_path)
    if not isinstance(translations, dict):
        return 0, 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT hanzi, gloss_en FROM words WHERE gloss_source = 'machine'"
        ).fetchall()
    finally:
        conn.close()

    seeded = 0
    skipped = 0
    for row in rows:
        entry = translations.get(row["hanzi"])
        if not isinstance(entry, dict) or entry.get("source") != "machine":
            continue
        gloss = (entry.get("gloss") or "").strip()
        if not gloss:
            continue
        parts = gloss.split(" / ")
        # Rejoining must give the gloss back: that proves the split on
        # " / " did not cut a part in half.
        if " / ".join(parts) != gloss:
            continue
        senses = split_senses(row["gloss_en"] or "")
        if len(senses) != len(parts):
            skipped += 1
            continue
        for sense, part in zip(senses, parts):
            if sense not in cache:
                cache[sense] = part
                seeded += 1
    return seeded, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate the vocabulary with NLLB-200")
    ap.add_argument("--level", help="only this HSK level")
    ap.add_argument("--limit", type=int, help="stop after N words")
    ap.add_argument("--batch", type=int, default=24, help="sentences per batch")
    ap.add_argument("--model", help="the translation model; the default is "
                                   "the permissive one (MIT)")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="carry on when an input is missing")
    args = ap.parse_args()

    if args.allow_degraded:
        set_allow_degraded()

    spec = resolve_model(args.model)
    CACHE = cache_path(CACHE_BASE, spec)
    print(f"model: {spec.model_id} ({spec.license}) -- {spec.note}")

    if not os.path.exists(VOCAB_JSON):
        print(f"ERROR: missing {VOCAB_JSON} - run 03_build_vocab.py first")
        return 1

    data = load_json(VOCAB_JSON)
    words = data["words"] if isinstance(data, dict) else data

    # Human glosses win over anything the model produces.
    human: dict[str, str] = {}
    bg_data = load_json(BG_GLOSS) or {}
    for word, glosses in bg_data.items():
        if isinstance(glosses, list) and glosses:
            human[word] = glosses[0]

    todo = []
    for w in words:
        hanzi = w.get("hanzi")
        if not hanzi:
            continue
        if args.level and str(w.get("hsk_level")) != args.level:
            continue
        todo.append(w)

    seen = set()
    unique = []
    for w in todo:
        if w["hanzi"] in seen:
            continue
        seen.add(w["hanzi"])
        unique.append(w)
    if args.limit:
        unique = unique[:args.limit]

    print(f"words needing a Bulgarian gloss: {len(unique):,} "
          f"(human glosses already cover {len(human):,})")
    if not unique:
        print("nothing to translate")
        return 0

    # Collect every sense that has to be translated.
    senses: list[str] = []
    sense_owner: dict[str, list[str]] = {}
    for w in unique:
        parts = split_senses(w.get("gloss_en") or "")
        w["_senses"] = parts
        for p in parts:
            if p not in sense_owner:
                sense_owner[p] = []
                senses.append(p)
    print(f"distinct English senses to translate: {len(senses):,}")

    # The cache holds the senses that are already translated. A first run
    # has to translate everything; a re-run after a change to the English
    # glosses only translates the senses that are new.
    cache, adopted = load_or_migrate_cache(CACHE_BASE, spec)
    if adopted:
        print(f"  adopted the old cache: it was {spec.name}'s work")

    # The cache holds the model's output, cleaned. When the cleaner
    # changes, the values it already cleaned are stale: the cleaner
    # gets a second pass over them, and the ones it now rejects are
    # dropped so they are translated again.
    #
    # Without this, a gloss the cleaner used to accept stays in the
    # cache for ever -- "Wording →" for 字眼 was an English answer the
    # cleaner did not recognise at the time it was cached.
    recleaned = 0
    dropped = 0
    for sense, value in list(cache.items()):
        cleaned = clean_translation(value)
        if not cleaned:
            del cache[sense]
            dropped += 1
        elif cleaned != value:
            cache[sense] = cleaned
            recleaned += 1
    if recleaned or dropped:
        print(f"  re-cleaned {recleaned:,} cached glosses, dropped {dropped:,}")
        save_cache(CACHE, cache)
    if not cache and spec.family == "nllb":
        # The previous run's output was NLLB's, so only NLLB may seed
        # its cache from it. Seeding the MIT model's cache with NLLB's
        # Bulgarian would put one model's translation under another
        # model's name.
        seeded, skipped = seed_cache_from_previous_run(cache, CONTENT_DB, OUT)
        if seeded:
            save_cache(CACHE, cache)
            print(f"  seeded the cache from the previous run: {seeded:,} senses "
                  f"({skipped:,} words could not be lined up)")
    todo_senses = [s for s in senses if s not in cache]
    print(f"  already in the cache: {len(senses) - len(todo_senses):,} "
          f"-> {len(todo_senses):,} to translate")

    # The clock starts here, not inside the translation loop: when every
    # sense is already in the cache there is nothing to translate, and
    # the summary still has to report how long the run took.
    started = time.time()

    if todo_senses:
        print(f"loading {spec.model_id} ...")
        translator = Translator(spec)
        print(f"  licence: {spec.license} ({spec.license_url})")
        print(f"  device: cpu, threads: {translator.threads}")

        for i in range(0, len(todo_senses), args.batch):
            chunk = todo_senses[i:i + args.batch]
            decoded = translator.translate(
                chunk, max_new_tokens=32, batch_size=args.batch
            )
            for source, out in zip(chunk, decoded):
                cache[source] = clean_translation(out)
            # The cache is written after every batch: a run that is killed
            # keeps the work it already did.
            save_cache(CACHE, cache)

            done = i + len(chunk)
            if done % (args.batch * 20) == 0 or done == len(todo_senses):
                rate = done / max(0.001, time.time() - started)
                remaining = (len(todo_senses) - done) / max(0.001, rate)
                print(f"  {done}/{len(todo_senses)} senses ({rate:.1f}/s, "
                      f"~{remaining / 60:.0f} min left)")

    # Assemble a Bulgarian gloss per word, de-duplicating the senses.
    results: dict[str, dict] = {}
    for w in unique:
        hanzi = w["hanzi"]
        parts = w.get("_senses") or []
        bg_parts: list[str] = []
        seen_bg: set[str] = set()
        for p in parts:
            t = cache.get(p, "")
            if not t:
                continue
            if t.lower() in seen_bg:
                continue
            seen_bg.add(t.lower())
            bg_parts.append(t)
        if bg_parts:
            results[hanzi] = {
                "gloss": " / ".join(bg_parts),
                "source": "machine",
            }

    # Merge with the human glosses so the file is the complete picture.
    #
    # The human gloss goes FIRST, because it was written by a person.
    # But it used to replace the machine gloss entirely, and that cost
    # the learner the other senses: 197 of the 457 words with a human
    # gloss had a single synonym where the English carries three or
    # more. It also cost correctness for the polyphonic characters: 和
    # was glossed "тишина" (quiet) because the Wiktionary entry that
    # was scanned lists that sense, while the entry teaches "and; with".
    #
    # So the human gloss leads and the machine senses follow it.
    merged: dict[str, dict] = {}
    for word, gloss in human.items():
        merged[word] = {"gloss": gloss, "source": "human"}

    for hanzi, got in results.items():
        human_gloss = human.get(hanzi)
        if not human_gloss:
            merged[hanzi] = got
            continue
        # The machine senses the human gloss does not already cover.
        extra: list[str] = []
        seen = {_strip_stress(human_gloss.strip().lower())}
        for part in got["gloss"].split(" / "):
            key = _strip_stress(part.strip().lower())
            if not key or key in seen:
                continue
            seen.add(key)
            extra.append(part)
        if extra:
            merged[hanzi] = {
                "gloss": " / ".join([human_gloss] + extra),
                "source": "human+machine",
            }
        else:
            merged[hanzi] = {"gloss": human_gloss, "source": "human"}

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=1, sort_keys=True)

    machine = sum(1 for v in merged.values() if v["source"] == "machine")
    record_provenance("vocabulary", spec, len(results))
    print()
    print(f"SUMMARY 07_translate_bulgarian: translated={len(results)} "
          f"human={len(human)} machine={machine} total={len(merged)} -> {OUT}")
    print(f"   elapsed={time.time() - started:.0f}s")
    for w in unique[:8]:
        h = w["hanzi"]
        got = results.get(h)
        print(f"   {h} ({str(w.get('gloss_en', ''))[:36]}) -> "
              f"{got['gloss'] if got else 'NO TRANSLATION'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

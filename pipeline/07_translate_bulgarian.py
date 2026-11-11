"""Translate the vocabulary into Bulgarian with NLLB-200 (local, no API).

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
people and are the reference. NLLB-200 fills the gap for the words that
have no human gloss, and every machine translation is marked as such so
the app can tell the learner which is which.

NLLB-200 is licensed CC-BY-NC, which is fine for this non-commercial
project. It is NOT fine for a commercial release: the Bulgarian glosses
would have to be replaced before any paid distribution.

Usage:
    python pipeline/07_translate_bulgarian.py
    python pipeline/07_translate_bulgarian.py --level 1        # one level first
    python pipeline/07_translate_bulgarian.py --limit 200
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

VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
BG_GLOSS = os.path.join(RAW, "bg_zh_wiktionary.json")
OUT = os.path.join(DATA, "bg_translations.json")
CACHE = os.path.join(DATA, "bg_sense_cache.json")
CONTENT_DB = os.path.join(DATA, "content.db")

MODEL_ID = "facebook/nllb-200-distilled-600M"

# The gloss is built from the English sense list, so English is the source.
SOURCE_LANG = "eng_Latn"
TARGET_LANG = "bul_Cyrl"

# How many senses a Bulgarian gloss carries. Three is enough to recognise
# a word; more turns the card into a dictionary entry.
MAX_SENSES = 3

# CC-CEDICT glosses carry noise that must not be translated.
_GLOSS_NOISE = re.compile(
    r"\b(?:CL:|abbr\. for|see also|variant of|old variant|surname|erhua)\b[^/]*",
    re.IGNORECASE,
)


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
    """Split a CC-CEDICT gloss into its individual senses."""
    if not gloss_en:
        return []
    clean = _GLOSS_NOISE.sub("", gloss_en)
    parts = [p.strip() for p in clean.split("/")]
    out: list[str] = []
    for p in parts:
        p = p.strip().strip(";").strip()
        if not p or len(p) > 60:
            continue
        if not re.search(r"[a-zA-Z]", p):
            continue
        out.append(p)
    return out[:MAX_SENSES]


def clean_translation(text: str) -> str:
    """Trim the model's output down to a usable gloss."""
    text = text.strip()
    text = text.rstrip(" .")
    text = " ".join(text.split())
    # The model sometimes returns the source text unchanged.
    if re.fullmatch(r"[A-Za-z\s\-']+", text):
        return ""
    return text


def load_cache(path: str) -> dict[str, str]:
    """Read the English sense -> Bulgarian translation cache.

    The cache is what makes a re-run cheap. A full translation of the
    vocabulary is 16 135 senses and takes about 95 minutes on the CPU;
    a re-run after a change to the English glosses only needs the senses
    that are actually new.

    >>> import tempfile, os
    >>> path = os.path.join(tempfile.mkdtemp(), "cache.json")
    >>> save_cache(path, {"water": "вода"})
    >>> load_cache(path)
    {'water': 'вода'}
    """
    data = load_json(path)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_cache(path: str, cache: dict[str, str]) -> None:
    """Write the cache atomically.

    The write goes to a temporary file that is then moved into place, so
    a run that is killed halfway never leaves a half-written cache
    behind: the old one stays valid and the work is simply redone.

    >>> import tempfile, os
    >>> path = os.path.join(tempfile.mkdtemp(), "cache.json")
    >>> save_cache(path, {"a": "а"})
    >>> load_cache(path)
    {'a': 'а'}
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


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
    args = ap.parse_args()

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
        if hanzi in human:
            continue
        if (w.get("gloss_bg") or "").strip():
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
    cache = load_cache(CACHE)
    if not cache:
        seeded, skipped = seed_cache_from_previous_run(cache, CONTENT_DB, OUT)
        if seeded:
            save_cache(CACHE, cache)
            print(f"  seeded the cache from the previous run: {seeded:,} senses "
                  f"({skipped:,} words could not be lined up)")
    todo_senses = [s for s in senses if s not in cache]
    print(f"  already in the cache: {len(senses) - len(todo_senses):,} "
          f"-> {len(todo_senses):,} to translate")

    if todo_senses:
        print(f"loading {MODEL_ID} ...")
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, src_lang=SOURCE_LANG)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
        model.eval()
        print(f"  device: cpu, threads: {torch.get_num_threads()}")

        bos = tokenizer.convert_tokens_to_ids(TARGET_LANG)

        started = time.time()
        for i in range(0, len(todo_senses), args.batch):
            chunk = todo_senses[i:i + args.batch]
            tokenizer.src_lang = SOURCE_LANG
            encoded = tokenizer(chunk, return_tensors="pt", padding=True, truncation=True)
            with torch.no_grad():
                generated = model.generate(
                    **encoded,
                    forced_bos_token_id=bos,
                    max_new_tokens=32,
                    num_beams=2,
                )
            decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
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
    merged: dict[str, dict] = {}
    for word, gloss in human.items():
        merged[word] = {"gloss": gloss, "source": "human"}
    merged.update(results)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=1, sort_keys=True)

    machine = sum(1 for v in merged.values() if v["source"] == "machine")
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

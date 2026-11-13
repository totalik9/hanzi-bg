"""Translate the short study sentences into Bulgarian with NLLB-200.

Input:
    data/sentences.json       the Tatoeba sentence corpus (05_build_sentences.py)

Output:
    data/sentences.json       the same file, with `translations_bg` filled
                              in for the sentences that had none

WHY THIS EXISTS

The word-order mode works on sentences that have a Bulgarian
translation: the learner sees the Bulgarian meaning and has to rebuild
the Chinese sentence. The database had 396 such sentences, and the mode
took the 60 SHORTEST of them -- so the learner met the same six words
over and over and then hit "Няма повече изречения" after a few dozen
exercises.

The corpus has 22 819 short sentences with an English translation and no
Bulgarian one. Translating them turns a dead end into a real study
material pool.

WHY ONLY THE SHORT ONES

A word-order exercise with twenty tokens is not a word-order exercise.
The sentences are the short ones -- the corpus is full of them --
because those are the ones a learner can hold in their head and reorder.

THE CACHE

The translation goes through the same kind of sense cache as
07_translate_bulgarian.py: English sentence -> Bulgarian sentence, in
data/bg_sentence_cache.json. The English sentences repeat a lot across
the corpus, so the cache saves a great deal of work: the first pass
translates the distinct sentences, and every later occurrence is free.

Usage:
    python pipeline/12_translate_sentences.py
    python pipeline/12_translate_sentences.py --limit 200
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA  # noqa: E402

SENTENCES_JSON = os.path.join(DATA, "sentences.json")
CACHE = os.path.join(DATA, "bg_sentence_cache.json")

MODEL_ID = "facebook/nllb-200-distilled-600M"
SOURCE_LANG = "eng_Latn"
TARGET_LANG = "bul_Cyrl"

# The longest sentence the model takes.
MAX_TOKENS = 128

# Sentences longer than this are not word-order material.
MAX_SENTENCE_CHARS = 12


def is_usable(text: str) -> bool:
    """True when a machine translation is clean enough to teach from.

    The word-order mode shows the Bulgarian sentence as the thing the
    learner is aiming at, and the learner rebuilds the Chinese to
    match it. A wrong Bulgarian sentence is not a slightly imperfect
    exercise -- it teaches the wrong meaning.

    NLLB-200 makes three kinds of mess on short sentences, and all
    three are caught here:

      * a DIALOGUE where there should be one sentence: "- Ето го. -
        Добре." The learner is asked to rebuild one Chinese sentence
        and the prompt shows two.
      * the English left in the text: "Подай се." is fine, but
        "Submit the form." is not a translation.
      * a gloss rather than a sentence: "Очарователно." for 討厭.
        (disgusting) is a wrong word, and no filter can catch every
        wrong word -- which is why the human glosses are preferred
        wherever they exist.

    The check is about the shape of the text, not about whether it is
    correct: a filter cannot tell a wrong word from a right one. The
    human translations from the corpus are always kept.
    """
    if not text:
        return False
    if len(text) > 80:
        return False
    # A dialogue: two or more dashes with a space after them.
    if re.search(r"-\s", text):
        return False
    # English left in the text.
    if re.search(r"[A-Za-z]", text):
        return False
    # It has to be Bulgarian.
    if not re.search(r"[\u0400-\u04ff]", text):
        return False
    return True


def load_cache(path: str) -> dict[str, str]:
    data = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = None
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_cache(path: str, cache: dict[str, str]) -> None:
    """Write the cache atomically: a killed run must not corrupt it."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def translate(texts: list[str], cache: dict[str, str], batch: int) -> dict[str, str]:
    """Translate the sentences that are not in the cache yet."""
    todo = [t for t in dict.fromkeys(texts) if t not in cache]
    if not todo:
        return cache

    print(f"loading {MODEL_ID} ...")
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, src_lang=SOURCE_LANG)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
    model.eval()
    print(f"  device: cpu, threads: {torch.get_num_threads()}")

    bos = tokenizer.convert_tokens_to_ids(TARGET_LANG)
    started = time.time()

    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        tokenizer.src_lang = SOURCE_LANG
        encoded = tokenizer(
            chunk, return_tensors="pt", padding=True, truncation=True,
            max_length=MAX_TOKENS,
        )
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                forced_bos_token_id=bos,
                max_new_tokens=MAX_TOKENS,
                num_beams=2,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for source, out in zip(chunk, decoded):
            cache[source] = out.strip()
        # The cache is written after every batch, so a run that is
        # killed keeps the work it already did.
        save_cache(CACHE, cache)

        done = i + len(chunk)
        if done % (batch * 20) == 0 or done == len(todo):
            rate = done / max(0.001, time.time() - started)
            remaining = (len(todo) - done) / max(0.001, rate)
            print(f"  {done}/{len(todo)} ({rate:.1f}/s, ~{remaining / 60:.0f} min left)")

    return cache


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate the sentences into Bulgarian")
    ap.add_argument("--limit", type=int,
                    help="stop after this many DISTINCT sentences")
    ap.add_argument("--batch", type=int, default=32, help="sentences per batch")
    args = ap.parse_args()

    if not os.path.exists(SENTENCES_JSON):
        print(f"ERROR: missing {SENTENCES_JSON} - run 05_build_sentences.py first")
        return 1

    with open(SENTENCES_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data["sentences"] if isinstance(data, dict) else data

    # The sentences that need a Bulgarian translation: short, with an
    # English one, and without a Bulgarian one already.
    wanted: list[str] = []
    seen: set[str] = set()
    for e in entries:
        zh = e.get("zh") or ""
        if not zh or len(zh) > MAX_SENTENCE_CHARS:
            continue
        if e.get("translations_bg"):
            continue
        en_list = e.get("translations_en") or []
        if not en_list:
            continue
        en = en_list[0].strip()
        if not en or en in seen:
            continue
        seen.add(en)
        wanted.append(en)

    print(f"short sentences needing a Bulgarian translation: {len(wanted):,}")
    if args.limit:
        wanted = wanted[:args.limit]
        print(f"  limited to {len(wanted):,}")

    cache = load_cache(CACHE)
    todo = [t for t in wanted if t not in cache]
    print(f"  already in the cache: {len(wanted) - len(todo):,}")
    print(f"  to translate: {len(todo):,}")

    if todo:
        cache = translate(todo, cache, args.batch)

    # Fill the translations in. A sentence with several English
    # translations gets the Bulgarian one that matches the first.
    filled = 0
    for e in entries:
        if e.get("translations_bg"):
            continue
        en_list = e.get("translations_en") or []
        if not en_list:
            continue
        bg = cache.get(en_list[0].strip())
        # A translation that is not clean enough to teach from is
        # dropped rather than shown: see is_usable().
        if bg and is_usable(bg):
            e["translations_bg"] = [bg]
            filled += 1

    with open(SENTENCES_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    total_bg = sum(1 for e in entries if e.get("translations_bg"))
    print()
    print(f"SUMMARY 12_translate_sentences: filled={filled:,} "
          f"total_with_bg={total_bg:,} -> {SENTENCES_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

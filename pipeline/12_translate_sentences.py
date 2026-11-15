"""Translate the short study sentences into Bulgarian.

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

THE MODEL

The model is chosen with --model. The default is facebook/m2m100_418M
(MIT); facebook/nllb-200-distilled-600M (CC-BY-NC-4.0) is still
selectable but must not be used for a release that is sold. The
sentences are shipped inside the app, so the licence of the model is
part of the licence of the app.

THE CACHE

The translation goes through the same kind of sense cache as
07_translate_bulgarian.py: English sentence -> Bulgarian sentence, in
data/bg_sentence_cache.json -- one file per model, because the cached
translations are the model's own output. The English sentences repeat
a lot across the corpus, so the cache saves a great deal of work: the
first pass translates the distinct sentences, and every later
occurrence is free.

Usage:
    python pipeline/12_translate_sentences.py
    python pipeline/12_translate_sentences.py --limit 200
    python pipeline/12_translate_sentences.py --model m2m100_418M
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
from _guards import set_allow_degraded  # noqa: E402
from _translation_model import (  # noqa: E402
    Translator,
    cache_path,
    load_cache,
    load_or_migrate_cache,
    record_provenance,
    resolve_model,
    save_cache,
)

SENTENCES_JSON = os.path.join(DATA, "sentences.json")
# One cache file per model: the cached translations are the model's own
# output, so two models must not share one.
CACHE_BASE = os.path.join(DATA, "bg_sentence_cache.json")

# The model that wrote the corpus before the model became a choice. The
# entries it wrote are marked with it, so a model switch replaces them
# and leaves the human translations alone.
LEGACY_MODEL = "nllb-200-distilled-600M"

# The longest sentence the model takes.
MAX_TOKENS = 128

# Sentences longer than this are not word-order material.
MAX_SENTENCE_CHARS = 12


def classify_legacy(entry: dict, legacy_outputs: set[str]) -> None:
    """Mark the entries that a previous, unmarked run wrote.

    Before the model became a choice, the sentences file carried no
    marker: a Bulgarian translation was just a Bulgarian translation.
    The machine-made ones are recognisable -- their text is in the old
    cache -- so they are marked here rather than being passed off as
    human translations that would never be replaced.

    The old cache was written by NLLB-200, so that is the model they
    are attributed to.
    """
    if entry.get("translations_bg_source"):
        return
    bg = entry.get("translations_bg") or []
    if not bg:
        return
    if bg[0] in legacy_outputs:
        entry["translations_bg_source"] = "machine"
        entry["translations_bg_model"] = LEGACY_MODEL
    else:
        # Not in the old cache: this translation did not come from the
        # model, so it is somebody's -- a Bulgarian speaker on Tatoeba.
        # Marking it says so, and says that no model switch may touch
        # it.
        entry["translations_bg_source"] = "human"


def needs_retranslation(entry: dict, spec) -> bool:
    """True when the Bulgarian in this entry must be translated again.

    There are two kinds of Bulgarian in the corpus:

      * a HUMAN translation from Tatoeba. It is somebody's work and it
        stays, whatever model is used.
      * a MACHINE translation from a previous run. It belongs to the
        model that wrote it, and when the model changes it has to be
        written again -- otherwise the corpus quietly mixes two
        translation styles, and the app ships text that no model in
        the pipeline produced.

    >>> import sys; sys.path.insert(0, ".")
    >>> from _translation_model import resolve_model
    >>> spec = resolve_model("m2m100_418M")
    >>> needs_retranslation({"translations_bg": ["Не е правилно."],
    ...                      "translations_bg_source": "human"}, spec)
    False
    >>> needs_retranslation({"translations_bg": ["Грешно."],
    ...                      "translations_bg_source": "machine",
    ...                      "translations_bg_model": "nllb-200-distilled-600M"}, spec)
    True
    >>> needs_retranslation({"translations_bg": ["Грешно."],
    ...                      "translations_bg_source": "machine",
    ...                      "translations_bg_model": "m2m100_418M"}, spec)
    False
    """
    if not entry.get("translations_bg"):
        return False
    if entry.get("translations_bg_source") != "machine":
        return False
    return entry.get("translations_bg_model") != spec.name


def is_usable(text: str) -> bool:
    """True when a machine translation is clean enough to teach from.

    The word-order mode shows the Bulgarian sentence as the thing the
    learner is aiming at, and the learner rebuilds the Chinese to
    match it. A wrong Bulgarian sentence is not a slightly imperfect
    exercise -- it teaches the wrong meaning.

    The model makes three kinds of mess on short sentences, and all
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


# The cache helpers are shared with the other translation steps, so
# every step treats a cache the same way.


def translate(
    texts: list[str],
    cache: dict[str, str],
    batch: int,
    spec,
) -> dict[str, str]:
    """Translate the texts that are not in the cache yet."""
    todo = [t for t in dict.fromkeys(texts) if t not in cache]
    if not todo:
        return cache

    print(f"loading {spec.model_id} ...")
    translator = Translator(spec)
    print(f"  licence: {spec.license} ({spec.license_url})")
    print(f"  device: cpu, threads: {translator.threads}")

    started = time.time()

    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        decoded = translator.translate(
            chunk, max_new_tokens=MAX_TOKENS, batch_size=batch
        )
        for source, out in zip(chunk, decoded):
            cache[source] = out.strip()
        # The cache is written after every batch, so a run that is
        # killed keeps the work it already did.
        save_cache(cache_path(CACHE_BASE, spec), cache)

        done = i + len(chunk)
        if done % (batch * 20) == 0 or done == len(todo):
            rate = done / max(0.001, time.time() - started)
            remaining = (len(todo) - done) / max(0.001, rate)
            print(f"  {done}/{len(todo)} ({rate:.1f}/s, "
                  f"~{remaining / 60:.0f} min left)")

    return cache


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate the sentences into Bulgarian")
    ap.add_argument("--limit", type=int,
                    help="stop after this many DISTINCT sentences")
    ap.add_argument("--batch", type=int, default=32, help="sentences per batch")
    ap.add_argument("--model", help="the translation model; the default is "
                                   "the permissive one (MIT)")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="carry on when an input is missing")
    args = ap.parse_args()

    if args.allow_degraded:
        set_allow_degraded()

    spec = resolve_model(args.model)
    print(f"model: {spec.model_id} ({spec.license}) -- {spec.note}")

    if not os.path.exists(SENTENCES_JSON):
        print(f"ERROR: missing {SENTENCES_JSON} - run 05_build_sentences.py first")
        return 1

    with open(SENTENCES_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data["sentences"] if isinstance(data, dict) else data

    # Mark the entries the old, unmarked run wrote, BEFORE the list of
    # texts to translate is built.
    #
    # The order matters. needs_retranslation() can only recognise a
    # machine translation that has been marked, and the marking is what
    # says "this text belongs to another model and has to be written
    # again". Building the list first skipped every unmarked entry, so
    # the sentences the old model wrote were never queued -- they would
    # have kept their CC-BY-NC Bulgarian for ever.
    legacy_outputs = set(load_cache(CACHE_BASE).values())
    for e in entries:
        classify_legacy(e, legacy_outputs)

    # The sentences that need a Bulgarian translation: short, with an
    # English one, and either without a Bulgarian one or with one that
    # another model wrote.
    wanted: list[str] = []
    seen: set[str] = set()
    for e in entries:
        zh = e.get("zh") or ""
        if not zh or len(zh) > MAX_SENTENCE_CHARS:
            continue
        if e.get("translations_bg") and not needs_retranslation(e, spec):
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

    cache, adopted = load_or_migrate_cache(CACHE_BASE, spec)
    if adopted:
        print(f"  adopted the old cache: it was {spec.name}'s work")

    todo = [t for t in wanted if t not in cache]
    print(f"  already in the cache: {len(wanted) - len(todo):,}")
    print(f"  to translate: {len(todo):,}")

    if todo:
        cache = translate(todo, cache, args.batch, spec)

    # Fill the translations in. A sentence with several English
    # translations gets the Bulgarian one that matches the first.
    filled = 0
    for e in entries:
        if e.get("translations_bg") and not needs_retranslation(e, spec):
            continue
        en_list = e.get("translations_en") or []
        if not en_list:
            # There is no English to translate from, so the current
            # model cannot write this one -- and the previous model's
            # text has to go with it, exactly as below.
            if e.get("translations_bg_source") == "machine":
                e.pop("translations_bg", None)
                e.pop("translations_bg_source", None)
                e.pop("translations_bg_model", None)
            continue
        bg = cache.get(en_list[0].strip())
        # A translation that is not clean enough to teach from is
        # dropped rather than shown: see is_usable().
        if bg and is_usable(bg):
            e["translations_bg"] = [bg]
            # The marker says who wrote this, so a later model switch
            # knows to replace it and a human translation is left
            # alone.
            e["translations_bg_source"] = "machine"
            e["translations_bg_model"] = spec.name
            filled += 1
        elif e.get("translations_bg_source") == "machine":
            # The current model cannot translate this one, so the
            # previous model's Bulgarian goes too: it may be licensed
            # CC-BY-NC, and the app must not ship it. The sentence
            # falls back to its English translation, which the word
            # order mode already handles.
            e.pop("translations_bg", None)
            e.pop("translations_bg_source", None)
            e.pop("translations_bg_model", None)

    with open(SENTENCES_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    total_bg = sum(1 for e in entries if e.get("translations_bg"))
    # The total, not the number filled in THIS run: a run that finds
    # everything in the cache translated nothing, and recording zero
    # would say the dataset is empty.
    record_provenance("sentences", spec, total_bg)
    print()
    print(f"SUMMARY 12_translate_sentences: filled={filled:,} "
          f"total_with_bg={total_bg:,} -> {SENTENCES_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Translate the grammar points into Bulgarian with NLLB-200.

Input:
    data/grammar.json         the grammar points (04_build_grammar.py)

Output:
    data/grammar.json         the same file, with the Bulgarian fields
                              filled in:
                                title_bg    the Bulgarian title
                                summary_bg  the Bulgarian summary
                                examples[].bg  the Bulgarian gloss of the
                                              example sentence

WHY THIS EXISTS

The app is for Bulgarian learners of Chinese, and the grammar screen was
entirely in English: 506 of 506 grammar points had an empty `title_bg`,
so the screen fell back to the English title. The grammar quiz was in
English too -- the learner was asked to match a Chinese sentence to an
English meaning, in an app whose whole premise is learning Chinese FROM
Bulgarian. That is the wall the learner hits at the grammar tab.

WHAT IS TRANSLATED

Three things, in this order of value:

  1. The TITLE of every grammar point -- the one-line name the learner
     scrolls through. 506 of them.
  2. The SUMMARY -- the first paragraph of the wiki page. 505 of them.
  3. The GLOSS of every example sentence -- 3 239 of them. These become
     the options of the grammar quiz.

The example glosses are the most valuable of the three, because they
turn the grammar quiz from an English exercise into a Bulgarian one.

WHAT IS NOT TRANSLATED

The Chinese characters, the pinyin and the body of the wiki page stay
as they are. The body is a long article with wiki markup that the model
would mangle; the Chinese and the pinyin are the lesson, not the
translation. The English title and summary are kept in the database as
well: they are the source of the translation, and they are useful to a
learner who gets stuck.

THE CACHE

The translation goes through the same kind of sense cache as
07_translate_bulgarian.py: English text -> Bulgarian text, in
data/bg_grammar_cache.json. A re-run after a change to the English only
translates what is new, so the work is never repeated and a run that is
killed halfway keeps what it already did.

Usage:
    python pipeline/11_translate_grammar.py
    python pipeline/11_translate_grammar.py --limit 50   # a quick check
    python pipeline/11_translate_grammar.py --titles-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW  # noqa: E402

GRAMMAR_JSON = os.path.join(DATA, "grammar.json")
CACHE = os.path.join(DATA, "bg_grammar_cache.json")
SYLLABLES_JSON = os.path.join(RAW, "pinyin_syllables.json")

MODEL_ID = "facebook/nllb-200-distilled-600M"
SOURCE_LANG = "eng_Latn"
TARGET_LANG = "bul_Cyrl"

# The model can only translate so much at once. 512 tokens is enough for
# a wiki summary.
MAX_TOKENS = 256

# The parts of the English that must survive the translation: the
# Chinese character and its pinyin, which name the grammar point
# itself. "Use 没有 (méiyǒu) to negate past actions" has to keep
# 没有 and méiyǒu.
#
# The model does NOT keep them on its own -- it transliterates "tai"
# into "тай" -- so they are masked before the translation and restored
# after it.
import re

# A quoted term: "tai", "excessively", "-bu dong".
_QUOTED = re.compile(r'"([^"]{1,60})"')
# A run of Chinese characters.
_CJK = re.compile(r"[一-鿿]+")
# A pinyin word: latin letters with an accent on one of them. The
# corpus uses the PRECOMPOSED letters (e, o with a caron), not the
# combining marks, so both have to be matched.
_TONED = re.compile(
    "[A-Za-z\u00c0-\u024f]*"
    "[\u00c0-\u024f\u0300-\u036f]"
    "[A-Za-z\u00c0-\u024f\u0300-\u036f]*"
)
# A plain latin word, for the echo check.
_LATIN_WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")


def _protected_parts(text: str) -> list[str]:
    """The Chinese characters and pinyin words in an English text."""
    parts = _CJK.findall(text)
    for match in _PINYIN.finditer(text):
        word = match.group(0)
        # A pinyin syllable next to a Chinese character is part of the
        # grammar point's name. A plain English word is not.
        if len(word) >= 2 and (word != word.lower() or any(
            ord(ch) > 0x300 for ch in word
        ) or _has_tone_mark(word)):
            parts.append(word)
    return parts


def _has_tone_mark(word: str) -> bool:
    return any(0x300 <= ord(ch) <= 0x36F for ch in word)


def _syllables() -> set[str]:
    """The Mandarin syllables, for telling a pinyin term from an English one."""
    try:
        with open(SYLLABLES_JSON, encoding="utf-8") as fh:
            return {k.lower() for k in json.load(fh).keys()}
    except (OSError, ValueError):
        return set()


def _segment(word: str, syllables: set[str]) -> list[str] | None:
    """Split a word into Mandarin syllables, or None if it is not one.

    The segmentation is a dynamic program over the syllable inventory,
    longest piece first, so "meiyou" becomes ["mei", "you"] and not
    ["m", "ei", "you"].

    >>> syl = {"tai", "mei", "you", "bu", "dong"}
    >>> _segment("tai", syl)
    ['tai']
    >>> _segment("meiyou", syl)
    ['mei', 'you']
    >>> _segment("excessively", syl) is None
    True
    """
    word = word.lower()
    if not word:
        return None
    longest = max((len(s) for s in syllables), default=0)
    if not longest:
        return None
    # dp[i] is the segmentation of word[i:]; None means it cannot be
    # segmented.
    dp: list[list[str] | None] = [None] * (len(word) + 1)
    dp[len(word)] = []
    for i in range(len(word) - 1, -1, -1):
        for length in range(min(longest, len(word) - i), 0, -1):
            piece = word[i:i + length]
            if piece in syllables and dp[i + length] is not None:
                dp[i] = [piece] + dp[i + length]
                break
    return dp[0]


def _is_pinyin_term(term: str, syllables: set[str]) -> bool:
    """True when a quoted term is a Mandarin reading rather than English.

    "tai", "meiyou" and "-bu dong" are readings; "excessively" and
    "a bit too" are English. A term counts as a reading when every one
    of its parts -- split on spaces and hyphens -- segments into
    Mandarin syllables.

    The test has to be the real inventory and a real segmentation: a
    single syllable lookup misses "meiyou", which is two syllables
    written together, and a lenient split would accept English words
    that happen to be made of syllable-shaped letters.

    >>> syl = {"tai", "mei", "you", "bu", "dong"}
    >>> _is_pinyin_term("tai", syl)
    True
    >>> _is_pinyin_term("meiyou", syl)
    True
    >>> _is_pinyin_term("-bu dong", syl)
    True
    >>> _is_pinyin_term("excessively", syl)
    False
    >>> _is_pinyin_term("a bit too", syl)
    False
    """
    if not syllables:
        return False
    parts = [p for p in re.split(r"[\s\-]+", term.strip().lower()) if p]
    if not parts:
        return False
    return all(_segment(part, syllables) is not None for part in parts)


def mask(text: str, syllables: set[str]) -> tuple[str, dict[str, str]]:
    """Replace the Chinese terms with placeholders.

    The model transliterates the Chinese terms it is given: "tai" comes
    back as "тай". So the terms are replaced by placeholders before the
    translation and put back after it.

    Three kinds of term are protected:
      * a quoted term that is a Mandarin syllable ("tai", "meiyou") --
        the grammar point's own name, which must not be translated;
      * a word with a tone mark in it ("méiyǒu") -- unmistakably pinyin;
      * a run of Chinese characters ("没有") -- the lesson itself.

    The English words in the same title ("excessively") are NOT masked:
    they are what the learner needs translated.

    Returns the masked text and the map from placeholder to the term it
    stands for. The same term always gets the same placeholder, so the
    model sees a consistent sentence.
    """
    terms: dict[str, str] = {}

    def placeholder(term: str) -> str:
        for name, value in terms.items():
            if value == term:
                return name
        name = f"TERM{len(terms) + 1}"
        terms[name] = term
        return name

    def mask_quoted(match: re.Match) -> str:
        term = match.group(1)
        if _is_pinyin_term(term, syllables):
            return '"' + placeholder(term) + '"'
        return match.group(0)

    masked = _QUOTED.sub(mask_quoted, text)
    masked = _CJK.sub(lambda m: placeholder(m.group(0)), masked)
    masked = _TONED.sub(lambda m: placeholder(m.group(0)), masked)
    return masked, terms


def unmask(text: str, terms: dict[str, str]) -> str:
    """Put the Chinese terms back.

    A placeholder the model dropped is appended rather than lost: a
    missing character is visible and can be fixed, an invisible one
    teaches the learner the wrong thing.
    """
    for name, term in terms.items():
        if name in text:
            text = text.replace(name, term)
        else:
            text = text.rstrip() + " " + term
    return text


def strip_echo(text: str, source: str) -> str:
    """Remove the English word the model echoes back at the end.

    NLLB sometimes appends the first word of the source: "Expressing
    "excessively" with "tai"" comes back as 'Изразяване на "прекалено"
    с "тай" Expressing'. The trailing "Expressing" is noise.
    """
    source_words = _LATIN_WORD.findall(source)
    if not source_words:
        return text
    first = source_words[0]
    out_words = text.rsplit(" ", 1)
    if len(out_words) != 2:
        return text
    if out_words[1].strip().strip('",.;').lower() == first.lower():
        return out_words[0].rstrip()
    return text


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
    """Write the cache atomically.

    A run that is killed halfway must not leave a half-written cache
    behind: the old cache stays valid and the work is simply redone.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def translate(texts: list[str], cache: dict[str, str], batch: int) -> dict[str, str]:
    """Translate the texts that are not in the cache yet."""
    todo = [t for t in dict.fromkeys(texts) if t not in cache]
    if not todo:
        return cache

    syllables = _syllables()
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
        masked_texts = []
        terms_per_text = []
        for source in chunk:
            masked, terms = mask(source, syllables)
            masked_texts.append(masked)
            terms_per_text.append(terms)

        tokenizer.src_lang = SOURCE_LANG
        encoded = tokenizer(
            masked_texts, return_tensors="pt", padding=True, truncation=True,
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
        for source, out, terms in zip(chunk, decoded, terms_per_text):
            text = unmask(out.strip(), terms)
            cache[source] = strip_echo(text, source)
        # The cache is written after every batch, so a run that is
        # killed keeps the work it already did.
        save_cache(CACHE, cache)

        done = i + len(chunk)
        if done % (batch * 10) == 0 or done == len(todo):
            rate = done / max(0.001, time.time() - started)
            remaining = (len(todo) - done) / max(0.001, rate)
            print(f"  {done}/{len(todo)} ({rate:.1f}/s, ~{remaining / 60:.0f} min left)")

    return cache


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate the grammar into Bulgarian")
    ap.add_argument("--limit", type=int, help="only translate this many texts")
    ap.add_argument("--batch", type=int, default=8,
                    help="texts per batch (the summaries are long)")
    ap.add_argument("--titles-only", action="store_true",
                    help="translate only the titles, not the summaries "
                         "or the example glosses")
    ap.add_argument("--examples-only", action="store_true",
                    help="translate only the example glosses")
    args = ap.parse_args()

    if not os.path.exists(GRAMMAR_JSON):
        print(f"ERROR: missing {GRAMMAR_JSON} - run 04_build_grammar.py first")
        return 1

    with open(GRAMMAR_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data["entries"] if isinstance(data, dict) else data

    # Collect the texts to translate.
    titles = [e.get("title") or "" for e in entries]
    summaries = [(e.get("summary") or "") for e in entries]
    examples: list[str] = []
    for e in entries:
        for ex in (e.get("examples") or []):
            if isinstance(ex, dict):
                en = (ex.get("en") or "").strip()
                if en:
                    examples.append(en)

    if args.titles_only:
        summaries = []
        examples = []
    if args.examples_only:
        titles = []
        summaries = []

    wanted = titles + [s for s in summaries if s] + examples
    wanted = [t for t in wanted if t]
    if args.limit:
        wanted = wanted[:args.limit]
    print(f"texts to consider: {len(wanted):,}")

    cache = load_cache(CACHE)
    todo = [t for t in dict.fromkeys(wanted) if t not in cache]
    print(f"  already in the cache: {len(wanted) - len(todo):,}")
    print(f"  to translate: {len(todo):,}")

    if todo:
        cache = translate(todo, cache, args.batch)

    # Fill the Bulgarian fields in.
    n_titles = n_summaries = n_examples = 0
    for e in entries:
        title = e.get("title") or ""
        if title and title in cache:
            e["title_bg"] = cache[title]
            n_titles += 1

        summary = e.get("summary") or ""
        if summary and summary in cache:
            e["summary_bg"] = cache[summary]
            n_summaries += 1

        for ex in (e.get("examples") or []):
            if not isinstance(ex, dict):
                continue
            en = (ex.get("en") or "").strip()
            if en and en in cache:
                ex["bg"] = cache[en]
                n_examples += 1

    with open(GRAMMAR_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    print()
    print(f"SUMMARY 11_translate_grammar: titles={n_titles} summaries={n_summaries} "
          f"examples={n_examples} -> {GRAMMAR_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

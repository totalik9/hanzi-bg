"""Read the HSK lists of levels 2, 3 and 4, and write the word lists.

    python pipeline/_build_hsk_levels.py

It writes three files into the scratch directory:

    hsk2_words.json   hsk3_words.json   hsk4_words.json

Each is a list of the words of that level:

    {"hanzi": "万", "pinyin": "wàn",
     "hsk_meaning": "ten thousand; a huge number",
     "bg_machine": "10 хиляди / Голямо число",
     "bg_source": "machine",
     "pos": ""}

WHY THIS FILE EXISTS

The scripts that DRAFT the HSK 2-4 path -- `assign_themes.py` and
`build_lessons.py` -- read those three files. They were written by
hand in a scratch directory, which is a thing that works exactly once:
a fresh clone has no `hsk2_words.json`, and the scripts that need it
say "ERROR: missing ...". So the step that produces them is written
down here, where it can be run again.

THE SOURCE IS THE CORPUS

The words of a level are the words the CORPUS puts in that level --
`data/vocab_hsk.json`, built by `03_build_vocab.py` from the official
HSK lists. The corpus already resolves the question the level files
leave open: the official lists repeat a word in every level it
appears in (啊 is in the files of levels 2, 3 and 4), and the corpus
gives every word the LOWEST level it appears in, because that is the
level it is taught at.

Measured on the shipped corpus: 300 words in level 1, 197 in level 2,
491 in level 3 and 990 in level 4 -- 1678 words for levels 2 to 4,
which is exactly the number of words of the path.

The English meaning is the English gloss of the corpus, cleaned: the
gloss explains itself in parentheses ("(of a person) short"), and a
gloss has to be short. The Bulgarian is the machine translation of the
corpus, carried along so that the scripts that group the words can
see what each word MEANS -- the machine translation is not fit to
teach, but it is a good enough hint to group by.

THE WORD LIST IS A DRAFT, NOT THE PATH

The path is `curriculum/12_hsk2to4.json`, and it is hand-maintained
in version control. These lists only feed the scripts that DRAFT a
path; see `build_lessons.py` for why a draft never overwrites the
committed file.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
TMP = os.environ.get("TMPDIR", ROOT)

#: The levels of the path that follow HSK 1.
LEVELS = ("2", "3", "4")


def load_vocabulary() -> dict[str, dict]:
    """Every word of the corpus, by its characters."""
    path = os.path.join(DATA, "vocab_hsk.json")
    if not os.path.exists(path):
        raise SystemExit(
            f"ERROR: missing {path} - run pipeline/03_build_vocab.py")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    words = data.get("words") if isinstance(data, dict) else data
    return {w["hanzi"]: w for w in words if w.get("hanzi")}


def load_translations() -> dict[str, dict]:
    """The Bulgarian of every word of the corpus."""
    path = os.path.join(DATA, "bg_translations.json")
    if not os.path.exists(path):
        print(f"  NOTE: {path} is not built, so the Bulgarian is empty")
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def clean_meaning(meaning: str) -> str:
    """The sense, without the dictionary explaining itself.

    The parenthetical of an English gloss is a note to the reader
    ("(of a person) short"), not part of the meaning, and a gloss has
    to be short. The part before the parenthesis is the sense.
    """
    meaning = (meaning or "").strip()
    if "(" in meaning:
        meaning = meaning[:meaning.index("(")].strip()
    return meaning.rstrip(";").strip()


def main() -> int:
    vocabulary = load_vocabulary()
    translations = load_translations()

    total = 0
    for level in LEVELS:
        words: list[dict] = []
        for hanzi, word in vocabulary.items():
            if str(word.get("hsk_level") or "") != level:
                continue
            translation = translations.get(hanzi) or {}
            words.append({
                "hanzi": hanzi,
                "pinyin": word.get("pinyin") or "",
                "hsk_meaning": clean_meaning(word.get("gloss_en") or ""),
                "bg_machine": (translation.get("gloss") or "").strip(),
                "bg_source": translation.get("source") or "",
                "pos": word.get("pos") or "",
            })
        out = os.path.join(TMP, f"hsk{level}_words.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(words, fh, ensure_ascii=False, indent=1)
        with_bulgarian = sum(1 for w in words if w["bg_machine"])
        print(f"   level {level}: {len(words):4} words, {with_bulgarian:4} "
              f"with Bulgarian -> {out}")
        total += len(words)
    print(f"   {total} words in {len(LEVELS)} levels")
    return 0


if __name__ == "__main__":
    sys.exit(main())

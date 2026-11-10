"""Build data/sentences.json from the Tatoeba Chinese (cmn) corpus.

Inputs (all CC BY 2.0 FR, Tatoeba):
    data/raw/cmn_sentences.tsv            Chinese sentences
    data/raw/cmn_links_eng.tsv            Chinese -> English sentence links
    data/raw/cmn_links_bul.tsv            Chinese -> Bulgarian sentence links
    data/raw/bul_sentences.tsv            Bulgarian sentences
    data/raw/cmn_sentences_with_audio.tsv sentence id -> audio id
    data/raw/cmn_transcriptions.tsv       sentence id -> pinyin transcription
    data/raw/sentences_with_audio.csv     global audio index
    data/hanzi.db                         dictionary built by 02_build_dictionary.py

Output: data/sentences.json
    {
      "meta": {...},
      "sentences": [ {id, zh, pinyin, translations_en[], translations_bg[],
                      audio_url, license}, ... ]
    }

Only sentences whose Chinese text is fully covered by the dictionary are
kept, so every sentence has a pinyin reading.

Usage:
    python pipeline/05_build_sentences.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import (  # noqa: E402
    DATA,
    RAW,
    is_hanzi,
    sentence_pinyin,
    split_pinyin_by_chars,
    split_pinyin_syllables,
    tone_marked_to_number,
)

DB_PATH = os.path.join(DATA, "hanzi.db")
OUT = os.path.join(DATA, "sentences.json")

TATOEBA_LICENSE = "CC BY 2.0 FR (Tatoeba)"
# audio files are contributed by individual users and carry their own licences
AUDIO_LICENSE = "Tatoeba audio, per-contributor licence (CC BY 2.0 FR or similar)"

# a Chinese sentence is plausible if it is mostly Han characters
HANZI_RE = re.compile(r"[一-鿿㐀-䶿]")


def load_sentences(path: str) -> dict[int, str]:
    """Load `id<TAB>lang<TAB>text` rows into {id: text}."""
    out: dict[int, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            try:
                sid = int(parts[0])
            except ValueError:
                continue
            out[sid] = parts[2]
    return out


def load_links(path: str) -> dict[int, list[int]]:
    """Load `id<TAB>translation_id` rows into {id: [translation_id, ...]}."""
    out: dict[int, list[int]] = defaultdict(list)
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                out[int(parts[0])].append(int(parts[1]))
            except ValueError:
                continue
    return out


def load_audio_ids(path: str) -> dict[int, int]:
    """Load `sentence_id<TAB>audio_id` rows into {sentence_id: audio_id}."""
    out: dict[int, int] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                out[int(parts[0])] = int(parts[1])
            except ValueError:
                continue
    return out


def load_transcriptions(path: str) -> dict[int, str]:
    """Load Tatoeba's own pinyin transcriptions: {sentence_id: pinyin}.

    The file has one row per (sentence, script) pair: "Latn" holds the
    romanised pinyin, while "Hans" and "Hant" hold the Chinese text itself.
    Only the "Latn" rows are pinyin -- taking the others puts Chinese
    characters into the pinyin field.
    """
    out: dict[int, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            if parts[2] != "Latn":
                continue
            try:
                sid = int(parts[0])
            except ValueError:
                continue
            text = parts[4].strip()
            if text:
                out[sid] = text
    return out


def main() -> int:
    import sqlite3

    if not os.path.exists(DB_PATH):
        print(f"ERROR: missing {DB_PATH} - run 02_build_dictionary.py first")
        return 1

    conn = sqlite3.connect(DB_PATH)

    print("loading the dictionary character set ...")
    known: set[str] = set()
    for simp, trad in conn.execute("SELECT simplified, traditional FROM dict"):
        known.add(simp)
        known.add(trad)
    # characters that the dictionary does not have but that are common
    # function characters still appear in the corpus
    print(f"  dictionary characters: {len(known):,}")

    print("loading Tatoeba data ...")
    cmn = load_sentences(os.path.join(RAW, "cmn_sentences.tsv"))
    eng_links = load_links(os.path.join(RAW, "cmn_links_eng.tsv"))
    bul_links = load_links(os.path.join(RAW, "cmn_links_bul.tsv"))
    bul = load_sentences(os.path.join(RAW, "bul_sentences.tsv"))
    audio_ids = load_audio_ids(os.path.join(RAW, "cmn_sentences_with_audio.tsv"))
    transcriptions = load_transcriptions(os.path.join(RAW, "cmn_transcriptions.tsv"))
    print(f"  chinese sentences: {len(cmn):,}")
    print(f"  english links: {len(eng_links):,}  bulgarian links: {len(bul_links):,}")
    print(f"  bulgarian sentences: {len(bul):,}")
    print(f"  sentences with audio: {len(audio_ids):,}")
    print(f"  sentences with a tatoeba pinyin transcription: {len(transcriptions):,}")

    # English sentence texts: the per-language export only has Chinese, so the
    # English text is fetched from Tatoeba's per-language English file
    print("loading English sentence texts ...")
    eng_sentences = load_sentences(
        os.path.join(RAW, "eng_sentences.tsv")
    )
    if not eng_sentences:
        print("  WARNING: eng_sentences.tsv missing - English texts will be omitted")
    print(f"  english sentences: {len(eng_sentences):,}")

    # the pinyin for a sentence comes from Tatoeba's own transcription when it
    # exists, otherwise it is built from the per-character readings
    char_readings: dict[str, list[str]] = {}
    cr_path = os.path.join(RAW, "char_readings.json")
    if os.path.exists(cr_path):
        with open(cr_path, encoding="utf-8") as fh:
            char_readings = json.load(fh)

    print("filtering sentences ...")
    entries = []
    not_covered = 0
    no_hanzi = 0
    for sid, text in cmn.items():
        if not HANZI_RE.search(text):
            no_hanzi += 1
            continue
        # every Han character in the sentence must be in the dictionary
        if any(c not in known for c in text if is_hanzi(c)):
            not_covered += 1
            continue

        pinyin = sentence_pinyin(text, transcriptions.get(sid), char_readings)

        translations_en = []
        for tid in eng_links.get(sid, []):
            t = eng_sentences.get(tid)
            if t:
                translations_en.append(t)

        translations_bg = []
        for tid in bul_links.get(sid, []):
            t = bul.get(tid)
            if t:
                translations_bg.append(t)

        audio_url = ""
        aid = audio_ids.get(sid)
        if aid:
            audio_url = f"https://tatoeba.org/audio/download/{aid}"

        entries.append({
            "id": sid,
            "zh": text,
            "pinyin": pinyin,
            "translations_en": translations_en,
            "translations_bg": translations_bg,
            "audio_url": audio_url,
            "license": TATOEBA_LICENSE,
            "audio_license": AUDIO_LICENSE if audio_url else "",
        })

    # shortest sentences first: they are the best study material
    entries.sort(key=lambda e: (len(e["zh"]), e["id"]))

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "Tatoeba Chinese (cmn) sentences",
        "source_url": "https://tatoeba.org/en/downloads",
        "license": TATOEBA_LICENSE,
        "audio_license": AUDIO_LICENSE,
        "total_chinese_sentences": len(cmn),
        "kept": len(entries),
        "dropped_no_hanzi": no_hanzi,
        "dropped_not_in_dictionary": not_covered,
        "with_english_translation": sum(1 for e in entries if e["translations_en"]),
        "with_bulgarian_translation": sum(1 for e in entries if e["translations_bg"]),
        "with_audio": sum(1 for e in entries if e["audio_url"]),
        "pinyin_source": "Tatoeba transcriptions, else per-character pinyin-data readings",
        "note": (
            "Only sentences whose Chinese characters are all covered by "
            "CC-CEDICT are kept, so every sentence can be given a pinyin reading."
        ),
    }

    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "sentences": entries}, fh, ensure_ascii=False, indent=1)

    print("\nsample sentences:")
    for e in entries[:5]:
        print(f"   [{e['id']}] {e['zh']}")
        print(f"        pinyin: {e['pinyin']}")
        if e["translations_en"]:
            print(f"        en: {e['translations_en'][0][:70]}")
        if e["translations_bg"]:
            print(f"        bg: {e['translations_bg'][0][:70]}")

    print("\nsample sentences with Bulgarian translations:")
    bg_entries = [e for e in entries if e["translations_bg"]][:5]
    for e in bg_entries:
        print(f"   [{e['id']}] {e['zh']}  ->  {e['translations_bg'][0]}")

    print()
    print(f"SUMMARY 05_build_sentences: sentences={len(entries)} out={OUT}")
    print(f"   with_en={meta['with_english_translation']} "
          f"with_bg={meta['with_bulgarian_translation']} "
          f"with_audio={meta['with_audio']}")
    print(f"   dropped_not_in_dictionary={not_covered} dropped_no_hanzi={no_hanzi}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

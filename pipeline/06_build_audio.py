"""Generate pronunciation audio with Microsoft Edge TTS (data/audio/*.mp3).

Inputs:
    data/vocab_hsk.json     the graded HSK vocabulary (from 03_build_vocab.py)
    data/sentences.json     the Tatoeba corpus (from 05_build_sentences.py)

Output:
    data/audio/<name>.mp3   one file per spoken text
    data/audio/manifest.json  {filename: text} for every generated clip

File names are CONTENT-ADDRESSED: the sanitised text plus the first 12 hex
digits of its SHA-1. The same text therefore always maps to the same file,
which means the script can be re-run over a growing vocabulary without
regenerating what already exists, and the same word spoken in two lessons
costs one file instead of two.

The app reads the clips from the APK's assets under "audio/<name>.mp3", so
the file name must survive a round trip through the APK unchanged: only
ASCII letters, digits and underscores are kept.

Usage:
    python pipeline/06_build_audio.py                 # everything
    python pipeline/06_build_audio.py --level 1        # one HSK level
    python pipeline/06_build_audio.py --limit 100      # first N words
    python pipeline/06_build_audio.py --no-sentences   # words only
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA  # noqa: E402

AUDIO_DIR = os.path.join(DATA, "audio")
VOCAB_JSON = os.path.join(DATA, "vocab_hsk.json")
SENTENCES_JSON = os.path.join(DATA, "sentences.json")
MANIFEST = os.path.join(AUDIO_DIR, "manifest.json")

# Edge TTS voice. Xiaoxiao is the standard mainland-Chinese female voice.
VOICE = "zh-CN-XiaoxiaoNeural"

# The text is spoken, so it must not contain characters the voice would
# read out or choke on. CJK punctuation is dropped; latin text and digits
# are kept because a lesson may legitimately mix them.
_STRIP = re.compile(r"[\s\u3000-\u303f\uff00-\uffef!-/:-@\[-`{-~]+")
_NON_SPEAKABLE = re.compile(r"[^一-鿿a-zA-Z0-9üÜà-ÿ\s]")

# Sentences above this length are skipped: the cost of the TTS request
# grows with the text, and a 40-character sentence is not study material.
MAX_SENTENCE_CHARS = 24

# A single TTS request must finish within this many seconds. edge-tts
# sometimes leaves the stream open instead of ending it, and one such
# request used to stop the whole run.
REQUEST_TIMEOUT = 30


def sanitize(text: str) -> str:
    """Reduce a text to the characters that will actually be spoken."""
    # Drop everything that is not a CJK ideograph, a latin letter or a
    # digit, then collapse the whitespace.
    cleaned = _NON_SPEAKABLE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def filename_for(text: str, label: str = "") -> str:
    """Content-addressed file name for a spoken text.

    The readable prefix helps when browsing the asset folder by hand; the
    hash makes the name unique and stable. The prefix comes from the
    pinyin, because the Chinese characters themselves are not ASCII and
    would be stripped.
    """
    clean = sanitize(text)
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").lower()[:24]
    if not prefix:
        prefix = "audio"
    return f"{prefix}_{digest}.mp3"


async def synthesize(text: str, path: str, voice: str) -> bool:
    """Fetch one clip from Edge TTS. Returns True on success.

    The stream is read under a timeout: edge-tts occasionally leaves a
    request open forever instead of ending it, and without the timeout
    the whole run stops on one word.
    """
    import edge_tts

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice)
            tmp = path + ".part"
            with open(tmp, "wb") as fh:

                async def pump() -> int:
                    n = 0
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            fh.write(chunk["data"])
                            n += 1
                    return n

                written = await asyncio.wait_for(pump(), timeout=REQUEST_TIMEOUT)
            if written == 0 or os.path.getsize(tmp) == 0:
                os.remove(tmp)
                raise RuntimeError("empty audio stream")
            os.replace(tmp, path)
            return True
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if os.path.exists(path + ".part"):
                try:
                    os.remove(path + ".part")
                except OSError:
                    pass
            # Edge TTS rate-limits; back off and retry.
            await asyncio.sleep(1.5 * (attempt + 1))
    print(f"    FAILED {text!r}: {last_error}")
    return False


async def run(texts: list[tuple[str, str]], voice: str, limit: int | None) -> tuple[int, int, dict[str, str]]:
    """Synthesise every text that has no file yet."""
    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Deduplicate: the same text is spoken once no matter how often it
    # appears in the corpus.
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for text, label in texts:
        clean = sanitize(text)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        unique.append((clean, label))

    if limit:
        unique = unique[:limit]

    done = 0
    failed = 0
    spoken: dict[str, str] = {}
    for i, (text, label) in enumerate(unique, 1):
        name = filename_for(text, label)
        path = os.path.join(AUDIO_DIR, name)
        spoken[name] = text
        if os.path.exists(path) and os.path.getsize(path) > 0:
            done += 1
            continue
        ok = await synthesize(text, path, voice)
        if ok:
            done += 1
        else:
            failed += 1
        if i % 25 == 0:
            print(f"    {i}/{len(unique)} clips ({done} ok, {failed} failed)")
            await asyncio.sleep(0.2)
            # Write the manifest as we go: a run that is interrupted
            # (or stalls on one word) must still leave a manifest that
            # matches the files on disk.
            write_manifest(spoken)
    return done, failed, spoken


def collect_word_texts(level: str | None) -> list[tuple[str, str]]:
    """Return (hanzi, pinyin) pairs for the vocabulary."""
    if not os.path.exists(VOCAB_JSON):
        print(f"ERROR: missing {VOCAB_JSON} - run 03_build_vocab.py first")
        return []
    data = json.load(open(VOCAB_JSON, encoding="utf-8"))
    words = data["words"] if isinstance(data, dict) else data
    out = []
    for w in words:
        if level and str(w.get("hsk_level")) != level:
            continue
        hanzi = w.get("hanzi")
        if hanzi:
            out.append((hanzi, w.get("pinyin") or w.get("pinyin_number") or ""))
    return out


def collect_sentence_texts() -> list[tuple[str, str]]:
    """Return (zh, pinyin) pairs for the short study sentences."""
    if not os.path.exists(SENTENCES_JSON):
        print(f"ERROR: missing {SENTENCES_JSON} - run 05_build_sentences.py first")
        return []
    data = json.load(open(SENTENCES_JSON, encoding="utf-8"))
    entries = data["sentences"] if isinstance(data, dict) else data
    out = []
    for e in entries:
        zh = e.get("zh") or ""
        # Only the short sentences are worth learning to pronounce.
        if not zh or len(zh) > MAX_SENTENCE_CHARS:
            continue
        if not e.get("translations_bg"):
            # A sentence without a Bulgarian translation is study material
            # the learner cannot use yet.
            continue
        out.append((zh, e.get("pinyin") or ""))
    return out


def write_manifest(spoken: dict[str, str]) -> int:
    """Record which text each file holds, for traceability.

    The manifest is the only place that says what a file contains: the
    file name is a hash. Anything already on disk is kept, so a resumed
    run does not lose the clips it already has.
    """
    previous: dict[str, str] = {}
    if os.path.exists(MANIFEST):
        try:
            previous = json.load(open(MANIFEST, encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
    previous.update(spoken)

    # Drop entries whose file is gone, so the manifest never claims a
    # clip that is not there.
    present = {name for name in previous if os.path.exists(os.path.join(AUDIO_DIR, name))}
    previous = {name: text for name, text in previous.items() if name in present}

    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(previous, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return len(previous)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Edge TTS pronunciation clips")
    ap.add_argument("--voice", default=VOICE, help="Edge TTS voice name")
    ap.add_argument("--level", help="only this HSK level (1-6, 7-9)")
    ap.add_argument("--limit", type=int, help="stop after N clips")
    ap.add_argument("--no-sentences", action="store_true",
                    help="skip the sentence corpus, generate words only")
    ap.add_argument("--words-only", action="store_true",
                    help="skip the words, generate sentences only")
    args = ap.parse_args()

    print(f"Edge TTS voice: {args.voice}")

    texts: list[tuple[str, str]] = []
    if not args.words_only:
        words = collect_word_texts(args.level)
        print(f"  words: {len(words):,}")
        texts.extend(words)
    if not args.no_sentences:
        sentences = collect_sentence_texts()
        print(f"  sentences (short, with a Bulgarian translation): {len(sentences):,}")
        texts.extend(sentences)

    if not texts:
        print("ERROR: nothing to synthesise")
        return 1

    print(f"synthesising {len(texts):,} texts (unique, sanitised) ...")
    started = time.time()
    done, failed, spoken = asyncio.run(run(texts, args.voice, args.limit))
    elapsed = time.time() - started

    count = write_manifest(spoken)

    print()
    print(f"SUMMARY 06_build_audio: clips={done} failed={failed} "
          f"files={count} elapsed={elapsed:.0f}s -> {AUDIO_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

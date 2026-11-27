"""Generate the audio of the reading passages in the hand-written path.

Input:
    curriculum/*.json      the learning path, including the "reading" cards

Output:
    data/audio/<name>.ogg  one clip per line of a passage
    data/audio/manifest.json  {filename: text}, kept in step with the files

WHY A SEPARATE STEP
-------------------
The words and the sentences are content-addressed: the file name is a
hash of the spoken text, so the same word costs one file however many
lessons use it. A passage line is different -- it is hand-written text
that exists nowhere else, and the CURRICULUM names its clip:

    {"hanzi": "我要三个苹果。", "audio": "reading_market_1.ogg"}

So the curriculum is the contract: the app plays "audio/<name>" without
a database lookup, and this step writes exactly the names the
curriculum asks for. A name that no line claims is not generated, and a
line whose clip is missing is an error the step reports -- a 🔊 button
that plays nothing is worse than no button.

The clips are encoded by _opus.py, like every other clip in the corpus:
one encoder, one set of settings.

Usage:
    python pipeline/13_build_reading_audio.py
    python pipeline/13_build_reading_audio.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _opus import EXTENSION  # noqa: E402
import importlib.util  # noqa: E402

# 06_build_audio.py holds the Edge TTS client, the encoder call and the
# manifest writer. They are imported rather than copied: a second copy of
# the encoder settings is a second corpus.
_spec = importlib.util.spec_from_file_location(
    "_build_audio", os.path.join(os.path.dirname(os.path.abspath(__file__)), "06_build_audio.py")
)
_audio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_audio)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURRICULUM_DIR = os.path.join(ROOT, "curriculum")
AUDIO_DIR = _audio.AUDIO_DIR
VOICE = _audio.VOICE


def collect_lines() -> list[tuple[str, str]]:
    """Return (file name, text) pairs for every clip the curriculum names.

    A reading card names the clip of every line, and an ITEM that is a
    sentence names the clip of the sentence. The name has to end in the
    extension, because the app plays the file name as it stands.

    A word does NOT name a clip: the corpus has one clip per word, and
    the app takes it from the dictionary. Only the hand-written text
    needs a clip of its own.
    """
    out: list[tuple[str, str]] = []
    if not os.path.isdir(CURRICULUM_DIR):
        print(f"  WARNING: no curriculum directory at {CURRICULUM_DIR}")
        return out

    for name in sorted(os.listdir(CURRICULUM_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CURRICULUM_DIR, name)
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"  ERROR: cannot read {path}: {exc}")
            continue
        if not isinstance(data, dict) or "units" not in data:
            continue

        for unit in data["units"]:
            for lesson in unit.get("lessons", []):
                for card in lesson.get("cards", []):
                    if not isinstance(card, dict):
                        continue
                    for line in card.get("lines", []):
                        hanzi = (line or {}).get("hanzi", "")
                        clip = (line or {}).get("audio", "")
                        if not hanzi or not clip:
                            print(f"  ERROR: {path}: a reading line has no "
                                  f"hanzi or no audio name: {line!r}")
                            continue
                        if not clip.endswith(EXTENSION):
                            print(f"  ERROR: {path}: the clip name {clip!r} "
                                  f"does not end in {EXTENSION}")
                            continue
                        out.append((clip, hanzi))
                    # An example that names its own clip is a
                    # hand-written sentence: the corpus holds no clip
                    # for it, so this step has to speak it.
                    for item in card.get("items", []):
                        hanzi = (item or {}).get("hanzi", "")
                        clip = (item or {}).get("audio", "")
                        if not clip:
                            continue
                        if not hanzi:
                            print(f"  ERROR: {path}: an example names a clip "
                                  f"but has no hanzi: {item!r}")
                            continue
                        if not clip.endswith(EXTENSION):
                            print(f"  ERROR: {path}: the clip name {clip!r} "
                                  f"does not end in {EXTENSION}")
                            continue
                        out.append((clip, hanzi))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Speak the reading passages")
    ap.add_argument("--voice", default=VOICE, help="Edge TTS voice name")
    ap.add_argument("--limit", type=int, help="stop after N clips")
    args = ap.parse_args()

    lines = collect_lines()
    if not lines:
        print("ERROR: no reading passages in the curriculum")
        return 1

    # The same clip name twice is a mistake in the curriculum, and a clip
    # that speaks something else is worse: the second one would win.
    seen: dict[str, str] = {}
    for clip, text in lines:
        if clip in seen and seen[clip] != text:
            print(f"  ERROR: the clip {clip} is claimed by two different "
                  f"lines: {seen[clip]!r} and {text!r}")
            return 1
        seen[clip] = text

    if args.limit:
        lines = lines[:args.limit]

    print(f"Edge TTS voice: {args.voice}")
    print(f"  reading lines: {len(lines)}")

    os.makedirs(AUDIO_DIR, exist_ok=True)
    started = time.time()
    ffmpeg = _audio.ffmpeg_path()
    ffprobe = shutil.which("ffprobe")

    done = 0
    failed = 0
    spoken: dict[str, str] = {}

    for clip, text in lines:
        path = os.path.join(AUDIO_DIR, clip)
        clean = _audio.sanitize(text)
        spoken[clip] = clean
        if os.path.exists(path) and os.path.getsize(path) > 0:
            done += 1
            continue
        ok = asyncio.run(_audio.synthesize(clean, path, args.voice))
        if not ok:
            failed += 1
            continue
        if not _audio.encode_one(ffmpeg, ffprobe, path + ".mp3.part", path):
            failed += 1
            continue
        done += 1

    count = _audio.write_manifest(spoken)
    elapsed = time.time() - started

    print()
    print(f"SUMMARY 13_build_reading_audio: clips={done} failed={failed} "
          f"manifest={count} elapsed={elapsed:.0f}s -> {AUDIO_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

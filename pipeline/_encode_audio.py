"""Encode the pronunciation clips as small, trimmed Opus files.

WHAT THIS IS FOR
----------------
Edge TTS hands back a 48 kbps constant-bitrate MP3 of a FIXED length:
every clip is 11 232 bytes and 1.872 seconds long, whether the word is
one character or ten. Measured on the shipped corpus, 83 % of a clip is
digital silence -- the voice itself is about 0.3 seconds in the middle of
the file.

The MP3 is already compressed, so the APK cannot compress it any further:
the silence is shipped to the device at full price. Measured on the
shipped corpus, the audio was 62.8 MiB of a 90.0 MB APK.

Re-encoding to Opus in an Ogg container with the silence trimmed off
makes the corpus 4.5 times smaller. Measured on the shipped corpus: a
clip went from 11 232 B / 1.872 s to 2 484 B / 0.522 s on average, and
the 5 732 clips went from 62.8 MiB to 13.6 MiB. Opus in Ogg is decoded
by the platform since Android 5.0, so the app needs no new dependency
for it.

WHAT IT DOES
------------
Every data/audio/*.mp3 is re-encoded to data/audio/*.ogg and the
manifest is rewritten to the new names, so the content database points
at the files that actually ship. The MP3 is deleted only after the Ogg
has been verified to be a playable file; a clip that fails to convert
keeps its MP3 and the run stops.

The clip NAMES are unchanged: the stem is the same, only the extension
differs. The database, the app and the manifest therefore all keep
pointing at the same clip.

Usage:
    python pipeline/_encode_audio.py              # convert everything
    python pipeline/_encode_audio.py --jobs 4     # fewer parallel jobs
    python pipeline/_encode_audio.py --check      # report only, change nothing
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA  # noqa: E402

# The encoder lives in _opus.py, and it is the SAME one 06_build_audio.py
# uses. It used to be copied into this file, and the copy drifted: the
# two files ended up with different settings, so a corpus converted here
# was not the corpus a fresh build produced. One source, one setting.
from _opus import (  # noqa: E402
    OPUS_BITRATE,
    SAMPLE_RATE,
    encode,
    ffmpeg_path,
    is_playable,
)

AUDIO_DIR = os.path.join(DATA, "audio")
MANIFEST = os.path.join(AUDIO_DIR, "manifest.json")

def load_manifest() -> dict[str, str]:
    if not os.path.exists(MANIFEST):
        print(
            f"ERROR: missing {MANIFEST} - run pipeline/06_build_audio.py first",
            file=sys.stderr,
        )
        raise SystemExit(1)
    with open(MANIFEST, encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(k): str(v) for k, v in data.items()}


def save_manifest(manifest: dict[str, str]) -> None:
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, MANIFEST)


def main() -> int:
    ap = argparse.ArgumentParser(description="Encode the clips as Opus")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4),
                    help="how many clips to encode at once")
    ap.add_argument("--check", action="store_true",
                    help="report what would change, without changing it")
    args = ap.parse_args()

    if not os.path.isdir(AUDIO_DIR):
        print(
            f"ERROR: missing {AUDIO_DIR} - run pipeline/06_build_audio.py first",
            file=sys.stderr,
        )
        return 1

    ffmpeg = ffmpeg_path()
    ffprobe = shutil.which("ffprobe")
    manifest = load_manifest()

    mp3s = sorted(
        os.path.join(AUDIO_DIR, name)
        for name in os.listdir(AUDIO_DIR)
        if name.lower().endswith(".mp3")
    )
    already = [
        os.path.join(AUDIO_DIR, name)
        for name in os.listdir(AUDIO_DIR)
        if name.lower().endswith(".ogg")
    ]
    if not mp3s:
        print(f"nothing to encode: {len(already)} Ogg clips already present")
        return 0

    print(f"ffmpeg:   {ffmpeg}")
    print(f"ffprobe:  {ffprobe or 'not found (size check only)'}")
    print(f"clips:    {len(mp3s):,} MP3 -> Opus {OPUS_BITRATE} mono "
          f"{SAMPLE_RATE} Hz, silence trimmed")
    print()

    if args.check:
        total_before = sum(os.path.getsize(p) for p in mp3s)
        print(f"MP3 total: {total_before:,} B "
              f"({total_before / 1048576:.1f} MiB)")
        return 0

    started = time.time()
    converted = 0
    skipped = 0
    failures: list[tuple[str, str]] = []

    def work(src: str) -> tuple[str, bool, str]:
        stem = os.path.splitext(src)[0]
        dst = stem + ".ogg"
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return src, True, "already encoded"
        ok, err = encode(ffmpeg, src, dst)
        if not ok:
            return src, False, err
        if not is_playable(dst, ffprobe):
            os.remove(dst)
            return src, False, "the encoded file is not playable"
        return src, True, ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, (src, ok, err) in enumerate(pool.map(work, mp3s), 1):
            if ok:
                converted += 1
            else:
                failures.append((os.path.basename(src), err))
            if i % 250 == 0 or i == len(mp3s):
                print(f"  {i}/{len(mp3s)} ({converted} encoded, "
                      f"{len(failures)} failed)")

    if failures:
        print()
        print(f"ERROR: {len(failures)} clips could not be encoded:", file=sys.stderr)
        for name, err in failures[:10]:
            print(f"  {name}: {err}", file=sys.stderr)
        print("       the MP3 originals were kept", file=sys.stderr)
        return 1

    # The manifest is rewritten to the new names, and the MP3s are
    # removed: a corpus that keeps both would ship the silence twice.
    new_manifest: dict[str, str] = {}
    for name, text in manifest.items():
        stem = os.path.splitext(name)[0]
        new_manifest[stem + ".ogg"] = text
    save_manifest(new_manifest)

    removed = 0
    for src in mp3s:
        ogg = os.path.splitext(src)[0] + ".ogg"
        if os.path.exists(ogg) and os.path.getsize(ogg) > 0:
            os.remove(src)
            removed += 1

    total = 0
    for name in os.listdir(AUDIO_DIR):
        if name.lower().endswith(".ogg"):
            total += os.path.getsize(os.path.join(AUDIO_DIR, name))
    elapsed = time.time() - started
    print()
    print(f"SUMMARY _encode_audio: encoded={converted} removed_mp3={removed} "
          f"total={total:,} B ({total / 1048576:.1f} MiB) "
          f"elapsed={elapsed:.0f}s -> {AUDIO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

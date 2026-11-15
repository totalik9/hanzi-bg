"""Encode a pronunciation clip as Opus in an Ogg container.

WHY OPUS
---------
Edge TTS hands back a 48 kbps constant-bitrate MP3 of a FIXED length:
every clip is 11 232 bytes and 1.872 seconds long, whether the word is
one character or ten. The voice itself is about half a second in the
middle of the file; the rest is near-silence.

The MP3 is already compressed, so the APK cannot compress it any further:
the silence is shipped to the device at full price. Measured on the
shipped corpus, the audio was 62.8 MiB of a 90.0 MB APK.

Re-encoding to Opus with the silence trimmed off makes the corpus 4.5
times smaller. Measured on the shipped corpus: a clip went from
11 232 B / 1.872 s to 2 484 B / 0.522 s on average, and the 5 732
clips went from 62.8 MiB to 13.6 MiB. Opus in Ogg is decoded by the
platform since Android 5.0, so the app needs no new dependency for it.

THE SETTINGS
------------
Opus is the right choice over a smaller MP3 here: at 32 kbps mono the
MP3 encoder has to throw away most of what distinguishes one Chinese
syllable from another, and the tones are the thing this app teaches.
Opus keeps them at a bitrate where the whole clip is still a fifth
of the size it was.

24 kHz is the sample rate Edge TTS already produces, so nothing is
gained by going higher and the decoder has less to do.

The leading silence is trimmed with a 20 ms floor so a quiet vowel
onset is not cut off, and the trailing silence only after 50 ms of it,
so a pause inside the word is not mistaken for the end of the clip.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

# The codec and the bitrate.
#
# Opus is the right choice over a smaller MP3 here: at 32 kbps mono the
# MP3 encoder has to throw away most of what distinguishes one Chinese
# syllable from another, and the tones are the thing this app teaches.
# Opus keeps them at a bitrate where the whole clip is still a fifth
# of the size it was.
#
# 24 kHz is the sample rate Edge TTS already produces, so nothing is
# gained by going higher and the decoder has less to do.
OPUS_BITRATE = "32k"
SAMPLE_RATE = "24000"

# The silence filter.
SILENCE_FILTER = (
    "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB"
    ":stop_periods=1:stop_duration=0.05:stop_threshold=-45dB"
)

# The container the app reads. Opus in Ogg is what Media3 plays.
EXTENSION = ".ogg"


def ffmpeg_path() -> str:
    """The ffmpeg binary, or a loud error naming how to install it."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    print(
        "ERROR: ffmpeg is not installed, and the audio cannot be encoded "
        "without it.\n"
        "       install it and put it on PATH:\n"
        "         Windows:  winget install Gyan.FFmpeg\n"
        "         Debian:  sudo apt install ffmpeg\n"
        "         macOS:   brew install ffmpeg\n"
        "       then run this script again",
        file=sys.stderr,
    )
    raise SystemExit(1)


def encode(ffmpeg: str, src: str, dst: str) -> tuple[bool, str]:
    """Encode one clip. Returns (ok, error message)."""
    cmd = [
        ffmpeg, "-v", "error", "-y",
        "-i", src,
        "-af", SILENCE_FILTER,
        "-c:a", "libopus",
        "-b:a", OPUS_BITRATE,
        "-ar", SAMPLE_RATE,
        "-ac", "1",
        dst,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or "").strip()[:400]
    return True, ""


def is_playable(path: str, ffprobe: str | None) -> bool:
    """True when the encoded file holds audio that a decoder can read.

    A zero-byte Ogg is not an error the encoder reports, so the file is
    checked: ffprobe has to read a codec and a duration out of it.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    if not ffprobe:
        # Without ffprobe the size is the only check available: a clip
        # that is empty or absurdly small is not a clip.
        return os.path.getsize(path) > 256
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "stream=codec_name",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    try:
        info = json.loads(result.stdout)
    except ValueError:
        return False
    streams = info.get("streams") or []
    if not streams or streams[0].get("codec_name") != "opus":
        return False
    try:
        duration = float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        return False
    return duration > 0.05


def convert(ffmpeg: str, ffprobe: str | None, src_mp3: str, dst_ogg: str) -> bool:
    """Encode an MP3 to Opus and delete the MP3 only once it is playable.

    The MP3 is kept when the conversion fails, so a run that is
    interrupted or that hits one broken clip never loses audio.
    """
    ok, _err = encode(ffmpeg, src_mp3, dst_ogg)
    if not ok:
        return False
    if not is_playable(dst_ogg, ffprobe):
        if os.path.exists(dst_ogg):
            os.remove(dst_ogg)
        return False
    if os.path.exists(src_mp3):
        os.remove(src_mp3)
    return True

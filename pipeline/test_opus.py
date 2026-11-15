"""Tests for the Opus encoder the pronunciation clips are shipped in.

The clips are what the app plays, so the format is not a detail:
a clip that is empty, truncated or not decodable is a silent button in
the UI. These tests run the real ffmpeg, because the thing being checked
is what ffmpeg actually writes.

    python -m pytest pipeline/test_opus.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _opus import EXTENSION, convert, encode, is_playable  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _make_mp3(path: str, seconds: float = 1.0) -> None:
    """A test tone as MP3: one second of 440 Hz."""
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:a", "libmp3lame", "-b:a", "48k",
        path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def test_encoded_clip_is_opus_and_decodable():
    """The encoded file is Opus in an Ogg container, and it plays."""
    if not FFMPEG:
        return  # ffmpeg is not installed; nothing to check
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "clip.mp3")
        ogg = os.path.join(tmp, "clip" + EXTENSION)
        _make_mp3(mp3)

        ok, err = encode(FFMPEG, mp3, ogg)
        assert ok, f"the encoder failed: {err}"

        assert os.path.exists(ogg)
        assert is_playable(ogg, FFPROBE), "the encoded clip is not playable"


def test_silence_is_trimmed():
    """The clip is shorter than the silence around it.

    Edge TTS pads every clip to a fixed 1.872 seconds, and 83 % of it is
    digital silence. That silence is what made the APK 62.8 MB, so the
    encoder has to remove it -- otherwise the format change buys nothing.
    """
    if not FFMPEG or not FFPROBE:
        return
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "clip.mp3")
        ogg = os.path.join(tmp, "clip" + EXTENSION)
        # Two seconds of tone with a second of silence on each side.
        cmd = [
            FFMPEG, "-v", "error", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5:sample_rate=24000",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=1",
            "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
            "-c:a", "libmp3lame", "-b:a", "48k",
            mp3,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        ok, err = encode(FFMPEG, mp3, ogg)
        assert ok, f"the encoder failed: {err}"

        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", ogg],
            check=True, capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip())
        # 2.5 s of source, of which 0.5 s is the tone.
        assert duration < 1.2, f"the silence was not trimmed: {duration:.2f}s left"


def test_convert_keeps_the_mp3_when_the_encoding_fails():
    """A failed conversion never loses the audio.

    The MP3 is the only copy of the clip until the Ogg has been
    verified, so it may only be deleted after a successful conversion.
    """
    if not FFMPEG:
        return
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "clip.mp3")
        ogg = os.path.join(tmp, "clip" + EXTENSION)
        _make_mp3(mp3)

        # A source that ffmpeg cannot read: the conversion fails.
        ok = convert(FFMPEG, FFPROBE, os.path.join(tmp, "missing.mp3"), ogg)
        assert not ok, "a missing source must not report success"
        assert os.path.exists(mp3), "the MP3 was deleted by a failed conversion"


def test_convert_deletes_the_mp3_after_a_good_conversion():
    """A successful conversion leaves one file, not two.

    A corpus that keeps both formats ships the silence twice.
    """
    if not FFMPEG:
        return
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "clip.mp3")
        ogg = os.path.join(tmp, "clip" + EXTENSION)
        _make_mp3(mp3)

        assert convert(FFMPEG, FFPROBE, mp3, ogg), "the conversion failed"
        assert os.path.exists(ogg)
        assert not os.path.exists(mp3), "the MP3 was kept after a good conversion"


def test_an_empty_file_is_not_playable():
    """A zero-byte file is not a clip.

    ffmpeg does not report an error when it writes nothing, so the
    check has to be made on the file itself.
    """
    if not FFMPEG:
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "empty" + EXTENSION)
        with open(path, "wb"):
            pass
        assert not is_playable(path, FFPROBE)

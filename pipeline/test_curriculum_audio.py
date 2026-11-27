"""The examples of the path have to be HEARABLE.

    python -m pytest pipeline/test_curriculum_audio.py -q

WHY THIS IS A TEST AND NOT A NOTE

A card shows a 🔊 button next to every example, and the button plays
the clip of that example. The clip of a WORD comes from the corpus; the
clip of a SENTENCE is named by the curriculum itself, because the
sentence is hand-written and exists nowhere else.

So there are two ways for an example to be silent:

  * the example names a clip, and the file was never built;
  * the example names no clip, and the word is not in the dictionary.

The first is a missing file, the second is a word the app cannot show.
Both are a button that plays nothing, and a button that plays nothing
is worse than no button -- so the app draws the button only when there
is a clip, and THIS test says whether there should have been one.

The audio files are a build artefact and they are not in version
control, so the test skips the files it cannot find and says so. The
NAMES are checked either way: a clip that the curriculum names must
end in the extension, and two examples must not share one name.
"""
from __future__ import annotations

import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURRICULUM = os.path.join(ROOT, "curriculum")
AUDIO = os.path.join(ROOT, "data", "audio")
EXTENSION = ".ogg"


def path_files() -> list[tuple[str, dict]]:
    """Every path file of the curriculum, with its content."""
    out = []
    if not os.path.isdir(CURRICULUM):
        return out
    for name in sorted(os.listdir(CURRICULUM)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CURRICULUM, name), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "units" in data:
            out.append((name, data))
    return out


def examples() -> list[tuple[str, str, dict]]:
    """Every example of every card: (file, unit key, item)."""
    out = []
    for name, data in path_files():
        for unit in data["units"]:
            for lesson in unit.get("lessons", []):
                for card in lesson.get("cards", []):
                    for item in card.get("items", []):
                        out.append((name, unit.get("key", ""), item))
    return out


def clip_names() -> list[tuple[str, str, str]]:
    """Every clip the curriculum names: (file, unit key, clip name)."""
    out = []
    for name, data in path_files():
        for unit in data["units"]:
            for lesson in unit.get("lessons", []):
                for card in lesson.get("cards", []):
                    for item in card.get("items", []):
                        if item.get("audio"):
                            out.append((name, unit.get("key", ""), item["audio"]))
                    for line in card.get("lines", []):
                        if line.get("audio"):
                            out.append((name, unit.get("key", ""), line["audio"]))
    return out


def test_the_curriculum_has_examples():
    assert examples(), "no examples found in the curriculum"


def test_every_clip_name_ends_in_the_extension():
    for name, unit, clip in clip_names():
        assert clip.endswith(EXTENSION), (
            f"{name}: the clip name {clip!r} of {unit} does not end in "
            f"{EXTENSION}")


def test_no_two_examples_share_a_clip():
    seen: dict[str, str] = {}
    for name, unit, clip in clip_names():
        assert clip not in seen, (
            f"{name}: the clip {clip!r} is claimed by {seen.get(clip)} and "
            f"by {unit} as well")
        seen[clip] = unit


def test_every_named_clip_was_built():
    """The clip a card names has to exist.

    The audio is a build artefact and it is not in version control, so
    this test SKIPS when the corpus has not been built. It does not
    fail: a fresh clone has no audio and the names are still checked
    by the two tests above.
    """
    if not os.path.isdir(AUDIO):
        pytest.skip("the audio corpus has not been built")
    missing = [
        (name, unit, clip)
        for name, unit, clip in clip_names()
        if not os.path.exists(os.path.join(AUDIO, clip))
    ]
    assert not missing, (
        "these clips are named by the curriculum but were never built: "
        + ", ".join(f"{clip} ({unit})" for _n, unit, clip in missing[:10]))


def test_every_example_that_names_no_clip_is_a_known_word():
    """An example that names no clip has to be a word the dictionary holds.

    A word takes its clip from the corpus, so the corpus has to know it.
    An example that is NOT a word and names no clip would be silent.
    """
    import sqlite3

    db = os.path.join(ROOT, "data", "content.db")
    if not os.path.exists(db):
        pytest.skip("the content database has not been built")
    conn = sqlite3.connect(db)
    known = {
        hanzi for (hanzi,) in conn.execute(
            "SELECT hanzi FROM words WHERE audio IS NOT NULL AND audio != ''"
        )
    }
    conn.close()
    silent = [
        (name, unit, item["hanzi"])
        for name, unit, item in examples()
        if not item.get("audio") and item["hanzi"] not in known
    ]
    assert not silent, (
        "these examples are silent: they are not words the dictionary "
        "holds and they name no clip: "
        + ", ".join(f"{hanzi} ({unit})" for _n, unit, hanzi in silent[:10]))

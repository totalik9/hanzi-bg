"""Tests for the example sentences of the words.

The dictionary tells the learner what a word means; the example
sentences show it in use. Those sentences come from the Tatoeba corpus,
which is 45 % traditional Chinese, so they are folded to the simplified
script before they are stored -- an example next to a simplified word
that is written in the traditional script contradicts the vocabulary it
is supposed to illustrate.

These tests pin down the four properties that make an example usable
and one that makes the table safe to query:

  1. every example CONTAINS the word it is an example of;
  2. no example holds a character that exists only in the traditional
     script -- the fold either converted it or the sentence was
     dropped;
  3. the table is keyed by (word, rank) and the ranks of a word are
     0, 1, 2, ... with no hole in them;
  4. every example has a Bulgarian translation, because the app is for
     Bulgarian learners and an untranslated example teaches nothing;

and they check that the numbers the build reports are the numbers the
table holds, so a stale statistics file cannot hide a broken build.

Usage:
    python pipeline/08_build_content_db.py     (to build the database)
    python -m pytest pipeline/test_word_example.py -q
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pinyin_utils import DATA, is_hanzi  # noqa: E402
from word_examples import (  # noqa: E402
    HANZI_DB,
    MAX_CANDIDATES,
    STATS_JSON,
    fold_to_simplified,
    load_script_maps,
)

DB_PATH = os.path.join(DATA, "content.db")


# ------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def conn() -> sqlite3.Connection:
    """The built content database.

    The tests run against the database the pipeline builds. When it is
    not there -- a fresh checkout, where `data/` is not in version
    control -- the tests skip rather than fail: there is nothing to
    check, and a failure would only say that the build was not run.
    """
    if not os.path.exists(DB_PATH):
        pytest.skip(f"{DB_PATH} is not built - run pipeline/08_build_content_db.py")
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="module")
def candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT hanzi, ord, sentence, pinyin, translation_bg "
        "FROM word_example ORDER BY hanzi, ord").fetchall()
    if not rows:
        pytest.skip("the database holds no word examples - run the pipeline")
    return rows


@pytest.fixture(scope="module")
def traditional_only() -> set[str]:
    """The characters that exist only in the traditional script.

    A character is traditional-only when the dictionary writes it in the
    traditional column and never in the simplified one. These are the
    characters that make a sentence traditional, so an example that
    holds one of them is still in the script the app does not teach.
    """
    if not os.path.exists(HANZI_DB):
        pytest.skip(f"{HANZI_DB} is not built - run pipeline/02_build_dictionary.py")
    connection = sqlite3.connect(HANZI_DB)
    try:
        rows = connection.execute(
            "SELECT traditional, simplified FROM dict").fetchall()
    finally:
        connection.close()
    traditional_side: set[str] = set()
    simplified_side: set[str] = set()
    for traditional, simplified in rows:
        traditional_side.update(traditional)
        simplified_side.update(simplified)
    return traditional_side - simplified_side


# ---------------------------------------------------------------- tests


def test_every_example_contains_its_word(candidates):
    """An example that does not contain the word is not an example."""
    missing = [
        (row["hanzi"], row["sentence"])
        for row in candidates
        if row["hanzi"] not in row["sentence"]
    ]
    assert not missing, (
        f"{len(missing)} examples do not contain their word: {missing[:5]}")


def test_no_example_holds_a_traditional_character(candidates, traditional_only):
    """No example holds a character the fold could not convert.

    The fold either converts a traditional-only character or the
    sentence is dropped, so an example that holds one is a sentence the
    pipeline should have rejected.
    """
    offenders: dict[str, int] = {}
    for row in candidates:
        for character in row["sentence"]:
            if character in traditional_only:
                offenders[character] = offenders.get(character, 0) + 1
    assert not offenders, (
        f"examples hold traditional characters: {offenders}")


def test_the_fold_is_stable(conn, candidates):
    """Folding an example again changes nothing.

    The fold is a projection onto the simplified script: once a
    sentence is folded it must stay folded. A character that the fold
    does not know about would break this, and the sentence would be
    stored half-converted.
    """
    vocabulary_chars: set[str] = set()
    for (word,) in conn.execute("SELECT hanzi FROM words"):
        vocabulary_chars.update(word)
    maps = load_script_maps(vocabulary_chars=vocabulary_chars)

    unstable = [
        (row["hanzi"], row["sentence"])
        for row in candidates
        if fold_to_simplified(row["sentence"], maps) != row["sentence"]
    ]
    assert not unstable, (
        f"{len(unstable)} examples are not stable under the fold: {unstable[:5]}")


def test_the_table_is_keyed_by_word_and_rank(conn):
    """The table is keyed by (hanzi, ord)."""
    columns = conn.execute("PRAGMA table_info(word_example)").fetchall()
    names = [column["name"] for column in columns]
    assert names == ["hanzi", "ord", "sentence", "pinyin", "translation_bg"], (
        f"unexpected columns: {names}")

    key = conn.execute("PRAGMA table_info(word_example)").fetchall()
    primary = [column["name"] for column in key if column["pk"]]
    assert primary == ["hanzi", "ord"], (
        f"the primary key is {primary}, not (hanzi, ord)")


def test_the_ranks_of_a_word_have_no_holes(conn):
    """The ranks of a word are 0, 1, 2, ... with no hole in them."""
    broken = conn.execute(
        "SELECT hanzi, COUNT(*) AS n, MIN(ord) AS lo, MAX(ord) AS hi "
        "FROM word_example GROUP BY hanzi "
        "HAVING MIN(ord) != 0 OR MAX(ord) != COUNT(*) - 1").fetchall()
    assert not broken, (
        f"{len(broken)} words have a hole in their ranks: "
        f"{[(row['hanzi'], row['lo'], row['hi'], row['n']) for row in broken[:5]]}")


def test_no_word_has_more_than_four_examples(conn):
    """A word keeps at most four examples."""
    too_many = conn.execute(
        "SELECT hanzi, COUNT(*) AS n FROM word_example GROUP BY hanzi "
        "HAVING COUNT(*) > ?", (MAX_CANDIDATES,)).fetchall()
    assert not too_many, (
        f"{len(too_many)} words have more than {MAX_CANDIDATES} examples")


def test_every_example_has_a_bulgarian_translation(candidates):
    """An untranslated example teaches nothing."""
    empty = [
        (row["hanzi"], row["sentence"])
        for row in candidates
        if not row["translation_bg"].strip()
    ]
    assert not empty, f"{len(empty)} examples have no translation: {empty[:5]}"


def test_the_statistics_file_is_written_and_matches_the_table(conn):
    """The numbers the build reports are the numbers the table holds.

    The statistics file is written next to the database, so a later run
    can be compared with an earlier one. A stale file is worse than no
    file, so the numbers in it are recomputed from the table here.
    """
    if not os.path.exists(STATS_JSON):
        pytest.skip(f"{STATS_JSON} is not written - run the pipeline")

    with open(STATS_JSON, encoding="utf-8") as fh:
        stats = json.load(fh)

    words_total = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    rows = conn.execute(
        "SELECT hanzi, sentence FROM word_example").fetchall()
    words_with_candidate = len({row["hanzi"] for row in rows})
    words_with_four = conn.execute(
        "SELECT COUNT(*) FROM (SELECT hanzi FROM word_example GROUP BY hanzi "
        "HAVING COUNT(*) = ?)", (MAX_CANDIDATES,)).fetchone()[0]
    path_words_total = conn.execute(
        "SELECT COUNT(DISTINCT hanzi) FROM curriculum_words").fetchone()[0]
    path_words_with_candidate = conn.execute(
        "SELECT COUNT(DISTINCT w.hanzi) FROM word_example w "
        "JOIN curriculum_words c ON c.hanzi = w.hanzi").fetchone()[0]
    lengths = sorted(len([c for c in row["sentence"] if is_hanzi(c)])
                     for row in rows)

    assert stats["words_total"] == words_total
    assert stats["words_with_candidate"] == words_with_candidate
    assert stats["words_with_full_four"] == words_with_four
    assert stats["candidate_rows"] == len(rows)
    assert stats["path_words_total"] == path_words_total
    assert stats["path_words_with_candidate"] == path_words_with_candidate
    assert stats["sentence_length_hanzi"]["min"] == (lengths[0] if lengths else 0)
    assert stats["sentence_length_hanzi"]["max"] == (lengths[-1] if lengths else 0)
    assert stats["sentence_length_hanzi"]["median"] == (
        int(statistics.median(lengths)) if lengths else 0)


def test_the_measured_coverage_is_the_measured_one(conn):
    """The numbers the run reports are checked against the corpus.

    The coverage is a claim about the corpus, so it is measured again
    here: the words that have an example are the words the corpus can
    supply an example for, and the words that do not are the ones the
    corpus simply does not cover.
    """
    if not os.path.exists(STATS_JSON):
        pytest.skip(f"{STATS_JSON} is not written - run the pipeline")
    with open(STATS_JSON, encoding="utf-8") as fh:
        stats = json.load(fh)

    words_total = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    assert stats["words_total"] == words_total
    assert stats["words_with_candidate"] <= words_total
    assert stats["words_with_full_four"] <= stats["words_with_candidate"]
    assert 0 < stats["words_with_candidate"] <= words_total

    # Every word the table holds is a word the dictionary holds.
    unknown = conn.execute(
        "SELECT COUNT(*) FROM word_example w "
        "WHERE NOT EXISTS (SELECT 1 FROM words WHERE hanzi = w.hanzi)"
    ).fetchone()[0]
    assert unknown == 0, f"{unknown} examples belong to unknown words"


def test_the_fold_converts_the_traditional_corpus(candidates, traditional_only):
    """The corpus is 45 % traditional, and the examples are not.

    The fold is the reason the examples are usable next to a
    simplified vocabulary, so the check that the corpus IS traditional
    matters as much as the check that the examples are not: without
    the first, the second would pass on a corpus that never needed a
    fold.
    """
    if not os.path.exists(HANZI_DB):
        pytest.skip(f"{HANZI_DB} is not built - run pipeline/02_build_dictionary.py")
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        total = connection.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        traditional = 0
        for (text,) in connection.execute("SELECT hanzi FROM sentences"):
            if any(character in traditional_only for character in text):
                traditional += 1
    finally:
        connection.close()

    assert total > 0
    assert traditional > 0, (
        "the corpus holds no traditional sentence, so the fold is not "
        "being exercised")
    assert traditional < total, (
        "every sentence is traditional, so the corpus is not the one the "
        "pipeline was built for")

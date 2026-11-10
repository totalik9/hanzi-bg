"""Build the normalised SQLite dictionary database (data/hanzi.db).

Inputs (produced by 01_fetch_sources.py):
    data/raw/cedict_1_0_ts_utf-8_mdbg.txt   CC-CEDICT, CC BY-SA 4.0
    data/raw/mmah_dictionary.txt             Make Me a Hanzi, Arphic Public License
    data/raw/mmah_graphics.txt              Make Me a Hanzi, Arphic Public License

Outputs:
    data/hanzi.db
        table dict(id, traditional, simplified, pinyin_number, pinyin_with_tones, definition)
        table dict_fts  FTS5 virtual table over (simplified, traditional, pinyin_with_tones, definition)
        table char_info(char, strokes, radical, decomposition, definition)
        table char_strokes(char, stroke_index, svg_path)

The script is safe to re-run: the database is rebuilt from scratch each time.

Usage:
    python pipeline/02_build_dictionary.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import DATA, RAW, pinyin_number_to_tones  # noqa: E402

DB_PATH = os.path.join(DATA, "hanzi.db")

CEDICT = os.path.join(RAW, "cedict_1_0_ts_utf-8_mdbg.txt")
MMAH_DICT = os.path.join(RAW, "mmah_dictionary.txt")
MMAH_GRAPHICS = os.path.join(RAW, "mmah_graphics.txt")

# CC-CEDICT line: TRAD SIMP [pin1 yin1] /def1/def2/
CEDICT_RE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.*)/\s*$")


def build_dict_table(conn: sqlite3.Connection) -> int:
    """Parse CC-CEDICT into the `dict` table. Returns the row count."""
    cur = conn.cursor()
    count = 0
    batch = []
    with open(CEDICT, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            m = CEDICT_RE.match(line.rstrip("\n"))
            if not m:
                continue
            traditional, simplified, pinyin_number, definition = m.groups()
            batch.append((
                traditional,
                simplified,
                pinyin_number,
                pinyin_number_to_tones(pinyin_number),
                definition,
            ))
            count += 1
            if len(batch) >= 5000:
                cur.executemany(
                    "INSERT INTO dict (traditional, simplified, pinyin_number, "
                    "pinyin_with_tones, definition) VALUES (?,?,?,?,?)",
                    batch,
                )
                batch.clear()
    if batch:
        cur.executemany(
            "INSERT INTO dict (traditional, simplified, pinyin_number, "
            "pinyin_with_tones, definition) VALUES (?,?,?,?,?)",
            batch,
        )
    conn.commit()
    return count


def build_char_info(conn: sqlite3.Connection) -> int:
    """Parse Make Me a Hanzi dictionary.txt (JSONL) into `char_info`.

    The JSONL records carry character / definition / pinyin / decomposition /
    radical but no stroke count, so `strokes` is filled in afterwards from
    graphics.txt (the number of strokes drawn for that character).
    """
    cur = conn.cursor()
    count = 0
    with open(MMAH_DICT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            char = obj.get("character")
            if not char:
                continue
            cur.execute(
                "INSERT OR REPLACE INTO char_info (char, strokes, radical, "
                "decomposition, definition) VALUES (?,?,?,?,?)",
                (
                    char,
                    obj.get("strokes"),
                    obj.get("radical"),
                    obj.get("decomposition"),
                    obj.get("definition"),
                ),
            )
            count += 1
    conn.commit()
    return count


def build_char_strokes(conn: sqlite3.Connection) -> int:
    """Parse Make Me a Hanzi graphics.txt (JSONL) into `char_strokes`.

    graphics.txt is JSONL: {"character": "中", "strokes": ["M ...", "M ..."], ...}
    The raw SVG path string of each stroke is stored, indexed from 0.
    """
    cur = conn.cursor()
    count = 0
    chars = 0
    with open(MMAH_GRAPHICS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            char = obj.get("character")
            strokes = obj.get("strokes")
            if not char or not strokes:
                continue
            rows = [(char, i, path) for i, path in enumerate(strokes)]
            cur.executemany(
                "INSERT INTO char_strokes (char, stroke_index, svg_path) VALUES (?,?,?)",
                rows,
            )
            # graphics.txt knows how many strokes each character has; the
            # dictionary.txt records do not carry a stroke count.
            cur.execute("UPDATE char_info SET strokes=? WHERE char=?", (len(strokes), char))
            count += len(rows)
            chars += 1
    conn.commit()
    return count


def main() -> int:
    for path in (CEDICT, MMAH_DICT, MMAH_GRAPHICS):
        if not os.path.exists(path):
            print(f"ERROR: missing input {path} - run 01_fetch_sources.py first")
            return 1

    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE dict (
            id INTEGER PRIMARY KEY,
            traditional TEXT,
            simplified TEXT,
            pinyin_number TEXT,
            pinyin_with_tones TEXT,
            definition TEXT
        );

        CREATE TABLE char_info (
            char TEXT PRIMARY KEY,
            strokes INTEGER,
            radical TEXT,
            decomposition TEXT,
            definition TEXT
        );

        CREATE TABLE char_strokes (
            char TEXT,
            stroke_index INTEGER,
            svg_path TEXT
        );

        CREATE INDEX idx_dict_simplified ON dict(simplified);
        CREATE INDEX idx_dict_traditional ON dict(traditional);
        CREATE INDEX idx_char_strokes_char ON char_strokes(char);
        """
    )

    print("building table dict from CC-CEDICT ...")
    n_dict = build_dict_table(conn)
    print(f"  dict rows: {n_dict:,}")

    print("building FTS5 table dict_fts ...")
    try:
        cur.executescript(
            """
            CREATE VIRTUAL TABLE dict_fts USING fts5(
                simplified,
                traditional,
                pinyin_with_tones,
                definition,
                content='dict',
                content_rowid='id'
            );
            INSERT INTO dict_fts(dict_fts) VALUES('rebuild');
            """
        )
        conn.commit()
        n_fts = cur.execute("SELECT count(*) FROM dict_fts").fetchone()[0]
    except sqlite3.OperationalError as exc:
        print(f"  FTS5 unavailable ({exc}); creating a plain fallback table")
        cur.executescript(
            """
            CREATE TABLE dict_fts (
                simplified TEXT, traditional TEXT,
                pinyin_with_tones TEXT, definition TEXT
            );
            INSERT INTO dict_fts SELECT simplified, traditional,
                                  pinyin_with_tones, definition FROM dict;
            """
        )
        conn.commit()
        n_fts = cur.execute("SELECT count(*) FROM dict_fts").fetchone()[0]

    print("building table char_info from Make Me a Hanzi ...")
    n_info = build_char_info(conn)
    print(f"  char_info rows: {n_info:,}")

    print("building table char_strokes from Make Me a Hanzi graphics ...")
    n_strokes = build_char_strokes(conn)
    print(f"  char_strokes rows: {n_strokes:,}")

    counts = {}
    for table in ("dict", "dict_fts", "char_info", "char_strokes"):
        counts[table] = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    # a couple of sanity samples
    sample = cur.execute(
        "SELECT simplified, pinyin_number, pinyin_with_tones, definition "
        "FROM dict WHERE simplified IN ('你好','学习','水') LIMIT 3"
    ).fetchall()
    print("\nsample rows:")
    for row in sample:
        print("   ", row)

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    print()
    print(f"SUMMARY 02_build_dictionary: db={DB_PATH}")
    for table, n in counts.items():
        print(f"   {table:14s} {n:>9,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

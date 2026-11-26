"""Seed the learner's own database on the emulator.

    python session/seed_learner.py --serial emulator-5554 --words 25

The writing step joins the lesson after 20 words (PathRules), so a
learner who has just installed the app never sees it. To test that
card, the learner's own database is given the words of the first
lessons, exactly as the app would have written them.

The database is pulled out with run-as, changed here with sqlite3 and
pushed back. The content database is never touched: only the
learner's own state is seeded.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PACKAGE = "bg.hanzi.learn.debug"
ADB = "C:/tools/android-sdk/platform-tools/adb.exe"


def adb(serial: str, *args: str, binary: bool = False):
    cmd = [ADB, "-s", serial, *args]
    result = subprocess.run(cmd, capture_output=True)
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", "replace") + result.stderr.decode(
        "utf-8", "replace"
    )


def pull(serial: str, local: Path) -> None:
    """Pull the learner's database out of the app's private space.

    The write-ahead log is pulled too: Room writes into the -wal file
    and the main file alone is an empty shell with no tables.
    """
    blob = adb(
        serial,
        "exec-out",
        "run-as",
        PACKAGE,
        "cat",
        "databases/hanzi_user.db",
        binary=True,
    )
    if not blob:
        raise SystemExit(
            "the database could not be read; is the app installed and "
            "has it been opened at least once?"
        )
    local.write_bytes(blob)
    for suffix in ("-wal", "-shm"):
        side = adb(
            serial,
            "exec-out",
            "run-as",
            PACKAGE,
            "cat",
            f"databases/hanzi_user.db{suffix}",
            binary=True,
        )
        if side:
            local.with_name(local.name + suffix).write_bytes(side)


def push(serial: str, local: Path) -> None:
    """Push the database back into the app's private space.

    The stale write-ahead log of the device is removed first: it
    belongs to the old database and the device's SQLite would try to
    apply it to the new one.
    """
    adb(serial, "push", str(local), "/data/local/tmp/hanzi_user.db")
    adb(
        serial,
        "shell",
        f"run-as {PACKAGE} sh -c "
        "'rm -f databases/hanzi_user.db-wal databases/hanzi_user.db-shm; "
        "cat /data/local/tmp/hanzi_user.db > databases/hanzi_user.db'",
    )
    adb(serial, "shell", f"run-as {PACKAGE} ls -l databases/hanzi_user.db")


def seed(local: Path, words: int, target_lesson: str | None) -> None:
    conn = sqlite3.connect(local)
    cur = conn.cursor()

    content = sqlite3.connect(REPO / "data" / "content.db")
    rows = list(
        content.execute(
            "select w.hanzi, l.unit_key from curriculum_words w "
            "join curriculum_lessons l on l.key = w.lesson_key "
            "where l.kind = 'words' order by l.ord, w.ord limit ?",
            (words,),
        )
    )
    content.close()

    now = int(time.time() * 1000)
    for hanzi, unit in rows:
        cur.execute(
            "insert or replace into srs_card "
            "(itemId, level, dueAt, stability, difficulty, reps, lapses, "
            " state, lastReviewAt) values (?,?,?,?,?,?,?,?,?)",
            (hanzi, unit, now + 86_400_000, 2.5, 5.0, 1, 0, 2, now),
        )

    # The lessons before the one we want to test are marked as passed,
    # so the path opens the lesson we want. Without this the path
    # always starts at the first lesson and the harness has to walk
    # the whole path to reach a late card.
    #
    # The target lesson itself is left open, so it is the one the path
    # offers as "the next lesson".
    content = sqlite3.connect(REPO / "data" / "content.db")
    keys = [
        key
        for (key,) in content.execute(
            "select key from curriculum_lessons order by ord"
        )
    ]
    content.close()
    target = target_lesson
    for key in keys:
        if target and key == target:
            break
        cur.execute(
            "insert or replace into lesson_progress "
            "(lessonKey, bestScore, attempts, completedAt) values (?,?,?,?)",
            (key, 100, 1, now),
        )

    settings = {
        "onboarded": "true",
        "goal": "hsk",
        "daily_minutes": "15",
        "daily_goal": "20",
    }
    for key, value in settings.items():
        cur.execute(
            "insert or replace into learner_setting (key, value) values (?,?)",
            (key, value),
        )

    conn.commit()
    print("srs cards:", list(cur.execute("select count(*) from srs_card"))[0][0])
    print("settings:", list(cur.execute("select * from learner_setting")))
    conn.close()


def seed_app(device, words: int, until: str = "numbers-1") -> None:
    """Give a learner the words of the first lessons.

    The app is stopped, its database is pulled out, the rows are
    written here with sqlite3 and the database is pushed back. The
    device has no python and `run-as` has no `push`, so this is the
    only way that works.

    The learner gets:
      * `words` cards in the SRS queue -- enough for the writing step,
        which joins the lesson after 20 words;
      * cards that are DUE, so the review session has something in it;
      * the lessons before `until` marked as passed, so the path opens
        a vocabulary lesson and not a reading one.
    """
    import shutil

    package = "bg.hanzi.learn.debug"
    work = REPO / "recordings" / "sessions"
    work.mkdir(parents=True, exist_ok=True)
    local = work / "hanzi_user.db"

    device.shell(f"am force-stop {package}")
    time.sleep(1.0)

    blob = subprocess.run(
        [ADB, "-s", device.serial, "exec-out", "run-as", package, "cat",
         "databases/hanzi_user.db"],
        capture_output=True,
    ).stdout
    if not blob:
        raise SystemExit("the learner's database could not be read")
    local.write_bytes(blob)
    for suffix in ("-wal", "-shm"):
        side = subprocess.run(
            [ADB, "-s", device.serial, "exec-out", "run-as", package, "cat",
             f"databases/hanzi_user.db{suffix}"],
            capture_output=True,
        ).stdout
        if side:
            local.with_name(local.name + suffix).write_bytes(side)

    content = sqlite3.connect(REPO / "data" / "content.db")
    rows = list(
        content.execute(
            "select w.hanzi, l.unit_key from curriculum_words w "
            "join curriculum_lessons l on l.key = w.lesson_key "
            "where l.kind = 'words' order by l.ord, w.ord limit ?",
            (words,),
        )
    )
    lessons = [
        key
        for (key,) in content.execute(
            "select key from curriculum_lessons order by ord"
        )
    ]
    content.close()

    conn = sqlite3.connect(local)
    cur = conn.cursor()
    now = int(time.time() * 1000)
    due = now - 86_400_000  # due NOW, so the review has cards
    for hanzi, unit in rows:
        cur.execute(
            "insert or replace into srs_card "
            "(itemId, level, dueAt, stability, difficulty, reps, lapses, "
            " state, lastReviewAt) values (?,?,?,?,?,?,?,?,?)",
            (hanzi, unit, due, 2.5, 5.0, 1, 0, 2, now),
        )
    for key in lessons:
        if key == until:
            break
        cur.execute(
            "insert or replace into lesson_progress "
            "(lessonKey, bestScore, attempts, completedAt) values (?,?,?,?)",
            (key, 100, 1, now),
        )
    for key, value in (
        ("onboarded", "true"),
        ("goal", "hsk"),
        ("daily_minutes", "15"),
        ("daily_goal", "20"),
    ):
        cur.execute(
            "insert or replace into learner_setting (key, value) values (?,?)",
            (key, value),
        )
    conn.commit()
    count = list(cur.execute("select count(*) from srs_card"))[0][0]
    conn.close()
    print(f"  {count} cards in the learner's queue")

    subprocess.run(
        [ADB, "-s", device.serial, "push", str(local), "/data/local/tmp/u.db"],
        capture_output=True,
    )
    subprocess.run(
        [
            ADB, "-s", device.serial, "shell",
            f"run-as {package} sh -c "
            "'rm -f databases/hanzi_user.db-wal databases/hanzi_user.db-shm; "
            "cat /data/local/tmp/u.db > databases/hanzi_user.db'",
        ],
        capture_output=True,
    )
    device.start_app()


def seed_on_device(device, words: int, due: bool = True) -> None:
    """Give a RUNNING learner the words of the first lessons.

    The app is open, so its database cannot be pulled and pushed. The
    rows are written with a small script through run-as instead, and
    the app is asked to read them again.

    The learner gets:
      * `words` cards in the SRS queue -- enough for the writing step,
        which joins the lesson after 20 words;
      * cards that are DUE, so the review session has something in it;
      * the lessons before the target marked as passed, so the path
        opens a vocabulary lesson and not a reading one.
    """
    import json as _json
    import sqlite3 as _sqlite3
    import time as _time

    content = _sqlite3.connect(REPO / "data" / "content.db")
    rows = list(
        content.execute(
            "select w.hanzi, l.unit_key, l.key from curriculum_words w "
            "join curriculum_lessons l on l.key = w.lesson_key "
            "where l.kind = 'words' order by l.ord, w.ord limit ?",
            (words,),
        )
    )
    lessons = [key for (key,) in content.execute(
        "select key from curriculum_lessons order by ord"
    )]
    content.close()

    now = int(_time.time() * 1000)
    tomorrow = now - 86_400_000  # due NOW, so the review has cards
    script = [
        "import sqlite3, time",
        "db = sqlite3.connect('/data/data/bg.hanzi.learn.debug/databases/hanzi_user.db')",
        "c = db.cursor()",
        f"now = {now}",
        f"due = {tomorrow}",
    ]
    for hanzi, unit, _lesson in rows:
        script.append(
            "c.execute('insert or replace into srs_card "
            "(itemId, level, dueAt, stability, difficulty, reps, lapses, state, "
            "lastReviewAt) values (?,?,?,?,?,?,?,?,?)', "
            f"({hanzi!r}, {unit!r}, due, 2.5, 5.0, 1, 0, 2, now))"
        )
    for key in lessons[:-1]:
        script.append(
            "c.execute('insert or replace into lesson_progress "
            "(lessonKey, bestScore, attempts, completedAt) values (?,?,?,?)', "
            f"({key!r}, 100, 1, now))"
        )
    script += [
        "for k, v in (('onboarded','true'),('goal','hsk'),('daily_minutes','15'),"
        "('daily_goal','20')):",
        "    c.execute('insert or replace into learner_setting (key, value) "
        "values (?,?)', (k, v))",
        "db.commit()",
        "db.close()",
        "print('seeded')",
    ]

    body = "\n".join(script)
    # The script goes through a file: a shell command with quotes and
    # newlines is a quoting problem waiting to happen.
    path = REPO / "recordings" / "sessions" / "_seed.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    device.shell(
        f"run-as bg.hanzi.learn.debug push {path} /data/local/tmp/_seed.py"
    )
    print(
        device.shell(
            "run-as bg.hanzi.learn.debug sh -c "
            "'cd /data/local/tmp && python3 _seed.py'"
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--words", type=int, default=25)
    parser.add_argument(
        "--until",
        default=None,
        help="the lesson that is left open; the ones before it are passed",
    )
    args = parser.parse_args()

    work = REPO / "recordings" / "sessions"
    work.mkdir(parents=True, exist_ok=True)
    local = work / "hanzi_user.db"

    # The database exists only after the app has been opened once: it
    # is created on the first launch. Without this the pull returns an
    # empty file and the tables are missing.
    adb(args.serial, "shell", f"am force-stop {PACKAGE}")
    adb(args.serial, "shell", f"monkey -p {PACKAGE} -c android.intent.category.LAUNCHER 1")
    time.sleep(6.0)
    adb(args.serial, "shell", f"am force-stop {PACKAGE}")

    pull(args.serial, local)
    seed(local, args.words, args.until)
    push(args.serial, local)
    print("seeded", args.serial)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

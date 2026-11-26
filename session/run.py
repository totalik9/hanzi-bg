"""Run a student session against an emulator and analyse the log.

    python session/run.py --student careful --serial emulator-5556

The session is reproducible: it clears the app's data first, so every
student starts from the same empty slate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.analyze import Analyzer  # noqa: E402
from session.device import Device  # noqa: E402
from session.runner import Session, SessionLog  # noqa: E402
from session.students import PERSONAS  # noqa: E402

APK = REPO / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
OUT = REPO / "recordings" / "sessions"


def install(device: Device, apk: Path) -> None:
    if not apk.exists():
        print(f"APK not found: {apk}", file=sys.stderr)
        print("Build it first: cd android && ./gradlew :app:assembleDebug", file=sys.stderr)
        raise SystemExit(2)
    print(f"installing {apk.name} ({apk.stat().st_size // 1024 // 1024} MB)")
    device.install(str(apk))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student", default="careful", choices=sorted(PERSONAS))
    parser.add_argument("--serial", default="emulator-5556")
    parser.add_argument("--out", default=None, help="the log file to write")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--keep-data", action="store_true",
                        help="do not clear the app's data first")
    parser.add_argument("--max-seconds", type=int, default=0,
                        help="how long the student walks; 0 means the student's own")
    parser.add_argument("--seed-words", type=int, default=0,
                        help="give the learner this many words, so the writing "
                             "step and the review can be reached")
    args = parser.parse_args()

    persona = PERSONAS[args.student]
    device = Device(args.serial)

    if not args.no_install:
        install(device, APK)

    if not args.seed_words:
        # A student can be a beginner, or a learner who has been at it
        # for a while.
        args.seed_words = persona.seed_words

    if not args.keep_data:
        print("clearing the app's data")
        device.clear_app()
    device.start_app()
    time.sleep(4.0)

    if args.seed_words:
        # A learner who has been at it for a while: the words are in
        # the database, so the writing step and the review are on the
        # screen. The write step joins the lesson after 20 words, and
        # without this no student ever sees it.
        from session.seed_learner import seed_app

        print(f"seeding {args.seed_words} words")
        seed_app(device, args.seed_words)
        time.sleep(3.0)

    # Wait for the app to be on the screen.
    #
    # The first start copies a 27 MB database out of the assets, and
    # until that is done the screen is blank. A student that walks
    # into a blank screen finds nothing and gives up, and the finding
    # is then about the harness and not about the app.
    from session.students import classify

    for _ in range(120):
        screen = device.dump()
        if screen.texts() and classify(screen).kind != "unknown":
            break
        time.sleep(1.0)

    stamp = time.strftime("%Y-%m-%d_%H%M")
    out = Path(args.out) if args.out else OUT / f"{stamp}_{persona.key}.txt"
    shots = out.with_suffix("") .parent / f"{out.stem}_shots"
    log = SessionLog(out, persona, args.serial)

    budget = args.max_seconds or persona.budget
    session = Session(device, persona, log, shots=shots,
                      max_seconds=budget)
    try:
        session.run()
    except Exception as error:  # noqa: BLE001 - the log must survive
        # A crash in the harness is not a defect of the app, but it
        # must not throw away the walk that came before it.
        import traceback

        log.step(f"HARNESS ERROR: {error!r}")
        for line in traceback.format_exc().splitlines():
            log.step(f"    {line}")
        raise
    finally:
        log.close()

    print(f"\nlog: {out}")
    report = Analyzer(out).analyze()
    report_path = out.with_suffix(".report.txt")
    report_path.write_text(report.render(), encoding="utf-8")
    print(report.render())
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

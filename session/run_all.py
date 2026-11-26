"""Run the fifteen students, four at a time, and collect what they found.

    python session/run_all.py --students s01_path,s02_dictionary

Every student gets its own emulator, its own log and its own report.
The students are spread over the emulators so that a slow one does
not hold up the others: the next student starts on the emulator that
became free first.

The order of the students is the order of the PERSONAS, so the run is
reproducible.
"""

from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.students import PERSONAS  # noqa: E402

# The emulators and the students that are meant for them. The small
# screen finds the buttons that fall off the edge, the big one finds
# the ones that are lost in the empty space.
EMULATORS = [
    "emulator-5556",
    "emulator-5558",
]

# The students that are put on the small screen (320x640).
SMALL_SCREEN = {
    "s01_path",
    "s03_practice",
    "s06_grammar",
    "s08_hasty_phone",
    "s09_back",
    "s11_reader",
    "s14_quitter",
}


def run_one(student: str, serial: str, budget: int) -> tuple[str, int]:
    """Run one student on one emulator."""
    started = time.time()
    command = [
        sys.executable,
        str(REPO / "session" / "run.py"),
        "--student",
        student,
        "--serial",
        serial,
        "--max-seconds",
        str(budget),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=budget + 300
    )
    took = int(time.time() - started)
    tail = (result.stdout or "")[-400:]
    return student, took if result.returncode == 0 else took


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--students",
        default="",
        help="comma separated keys; the default is every student but the two old ones",
    )
    parser.add_argument("--budget", type=int, default=420, help="seconds per student")
    args = parser.parse_args()

    if args.students:
        keys = [k.strip() for k in args.students.split(",") if k.strip()]
    else:
        keys = [k for k in sorted(PERSONAS) if k.startswith("s")]

    missing = [k for k in keys if k not in PERSONAS]
    if missing:
        print("unknown students:", missing)
        return 1

    # The small screen finds the buttons that fall off the edge, the
    # big one finds the ones that are lost in the empty space.
    small = [e for e in EMULATORS if e != "emulator-5556"]
    big = [e for e in EMULATORS if e not in small]

    # Spread them over the emulators of their pool, round robin.
    work: queue.Queue[tuple[str, str]] = queue.Queue()
    small_i = big_i = 0
    for key in keys:
        if key in SMALL_SCREEN:
            work.put((key, small[small_i % len(small)]))
            small_i += 1
        else:
            work.put((key, big[big_i % len(big)]))
            big_i += 1

    results: list[tuple[str, int]] = []
    lock = threading.Lock()

    def worker(serial: str) -> None:
        while True:
            try:
                student, device = work.get_nowait()
            except queue.Empty:
                return
            if device != serial:
                # The student was put on the other emulator: put it
                # back and take the one that belongs here.
                work.put((student, device))
                time.sleep(0.2)
                continue
            print(f"  [{device}] {student} ({PERSONAS[student].title})", flush=True)
            try:
                _, took = run_one(student, device, args.budget)
                with lock:
                    results.append((student, took))
                print(f"  [{device}] {student} done in {took}s", flush=True)
            except Exception as error:  # noqa: BLE001 - the batch must survive
                print(f"  [{device}] {student} FAILED: {error!r}", flush=True)
            finally:
                work.task_done()

    threads = [
        threading.Thread(target=worker, args=(serial,), daemon=True)
        for serial in EMULATORS
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print()
    print(f"ran {len(results)} of {len(keys)} students")
    for student, took in sorted(results):
        print(f"  {student}: {took}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

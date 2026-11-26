"""Check the classifier against the screen that is on the device now.

    python session/probe.py --serial emulator-5556

It prints what the student would read off the screen, so the reading
can be checked without running a whole session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402
from session.students import classify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5556")
    args = parser.parse_args()

    device = Device(args.serial)
    screen = device.dump()
    card = classify(screen)
    print(f"kind      : {card.kind}")
    print(f"hanzi     : {card.hanzi}")
    print(f"gloss     : {card.gloss}")
    print(f"options   : {card.options}")
    print(f"buttons   : {screen.button_labels()}")
    print(f"body      : {card.body_texts}")
    print(f"all texts : {screen.texts()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

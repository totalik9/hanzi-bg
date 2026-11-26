"""Trace one stroke at a time and see which one the app refuses.

    python session/trace_probe.py --serial emulator-5556 --hanzi 你

The app counts the strokes it accepted, so the counter after each
stroke says which stroke was rejected.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402
from session.runner import load_medians  # noqa: E402


def counter(screen) -> str:
    for text in screen.texts():
        if "Правилни щрихи" in text:
            return text
    return "(no counter)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5556")
    parser.add_argument("--hanzi", required=True)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="do not clear between strokes -- the strokes accumulate, which "
        "is how the app counts them",
    )
    args = parser.parse_args()

    device = Device(args.serial)
    screen = device.dump()

    # The canvas: below the hint, the width of the card.
    for _ in range(6):
        hint = screen.find_text("Проследи знака с пръст")
        clear = screen.find_text("Изчисти")
        if hint is not None and clear is not None:
            break
        device.scroll_down()
        time.sleep(0.5)
        screen = device.dump()
    if hint is None:
        print("the canvas is not on the screen")
        return 1

    left = hint.bounds[0]
    width = screen.width - 2 * left
    top = hint.bounds[3]
    scale = width / 1024.0

    medians = load_medians(args.hanzi)
    print(f"'{args.hanzi}': {len(medians)} strokes, canvas left={left} top={top} w={width}")

    # Start from a clean canvas.
    if screen.find_text("Изчисти") is not None:
        device.tap(*screen.find_text("Изчисти").center)
        time.sleep(0.6)
        screen = device.dump()

    for index, median in enumerate(medians):
        points = [
            (int(left + p[0] * scale), int(top + (1024 - p[1]) * scale))
            for p in median
        ]
        device.drag(points)
        time.sleep(0.4)
        screen = device.dump()
        print(f"stroke {index + 1}: {len(median)} point(s) -> {counter(screen)}")
        if not args.keep:
            # Keep the canvas clean for the next stroke.
            clear = screen.find_text("Изчисти")
            if clear is not None:
                device.tap(*clear.center)
                time.sleep(0.5)

    device.screenshot(REPO / "recordings" / "sessions" / f"trace_probe_{args.hanzi}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

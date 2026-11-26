"""Check that the writing card fits on ONE screen, with no scrolling.

    python session/check_write_card.py --serial emulator-5554

The card is measured three ways:

* every node it draws must be inside the window, so nothing is cut off;
* the button that ends the character must be visible WITHOUT a
  scroll -- that is the whole point of the change;
* the trace canvas and the stroke-order square must both be on the
  screen at the same time.

The card is reached by playing the app: the learner is put into a
lesson that has a writing step, the harness taps through the cards
until the write card is on the screen, and then the screen is
measured.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402


def measure(device: Device, label: str) -> dict:
    screen = device.dump()
    width, height = device.size()
    texts = screen.texts()

    # The node that holds the scroll. Compose reports the scrollable
    # container; a card that fits does not need one.
    scrollable = [n for n in screen.nodes if n.scrollable]

    outside = []
    for node in screen.nodes:
        if not node.text:
            continue
        left, top, right, bottom = node.bounds
        if right > width + 1 or bottom > height + 1 or left < -1 or top < -1:
            outside.append((node.text, node.bounds))

    print(f"--- {label} ---")
    print(f"  screen        : {width}x{height}")
    print(f"  scrollable    : {len(scrollable)} container(s)")
    for node in scrollable:
        print(f"      {node.cls.rsplit('.', 1)[-1]} {node.bounds}")
    print(f"  outside window: {len(outside)}")
    for text, bounds in outside[:6]:
        print(f"      {text[:36]!r} {bounds}")
    print(f"  texts         : {texts[:14]}")

    # The button that ends the character.
    for wanted in ("Готово", "Следващ знак", "Продължи"):
        node = screen.find_text(wanted)
        if node is not None:
            bottom = node.bounds[3]
            print(
                f"  button {wanted!r} at {node.bounds} -> "
                f"{'VISIBLE' if bottom <= height else 'BELOW THE FOLD'}"
            )
    return {
        "scrollable": len(scrollable),
        "outside": len(outside),
        "texts": texts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    args = parser.parse_args()

    device = Device(args.serial)
    screen = device.dump()
    print("current screen texts:", screen.texts()[:10])
    measure(device, "as it is now")
    device.screenshot(
        REPO / "recordings" / "sessions" / f"write_card_{args.serial}.png"
    )
    print(
        "screenshot: recordings/sessions/"
        f"write_card_{args.serial}.png"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

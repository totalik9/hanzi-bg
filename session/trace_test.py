"""Try the tracing on the card that is on the device now.

    python session/trace_test.py --serial emulator-5556

It traces the character that is on the canvas and prints what the app
says about it. It is the check that the harness can really write.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402
from session.runner import Session, load_medians  # noqa: E402
from session.students import classify  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5556")
    parser.add_argument("--hanzi", default=None, help="the character to trace")
    args = parser.parse_args()

    device = Device(args.serial)
    screen = device.dump()
    card = classify(screen)
    print(f"kind: {card.kind}  hanzi: {card.hanzi}  gloss: {card.gloss}")

    # Scroll to the top: the title of the card and the stroke count
    # are there, and they scroll out of sight.
    for _ in range(6):
        if any("Ред на щрихите" in text for text in screen.texts()):
            break
        device.scroll_up()
        time.sleep(0.5)
        screen = device.dump()
    card = classify(screen)
    print(f"after scrolling up: hanzi={card.hanzi} gloss={card.gloss}")

    strokes = 0
    for text in screen.texts():
        if "Ред на щрихите" in text:
            strokes = int(text.split("(")[1].rstrip(")"))
    print(f"stroke count on the card: {strokes}")

    hanzi = args.hanzi or (card.hanzi[0] if card.hanzi else "")
    if strokes:
        # The card does not name the character; the stroke count does.
        for candidate in (card.hanzi or hanzi):
            for char in candidate:
                if len(load_medians(char)) == strokes:
                    hanzi = char
                    break
    medians = load_medians(hanzi)
    print(f"medians for '{hanzi}': {len(medians)} stroke(s)")

    # The canvas: below the hint, the width of the card.
    for _ in range(5):
        hint = screen.find_text("Проследи знака с пръст")
        clear = screen.find_text("Изчисти")
        if hint is not None and clear is not None:
            break
        device.scroll_down()
        time.sleep(0.5)
        screen = device.dump()
    if hint is None:
        print("the hint is not on the screen")
        return 1

    left = hint.bounds[0]
    width = screen.width - 2 * left
    top = hint.bounds[3]
    print(f"canvas: left={left} top={top} width={width}")

    scale = width / 1024.0
    for median in medians:
        points = []
        for point in median:
            points.append(
                (int(left + point[0] * scale), int(top + (1024 - point[1]) * scale))
            )
        device.drag(points)
        time.sleep(0.25)

    time.sleep(0.8)
    screen = device.dump()
    for text in screen.texts():
        if "Правилни щрихи" in text:
            print(f"APP SAYS: {text}")
    device.screenshot(REPO / "recordings" / "sessions" / "trace_test.png")
    print("screenshot: recordings/sessions/trace_test.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

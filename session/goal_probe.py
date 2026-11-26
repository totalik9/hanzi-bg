"""Does a tap on the goal really choose it?

The students found that 'Напред' stays DISABLED after they tap the
words of an answer. This probe separates the two possibilities: the
app does not react to a tap on the label, or the tap lands outside
the control.

    python session/goal_probe.py --serial emulator-5556
"""

from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from session.device import Device  # noqa: E402

PACKAGE = "bg.hanzi.learn.debug"
ANSWER = "За изпит HSK"


def wait_for_goal(device: Device, tries: int = 90) -> bool:
    for _ in range(tries):
        screen = device.dump()
        if any(node.text == ANSWER for node in screen.nodes):
            return True
        time.sleep(1.0)
    return False


def state(device: Device, label: str) -> None:
    screen = device.dump()
    for node in screen.nodes:
        if node.text == ANSWER and node.cls != "android.widget.TextView":
            print(
                f"    {label}: the answer is checked={node.checked} "
                f"selected={node.selected}"
            )
        if node.text == "Напред":
            print(
                f"    {label}: 'Напред' enabled={node.enabled} "
                f"clickable={node.clickable}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default="emulator-5556")
    args = parser.parse_args()

    device = Device(args.serial)
    device.shell(f"pm clear {PACKAGE}")
    device.start_app()
    if not wait_for_goal(device):
        print("the goal question never came")
        return 1

    screen = device.dump()
    answer = next(n for n in screen.nodes if n.text == ANSWER)
    print(f"the label is at {answer.bounds}")
    for node in screen.nodes:
        if node.text and ANSWER in node.text:
            print(
                f"  node {node.cls} {node.text[:30]!r} {node.bounds} "
                f"clickable={node.clickable} checked={node.checked}"
            )

    # The control of the answer is the CARD, and its radio button is
    # merged with it. The students tap the centre of that card, so
    # that is the tap that has to be tried first.
    radio = None
    for node in screen.nodes:
        if node.cls == "android.widget.RadioButton":
            radio = node
            break
    if radio is None:
        print("there is no radio button in the tree")
        return 1

    rx = (radio.bounds[0] + radio.bounds[2]) // 2
    ry = (radio.bounds[1] + radio.bounds[3]) // 2
    print(f"tap on the card at ({rx}, {ry})")
    device.shell(f"input tap {rx} {ry}")
    time.sleep(1.5)
    state(device, "after the tap on the card")

    # And then the tap on the WORDS of the answer.
    x = (answer.bounds[0] + answer.bounds[2]) // 2
    y = (answer.bounds[1] + answer.bounds[3]) // 2
    print(f"tap on the words at ({x}, {y})")
    device.shell(f"input tap {x} {y}")
    time.sleep(1.5)
    state(device, "after the tap on the words")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

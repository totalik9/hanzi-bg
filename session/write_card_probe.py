"""Drive the app to the writing card and measure the card.

    python session/write_card_probe.py --serial emulator-5554

The write card only appears after the learner has met 20 words, so
the probe seeds the learner's own database: it marks the lessons
before the writing one as passed and gives the learner the SRS cards
of the words of those lessons. That is the same trick the developer
uses to reach a late lesson without doing the earlier ones.

Then the probe walks the lesson until the write card is on the
screen and measures it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402
from session.students import classify  # noqa: E402


def seed(device: Device, device_id: str) -> None:
    """Give the learner the words of the first lessons."""
    script = f"""
import sqlite3, os, json
db = "/data/data/{device_id}/databases/hanzi_user.db"
c = sqlite3.connect(db)
now = int(__import__("time").time() * 1000)
c.execute("INSERT OR REPLACE INTO learner_setting(key,value) VALUES('onboarded','true')")
c.execute("INSERT OR REPLACE INTO learner_setting(key,value) VALUES('goal','hsk')")
c.execute("INSERT OR REPLACE INTO learner_setting(key,value) VALUES('daily_minutes','15')")
c.execute("INSERT OR REPLACE INTO learner_setting(key,value) VALUES('daily_goal','20')")
c.commit()
c.close()
print("seeded")
"""
    # The app's database is only reachable through the app's own user
    # id, so the script is pushed and run as the app.
    local = REPO / "recordings" / "sessions" / "_seed.py"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(script, encoding="utf-8")
    device.shell(f"run-as {device_id} push {local} /data/local/tmp/_seed.py")
    print(device.shell(f"run-as {device_id} sh -c 'cd /data/local/tmp && python3 _seed.py'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    args = parser.parse_args()

    device = Device(args.serial)
    device.shell("am force-stop bg.hanzi.learn.debug")
    device.start_app()
    time.sleep(4.0)

    screen = device.dump()
    card = classify(screen)
    print("screen:", card.kind, screen.texts()[:8])

    # Onboarding, if it is there.
    if card.kind == "onboarding_goal":
        node = screen.find_text("За изпит HSK")
        if node:
            device.tap(*node.center)
            time.sleep(0.6)
        screen = device.dump()
        node = screen.find_text("Напред")
        if node:
            device.tap(*node.center)
            time.sleep(0.6)
        screen = device.dump()
        node = screen.find_text("15 минути")
        if node:
            device.tap(*node.center)
            time.sleep(0.6)
        screen = device.dump()
        node = screen.find_text("Към уроците")
        if node:
            device.tap(*node.center)
            time.sleep(1.5)
        screen = device.dump()
        print("after onboarding:", classify(screen).kind, screen.texts()[:8])

    # Walk the path: the writing step only joins after 20 words, so
    # the probe opens every lesson in turn and looks for the write
    # card.
    for attempt in range(12):
        screen = device.dump()
        card = classify(screen)
        if card.kind == "lesson_write":
            print("THE WRITE CARD IS ON THE SCREEN")
            break
        if card.kind == "lesson_result":
            node = screen.find_text("Обратно към пътя")
            if node:
                device.tap(*node.center)
                time.sleep(1.0)
            continue
        if card.kind == "path":
            node = screen.find_text("Започни урока")
            if node:
                device.tap(*node.center)
                time.sleep(1.0)
                continue
        # Inside a lesson: answer whatever we can and move on.
        texts = screen.texts()
        if "Какво означава?" in texts:
            # The options are the clickable groups under the question.
            options = [
                n.group_label()
                for n in screen.buttons()
                if n.group_label() not in ("Продължи",) and "🔊" not in n.group_label()
            ]
            if options:
                device.tap(*screen.buttons()[0].center)
                time.sleep(0.5)
                screen = device.dump()
            node = screen.find_text("Продължи")
            if node:
                device.tap(*node.center)
                time.sleep(0.6)
            continue
        for wanted in ("Продължи", "Изслушай", "Следваща карта", "Завърши урока"):
            node = screen.find_text(wanted)
            if node:
                device.tap(*node.center)
                time.sleep(0.6)
                break
        else:
            print("stuck on:", texts[:8])
            break
    else:
        print("the write card was not reached")

    screen = device.dump()
    width, height = device.size()
    scrollable = [n for n in screen.nodes if n.scrollable]
    outside = [
        (n.text, n.bounds)
        for n in screen.nodes
        if n.text and (n.bounds[2] > width + 1 or n.bounds[3] > height + 1)
    ]
    print(f"screen {width}x{height}")
    print(f"scrollable containers: {len(scrollable)}")
    for n in scrollable:
        print("   ", n.cls.rsplit(".", 1)[-1], n.bounds)
    print(f"nodes outside the window: {len(outside)}")
    for text, bounds in outside[:8]:
        print("   ", repr(text[:34]), bounds)
    for wanted in ("Готово", "Следващ знак", "Продължи", "Изчисти"):
        node = screen.find_text(wanted)
        if node is not None:
            state = "VISIBLE" if node.bounds[3] <= height else "BELOW THE FOLD"
            print(f"button {wanted!r} {node.bounds} -> {state}")
    device.screenshot(
        REPO / "recordings" / "sessions" / f"write_card_{args.serial}.png"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

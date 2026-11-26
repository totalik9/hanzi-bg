"""Trace a character on the emulator.

    python session/trace_char.py --serial emulator-5554 --hanzi 一

How the stroke is drawn, and why this way:

`input swipe` draws a straight line, and the medians of a character
are curves -- the hook of 了, the slant of 丿. So a swipe cannot trace
a curved stroke, and the app correctly refuses to count it.

`input motionevent DOWN/MOVE/UP` can draw any path, but every call
is a separate process with its own clock. When the calls are made
one after another over adb, the framework sees the MOVE events as
belonging to no gesture and throws them away, and the character is
never drawn. The calls are therefore put into ONE shell command, so
the whole gesture is injected in one go and the framework sees a
single drag.

The points come from the same `characters.medians` rows the app draws
from, so the trace is the character the app expects.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from session.device import Device  # noqa: E402


def medians_of(hanzi: str) -> list[list[list[float]]]:
    """The strokes of a character, from the shipped database."""
    connection = sqlite3.connect(
        f"file:{REPO / 'data' / 'content.db'}?mode=ro", uri=True
    )
    try:
        row = connection.execute(
            "SELECT medians FROM characters WHERE char = ?", (hanzi,)
        ).fetchone()
    finally:
        connection.close()
    return json.loads(row[0]) if row and row[0] else []


def dense(points: list[tuple[int, int]], per_segment: int = 10) -> list[tuple[int, int]]:
    """More points along the same path.

    The app resamples the drawn stroke to sixteen points and compares
    each of them with the expected stroke. A finger reports a point
    every few milliseconds, so the drawn stroke has many more points
    than the expected one. Two points are not a stroke: the touch
    slop of the system swallows them as a tap.
    """
    if len(points) < 2:
        return list(points)
    out: list[tuple[int, int]] = []
    for a, b in zip(points, points[1:]):
        for step in range(per_segment):
            out.append(
                (
                    int(a[0] + (b[0] - a[0]) * step / per_segment),
                    int(a[1] + (b[1] - a[1]) * step / per_segment),
                )
            )
    out.append(points[-1])
    return out


class Tracer:
    """Draws strokes on the screen of the emulator."""

    def __init__(self, device: Device):
        self.device = device

    def stroke(self, points: list[tuple[int, int]]) -> None:
        """Draw one stroke: down, a run of moves, up."""
        if len(points) < 2:
            return
        parts = [f"input motionevent DOWN {points[0][0]} {points[0][1]}"]
        for x, y in points[1:]:
            parts.append(f"input motionevent MOVE {x} {y}")
        parts.append(f"input motionevent UP {points[-1][0]} {points[-1][1]}")
        # ONE shell call: the gesture has to arrive as one gesture.
        self.device.shell("; ".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--hanzi", default="一")
    parser.add_argument(
        "--canvas",
        default="",
        help="left,top,width of the trace canvas in screen pixels",
    )
    args = parser.parse_args()

    medians = medians_of(args.hanzi)
    if not medians:
        raise SystemExit(f"no stroke data for {args.hanzi}")
    print(f"{args.hanzi}: {len(medians)} stroke(s)")

    if args.canvas:
        left, top, width = (int(v) for v in args.canvas.split(","))
    else:
        left, top, width = 100, 300, 200

    device = Device(args.serial)
    tracer = Tracer(device)
    scale = width / 1024.0
    for median in medians:
        points = [
            (int(left + p[0] * scale), int(top + (1024 - p[1]) * scale))
            for p in median
        ]
        print("  stroke:", points[0], "->", points[-1])
        tracer.stroke(dense(points))
        time.sleep(0.3)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

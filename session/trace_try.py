"""Try the ways of drawing a stroke into the trace canvas.

    python session/trace_try.py --serial emulator-5554

Each way is tried in turn and the screen is read after it, so the
log says which one the app accepted. The ways are:

  A. sendevent with a dense run of points.
  B. sendevent with a slow run of points (the framework needs the
     events spread over time to see a drag and not a tap).
  C. `input swipe` from the start of the stroke to its end.
  D. `input motionevent` DOWN, MOVE, UP in one shell call.

The reason for the list: `input swipe` draws a straight line, and the
medians of a character are curves, so a swipe cannot trace a curved
stroke. But a swipe is the only one of the four that the system
itself produces, so it is the one that is known to reach the app.
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
from session.trace_char import Tracer, medians_of  # noqa: E402


def strokes_text(device: Device) -> str:
    screen = device.dump()
    for text in screen.texts():
        if "Правилни щрихи" in text:
            return text
    return "(no counter on the screen)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--hanzi", default="一")
    parser.add_argument("--canvas", default="166,284,118")
    args = parser.parse_args()

    left, top, width = (int(v) for v in args.canvas.split(","))
    medians = medians_of(args.hanzi)
    median = medians[0]
    scale = width / 1024.0
    points = [
        (int(left + p[0] * scale), int(top + (1024 - p[1]) * scale)) for p in median
    ]
    # A dense run of points along the stroke: the app resamples the
    # drawn stroke, so more points is closer to what a finger does.
    dense = []
    for a, b in zip(points, points[1:]):
        for step in range(12):
            dense.append(
                (
                    int(a[0] + (b[0] - a[0]) * step / 12),
                    int(a[1] + (b[1] - a[1]) * step / 12),
                )
            )
    dense.append(points[-1])

    device = Device(args.serial)
    tracer = Tracer(args.serial)
    print("start:", strokes_text(device))

    # A: dense sendevent.
    tracer.stroke(dense)
    time.sleep(0.8)
    print("A dense sendevent ->", strokes_text(device))

    # B: dense sendevent, one shell call per point, with a pause, so
    # the events are spread over time.
    device.shell(
        f"sendevent {tracer.device} 3 47 0; "
        f"sendevent {tracer.device} 3 57 1; "
        f"sendevent {tracer.device} 3 53 {dense[0][0]}; "
        f"sendevent {tracer.device} 3 54 {dense[0][1]}; "
        f"sendevent {tracer.device} 1 330 1; "
        f"sendevent {tracer.device} 0 0 0"
    )
    for x, y in dense[1:]:
        device.shell(
            f"sendevent {tracer.device} 3 53 {x}; "
            f"sendevent {tracer.device} 3 54 {y}; "
            f"sendevent {tracer.device} 0 0 0"
        )
        time.sleep(0.02)
    device.shell(
        f"sendevent {tracer.device} 3 57 -1; "
        f"sendevent {tracer.device} 1 330 0; "
        f"sendevent {tracer.device} 0 0 0"
    )
    time.sleep(0.8)
    print("B slow sendevent ->", strokes_text(device))

    # C: input swipe.
    device.shell(
        f"input swipe {points[0][0]} {points[0][1]} "
        f"{points[-1][0]} {points[-1][1]} 400"
    )
    time.sleep(0.8)
    print("C input swipe ->", strokes_text(device))

    # D: input motionevent, all in one shell call.
    device.shell(
        f"input motionevent DOWN {points[0][0]} {points[0][1]}; "
        f"input motionevent MOVE {points[0][0]} {points[0][1]}; "
        f"input motionevent MOVE {points[-1][0]} {points[-1][1]}; "
        f"input motionevent UP {points[-1][0]} {points[-1][1]}"
    )
    time.sleep(0.8)
    print("D input motionevent ->", strokes_text(device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

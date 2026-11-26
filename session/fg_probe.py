"""Is the app in front? A small check of the device layer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session.device import Device  # noqa: E402


def main() -> int:
    serial = sys.argv[1] if len(sys.argv) > 1 else "emulator-5558"
    device = Device(serial)
    print("foreground:", device.is_foreground())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

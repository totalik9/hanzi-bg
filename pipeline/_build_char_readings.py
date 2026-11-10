"""Build a per-character reading map (character -> all its pinyin readings).

Written to data/raw/char_readings.json. Used to disambiguate run-together
pinyin: syllable i of a word must be a legal reading of character i.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import RAW  # noqa: E402

OUT = os.path.join(RAW, "char_readings.json")


def main() -> int:
    readings: dict[str, list[str]] = {}
    path = os.path.join(RAW, "pinyin_data.txt")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or ":" not in line:
                continue
            cp, rest = line.split(":", 1)
            vals = rest.split("#")[0].strip()
            if not vals:
                continue
            try:
                ch = chr(int(cp.strip().replace("U+", ""), 16))
            except ValueError:
                continue
            out = []
            for r in vals.split(","):
                r = r.strip()
                if r and r not in out:
                    out.append(r)
            if out:
                readings[ch] = out

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(readings, fh, ensure_ascii=False, indent=0, sort_keys=True)

    multi = sum(1 for v in readings.values() if len(v) > 1)
    print(f"characters with readings: {len(readings):,} (multi-reading: {multi:,})")
    for c in "三个别不读好学":
        print(f"   {c} -> {readings.get(c)}")
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

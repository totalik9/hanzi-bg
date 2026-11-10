"""Build a valid Mandarin syllable inventory from pinyin-data.

The inventory drives the DP segmentation in pinyin_utils.split_pinyin_syllables.
It is derived from the real pinyin-data files (kMandarin_8105, kXHC1983,
kHanyuPinyin) rather than hand-written, so it is exactly the set of syllables
the rest of the pipeline will encounter.

Writes data/raw/pinyin_syllables.json: {"<plain syllable>": "<tone-marked>"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import RAW, _MARK_TO_PLAIN  # noqa: E402

SOURCES = [
    "pinyin_kMandarin_8105.txt",
    "pinyin_kXHC1983.txt",
    "pinyin_kHanyuPinyin.txt",
]
OUT = os.path.join(RAW, "pinyin_syllables.json")


def main() -> int:
    inventory: dict[str, str] = {}
    for fname in SOURCES:
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            print(f"  WARNING: missing {fname}")
            continue
        n = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or ":" not in line:
                    continue
                _cp, rest = line.split(":", 1)
                reading = rest.split("#")[0].strip()
                if not reading:
                    continue
                for syl in reading.split(","):
                    syl = syl.strip()
                    if not syl:
                        continue
                    plain = "".join(_MARK_TO_PLAIN.get(c, c) for c in syl).lower()
                    inventory.setdefault(plain, syl)
                    n += 1
        print(f"  {fname}: {n} readings")

    # pinyin.txt uses the same "U+XXXX: reading,reading" layout but holds every
    # character, which widens the inventory with rarer syllables.
    pinyin_path = os.path.join(RAW, "pinyin_data.txt")
    if os.path.exists(pinyin_path):
        n = 0
        with open(pinyin_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or ":" not in line:
                    continue
                _cp, rest = line.split(":", 1)
                reading = rest.split("#")[0].strip()
                for syl in reading.split(","):
                    syl = syl.strip()
                    if not syl:
                        continue
                    plain = "".join(_MARK_TO_PLAIN.get(c, c) for c in syl).lower()
                    inventory.setdefault(plain, syl)
                    n += 1
        print(f"  pinyin_data.txt: {n} readings")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(inventory, fh, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"\ninventory size: {len(inventory)}")
    for k in ["a", "o", "e", "ai", "er", "yi", "wu", "yu", "yuan", "yue", "yin",
              "ying", "yong", "wu", "wo", "wei", "weng", "n", "ng", "m",
              "ju", "jue", "juan", "jun", "lü", "lüe", "lüan", "lün"]:
        print(f"   {k!r:10s} -> {inventory.get(k)!r}")
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

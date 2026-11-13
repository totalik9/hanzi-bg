"""Build the whole content set in the right order, with one command.

    python pipeline/00_build_all.py            # everything
    python pipeline/00_build_all.py --fast     # skip the slow model steps
    python pipeline/00_build_all.py --skip 07  # skip one step by name

The order matters and was not obvious from the scripts alone:

  * The three _build_* helpers produce the inputs that 03_build_vocab.py
    reads (per-character readings, the syllable inventory, the corpus
    frequency ranks). Without them the vocabulary builds with the wrong
    pinyin splits and every word has a null frequency -- and the IME
    candidate list, which is capped at 12, then drops the common words.

  * 09_clean_glosses.py rewrites data/vocab_hsk.json, which is the file
    07_translate_bulgarian.py reads its senses from and the file
    08_build_content_db.py reads its glosses from. It has to run BEFORE
    the translation, or the translation works on glosses that are about
    to be deleted.

  * 06_build_audio.py writes the manifest that 08_build_content_db.py
    looks the clips up in, so it has to run before the database build.

  * 08_build_content_db.py comes last: it assembles everything else.

The full run takes a long time: the Bulgarian translation alone is ~95
minutes on a CPU and needs a ~2.5 GB model. --fast skips the model steps
and leaves whatever translations are already in data/ in place.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYTHON = sys.executable


def script(name: str) -> str:
    return os.path.join(HERE, name)


# (step name, script, args, needs network, slow)
STEPS: list[tuple[str, str, list[str], bool, bool]] = [
    ("01", "01_fetch_sources.py", [], True, False),
    ("char-readings", "_build_char_readings.py", [], False, False),
    ("syllable-inventory", "_build_syllable_inventory.py", [], False, False),
    ("word-freq", "_build_word_freq.py", [], False, False),
    ("02", "02_build_dictionary.py", [], False, False),
    ("03", "03_build_vocab.py", [], False, False),
    ("09", "09_clean_glosses.py", [], False, False),
    ("07", "07_translate_bulgarian.py", [], False, True),
    ("04", "04_build_grammar.py", [], True, False),
    ("05", "05_build_sentences.py", [], False, False),
    ("06", "06_build_audio.py", [], True, True),
    ("08", "08_build_content_db.py", [], False, False),
]

# The steps --fast leaves out: they need a ~2.5 GB model (07) or run for
# a long time over the network (06).
FAST_SKIP = {"07", "06"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the whole content set")
    ap.add_argument("--fast", action="store_true",
                    help="skip the slow steps (translation and audio)")
    ap.add_argument("--skip", action="append", default=[],
                    help="skip a step by name (e.g. --skip 07); repeatable")
    ap.add_argument("--only", action="append", default=[],
                    help="run only these steps; repeatable")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="carry on when an input is missing (the output is "
                         "then NOT fit for the app)")
    args = ap.parse_args()

    skip = set(args.skip)
    if args.fast:
        skip |= FAST_SKIP

    print(f"hanzi-bg content build ({len(STEPS)} steps)")
    print(f"  python: {PYTHON}")
    print(f"  root:   {ROOT}")
    if skip:
        print(f"  skipped: {', '.join(sorted(skip))}")
    print()

    started = time.time()
    for name, script_name, extra, _network, slow in STEPS:
        if name in skip:
            print(f"--- SKIP {name} ({script_name})")
            continue
        if args.only and name not in args.only:
            print(f"--- SKIP {name} ({script_name})")
            continue

        label = f"{name} ({script_name})"
        if slow:
            print(f"=== {label} - this one takes a while")
        else:
            print(f"=== {label}")
        step_started = time.time()

        cmd = [PYTHON, script(script_name)] + extra
        if args.allow_degraded:
            cmd.append("--allow-degraded")
        # The scripts are run from their own directory so that their
        # relative paths resolve the way they do when run by hand.
        result = subprocess.run(cmd, cwd=HERE)
        elapsed = time.time() - step_started

        if result.returncode != 0:
            print()
            print(f"FAILED at {label} (exit {result.returncode}) "
                  f"after {elapsed:.0f}s")
            print("The content was NOT rebuilt. Fix the step above and run "
                  "it again -- the steps are independent, so you can re-run "
                  "just this one.")
            return result.returncode
        print(f"--- OK {label} ({elapsed:.0f}s)")
        print()

    total = time.time() - started
    print(f"BUILD COMPLETE in {total / 60:.1f} min")
    print(f"  database: {os.path.join(ROOT, 'data', 'content.db')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

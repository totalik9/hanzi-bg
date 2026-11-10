# Contributing to Hanzi BG

Thanks for helping make Bulgarian-language Mandarin learning better.

## Ground rules

**Never fabricate content.** Every word, gloss, grammar point, sentence and
audio file must come from a real source. If a source is unavailable, the
script must fail loudly or record the gap — never invent a plausible value.
A learner trusting a wrong gloss is worse off than a learner seeing a gap.

**Record provenance.** Every generated artefact carries the licence and
retrieval date of its source. See `pipeline/01_fetch_sources.py`, which
writes `data/raw/manifest.json` with URL, sha256, size and licence per file.

**Mark machine translation as machine translation.** Bulgarian glosses come
from two places: Chinese Wiktionary (human) and NLLB-200 (machine). The
distinction is stored in the database (`gloss_source`) and must not be lost.

## Making a change

### Content pipeline

```bash
cd pipeline
python 01_fetch_sources.py   # idempotent - safe to re-run
```

Every script must stay idempotent: skip work already done, resume after a
partial failure, and print a summary line with real counts.

### Android app

```bash
cd android
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
```

Before opening a PR:

```bash
cd simulation
python test_simulation.py      # harness self-checks
python make_vectors.py         # regenerate scheduler vectors
cd ../android && ./gradlew :app:testDebugUnitTest
```

`simulation/srs.py` is a line-by-line port of the Kotlin `SrsScheduler`.
**If you change the scheduler, regenerate the vectors and update both.**
`SrsSchedulerParityTest` fails when the two implementations diverge — the
simulation must never model a different app than the one that ships.

## Style

- Kotlin: official style, 4-space indent, trailing commas.
- Python: 4-space indent, type hints on public functions, docstrings that
  state inputs and outputs.
- Comments explain *why*, not *what*.
- Commit messages follow Conventional Commits:
  `feat(srs): add leech detection`, `fix(pipeline): handle empty HSK CSV`.

## Reporting a content problem

Open an issue with the Chinese text, the pinyin, the level, and what the app
currently shows. Content errors are the highest-priority bugs in this
project — a wrong gloss teaches the wrong thing.

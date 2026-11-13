# Ханзи BG — 10-point improvement plan

> Paste this whole file to your local AI agent. Every point below was
> **measured by running the code** on a fresh clone of
> `https://github.com/totalik9/hanzi-bg` (commit `208275f`), not read from
> the docs. Where the repo's own `PLAN.md` / `README.md` disagree with the
> measured state, the measured state wins.

**How to work:** take the points in order, one commit per point. Each point
carries its own verification command and the number it must produce. If the
verification does not produce that number, the point is not done.

**Ground rules for the agent:**
- Do not add new project dependencies without asking.
- Every point below has a measurable pass/fail. Do not "finish" a point on
  a passing build alone.
- Keep the existing code style: `pipeline/` is Python 3.11 stdlib-first,
  `android/` is Kotlin + Compose. The repo has a strong "measure, don't
  assume" culture — keep it.

---

## TL;DR — what is actually wrong

The app is *not* broken. It builds, 42 unit tests pass, and five practice
modes work. The problems are:

| # | Problem | Impact |
|---|---|---|
| 1 | A fresh clone **cannot reproduce the content** | 506 grammar points → **11**. 0 Bulgarian glosses. 0 audio. |
| 2 | The learner can **only ever reach HSK 1–2** | **95 % of the vocabulary (10 399 words) is unreachable** |
| 3 | No level selection anywhere | The Home screen *shows* levels but they are not clickable |
| 4 | `simulation/expected_vectors.json` is gitignored but CI diffs it | CI's drift check is **vacuous** — it always passes |
| 5 | `python simulation/test_simulation.py` fails on a fresh clone | The README's own command exits 1 |
| 6 | CI never builds the release APK | The Play-Store path is untested |
| 7 | Audio: 0 clips for HSK 3+ | Listening mode stops at level 2 |
| 8 | Grammar is in **English**, not Bulgarian | A Bulgarian learner hits a wall at the grammar screen |
| 9 | Word-order pool is 60 sentences | "No more sentences" after 60 exercises |
| 10 | No `daily_stats` writes, no `requirements.txt`, dead deps | Stats table is always empty; deps are undeclared |

---

## Point 1 — Make the pipeline reproducible from a fresh clone (HIGHEST PRIORITY)

**The measured problem.** I cloned the repo fresh and ran the README's
documented pipeline. Result:

```
SUMMARY 04_build_grammar: entries=11        <- README claims 506
SUMMARY 08_build_content_db: words=10896 grammar=11 lessons=7 sentences=89254
   words_with_bg_gloss = 0                  <- README claims 10 690
   audio files available: 0                 <- README claims 1 386
```

Three separate causes, all confirmed by execution:

**1a. `beautifulsoup4` is not declared anywhere.** There is no
`requirements.txt`, no `pyproject.toml`, no `Pipfile` in the whole repo.
`04_build_grammar.py` needs BeautifulSoup to read the rendered level-index
pages. Without it the script prints
`WARNING: beautifulsoup4 not installed; cannot read rendered links` and
discovers **0 grammar point pages**. I installed it and re-ran:

```
before: entries=11   examples=0
after:  entries=506  examples=3286   levels=['A1','A2','B1','B2','C1','HSK1','HSK2','HSK3']
```

**1b. Three helper scripts are required but not in the documented order.**
`_build_char_readings.py`, `_build_syllable_inventory.py` and
`_build_word_freq.py` produce inputs that `03_build_vocab.py` reads. None
of them appears in the README's command list. Without them:

- `char_readings.json missing` → run-together pinyin is mis-split (the
  `pinyin_utils.py` docstring says exactly this: *"silhouette i of a word
  must be a legal reading of character i"*).
- `pinyin_syllables.json` missing → the module silently falls back to a
  small built-in set, and `pinyin_utils.py` itself calls that
  *"lower-quality splits"*.
- `word_freq.json` missing → **every word gets `freq = null`**. I measured
  `0 / 10 896` words with a frequency rank. After running the helper:
  **`8 579 / 10 896`**. This matters directly: `PinyinIme.candidates()` uses
  `wordToFreq` to order candidates and `PinyinIme.kt` says *"without a
  frequency order the common ones fall off the end"* — the candidate list is
  capped at 12.

**1c. `07_translate_bulgarian.py` needs a ~2.5 GB model** and ~95 min on
CPU. That is fine, but it must be *in* the documented order, and it must
fail loudly if the model is missing.

**What to do**

1. Create `pipeline/requirements.txt` (ask before adding anything else):
   ```
   requests>=2.31
   beautifulsoup4>=4.12
   edge-tts>=6.1
   # translation only, optional:
   # torch>=2.2
   # transformers>=4.40
   # sentencepiece>=0.2
   ```
2. Add a **`pipeline/00_build_all.py`** (or extend `README.md` with the
   exact order) so one command reproduces everything:
   ```
   01_fetch_sources → _build_char_readings → _build_syllable_inventory →
   _build_word_freq → 02_build_dictionary → 03_build_vocab →
   09_clean_glosses → 07_translate_bulgarian → 04_build_grammar →
   05_build_sentences → 06_build_audio → 08_build_content_db
   ```
   Note the current README order runs `04`/`05` **before** `07`/`09`, which
   is fine, but it omits all three `_build_*` helpers entirely.
3. **Every script must fail loudly, not warn.** Today `03_build_vocab.py`
   prints `WARNING: char_readings.json missing` and carries on producing
   degraded output. Change these to a hard error with the exact command to
   run, unless an explicit `--allow-degraded` flag is passed:
   - `03_build_vocab.py`: missing `char_readings.json` / `word_freq.json`
   - `04_build_grammar.py`: BeautifulSoup not importable
   - `pinyin_utils.py:_load_syllable_inventory`: missing
     `pinyin_syllables.json` → currently silently falls back to
     `_FALLBACK_SYLLABLES`
4. `08_build_content_db.py` should **assert a minimum content bar** before
   writing the DB, and refuse to write a degraded one:
   ```python
   if grammar_points < 400: raise SystemExit("grammar: 11 points — run 04_build_grammar.py")
   if words_with_bg_gloss < 10000: raise SystemExit("bg glosses: 0 — run 07_translate_bulgarian.py")
   if audio_files == 0: raise SystemExit("no audio — run 06_build_audio.py")
   ```
   A silently-degraded `content.db` that still "builds" is the worst
   possible outcome, because it ships to the APK.

**Verify**
```bash
git clone https://github.com/totalik9/hanzi-bg.git /tmp/hb && cd /tmp/hb
pip install -r pipeline/requirements.txt
python pipeline/01_fetch_sources.py && python pipeline/03_build_vocab.py
# expect: "words with a corpus frequency rank: 8,579" (not 0)
python pipeline/04_build_grammar.py
# expect: "entries=506  examples=3286"  (not 11)
```
**Pass =** grammar `506` points, `3 286` examples, `8 579+` words with freq.

---

## Point 2 — Let the learner reach HSK 3 and beyond (95 % of the app is dark)

**The measured problem.** The practice pool is hardcoded:

```kotlin
// PracticeViewModel.kt:150-151
val words = content.wordsForLevel("1", limit = 300) +
    content.wordsForLevel("2", limit = 200)
```

I queried the freshly built `content.db`:

| HSK level | words | reachable today? |
|---|---|---|
| 1–2 | 497 | yes (practice pool) |
| 3 | 491 | **no** |
| 4–6 | 4 346 | **no** |
| 7–9 | 5 562 | **no** |
| **total** | **10 896** | **497 = 4.6 %** |

`10 399` words (95 %) are in the database, shipped in the 19.7 MB
`content.db`, and **unreachable**. The same applies to the review screen:
`ReviewViewModel.kt:124` seeds from `content.levels().firstOrNull()` —
the first level only.

**What to do**

1. Add a **level selector** that is a real part of the navigation, not a
   display. Pass the level as a **nav argument**, not as a hardcoded
   string:
   ```kotlin
   composable("review?level={level}", arguments = listOf(navArgument("level") {
       type = NavType.StringType; defaultValue = "1"
   }))
   ```
2. Make the **Home level cards clickable** (`HomeScreen.kt:120-145` — the
   `Card` currently has no `onClick` and no `Modifier.clickable`). Tapping
   a level navigates to `review?level={level}`.
3. `PracticeViewModel` should load the pool **for the selected level**,
   not for `"1"` and `"2"`. Keep HSK 1–2 as the default so first-run
   behaviour is unchanged.
4. `ReviewViewModel.loadNext()` should seed from the **selected** level.
5. Pool sizes must scale with the level: level 7–9 has 5 562 words, so a
   `limit` of 200 is arbitrary — pull the whole level and let the
   `usedWords` set handle variety.

**Verify**
- Tap HSK 3 on Home → Review shows level-3 words (spot-check a word that
  only exists in level 3, e.g. 策略).
- The practice pool for level 3 is non-empty (`content.wordsForLevel("3")`
  returns 491).
- **Measure**: the number of words reachable across all screens goes from
  497 → 10 896.

---

## Point 3 — Fix the two broken CI checks and the failing self-check

**The measured problem.** Three separate defects in the same area.

**3a. `simulation/expected_vectors.json` is gitignored, but CI diffs it.**

```gitignore
# simulation/.gitignore:6
/expected_vectors.json
```

But the root `.gitignore` says the opposite in a comment:

> *expected_vectors.json IS tracked: CI diffs it against the Kotlin test
> vectors to catch scheduler drift, and `git diff` on an untracked file
> silently passes, which would make that check vacuous.*

It is **not** tracked — `git ls-files simulation/expected_vectors.json`
returns nothing. And `git diff` on an untracked file *does* silently pass.
I confirmed the CI check exits 0:

```
CI git-diff exit code: 0   (0 = check PASSES = vacuous)
```

So **the scheduler-drift guard has never actually worked.** The Python SRS
port and the Kotlin `SrsScheduler` can silently diverge and CI stays green.

**3b. `python simulation/test_simulation.py` fails on a fresh clone.** The
README documents this exact command. It exits **1**:

```
1 CHECK(S) FAILED: ['expected_vectors.json exists']
```

Because the file is gitignored, a fresh clone does not have it.

**3c. CI "fixes" this by accident.** The `simulation` job runs
`make_vectors.py` *before* `test_simulation.py`, which creates the ignored
file — so CI passes while a developer cloning the repo gets a failure.

**What to do**

1. **Untrack-ignore it.** Delete the `/expected_vectors.json` line from
   `simulation/.gitignore` so the root `.gitignore` comment becomes true.
   Then `git add -f simulation/expected_vectors.json` and commit it.
2. Make the CI check **fail when the file is untracked** instead of
   silently passing:
   ```bash
   git diff --exit-code -- simulation/expected_vectors.json \
     android/app/src/test/resources/srs_vectors.json || exit 1
   test -n "$(git ls-files simulation/expected_vectors.json)" || {
     echo "::error::expected_vectors.json is not tracked — the drift check is vacuous"; exit 1; }
   ```
3. `simulation/test_simulation.py` should **generate the vectors if they
   are missing** (or skip gracefully) instead of failing the whole run —
   a missing artefact and a broken model are different problems.
4. Same treatment for `android/app/src/test/resources/srs_vectors.json`:
   it *is* tracked, good — keep it that way.

**Verify**
```bash
git clone https://github.com/totalik9/hanzi-bg.git /tmp/hb2 && cd /tmp/hb2
python simulation/test_simulation.py; echo "exit=$?"   # expect exit=0
git ls-files simulation/expected_vectors.json            # expect a path, not empty
```
Then **prove the check is not vacuous**: change one number in
`simulation/expected_vectors.json`, re-run the CI diff command, and
confirm it now exits non-zero. A check that cannot fail is not a check.

---

## Point 4 — Add the release build to CI (the Play-Store path is untested)

**The measured problem.** `grep -c "assembleRelease" .github/workflows/ci.yml`
→ **0**. CI runs `testDebugUnitTest` and `assembleDebug` only.

The release build is the one that actually matters, and it is the one that
has broken before. The repo's own history shows it: `README.md` documents
that `syncContentDb` used to write into `app/src/main/assets` — a *source*
directory — which made `lintVital` fail with *"uses this output of task
':app:syncContentDb' without declaring an explicit or implicit
dependency"*. That is fixed (`build.gradle.kts` now uses
`layout.buildDirectory.dir("generated/assets")`), but **nothing in CI would
catch a regression**.

**What to do**

1. Add to the `android` job:
   ```yaml
   - name: Build release APK
     working-directory: android
     run: ./gradlew :app:assembleRelease --no-daemon
   ```
2. Add a `lintVitalRelease` step (it runs automatically inside
   `assembleRelease`, but run it explicitly so the failure is legible).
3. Verify the content DB ships **uncompressed** — the provider copies it
   byte-for-byte out of the APK, so a compressed entry would break the
   copy:
   ```bash
   unzip -l android/app/build/outputs/apk/release/*.apk | grep content.db
   # expect "Stored", not "Defl"
   ```
4. Upload the release APK as an artifact too (even unsigned).

**Verify:** CI is green **and** a deliberately broken release build fails
CI. Run `./gradlew :app:assembleRelease` locally once to confirm it
currently passes.

---

## Point 5 — Generate the missing audio (levels 3+)

**The measured problem.** In the freshly built DB:
`words with audio = 0`. The repo ships 509 clips for HSK 1–2 only.
`06_build_audio.py` already supports `--level`:

```bash
python pipeline/06_build_audio.py --level 3
```

**What to do**

1. Generate levels 3–6. Time cost: level 3 is ~491 words (~10 min),
   levels 4–6 are ~4 346 words (~1.5 h). Edge TTS rate-limits, so run it
   in the background and let it resume — `06` already skips files that
   exist and writes the manifest incrementally.
2. **Decide on levels 7–9** (5 562 words, ~2 h, ~15 MB of APK). The APK
   is already 27.6 MB; this pushes it toward 45 MB. Given HSK 3.0's
   cumulative levels, 7–9 is 51 % of the vocabulary, so excluding it is a
   real product decision, not a technical one. **Ask the user.** My
   recommendation: generate 3–6 now, and 7–9 as a separate optional
   artefact so the size is the user's call.
3. **Fix the 12 orphan clips** reported in `.hermes/plans/...md` — manifest
   entries with no matching word row.
4. **Fix the `ü` gap in the IME.** The IME index stores the syllable as
   `ü` (`'lü'` → 45 words, `'nü'` → 20 words), but a learner typing on a
   phone keyboard **cannot type `ü`**. I checked every ASCII spelling:
   `'lue'` → 0 words, `'lu:'` → 0, `'lv'` → 0, `'lve'` → 0. The only form
   that works is the literal `ü`. **76 IME rows (and ~76 words) are
   unreachable** unless the learner types the umlaut. Fix: store **both**
   `lü` and `lu` (and `nü`/`nu`) in the `ime` table — the `ime` table is
   `(syllable, hanzi)` so a second row per spelling is cheap. This is
   ~0.7 % of the vocabulary but it is the *most visible* kind of bug:
   the learner types `lu`, gets nothing, and concludes the app is broken.
5. **Sentence audio** is a bigger prize: `05_build_sentences.py` already
   records **5 820** Tatoeba audio URLs with real human voices, and only
   **396** sentences have a Bulgarian translation. Downloading those is a
   separate script (`sentences_with_audio.tar.bz2` is already in
   `01_fetch_sources.py`). Machine TTS for sentences is a fallback, not a
   goal.

**Verify**
```bash
python -c "
import sqlite3; c=sqlite3.connect('data/content.db')
print(c.execute(\"select count(*) from words where audio!=''\").fetchone()[0])"
# expect 497 + 491 + ... i.e. every word in levels 1-N has audio
```

---

## Point 6 — Put the grammar in Bulgarian (this is a Bulgarian app)

**The measured problem.** `title_bg` is empty in **506 / 506** grammar
points. `GrammarScreen.kt:60` falls back to `entry.titleBg.ifBlank { entry.title }`
— so the learner sees English. The grammar screen is one of five tabs and
it is entirely in the wrong language.

Worse, the **grammar quiz is also in English**:
`PracticeViewModel.kt:235` builds the options from `example.en`. The
learner is asked to match Chinese to an **English** meaning in an app
whose entire premise is learning Chinese *from Bulgarian*.

**What to do**

1. Translate `title` and `summary` for the **A1 + A2 points first**
   (141 points — the level the app actually targets). `07_translate_bulgarian.py`
   already has a working NLLB-200 setup with a **sense-level cache**; reuse
   the same machinery with a `grammar_bg.json` output. The existing
   `bg_sense_cache.json` means the second pass is cheap.
2. Human-check the A1/A2 grammar titles. 141 points is a few hours of
   work for a native speaker and it is the single highest-value content
   gap — the app's own plan calls Bulgarian grammar "missing function #3".
3. Make the **grammar quiz answer in Bulgarian**: translate the example
   sentences' English glosses into Bulgarian (same NLLB pass), and use the
   Bulgarian versions as both the correct answer and the distractors.
4. Keep the English text in the DB — it is the source for the translation
   and it is useful for a learner who gets stuck.

**Verify:** `title_bg` non-empty for ≥ 141 points; the grammar quiz's
options are in Bulgarian; the grammar screen shows Bulgarian titles.

---

## Point 7 — Fix the word-order pool (60 sentences, then "no more sentences")

**The measured problem.** `PracticeViewModel.kt:152`:
`content.sentencesWithBulgarian(limit = 60)`. The DB has **396** sentences
with a Bulgarian translation, and `05_build_sentences.py` reports
**37 596** short sentences with English but no Bulgarian. `sentencesWithBulgarian`
also sorts by `LENGTH(s.hanzi)`, so it always returns the *same* 60
shortest ones. After 60 exercises the learner gets
*"Няма повече изречения"* — a dead end.

**What to do**

1. Translate the short English sentences into Bulgarian via NLLB-200 and
   merge them into `sentences.json`. Target **≥ 2 000** translated
   sentences (short ones only — ≤ 8 characters — because a word-order
   exercise with 20 tokens is not a word-order exercise).
2. The existing sense-level cache makes this cheap: only the *new* English
   senses need translating.
3. **Randomise the pool.** Sorting by length then taking the first 60 is
   the actual bug — the fix is to shuffle over the whole pool, not to
   enlarge the limit. Do both: shuffle *and* enlarge.
4. Also check the token splitting. `segmentForWordOrder` splits per
   **character** (`PracticeViewModel.kt:430-438`: *"Each CJK character is
   its own token, which is the safest split"*). That works, but a
   word-level split would make the exercise test word order rather than
   character order. The dictionary is already in the DB — a longest-match
   segmentation over `words` is a contained change.

**Verify:** the word-order pool is ≥ 2 000; the same sentence does not
repeat across 200 consecutive exercises; after 60 exercises the
"no more sentences" message does not appear.

---

## Point 8 — Remove the dead code and wire up the empty stats table

**The measured problem.** Several things are defined and never used:

| Dead thing | Where | Verified |
|---|---|---|
| `daily_stats` table | `HanziUserDatabase.kt` | `grep` finds **no writes** — the table is always empty |
| `DailyStatsDao` | injected in `DatabaseModule.kt:30` | no caller |
| `SrsCardDao.totalCards()` | `HanziUserDatabase.kt` | no caller |
| `SrsCardDao.clear()` | `HanziUserDatabase.kt` | no caller |
| `ContentRepository.wordsStartingWithPinyin()` | `ContentRepository.kt:422` | no caller — **and buggy**: it does `WHERE pinyin_tones LIKE '$plain%'` with a **toneless** prefix, but `pinyin_tones` holds **numeric** pinyin (`ce4 lüe4`). A single syllable still matches by luck (`'ce'` → 20 rows), but a **multi-syllable** prefix matches **0**: `'ce lü'` → 0 rows via `pinyin_tones`, 1 row via `pinyin_plain`. `pinyin_plain` is the right column. |
| `ContentRepository.sentences()` | `ContentRepository.kt:329` | no caller |
| `ContentRepository.grammar()` vs `grammarWithExamples()` | — | near-duplicates, only one is used |
| `androidx.datastore:datastore-preferences` | `build.gradle.kts` | declared, **zero usages** |
| `io.coil-kt:coil-compose` | `build.gradle.kts` | declared, **zero usages** |
| `androidTestImplementation` deps | `build.gradle.kts` | `src/androidTest/` **does not exist** |

**What to do**

1. **Delete** the unused dependencies (`datastore-preferences`, `coil-compose`)
   and the `androidTestImplementation` block — or add the androidTest
   source set back if you plan to write instrumented tests (you should;
   see Point 9).
2. **Delete** `wordsStartingWithPinyin()` — it is dead *and* wrong. Or fix
   it to use `pinyin_plain` and use it. Dead-and-wrong is the worst
   combination: it looks like a working feature in search.
3. **Merge** `grammar()` and `grammarWithExamples()` into one function.
4. **Wire up `daily_stats`** or delete it. If you wire it up, record
   `reviews` / `correct` / `newWords` per day in `ReviewViewModel.grade()`
   and show a streak + daily goal on the Home screen. The Home screen
   currently shows a progress bar per level but **no daily goal**, which
   is the single biggest retention feature this app is missing.
5. Delete the `androidTest` dependencies if you skip Point 9.

**Verify:** `grep -rn "datastore\|coil" android/app/src/main/` returns
nothing and the build still passes; no `@Entity` table is left with zero
writers.

---

## Point 9 — Add instrumented tests for the five practice modes

**The measured problem.** 42 unit tests exist across 5 files:
`WordEntryTest` (7), `PinyinImeTest` (11), `SrsSchedulerParityTest` (4),
`StrokeMatchingTest` (10), `WordOrderScoringTest` (10). The pure logic is
well covered.

But **no screen is tested**. `src/androidTest/` does not exist at all.
The five practice modes — the thing that turns a passive dictionary into
an active language — have **zero** UI coverage. The repo's own plan
noted this gap ("Няма тест за нито един от 5-те учебни режима") and it
was only partially closed: the *scoring functions* were extracted, but the
*modes* themselves are untested.

**What to do**

1. Create `android/app/src/androidTest/` with Compose UI tests
   (`createAndroidComposeRule<HanziApp>()`) — the `androidTestImplementation`
   deps are already in `build.gradle.kts`, so no new dependency is needed.
2. Cover, at minimum:
   - **Production**: type "hao" → the candidate list contains 好; pick a
     wrong candidate → the exercise is marked wrong.
   - **Listening**: tap play → the audio button state changes.
   - **Word order**: pick tokens in the right order → "Правилно!".
   - **Writing**: trace the strokes → the score updates.
   - **Grammar quiz**: pick an option → correct/incorrect is shown.
3. The `ContentDatabaseProvider` needs a test hook so the tests can point
   at a **fixture** `content.db` rather than the 19.7 MB real one. Build a
   small fixture DB from a handful of words (好, 你好, 水) in
   `src/androidTest/assets/`.
4. Wire it into CI: `./gradlew :app:connectedDebugAndroidTest` needs an
   emulator. Use `reactivecircus/android-emulator-runner` in CI — it is
   the standard, and it is worth it: it is the only way to catch the
   "the APK builds but the screen is blank" class of bug.

**Verify:** the instrumented tests run green locally and in CI; each of
the five modes has at least one test.

---

## Point 10 — Polish: docs, licence, and the things the README gets wrong

**10a. The docs contradict the measured state.** The repo's own
`.hermes/plans/...md` catalogued these (С8) and most are still true.
Fix them:

| Claim | Measured |
|---|---|
| README: "1 386 clips = all of HSK 1–3" | 509 clips = HSK 1–2 only |
| README: "38/38 unit tests pass" | 42 `@Test` methods across 5 files |
| README: "content.db (19.8 MB)" | 19 730 432 B ≈ 18.8 MiB / 19.7 MB — pick one and be consistent |
| PLAN.md: "grammar 335 points" | 506 points, 3 286 examples |
| PLAN.md: "words with bg gloss 475 → ~10 400" | 10 381 |
| PLAN.md §2 "the app does NOT give you production/writing/word-order" | all three are implemented |
| PLAN.md §4.2 "verbs — separate table `hanzi\|pinyin\|pattern\|note`" | **that table does not exist**; `verbsForLevel()` filters `words.is_verb` |
| `.gitattributes` claims CRLF caused a CI failure | the real cause was the gitignored vectors (Point 3) |

**10b. The NLLB licence blocks the Play Store — decide it now, not in
stage 4.** `facebook/nllb-200-distilled-600M` is **CC-BY-NC**. The README
is honest that this blocks paid distribution. A Bulgarian app for
Bulgarian learners is plausibly non-commercial, but "we will deal with it
later" is how projects end up with 10 000 machine glosses they cannot
ship. Options, in order of effort:

1. **Keep NLLB, ship as free / non-commercial** (CC BY-NC 4.0 permits
   this — just attribute it properly and keep it non-commercial).
2. **Replace with a permissively licensed model** for the final glosses.
   `10_compare_models.py` already compares NLLB-200 against M2M-100 and
   found M2M-100 breaks less often (3.3 % vs 5.3 %) but leaves more
   English in the output — and the pipeline already strips that. Worth
   re-running with a third candidate.
3. **Human-verify HSK 1** (300 words). The repo tracks this as human
   work and it is still not done — 457 words already have human glosses,
   so the workflow exists.

**10c. Hardcoded Windows paths.** Six scripts contain the original
developer's absolute path:
```
pipeline/_probe_coverage.py:2,5   pipeline/_probe_vocab.py:4
pipeline/_probe_vs_cedict.py:7,10 pipeline/_scan_bg_wiktionary.py:16
pipeline/_scan_wiktionary_pos.py:20
```
All six are `C:/Users/IPP/projects/hanzi-bg/...`. They are dead on any
other machine. Fix them to derive the path from `__file__` like the rest
of the pipeline does, or delete the `_probe_*` scripts (they are one-off
diagnostics and their findings are already in the docs).

**10d. Small things worth doing:**
- `README.md` and `PLAN.md` are in Bulgarian; the code comments and
  commit messages are in English. Pick one per audience — keep the docs
  Bulgarian (that is the point of the app) and the code English.
- The `Home` screen shows a level list but no **daily goal** or
  **streak**. Add one (see Point 8.4) — it is the cheapest retention
  win available.
- Add a `LICENSE` reference for each source to a machine-readable file
  (`data/sources.json` is partly there via `01`'s manifest — extend it to
  include the model licence and the audio contributor licences, which
  are **per-contributor** for Tatoeba and therefore genuinely per-file).

**Verify:** a fresh reader who follows the README end-to-end gets the
numbers in the README. Every claim in the README is a number you measured.

---

## Suggested order

```
Point 1 (reproducibility)  ← do this FIRST, everything else depends on it
   ├── Point 3 (broken CI checks + failing self-check)
   ├── Point 4 (release build in CI)
   └── Point 5 (audio)
Point 2 (level reachability) ← the biggest learner-facing win
Point 8 (dead code)          ← small, do it while you are in the Kotlin files
Point 9 (instrumented tests) ← after 2, so the new screens are covered
Point 6 (Bulgarian grammar)  ← content, slow, can run in the background
Point 7 (word-order pool)    ← content, slow, can run in the background
Point 10 (docs + licence)    ← last, so the docs describe the final state
```

**Point 1 is not optional.** Every other number in this document assumes
a `content.db` that can actually be rebuilt. Right now it cannot.

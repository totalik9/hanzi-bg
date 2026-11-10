## What this changes

<!-- One or two sentences. What is different after this PR? -->

## Why

<!-- The problem this solves. Reference an issue if there is one:
     Closes #123 -->

## How

<!-- The approach. Note anything a reviewer should know:
     - schema changes (Room migration?)
     - content pipeline changes (do the generated data files change?)
     - scheduler changes (regenerate simulation/make_vectors.py!) -->

## Testing

- [ ] `./gradlew :app:assembleDebug` passes
- [ ] `./gradlew :app:testDebugUnitTest` passes
- [ ] `python simulation/test_simulation.py` passes
- [ ] `python simulation/make_vectors.py` was run if the scheduler changed
- [ ] Verified on a device or emulator (Android 16 / API 36)

## Content impact

- [ ] No content changes
- [ ] Content changed - sources and licences are recorded in `data/raw/manifest.json`
- [ ] Machine-translated content is marked as such

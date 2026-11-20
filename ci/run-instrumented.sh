#!/usr/bin/env bash
# Run the instrumented tests on the emulator and KEEP the output.
#
# WHY THIS EXISTS
#
# The emulator job had never succeeded once, and the reason could not be
# read: the GitHub Actions job log needs admin rights on the
# repository, so a failing run said "the process failed with exit code
# 1" and nothing else. Every attempt to fix it was guesswork.
#
# So the job now diagnoses itself. Everything that explains a failure
# is written into instrumented-diagnostics/ and uploaded as an
# artefact, which anybody with read access can download.
#
# The device state has to be collected HERE, while the emulator is
# still alive: the emulator action kills the emulator when its step
# ends, so a later step would find no device.
#
# Usage:
#   ci/run-instrumented.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/instrumented-diagnostics"
mkdir -p "$OUT"

ADB="${ANDROID_HOME:-$HOME/Android/Sdk}/platform-tools/adb"

capture() {
  # capture <file> <command...>
  local name="$1"
  shift
  "$@" > "$OUT/$name" 2>&1 || true
}

echo "== instrumented tests =="
echo "   diagnostics: $OUT"

cd "$ROOT/android"

# The emulator can report itself booted before the package manager is
# able to install anything. The install then dies with a
# NullPointerException inside InstallLocationUtils ("StorageManager is
# null") and the job fails with "0 tests" -- the tests never ran, and
# the failure says nothing about the app.
#
# So the script waits for the package manager to answer before it starts.
echo "== waiting for the package manager =="
for _ in $(seq 1 60); do
  if "$ADB" shell cmd package list packages 2>/dev/null | grep -q "^package:"; then
    echo "   the package manager answers"
    break
  fi
  sleep 5
done

# The Gradle output goes to the log AND to the console. pipefail keeps
# Gradle's exit code, which a pipeline would otherwise throw away.
set -o pipefail

run_tests() {
  ./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace 2>&1 \
    | tee "$OUT/gradle.log"
  GRADLE_STATUS="${PIPESTATUS[0]}"
}

run_tests
status="$GRADLE_STATUS"

# An install failure is the emulator, not the app, so it gets one more
# chance with a fresh attempt.
if [ "$status" != "0" ] && grep -q "Failed to install" "$OUT/gradle.log"; then
  echo
  echo "== the install failed; the emulator was not ready. Retrying in 30s =="
  sleep 30
  run_tests
  status="$GRADLE_STATUS"
fi

# What the device was doing when it failed.
capture adb-devices.txt "$ADB" devices -l
capture logcat-crash.txt "$ADB" logcat -d -b crash
capture logcat-tail.txt "$ADB" logcat -d -t 400
capture emulator-info.txt "$ADB" shell getprop
capture disk.txt df -h "$ROOT"

# The last lines of the Gradle output go into the job summary. The
# job LOG needs admin rights on the repository, so it cannot be read
# by the people who have to fix the failure -- but the summary is on
# the run page, and it is what the next person reads first.
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## Instrumented tests"
    echo
    echo "Gradle exit code: \`$status\`"
    echo
    echo '```'
    tail -60 "$OUT/gradle.log"
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
fi

echo
echo "== gradle exit: $status =="
exit "$status"

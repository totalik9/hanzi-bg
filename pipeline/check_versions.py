"""Check that the build's version and the version record agree.

    python pipeline/check_versions.py           # the report
    python pipeline/check_versions.py --gate    # exits 1 when they disagree

WHY THERE IS A RECORD AND NOT JUST A NUMBER

`versionCode` in build.gradle.kts says what the APK calls itself. It
does not say what CHANGED, and it does not survive as a comparison:
two builds with the same code are two builds nobody can tell apart
later, and a build that quietly carries an old code is a release that
does not install over the previous one.

So the code is paired with a record of every build: the version, the
date, the tag, what changed and what the corpus measured. The record
is what makes a later build comparable to an earlier one.

THE RULES

  * the code goes UP, never down;
  * the name and the code agree;
  * the name of the build in the code is the LAST entry of the record;
  * the codes in the record are unique and ordered.

The last rule is the one that catches a build that was given a number
which is already taken: the release workflow compares the code against
the previous TAG, so a code that repeats an old one passes that check
and installs over nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD_GRADLE = os.path.join(ROOT, "android", "app", "build.gradle.kts")
VERSIONS = os.path.join(ROOT, "versions.json")

_CODE = re.compile(r"versionCode\s*=\s*(\d+)")
_NAME = re.compile(r'versionName\s*=\s*"([^"]+)"')


def read_build_version() -> tuple[int, str]:
    """The versionCode and the versionName of the app, as the build has them."""
    with open(BUILD_GRADLE, encoding="utf-8") as fh:
        text = fh.read()
    code = _CODE.search(text)
    name = _NAME.search(text)
    if not code or not name:
        raise SystemExit(
            "ERROR: android/app/build.gradle.kts has no versionCode and "
            "versionName, or they are not written the way the script reads "
            "them")
    return int(code.group(1)), name.group(1)


def read_record() -> list[dict]:
    """Every build in the record, oldest first."""
    with open(VERSIONS, encoding="utf-8") as fh:
        data = json.load(fh)
    builds = data.get("builds")
    if not isinstance(builds, list) or not builds:
        raise SystemExit("ERROR: versions.json has no build list")
    return builds


def expected_code(version: str) -> int:
    """The code the rule gives a version name: major*100 + minor*10 + patch.

    The first three builds used a short code, so the rule is only
    checked for the builds that follow it. A build that does not follow
    the rule is still accepted as long as its code goes UP.
    """
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"ERROR: {version!r} is not a version name")
    major, minor, patch = (int(p) for p in parts)
    return major * 100 + minor * 10 + patch


def check() -> list[str]:
    """The problems with the version and the record. Empty when they agree."""
    problems: list[str] = []
    code, name = read_build_version()
    builds = read_record()

    # The codes in the record go up and are unique.
    seen: dict[int, str] = {}
    previous: int | None = None
    for build in builds:
        build_code = build.get("versionCode")
        version = build.get("version", "")
        if not isinstance(build_code, int):
            problems.append(f"{version}: the record has no versionCode")
            continue
        if build_code in seen:
            problems.append(
                f"{version}: the code {build_code} is already used by "
                f"{seen[build_code]} — a build needs its own number")
        seen[build_code] = version
        if previous is not None and build_code <= previous:
            problems.append(
                f"{version}: the code {build_code} does not go up from "
                f"{previous} — a release that does not install over the "
                f"previous one is a release nobody can upgrade to")
        previous = build_code

    # The name of the build in the code is the last one in the record.
    last = builds[-1]
    if last.get("version") != name:
        problems.append(
            f"the build says {name!r} but the record's last build is "
            f"{last.get('version')!r} — the record has to end with the "
            f"build that is being made")
    if last.get("versionCode") != code:
        problems.append(
            f"the build says versionCode {code} but the record's last build "
            f"says {last.get('versionCode')}")

    # The code goes up from every build before it.
    for build in builds[:-1]:
        build_code = build.get("versionCode")
        if isinstance(build_code, int) and code <= build_code:
            problems.append(
                f"versionCode {code} is not greater than the {build_code} of "
                f"{build.get('version')}")

    # The name and the code agree.
    try:
        wanted = expected_code(name)
    except SystemExit:
        wanted = None
    if wanted is not None and wanted != code and code >= 10:
        problems.append(
            f"the version {name} should carry the code {wanted} by the rule "
            f"(major*100 + minor*10 + patch), but the build says {code}")

    return problems


def report() -> None:
    """The record, as a table."""
    code, name = read_build_version()
    builds = read_record()
    print("=" * 78)
    print("THE BUILDS")
    print("=" * 78)
    print("   %-9s %-11s %-12s %s" % ("version", "versionCode", "date", "changes"))
    for build in builds:
        print("   %-9s %-11s %-12s %s" % (
            build.get("version", "?"),
            build.get("versionCode", "?"),
            build.get("date", "?"),
            (build.get("changes") or "")[:70],
        ))
    print()
    print(f"   the build in the tree: {name} (versionCode {code})")
    for build in builds:
        corpus = build.get("corpus")
        if not corpus:
            continue
        print("   %-9s corpus: %s" % (
            build.get("version"),
            ", ".join(f"{k}={v}" for k, v in sorted(corpus.items()))))


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the app version")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 when the version and the record disagree")
    args = ap.parse_args()

    report()
    problems = check()
    if problems:
        print()
        print("=" * 78)
        print("THE VERSION AND THE RECORD DISAGREE")
        print("=" * 78)
        for problem in problems:
            print("   ::error::%s" % problem)
        if args.gate:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

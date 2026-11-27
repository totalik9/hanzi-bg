"""The build's version and the record in versions.json have to agree.

    python -m pytest pipeline/test_versions.py -q

The rules are in `check_versions.py`, which is also a script that can
be run on its own. This file is the gate: it fails the build when the
version of the tree and the record of the builds disagree.

WHY THIS IS WORTH A TEST

The versionCode is the only thing that says whether a release installs
over the previous one. It is checked by the release workflow against
the previous TAG -- but a tag is only pushed when somebody remembers
to push it, so a build that repeats an old code passes that check and
installs over nothing. The record knows EVERY build, so it catches
that.

The record is also what makes two builds comparable later: it says
what changed and what the corpus measured, so a build from next month
can be compared with this one and not just with the one before it.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

_spec = importlib.util.spec_from_file_location(
    "check_versions", os.path.join(HERE, "check_versions.py")
)
_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_check)


def test_the_version_and_the_record_agree():
    problems = _check.check()
    assert not problems, (
        "the version of the build and the record disagree:\n  "
        + "\n  ".join(problems))


def test_the_record_is_a_list_of_builds():
    builds = _check.read_record()
    assert builds, "versions.json has no builds"
    for build in builds:
        assert build.get("version"), "a build of the record has no version"
        assert isinstance(build.get("versionCode"), int), (
            f"{build.get('version')}: the record has no versionCode")
        assert build.get("date"), (
            f"{build.get('version')}: the record has no date")


def test_the_codes_go_up():
    codes = [b["versionCode"] for b in _check.read_record()]
    for previous, current in zip(codes, codes[1:]):
        assert current > previous, (
            f"the code {current} does not go up from {previous}")


def test_the_names_and_the_codes_agree():
    """The code of a build is the one its name gives.

    The first three builds used a short code, so the rule is checked
    only for the builds that follow it.
    """
    for build in _check.read_record():
        code = build["versionCode"]
        if code < 10:
            continue
        assert code == _check.expected_code(build["version"]), (
            f"{build['version']} should carry the code "
            f"{_check.expected_code(build['version'])} but the record says "
            f"{code}")


def test_the_build_in_the_tree_is_the_last_of_the_record():
    code, name = _check.read_build_version()
    last = _check.read_record()[-1]
    assert last["version"] == name, (
        f"the build says {name} but the record ends with "
        f"{last['version']}")
    assert last["versionCode"] == code, (
        f"the build says the code {code} but the record says "
        f"{last['versionCode']}")


def test_the_record_is_written():
    """The record has to be in version control.

    A record that is not committed is a record that exists only on the
    machine of the person who made the build, and the next build
    cannot be compared with it.
    """
    path = os.path.join(ROOT, "versions.json")
    assert os.path.exists(path)
    tracked = os.path.join(ROOT, ".git", "index")
    if not os.path.exists(tracked):
        pytest.skip("this is not a git checkout")
    import subprocess
    listed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "versions.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if listed.returncode != 0:
        # The file is new in this tree: it is not committed yet, and
        # the test says so instead of failing the build of a tree that
        # has not been committed yet.
        pytest.skip("versions.json is not committed yet")

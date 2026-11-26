"""Read the logs of the students and say what they found.

    python session/aggregate.py

The fifteen students each write a log and a report. This script puts
them together:

* every finding of every student, with the students that found it;
* the COVERAGE of the app: which buttons the students pressed and
  which they never pressed, so a part of the app that nobody looked
  at is visible;
* the screens the students reached.

The output is written to `recordings/sessions/AGGREGATE.txt`, and it
is the thing that is read before anything is changed.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SESSIONS = REPO / "recordings" / "sessions"

# The clicks the app offers, and the label they carry on the screen.
# A student that never pressed one of them did not look at that part
# of the app -- which is worth knowing on its own.
EXPECTED_CLICKS = {
    "path": ["Започни урока", "Прегледай", "Покажи още", "Значки", "Напредък"],
    "menu": ["Повторение", "Упражнения", "Граматика", "Нива"],
    "lesson": ["Продължи", "Покажи отговор", "Готово", "Следващ знак", "Изчисти"],
    "review": ["Отново", "Трудно", "Добре", "Лесно"],
    "practice": ["Производство", "Слушане", "Подреждане", "Писане", "Помощ"],
    "dictionary": ["Търси китайски или латински", "Само човешки сверени глоси", "Честите думи", "Покажи още"],
    "onboarding": ["За изпит HSK", "За пътуване", "За работа", "Напред", "Назад", "Към уроците"],
}


def main() -> int:
    logs = sorted(SESSIONS.glob("*.txt"))
    logs = [
        p
        for p in logs
        if not p.name.endswith(".report.txt")
        and p.name != "AGGREGATE.txt"
        # Only the new students: the old two have no TOUCHED line and
        # their findings are from a build that is long gone.
        and re.search(r"_s\d\d_", p.name)
    ]
    if not logs:
        print("no session logs in", SESSIONS)
        return 1

    fresh_reports = {p.name for p in logs}
    findings: list[tuple[str, str, int, list[str]]] = []
    touched: Counter[str] = Counter()
    per_student: dict[str, list[str]] = {}
    students = 0

    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "SESSION START" not in text:
            continue
        students += 1
        key = ""
        title = ""
        match = re.search(r"student=(\S+) \(([^)]*)\)", text)
        if match:
            key, title = match.group(1), match.group(2)

        labels: list[str] = []
        for line in text.split("\n"):
            # The line carries a timestamp: "[18:53:00] TOUCHED: a | b".
            if "TOUCHED:" in line:
                labels = [x.strip() for x in line.split("TOUCHED:", 1)[1].split("|")]
                break
        per_student[key] = labels
        for label in labels:
            touched[label] += 1

        report = path.with_suffix(".report.txt")
        if report.exists() and path.name in fresh_reports:
            body = report.read_text(encoding="utf-8", errors="replace")
            if "FINDINGS: none" not in body:
                block = body.split("FINDINGS:", 1)[1]
                for entry in re.finditer(
                    r"\[(P\d)\] (.+?)\n(?:\s{4}(.+?)\n)?", block
                ):
                    severity = entry.group(1)
                    title_text = entry.group(2).strip()
                    detail = (entry.group(3) or "").strip()
                    findings.append((severity, title_text, detail, [key]))

    out = SESSIONS / "AGGREGATE.txt"
    lines = [
        "AGGREGATE OF THE STUDENT SESSIONS",
        f"students: {students}",
        f"logs: {len(logs)}",
        "",
        "=" * 68,
        "FINDINGS",
        "=" * 68,
    ]
    if not findings:
        lines.append("none")
    else:
        by_title: dict[str, list[str]] = defaultdict(list)
        for severity, title_text, detail, who in findings:
            by_title[(severity, title_text)].append(who[0])
        for (severity, title_text), who in sorted(
            by_title.items(), key=lambda item: item[0][0]
        ):
            lines.append(f"[{severity}] {title_text}")
            lines.append(f"    found by: {', '.join(who)}")
        lines.append("")
        lines.append(f"total findings: {len(findings)}")

    lines += ["", "=" * 68, "COVERAGE -- the clicks of the app", "=" * 68]
    for area, labels in EXPECTED_CLICKS.items():
        lines.append(f"[{area}]")
        for label in labels:
            count = touched.get(label, 0)
            mark = "ok  " if count else "NEVER"
            lines.append(f"  {mark} {label!r}: pressed by {count} student(s)")
    lines.append("")
    lines.append(f"distinct labels pressed: {len(touched)}")

    lines += ["", "=" * 68, "THE STUDENTS", "=" * 68]
    for key, labels in sorted(per_student.items()):
        lines.append(f"{key}: {len(labels)} distinct labels")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print()
    print("written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

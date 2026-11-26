"""The analyzer: it reads the session log and says what went wrong.

The log is written by a student, not by the app, so the analyzer looks
for the things a student can SEE:

* a question whose right answer is not among the options;
* an answer the app marked wrong although the student had learned the
  right meaning;
* a tap that changed nothing -- a button that does not do what it
  says;
* a screen with no way out of it;
* a mode that cannot be reached;
* a card with no options at all.

Every finding names the line of the log it comes from, so it can be
read against the walk that produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# A finding is a defect only if it is reproducible and it is in the
# app. The severity is how much it hurts a learner.
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass
class Finding:
    severity: str
    title: str
    detail: str
    line: int = 0
    evidence: list[str] = field(default_factory=list)

    def render(self, log_name: str) -> str:
        out = [f"[{self.severity}] {self.title}"]
        out.append(f"    {self.detail}")
        if self.line:
            out.append(f"    {log_name}:{self.line}")
        for item in self.evidence[:4]:
            out.append(f"      | {item}")
        return "\n".join(out)


@dataclass
class Report:
    student: str = ""
    log_name: str = ""
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def render(self) -> str:
        lines = [
            f"STUDENT SESSION REPORT -- {self.student}",
            f"log: {self.log_name}",
            "",
            "STATS",
        ]
        for key, value in self.stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        if not self.findings:
            lines.append("FINDINGS: none")
            return "\n".join(lines)
        ordered = sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.line))
        lines.append(f"FINDINGS: {len(ordered)}")
        lines.append("")
        for finding in ordered:
            lines.append(finding.render(self.log_name))
            lines.append("")
        return "\n".join(lines)


class Analyzer:
    """Reads a session log and finds what is wrong with the app."""

    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.report = Report(log_name=path.name)

    def analyze(self) -> Report:
        report = self.report
        for index, line in enumerate(self.lines, start=1):
            if line.startswith("SESSION START:"):
                match = re.search(r"student=(\w+)", line)
                if match:
                    report.student = match.group(1)
                continue
            self._line(index, line)

        self._summarize()
        return report

    # -- the individual checks --------------------------------------

    def _line(self, index: int, line: str) -> None:
        if "the learned meaning" in line and "is NOT among the options" in line:
            self.report.add(
                Finding(
                    severity="P0",
                    title="The right answer is not among the options",
                    detail=(
                        "The student learned the meaning of the word on the "
                        "LISTEN card, and the RECOGNISE card does not offer it. "
                        "The question cannot be answered correctly."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "picked" in line and "had learned" in line:
            self.report.add(
                Finding(
                    severity="P1",
                    title="The answer the student learned was marked wrong",
                    detail=(
                        "The student answered with the meaning it had learned, "
                        "and the app did not accept it. Either the option is "
                        "not the answer, or the app compares the strings "
                        "differently from the way the student reads them."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "THE LEARNER CANNOT LEAVE IT" in line:
            self.report.add(
                Finding(
                    severity="P0",
                    title="The learner is STUCK on a card",
                    detail=(
                        "The card does not change when the button is pressed, "
                        "so the learner cannot leave it: the lesson stops "
                        "there and nothing on the screen says why. This is "
                        "the worst kind of defect for a beginner -- the "
                        "app looks broken and there is no way forward."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "NO CHANGE after tapping" in line:
            self.report.add(
                Finding(
                    severity="P1",
                    title="A tap on a button changed nothing",
                    detail=(
                        "The button is on the screen, it looks pressable, and "
                        "pressing it does nothing. The learner has no way to "
                        "know what went wrong."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "the question has NO options" in line:
            self.report.add(
                Finding(
                    severity="P0",
                    title="A question with no options",
                    detail="The RECOGNISE card has nothing to choose from.",
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "is STILL not reachable" in line:
            self.report.add(
                Finding(
                    severity="P2",
                    title="A practice mode cannot be reached",
                    detail=(
                        "The mode is in the list, but the list does not scroll "
                        "far enough to bring it on the screen. The learner "
                        "cannot use the mode at all."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "is NOT on the screen" in line or "nothing on the screen contains" in line:
            self.report.add(
                Finding(
                    severity="P2",
                    title="Something the learner needs is not on the screen",
                    detail=(
                        "The student looked for it and could not find it. The "
                        "screen does not carry what the walk needs."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "the trace canvas could not be located" in line:
            self.report.add(
                Finding(
                    severity="P2",
                    title="The writing step has no reachable canvas",
                    detail=(
                        "The write card shows the stroke order and the hint, "
                        "but there is no canvas the learner can trace."
                    ),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

        if "did not open" in line:
            self.report.add(
                Finding(
                    severity="P1",
                    title="A control that does not open what it promises",
                    detail=line.split(":", 1)[-1].strip(),
                    line=index,
                    evidence=[line.strip()],
                )
            )
            return

    # -- the summary ------------------------------------------------

    def _summarize(self) -> None:
        text = "\n".join(self.lines)
        report = self.report

        steps = len([line for line in self.lines if line.startswith("[") and "TAP " in line])
        report.stats["taps"] = steps

        results = re.findall(r"LESSON RESULT: (\w+) score=(\S*)", text)
        if results:
            report.stats["lessons"] = len(results)
            report.stats["lessons_passed"] = sum(1 for verb, _ in results if verb == "passed")
            report.stats["lessons_failed"] = sum(1 for verb, _ in results if verb != "passed")
            scores = [int(score.rstrip("%")) for _, score in results if score.endswith("%")]
            if scores:
                report.stats["mean_score"] = f"{sum(scores) // len(scores)}%"

        questions = re.findall(r"RECOGNISE (\S+) options=", text)
        report.stats["questions"] = len(questions)
        wrongs = text.count("-> WRONG")
        report.stats["wrong_answers"] = wrongs
        report.stats["dead_ends"] = text.count("NO CHANGE after tapping")
        # The cards the learner could not leave: the worst defect there
        # is, and it is worth its own number.
        report.stats["stuck_cards"] = text.count("THE LEARNER CANNOT LEAVE IT")

        cards = re.findall(r"LESSON card (\d+)/(\d+)", text)
        if cards:
            report.stats["cards_played"] = len(cards)

        heard = re.findall(r"LESSON card \d+/\d+ LISTEN (\S+)", text)
        report.stats["words_heard"] = len(set(heard))

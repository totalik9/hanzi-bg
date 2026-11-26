"""The session runner: it walks the app and writes down every step.

The log is the artefact. It is a plain text file, one line per action,
in the shape of the session log of 2026-11-23:

    [21:14:03] PATH: 'Следващият урок' = 'Числа от 1 до 10' (10 думи)
    [21:14:07] TAP 'Започни урока' at (540, 1180)
    [21:14:09] LESSON numbers-1: card 1/28 LISTEN 一 'едно'

Everything the analyzer needs is in that file, so a session can be
re-read long after the emulator is gone.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .device import Device, Node, Screen
from .students import Card, Persona, classify, is_gloss, is_hanzi

REPO = Path(__file__).resolve().parent.parent


class SessionLog:
    """The text file the session is written to."""

    def __init__(self, path: Path, persona: Persona, serial: str):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")
        self.started = time.time()
        self._write(
            f"SESSION START: student={persona.key} ({persona.title}) "
            f"device={serial} goal='{persona.goal}' minutes='{persona.minutes}'"
        )

    def _write(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime())
        self._handle.write(f"[{stamp}] {line}\n")
        self._handle.flush()

    def step(self, line: str) -> None:
        self._write(line)

    def close(self) -> None:
        elapsed = int(time.time() - self.started)
        self._write(f"SESSION END: {elapsed}s")
        self._handle.close()


@dataclass
class Outcome:
    """What one action achieved."""

    changed: bool = False
    note: str = ""
    detail: dict = field(default_factory=dict)


class Session:
    """One student, one walk through the app."""

    def __init__(
        self,
        device: Device,
        persona: Persona,
        log: SessionLog,
        shots: Path | None = None,
        max_seconds: int = 40 * 60,
    ):
        self.device = device
        self.persona = persona
        self.log = log
        self.shots = shots
        self.max_seconds = max_seconds
        # What the student learned: hanzi -> meaning.
        self.known: dict[str, str] = {}
        # The screen as it was before the last action.
        self.before: Screen | None = None
        self.step_count = 0
        self.dead_ends = 0
        self.stuck_screen: str | None = None
        self.stuck_since = 0.0
        # Every label this student pressed, without repeats.
        self.tapped: list[str] = []

    # -- plumbing --------------------------------------------------

    @property
    def elapsed(self) -> float:
        return time.time() - self.log.started

    def shot(self, name: str) -> None:
        if not self.shots:
            return
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:60]
        self.device.screenshot(self.shots / f"{safe}.png")

    def read(self) -> Screen:
        screen = self.device.dump()
        self.before = screen
        return screen

    def tap(self, node: Node, what: str = "", expect_no_change: bool = False) -> Outcome:
        """Tap a node and report whether the screen changed.

        Some buttons change nothing on the screen -- the audio button
        plays a clip and leaves the card as it is. Those are marked, so
        that a student that plays a pronunciation is not reported as
        having pressed a dead button.
        """
        x, y = node.center
        self.step_count += 1
        label = what or node.label()
        # The labels are collected apart from the log, so that the
        # fifteen students together can be checked against the list of
        # every click the app offers: what was never pressed is a part
        # of the app nobody looked at.
        if label and label not in self.tapped:
            self.tapped.append(label)
        self.log.step(f"TAP '{label}' at ({x}, {y})")
        self.device.tap(x, y)
        time.sleep(0.55)
        after = self.device.dump()
        changed = after.fingerprint() != (self.before.fingerprint() if self.before else "")
        if not changed:
            if expect_no_change:
                self.log.step(f"  -> the screen is the same, as expected")
            elif not node.is_enabled:
                # A DISABLED button does nothing when it is tapped, and
                # that is not a dead end: the app is telling the learner
                # that the step is not ready yet. The word-order
                # exercise says so: "Провери" is greyed out until a
                # word is picked. Reporting it as a broken button would
                # be a finding about the harness, not about the app.
                self.log.step(f"  -> the button '{label}' is DISABLED, so it does nothing")
            else:
                # A learner taps again when nothing happens, and the
                # app is sometimes still settling -- the first tap
                # after the screen appears can be lost. A button that
                # is truly dead stays dead on the second tap, so the
                # finding is the same.
                time.sleep(1.2)
                self.device.tap(x, y)
                time.sleep(1.0)
                after = self.device.dump()
                changed = after.fingerprint() != (
                    self.before.fingerprint() if self.before else ""
                )
                if changed:
                    self.log.step(f"  -> the second tap on '{label}' worked")
                else:
                    self.dead_ends += 1
                    self.log.step(f"  -> NO CHANGE after tapping '{label}'")
        return Outcome(changed=changed, detail={"label": label})

    def tap_text(self, text: str, exact: bool = True) -> Outcome:
        """Tap the thing that says `text`.

        The tap goes to the clickable group, not to the text: a text
        node is not itself pressable, and a text that sits NEXT to a
        button (which is how Compose draws it) would be tapped in the
        wrong place.

        When the thing is not on the screen, the page is scrolled and
        the search is repeated: a learner scrolls to reach a button,
        and so does the student.
        """
        node = self._target(text, exact)
        if node is None:
            self.log.step(f"  '{text}' is not on the screen, scrolling")
            for _ in range(4):
                self.scroll_down()
                node = self._target(text, exact)
                if node is not None:
                    self.log.step(f"  found '{text}' after scrolling")
                    break
        if node is None:
            self.log.step(f"  !! '{text}' is NOT on the screen")
            return Outcome(changed=False, note="missing")
        return self.tap(node, text)

    def _target(self, text: str, exact: bool) -> Node | None:
        if self.before is None:
            return None
        # A button with that label.
        for node in self.before.buttons():
            label = node.group_label()
            if (label == text) if exact else (text in label):
                return node
        # Plain text: the text node itself, or the clickable group it
        # belongs to.
        for node in self.before.nodes:
            if not node.text:
                continue
            if (node.text == text) if exact else (text in node.text):
                if node.clickable:
                    return node
                for ancestor in node.ancestors():
                    if ancestor.clickable:
                        return ancestor
                return node
        # A label that CARRIES something else is still the button the
        # student is looking for: "Прегледай 25 карти за днес" is the
        # review button with a number on it.
        for node in self.before.nodes:
            if not node.text or not node.text.startswith(text):
                continue
            if node.clickable:
                return node
            for ancestor in node.ancestors():
                if ancestor.clickable:
                    return ancestor
            return node
        return None

    def tap_containing(self, needle: str) -> Outcome:
        nodes = self.before.find_containing(needle) if self.before else []
        if not nodes:
            self.log.step(f"  !! nothing on the screen contains '{needle}'")
            return Outcome(changed=False, note="missing")
        return self.tap(nodes[0], needle)

    def scroll_down(self) -> Outcome:
        self.step_count += 1
        self.log.step("SCROLL down")
        self.device.scroll_down()
        time.sleep(0.5)
        after = self.device.dump()
        changed = after.fingerprint() != (self.before.fingerprint() if self.before else "")
        return Outcome(changed=changed)

    def back(self) -> Outcome:
        self.step_count += 1
        self.log.step("BACK")
        self.device.back()
        time.sleep(0.6)
        after = self.device.dump()
        changed = after.fingerprint() != (self.before.fingerprint() if self.before else "")
        return Outcome(changed=changed)

    def note(self, line: str) -> None:
        self.log.step(line)

    def wait_for(self, kinds: tuple[str, ...], tries: int = 12) -> Screen | None:
        """Wait until the screen is one of these kinds.

        The app needs a while on a cold emulator -- it copies a 27 MB
        database out of the assets -- and the screen can come and go
        while it does. A student that walks into a screen it does not
        understand gives up, and the finding is then about the
        harness and not about the app.
        """
        for _ in range(tries):
            screen = self.read()
            if classify(screen).kind in kinds:
                return screen
            time.sleep(1.0)
        self.note(
            f"  !! the screen stayed unknown, wanted one of {kinds}"
        )
        return None

    # -- the walk --------------------------------------------------

    def run(self) -> None:
        # Set when a card cannot be left: the learner is stuck, and the
        # walk is over.
        self.stuck = False
        self.onboarding()
        # The walk of the areas this student came for.
        self.tour()
        if not self.stuck:
            # The whole app, so that the students between them cover
            # every click.
            self.path_loop()
            self.review()
            self.practice()
            self.dictionary()
            self.levels()
        self.log.step(
            f"DONE: steps={self.step_count} dead_ends={self.dead_ends} "
            f"words_known={len(self.known)}"
        )
        # The labels that were pressed, so the coverage of the app can
        # be measured across all the students.
        self.log.step(f"TOUCHED: {' | '.join(self.tapped)}")

    # -- the tour ----------------------------------------------------
    #
    # Every focus area is a small walk through one part of the app. A
    # student walks the areas its persona names, and the fifteen
    # students together walk every part.

    def tour(self) -> None:
        """Walk the areas this student came for."""
        self.wait_for(("path", "unknown"))
        for area in self.persona.focus:
            if self.elapsed > self.max_seconds:
                return
            self.note(f"TOUR: {area}")
            walker = getattr(self, f"tour_{area}", None)
            if walker is None:
                self.note(f"  !! there is no walk for '{area}'")
                continue
            try:
                walker()
            except Exception as error:  # noqa: BLE001 - the log must survive
                self.note(f"  !! the walk for '{area}' broke: {error!r}")
            # Every walk ends on the path, so the next one starts from
            # the same place a learner starts from.
            self.back_to_path()

    # -- helpers for the tour ----------------------------------------

    def on_path(self) -> bool:
        """Whether the path screen is the one on top."""
        return classify(self.read()).kind == "path"

    def open_more(self, item: str) -> bool:
        """Open an item of the "More" menu."""
        screen = self.read()
        if not any(text == item for text in screen.texts()):
            # The menu is closed: open it first.
            node = screen.find_desc("Още") or screen.find_text("Още")
            if node is None:
                self.note(f"  !! there is no 'Още' button")
                return False
            self.tap(node, "Още")
            time.sleep(0.4)
            screen = self.read()
        node = screen.find_text(item)
        if node is None:
            self.note(f"  !! the menu has no '{item}'")
            return False
        self.tap(node, item)
        time.sleep(0.6)
        return True

    def tap_first(self, *labels: str, note: str = "") -> bool:
        """Tap the first of the labels that is on the screen."""
        screen = self.read()
        for label in labels:
            node = screen.find_text(label)
            if node is not None:
                self.tap(node, label)
                return True
        if note:
            self.note(note)
        return False

    def tab_is_selected(self, node: Node) -> bool:
        """Whether the bottom-bar item of a label is the open one."""
        if node.selected:
            return True
        for ancestor in node.ancestors():
            if ancestor.selected:
                return True
        return False

    def find_switch(self) -> Node | None:
        """The switch of the screen, if there is one."""
        screen = self.read()
        for node in screen.nodes:
            if "Switch" in node.cls or "ToggleButton" in node.cls:
                return node
        return None

    def tap_desc_first(self, *descs: str) -> bool:
        screen = self.read()
        for desc in descs:
            node = screen.find_desc(desc)
            if node is not None:
                self.tap(node, f"[{desc}]")
                return True
        return False

    # -- the areas ----------------------------------------------------

    def tour_path(self) -> None:
        """The path screen: the lesson button and the review button."""
        if not self.on_path():
            self.note("  the path is not on the screen")
            return
        screen = self.read()
        self.note(f"  the path says: {screen.texts()[:8]}")
        # The review button is on the path only when something is due.
        # On the first day there is nothing, and the button is
        # correctly not there -- that is not a missing control.
        if any(text.startswith("Прегледай") for text in screen.texts()):
            self.tap_text("Прегледай")
        else:
            self.note("  nothing is due yet, so there is no review button")
        self.back_to_path()

    def tour_path_units(self) -> None:
        """The units of the path: they open and close."""
        if not self.on_path():
            return
        for _ in range(6):
            screen = self.read()
            node = screen.find_text("Покажи още")
            if node is None:
                break
            self.tap(node, "Покажи още")
            time.sleep(0.4)
            self.shot("path-expanded")
            screen = self.read()
            back = screen.find_text("Покажи по-малко")
            if back is None:
                break
            self.tap(back, "Покажи по-малко")
            time.sleep(0.4)

    def tour_badges(self) -> None:
        """The badges of the path."""
        if not self.on_path():
            return
        screen = self.read()
        node = screen.find_text("Значки")
        if node is None:
            self.note("  there is no 'Значки' on the path")
            return
        self.tap(node, "Значки")
        time.sleep(0.6)
        self.shot("badges")
        self.back_to_path()

    def tour_dictionary(self) -> None:
        """The dictionary: search in Chinese, search in Latin."""
        screen = self.read()
        node = screen.find_text("Речник")
        if node is None:
            self.note("  there is no 'Речник' tab")
            return
        self.tap(node, "Речник")
        time.sleep(0.8)
        self.shot("dictionary")
        for query in ("一", "ni", "你好"):
            screen = self.read()
            field = screen.find_desc("Търси китайски или латински")
            if field is None:
                field = screen.find_text("Търси китайски или латински")
            if field is None:
                self.note("  there is no search field")
                return
            # Focusing a field does not change the screen, so this tap
            # is not a dead button.
            self.tap(field, "Търси", expect_no_change=True)
            time.sleep(0.3)
            # Clear what the last search left behind: the learner
            # would select the text and replace it.
            self.device.key("KEYCODE_MOVE_END")
            for _ in range(12):
                self.device.key("KEYCODE_DEL")
            self.device.type_text(query)
            time.sleep(0.8)
            self.shot(f"dictionary-{query}")
            screen = self.read()
            self.note(f"  '{query}' -> {screen.texts()[:6]}")

    def tour_dictionary_filters(self) -> None:
        """The two filters of the dictionary."""
        screen = self.read()
        if "Търси китайски или латински" not in screen.texts():
            node = screen.find_text("Речник")
            if node is None:
                self.note("  there is no 'Речник' tab")
                return
            self.tap(node, "Речник")
            time.sleep(0.8)
        for label in ("Само човешки сверени глоси", "Честите думи"):
            screen = self.read()
            node = screen.find_text(label)
            if node is None:
                self.note(f"  there is no '{label}' in the dictionary")
                continue
            # The learner taps the WORDS of the filter. If the words
            # are not a control, the only way to work the filter is to
            # hit the small switch next to them -- and that is a
            # finding worth reporting.
            outcome = self.tap(node, label)
            time.sleep(0.7)
            if not outcome.changed:
                self.note(
                    f"  the words '{label}' are not a control: tapping them "
                    f"did nothing"
                )
                switch = self.find_switch()
                if switch is not None:
                    self.tap(switch, "[the switch next to it]")
                    time.sleep(0.7)
            self.shot(f"dictionary-filter-{label[:8]}")
            self.note(f"  after '{label}': {self.read().texts()[:6]}")

    def tour_dictionary_more(self) -> None:
        """The "show more" of the dictionary."""
        screen = self.read()
        if "Търси китайски или латински" not in screen.texts():
            node = screen.find_text("Речник")
            if node is None:
                return
            self.tap(node, "Речник")
            time.sleep(0.8)
        for _ in range(3):
            screen = self.read()
            node = screen.find_text("Покажи още")
            if node is None:
                break
            self.tap(node, "Покажи още")
            time.sleep(0.6)
        self.shot("dictionary-more")

    def tour_practice(self) -> None:
        """The five practice modes."""
        if not self.open_more("Упражнения"):
            return
        self.shot("practice")
        for mode in ("Производство", "Слушане", "Подреждане", "Писане", "Граматика"):
            screen = self.read()
            node = screen.find_text(mode)
            if node is None:
                self.scroll_modes(up=True)
                screen = self.read()
                node = screen.find_text(mode)
            if node is None:
                self.note(f"  !! the mode '{mode}' is not on the screen")
                continue
            self.tap(node, mode)
            time.sleep(0.6)
            self.shot(f"practice-{mode}")

    def tour_practice_help(self) -> None:
        """The help of each practice mode."""
        if not self.open_more("Упражнения"):
            return
        for mode in ("Производство", "Слушане", "Подреждане", "Писане", "Граматика"):
            screen = self.read()
            node = screen.find_text("Помощ")
            if node is None:
                break
            self.tap(node, "Помощ")
            time.sleep(0.5)
            self.shot(f"help-{mode}")
            screen = self.read()
            node = screen.find_text("Помощ")
            if node is not None:
                self.tap(node, "Помощ")
                time.sleep(0.4)

    def tour_review(self) -> None:
        """The review session."""
        if not self.open_more("Повторение"):
            return
        self.shot("review")
        for _ in range(4):
            screen = self.read()
            if "Няма карти за преглед." in screen.texts():
                self.note("  there is nothing to review")
                return
            if "Прегледът приключи." in screen.texts():
                self.note("  the review is over")
                return
            if "Покажи отговор" not in screen.texts():
                self.note("  there is no card to reveal")
                return
            if not self.tap_text("Покажи отговор").changed:
                return

    def tour_review_ratings(self) -> None:
        """The four ratings of the review card."""
        if not self.open_more("Повторение"):
            return
        for _ in range(3):
            screen = self.read()
            if "Покажи отговор" not in screen.texts():
                return
            self.tap_text("Покажи отговор")
            time.sleep(0.5)
            for rating in ("Отново", "Трудно", "Добре", "Лесно"):
                screen = self.read()
                node = screen.find_text(rating)
                if node is None:
                    continue
                self.tap(node, rating)
                time.sleep(0.5)
                break

    def tour_levels(self) -> None:
        """The level picker."""
        if not self.open_more("Нива"):
            return
        self.shot("levels")
        screen = self.read()
        self.note(f"  the levels are: {screen.texts()[:10]}")

    def tour_levels_jump(self) -> None:
        """Choosing a level, and where it sends the learner."""
        if not self.open_more("Нива"):
            return
        for _ in range(3):
            screen = self.read()
            node = None
            for candidate in screen.buttons():
                label = candidate.group_label()
                if label and ("HSK" in label or "Ниво" in label) and candidate.is_enabled:
                    node = candidate
                    break
            if node is None:
                self.note("  there is no level to choose")
                return
            self.tap(node, node.group_label())
            time.sleep(0.8)
            self.shot("level-chosen")
            self.note(f"  after the level: {self.read().texts()[:8]}")
            self.back()

    def tour_grammar(self) -> None:
        """The grammar reference."""
        if not self.open_more("Граматика"):
            return
        self.shot("grammar")
        screen = self.read()
        self.note(f"  the grammar says: {screen.texts()[:10]}")

    def tour_lesson_all_cards(self) -> None:
        """A lesson, through every kind of card it holds."""
        if not self.on_path():
            return
        if not self.tap_text("Започни урока").changed:
            self.note("  the lesson did not open")
            return
        self.lesson()

    def tour_onboarding_back(self) -> None:
        """The onboarding questions, and the way back out of them."""
        screen = self.read()
        card = classify(screen)
        if card.kind != "onboarding_goal":
            self.note("  the onboarding is already past")
            return
        # The back button is on the SECOND question: from the first
        # one there is nothing to go back to.
        self.tap_text("Напред")
        time.sleep(0.6)
        screen = self.read()
        if "Назад" not in screen.texts():
            self.note("  the second question has no 'Назад'")
            return
        self.tap_text("Назад")
        time.sleep(0.6)
        screen = self.read()
        self.note(f"  after 'Назад': {screen.texts()[:6]}")
        self.tap_text(self.persona.goal)
        self.tap_text("Напред")

    def ensure_app(self) -> None:
        """Make sure the app is in front of the learner.

        BACK on the path LEAVES the app: there is nothing behind the
        first screen. A learner who walks back out of the app opens
        it again -- and so does the student.
        """
        if self.device.is_foreground():
            return
        self.log.step("  the app is not in front, opening it again")
        self.device.start_app()
        time.sleep(3.0)

    def back_to_path(self) -> None:
        """Get back to the path, whatever we are on."""
        for _ in range(5):
            self.ensure_app()
            screen = self.read()
            if classify(screen).kind == "path":
                return
            # The tab of the path is the way a learner goes back -- but
            # only when another tab is the one that is open. Tapping
            # the tab that is already open changes nothing, and that
            # is not a finding about the app.
            node = screen.find_text("Път")
            if node is not None and not self.tab_is_selected(node):
                self.tap(node, "Път")
                time.sleep(0.6)
                continue
            node = screen.find_desc("Назад") or screen.find_text("Назад")
            if node is not None:
                self.tap(node, "Назад")
                time.sleep(0.5)
                continue
            self.back()
            time.sleep(0.6)

    # -- onboarding ------------------------------------------------

    def onboarding(self) -> None:
        screen = self.wait_for(("onboarding_goal", "path", "unknown"))
        card = classify(screen) if screen else None
        if card is None or card.kind not in ("onboarding_goal", "path"):
            self.note("ONBOARDING: the screen is not the one of the questions")
            return
        if card.kind != "onboarding_goal":
            self.note(f"ONBOARDING: skipped, already past it ({card.kind})")
            return
        self.note("ONBOARDING: goal question")
        self.tap_text(self.persona.goal)
        self.tap_text("Напред")
        screen = self.read()
        if classify(screen).kind != "onboarding_time":
            self.note("ONBOARDING: the time question did not open")
            return
        self.note(f"ONBOARDING: time question, choosing '{self.persona.minutes}'")
        self.tap_text(self.persona.minutes)
        self.tap_text("Към уроците")
        time.sleep(1.2)
        screen = self.read()
        self.note(f"ONBOARDING: done, now on '{classify(screen).kind}'")

    # -- the path --------------------------------------------------

    def path_loop(self) -> None:
        for lesson_number in range(1, self.persona.lessons + 1):
            if self.elapsed > self.max_seconds:
                self.note("TIME: out of budget, stopping the path")
                return
            screen = self.read()
            card = classify(screen)
            if card.kind != "path":
                self.note(f"PATH: expected the path screen, got '{card.kind}'")
                return
            self.describe_path(screen)
            if not self.tap_text("Започни урока").changed:
                self.note("PATH: 'Започни урока' did not open a lesson")
                return
            self.lesson()
            if self.stuck:
                return

    def describe_path(self, screen: Screen) -> None:
        """What the path screen says about the learner's place."""
        texts = screen.texts()
        title = ""
        for index, text in enumerate(texts):
            if text == "Следващият урок" and index + 1 < len(texts):
                title = texts[index + 1]
                break
        percent = ""
        for index, text in enumerate(texts):
            if text == "Напредък" and index + 1 < len(texts):
                percent = texts[index + 1]
                break
        words = ""
        for index, text in enumerate(texts):
            if text == "думи" and index > 0:
                words = texts[index - 1]
                break
        locked = sum(1 for text in texts if text.startswith("Заключен"))
        due = ""
        for text in texts:
            if text.startswith("Прегледай"):
                due = text
                break
        self.note(
            f"PATH: next='{title}' progress={percent} words={words} "
            f"locked={locked} due='{due}'"
        )

    # -- a lesson --------------------------------------------------

    def lesson(self) -> None:
        """One lesson, card by card."""
        card_index = 0
        total = 0
        lesson_key = ""
        while self.elapsed < self.max_seconds:
            screen = self.read()
            card = classify(screen)
            if card.kind == "lesson_result":
                self.note(self.result_line(screen))
                self.shot("lesson-result")
                self.tap_text("Обратно към пътя")
                return
            if card.kind in ("path", "unknown"):
                self.note(f"LESSON: the lesson ended on '{card.kind}'")
                return
            if card.kind == "lesson_recognise":
                total = self.position(screen)
                card_index += 1
                self.recognise(screen, card, card_index, total)
                continue
            if card.kind == "lesson_listen":
                total = self.position(screen)
                card_index += 1
                before = self.before.fingerprint() if self.before else ""
                self.listen(screen, card, card_index, total)
                # A card the learner cannot leave is a stuck lesson: the
                # student taps the same button for ever and the session
                # times out without saying why. When the screen does
                # not change, the card is stuck -- say so and stop.
                after = self.read().fingerprint()
                if after == before:
                    self.note(
                        f"LESSON: the card {card_index}/{total} did not change "
                        f"after the tap -- THE LEARNER CANNOT LEAVE IT"
                    )
                    self.stuck = True
                    return
                continue
            if card.kind == "lesson_say":
                total = self.position(screen)
                card_index += 1
                self.say(screen, card, card_index, total)
                continue
            if card.kind == "lesson_write":
                total = self.position(screen)
                card_index += 1
                self.write(screen, card, card_index, total)
                continue
            if card.kind == "lesson_review":
                self.note("LESSON: a review card")
                self.tap_text("Продължи")
                continue
            if card.kind == "lesson_reading":
                total = self.position(screen)
                card_index += 1
                self.note(f"LESSON card {card_index}/{total} READING")
                # The last card of the lesson ends it. The button says
                # so, and looking for the wrong one first would make
                # the student scroll a screen that does not change.
                if "Завърши урока" in screen.texts():
                    self.tap_text("Завърши урока")
                else:
                    self.tap_text("Следваща карта")
                continue
            self.note(f"LESSON: unknown screen, texts={screen.texts()[:8]}")
            return
        self.note("LESSON: out of budget")

    def position(self, screen: Screen) -> int:
        """The '3 of 28' counter in the header."""
        for text in screen.texts():
            match = re.match(r"^(\d+) от (\d+)$", text)
            if match:
                return int(match.group(2))
        return 0

    def result_line(self, screen: Screen) -> str:
        texts = screen.texts()
        score = ""
        for text in texts:
            if text.endswith("%"):
                score = text
        right = ""
        for text in texts:
            if "верни" in text:
                right = text
        if "Само преподаване" in texts:
            # A lesson that only taught: no question in it, so no
            # score. The words are tested in the next lesson.
            return "LESSON RESULT: taught only, no questions (tested next lesson)"
        verdict = "passed" if "Урокът е минат" in texts else "FAILED"
        return f"LESSON RESULT: {verdict} score={score} {right}"

    def tap_audio(self) -> Outcome:
        """Play the pronunciation.

        The screen does not change when the clip plays, so the tap is
        not a dead button.
        """
        node = self._target("🔊", exact=False)
        if node is None:
            node = self._target("Изслушай", exact=False)
        if node is None:
            self.log.step("  !! there is no audio button on this card")
            return Outcome(changed=False, note="missing")
        return self.tap(node, "🔊 Изслушай", expect_no_change=True)

    def listen(self, screen: Screen, card: Card, index: int, total: int) -> None:
        if card.hanzi and card.gloss:
            self.known[card.hanzi] = card.gloss
        self.note(
            f"LESSON card {index}/{total} LISTEN {card.hanzi} '{card.gloss}' "
            f"(known={len(self.known)})"
        )
        if self.persona.listens:
            self.tap_audio()
        self.tap_text("Продължи")

    def say(self, screen: Screen, card: Card, index: int, total: int) -> None:
        if card.hanzi and card.gloss:
            self.known[card.hanzi] = card.gloss
        self.note(f"LESSON card {index}/{total} SAY {card.hanzi} '{card.gloss}'")
        if self.persona.listens:
            self.tap_audio()
        self.tap_text("Продължи")

    def recognise(self, screen: Screen, card: Card, index: int, total: int) -> None:
        """The question. The answer is what the student has learned."""
        expected = self.known.get(card.hanzi, "")
        options = card.options
        self.note(
            f"LESSON card {index}/{total} RECOGNISE {card.hanzi} "
            f"options={options} expected='{expected}'"
        )
        if not options:
            self.note("  !! the question has NO options")
            self.tap_text("Продължи")
            return

        chosen = ""
        if self.persona.careful and expected:
            for option in options:
                if option.strip().lower() == expected.strip().lower():
                    chosen = option
                    break
            if not chosen:
                # The right answer is not among the options. That is a
                # defect in the card, and the student says so.
                self.note(
                    f"  !! the learned meaning '{expected}' is NOT among the "
                    f"options {options}"
                )
        if not chosen:
            # The student guesses: the first option it did not rule out.
            chosen = options[0]

        self.tap_text(chosen)
        time.sleep(0.4)
        after = self.read()
        texts = after.texts()
        if "Правилно!" in texts:
            verdict = "RIGHT"
        elif "Неправилно" in texts:
            verdict = "WRONG"
            shown = answered_gloss(after)
            self.note(
                f"  -> WRONG: chose '{chosen}', the app shows '{shown}'. "
                f"options were {options}"
            )
            self.shot(f"wrong-{index}")
        else:
            verdict = "?"
        if expected and chosen.strip().lower() != expected.strip().lower():
            self.note(
                f"  !! picked '{chosen}' but had learned '{expected}' -- "
                f"the app's answer was '{verdict}'"
            )
        self.tap_text("Продължи")

    def write(self, screen: Screen, card: Card, index: int, total: int) -> None:
        """The writing step: the student traces the character.

        The card has the stroke-order animation, the trace canvas and
        the button that ends the character. The card is taller than
        the screen, so the student scrolls: up first, to read the
        title of the card, and down to the canvas.
        """
        self.note(f"LESSON card {index}/{total} WRITE {card.hanzi} '{card.gloss}'")
        self.shot(f"write-{card.hanzi}-{index}")

        # The word may be more than one character, and the step goes
        # through them one by one. The card says how many strokes the
        # CURRENT character has, which is how the student knows which
        # character is on the canvas.
        screen = self.scroll_to_top(screen)
        stroke_count = self.stroke_count(screen)
        characters = list(card.hanzi)
        char_index = 0
        while True:
            screen = self.read()
            if classify(screen).kind != "lesson_write":
                self.note("  !! the write card is gone")
                return
            current_strokes = self.stroke_count(screen) or stroke_count
            medians = self.medians_for(characters, char_index, current_strokes)
            traced = self.trace_strokes(screen, card.hanzi, medians)
            if traced is None:
                self.note("  !! the trace canvas could not be located")
                return
            time.sleep(0.5)
            screen = self.read()
            for text in screen.texts():
                if "Правилни щрихи" in text:
                    self.note(f"  -> {text}")
            # The next character, or the end of the step.
            if char_index < len(characters) - 1:
                if not self.tap_text("Следващ знак").changed:
                    self.note("  !! 'Следващ знак' did not move on")
                    return
                char_index += 1
                continue
            if not self.tap_text("Готово").changed:
                self.note("  !! 'Готово' did not move on")
                return
            # "Готово" confirms the LAST character: the card then shows
            # the verdict and a "Продължи" button, and the learner taps
            # it to leave the card. The harness has to do the same, or
            # it stays on the card and traces it for ever.
            time.sleep(0.4)
            screen = self.read()
            if "Продължи" in screen.texts():
                self.tap_text("Продължи")
            return

    def scroll_to_top(self, screen: Screen) -> Screen:
        """Scroll the card back up, so the title is on the screen."""
        for _ in range(5):
            if self.stroke_count(screen) > 0:
                return screen
            self.scroll_up()
            screen = self.read()
        return screen

    def stroke_count(self, screen: Screen) -> int:
        """How many strokes the character on the canvas has."""
        for text in screen.texts():
            match = re.search(r"Ред на щрихите \((\d+)\)", text)
            if match:
                return int(match.group(1))
        return 0

    def medians_for(
        self, characters: list[str], index: int, strokes: int
    ) -> list[list[list[float]]] | None:
        """The stroke data of the character that is on the canvas.

        The card does not name the character, so the student uses the
        stroke count: the character of the word with that many strokes
        is the one on the canvas.
        """
        for offset in range(index, len(characters)):
            medians = load_medians(characters[offset])
            if strokes and len(medians) != strokes:
                continue
            return medians
        return None

    def trace_strokes(
        self, screen: Screen, hanzi: str, medians: list[list[list[float]]] | None
    ) -> int | None:
        """Draw the character, the way the app expects it.

        The medians of the character come out of the database -- the
        same rows the app draws from -- and they are walked with the
        finger, in order, from the first stroke to the last.
        """
        canvas = self.locate_canvas(screen)
        if canvas is None:
            return None
        if medians is None:
            self.note(f"  !! no stroke data for '{hanzi}'")
            return 0
        left, top, width = canvas
        scale = width / 1024.0
        for median in medians:
            points = []
            for point in median:
                x = left + point[0] * scale
                y = top + (1024 - point[1]) * scale
                points.append((int(x), int(y)))
            self.device.drag(points)
            time.sleep(0.2)
        return len(medians)

    def locate_canvas(self, screen: Screen) -> tuple[int, int, int] | None:
        """Where the trace canvas is: left, top and width, in pixels.

        The canvas carries the name "канавка за писане" -- it is the
        one thing on the card with no text, and a learner needs a way
        to point at it. When the name is not there (an older build, or
        a card that draws nothing), the canvas is found from the
        layout: it is the square under the "Проследи знака с пръст"
        hint, on the right of the stroke order.
        """
        named = screen.find_desc("канавка за писане")
        if named is not None:
            left, top, right, bottom = named.bounds
            width = right - left
            if width > 0:
                return left, top, width

        for _ in range(3):
            hint = screen.find_text("Проследи знака с пръст")
            clear = screen.find_text("Изчисти")
            if hint is not None and clear is not None:
                left = hint.bounds[0]
                width = screen.width - 2 * left
                return left, hint.bounds[3], width
            screen = self.read()
            if classify(screen).kind != "lesson_write":
                return None
            self.scroll_down()
        return None

    # -- the other screens -----------------------------------------

    def review(self) -> None:
        """The review session, from the path screen."""
        screen = self.read()
        card = classify(screen)
        if card.kind != "path":
            self.note(f"REVIEW: not on the path ({card.kind})")
            return
        # The button "Прегледай N карти за днес" is on the path only
        # when there IS something due. A learner who has just installed
        # the app has nothing to review, and the button is correctly
        # not there. That is not a dead end -- it is the absence of a
        # thing that does not exist yet.
        if not any(text.startswith("Прегледай") for text in screen.texts()):
            self.note("REVIEW: nothing is due yet, so there is no review to do")
            return
        if not self.tap_containing("Прегледай").changed:
            self.note("REVIEW: the button was on the screen but did not open")
            return
        seen = 0
        while self.elapsed < self.max_seconds and seen < 40:
            screen = self.read()
            card = classify(screen)
            if card.kind != "review":
                self.note(f"REVIEW: ended on '{card.kind}'")
                return
            if "Няма карти за преглед." in screen.texts() or "Прегледът приключи." in screen.texts():
                self.note(f"REVIEW: {card.text[:60]}")
                return
            if "Покажи отговор" in screen.texts():
                self.tap_text("Покажи отговор")
                continue
            # The card is revealed: rate it.
            seen += 1
            self.tap_text("Добре")
        self.note(f"REVIEW: rated {seen} card(s)")

    def practice(self) -> None:
        """The five practice modes."""
        screen = self.read()
        card = classify(screen)
        if card.kind != "path":
            self.note(f"PRACTICE: not on the path ({card.kind})")
            return
        self.tap_desc("Още")
        screen = self.read()
        if not self.tap_text("Упражнения").changed:
            self.note("PRACTICE: 'Упражнения' did not open")
            return
        for mode in ("Производство", "Слушане", "Подреждане", "Писане", "Граматика"):
            if self.elapsed > self.max_seconds:
                return
            screen = self.read()
            if classify(screen).kind != "practice":
                self.note(f"PRACTICE: left the practice screen ({classify(screen).kind})")
                return
            node = screen.find_text(mode)
            if node is None:
                # The list of the modes is taller than a small screen.
                # After the learner picks a mode the screen scrolls DOWN
                # to the exercise, so the list is now ABOVE the fold:
                # scroll UP first, then down.
                self.note(f"PRACTICE: '{mode}' is not visible, scrolling the list")
                self.scroll_modes(up=True)
                screen = self.read()
                node = screen.find_text(mode)
                if node is None:
                    self.scroll_modes(up=False)
                    screen = self.read()
                    node = screen.find_text(mode)
                if node is None:
                    self.note(f"PRACTICE: '{mode}' is STILL not reachable")
                    continue
            self.note(f"PRACTICE: mode '{mode}'")
            self.tap(node, mode)
            time.sleep(0.6)
            screen = self.read()
            self.note(f"  screen: {screen.texts()[:10]}")
            self.shot(f"practice-{mode}")
            self.practice_one(mode, screen)

            # The help of the mode: the learner asks for it with the
            # "Помощ" button and the longer text opens under the row.
            self.open_help(mode)
            self.shot(f"practice-{mode}-help")

    def scroll_modes(self, up: bool = True) -> None:
        """Move the list of the modes.

        The list is above the exercise, and choosing a mode scrolls the
        screen down to the exercise -- so after the first choice the
        list has to be found by scrolling UP.
        """
        width, height = self.device.size()
        x = int(width * 0.5)
        if up:
            self.device.swipe(x, int(height * 0.3), x, int(height * 0.8), 300)
        else:
            self.device.swipe(x, int(height * 0.7), x, int(height * 0.3), 300)
        time.sleep(0.4)

    def open_help(self, mode: str) -> None:
        """Open the help of a mode and check that it says something."""
        screen = self.read()
        node = screen.find_text("Помощ")
        if node is None:
            self.note(f"  HELP: the button 'Помощ' is not on the screen")
            return
        self.tap(node, "Помощ")
        time.sleep(0.5)
        after = self.read()
        # The help is longer than the one-line description, so the
        # screen must have changed.
        if after.fingerprint() == screen.fingerprint():
            self.note("  HELP: the button 'Помощ' changed nothing")
            return
        texts = after.texts()
        if not any(len(t) > 40 for t in texts):
            self.note(f"  HELP: no longer text appeared, the screen holds {texts[:8]}")
        else:
            self.note("  HELP: the longer help opened")
        # It is a toggle: the second tap closes it.
        node = after.find_text("Помощ")
        if node is not None:
            self.tap(node, "Помощ")
            time.sleep(0.4)

    def practice_one(self, mode: str, screen: Screen) -> None:
        """Do one thing in a practice mode, so the mode is really used."""
        if mode == "Производство":
            self.tap_text("Следваща дума")
            screen = self.read()
            # Only the FIELD carries the description "Пиньин". The
            # help text of the mode mentions the word too, and a text
            # match there is the help paragraph, not something to type
            # into.
            field = screen.find_desc("Пиньин")
            if field is not None:
                self.device.tap(*field.center)
                time.sleep(0.4)
                self.device.type_text("ni")
                time.sleep(0.6)
                self.log.step("  typed 'ni' into the pinyin field")
                self.shot("practice-production-typed")
        elif mode == "Слушане":
            # The exercise is "hear it, then say which one it is". The
            # student answers first, the way the screen asks, and then
            # moves on.
            self.tap_audio()
            self.tap_text("Това е думата")
            time.sleep(0.5)
            self.tap_text("Следваща дума")
        elif mode == "Подреждане":
            # The tokens have to be placed BEFORE "Провери" is
            # available: the button is greyed out until the answer is
            # built, and a greyed-out button does nothing when it is
            # tapped. The student places the tokens first.
            screen = self.read()
            tray = [
                node
                for node in screen.buttons()
                if node.group_label()
                and node.group_label() not in ("Провери", "Следващо изречение")
                and node.group_label() not in ("Помощ",)
                and node.is_enabled
            ]
            for node in tray[:4]:
                self.tap(node, node.group_label())
                time.sleep(0.3)
            self.tap_text("Провери")
        elif mode == "Писане":
            self.shot("practice-writing")
        elif mode == "Граматика":
            self.tap_text("Следващ въпрос")

    def tap_desc(self, desc: str) -> Outcome:
        node = self.before.find_desc(desc) if self.before else None
        if node is None:
            self.log.step(f"  !! no element with the description '{desc}'")
            return Outcome(changed=False, note="missing")
        return self.tap(node, f"[{desc}]")

    def dictionary(self) -> None:
        """The dictionary: a search and a browse."""
        screen = self.read()
        if classify(screen).kind != "path":
            self.note(f"DICTIONARY: not on the path ({classify(screen).kind})")
            return
        # The dictionary is a tab at the bottom.
        node = screen.find_text("Речник")
        if node is None:
            self.note("DICTIONARY: the 'Речник' tab is not on the screen")
            return
        self.tap(node, "Речник")
        time.sleep(0.6)
        screen = self.read()
        self.note(f"DICTIONARY: {screen.texts()[:6]}")
        hint = screen.find_text("Търси китайски или латински")
        if hint is not None:
            self.device.tap(*hint.center)
            time.sleep(0.4)
            self.device.type_text("ni")
            time.sleep(0.8)
            screen = self.read()
            self.note(f"DICTIONARY: search 'ni' -> {screen.texts()[:6]}")
            self.shot("dictionary-search")
        # The browse mode and the switch.
        self.scroll_up()
        screen = self.read()
        switches = [n for n in screen.nodes if n.cls.endswith("Switch")]
        if switches:
            self.tap(switches[0], "human-glosses switch")
            time.sleep(0.6)
            screen = self.read()
            self.note(f"DICTIONARY: after the switch -> {screen.texts()[:6]}")

    def levels(self) -> None:
        """The level picker."""
        screen = self.read()
        if classify(screen).kind != "path":
            self.note(f"LEVELS: not on the path ({classify(screen).kind})")
            return
        self.tap_desc("Още")
        screen = self.read()
        if not self.tap_text("Нива").changed:
            self.note("LEVELS: 'Нива' did not open")
            return
        screen = self.read()
        self.note(f"LEVELS: {screen.texts()[:12]}")
        self.shot("levels")


UI_IGNORE = {
    "Какво означава?",
    "Продължи",
    "Правилно!",
    "Неправилно",
    "машинен превод — може да е неточен",
    "1. Чуй",
    "2. Разпознай",
    "3. Произнеси",
    "4. Напиши",
}


def answered_gloss(screen: Screen) -> str:
    """The meaning the app shows after a wrong answer.

    It is the plain text under the verdict: the options are buttons,
    so the text that is NOT inside a button and NOT a label of the
    app is the meaning.
    """
    from .students import card_body

    for node in card_body(screen):
        if not node.text:
            continue
        if node.text in UI_IGNORE:
            continue
        if any(ancestor.is_button for ancestor in node.ancestors()):
            continue
        if is_gloss(node.text):
            return node.text
    return ""


_MEDIAN_CACHE: dict[str, list[list[list[float]]]] = {}


def load_medians(hanzi: str) -> list[list[list[float]]]:
    """The stroke data of a character, from the shipped database.

    The app draws from the same rows, so a trace that follows these
    points is a trace the app should accept. If it is not, the defect
    is in the app, not in the student.
    """
    if hanzi in _MEDIAN_CACHE:
        return _MEDIAN_CACHE[hanzi]
    db = REPO / "data" / "content.db"
    medians: list[list[list[float]]] = []
    if db.exists():
        connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT medians FROM characters WHERE char = ?", (hanzi,)
            ).fetchone()
        finally:
            connection.close()
        if row and row[0]:
            medians = json.loads(row[0])
    _MEDIAN_CACHE[hanzi] = medians
    return medians

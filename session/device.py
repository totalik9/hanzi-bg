"""The adb side of a student session.

The harness drives the app the way a finger does: it reads the screen
with `uiautomator dump`, finds a node by its text, and taps the middle
of it. Nothing here knows what the app is -- the students in
`students.py` do.

Two things are worth knowing about the dump:

* Compose puts every visible text in the tree as an `android.widget.
  TextView`, and the clickable thing around it as an `android.view.View`
  with `clickable="true"`. Tapping the middle of the TEXT node works
  for both, so the harness always taps text, never the parent.
* A node that is laid out below the bottom of the window is not in the
  dump at all. A button the learner cannot see is a button that does
  not exist as far as the harness is concerned -- which is the same as
  it is for the learner, and is why the harness scrolls before it
  gives up.
"""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ADB = r"C:/tools/android-sdk/platform-tools/adb.exe"

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class Node:
    """One node of the screen tree."""

    text: str = ""
    desc: str = ""
    cls: str = ""
    rid: str = ""
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    checkable: bool = False
    checked: bool = False
    selected: bool = False
    scrollable: bool = False
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]

    @property
    def is_enabled(self) -> bool:
        """Whether this node can be pressed.

        The flag of a DISABLED Compose button sits on the clickable
        view around the label, and the label itself still says
        enabled="true". So the answer comes from the nearest clickable
        ancestor, not from this node.
        """
        if self.clickable:
            return self.enabled
        for ancestor in self.ancestors():
            if ancestor.clickable:
                return ancestor.enabled
        return self.enabled

    @property
    def is_button(self) -> bool:
        """Whether this node is a button of the app.

        Compose draws a button as a clickable `android.view.View` with
        the label in a child, and it also emits an empty
        `android.widget.Button` next to it. So the label of a button
        is the text of its child, and the button node itself carries
        no text.
        """
        return self.cls.endswith("Button") or self.clickable

    def label(self) -> str:
        """What to call this node in the log."""
        if self.text:
            return self.text
        if self.desc:
            return f"[{self.desc}]"
        if self.is_button:
            child = self.child_text()
            if child:
                return child
        return self.cls.rsplit(".", 1)[-1] or "node"

    def child_text(self) -> str:
        """The label of a button: the text of its child."""
        for child in self.children:
            if child.text:
                return child.text
            if child.desc:
                return child.desc
        return ""

    def group_label(self) -> str:
        """The label of a clickable thing, wherever the label sits.

        Compose puts the label of a button next to the button node
        rather than inside it, so the search goes through the parent's
        children too.
        """
        if self.text:
            return self.text
        if self.desc:
            return self.desc
        own = self.child_text()
        if own:
            return own
        if self.parent is not None:
            for sibling in self.parent.children:
                if sibling is self:
                    continue
                text = sibling.child_text() or sibling.text or sibling.desc
                if text:
                    return text
        return ""

    def ancestors(self) -> list["Node"]:
        out: list[Node] = []
        node = self.parent
        while node is not None:
            out.append(node)
            node = node.parent
        return out

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Node({self.label()!r}, {self.bounds}, clickable={self.clickable})"


@dataclass
class Screen:
    """The screen as the harness sees it."""

    nodes: list[Node] = field(default_factory=list)
    width: int = 0
    height: int = 0

    @classmethod
    def parse(cls, xml_text: str, width: int = 0, height: int = 0) -> "Screen":
        nodes: list[Node] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return cls([], width, height)

        def walk(element, parent: Node | None) -> None:
            for child_element in element.findall("node"):
                match = _BOUNDS.match(child_element.get("bounds", ""))
                bounds = (
                    tuple(int(g) for g in match.groups()) if match else (0, 0, 0, 0)
                )
                node = Node(
                    text=child_element.get("text", ""),
                    desc=child_element.get("content-desc", ""),
                    cls=child_element.get("class", ""),
                    rid=child_element.get("resource-id", ""),
                    clickable=child_element.get("clickable") == "true",
                    enabled=child_element.get("enabled") == "true",
                    focused=child_element.get("focused") == "true",
                    checkable=child_element.get("checkable") == "true",
                    checked=child_element.get("checked") == "true",
                    selected=child_element.get("selected") == "true",
                    scrollable=child_element.get("scrollable") == "true",
                    bounds=bounds,
                    parent=parent,
                )
                nodes.append(node)
                if parent is not None:
                    parent.children.append(node)
                walk(child_element, node)

        walk(root, None)
        return cls(nodes, width, height)

    # -- finding ---------------------------------------------------

    def texts(self) -> list[str]:
        """Every visible text, in the order the tree has them."""
        return [n.text for n in self.nodes if n.text]

    def all_text(self) -> str:
        return "\n".join(self.texts())

    def find_text(self, needle: str, exact: bool = True) -> Node | None:
        for node in self.nodes:
            if not node.text:
                continue
            if (node.text == needle) if exact else (needle in node.text):
                return node
        return None

    def find_desc(self, needle: str) -> Node | None:
        for node in self.nodes:
            if node.desc == needle:
                return node
        return None

    def find_containing(self, needle: str) -> list[Node]:
        return [n for n in self.nodes if n.text and needle in n.text]

    def find_clickable(self) -> list[Node]:
        return [n for n in self.nodes if n.clickable and n.enabled]

    def buttons(self) -> list[Node]:
        """Every clickable thing on the screen, with its label.

        The label of a Compose button sits next to the button node
        rather than inside it, so the label is looked up through the
        parent. A button appears twice in the tree -- once as a
        clickable view and once as an empty `android.widget.Button` --
        so only the first of each label is kept.
        """
        out = []
        seen: set[str] = set()
        for node in self.nodes:
            if node.is_button and node.enabled:
                label = node.group_label()
                if label and label not in seen:
                    seen.add(label)
                    out.append(node)
        return out

    def button_labels(self) -> list[str]:
        return [node.group_label() for node in self.buttons()]

    def button(self, label: str) -> Node | None:
        for node in self.buttons():
            if node.group_label() == label:
                return node
        return None

    def fingerprint(self) -> str:
        """A short digest of the screen, used to tell one state from another.

        The digest covers more than the text. Choosing an answer in the
        onboarding changes no text at all -- it enables the "Напред"
        button -- and a screen that only changed its state still
        changed. So the ENABLED flag of every node is part of the
        digest, and so is the FOCUSED one.
        """
        import hashlib

        parts = sorted(
            f"{n.text}|{n.bounds}|e={int(n.enabled)}|f={int(n.focused)}"
            f"|c={int(n.checked)}|s={int(n.selected)}"
            for n in self.nodes
            if n.text or n.checkable or n.cls.endswith("Button")
        )
        return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:10]

    def clipped(self) -> list[Node]:
        """Nodes that stick out of the window -- text the learner cannot read."""
        out = []
        for node in self.nodes:
            if not node.text:
                continue
            left, top, right, bottom = node.bounds
            if right > self.width or bottom > self.height or left < 0 or top < 0:
                out.append(node)
        return out


PACKAGE = "bg.hanzi.learn.debug"


class Device:
    """One emulator, seen through adb."""

    def __init__(self, serial: str, adb: str = ADB, timeout: int = 60):
        self.serial = serial
        self.adb = adb
        self.timeout = timeout
        self._size = (0, 0)

    # -- plumbing --------------------------------------------------

    def _run(self, args: list[str], binary: bool = False):
        cmd = [self.adb, "-s", self.serial] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )

    def shell(self, command: str) -> str:
        result = self._run(["shell", command])
        return result.stdout.decode("utf-8", "replace").strip()

    def exec_out(self, command: str) -> bytes:
        result = self._run(["exec-out", command])
        return result.stdout

    # -- screen ----------------------------------------------------

    def size(self) -> tuple[int, int]:
        if self._size == (0, 0):
            out = self.shell("wm size")
            match = re.search(r"(\d+)x(\d+)", out)
            self._size = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
        return self._size

    def dump(self, retries: int = 4) -> Screen:
        """Read the screen.

        The tree is written to a FILE and read back, not taken from
        /dev/tty: the tty way leaves the UiAutomation connection open
        when the emulator is busy, and the next read then fails with
        "Bad file descriptor" -- the screen looks empty, the student
        walks into nothing, and the finding is about the harness and
        not about the app.

        An empty tree is retried, and only a tree that stays empty is
        reported as a screen.
        """
        for attempt in range(retries):
            self.shell("uiautomator dump /sdcard/hanzi_ui.xml")
            raw = self.exec_out("cat /sdcard/hanzi_ui.xml")
            text = raw.decode("utf-8", "replace")
            start = text.find("<?xml")
            end = text.rfind("</hierarchy>")
            if start >= 0 and end >= 0:
                width, height = self.size()
                screen = Screen.parse(
                    text[start : end + len("</hierarchy>")], width, height
                )
                if screen.nodes:
                    return screen
            time.sleep(1.5 + attempt)
        return Screen([], *self.size())

    # -- actions ---------------------------------------------------

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def tap_node(self, node: Node) -> None:
        x, y = node.center
        self.tap(x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 400) -> None:
        self.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {duration}")

    def scroll_down(self, amount: int = 700) -> None:
        """Scroll the page down (the content moves up)."""
        width, height = self.size()
        x = width // 2
        self.swipe(x, int(height * 0.75), x, int(height * 0.25), 300)

    def scroll_up(self, amount: int = 700) -> None:
        width, height = self.size()
        x = width // 2
        self.swipe(x, int(height * 0.30), x, int(height * 0.80), 300)

    def type_text(self, value: str) -> None:
        safe = value.replace(" ", "%s").replace("'", "")
        self.shell(f"input text '{safe}'")

    def key(self, code: str) -> None:
        self.shell(f"input keyevent {code}")

    def back(self) -> None:
        self.key("KEYCODE_BACK")

    def drag(self, points: list[tuple[int, int]], step_ms: int = 24) -> None:
        """Draw one stroke through the given points.

        The WHOLE gesture goes into ONE shell call. Each `input
        motionevent` is a separate process with its own clock, so when
        the calls are made one after another over adb the framework
        sees a MOVE that belongs to no gesture and throws it away: the
        character is never drawn and the stroke counter stays at 0.
        """
        if len(points) < 2:
            return
        first = points[0]
        parts = [f"input motionevent DOWN {first[0]} {first[1]}"]
        for x, y in points[1:]:
            parts.append(f"input motionevent MOVE {x} {y}")
        last = points[-1]
        parts.append(f"input motionevent UP {last[0]} {last[1]}")
        self.shell("; ".join(parts))

    # -- app -------------------------------------------------------

    def package(self) -> str:
        return "bg.hanzi.learn.debug"

    def clear_app(self) -> None:
        self.shell(f"pm clear {self.package()}")

    def is_foreground(self) -> bool:
        """Whether the app is the one in front.

        The check has to be right: a wrong "no" makes the student open
        the app again and again, and a wrong "yes" leaves the student
        staring at the home screen.
        """
        for command in (
            "dumpsys activity activities | grep -m1 mResumedActivity",
            "dumpsys window | grep -m1 mCurrentFocus",
            "dumpsys window windows | grep -m1 mCurrentFocus",
        ):
            out = self.shell(command)
            if PACKAGE in out:
                return True
            if out and "mCurrentFocus" in out:
                # Another app is in front: that is a real "no".
                return False
        return True

    def start_app(self) -> None:
        self.shell(
            f"am start -n {self.package()}/bg.hanzi.learn.MainActivity"
        )

    def stop_app(self) -> None:
        self.shell(f"am force-stop {self.package()}")

    def install(self, apk: str) -> None:
        subprocess.run(
            [self.adb, "-s", self.serial, "install", "-r", apk],
            capture_output=True,
            timeout=600,
            check=False,
        )

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.exec_out("screencap -p")
        path.write_bytes(data)

    def is_running(self) -> bool:
        out = self.shell(f"pidof {self.package()}")
        return bool(out.strip())

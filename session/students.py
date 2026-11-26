"""The two students, and the walk they take through the app.

A "student" here is a persona: the same app, driven by two different
people. One is careful and answers what it has learned; the other is
in a hurry, guesses, and tries to get out of a lesson it does not like.
Both walk the WHOLE app -- onboarding, the path, the lessons, the
review, the five practice modes, the dictionary and the level picker --
because the interesting defects live in the transitions, not in one
screen.

The careful student is the one that finds the traps that a learner
falls into:

* A question the learner cannot answer because the meaning was never
  shown -- the student answers from what it learned on the LISTEN card
  and logs when it could not.
* An option that is the same as the right answer -- the student picks
  the one it believes and the app says it is wrong; the log shows the
  two texts.
* A card with no way out -- the student presses Back and the log says
  what happened.
* A wrong answer that paints every option red -- the student takes a
  screenshot of it, and the analyzer samples the colours.

The hasty student adds the mistakes a real beginner makes: it taps
through the options in order, it leaves the lesson halfway, it looks
for the grammar and the levels on its own.

What the students CANNOT do is read the database. They see the screen
and they tap it, exactly like a person.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .device import Device, Node, Screen

# The strings the app itself puts on the screen. A student knows them
# and does not confuse them with the content.
UI_STRINGS = {
    "Път",
    "Речник",
    "Още",
    "Повторение",
    "Упражнения",
    "Граматика",
    "Нива",
    "Пътят е минат",
    "Всички уроци са завършени. Продължи с упражненията или преглеждай речника.",
    "Следващият урок",
    "Започни урока",
    "Напредък",
    "Значки",
    "Пътят",
    "думи",
    "ден поред",
    "дни поред",
    "днес",
    "Завършен",
    "Заключен",
    "Повтори",
    "Започни",
    "Заключен, докато не минеш предходния урок",
    "Ханзи BG",
    "Ще научиш китайски стъпка по стъпка. Първо два въпроса, после първия урок.",
    "Защо учиш китайски?",
    "За изпит HSK",
    "Целта е да минеш нивата 1 до 3",
    "За пътуване",
    "Менюта, знаци, разговори",
    "За работа",
    "Да общувам с колеги",
    "За удоволствие",
    "Просто ми харесва езикът",
    "Колко време имаш на ден?",
    "5 минути",
    "15 минути",
    "30 минути",
    "1 час",
    "Назад",
    "Към уроците",
    "Можеш да промениш целта и времето си по-късно в профила.",
    "1. Чуй",
    "2. Разпознай",
    "3. Произнеси",
    "4. Напиши",
    "Какво означава?",
    "Изслушай",
    "Продължи",
    "Готово",
    "Следващ знак",
    "Предишен знак",
    "Изчисти",
    "Правилно!",
    "Неправилно",
    "Проследи знака с пръст",
    "Ред на щрихите (%1$d)",
    "Пусни пръст по контура на знака.",
    "Правилни щрихи: %1$d / %2$d",
    "Проследи знака с пръст. Ще се броят само правите щрихи.",
    "Изслушай и повтори на глас",
    "Урокът е минат",
    "Още не е минат",
    "Прочетено до края",
    "Обратно към пътя",
    "Покажи отговор",
    "Отново",
    "Трудно",
    "Добре",
    "Лесно",
    "Няма карти за преглед.",
    "Прегледът приключи.",
    "Търси китайски или латински",
    "Само човешки сверени глоси",
    "Няма резултати.",
    "Честите думи",
    "Покажи още",
    "Избери ниво",
    "Ниво:",
    "Производство",
    "Слушане",
    "Подреждане",
    "Писане",
    "Все още няма граматични теми.",
}

CJK = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")
CYRILLIC = re.compile(r"[\u0400-\u04ff]")
LATIN = re.compile(r"[A-Za-z]")


def is_hanzi(text: str) -> bool:
    """A text that is nothing but Chinese characters."""
    stripped = text.strip()
    if not stripped or not CJK.search(stripped):
        return False
    return not LATIN.search(stripped) and not CYRILLIC.search(stripped)


def is_gloss(text: str) -> bool:
    """A text that could be the meaning of a word: Bulgarian words."""
    return bool(CYRILLIC.search(text)) and text not in UI_STRINGS


@dataclass
class Card:
    """What the student knows about the screen it is looking at."""

    screen: Screen
    kind: str = "unknown"
    hanzi: str = ""
    gloss: str = ""
    options: list[str] = field(default_factory=list)
    body_texts: list[str] = field(default_factory=list)
    example: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.screen.all_text()


def classify(screen: Screen) -> Card:
    """What screen is this?

    The markers are the words the app puts on the screen, so the
    classifier is a set of string tests and nothing else.

    The lesson screen has a HEADER -- the unit, the lesson title, the
    progress bar and the "2 of 30" counter -- and a BODY with the card
    itself. The two must not be mixed: the unit of the numbers lesson
    is called "Числа" (numbers), and a student that read the header
    for the card would learn the wrong word. So the body is the part
    below the counter, and only the body is read.
    """
    texts = screen.texts()
    joined = "\n".join(texts)

    def has(text: str) -> bool:
        return text in texts

    card = Card(screen=screen)

    if has("Защо учиш китайски?"):
        card.kind = "onboarding_goal"
        return card
    if has("Колко време имаш на ден?"):
        card.kind = "onboarding_time"
        return card
    if has("Търси китайски или латински"):
        card.kind = "dictionary"
        return card
    if has("Избери ниво"):
        card.kind = "levels"
        return card
    # The path is recognised by its OWN title -- "Пътят е минат" -- and
    # by the tab of the path being the selected one. The tab is the
    # reliable sign: the path itself scrolls, and "Следващият урок"
    # can be out of sight while the learner is further down.
    # The SELECTED tab of the bottom bar is the sign of the path. The
    # flag is on the clickable item, and the label is on a child of
    # it, so the ancestors of the label are asked.
    path_tab_selected = False
    for node in screen.nodes:
        if node.text != "Път":
            continue
        if node.selected:
            path_tab_selected = True
            break
        for ancestor in node.ancestors():
            if ancestor.selected:
                path_tab_selected = True
                break
        if path_tab_selected:
            break
    if (
        has("Следващият урок")
        or has("Пътят е минат")
        or path_tab_selected
        or (has("Напредък") and has("Път"))
    ):
        card.kind = "path"
        return card
    if (
        has("Урокът е минат")
        or has("Още не е минат")
        or has("Прочетено до края")
        # A lesson that only TAUGHT has no score and no question in it.
        or has("Само преподаване")
    ):
        card.kind = "lesson_result"
        return card
    if has("Покажи отговор") or has("Няма карти за преглед.") or has("Прегледът приключи."):
        card.kind = "review"
        return card

    # The practice screen shows the list of the five modes. The label
    # of the level is on it too ("Ниво: HSK 1-2"), and it is what
    # identifies the screen after the learner has scrolled the list
    # out of sight.
    practice_modes = {"Производство", "Слушане", "Подреждане", "Писане"}
    if practice_modes & set(texts) or any(
        text.startswith("Ниво:") for text in texts
    ):
        card.kind = "practice"
        return card

    if has("1. Чуй"):
        card.kind = "lesson_listen"
    elif has("3. Произнеси"):
        card.kind = "lesson_say"
    elif (
        has("4. Напиши")
        or has("Проследи знака с пръст")
        or has("Ред на щрихите")
    ):
        # The write card. The title scrolls out of sight when the
        # student scrolls down to the canvas, so the card is also
        # recognised by the two labels that stay.
        card.kind = "lesson_write"
    elif has("Какво означава?"):
        card.kind = "lesson_recognise"
    elif has("Следваща карта") or has("Завърши урока"):
        # A reading lesson: it teaches the sound system with cards and
        # there is no question to answer.
        card.kind = "lesson_reading"
    elif "Преглед:" in joined:
        card.kind = "lesson_review"
    else:
        return card

    body = card_body(screen)
    card.body_texts = [n.text for n in body if n.text]

    # The character and the meaning of the card's word. Both are plain
    # text: a label inside a button is a label of the app, not the
    # content of the card.
    for text in plain_texts(body):
        if is_hanzi(text) and not card.hanzi:
            card.hanzi = text
        elif is_gloss(text) and not card.gloss:
            card.gloss = text

    if card.kind == "lesson_recognise":
        # The options are the CLICKABLE groups of the card: each one
        # is a card with a label in it. The header and the labels of
        # the card are not clickable, so they cannot be mistaken for
        # answers.
        card.options = [
            label
            for label in body_clickable_labels(body)
            if label not in ("Продължи",) and not label.startswith("🔊")
        ]
        # The gloss of the card is shown only AFTER the answer, so it
        # is not part of the options.
        card.gloss = ""
        # The example sentence under the question. Its label is
        # "В изречение", and the sentence itself is a run of Chinese
        # that is not the word of the card.
        if has("В изречение"):
            card.example = [
                text
                for text in plain_texts(body)
                if is_hanzi(text) and text != card.hanzi
            ]

    return card


def plain_texts(nodes: list[Node]) -> list[str]:
    """The texts that are not inside a clickable thing.

    A button's label is a label of the app -- "Изслушай", "Продължи" --
    and a student that read it as the meaning of the word would learn
    nonsense.
    """
    out = []
    for node in nodes:
        if not node.text:
            continue
        if any(ancestor.is_button for ancestor in node.ancestors()):
            continue
        out.append(node.text)
    return out


def body_clickable_labels(nodes: list[Node]) -> list[str]:
    """The labels of the clickable things among the given nodes."""
    out = []
    for node in nodes:
        if node.clickable:
            label = node.group_label()
            if label and label not in out:
                out.append(label)
    return out


def body_button_labels(nodes: list[Node]) -> list[str]:
    """The labels of the buttons among the given nodes."""
    out = []
    for node in nodes:
        if node.cls.endswith("Button"):
            label = node.group_label()
            if label:
                out.append(label)
    return out


def card_body(screen: Screen) -> list[Node]:
    """The nodes of the card, without the header above it.

    The header ends with the "2 of 30" counter. When the counter is
    not there, the whole screen is the body.
    """
    counter = None
    for node in screen.nodes:
        if re.match(r"^\d+ от \d+$", node.text or ""):
            counter = node
            break
    if counter is None:
        return list(screen.nodes)
    top = counter.bounds[3]
    return [n for n in screen.nodes if n.bounds[3] > top]


def body_button_labels(nodes: list[Node]) -> list[str]:
    """The labels of the buttons among the given nodes."""
    out = []
    for node in nodes:
        if node.is_button:
            label = node.child_text()
            if label:
                out.append(label)
    return out


@dataclass
class Persona:
    """How one student behaves."""

    key: str
    title: str
    goal: str = "За изпит HSK"
    minutes: str = "15 минути"
    # Whether the student tries to answer correctly.
    careful: bool = True
    # Whether the student plays the audio of every word.
    listens: bool = False
    # Whether the student tries to leave a lesson it does not like.
    restless: bool = False
    # How many lessons the student walks through.
    lessons: int = 3
    # The number of wrong answers the careful student allows itself.
    mistakes: int = 0
    # The parts of the app this student is here to exercise. The list
    # is a set of names from the catalogue in runner.py; the union of
    # the fifteen students covers every click of the app.
    focus: tuple[str, ...] = ()
    # Whether the student reads every word of the screen before
    # tapping anything (slow, and it finds text that does not fit).
    reads: bool = False
    # Whether the student presses BACK to see what happens.
    presses_back: bool = False
    # Whether the student tries to leave a screen by tapping outside
    # of what it wants.
    wanders: bool = False
    # How long this student walks, in seconds. The student that walks
    # EVERYTHING needs more time than the one that looks at the path.
    budget: int = 360
    # The learner starts with this many words already learned, so the
    # writing step (which joins after 20) and the review (which needs
    # cards that are due) are on the screen at all.
    seed_words: int = 0


PERSONAS = {
    "careful": Persona(
        key="careful",
        title="Внимателният ученик",
        careful=True,
        listens=True,
        restless=False,
        lessons=6,
        mistakes=0,
    ),
    "hasty": Persona(
        key="hasty",
        title="Бързата ученичка",
        goal="За работа",
        minutes="5 минути",
        careful=False,
        listens=False,
        restless=True,
        lessons=2,
        mistakes=0,
    ),
}


# ---------------------------------------------------------------------------
# The fifteen students.
#
# The app has about thirty places a finger can go: the two tabs, the
# four items of the "More" menu, the path with its badges and its
# units, the four kinds of lesson card, the result screen, the review
# with its four ratings, the five practice modes with their help, the
# dictionary with its search and its two filters, the level picker,
# the grammar reference and the onboarding questions.
#
# Fifteen students, each one with a different set of those places and
# a different temper, so that the union of their walks reaches every
# click AND every one of them is stressed in a different way: a
# careful student on a small screen finds the buttons that fall off
# the edge, a hasty student finds the ones that do nothing, a
# wandering student finds the ones that lead nowhere.
# ---------------------------------------------------------------------------

_STUDENTS = [
    Persona(
        key="s01_path",
        title="Ученикът от пътя",
        focus=("path", "path_units", "badges"),
        careful=True,
        lessons=1,
    ),
    Persona(
        key="s02_dictionary",
        title="Речниколюбецът",
        focus=("dictionary", "dictionary_filters", "dictionary_more"),
        careful=True,
        reads=True,
    ),
    Persona(
        key="s03_practice",
        title="Треньорът",
        focus=("practice", "practice_help"),
        careful=True,
    ),
    Persona(
        key="s04_review",
        title="Повтарящият се",
        focus=("review", "review_ratings"),
        careful=True,
        seed_words=25,
        budget=600,
    ),
    Persona(
        key="s05_levels",
        title="Избирачът на нива",
        focus=("levels", "levels_jump"),
        careful=True,
    ),
    Persona(
        key="s06_grammar",
        title="Грамматикът",
        focus=("grammar",),
        careful=True,
        reads=True,
    ),
    Persona(
        key="s07_lesson_types",
        title="Ученикът по карти",
        focus=("lesson_all_cards",),
        careful=True,
        lessons=3,
        seed_words=25,
        budget=600,
    ),
    Persona(
        key="s08_hasty_phone",
        title="Бързата на малък екран",
        goal="За пътуване",
        minutes="5 минути",
        careful=False,
        restless=True,
        focus=("path", "lesson_all_cards", "practice"),
        lessons=1,
    ),
    Persona(
        key="s09_back",
        title="Оният, който се връща",
        presses_back=True,
        focus=("lesson_all_cards", "dictionary", "levels", "practice", "grammar"),
        careful=False,
        lessons=1,
        budget=480,
        seed_words=25,
    ),
    Persona(
        key="s10_wanderer",
        title="Скитникът",
        wanders=True,
        focus=("path", "practice", "dictionary", "review", "levels"),
        careful=False,
        lessons=1,
        budget=480,
    ),
    Persona(
        key="s11_reader",
        title="Читателят",
        reads=True,
        careful=True,
        focus=("dictionary", "grammar", "path_units"),
        lessons=1,
    ),
    Persona(
        key="s12_onboarding",
        title="Новобранeцът",
        focus=("onboarding_back", "path"),
        careful=True,
        lessons=1,
    ),
    Persona(
        key="s13_night",
        title="Нощният ученик",
        goal="Да общувам с колеги",
        minutes="1 час",
        careful=True,
        listens=True,
        focus=("lesson_all_cards", "practice", "review"),
        lessons=2,
        seed_words=25,
        budget=600,
    ),
    Persona(
        key="s14_quitter",
        title="Напускачът",
        goal="Просто ми харесва езикът",
        minutes="15 минути",
        careful=False,
        restless=True,
        mistakes=3,
        focus=("path", "lesson_all_cards"),
        lessons=1,
    ),
    Persona(
        key="s15_everything",
        title="Изчерпателният",
        careful=True,
        listens=True,
        reads=True,
        focus=(
            "path",
            "path_units",
            "badges",
            "lesson_all_cards",
            "review",
            "review_ratings",
            "practice",
            "practice_help",
            "dictionary",
            "dictionary_filters",
            "dictionary_more",
            "levels",
            "levels_jump",
            "grammar",
            "onboarding_back",
        ),
        lessons=2,
        budget=600,
        seed_words=25,
    ),
]

PERSONAS.update({persona.key: persona for persona in _STUDENTS})

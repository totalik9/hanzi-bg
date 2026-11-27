"""Build the lesson files of the HSK 2-4 path from the themed words.

    python pipeline/build_lessons.py       (writes curriculum/40_hsk2to4.json)

THE ORDER OF THE PATH

The path is level-major: everything of HSK 2, then everything of HSK 3,
then everything of HSK 4. The learner meets the easy words before the
hard ones, and a word of HSK 4 is never taught before a word of HSK 2
just because the two happen to share a theme.

Inside a level the order is by THEME, and the theme is a field of life
(the body, the house, the road). A theme is a teaching decision, so it
is written down here and not derived from the corpus.

A lesson is 8 to 15 words of the SAME theme, and the words inside it
are ordered so the learner meets the simple ones first: the single
character before the compound, the more common word before the rarer
one. The order inside a theme is the order of the THEME, not the
alphabet -- a theme has an order the learner can follow, and the
alphabet is not one.

The unit title is the title of the theme. The lesson title is short
and says what the lesson holds, so the learner can tell two lessons
of the same theme apart.

The file that is written is the PATH: units, lessons and their words.
The Bulgarian glosses are written by hand and live in a separate
patch file -- see `check_lesson_files.py` for the rules they follow.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURRICULUM = os.path.join(ROOT, "curriculum")
TMP = os.environ.get("TMPDIR", ROOT)

#: The curriculum rule: a lesson carries 8 to 15 words.
MIN_LESSON_WORDS = 8
MAX_LESSON_WORDS = 15

#: The levels of the path, in the order the learner meets them.
LEVELS = ("2", "3", "4")

#: The themes, in the order the learner meets them inside a level. The
#: order is a teaching decision: the concrete and the daily come
#: before the abstract and the institutional.
THEME_ORDER = [
    "greetings", "numbers", "people", "family", "body", "food",
    "home", "time", "nature", "places", "travel", "schoolwork",
    "education", "shopping", "questions", "adverbs",
    "describing", "verbs", "media",
]

#: The theme titles, in Bulgarian. They are the titles the learner
#: reads on the path screen.
THEME_TITLES = {
    "greetings": "Поздрави и учтивост",
    "numbers": "Числа и количества",
    "people": "Хора, чувства и отношения",
    "family": "Семейство и близки",
    "body": "Тяло и здраве",
    "food": "Храна и напитки",
    "home": "Дом и вещи",
    "time": "Време и дни",
    "nature": "Природа и животни",
    "places": "Места и посока",
    "travel": "Път и пътуване",
    "schoolwork": "Училище и работа",
    "education": "Образование и знание",
    "shopping": "Пари и цени",
    "questions": "Въпроси и връзки",
    "adverbs": "Наречия и начин",
    "describing": "Качества и описание",
    "verbs": "Глаголи и действия",
    "media": "Култура и медии",
}

#: The lesson titles, by theme. They say what the lesson holds, so two
#: lessons of the same theme can be told apart on the path screen.
LESSON_TITLES = {
    "greetings": ["Поздрави и благодарности", "Учтивост и извинения",
                  "Покана и пожелание"],
    "numbers": ["Броене и числа", "Големи числа и количества",
                "Мерки и размери"],
    "people": ["Хора и лични местоимения", "Чувства и настроение",
               "Характер и поведение", "Отношения и приятелство"],
    "family": ["Семейство и род", "Съпрузи и деца"],
    "body": ["Части на тялото", "Болки и симптоми", "Спорт и движение"],
    "food": ["Храна и ястия", "Напитки и вкусове", "В ресторанта"],
    "home": ["Дом и стаи", "Мебели и вещи", "Дрехи и обувки"],
    "time": ["Дни и часове", "Месеци и години", "Сезони и празници"],
    "nature": ["Времето и небето", "Растения и дървета", "Животни и хора"],
    "places": ["Места в града", "Сгради и помещения", "Страни и посоки"],
    "travel": ["Видове транспорт", "Път и улици", "Пътуване и багаж"],
    "schoolwork": ["Училище и ученици", "Уроци и учене", "Работа и служба"],
    "education": ["Университет и образование", "Книги и знание",
                  "Наука и изследване"],
    "shopping": ["Пари и банка", "Цени и плащане", "Магазин и купувач"],
    "questions": ["Въпросителни думи", "Фрази и отговори", "Връзки и причина"],
    "adverbs": ["Честота и време", "Степени на сравнение", "Начин на действие"],
    "describing": ["Качества и оценки", "Външен вид", "Състояние и качество"],
    "verbs": ["Глаголи за работа", "Глаголи за движение", "Глаголи за учене",
              "Глаголи за чувства"],
    "media": ["Култура и изкуство", "Медии и вестници", "Технологии и интернет"],
}


#: The titles of the units that hold more than one theme. A unit that
#: holds two fields says both, but in one phrase and not as a list.
GROUP_TITLES = {
    ("numbers", "people", "family"): "Числа, хора и семейство",
    ("food", "home", "time", "nature"): "Всекиднещият свят",
    ("schoolwork", "education"): "Училище и образование",
    ("verbs", "media"): "Глаголи и медии",
    ("greetings", "numbers"): "Поздрави и числа",
    ("people", "family"): "Хора и семейство",
    ("education", "shopping"): "Знание и пари",
}


def load_words() -> dict[str, dict]:
    """Every HSK 2-4 word, by its hanzi."""
    words: dict[str, dict] = {}
    for level in LEVELS:
        path = os.path.join(TMP, f"hsk{level}_words.json")
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: missing {path}")
        with open(path, encoding="utf-8") as fh:
            for word in json.load(fh):
                word["level"] = level
                words[word["hanzi"]] = word
    return words


def sort_key(word: dict) -> tuple:
    """The order the learner meets the words of a theme in.

    The single character first, then the compound: 一 is a word the
    learner can use on its own, and 一会儿 is a word that needs it.
    Then the more frequent word, then the shorter one, and the hanzi
    last so the order is stable between runs.
    """
    return (
        len(word["hanzi"]),
        -int(word.get("freq") or 0),
        len(word["hanzi"]),
        word["hanzi"],
    )


def lesson_count(size: int) -> int | None:
    """The number of lessons that hold `size` words, or None.

    A lesson carries 8 to 15 words, so a unit of `size` words needs a
    number of lessons `k` with 8k <= size <= 15k. Every size from 8
    upwards can be split that way, so this returns None only for a
    unit that is too small to be a unit at all.
    """
    for count in range(1, size + 1):
        if MIN_LESSON_WORDS * count <= size <= MAX_LESSON_WORDS * count:
            return count
    return None


def split_sizes(size: int, count: int) -> list[int]:
    """The size of every lesson of a unit, spread as evenly as the
    rule allows. 25 words over three lessons are 9, 8 and 8."""
    base, extra = divmod(size, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def lessons_for(size: int) -> list[int] | None:
    """The sizes of the lessons of a unit of `size` words, or None.

    The lessons are as FULL as the rule allows: a unit of 30 words is
    two lessons of 15 and not three lessons of 10, because a lesson of
    fifteen teaches the same words as a lesson of ten and the learner
    meets them in fewer steps.
    """
    for count in range(1, size + 1):
        if not (MIN_LESSON_WORDS * count <= size <= MAX_LESSON_WORDS * count):
            continue
        sizes = split_sizes(size, count)
        # The lessons have to be full: a lesson of 8 next to a lesson
        # of 15 is two lessons where one would do.
        if min(sizes) < MIN_LESSON_WORDS:
            continue
        if max(sizes) - min(sizes) > 1:
            continue
        return sizes
    return None


def group_themes(sizes: dict[str, int], order: list[str]) -> list[list[str]]:
    """Group the themes of a level into units that can be split.

    A theme with fewer than 8 words can never be a unit of its own --
    there is no lesson that holds three words -- so it has to join
    another theme.

    Every theme that CAN be a unit is one. The themes are not piled
    into a single unit: a unit is a field of life, and a unit that
    holds the body, the house and the road is not a field, it is the
    whole level with a name on it.

    The groups keep the order of the themes, so the learner meets the
    units in the order the themes come in.
    """
    groups: list[list[str]] = [[name] for name in order if sizes.get(name)]
    while True:
        # The first group that is too small to be a unit.
        index = next((i for i, group in enumerate(groups)
                      if sum(sizes[g] for g in group) < MIN_LESSON_WORDS),
                     None)
        if index is None:
            return groups
        size = sum(sizes[g] for g in groups[index])
        # The group joins the group before it, or the group after it.
        # Either way the result has to be splittable.
        merged = False
        for other in (index - 1, index + 1):
            if other < 0 or other >= len(groups):
                continue
            total = (sum(sizes[g] for g in groups[index])
                     + sum(sizes[g] for g in groups[other]))
            if lessons_for(total) is None:
                continue
            if other < index:
                groups[other].extend(groups[index])
                del groups[index]
            else:
                groups[other] = groups[index] + groups[other]
                del groups[index]
            merged = True
            break
        if not merged:
            raise SystemExit(
                f"ERROR: the theme {groups[index]} ({size} words) cannot "
                f"be grouped into a unit of {MIN_LESSON_WORDS} to "
                f"{MAX_LESSON_WORDS} words per lesson")


def split_sizes(size: int, count: int) -> list[int]:
    """The size of every lesson of a unit, spread as evenly as the
    rule allows. 25 words over three lessons are 9, 8 and 8."""
    base, extra = divmod(size, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def build_units(themed: dict[str, list[str]],
                words: dict[str, dict]) -> list[dict]:
    """The units of the path, level by level and theme by theme."""
    units: list[dict] = []
    for level in LEVELS:
        # The words of every theme of this level.
        sizes: dict[str, int] = {}
        members: dict[str, list[str]] = {}
        for theme in THEME_ORDER:
            words_of_theme = [w for w in themed.get(theme, [])
                              if words[w].get("level") == level]
            if not words_of_theme:
                continue
            sizes[theme] = len(words_of_theme)
            members[theme] = words_of_theme

        # The themes that are too small to be a unit are joined to a
        # neighbour, so that every unit holds at least eight words.
        for group in group_themes(sizes, THEME_ORDER):
            group_members: list[str] = []
            for theme in group:
                group_members.extend(members[theme])
            ordered = sorted(group_members, key=lambda h: sort_key(words[h]))
            sizes_ = lessons_for(len(ordered))
            if sizes_ is None:
                raise SystemExit(
                    f"ERROR: the unit {group} of HSK {level} holds "
                    f"{len(ordered)} words, which cannot be split into "
                    f"lessons of {MIN_LESSON_WORDS} to {MAX_LESSON_WORDS}")
            chunks: list[list[str]] = []
            cursor = 0
            for size in sizes_:
                chunks.append(ordered[cursor:cursor + size])
                cursor += size

            # The title of the unit is the title of its theme, or a
            # title written for the group. A unit that holds two
            # fields says both, and a unit that holds one says it.
            title = GROUP_TITLES.get(tuple(group))
            if title is None:
                title = " и ".join(THEME_TITLES.get(theme, theme)
                                   for theme in group)
            unit_key = "-".join(f"hsk{level}-{theme}" for theme in group)
            lesson_titles = LESSON_TITLES.get(group[0]) or [title]
            lessons = []
            for index, chunk in enumerate(chunks):
                key = f"{unit_key}-{index + 1}"
                lesson_title = (lesson_titles[index]
                                if index < len(lesson_titles)
                                else f"{lesson_titles[-1]} ({index + 1})")
                lessons.append({"key": key, "title": lesson_title,
                                "words": chunk})
            units.append({
                "key": unit_key,
                "title": title,
                "lessons": lessons,
            })
    return units


def main() -> int:
    themed_path = os.path.join(TMP, "themed.json")
    if not os.path.exists(themed_path):
        raise SystemExit(f"ERROR: missing {themed_path} - run assign_themes.py")
    with open(themed_path, encoding="utf-8") as fh:
        themed = json.load(fh)
    words = load_words()

    units = build_units(themed, words)

    # The file name controls where the path sits in the sequence: the
    # curriculum files are read in name order, so "12_" puts the new
    # levels after HSK 1 and before the reading passages of "30_".
    #
    # THE DRAFT NEVER OVERWRITES THE COMMITTED PATH
    #
    # The path is a hand-maintained file in version control: the
    # lessons of a theme are a TEACHING decision, and the glosses of
    # the words are written by hand against those lessons. A script
    # that rewrites it silently destroys both -- and it destroys them
    # without a word, because the file still parses.
    #
    # So the draft is written to the SCRATCH directory, and the
    # committed file is only replaced when somebody asks for it with
    # --write. That is the difference between a generator and an
    # accident.
    #
    # The draft is NOT written beside the path on purpose: the content
    # builder reads EVERY json file of curriculum/, and a second file
    # of units would put every word of the path on it twice.
    draft = os.path.join(TMP, "12_hsk2to4.draft.json")
    target = draft
    if "--write" in sys.argv:
        target = os.path.join(CURRICULUM, "12_hsk2to4.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"units": units}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    total_words = sum(len(l["words"]) for u in units for l in u["lessons"])
    total_lessons = sum(len(u["lessons"]) for u in units)
    print(f"written {target}")
    if target == draft:
        print(f"   this is a DRAFT. The committed path is "
              f"curriculum/12_hsk2to4.json; it is replaced only with "
              f"--write.")
    print(f"   {len(units)} units, {total_lessons} lessons, {total_words} words")
    for unit in units:
        sizes = [len(l["words"]) for l in unit["lessons"]]
        print(f"   {unit['key']:14} {unit['title'][:30]:32} "
              f"lessons={len(sizes):3} words={sum(sizes):4} sizes={sizes[:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

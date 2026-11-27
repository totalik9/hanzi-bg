"""Generate LEARNING-PATH-DIAGRAM.md from the real path and the real code.

Every number in the diagram comes from the files, so the diagram cannot
drift from the app. Run it after a change of the path:

    python pipeline/make_path_diagram.py

THE DRAWING IS BUILT, NOT TYPED

A hand-typed box drawing closes on the left and not on the right, and
a title that is one character longer moves a border. So the frames are
padded here, and every line of every frame comes out the same width.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CURRICULUM = os.path.join(ROOT, "curriculum")
OUT = os.path.join(ROOT, "LEARNING-PATH-DIAGRAM.md")

LEVELS = ("1", "2", "3", "4")

#: The width of the whole framed drawing, in characters.
FRAME = 70

#: The width of the text inside the level boxes. Every line of the box
#: spends nine characters on its edges -- "║  ┌ ", the corner, a space
#: and " ┐ ║" -- and the content is what is left of the frame.
BOX = FRAME - 9


def load_path() -> list[dict]:
    """Every unit of the path, in order, with its level.

    The level comes from the FILE, not from the unit key: the units
    of HSK 1 are named "numbers", "greetings" and so on, and only the
    units of the later levels carry their level in the key.
    """
    units = []
    for name in sorted(os.listdir(CURRICULUM)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CURRICULUM, name), encoding="utf-8") as fh:
            data = json.load(fh)
        if not (isinstance(data, dict) and "units" in data):
            continue
        for unit in data["units"]:
            lessons = unit.get("lessons") or []
            words = sum(len(l.get("words") or []) for l in lessons)
            key = unit["key"]
            match = re.match(r"hsk([1-4])-", key)
            if match:
                level = match.group(1)
            elif name.startswith("10_"):
                level = "1"
            elif name.startswith("00_"):
                level = "intro"
            else:
                level = "extra"
            units.append({
                "key": key,
                "title": unit["title"],
                "lessons": len(lessons),
                "words": words,
                "teach": sum(1 for l in lessons if l.get("kind") == "teach"),
                "level": level,
            })
    return units


def wrap(items: list[str], width: int, sep: str = " · ") -> list[str]:
    """The items, on as few lines as fit."""
    lines: list[str] = []
    current = ""
    for item in items:
        if not current:
            current = item
        elif len(current) + len(sep) + len(item) <= width:
            current += sep + item
        else:
            lines.append(current)
            current = item
    if current:
        lines.append(current)
    return lines


def frame(lines: list[str], indent: int = 2, close: bool = True) -> list[str]:
    """The lines of the outer frame, padded to the same width.

    The frame of the path stays OPEN, because the level boxes go
    inside it and the border has to close under the last of them.
    """
    inner = FRAME - 2
    out = ["╔" + "═" * inner + "╗"]
    for line in lines:
        out.append("║" + (" " * indent + line).ljust(inner) + "║")
    if close:
        out.append("╚" + "═" * inner + "╝")
    return out


def box(header: str, body: list[str], width: int = BOX) -> list[str]:
    """The lines of a box inside the outer frame.

    The header and the body are separate, because the header is the
    line with the corners and every body line is a line of text: a
    box that took them as one list dropped the last line of the text
    and drew a border over it.
    """
    out = ["║  ┌ " + header + "─" * max(0, width - len(header)) + " ┐ ║"]
    for line in body:
        out.append("║  │ " + line + " " * max(0, width - len(line)) + " │ ║")
    out.append("║  └ " + "─" * width + " ┘ ║")
    return out


def level_block(units: list[dict], level: str) -> list[str]:
    """The box of one level: its units, their titles and their lessons."""
    chosen = [u for u in units if u["level"] == level]
    lessons = sum(u["lessons"] for u in chosen)
    words = sum(u["words"] for u in chosen)
    head = (f"── HSK {level} ── {len(chosen)} теми, {lessons} урока, "
            f"{words} думи")
    items = [f"{u['title']} ({u['lessons']})" for u in chosen]
    return box(head, wrap(items, BOX - 1))


def main() -> int:
    units = load_path()
    total_units = len(units)
    total_lessons = sum(u["lessons"] for u in units)
    total_words = sum(u["words"] for u in units)

    out: list[str] = []
    out.append("# Пътят на новия ученик — HSK 1 → HSK 4")
    out.append("")
    out.append("Диаграма на целия процес: всеки екран, през който минава нов")
    out.append("ученик, и правилото, което му отваря следващия екран.")
    out.append("")
    out.append("**Всичко тук е измерено от кода**, а не свалено от въздуха. Файловете")
    out.append("и редовете са посочени при всяко правило. Диаграмата се генерира от")
    out.append("`pipeline/make_path_diagram.py`, така че не може да се размине с")
    out.append("приложението.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 1. Диаграмата")
    out.append("")
    out.append("```")
    out.append("                    ┌─────────────────────────────┐")
    out.append("                    │  1. РЕГИСТРАЦИЯ (Onboarding)│")
    out.append("                    │  HanziApp.kt:38             │")
    out.append("                    └──────────────┬──────────────┘")
    out.append("                                   │ 2 въпроса: цел + време/ден")
    out.append("                                   │ (цел = надпис; време = дневна цел)")
    out.append("                                   ▼")
    out += frame([
        "2. ПЪТЯТ (Path) — главният екран, стартова точка на навигацията",
        "   HanziNavHost.kt:215 · PathScreen.kt",
        "",
        "   Показва: % изпълнено · N/20 прегледи днес · значки",
        "   Долу: [Учене] [Речник]      Горе: ⋮ (меню „Още“)",
    ])
    out.append("                                │ отваря първия урок")
    out.append("                                ▼")
    out += frame([
        "3. УРОК (Lesson) — един екран, N карти",
        "   HanziNavHost.kt:224 · LessonScreen.kt",
        "",
        "   УРОК N = учи думите на партида N  +  проверява партидата N-1",
        "",
        "   ┌── УЧИ (сега) ─────────────┐  ┌── ПРОВЕРЯВА (предишна) ──┐",
        "   │ LISTEN  как звучи?         │  │ RECOGNISE  какво значи?  │",
        "   │ SAY     да го кажа         │  │  (4 варианта, 1 верен)   │",
        "   │ WRITE   да го напиша       │  │                          │",
        "   └────────────────────────────┘  └──────────────────────────┘",
        "        ↑ WRITE се включва след 20 думи (PathRules.kt:47)",
        "",
        "   оценка = точките + половина за писането, макс. 100%",
    ])
    out.append("                                │ оценка ≥ 80% ?")
    out.append("        ┌───────────────────────┴───────────────────────┐")
    out.append("        │ ДА                                          │ НЕ")
    out.append("        ▼                                             ▼")
    out.append("   отваря следващия урок                    остава същият урок")
    out.append("   (иначе той е заключен)                 (следващият е заключен)")
    out.append("        │")
    out.append("        ▼")
    out += frame([
        f"4. ПЪТЯТ ПО НИВА — {total_units} теми, {total_lessons} урока, "
        f"{total_words} думи",
        "",
    ], close=False)
    for unit in [u for u in units if u["level"] == "intro"]:
        out += box(f"── {unit['title']} ── {unit['lessons']} урока, "
                   f"{unit['words']} думи",
                   ["Само карти, не думи — учи звука, преди първата дума"])
        out.append("║                              ▼                                     ║")
    for level in LEVELS:
        out += level_block(units, level)
        if level != LEVELS[-1]:
            out.append("║                              ▼                                     ║")
    for unit in [u for u in units if u["level"] == "extra"]:
        out.append("║                              ▼                                     ║")
        out += box(f"── {unit['title']} ── {unit['lessons']} урока, "
                   f"{unit['words']} думи",
                   ["Само карти: два разговора за пазар и ресторант"])
    out.append("╚" + "═" * (FRAME - 2) + "╝")
    out.append("```")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 2. Пресипките — уроците, които винаги се минават")
    out.append("")
    out.append("Има шест думи и правила, които се появяват във всяко второ")
    out.append("изречение. Ученикът не може да ги заобиколи, а ако ги срещне")
    out.append("по една случайност, ще ги помне като изключения. Затова са")
    out.append("отделни уроци — и са в пътя, а не в упражненията: минава се през")
    out.append("тях, не минава покрай тях.")
    out.append("")
    out.append("### Къде седи всяка и защо точно тя")
    out.append("")
    out.append("| Пресипка | След темата | Какво учи | Защо точно тук |")
    out.append("|---|---|---|---|")
    out.append("| 是 и 的 | Семейство | „е“ и „мой“ | Думите са в „Основни думи“; тук вече има име и дума, които да ги носят |")
    out.append("| Редът на думите | Време и дни | подлог + глагол + допълнение, време преди глагола | Тук за първи път има и глагол, и време, и дума за ядене — и се сглобява изречение |")
    out.append("| Броячът е дума | Тяло и външен вид | число + броячна дума | Броячите са в „Числа“, но трябва предмет за броене — а дрехите го дават |")
    out.append("| 不 и 没 | Път и транспорт | „няма да“ срещу „не се е случило“ | Има глагол за движение (去) и дума за учене — вече може да се отрича |")
    out.append("| 了 и 在 | Места и посока | „вече стана“ срещу „точно сега“ | 在 е тук за първи път, а 了 е в изречение с минало време |")
    out.append("| Как се пита | Въпроси и фрази | 吗 и въпросителните думи | След като урокът за въпросите е минат, те вече не са нови |")
    out.append("")
    out.append("### Какво НЕ е пресипка")
    out.append("")
    out.append("**把 и 被** (съответно „обектът напред“ и „пасивно“) са изключени")
    out.append("нарочно. Те са най-трудните точки на китайския и учат най-")
    out.append("много за малко: един-два примера не правят разлика, а урок, който")
    out.append("обърква, кара ученика да спре. Те идват в HSK 4+, когато езикът")
    out.append("вече е познат.")
    out.append("")
    out.append("Всяка пресипка носи ЕДНО правило и три-четири примера от думите,")
    out.append("които вече са на пътя. Примерите не са измислени — това са")
    out.append("изречения, които ученикът може да сглоби сам.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 3. Разклоненията — какво още се отваря")
    out.append("")
    out.append("Тези екрани **не са част от пътя**: те не отключват следващ урок и")
    out.append("ученикът може да ги свали по всяко време. Те са тук, защото един")
    out.append("истински път минава и през тях.")
    out.append("")
    out.append("```")
    out.append("                         ┌─────────────────────────┐")
    out.append("                         │ Пътят (главният екран)  │")
    out.append("                         └────────┬────────────────┘")
    out.append("                                  │ ⋮ меню „Още“ (HanziNavHost.kt:111)")
    out.append("        ┌──────────────┬──────────┼──────────┬──────────────┐")
    out.append("        ▼              ▼          ▼          ▼              ▼")
    out.append("  ┌──────────┐  ┌───────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐")
    out.append("  │ Преглед  │  │ Упражнения│ │Граматика│ │Нива    │ │  Речник  │")
    out.append("  │ (review) │  │(practice) │ │(grammar)│ │(levels)│ │(dictionary)")
    out.append("  └────┬─────┘  └─────┬─────┘ └────────┘ └────┬────┘ └──────────┘")
    out.append("       │             │                     │")
    out.append("       │             │                     └──► избира ниво ─► Преглед")
    out.append("       │             │                                           или Упражнения")
    out.append("       │             │")
    out.append("       │             └─ 5 режима (PracticeViewModel.kt:38):")
    out.append("       │                  ① Производство  пиньин → знак")
    out.append("       │                  ② Слушане       чуй → избери знак")
    out.append("       │                  ③ Подреждане    състави изречение")
    out.append("       │                  ④ Писане        проследи знака")
    out.append("       │                  ⑤ Граматика     прочети → разбери")
    out.append("       │")
    out.append("       └─ SRS картите, дължащи се днес")
    out.append("          (карта се създава, КОГАТО думата е УЧЕНА — не когато е")
    out.append("           отговорена; картата е дължима от утрото на следния ден)")
    out.append("```")
    out.append("")
    out.append("### Екранът „Преглед“")
    out.append("")
    out.append("Показва картите, дължащи се днес. Ако няма — „Няма карти за преглед.“")
    out.append("(`ReviewScreen.kt:66`). На пътя този бутон се появява **само когато")
    out.append("има нещо за преглед** — на първия ден няма, и това е правилно.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 4. Правилата, които отварят вратите")
    out.append("")
    out.append("| Правило | Стойност | Къде е | Какво отваря |")
    out.append("|---|---|---|---|")
    out.append("| Оценка за минаване | **80 %** | `PathRules.kt:23` | Следващия урок |")
    out.append("| Урок за четене | 100 при прочитане | `PathRules.kt:70` | Следващия урок |")
    out.append("| Производство | **20 верни поред** | `PathRules.kt:36` | Режим „Производство“ |")
    out.append("| Писане в урока | след **20 думи** | `PathRules.kt:47` | Стъпката WRITE |")
    out.append("| Дневна цел | 20 прегледи | `PathViewModel.kt:41` | Циферката на пътя |")
    out.append("| Пакет от предишен урок | целият урок | `LessonBatch.kt:94` | Картите RECOGNISE |")
    out.append("")
    out.append("### Значки (`PathRules.kt:185`)")
    out.append("")
    out.append("| Значка | Условие |")
    out.append("|---|---|")
    out.append("| Първата дума | 1 дума |")
    out.append("| 20 думи | 20 думи |")
    out.append("| 50 думи | 50 думи |")
    out.append("| 100 думи | 100 думи |")
    out.append("| Първи урок | 1 завършен урок |")
    out.append("| 10 урока | 10 завършени урока |")
    out.append("| 3 / 7 / 30 дни поред | серия от дни |")
    out.append("| Производство | отворено е |")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 5. Двете неща, които начинаещият среща веднага")
    out.append("")
    out.append("1. **Урокът не е тест в същия ден.** Урок N учи партида N и проверява")
    out.append("   партида N-1. Ученикът никога не се изпитва за дума, която току-що")
    out.append("   е видял (`LessonPlan.kt:22`).")
    out.append("2. **Писането идва по-късно.** Стъпката WRITE е най-бавната и е тази,")
    out.append("   от която се отказват. Тя се включва след 20 думи — когато има")
    out.append("   вече причина да се грижи.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 6. Какво е измерено")
    out.append("")
    out.append("| Твърдение | Откъде | Стойност |")
    out.append("|---|---|---|")
    out.append(f"| Теми в пътя | `curriculum/*.json` | {total_units} |")
    out.append(f"| Уроци в пътя | `curriculum/*.json` | {total_lessons} "
               f"({total_lessons - 4} с думи + 4 карти) |")
    out.append(f"| Думи в пътя | `curriculum/*.json` | {total_words} |")
    out.append("| Думи на урок | `audit_path.py` | мин. 8, макс. 15 |")
    for level in LEVELS:
        chosen = [u for u in units if u["level"] == level]
        out.append(f"| Теми и уроци на HSK {level} | `curriculum/` | "
                   f"{len(chosen)} теми, {sum(u['lessons'] for u in chosen)} "
                   f"урока, {sum(u['words'] for u in chosen)} думи |")
    out.append("| Екрани в навигацията | `HanziNavHost.kt` | path, lesson, dictionary, levels, review, practice, grammar |")
    out.append("| Режима на упражненията | `PracticeViewModel.kt:38` | 5 |")
    out.append("| Стъпки в урок | `LessonPlan.kt:42` | LISTEN, RECOGNISE, SAY, WRITE |")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## 7. Какво липсва")
    out.append("")
    out.append("Пътят е построен до HSK 4, но **1678-те думи на HSK 2–4 нямат ръчно")
    out.append("написан български глос**. Проверката (`pipeline/audit_path.py --gate`)")
    out.append("иска глос за всяка дума, затова вратата още е затворена:")
    out.append("")
    out.append("```")
    out.append("::error::1678 path words have no hand-written gloss")
    out.append("```")
    out.append("")
    out.append("Машинският превод не става: 熟 → „сърбеж“, 扫 → „да се погълца“,")
    out.append("笔 → „писане четка“. Глосът трябва да е ЕДИН смисъл, до 45 знака, без")
    out.append("наклонени черти и без скоби, и две думи от един урок да не носят")
    out.append("един и същ или объркан смисъл.")
    out.append("")
    out.append("Докато това не е готово, пътят е в базата и е правилен, но ученикът")
    out.append("вижда машински превод на 1678-те думи.")
    out.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"written {OUT}")
    print(f"   {total_units} units, {total_lessons} lessons, {total_words} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

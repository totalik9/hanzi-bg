#!/usr/bin/env python
"""Rewrite the glosses of the pairs the path audit found.

The pairs were found by `python pipeline/audit_path.py`: two words of
the same lesson carried the SAME meaning, so the RECOGNISE card asked
a question with two right answers. The 2026-11-23 session hit one of
them for real -- the review card of 二 offered "два" and "две" and
marked the everyday word wrong.

Each new gloss says what the word means ON ITS OWN, so the learner can
tell the pair apart. The rules of the file are in curriculum/README.md:
short, no brackets, no "/".
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "curriculum", "20_glosses_hsk1.json")

NEW = {
    # -- numbers: two words, one meaning ------------------------------
    "半": "половинна част",
    "一半": "половината от нещо",
    "一点儿": "малко количество",
    "有点儿": "донейде; леко",
    "有些": "някои; не всички",
    "有的": "има такива",
    # the numeral two, and the "two of them" two
    "二": "два",
    "两": "два, когато броим предмети",
    # the classifiers: what they count, not what they are
    "个": "измерителна дума, обща",
    "件": "измерителна дума за вещи",
    "第": "номер на поредка",
    "的": "структурна частица",
    "们": "частица за множествено число",

    # -- people: the three "they" -------------------------------------
    "他们": "те — хора",
    "她们": "те — жени",
    "它们": "те — неща",
    "孩子": "дете",
    "小朋友": "малко дете; приятелче",

    # -- time ----------------------------------------------------------
    "星期天": "неделя",
    "星期日": "неделя, официалното име",
    "时候": "време, когато",
    "时间": "време, час",

    # -- school --------------------------------------------------------
    "学习": "да уча",
    "学": "учене; наука",
    "中文": "китайски език",
    "汉语": "китайски език, ханският",

    # -- travel and places ---------------------------------------------
    "看见": "виждам",
    "见": "срещам; виждам",
    "商店": "магазин",
    "店": "магазин, дюкян",
    "这里": "тук, това място",
    "这儿": "тук, наоколо",
    "这边": "тук, от тази страна",
    "那里": "там, това място",
    "那儿": "там, наоколо",

    # -- describing ----------------------------------------------------
    "很": "много, степен",
    "多": "много, количество",

    # -- questions ------------------------------------------------------
    "谁": "кой — лице",
    "哪个": "кой — предмет",
    "哪儿": "къде — място",
    "哪里": "къде — в коя страна",
}


def main():
    data = json.load(open(PATH, encoding="utf-8"))
    changed = []
    for hanzi, gloss in NEW.items():
        if hanzi not in data:
            print("  MISSING from the gloss patch:", hanzi)
            continue
        if data[hanzi] != gloss:
            changed.append((hanzi, data[hanzi], gloss))
            data[hanzi] = gloss
    for hanzi, old, new in changed:
        print("  %-6s %-28s -> %s" % (hanzi, old, new))
    print("changed: %d glosses" % len(changed))

    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("written", PATH)


if __name__ == "__main__":
    main()

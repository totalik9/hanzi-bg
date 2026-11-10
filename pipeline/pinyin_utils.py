"""Shared helpers for the hanzi-bg pipeline: pinyin conversion and file paths.

Implements numeric-tone pinyin ("ni3 hao3") -> tone-marked pinyin ("nǐ hǎo")
using the standard Mandarin tone-placement rules, plus the reverse conversion
(tone-marked -> numeric) used when joining dictionary data with HSK lists.

Tone placement priority (per syllable):
    a  >  o  >  e  >  iu (mark the u)  >  ui (mark the i)  >  i  >  ü
A neutral tone (tone 5) is written unmarked.

CC-CEDICT spells the umlaut as "u:" and sometimes "v"; both are normalised to "ü".
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")

# tone mark tables, index = tone number (0 = unmarked/neutral, 1..4, 5 = neutral)
_MARKS = {
    "a": "aāáǎà",
    "o": "oōóǒò",
    "e": "eēéěè",
    "i": "iīíǐì",
    "u": "uūúǔù",
    "ü": "üǖǘǚǜ",
}
# syllabic nasals carry their tone on a combining macron
_MACRON = {1: "̄", 2: "́", 3: "̌", 4: "̀"}
# Reverse map for *marked* characters only. An unmarked vowel is a neutral tone,
# so index 0 of each table is deliberately skipped.
_REVERSE = {}
for _vowel, _marks in _MARKS.items():
    for _i, _ch in enumerate(_marks):
        if _i == 0:
            continue
        _REVERSE.setdefault(_ch, (_vowel, _i))


def _normalise_vowels(syl: str) -> str:
    """Turn CC-CEDICT's "u:" / "v" spelling of ü into the real character."""
    return syl.replace("u:", "ü").replace("v", "ü")


def syllable_to_tones(syl: str) -> str:
    """Convert one numeric-tone syllable to its tone-marked form.

    >>> syllable_to_tones("ni3")
    'nǐ'
    >>> syllable_to_tones("lu:4")
    'lǜ'
    >>> syllable_to_tones("ma5")
    'ma'
    """
    if not syl:
        return syl
    syl = _normalise_vowels(syl)
    tone = 0
    for ch in syl:
        if ch.isdigit():
            tone = int(ch)
            break
    syl = "".join(c for c in syl if not c.isdigit())
    if tone in (0, 5) or not syl:
        return syl

    target = None
    idx = -1
    if syl in ("m", "n", "ng"):
        # syllabic nasal (e.g. 呣 "m"): the tone is shown with a combining macron
        return syl + _MACRON[tone] if tone in (1, 2, 3, 4) else syl
    if "a" in syl:
        target, idx = "a", syl.index("a")
    elif "o" in syl:
        target, idx = "o", syl.index("o")
    elif "e" in syl:
        target, idx = "e", syl.index("e")
    elif "iu" in syl:
        target, idx = "u", syl.index("iu") + 1   # mark the u of "iu"
    elif "ui" in syl:
        target, idx = "i", syl.index("ui") + 1   # mark the i of "ui"
    elif "i" in syl:
        target, idx = "i", syl.index("i")
    elif "ü" in syl:
        target, idx = "ü", syl.index("ü")
    elif "u" in syl:
        target, idx = "u", syl.index("u")
    else:
        return syl

    if idx < 0:
        return syl

    marked = _MARKS[target][tone]
    return syl[:idx] + marked + syl[idx + 1:]


def pinyin_number_to_tones(text: str) -> str:
    """Convert a whole numeric-tone pinyin phrase to tone-marked form.

    >>> pinyin_number_to_tones("ni3 hao3")
    'nǐ hǎo'
    """
    if not text:
        return ""
    out = []
    for token in text.split():
        out.append(syllable_to_tones(token))
    return " ".join(out)


def tone_marked_to_number(text: str) -> str:
    """Convert tone-marked pinyin to numeric form ("nǐ hǎo" -> "ni3 hao3").

    Unmarked syllables get a trailing 5 (neutral tone), which is the convention
    used by CC-CEDICT and by pinyin-data. The umlaut is written as "ü"; use
    canonical_pinyin_number() when joining against CC-CEDICT strings, which
    spell the same vowel as "u:".
    """
    if not text:
        return ""
    out = []
    for token in text.split():
        syl = _normalise_vowels(token)
        tone = 5
        for i, ch in enumerate(syl):
            if ch in _REVERSE:
                vowel, t = _REVERSE[ch]
                syl = syl[:i] + vowel + syl[i + 1:]
                tone = t
                break
        else:
            # syllabic nasal written with a combining macron (e.g. "m̄")
            for tone_num, macron in _MACRON.items():
                if syl.endswith(macron):
                    syl = syl[: -len(macron)]
                    tone = tone_num
                    break
        out.append(f"{syl}{tone}")
    return " ".join(out)


def canonical_pinyin_number(text: str) -> str:
    """Normalise numeric pinyin so different sources can be joined.

    CC-CEDICT spells the umlaut as "u:", some sources use "v", others "ü".
    All three collapse to "ü" here, and whitespace is squeezed to single spaces.

    >>> canonical_pinyin_number("lu:4 lv:4")
    'lü4 lü4'
    """
    if not text:
        return ""
    return " ".join(_normalise_vowels(tok) for tok in text.split())


# Pinyin syllable initials, longest first so that "zh"/"ch"/"sh" win over "z"/"c"/"s".
# "y" and "w" are included because they behave as initials in Mandarin
# ("yi" = y+i, "wo" = w+o, "yuan" = y+uan).
_INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g",
             "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w")

# All legal Mandarin syllable finals. A syllable is initial + final, or just a
# final when it has no initial. Matching against this table (longest first)
# is what makes the split unambiguous: "xièxie" -> "xi"+"e"+"xie" is rejected
# because "ie" is a legal final, so the split is "xiè"+"xie".
# "ue" is the "üe" final as written after j/q/x/y ("jue" = ju + ue).
_FINALS = (
    "iang", "iong", "uang", "ueng", "uian",
    "ai", "an", "ang", "ao", "ei", "en", "eng", "er", "ia", "ian", "iang",
    "iao", "ie", "in", "ing", "iu", "ong", "on", "ou", "ua", "uai", "uan",
    "uang", "ui", "un", "uo", "ue", "üan", "üe", "ün",
    "a", "e", "i", "o", "u", "ü", "m", "n", "ng",
)
_FINALS_BY_LEN = sorted(set(_FINALS), key=len, reverse=True)

# cache for the syllable inventory loaded from data/raw/pinyin_syllables.json
_INVENTORY: set[str] | None = None

# used only if the inventory file is missing; keeps the pipeline runnable
_FALLBACK_SYLLABLES = {
    "a", "o", "e", "ai", "ei", "ao", "ou", "an", "en", "ang", "eng", "er",
    "i", "ia", "ie", "iao", "iu", "ian", "in", "iang", "ing", "iong",
    "u", "ua", "uo", "uai", "ui", "uan", "un", "uang", "ueng",
    "ü", "üe", "üan", "ün", "ue",
    "yi", "ya", "ye", "yao", "you", "yan", "yin", "yang", "ying", "yong",
    "yu", "yue", "yuan", "yun", "wu", "wo", "wai", "wei", "wan", "wen",
    "wang", "weng",
}

# tone-marked vowels, mapped to their plain form for final matching
_MARK_TO_PLAIN = {}
for _vowel, _marks in _MARKS.items():
    for _ch in _marks:
        _MARK_TO_PLAIN[_ch] = _vowel
_MARK_TO_PLAIN["ü"] = "ü"


def _plain(text: str) -> str:
    """Strip tone marks so a syllable can be matched against the final table.

    The result is lower-cased because the HSK CSVs capitalise surnames
    ("Māma", "Zhōng") while the initial/final tables are lower-case.
    """
    return "".join(_MARK_TO_PLAIN.get(c, c) for c in text).lower()


def strip_tones(text: str) -> str:
    """Remove tone marks and normalise case, keeping only the pinyin letters.

    Used to compare readings that differ only in tone sandhi or in how the
    erhua suffix is written ("nǎr" vs "nǎ ér").
    """
    return _plain(text).replace("'", "").replace("’", "")


def split_pinyin_by_chars(
    text: str,
    chars: str,
    char_readings: dict[str, list[str]],
) -> list[str] | None:
    """Split run-together pinyin into syllables, constrained by the characters.

    Run-together pinyin is ambiguous on its own ("sāngè" could be "sān gè" or
    "sāng è"), but the reading of each Chinese character is known, so the
    syllable boundaries can be pinned down exactly: syllable *i* must be one
    of the readings of character *i*.

    `char_readings` maps a character to its list of possible readings, each
    given as plain (tone-stripped) pinyin. Returns the syllable list, or None
    when no consistent split exists.

    >>> readings = {"三": ["san"], "个": ["ge"]}
    >>> split_pinyin_by_chars("sāngè", "三个", readings)
    ['sān', 'gè']
    """
    text = text.strip()
    if not text or " " in text:
        return None
    if len(chars) != len(text):
        # the pinyin length must match the character count for this to apply
        return None

    plain = _plain(text)
    inventory = _load_syllable_inventory()
    n = len(plain)

    # allowed plain syllable forms for each character position
    allowed: list[set[str]] = []
    for ch in chars:
        forms = {strip_tones(r) for r in char_readings.get(ch, [])}
        allowed.append(forms)

    # best[i][k] = syllable lengths that parse plain[i:] into k syllables
    best: list[dict[int, list[int]]] = [dict() for _ in range(n + 1)]
    best[n][0] = []
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n + 1):
            piece = plain[i:j]
            if piece not in inventory:
                continue
            for k, tail in best[j].items():
                cand = [j - i] + tail
                cur = best[i].get(k + 1)
                if cur is None or _better_split(cand, cur):
                    best[i][k + 1] = cand

    # walk forward, choosing at each step a piece that is a legal reading of
    # the character at that position
    result: list[str] = []
    pos = 0
    char_pos = 0
    while pos < n:
        placed = False
        for length in range(1, n - pos + 1):
            piece = plain[pos:pos + length]
            if char_pos >= len(allowed):
                break
            if piece in allowed[char_pos]:
                result.append(text[pos:pos + length])
                pos += length
                char_pos += 1
                placed = True
                break
        if not placed:
            return None
    return result if char_pos == len(allowed) else None


def _load_syllable_inventory() -> set[str]:
    """Load the set of valid Mandarin syllables.

    The inventory is built from the real pinyin-data files by
    _build_syllable_inventory.py and cached in data/raw/pinyin_syllables.json.
    If that file is missing the module falls back to a small built-in set so
    the pipeline still runs (with lower-quality splits).
    """
    global _INVENTORY
    if _INVENTORY is not None:
        return _INVENTORY
    path = os.path.join(RAW, "pinyin_syllables.json")
    inv: set[str] = set()
    try:
        with open(path, encoding="utf-8") as fh:
            inv = {k.lower() for k in json.load(fh).keys()}
    except Exception:
        inv = set(_FALLBACK_SYLLABLES)
    _INVENTORY = inv
    return inv


def split_pinyin_syllables(text: str, n_syllables: int | None = None) -> list[str]:
    """Split a run-together pinyin string into its syllables.

    The HSK CSV files write multi-character words without spaces ("bàba",
    "dàxué"), so the syllables have to be recovered before the numeric form
    can be derived ("ba4 ba5").

    The split is found with dynamic programming over the valid Mandarin
    syllable inventory, so it is exact rather than greedy: greedy longest
    matching mis-splits "yīnián" ("yi"+"nian") into "yin"+"ian".

    Run-together pinyin can be genuinely ambiguous ("sān gè" also parses as
    "sāng è"), so callers that know the character count of the word should
    pass `n_syllables`; the parser then returns the split with exactly that
    many syllables.

    >>> split_pinyin_syllables("bàba")
    ['bà', 'ba']
    >>> split_pinyin_syllables("yīnián")
    ['yī', 'nián']
    >>> split_pinyin_syllables("sāngè", n_syllables=2)
    ['sān', 'gè']
    >>> split_pinyin_syllables("ni3 hao3")
    ['ni3', 'hao3']
    """
    text = text.strip()
    if not text:
        return []
    if " " in text:
        return text.split()

    plain = _plain(text)
    inventory = _load_syllable_inventory()
    n = len(plain)

    # best[i][k] = list of syllable lengths that parse plain[i:] into k syllables
    # (k is the number of syllables still to place, capped at n_syllables)
    # The table is built backwards; each entry stores the best parse found.
    limit = n_syllables if n_syllables else n
    best: list[dict[int, list[int]]] = [dict() for _ in range(n + 1)]
    best[n][0] = []
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n + 1):
            if plain[i:j] not in inventory:
                continue
            for k, tail in best[j].items():
                if k + 1 > limit:
                    continue
                cand = [j - i] + tail
                cur = best[i].get(k + 1)
                if cur is None or _better_split(cand, cur):
                    best[i][k + 1] = cand

    # choose the parse to use
    chosen = None
    if n_syllables:
        chosen = best[0].get(n_syllables)
    if chosen is None:
        # prefer the fewest syllables, then the longest-first parse
        candidates = sorted(best[0].items(), key=lambda kv: (kv[0], [-x for x in kv[1]]))
        if candidates:
            chosen = candidates[0][1]

    if chosen is None:
        # no exact parse: fall back to the greedy longest-initial/final split
        return _greedy_split(text, plain)

    out: list[str] = []
    pos = 0
    for length in chosen:
        out.append(text[pos:pos + length])
        pos += length
    return out


def _better_split(candidate: list[int], current: list[int]) -> bool:
    """True if `candidate` is a better syllable split than `current`.

    Both parses cover the same text, so they have the same syllable count;
    the tie-break prefers longer syllables early, which matches how Mandarin
    syllables are actually built.
    """
    return candidate > current


def _greedy_split(text: str, plain: str) -> list[str]:
    """Fallback split used when no exact syllable parse exists."""
    out: list[str] = []
    i = 0
    n = len(plain)
    while i < n:
        chosen = ""
        for init in ("zh", "ch", "sh"):
            if plain.startswith(init, i):
                chosen = init
                break
        if not chosen:
            for init in _INITIALS:
                if plain.startswith(init, i):
                    chosen = init
                    break
        if chosen:
            after = i + len(chosen)
            for fin in _FINALS_BY_LEN:
                if plain.startswith(fin, after):
                    out.append(text[i:after + len(fin)])
                    i = after + len(fin)
                    break
            else:
                out.append(text[i])
                i += 1
        else:
            for fin in _FINALS_BY_LEN:
                if plain.startswith(fin, i):
                    out.append(text[i:i + len(fin)])
                    i += len(fin)
                    break
            else:
                out.append(text[i])
                i += 1
    return out


def is_hanzi(ch: str) -> bool:
    """True if the character is a CJK ideograph."""
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2A6DF
    )


def has_hanzi(text: str) -> bool:
    return any(is_hanzi(c) for c in text)

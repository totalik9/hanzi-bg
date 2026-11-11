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
import re

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
    """Turn CC-CEDICT's "u:" / "v" spelling of ü into the real character.

    CC-CEDICT writes "lu:4"; other sources write "lv:4". The colon has to
    go with the letter, otherwise "lv:4" becomes "lü:4" -- a syllable
    that does not exist.

    >>> _normalise_vowels("lu:4")
    'lü4'
    >>> _normalise_vowels("lv:4")
    'lü4'
    >>> _normalise_vowels("nv:3")
    'nü3'
    """
    return syl.replace("u:", "ü").replace("v:", "ü").replace("v", "ü")


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
        # ASCII digits only: str.isdigit() is also true for superscripts
        # ("²"), which would raise on int().
        if ch in "0123456789":
            tone = int(ch)
            break
    syl = "".join(c for c in syl if c not in "0123456789")
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

# The inventory of legal Mandarin syllables, used to segment run-together
# pinyin. It is derived from the real pinyin-data files by
# _build_syllable_inventory.py and cached in data/raw/pinyin_syllables.json.
#
# The list below is the same inventory, written out, so the module still
# segments correctly on a fresh clone that has not downloaded anything
# yet. An earlier, much shorter list held only the syllables without a
# consonant initial, and a missing syllable is not a harmless gap: the
# segmenter then splits a word at the wrong place -- 去年 came out as
# "qu nian" instead of "qu nian" with the right boundary, because "qu"
# was missing and the parser fell back to "qun"+"ian".
#
# The order is alphabetical; the syllabic nasals and the rare ê vowel are
# deliberately left out -- they are not needed to segment a word and they
# would only add noise.
_FALLBACK_SYLLABLES = set("""
a ai an ang ao ba bai ban bang bao bei ben beng bi bian biang biao bie bin
bing bo bong bu ca cai can cang cao ce cei cen ceng cha chai chan chang chao
che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo ci
cong cou cu cuan cui cun cuo da dai dan dang dao de dei den deng di dia dian
diao die din ding diu dong dou du duan dui dun duo e ei en eng er fa fan
fang fei fen feng fiao fo fou fu ga gai gan gang gao ge gei gen geng gong
gou gu gua guai guan guang gui gun guo ha hai han hang hao he hei hen heng
hm hng hong hou hu hua huai huan huang hui hun huo ji jia jian jiang jiao
jie jin jing jiong jiu ju juan jue jun ka kai kan kang kao ke kei ken keng
kong kou ku kua kuai kuan kuang kui kun kuo la lai lan lang lao le lei len
leng li lia lian liang liao lie lin ling liu lo long lou lu luan lun luo lü
lüe ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou
mu n na nai nan nang nao ne nei nen neng ng ni nia nian niang niao nie nin
ning niu nong nou nu nuan nun nuo nü nüe o ou pa pai pan pang pao pei pen
peng pi pian piao pie pin ping po pou pu qi qia qian qiang qiao qie qin qing
qiong qiu qu quan que qun ran rang rao re ren reng ri rong rou ru rua ruan
rui run ruo sa sai san sang sao se sen seng sha shai shan shang shao she shei
shen sheng shi shou shu shua shuai shuan shuang shui shun shuo si song sou su
suan sui sun suo ta tai tan tang tao te tei teng ti tian tiao tie ting tong
tou tu tuan tui tun tunwa tuo wa wai wan wang wei wen weng wo wong wu xi
xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun ya yan yang yao
ye yi yin ying yo yong you yu yuan yue yun za zai zan zang zao ze zei zen
zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua
zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo
""".split())

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


def _has_initial(syllable: str) -> bool:
    """True when a plain syllable begins with a consonant initial.

    A Mandarin syllable is normally initial + final. The bare finals
    ("a", "an", "e", "ang", ...) and the syllabic nasals ("m", "n", "ng")
    have no initial, and they are the syllables that make a run-together
    pinyin string ambiguous: "sange" parses as "san"+"ge" or "sang"+"e",
    and only the first reading is a normal syllable.

    >>> _has_initial("san")
    True
    >>> _has_initial("an")
    False
    >>> _has_initial("ng")
    False
    """
    if syllable in _BARE_SYLLABLES:
        return False
    for initial in _INITIALS:
        if syllable.startswith(initial):
            return True
    return False


# Syllables that are a bare final or a syllabic nasal: no initial.
_BARE_SYLLABLES = {
    "a", "o", "e", "ê", "ai", "ei", "ao", "ou", "an", "en",
    "ang", "eng", "er", "m", "n", "ng",
}


def _parse_score(lengths: list[int], plain: str) -> tuple[int, int]:
    """Rank a syllable parse: more initials first, then a shorter first syllable.

    The score is the number of syllables that carry an initial consonant
    (higher is better) and, as the tie-break, the length of the first
    syllable (shorter is better). Both are needed: "sange" has two
    two-syllable readings -- "san"+"ge" (two initials) and "sang"+"e"
    (one initial) -- and only the first is right.

    >>> _parse_score([3, 2], "sange")
    (2, -3)
    >>> _parse_score([4, 1], "sange")
    (1, -4)
    """
    syllables: list[str] = []
    pos = 0
    for length in lengths:
        syllables.append(plain[pos:pos + length])
        pos += length
    initials = sum(1 for s in syllables if _has_initial(s))
    first = lengths[0] if lengths else 0
    return (initials, -first)


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

    >>> readings = {"三": ["sān"], "个": ["gè"]}
    >>> split_pinyin_by_chars("sāngè", "三个", readings)
    ['sān', 'gè']
    >>> split_pinyin_by_chars("sāngè", "三", readings) is None
    True
    """
    text = text.strip()
    if not text or " " in text:
        return None

    plain = _plain(text)
    n = len(plain)

    # allowed plain syllable forms for each character position
    allowed: list[set[str]] = []
    for ch in chars:
        forms = {strip_tones(r) for r in char_readings.get(ch, [])}
        allowed.append(forms)
    if not all(allowed):
        return None

    # Walk forward, choosing at each step a piece that is a legal reading of
    # the character at that position. The search backtracks: the longest
    # piece is tried first, but a piece that leaves the rest of the word
    # unparseable is abandoned in favour of a shorter one.
    def place(pos: int, char_pos: int) -> list[str] | None:
        if char_pos == len(allowed):
            return [] if pos == n else None
        if pos >= n:
            return None
        for length in range(min(n - pos, 12), 0, -1):
            piece = plain[pos:pos + length]
            if piece not in allowed[char_pos]:
                continue
            tail = place(pos + length, char_pos + 1)
            if tail is not None:
                return [text[pos:pos + length]] + tail
        return None

    return place(0, 0)


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
                if cur is None or _better_split(cand, cur, plain[i:]):
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


def _better_split(candidate: list[int], current: list[int], plain: str) -> bool:
    """True if `candidate` is a better syllable split than `current`.

    Both parses cover the same text, so they have the same syllable count.
    The tie-break prefers the parse whose syllables carry an initial
    consonant, because a bare final ("an", "e", "ang") only turns up in
    run-together pinyin as the tail of an ambiguous split: "sange" is
    "san"+"ge", not "sang"+"e". The shorter first syllable breaks the
    remaining ties.

    >>> _better_split([3, 2], [4, 1], "sange")
    True
    >>> _better_split([4, 1], [3, 2], "sange")
    False
    """
    return _parse_score(candidate, plain) > _parse_score(current, plain)


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


# --------------------------------------------------------------------------
# Sentence pinyin
# --------------------------------------------------------------------------

# A syllable in Tatoeba's numeric transcription is letters followed by a
# tone digit. The transcription writes a whole sentence as whitespace-
# separated WORDS, and each word may pack several syllables together
# ("mei2you3ren2" = mei2 you3 ren2).
_NUMERIC_SYLLABLE = re.compile(r"([a-zA-ZüÜ]+)([1-5])")

# Punctuation is written attached to the word it follows ("Cuo4."), and the
# trailing dot is not part of the syllable.
_EDGE_PUNCT = ".,!?;:()[]\"«»…、，。！？；：“”‘’"


def _strip_edge_punct(token: str) -> str:
    """Remove punctuation glued to the front or back of a token."""
    return token.strip(_EDGE_PUNCT)


def split_numeric_syllables(text: str) -> list[str]:
    """Split a numeric-tone pinyin run into individual syllables.

    Tatoeba writes a sentence as whitespace-separated words, and a word can
    pack several syllables without a space ("mei2you3ren2"). Every syllable
    carries exactly one tone digit, so the digits give the boundaries for
    free -- no dictionary matching is needed.

    >>> split_numeric_syllables("mei2you3ren2")
    ['mei2', 'you3', 'ren2']
    >>> split_numeric_syllables("ni3 hao3")
    ['ni3', 'hao3']

    Punctuation glued to a word is dropped: "Cuo4." is one syllable, "cuo4".
    Tokens that are not a syllable at all are returned unchanged so the
    caller can decide what to do with them.
    """
    out: list[str] = []
    for token in text.split():
        token = _strip_edge_punct(token)
        if not token:
            continue
        parts = _NUMERIC_SYLLABLE.findall(token)
        if parts and "".join(a + b for a, b in parts) == token:
            out.extend(a + b for a, b in parts)
        else:
            out.append(token)
    return out


def split_transcription_syllables(text: str) -> list[str]:
    """Split a Tatoeba transcription into syllables, numeric form.

    Handles both transcription styles found in the corpus: numeric
    ("ni3 hao3") and tone-marked ("nǐ hǎo"). Tone-marked words that pack
    several syllables together are split with the syllable inventory.

    Punctuation tokens are dropped -- the pinyin of a sentence is the
    pinyin of its characters, not of its commas.
    """
    out: list[str] = []
    for token in text.split():
        token = _strip_edge_punct(token)
        if not token:
            continue
        if not token[:1].isalpha():
            # punctuation and other non-syllable tokens
            continue
        if any(c in "0123456789" for c in token):
            out.extend(split_numeric_syllables(token))
        else:
            # tone-marked: split with the syllable inventory, then convert
            syls = split_pinyin_syllables(token)
            out.extend(tone_marked_to_number(s) for s in syls)
    return out


def sentence_pinyin(
    zh: str,
    transcription: str | None,
    char_readings: dict[str, list[str]],
) -> str:
    """Build the tone-marked pinyin for a Chinese sentence.

    Prefers Tatoeba's own transcription, which is written by humans and
    therefore gets polyphonic characters right in context. The fallback
    reads each character individually, which is wrong for polyphonic
    characters but never worse than having no pinyin at all.

    The two sources are reconciled by SYLLABLE COUNT: a transcription whose
    syllable count does not match the number of characters in the sentence
    cannot be trusted, so it is discarded rather than silently mismatched.

    Returns a space-separated tone-marked pinyin string, or "" when neither
    source can produce one.
    """
    chars = [c for c in zh if is_hanzi(c)]

    if transcription:
        syls = split_transcription_syllables(transcription)
        if syls and len(syls) == len(chars):
            return " ".join(syllable_to_tones(s) for s in syls)

    # Fallback: read each character on its own.
    parts = []
    for ch in chars:
        readings = char_readings.get(ch)
        if readings:
            parts.append(readings[0])
    return " ".join(parts)

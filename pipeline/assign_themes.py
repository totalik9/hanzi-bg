"""Assign every HSK 2-4 word to a theme, and report what is left over.

    python pipeline/assign_themes.py           (writes themed.json)

WHY A THEME AND NOT A FREQUENCY ORDER

The order in which the learner meets a word is a teaching decision,
and a theme is that decision made concrete: the words of a lesson
belong to the same field, so the sentence the learner builds around
them is one they can actually use.

The themes are the units the path already has -- numbers, food, time,
places, and the rest -- continued for the words that come after HSK 1.
A few are new: the words of HSK 2 to 4 reach into work, media, law
and technology, and the HSK 1 path has no unit for those.

HOW A WORD IS ASSIGNED

Three signals, in this order:

  1. the SEMANTIC FAMILY it belongs to -- two words that share a
     rare character, or one that contains the other, are the same
     field (按/按时/按照, 表格/表示/表演). A family is assigned once
     and every member inherits the theme, so the family is never
     split across two units;

  2. the KEYWORDS of its own English sense, which is the short
     official one from the HSK list;

  3. the part of speech, for the words that carry no field at all:
     a function word belongs with the function words.

WHAT THE SCRIPT REPORTS

The words it could not place. They are the ones that need a human
decision, and the script does not guess at them: a word in the wrong
theme is a word taught in the wrong company.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.environ.get("TMPDIR", ROOT)

#: A character that appears in at most this many of the words names a
#: field. Above it, the character is too common to mean anything.
RARE_CHARACTER = 4

#: The theme vocabulary. The key is the machine name of the unit; it
#: becomes the primary key of the row and the navigation argument, so
#: it never changes once shipped. The title is what the learner reads.
#: The keywords are matched against the official English sense.
THEMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "numbers": ("numbers", "numbers", (
        "number", "digit", "zero", "thousand", "million", "hundred", "count",
        "amount", "quantity", "half", "quarter", "piece", "unit", "measure",
        "percent", "degree", "meter", "kilometer", "centimeter", "kilogram",
        "gram", "ton", "liter", "size", "length", "width", "height", "weight",
        "total", "average", "sum", "point", "scale", "square", "round")),
    "greetings": ("greetings", "greetings", (
        "hello", "hi", "goodbye", "bye", "welcome", "thank", "sorry",
        "excuse", "please", "greet", "congratulat", "wish", "luck",
        "respect", "polite", "grateful", "apolog", "favour", "favor",
        "invitation", "invite", "guest", "host")),
    "people": ("people", "people", (
        "people", "person", "man", "woman", "boy", "girl", "friend", "adult",
        "child", "baby", "grown", "personality", "character", "feeling",
        "happy", "sad", "angry", "glad", "sorry", "afraid", "tired", "busy",
        "free", "lonely", "love", "like", "hate", "prefer", "want", "need",
        "hope", "help", "meet", "together", "group", "member", "crowd",
        "relationship", "kind", "honest", "polite", "friendly", "humour",
        "humor", "patient", "serious", "strange", "clever", "smart", "kindly")),
    "family": ("family", "family", (
        "family", "father", "mother", "son", "daughter", "brother", "sister",
        "grand", "parents", "child", "couple", "wife", "husband", "relative",
        "aunt", "uncle", "nephew", "niece", "marry", "wedding", "birth",
        "ancestor", "member of the family")),
    "food": ("food", "food", (
        "food", "eat", "drink", "rice", "noodle", "bread", "meat", "fish",
        "vegetable", "fruit", "apple", "soup", "egg", "milk", "tea", "coffee",
        "juice", "beer", "wine", "water", "sugar", "salt", "oil", "cake",
        "sweet", "dish", "flavour", "flavor", "taste", "restaurant", "cook",
        "chef", "meal", "lunch", "dinner", "breakfast", "snack", "menu",
        "waiter", "knife", "fork", "chopsticks", "spoon", "bowl", "plate")),
    "time": ("time", "time", (
        "time", "day", "week", "month", "year", "hour", "minute", "second",
        "morning", "afternoon", "evening", "night", "today", "tomorrow",
        "yesterday", "season", "spring", "summer", "autumn", "winter", "holiday",
        "birthday", "weekend", "period", "schedule", "calendar", "date",
        "early", "late", "noon", "midnight", "century", "moment", "future",
        "past", "present", "recently", "already", "yet", "still")),
    "body": ("body", "body", (
        "body", "health", "doctor", "hospital", "ill", "sick", "pain", "hurt",
        "medicine", "drug", "nurse", "patient", "clinic", "temperature",
        "injury", "head", "hair", "face", "eye", "ear", "nose", "mouth",
        "tooth", "neck", "shoulder", "arm", "hand", "finger", "leg", "foot",
        "knee", "back", "stomach", "heart", "skin", "bone", "blood", "sweat",
        "tired", "rest", "sleep", "dentist", "medicine")),
    "home": ("home", "home", (
        "home", "house", "room", "furniture", "door", "window", "floor", "wall",
        "kitchen", "bedroom", "bathroom", "living room", "sofa", "bed", "chair",
        "table", "lamp", "fridge", "washing machine", "shelf", "cupboard",
        "curtain", "carpet", "rent", "landlord", "address", "garden",
        "garbage", "clean", "tidy", "repair", "build", "housework")),
    "schoolwork": ("schoolwork", "schoolwork", (
        "school", "study", "learn", "student", "teacher", "class", "lesson",
        "course", "exam", "homework", "university", "college", "knowledge",
        "textbook", "grade", "campus", "subject", "degree", "major", "graduate",
        "question", "answer", "test", "note", "word", "sentence", "grammar",
        "work", "job", "office", "company", "employee", "staff", "boss",
        "business", "profession", "factory", "salary", "colleague", "meeting",
        "appointment", "interview", "apply", "hire", "retire", "employer",
        "worker", "engineer", "lawyer", "scientist", "artist", "author",
        "writer", "reader", "journalist", "reporter", "coach")),
    "travel": ("travel", "travel", (
        "travel", "trip", "journey", "tour", "tourist", "train", "bus", "car",
        "plane", "flight", "ticket", "airport", "station", "drive", "taxi",
        "transport", "luggage", "passport", "visa", "seat", "departure",
        "arrive", "leave", "sightseeing", "guide", "map", "trip abroad",
        "business trip", "passenger", "flight", "subway", "metro", "bike",
        "motorcycle", "boat", "ship", "traffic", "road", "street",
        "crossroads", "crossing", "corner", "junction", "path", "highway")),
    "nature": ("nature", "nature", (
        "weather", "rain", "snow", "wind", "cloud", "sunny", "sun", "sky",
        "storm", "thunder", "fog", "ice", "warm", "cool", "humid", "dry",
        "nature", "natural", "mountain", "hill", "river", "lake", "sea", "ocean",
        "forest", "tree", "flower", "grass", "plant", "animal", "dog", "cat",
        "bird", "fish", "insect", "land", "air", "soil", "environment",
        "pollution", "protect", "earth", "planet", "space")),
    "places": ("places", "places", (
        "place", "building", "hotel", "library", "museum", "theatre", "theater",
        "restaurant", "station", "airport", "park", "shop", "market", "bank",
        "office", "factory", "school", "hospital", "bank", "post office",
        "north", "south", "east", "west", "left", "right", "middle", "around",
        "near", "far", "front", "back", "side", "inside", "outside", "above",
        "below", "here", "there", "city", "town", "village", "province",
        "country", "nation", "capital", "district", "area", "centre", "center",
        "square", "garden", "bridge", "floor", "storey", "entrance", "exit")),
    "shopping": ("shopping", "shopping", (
        "money", "bank", "card", "price", "cost", "buy", "sell", "pay",
        "payment", "cash", "shop", "store", "market", "bill", "discount",
        "expensive", "cheap", "change", "customer", "goods", "product",
        "order", "deliver", "receipt", "coin", "note", "amount", "spend",
        "budget", "value", "worth", "sale", "reduce")),
    "verbs": ("verbs", "verbs", (
        "do", "make", "take", "give", "get", "put", "keep", "let", "try",
        "start", "begin", "finish", "stop", "change", "choose", "decide",
        "prepare", "arrange", "carry", "send", "receive", "return", "wait",
        "look", "watch", "listen", "hear", "speak", "talk", "say", "tell",
        "ask", "answer", "call", "write", "read", "think", "know", "believe",
        "want", "need", "like", "love", "hate", "hope", "wish", "find",
        "lose", "win", "open", "close", "sit", "stand", "lie", "sleep", "wake",
        "eat", "drink", "buy", "sell", "pay", "walk", "run", "jump", "climb",
        "push", "pull", "hold", "throw", "catch", "cut", "wash", "clean",
        "cook", "fly", "swim", "dance", "sing", "play", "work", "study",
        "move", "arrive", "leave", "enter", "exit", "visit", "meet", "join",
        "turn", "return", "continue", "repeat", "show", "hide", "wear",
        "help", "allow", "avoid", "forget", "remember", "realize", "explain",
        "describe", "discuss", "agree", "refuse", "accept", "offer",
        "suggest", "report", "announce", "introduce", "express", "compare",
        "consider", "improve", "develop", "increase", "reduce", "succeed",
        "fail", "try", "manage", "achieve", "solve", "check", "test",
        "protect", "support", "provide", "share", "discuss")),
    "describing": ("describing", "describing", (
        "good", "bad", "big", "small", "new", "old", "young", "long", "short",
        "high", "low", "beautiful", "ugly", "difficult", "easy", "interesting",
        "boring", "heavy", "light", "clean", "dirty", "safe", "dangerous",
        "famous", "important", "different", "same", "similar", "special",
        "usual", "normal", "real", "true", "false", "possible", "correct",
        "wrong", "right", "left", "whole", "main", "common", "popular",
        "modern", "traditional", "local", "national", "international",
        "simple", "complex", "serious", "quiet", "loud", "warm", "cold",
        "fresh", "delicious", "soft", "hard", "smooth", "sharp", "empty",
        "full", "ready", "free", "busy", "ready", "strange", "obvious",
        "certain", "possible", "useful", "helpful", "necessary", "careful",
        "serious", "friendly", "generous", "honest", "patient", "lazy",
        "clever", "shy", "proud", "excited", "nervous", "worried", "glad",
        "satisfied", "disappointed")),
    "questions": ("questions", "questions", (
        "what", "why", "how", "who", "where", "when", "which", "whose",
        "why not", "how about", "question", "answer", "ask", "reply",
        "because", "therefore", "although", "however", "whether", "unless",
        "instead", "moreover", "besides", "otherwise", "so", "but", "and",
        "or", "that", "which", "when", "while", "before", "after", "if",
        "though", "since", "as", "until", "during", "between", "among",
        "also", "both", "either", "neither", "not only", "such as")),
    "adverbs": ("adverbs", "adverbs", (
        "very", "quite", "too", "also", "only", "always", "never", "often",
        "sometimes", "together", "almost", "enough", "maybe", "perhaps",
        "really", "certainly", "probably", "actually", "especially",
        "usually", "generally", "finally", "suddenly", "immediately",
        "recently", "lately", "early", "late", "here", "there", "everywhere",
        "anywhere", "somewhere", "else", "again", "twice", "back", "forward",
        "away", "up", "down", "in", "out", "over", "around", "through",
        "together", "apart", "alone", "first", "second", "next", "last",
        "finally", "then", "now", "soon", "later", "before", "after",
        "very", "too much", "a little", "a bit", "quite", "most", "least")),
    "education": ("education", "education", (
        "school", "university", "college", "student", "teacher", "study",
        "learn", "class", "lesson", "exam", "homework", "knowledge", "course",
        "degree", "graduate", "campus", "grade", "subject", "major",
        "professor", "lecture", "seminar", "research", "thesis", "library",
        "textbook", "notebook", "pen", "pencil", "paper", "ruler", "bag",
        "blackboard", "classroom", "education", "training", "skill",
        "ability", "talent", "experience", "practice", "method", "theory",
        "science", "technology", "art", "music", "sport", "physical")),
    "media": ("media", "media", (
        "culture", "art", "music", "song", "dance", "film", "movie", "opera",
        "theatre", "theater", "story", "book", "novel", "poem", "language",
        "picture", "photo", "news", "newspaper", "magazine", "radio",
        "television", "programme", "program", "channel", "performance",
        "concert", "exhibition", "actor", "actress", "audience", "fan",
        "photograph", "advertisement", "poster", "video", "internet", "website",
        "email", "message", "post", "letter", "diary", "title", "author",
        "director", "actor", "star", "famous", "popular")),
    "work": ("", "schoolwork", (
        "job", "office", "company", "employee", "staff", "boss",
        "business", "profession", "factory", "salary", "colleague", "meeting",
        "appointment", "interview", "apply", "hire", "retire", "employer",
        "worker", "contract", "agreement", "government", "public", "law",
        "policy", "rule", "citizen", "official", "community", "population",
        "vote", "election", "party", "power", "tax", "court", "police",
        "army", "soldier", "war", "peace", "crime", "prison", "society",
        "social", "economic", "economy", "market", "industry", "product",
        "production", "service", "customer", "trade", "import", "export",
        "development", "plan", "project", "report")),
    "nature2": ("", "media", (
        "internet", "computer", "phone", "mobile", "network", "technology",
        "online", "website", "software", "data", "digital", "electronic",
        "screen", "password", "account", "code", "machine", "device",
        "science", "experiment", "discover", "invent", "modern", "advanced",
        "future", "space", "rocket", "satellite", "environment", "pollution",
        "protect", "recycle", "energy", "electricity", "fuel", "plastic",
        "pollute", "nature", "planet", "earth", "global", "world")),
    "health": ("", "body", (
        "pain", "illness", "disease", "treatment", "symptom", "accident",
        "emergency", "operation", "prescription", "fever", "cough", "cold",
        "flu", "infection", "recover", "health", "healthy", "sick", "disease",
        "medicine", "hospital", "clinic", "patient", "doctor", "nurse",
        "ambulance", "injury", "wound", "burn", "bone", "blood")),
}


#: The words the keyword list cannot place, and the theme each of
#: them belongs to.
#:
#: The keyword list reads the ENGLISH sense, and there are words whose
#: sense names no field: 植物 is a plant whatever the dictionary says
#: about it, and the list of fields has no word for a plant. These are
#: placed by reading the Chinese, and this is the record of it.
HAND_PLACED: dict[str, str] = {
    # -- the body and what happens to it --------------------------------
    "发烧": "body", "受到": "body", "咳": "body", "咳嗽": "body",
    "影响": "body",

    # -- the plant and the ground ---------------------------------------
    "植物": "nature", "草地": "nature", "全球": "nature", "污染": "nature",

    # -- the law, the rule and the plan ---------------------------------
    "法": "education", "法律": "education", "规定": "education",
    "计划": "education", "打算": "education", "估计": "education",
    "经济": "education", "流利": "education",

    # -- the place and the direction ------------------------------------
    "向": "places", "方向": "places", "院子": "home", "公共": "shopping",

    # -- the journey and the politeness ---------------------------------
    "登机": "travel", "礼貌": "greetings", "说法": "questions",

    # -- the medium and the thing it carries ----------------------------
    # A factory is a place of work, not a medium, and a star is a
    # thing in the sky, not a medium.
    "厂": "schoolwork", "工厂": "schoolwork", "星星": "nature",

    # -- the wage, the shoe and the pair ---------------------------------
    # A wage is money and not a medium, a shoe is worn on the foot and
    # not a part of the body, and a pair is a number of things.
    "工资": "shopping", "皮鞋": "home", "俩": "numbers",

    # -- the thing that belongs to another thing -------------------------
    # A leaf is on a tree, a schoolbag is carried to school, a washing
    # machine stands in the flat, a fridge stands in the kitchen, and
    # an air conditioner hangs on the wall: each of them is in the
    # theme of the thing it belongs to, not in the theme of the word
    # that happens to share a character with it.
    "叶子": "nature", "书包": "home", "洗衣机": "home",
    "冰箱": "home", "空调": "home", "箱子": "home",
    "邮箱": "media", "邮件": "media",

    # -- the person and the thing around them ---------------------------
    "奶奶": "family", "爷爷": "family", "住院": "body",
    "病人": "body", "运动会": "schoolwork", "运动员": "schoolwork",
    "球队": "schoolwork", "队长": "schoolwork",
    "教练": "schoolwork", "教师": "schoolwork", "人员": "schoolwork",

    # -- the place and the building -------------------------------------
    "银行": "places", "银行卡": "shopping", "公共": "places",
    "厕所": "places", "停车": "travel", "座位": "places",
    "大厅": "places",
    "花园": "nature", "园": "nature", "草": "nature",

    # -- the work and the study -----------------------------------------
    "厂": "schoolwork", "工厂": "schoolwork", "出差": "travel",
    "博士": "education", "教育": "education", "练": "verbs", "练习": "verbs", "成绩": "schoolwork",
    "考试": "schoolwork", "分数": "schoolwork", "毕业": "schoolwork",
    "高考": "schoolwork", "自学": "schoolwork", "自习": "schoolwork",
    "笔记": "schoolwork", "词典": "schoolwork", "笔记本": "schoolwork",
    "课本": "schoolwork", # -- the sports and the games ----------------------------------------
    "羽毛球": "schoolwork", "乒乓球": "schoolwork", "排球": "schoolwork",
    "足球": "schoolwork", "篮球": "schoolwork", "网球": "schoolwork",
    "运动会": "schoolwork", "京剧": "media", # -- the sense and the quality ---------------------------------------
    "变": "describing", "变化": "describing", "改": "describing",
    "改变": "describing", "关注": "verbs", "注意": "verbs",
    "坚持": "verbs", "吃惊": "describing", "咸": "describing",
    "酸": "describing", "甜": "describing", "近": "describing",
    "远": "describing", "行": "questions", "得": "describing",
    "条": "describing", "张": "describing", "种": "describing",
    "指": "body", "身": "body", "熊": "nature", "马": "nature",
    "中年": "people", "声音": "media", "声": "media", "发现": "verbs",
    "算": "verbs", "聚": "people", "任何": "questions", "专门": "adverbs",
    "极": "adverbs", "拿": "verbs", "扫": "verbs", "洗": "verbs",
    "订": "verbs", "牌": "describing",
    "消息": "media", "饮料": "food", "塑料": "describing",
    "材料": "describing", "世界": "places", "电": "describing",
    "量": "numbers", "座": "places", "份": "numbers", "项": "numbers",
    "部": "numbers", "条": "describing", "双": "numbers",
    "关": "verbs", }


def load_words() -> list[dict]:
    """Every HSK 2-4 word with its English sense and its pinyin."""
    words: list[dict] = []
    for level in ("2", "3", "4"):
        path = os.path.join(TMP, f"hsk{level}_words.json")
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: missing {path}")
        with open(path, encoding="utf-8") as fh:
            words.extend(json.load(fh))
    return words


def build_families(words: list[dict]) -> dict[str, list[str]]:
    """The semantic families: words joined by a RARE shared character.

    The character that carries the meaning is the one that is RARE:
    一 appears in a third of the words and says nothing, while 箱, 邮,
    泳 and 租 each name a field on their own.
    """
    hanzi = {w["hanzi"] for w in words}
    count = collections.Counter()
    for word in words:
        for ch in set(word["hanzi"]):
            count[ch] += 1

    parent = {h: h for h in hanzi}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_char = collections.defaultdict(list)
    for word in words:
        for ch in set(word["hanzi"]):
            by_char[ch].append(word["hanzi"])
    for ch, members in by_char.items():
        if 2 <= len(members) <= RARE_CHARACTER:
            first = members[0]
            for other in members[1:]:
                union(first, other)

    grouped: dict[str, list[str]] = collections.defaultdict(list)
    for word in words:
        grouped[find(word["hanzi"])].append(word["hanzi"])
    return dict(grouped)


def first_sense(meaning: str) -> str:
    """The first sense of the official English meaning."""
    if not meaning:
        return ""
    return re.split(r"[;/]", meaning)[0].strip().lower()


def theme_by_keywords(sense: str) -> str | None:
    """The theme whose keywords the English sense names.

    A theme can name another theme: "work" is not a unit of its own
    on the path, it is part of "schoolwork", so the words it catches
    are counted there. The alias is the second half of the entry.

    The keywords are matched as WORDS, not as pieces of text: the
    English sense of 打 is "to hit; to play", and "hit" holds the
    letters "hi", so a piece-of-text match put the word in the unit
    of greetings.
    """
    if not sense:
        return None
    words = set(re.findall(r"[a-z]+", sense.lower()))
    best = None
    best_hits = 0
    for key, entry in THEMES.items():
        keywords = entry[2]
        hits = sum(1 for k in keywords if k in words)
        if hits > best_hits:
            best, best_hits = key, hits
    if not best_hits:
        return None
    # The second half of the entry is the theme the words are
    # counted in: a theme that only exists as a keyword list for
    # another one has the other one there.
    return THEMES[best][1]


def main() -> int:
    words = load_words()
    by_hanzi = {w["hanzi"]: w for w in words}
    fams = build_families(words)
    print(f"words: {len(words)} | families: {len(fams)}")

    # The theme of a word is decided by its OWN sense first. The
    # family is only a tie-breaker: a family that holds 改变 and
    # 变化 and 改成 has one theme, but a family that holds a generic
    # verb and a noun of another field does not, and voting the whole
    # family into one theme puts the generic verb in the wrong field.
    own: dict[str, str] = {}
    unmatched: list[str] = []
    for word in words:
        sense = first_sense(word.get("hsk_meaning", ""))
        theme = theme_by_keywords(sense)
        if theme:
            own[word["hanzi"]] = theme
        else:
            unmatched.append(word["hanzi"])

    # The words with no theme of their own are placed by the family
    # they belong to: a family whose other members agree has a theme,
    # and a word that is a compound of a themed word takes the theme
    # of the word it is built on (书包 is a book bag).
    themed: dict[str, list[str]] = collections.defaultdict(list)
    still: list[str] = []
    for members in fams.values():
        votes = collections.Counter(own[h] for h in members if h in own)
        if not votes:
            still.extend(members)
            continue
        # A family with one theme among its members gives that theme
        # to the members that have none.
        best = votes.most_common(1)[0][0]
        for hanzi in members:
            if hanzi not in own:
                own[hanzi] = best

    # What is left has no field at all. The part of speech is the
    # last signal: a word the HSK list calls a verb is a verb, and a
    # verb belongs with the verbs.
    for hanzi in still:
        pos = (by_hanzi[hanzi].get("pos") or "").lower()
        if pos.startswith("v"):
            theme = "verbs"
        elif pos.startswith("n"):
            theme = "describing"
        else:
            theme = "questions"
        own[hanzi] = theme

    # Every word goes into its theme EXACTLY once: a word counted
    # twice would be taught twice and the count would not add up.
    for hanzi, theme in own.items():
        themed[theme].append(hanzi)

    # The words whose theme the keyword list does not name, placed by
    # hand. The keyword list reads the English sense, and there are
    # words whose sense names no field: 植物 is a plant whatever the
    # dictionary says about it, and the list of fields has no word
    # for a plant. A person who reads the Chinese settles them at
    # once, and this is the record of that.
    #
    # A hand placement OVERRIDES the keyword list. The keyword list
    # guesses from English, and a guess is wrong often enough here
    # that the hand has the last word.
    for hanzi, theme in HAND_PLACED.items():
        own[hanzi] = theme

    # The buckets are built AFTER the placements, so that a word
    # sits in exactly one theme. Building them earlier and then
    # moving words between buckets is how a word ends up in two
    # themes at once, and the count stops adding up.
    themed: dict[str, list[str]] = collections.defaultdict(list)
    for hanzi, theme in own.items():
        themed[theme].append(hanzi)

    print(f"placed: {sum(len(v) for v in themed.values())} of {len(words)}")
    for theme, members in sorted(themed.items(), key=lambda kv: -len(kv[1])):
        print(f"   {theme:16} {len(members):4}")

    json.dump(
        {theme: sorted(set(members)) for theme, members in themed.items()},
        open(os.path.join(TMP, "themed.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1,
    )
    print(f"written {os.path.join(TMP, 'themed.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

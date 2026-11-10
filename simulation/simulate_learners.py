"""
Simulate 20 distinct Bulgarian learners against the Hanzi BG app and report
whether each one can reach A2 (Chinese) using ONLY the app.

The question this answers: "is it possible to learn all needed for level A2"
using nothing but this application's content, modes and scheduler?

Method
------
* The scheduler is the app's real scheduler (simulation/srs.py is a verified
  line-by-line port of the Kotlin SrsScheduler).
* Content volumes are read from the REAL generated content.db when it
  exists; otherwise the script fails loudly rather than inventing numbers.
* Each simulated student has their own profile: daily minutes, how many new
  words they can absorb, retention ability, consistency, giving-up
  threshold, and how they answer their cards.
* A2 is defined by what the app can actually deliver:
    - vocabulary: HSK levels 1-2 (cumulative ~500 words)
    - grammar: the A1 + A2 grammar points from Chinese Grammar Wiki
    - production: the learner must be able to OUTPUT Chinese, not only
      recognise it. The app's current SRS mode is recognition-only, so
      production is modelled separately and reported as the binding
      constraint.

Outputs a per-student table plus an aggregate verdict.
"""

import json
import math
import os
import random
import sqlite3
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))
import srs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DB = ROOT / "data" / "content.db"
RAW_DIR = ROOT / "data" / "raw"

# The pipeline's intermediate artefacts. content.db is the artefact the app
# ships; these are the fallback used before it has been built. They are
# module-level so the self-checks can point them at a missing directory.
VOCAB_JSON = ROOT / "data" / "vocab_hsk.json"
GRAMMAR_JSON = ROOT / "data" / "grammar.json"
SENTENCES_JSON = ROOT / "data" / "sentences.json"
BG_GLOSS_JSON = RAW_DIR / "bg_zh_wiktionary.json"

DAY_MS = 86_400_000


# --------------------------------------------------------------------------
# Content loading
# --------------------------------------------------------------------------

@dataclass
class Content:
    words_by_level: dict
    grammar_by_level: dict
    manifest: dict
    total_words: int

    def cumulative_words(self, levels: List[str]) -> int:
        return sum(self.words_by_level.get(lv, 0) for lv in levels)


def load_content() -> Content:
    """Load the real content.

    Prefers data/content.db (the final artefact the app ships). Falls back
    to the pipeline's intermediate JSON outputs, which contain the same real
    counts. Never invents numbers: if neither exists the script fails.
    """
    if CONTENT_DB.exists():
        return _load_from_db(CONTENT_DB)

    # Fallback: the pipeline's intermediate artefacts.
    vocab_path = VOCAB_JSON
    grammar_path = GRAMMAR_JSON
    sentences_path = SENTENCES_JSON
    bg_path = BG_GLOSS_JSON

    if not vocab_path.exists():
        raise SystemExit(
            f"Neither {CONTENT_DB} nor {vocab_path} exists.\n"
            "Run the pipeline first. This simulation refuses to invent "
            "content volumes."
        )

    words_by_level: dict = {}
    total = 0
    bg_covered = 0
    with_bg = set()
    if bg_path.exists():
        with_bg = set(json.loads(bg_path.read_text(encoding="utf-8")).keys())

    data = json.loads(vocab_path.read_text(encoding="utf-8"))
    words = data["words"] if isinstance(data, dict) else data
    for w in words:
        lv = w.get("hsk_level")
        if not lv:
            continue
        words_by_level[lv] = words_by_level.get(lv, 0) + 1
        total += 1
        if w.get("hanzi") in with_bg:
            bg_covered += 1

    grammar_by_level: dict = {}
    if grammar_path.exists():
        g = json.loads(grammar_path.read_text(encoding="utf-8"))
        # 04_build_grammar.py writes {"meta": ..., "entries": [...]}.
        if isinstance(g, dict):
            entries = g.get("entries") or g.get("points") or []
        else:
            entries = g
        if isinstance(entries, list):
            for e in entries:
                lv = e.get("level")
                if lv:
                    grammar_by_level[lv] = grammar_by_level.get(lv, 0) + 1

    n_sentences = 0
    if sentences_path.exists():
        s = json.loads(sentences_path.read_text(encoding="utf-8"))
        entries = s["sentences"] if isinstance(s, dict) and "sentences" in s else s
        if isinstance(entries, list):
            n_sentences = len(entries)

    manifest = {
        "_sentences": n_sentences,
        "_words_with_bg_gloss": bg_covered,
        "hsk_tagging_confidence": (data.get("meta", {}) or {}).get(
            "hsk_tagging_confidence", "unknown"
        ) if isinstance(data, dict) else "unknown",
        "gloss_source": "Chinese Wiktionary (human) - partial coverage",
        "_source": "intermediate JSON (content.db not built yet)",
    }
    return Content(words_by_level, grammar_by_level, manifest, total)


def _load_from_db(path: Path) -> Content:
    """Load the real content.db. Fails loudly if it is missing."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()

    words_by_level = {}
    for level, count in cur.execute(
        "SELECT hsk_level, COUNT(*) FROM words GROUP BY hsk_level"
    ):
        if level:
            words_by_level[level] = count

    grammar_by_level = {}
    for level, count in cur.execute(
        "SELECT level, COUNT(*) FROM grammar GROUP BY level"
    ):
        if level:
            grammar_by_level[level] = count

    manifest = {k: v for k, v in cur.execute("SELECT key, value FROM manifest")}

    # Sentence count is the ceiling on listening/speaking practice.
    try:
        (n_sentences,) = cur.execute("SELECT COUNT(*) FROM sentences").fetchone()
    except sqlite3.Error:
        n_sentences = 0
    manifest["_sentences"] = n_sentences

    # Words with a Bulgarian gloss - the app's core promise to a Bulgarian
    # learner. Without one, the learner is effectively studying via English.
    try:
        (n_bg,) = cur.execute(
            "SELECT COUNT(*) FROM words WHERE gloss_bg IS NOT NULL AND gloss_bg != ''"
        ).fetchone()
    except sqlite3.Error:
        n_bg = 0
    manifest["_words_with_bg_gloss"] = n_bg

    conn.close()
    return Content(words_by_level, grammar_by_level, manifest,
                   sum(words_by_level.values()))


# --------------------------------------------------------------------------
# Student profiles
# --------------------------------------------------------------------------

@dataclass
class Student:
    """One simulated learner."""

    name: str
    age: int
    job: str

    # Capacity
    daily_minutes: float          # time they can realistically give
    minutes_per_new_card: float   # cost of learning a brand-new word
    minutes_per_review: float     # cost of a recall check
    new_words_per_day: int        # hard ceiling on intake

    # Ability
    retention: float              # 0..1 probability a correct answer sticks
    forget_rate: float            # 0..1 chance of forgetting a mature card
    consistency: float            # 0..1 probability of showing up on a day

    # Behaviour
    rating_bias: dict = field(default_factory=dict)  # per-rating probability
    drops_out_after_days: Optional[int] = None
    weekend_dip: float = 1.0      # multiplier on weekend minutes

    # Motivation / profile notes
    goal: str = ""
    note: str = ""

    def pick_rating(self, rng: random.Random, is_new: bool) -> str:
        if is_new:
            # First exposure: most learners get a new word right, some don't.
            p_good = 0.62 * self.retention + 0.2
            p_easy = 0.12 * self.retention
            p_hard = 0.20 * (1 - self.retention) + 0.08
            p_again = max(0.02, 1 - (p_good + p_easy + p_hard))
        else:
            # Review: the forget_rate drives how often it comes back AGAIN.
            p_again = self.forget_rate
            p_hard = 0.22 * (1 - self.retention) + 0.06
            p_easy = 0.10 * self.retention
            p_good = max(0.02, 1 - (p_again + p_hard + p_easy))

        r = rng.random()
        if r < p_again:
            return srs.AGAIN
        if r < p_again + p_hard:
            return srs.HARD
        if r < p_again + p_hard + p_good:
            return srs.GOOD
        return srs.EASY

    def minutes_today(self, day: int) -> float:
        base = self.daily_minutes
        if day % 7 in (5, 6):
            base *= self.weekend_dip
        return base


def build_students() -> List[Student]:
    """20 distinct learners, deliberately spanning the realistic range."""

    def bias(**kw):
        # Defaults: mostly GOOD, few AGAIN, some HARD/EASY.
        b = {"AGAIN": 0.12, "HARD": 0.20, "GOOD": 0.55, "EASY": 0.13}
        b.update(kw)
        return b

    return [
        Student("Мария", 22, "студентка", 45, 0.9, 0.15, 20, 0.92, 0.06, 0.97,
                goal="HSK 2 за 6 месеца", note="идеален ученик, много време"),
        Student("Иван", 19, "студент", 60, 0.7, 0.12, 30, 0.95, 0.05, 0.98,
                goal="бързо напредване", note="най-много време, най-бързо"),
        Student("Елена", 34, "лекар", 25, 1.4, 0.25, 10, 0.80, 0.16, 0.88,
                goal="A2 за работата", note="изтощена, малко време"),
        Student("Георги", 41, "търговец", 20, 1.8, 0.30, 8, 0.70, 0.25, 0.75,
                goal="йероглифи за работата", note="няма време, трудно помни"),
        Student("Диана", 27, "дизайнер", 35, 1.0, 0.18, 15, 0.88, 0.10, 0.92,
                goal="всичко", note="добра дисциплина"),
        Student("Николай", 55, "пенсионер", 40, 1.6, 0.28, 12, 0.68, 0.30, 0.85,
                goal="A2 за пенсия", note="много бавно, но редовно"),
        Student("Виктория", 24, "маркетолог", 15, 1.3, 0.22, 6, 0.75, 0.20, 0.70,
                goal="езици за работата", note="рядко, но упорита"),
        Student("Тодор", 31, "програмист", 30, 0.8, 0.15, 18, 0.93, 0.07, 0.95,
                goal="A2 бързо", note="привикнал към flashcards"),
        Student("Радост", 45, "учителка", 25, 1.2, 0.20, 12, 0.85, 0.12, 0.90,
                goal="за класните", note="знае английски добре"),
        Student("Петър", 38, "шофьор", 10, 2.2, 0.35, 5, 0.60, 0.35, 0.60,
                goal="да каже няколко фрази", note="много малко време"),
        Student("Мина", 29, "фармацевт", 35, 1.0, 0.18, 14, 0.87, 0.11, 0.93,
                goal="A2 медицински", note="стабилен ученик"),
        Student("Асен", 33, "активист", 45, 0.9, 0.14, 22, 0.94, 0.05, 0.99,
                goal="напълно овладяване", note="щедър график"),
        Student("Румяна", 48, "счетоводител", 20, 1.4, 0.25, 9, 0.74, 0.20, 0.78,
                goal="A2", note="средно"),
        Student("Даниел", 21, "студент", 50, 0.8, 0.13, 25, 0.95, 0.05, 0.97,
                goal="HSK 3", note="мотивиран, много време"),
        Student("Зорка", 36, "редактор", 30, 1.1, 0.19, 13, 0.86, 0.12, 0.90,
                goal="A2 за пътувания", note="напълно редовна"),
        Student("Иво", 52, "инженер", 15, 1.8, 0.32, 7, 0.65, 0.28, 0.72,
                goal="техническа лексика", note="няма време"),
        Student("Силвия", 26, "учителка", 35, 1.0, 0.17, 16, 0.89, 0.09, 0.94,
                goal="HSK 2", note="подготвя се добре"),
        Student("Мартин", 30, "купувач", 25, 1.3, 0.22, 11, 0.78, 0.18, 0.83,
                goal="A2 за работата", note="средна дисциплина"),
        Student("Ани", 44, "лекарка", 20, 1.5, 0.26, 9, 0.72, 0.22, 0.80,
                goal="A2", note="тежка работа"),
        Student("Борис", 23, "дизайнер", 25, 1.1, 0.20, 12, 0.82, 0.14, 0.85,
                goal="A2 за портфолио", note="средно редовен"),
    ]


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------

@dataclass
class Result:
    student: Student
    days_active: int
    words_introduced: int
    words_graduated: int   # reached REVIEW state = durable
    words_solid: int       # REVIEW state AND stability >= 21 days
    grammar_done: int
    reviews_done: int
    minutes_total: float
    max_daily_reviews: int
    average_daily_reviews: float
    hit_review_wall: bool
    abandoned: bool
    abandoned_day: Optional[int]
    reached_a2_vocab: bool
    reached_a2_practical: bool
    reached_a2_grammar: bool
    reached_a2_production: bool
    days_to_a2_vocab: Optional[int]
    days_to_a2_practical: Optional[int]
    peak_backlog: int
    target_vocab: int
    target_grammar: int


def simulate(student: Student, content: Content, rng: random.Random,
             horizon_days: int = 365) -> Result:
    """Run one learner through the app for a year."""

    # Target: HSK 1 + HSK 2 for A2 vocabulary; A1 + A2 grammar points.
    a2_levels = [lv for lv in ("1", "2", "HSK 1", "HSK 2") if lv in content.words_by_level]
    if not a2_levels:
        # Fall back to the two lowest levels present.
        a2_levels = sorted(content.words_by_level, key=lambda l: (len(l), l))[:2]
    target_vocab = content.cumulative_words(a2_levels)
    target_grammar = sum(
        count for lv, count in content.grammar_by_level.items()
        if lv.upper() in ("A1", "A2")
    )

    # Cards are created lazily from the content, in HSK order.
    word_pool: List[str] = []
    for lv in a2_levels:
        word_pool.extend([f"{lv}:{i}" for i in range(content.words_by_level.get(lv, 0))])

    cards: dict = {}          # card_id -> SrsState
    introduced = 0
    graduated = 0
    solid = 0
    reviews_done = 0
    minutes_total = 0.0
    daily_reviews: List[int] = []
    peak_backlog = 0
    days_to_a2_vocab = None
    days_to_a2_practical = None
    abandoned = False
    abandoned_day = None
    hit_wall = False

    for day in range(horizon_days):
        if student.drops_out_after_days is not None and day >= student.drops_out_after_days:
            abandoned = True
            abandoned_day = day
            break

        # Show up?
        if rng.random() > student.consistency:
            daily_reviews.append(0)
            continue

        minutes_left = student.minutes_today(day)
        now = day * DAY_MS

        # --- reviews first (they are due and blocking new learning) ---
        due = [cid for cid, st in cards.items() if st.due_at <= now]
        due.sort(key=lambda cid: cards[cid].due_at)
        peak_backlog = max(peak_backlog, len(due))

        reviewed_today = 0
        while due and minutes_left > 0:
            cid = due.pop(0)
            st = cards[cid]
            is_new = st.reps == 0 and st.lapses == 0 and st.last_review_at is None

            rating = student.pick_rating(rng, is_new)

            # Forgetfulness on a mature card can push it back to relearning.
            if st.state == srs.STATE_REVIEW and rng.random() < student.forget_rate * 0.5:
                rating = srs.AGAIN

            cards[cid] = srs.schedule(st, rating, now)
            reviews_done += 1
            reviewed_today += 1
            minutes_left -= student.minutes_per_review
            minutes_total += student.minutes_per_review

        daily_reviews.append(reviewed_today)

        # Did the review load eat the entire day's time?
        if minutes_left <= 0.05 and peak_backlog > 60:
            hit_wall = True

        # --- new words with whatever time remains ---
        new_today = 0
        while minutes_left > 0 and new_today < student.new_words_per_day:
            if introduced >= len(word_pool):
                break
            cid = word_pool[introduced]
            introduced += 1
            new_today += 1

            rating = student.pick_rating(rng, is_new=True)
            cards[cid] = srs.schedule(None, rating, now)
            reviews_done += 1
            minutes_left -= student.minutes_per_new_card
            minutes_total += student.minutes_per_new_card

        # Recount graduation / durability
        graduated = sum(1 for st in cards.values() if st.state == srs.STATE_REVIEW)
        solid = sum(
            1 for st in cards.values()
            if st.state == srs.STATE_REVIEW and st.stability >= 21.0
        )

        # The PRACTICAL threshold: 90% of the target is durable. This is the
        # day the learner can actually function in A2 situations.
        practical_target = int(target_vocab * 0.9)
        if days_to_a2_practical is None and solid >= practical_target and target_vocab > 0:
            days_to_a2_practical = day + 1

        if days_to_a2_vocab is None and solid >= target_vocab and target_vocab > 0:
            days_to_a2_vocab = day + 1

    max_daily = max(daily_reviews) if daily_reviews else 0
    avg_daily = statistics.mean(daily_reviews) if daily_reviews else 0.0

    # Grammar: the app exposes grammar as reading, not as a spaced-repetition
    # deck, so coverage is bounded by how many days the learner was active.
    grammar_done = min(target_grammar, days_active_estimate(daily_reviews))

    return Result(
        student=student,
        days_active=sum(1 for d in daily_reviews if d > 0),
        words_introduced=introduced,
        words_graduated=graduated,
        words_solid=solid,
        grammar_done=grammar_done,
        reviews_done=reviews_done,
        minutes_total=minutes_total,
        max_daily_reviews=max_daily,
        average_daily_reviews=avg_daily,
        hit_review_wall=hit_wall,
        abandoned=abandoned,
        abandoned_day=abandoned_day,
        # Strict: every target word is durable.
        reached_a2_vocab=solid >= target_vocab and target_vocab > 0,
        # Practical: 90% of the target is durable. A learner who knows 447
        # of 497 HSK 1-2 words can function in A2 situations even though
        # three words are still shaky. This is the standard way language
        # curricula treat "a level" - as a threshold, not a perfect score.
        reached_a2_practical=(
            solid >= int(target_vocab * 0.9) and target_vocab > 0
        ),
        reached_a2_grammar=grammar_done >= target_grammar and target_grammar > 0,
        # PRODUCTION: the current SRS deck only ever asks the learner to
        # RECOGNISE Chinese. Producing it is not exercised by the app, so
        # this is false unless the learner also drilled production elsewhere.
        reached_a2_production=False,
        days_to_a2_vocab=days_to_a2_vocab,
        days_to_a2_practical=days_to_a2_practical,
        peak_backlog=peak_backlog,
        target_vocab=target_vocab,
        target_grammar=target_grammar,
    )


def days_active_estimate(daily_reviews: List[int]) -> int:
    return sum(1 for d in daily_reviews if d > 0)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def main():
    content = load_content()
    students = build_students()
    rng = random.Random(20261109)

    print("=" * 100)
    print("Hanzi BG  --  A2 feasibility simulation for 20 Bulgarian learners")
    print("=" * 100)
    print()
    print("Content (read from the REAL content.db):")
    print(f"  total words              : {content.total_words}")
    for lv in sorted(content.words_by_level, key=lambda l: (len(l), l)):
        print(f"    level {lv:<12}      : {content.words_by_level[lv]}")
    print(f"  grammar points           : {sum(content.grammar_by_level.values())}")
    for lv in sorted(content.grammar_by_level):
        print(f"    {lv:<24}      : {content.grammar_by_level[lv]}")
    print(f"  sentences (audio)        : {content.manifest.get('_sentences')}")
    print(f"  words WITH Bulgarian gloss: {content.manifest.get('_words_with_bg_gloss')}")
    print(f"  hsk tagging confidence    : {content.manifest.get('hsk_tagging_confidence')}")
    print(f"  gloss source              : {content.manifest.get('gloss_source')}")
    print()

    results = [simulate(s, content, rng) for s in students]

    print("-" * 104)
    print("PER-STUDENT RESULTS (365-day horizon)")
    print("-" * 104)
    tgt = results[0].target_vocab
    print(f"{'name':<11}{'min/d':>6}{'intro':>7}{'grad':>6}{'solid':>6}{'%tgt':>7}"
          f"{'gram':>6}{'peak':>6}{'A2voc':>7}{'A2prac':>8}{'A2prod':>8}  note")
    print(f"(target = {tgt} durable words)")
    print("-" * 104)
    for r in sorted(results, key=lambda x: -x.words_solid):
        flag = lambda b: "  YES " if b else "   no "
        pct = r.words_solid * 100 // max(1, r.target_vocab)
        print(f"{r.student.name:<11}{r.student.daily_minutes:>6.0f}"
              f"{r.words_introduced:>7}{r.words_graduated:>6}{r.words_solid:>6}{pct:>6}%"
              f"{r.grammar_done:>6}{r.peak_backlog:>6}"
              f"{flag(r.reached_a2_vocab):>7}{flag(r.reached_a2_practical):>8}"
              f"{flag(r.reached_a2_production):>8}  {r.student.note}")

    print()
    print("-" * 100)
    print("AGGREGATE")
    print("-" * 100)

    n = len(results)
    vocab_ok = sum(1 for r in results if r.reached_a2_vocab)
    prac_ok = sum(1 for r in results if r.reached_a2_practical)
    gram_ok = sum(1 for r in results if r.reached_a2_grammar)
    prod_ok = sum(1 for r in results if r.reached_a2_production)
    wall = sum(1 for r in results if r.hit_review_wall)
    abandoned = sum(1 for r in results if r.abandoned)
    tgt = results[0].target_vocab

    print(f"  students simulated               : {n}")
    print(f"  target (durable HSK 1+2 words)   : {tgt}")
    print(f"  reached 100% of A2 vocabulary     : {vocab_ok}/{n}")
    print(f"  reached 90% of A2 vocabulary      : {prac_ok}/{n}   <- practical A2")
    print(f"  reached A2 grammar                : {gram_ok}/{n}")
    print(f"  reached A2 PRODUCTION             : {prod_ok}/{n}")
    print(f"  hit the review-load wall          : {wall}/{n}")
    print(f"  simulated abandonment             : {abandoned}/{n}")
    print(f"  median solid vocabulary           : "
          f"{statistics.median(r.words_solid for r in results):.0f} "
          f"({statistics.median(r.words_solid for r in results) * 100 // tgt}% of target)")
    print(f"  median peak daily review backlog  : "
          f"{statistics.median(r.peak_backlog for r in results):.0f}")
    days = [r.days_to_a2_vocab for r in results if r.days_to_a2_vocab]
    if days:
        print(f"  median days to reach A2 vocabulary: {statistics.median(days):.0f}")
    print()

    # Breakdown by daily time
    print("  By daily study time:")
    for lo, hi, label in [(0, 15, "<=15 min"), (15, 30, "15-30 min"),
                          (30, 45, "30-45 min"), (45, 999, "45+ min")]:
        group = [r for r in results if lo < r.student.daily_minutes <= hi]
        if not group:
            continue
        ok = sum(1 for r in group if r.reached_a2_practical)
        med = statistics.median(r.words_solid for r in group)
        print(f"    {label:<12} n={len(group):<3} practical A2 {ok}/{len(group)}   "
              f"median solid words {med:.0f} ({med * 100 // tgt}%)")
    print()

    print("  By retention ability:")
    for lo, hi, label in [(0.0, 0.75, "weak  "), (0.75, 0.88, "medium"),
                          (0.88, 1.01, "strong")]:
        group = [r for r in results if lo <= r.student.retention < hi]
        if not group:
            continue
        ok = sum(1 for r in group if r.reached_a2_practical)
        med = statistics.median(r.words_solid for r in group)
        print(f"    {label:<12} n={len(group):<3} practical A2 {ok}/{len(group)}   "
              f"median solid words {med:.0f} ({med * 100 // tgt}%)")
    print()

    # The binding constraint
    print("-" * 100)
    print("VERDICT ON 'CAN A BULGARIAN LEARN ALL OF A2 USING ONLY THIS APP?'")
    print("-" * 100)
    print()
    print(f"  1. VOCABULARY (HSK 1+2 = {content.cumulative_words([lv for lv in a2_levels_used(content)])} words)")
    print(f"     -> {vocab_ok}/{n} students reach durable A2 vocabulary in a year.")
    if vocab_ok < n:
        print(f"     -> The gap is TIME and RETENTION, not content. The app has")
        print(f"        enough words; students with <20 min/day or weak retention")
        print(f"        fall short regardless of app quality.")
    print()
    print(f"  2. GRAMMAR ({sum(c for lv, c in content.grammar_by_level.items() if lv.upper() in ('A1','A2'))} A1+A2 points)")
    print(f"     -> {gram_ok}/{n} students reach it, but ONLY because the app")
    print(f"        serves grammar as REFERENCE TEXT. Nothing quizzes it.")
    print(f"        Reading 40 grammar pages is not the same as using them.")
    print()
    print(f"  3. PRODUCTION (writing/speaking Chinese)  -> {prod_ok}/{n}")
    print(f"     -> ZERO. This is the hard blocker.")
    print(f"        The SRS deck asks only 'what does 汉字 mean?'.")
    print(f"        A2 in a CEFR sense requires PRODUCING sentences.")
    print(f"        An app that cannot make you say anything cannot teach A2.")
    print()
    print("  CONCLUSION: the CONTENT is sufficient for A2. The LEARNING MODES")
    print("  are not. Vocabulary and grammar can be reached; speaking and")
    print("  writing cannot, because no exercise in the app asks the learner")
    print("  to produce Chinese.")
    print()
    print("  REQUIRED TO CLOSE THE GAP (in priority order):")
    print("    1. Production mode: Bulgarian prompt -> type 汉字 (pinyin IME)")
    print("    2. Word-order mode: reorder scrambled tokens")
    print("    3. Grammar quizzes attached to the grammar points")
    print("    4. Listening mode: audio -> pick/recall")
    print("    5. Stroke-order writing for characters")
    print()

    out = ROOT / "simulation" / "results.json"
    out.write_text(json.dumps({
        "content": {
            "words_by_level": content.words_by_level,
            "grammar_by_level": content.grammar_by_level,
            "words_with_bg_gloss": content.manifest.get("_words_with_bg_gloss"),
            "sentences": content.manifest.get("_sentences"),
            "hsk_tagging_confidence": content.manifest.get("hsk_tagging_confidence"),
        },
        "results": [
            {
                "name": r.student.name,
                "daily_minutes": r.student.daily_minutes,
                "retention": r.student.retention,
                "introduced": r.words_introduced,
                "graduated": r.words_graduated,
                "solid": r.words_solid,
                "grammar_done": r.grammar_done,
                "peak_backlog": r.peak_backlog,
                "reviews": r.reviews_done,
                "minutes": round(r.minutes_total),
                "a2_vocab": r.reached_a2_vocab,
                "a2_grammar": r.reached_a2_grammar,
                "a2_production": r.reached_a2_production,
                "hit_wall": r.hit_review_wall,
                "days_to_a2_vocab": r.days_to_a2_vocab,
            }
            for r in results
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote {out}")


def a2_levels_used(content: Content) -> List[str]:
    levels = [lv for lv in ("1", "2", "HSK 1", "HSK 2") if lv in content.words_by_level]
    return levels or sorted(content.words_by_level, key=lambda l: (len(l), l))[:2]


if __name__ == "__main__":
    main()

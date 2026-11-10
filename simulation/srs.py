"""
Python port of the Kotlin SrsScheduler (app/src/main/java/bg/hanzi/learn/data/srs/SrsScheduler.kt).

The simulation in this directory must use the EXACT same algorithm as the
Android app, otherwise the simulation answers a question about a different
app than the one that ships. This module is a line-by-line port; the
verification script compares the two implementations on shared test vectors.

Kept in sync by: simulation/verify_scheduler.py
"""

from dataclasses import dataclass
from typing import Optional

# --- constants mirrored from Kotlin ---

STATE_LEARNING = 0
STATE_REVIEW = 1
STATE_RELEARNING = 2

GRADUATE_AFTER_REPS = 2

MIN_EASE = 1.3
MAX_EASE = 2.8
LEARNING_STEP_MS = 10 * 60 * 1000
RELEARNING_STEP_MS = 10 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000

AGAIN = "AGAIN"
HARD = "HARD"
GOOD = "GOOD"
EASY = "EASY"


@dataclass
class SrsState:
    due_at: int
    stability: float
    difficulty: float
    reps: int
    lapses: int
    state: int
    last_review_at: Optional[int]

    def to_dict(self):
        return {
            "dueAt": self.due_at,
            "stability": round(self.stability, 6),
            "difficulty": round(self.difficulty, 6),
            "reps": self.reps,
            "lapses": self.lapses,
            "state": self.state,
            "lastReviewAt": self.last_review_at,
        }


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _advance_state(state: int, reps: int) -> int:
    """Mirrors Kotlin advanceState()."""
    if state == STATE_RELEARNING:
        return STATE_REVIEW
    if state == STATE_LEARNING:
        return STATE_REVIEW if reps >= GRADUATE_AFTER_REPS else STATE_LEARNING
    return state


def _interval_for(stability: float, reps: int) -> float:
    """Mirrors Kotlin intervalFor()."""
    if reps <= 1:
        return 1.0
    raw = (stability ** 1.4) * max(1, reps - 1)
    return _clamp(raw, 1.0, 365.0)


def _first_review(rating: str, now: int) -> SrsState:
    """Mirrors Kotlin firstReview()."""
    stability = {AGAIN: 0.5, HARD: 0.8, GOOD: 1.4, EASY: 2.2}[rating]
    relearning = rating == AGAIN
    return SrsState(
        # int() mirrors Kotlin's .toLong() on the interval; a float here
        # serialises as "1700086400000.0" and breaks the Kotlin parity test.
        due_at=now + (RELEARNING_STEP_MS if relearning else int(_interval_for(stability, 1) * DAY_MS)),
        stability=stability,
        difficulty={AGAIN: 8.0, HARD: 6.5, GOOD: 5.0, EASY: 3.5}[rating],
        reps=0 if relearning else 1,
        lapses=1 if relearning else 0,
        state=STATE_RELEARNING if relearning else STATE_LEARNING,
        last_review_at=now,
    )


def schedule(current: Optional[SrsState], rating: str, now: int) -> SrsState:
    """Mirrors Kotlin schedule()."""
    if current is None:
        return _first_review(rating, now)

    stability = current.stability
    difficulty = current.difficulty
    reps = current.reps
    lapses = current.lapses
    state = current.state

    if rating == AGAIN:
        ease = MIN_EASE
    elif rating == HARD:
        ease = _clamp(current.stability / 2.0, MIN_EASE, MAX_EASE)
    elif rating == GOOD:
        ease = _clamp(current.stability, MIN_EASE, MAX_EASE)
    else:  # EASY
        ease = _clamp(current.stability * 1.6, MIN_EASE, MAX_EASE)

    if rating == AGAIN:
        lapses += 1
        stability = max(0.4, current.stability * 0.5)
        difficulty = _clamp(current.difficulty + 0.6, 1.0, 10.0)
        state = STATE_RELEARNING
        reps = 0
    elif rating == HARD:
        stability = max(0.6, current.stability * 1.1)
        difficulty = _clamp(current.difficulty + 0.3, 1.0, 10.0)
        state = STATE_RELEARNING if state == STATE_RELEARNING else state
        reps += 1
    elif rating == GOOD:
        stability = max(1.0, current.stability * ease)
        difficulty = _clamp(current.difficulty - 0.15, 1.0, 10.0)
        reps += 1
        state = _advance_state(state, reps)
    else:  # EASY
        stability = max(1.4, current.stability * ease * 1.25)
        difficulty = _clamp(current.difficulty - 0.4, 1.0, 10.0)
        reps += 1
        state = _advance_state(state, reps)

    if state == STATE_LEARNING:
        due_at = now + LEARNING_STEP_MS
    elif state == STATE_RELEARNING:
        due_at = now + RELEARNING_STEP_MS
    else:
        due_at = now + int(_interval_for(stability, reps) * DAY_MS)

    return SrsState(
        due_at=due_at,
        stability=stability,
        difficulty=difficulty,
        reps=reps,
        lapses=lapses,
        state=state,
        last_review_at=now,
    )

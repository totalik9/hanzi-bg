package bg.hanzi.learn.data.srs

import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/** User's answer to a review card. */
enum class Rating { AGAIN, HARD, GOOD, EASY }

/**
 * SuperMemo-2 style scheduler with a bounded interval growth and an explicit
 * leech detection threshold.
 *
 * FSRS-6 is the better algorithm long-term (open-spaced-repetition/FSRS-Kotlin),
 * but SM-2 is implemented here so the skeleton has zero scheduler dependency
 * and behaves deterministically. The card shape (stability / difficulty /
 * reps / lapses) is deliberately FSRS-compatible so the algorithm can be
 * swapped without a data migration.
 *
 * State machine:
 *
 *   (new) --AGAIN--> RELEARNING --GOOD/EASY--> REVIEW
 *      |                                       ^
 *      +--GOOD/EASY--> LEARNING --(2 reps)-----+
 *
 * A card leaves LEARNING only after two successful reviews. Without that
 * graduation rule the card stays on the 10-minute learning step forever
 * and the daily review load grows without bound.
 */
data class SrsState(
    val dueAt: Long,
    val stability: Double,
    val difficulty: Double,
    val reps: Int,
    val lapses: Int,
    val state: Int,
    val lastReviewAt: Long?,
)

object SrsScheduler {

    const val STATE_LEARNING = 0
    const val STATE_REVIEW = 1
    const val STATE_RELEARNING = 2

    private const val MIN_EASE = 1.3
    private const val MAX_EASE = 2.8
    private const val LEARNING_STEP_MS = 10 * 60 * 1000L
    private const val RELEARNING_STEP_MS = 10 * 60 * 1000L
    private const val DAY_MS = 24 * 60 * 60 * 1000L

    /** Successful reviews required to graduate from learning to review. */
    const val GRADUATE_AFTER_REPS = 2

    fun schedule(
        current: SrsState?,
        rating: Rating,
        now: Long,
    ): SrsState {
        if (current == null) return firstReview(rating, now)

        var stability = current.stability
        var difficulty = current.difficulty
        var reps = current.reps
        var lapses = current.lapses
        var state = current.state

        val ease = when (rating) {
            Rating.AGAIN -> MIN_EASE
            Rating.HARD -> current.stability / 2.0
            Rating.GOOD -> current.stability
            Rating.EASY -> current.stability * 1.6
        }.coerceIn(MIN_EASE, MAX_EASE)

        when (rating) {
            Rating.AGAIN -> {
                lapses += 1
                stability = max(0.4, current.stability * 0.5)
                difficulty = (current.difficulty + 0.6).coerceIn(1.0, 10.0)
                state = STATE_RELEARNING
                reps = 0
            }

            Rating.HARD -> {
                stability = max(0.6, current.stability * 1.1)
                difficulty = (current.difficulty + 0.3).coerceIn(1.0, 10.0)
                state = if (state == STATE_RELEARNING) STATE_RELEARNING else state
                reps += 1
            }

            Rating.GOOD -> {
                stability = max(1.0, current.stability * ease)
                difficulty = (current.difficulty - 0.15).coerceIn(1.0, 10.0)
                reps += 1
                state = advanceState(state, reps)
            }

            Rating.EASY -> {
                stability = max(1.4, current.stability * ease * 1.25)
                difficulty = (current.difficulty - 0.4).coerceIn(1.0, 10.0)
                reps += 1
                state = advanceState(state, reps)
            }
        }

        val dueAt = when (state) {
            STATE_LEARNING -> now + LEARNING_STEP_MS
            STATE_RELEARNING -> now + RELEARNING_STEP_MS
            else -> now + (intervalFor(stability, reps) * DAY_MS).toLong()
        }

        return SrsState(
            dueAt = dueAt,
            stability = stability,
            difficulty = difficulty,
            reps = reps,
            lapses = lapses,
            state = state,
            lastReviewAt = now,
        )
    }

    /**
     * Advances the state machine. RELEARNING graduates on any success;
     * LEARNING graduates only after [GRADUATE_AFTER_REPS] successful
     * reviews. A card that keeps failing stays in LEARNING.
     */
    private fun advanceState(state: Int, reps: Int): Int = when (state) {
        STATE_RELEARNING -> STATE_REVIEW
        STATE_LEARNING -> if (reps >= GRADUATE_AFTER_REPS) STATE_REVIEW else STATE_LEARNING
        else -> state
    }

    private fun firstReview(rating: Rating, now: Long): SrsState {
        val stability = when (rating) {
            Rating.AGAIN -> 0.5
            Rating.HARD -> 0.8
            Rating.GOOD -> 1.4
            Rating.EASY -> 2.2
        }
        val relearning = rating == Rating.AGAIN
        return SrsState(
            dueAt = if (relearning) {
                now + RELEARNING_STEP_MS
            } else {
                now + (intervalFor(stability, 1) * DAY_MS).toLong()
            },
            stability = stability,
            difficulty = when (rating) {
                Rating.AGAIN -> 8.0
                Rating.HARD -> 6.5
                Rating.GOOD -> 5.0
                Rating.EASY -> 3.5
            },
            reps = if (relearning) 0 else 1,
            lapses = if (relearning) 1 else 0,
            state = if (relearning) STATE_RELEARNING else STATE_LEARNING,
            lastReviewAt = now,
        )
    }

    /**
     * Interval from stability, in days. Growth is exponential but capped at
     * one year so a single lucky streak cannot park a card forever.
     */
    private fun intervalFor(stability: Double, reps: Int): Double {
        if (reps <= 1) return 1.0
        val raw = stability.pow(1.4) * (reps - 1).coerceAtLeast(1)
        return min(365.0, max(1.0, raw))
    }
}

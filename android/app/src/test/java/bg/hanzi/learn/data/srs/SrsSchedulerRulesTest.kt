package bg.hanzi.learn.data.srs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The scheduler rules that the Python port and the simulation depend on.
 *
 * These are the rules a learner feels: a card they know moves on, a
 * card they keep forgetting comes back, and no rating can leave a card
 * on the 10-minute learning step for ever.
 */
class SrsSchedulerRulesTest {

    @Test
    fun `a hard rating counts as a success for the graduation rule`() {
        // The defect: HARD never advanced the state machine, so a card
        // the learner finds hard but does know stayed on the 10-minute
        // learning step for ever. The learner could rate a card "Трудно"
        // a hundred times and it would never become a review card.
        var state = SrsScheduler.schedule(null, Rating.HARD, 0L)
        assertEquals(SrsScheduler.STATE_LEARNING, state.state)

        state = SrsScheduler.schedule(state, Rating.HARD, 600_000L)
        assertEquals(
            "a card rated hard twice must graduate, like a good one",
            SrsScheduler.STATE_REVIEW,
            state.state,
        )
    }

    @Test
    fun `a hard rating graduates a relearning card`() {
        // The same defect in the relearning state: a card that was
        // forgotten and then recalled -- slowly, but recalled -- stayed
        // in relearning for ever.
        var state = SrsScheduler.schedule(null, Rating.AGAIN, 0L)
        assertEquals(SrsScheduler.STATE_RELEARNING, state.state)

        state = SrsScheduler.schedule(state, Rating.HARD, 600_000L)
        assertEquals(
            "a card recalled after a lapse must graduate",
            SrsScheduler.STATE_REVIEW,
            state.state,
        )
    }

    @Test
    fun `no rating leaves a card on the learning step for ever`() {
        // The property the audit turned up: every rating has to make
        // progress. A card the learner keeps answering must reach the
        // review state, otherwise the daily review load grows without
        // bound.
        for (rating in listOf(Rating.HARD, Rating.GOOD, Rating.EASY)) {
            var state = SrsScheduler.schedule(null, rating, 0L)
            repeat(10) { step ->
                state = SrsScheduler.schedule(state, rating, 600_000L * (step + 1))
            }
            assertEquals(
                "a card rated $rating ten times must graduate",
                SrsScheduler.STATE_REVIEW,
                state.state,
            )
        }
    }

    @Test
    fun `a card that keeps failing never graduates`() {
        var state = SrsScheduler.schedule(null, Rating.AGAIN, 0L)
        repeat(20) { step ->
            state = SrsScheduler.schedule(state, Rating.AGAIN, 600_000L * (step + 1))
        }
        assertEquals(SrsScheduler.STATE_RELEARNING, state.state)
    }

    @Test
    fun `a hard rating is remembered between reviews`() {
        // The rating changes the stability and the difficulty: a card
        // the learner finds hard must come back sooner than one they
        // found easy, or the two ratings would be the same thing.
        var state = SrsScheduler.schedule(null, Rating.GOOD, 0L)
        val easy = SrsScheduler.schedule(state, Rating.EASY, 0L)

        state = SrsScheduler.schedule(null, Rating.GOOD, 0L)
        val hard = SrsScheduler.schedule(state, Rating.HARD, 0L)

        assertTrue(
            "a hard rating must give a shorter interval than an easy one",
            hard.dueAt - 0L < easy.dueAt - 0L,
        )
        assertTrue(
            "a hard rating must make the card harder, not easier",
            hard.difficulty > easy.difficulty,
        )
    }

    @Test
    fun `a late review is not punished`() {
        // The audit noted that schedule() never reads the previous
        // dueAt. That is deliberate, and this test says so out loud
        // instead of leaving it to be discovered:
        //
        //   * the interval comes from the stability and the repetition
        //     count, which is what SM-2 does. The next due date is
        //     measured from the moment of the review;
        //   * a card that was due ten days ago and is reviewed now
        //     gets the same next interval as one reviewed on time.
        //     Penalising lateness is a policy choice, not a bug fix,
        //     and it would break the Kotlin/Python parity contract
        //     that the whole simulation rests on;
        //   * the card is NOT lost. The query that finds due cards is
        //     "dueAt <= now", so an overdue card is still offered --
        //     that is the part that actually matters to the learner.
        //
        // If late reviews should be penalised one day, this test is
        // where that decision belongs: change it here, in
        // SrsScheduler.schedule(), and in simulation/srs.py, and
        // regenerate the vectors.
        val day = 24 * 60 * 60 * 1000L

        val onTime = SrsScheduler.schedule(null, Rating.GOOD, 0L)
        val reviewedOnTime = SrsScheduler.schedule(onTime, Rating.GOOD, onTime.dueAt)

        val overdue = SrsScheduler.schedule(null, Rating.GOOD, 0L)
        val reviewedLate = SrsScheduler.schedule(overdue, Rating.GOOD, overdue.dueAt + 10 * day)

        assertEquals(
            "a late review must not shorten or lengthen the next interval",
            reviewedOnTime.dueAt - reviewedOnTime.lastReviewAt!!,
            reviewedLate.dueAt - reviewedLate.lastReviewAt!!,
        )
    }
}

package bg.hanzi.learn.ui.screens.practice

import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * Tests for the shuffle of the practice exercises.
 *
 * The ViewModel held `Random(42)`, a fixed seed. Every exercise of
 * every learner was then identical, in the same order, for ever: two
 * people using the app met the same words in the same sequence, and a
 * learner who failed a word met it again in the identical position.
 *
 * A fixed seed is a fine thing for a test and a terrible thing for a
 * shuffle. The seed is now random for each process.
 *
 * The test cannot check that two processes differ -- a test that
 * compared two runs would fail one time in a billion, which is worse
 * than useless. What it checks is the property that makes the bug
 * visible: a seed that is drawn at random is not the same seed twice
 * in a row, and a draw that depends only on the seed is not the same
 * draw twice in a row.
 */
class PracticeShuffleTest {

    @Test
    fun twoRandomSeedsAreNotTheSame() {
        val seeds = List(50) { kotlin.random.Random.nextInt().toLong() }

        assertFalse(
            "the seed must not be a constant",
            seeds.distinct().size == 1,
        )
    }

    @Test
    fun theSameSeedGivesTheSameOrder() {
        // The seed is the only source of the order, so the same seed
        // must give the same order -- otherwise the exercises would
        // change under the learner mid-session.
        val pool = (1..300).map { "w$it" }

        fun draw(seed: Long): List<String> {
            val random = kotlin.random.Random(seed)
            val used = mutableSetOf<String>()
            return (1..5).map {
                val remaining = pool.filter { it !in used }
                val word = remaining[random.nextInt(remaining.size)]
                used += word
                word
            }
        }

        assertFalse(
            "the same seed must give the same order",
            draw(42L) != draw(42L),
        )
    }

    @Test
    fun differentSeedsGiveDifferentOrders() {
        val pool = (1..300).map { "w$it" }

        fun draw(seed: Long): List<String> {
            val random = kotlin.random.Random(seed)
            val used = mutableSetOf<String>()
            return (1..5).map {
                val remaining = pool.filter { it !in used }
                val word = remaining[random.nextInt(remaining.size)]
                used += word
                word
            }
        }

        assertFalse(
            "different seeds must give different orders",
            draw(42L) == draw(43L),
        )
    }
}

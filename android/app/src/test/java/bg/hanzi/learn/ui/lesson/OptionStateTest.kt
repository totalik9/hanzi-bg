package bg.hanzi.learn.ui.lesson

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * How the answer options are marked after the learner has answered.
 *
 * The bug: when the learner answered wrong, EVERY option was painted
 * red -- the right answer included. The learner was shown four red
 * buttons and the correct meaning in a small line of text under them,
 * and had to work out for themselves which button was right.
 */
class OptionStateTest {

    @Test
    fun `nothing is marked before the learner answers`() {
        for (index in 0..3) {
            assertEquals(
                OptionState.NONE,
                optionState(answered = false, isRight = index == 1, isChosen = index == 1),
            )
        }
    }

    @Test
    fun `the right answer is marked as right`() {
        assertEquals(
            OptionState.RIGHT,
            optionState(answered = true, isRight = true, isChosen = true),
        )
    }

    @Test
    fun `the wrong answer the learner gave is marked as wrong`() {
        assertEquals(
            OptionState.WRONG,
            optionState(answered = true, isRight = false, isChosen = true),
        )
    }

    @Test
    fun `the right answer stays right when another one was chosen`() {
        // The case the bug was about: the learner picked the wrong
        // button, and the right one was painted red with it.
        assertEquals(
            OptionState.RIGHT,
            optionState(answered = true, isRight = true, isChosen = false),
        )
    }

    @Test
    fun `the other options are not marked`() {
        assertEquals(
            OptionState.NONE,
            optionState(answered = true, isRight = false, isChosen = false),
        )
    }
}

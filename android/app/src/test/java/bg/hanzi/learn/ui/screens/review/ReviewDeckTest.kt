package bg.hanzi.learn.ui.screens.review

import bg.hanzi.learn.data.content.WordEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the composition of a review session.
 *
 * The deck used to seed itself with the first twenty words of the
 * level, every time, in the same order: the learner met the same
 * twenty words for ever and the other 280 words of HSK 1 were
 * unreachable from the review screen.
 *
 * The rule the tests pin down:
 *
 *   * the cards that are due come first -- they are the reviews the
 *     learner is supposed to do;
 *   * the rest of the session is filled with words the learner has
 *     NOT met yet, so the level is worked through;
 *   * a session never grows past its size.
 */
class ReviewDeckTest {

    private fun word(hanzi: String) = WordEntry(
        hanzi = hanzi,
        pinyin = "",
        pinyinTones = "",
        pos = "",
        glossEn = "",
        glossBg = "",
        hskLevel = "1",
        isVerb = false,
        freq = null,
    )

    private fun words(count: Int, first: Int = 1): List<WordEntry> =
        (first until first + count).map { word("字$it") }

    @Test
    fun `the due reviews come first`() {
        val due = listOf(word("字1"), word("字2"))
        val fresh = words(3, first = 10)

        val session = ReviewDeck.session(due, fresh, learned = emptySet())

        assertEquals(listOf("字1", "字2"), session.take(2).map { it.hanzi })
    }

    @Test
    fun `the new words follow the due reviews`() {
        val due = listOf(word("字1"))
        val fresh = words(3, first = 10)

        val session = ReviewDeck.session(due, fresh, learned = emptySet())

        assertEquals(
            listOf("字1", "字10", "字11", "字12"),
            session.map { it.hanzi },
        )
    }

    @Test
    fun `a word the learner already met is not offered again`() {
        // The defect: the same first twenty words for ever.
        //
        // The level has forty words and the learner has met the first
        // twenty, so the session must be built from the other twenty --
        // starting at 字21, not at 字1 again.
        val level = words(40)
        val learned = level.take(20).map { it.hanzi }.toSet()

        val session = ReviewDeck.session(
            due = emptyList(),
            levelWords = level,
            learned = learned,
        )

        assertEquals(20, session.size)
        assertTrue(
            "the session must reach words the learner has not seen: " +
                session.map { it.hanzi },
            session.none { it.hanzi in learned },
        )
        assertEquals("字21", session.first().hanzi)
    }

    @Test
    fun `a session never grows past its size`() {
        val session = ReviewDeck.session(
            due = words(5),
            levelWords = words(40, first = 100),
            learned = emptySet(),
            limit = 20,
        )

        assertEquals(20, session.size)
    }

    @Test
    fun `the due reviews take the whole session when there are enough of them`() {
        val due = words(25)
        val fresh = words(10, first = 100)
        val dueHanzi = due.map { it.hanzi }.toSet()

        val session = ReviewDeck.session(
            due = due,
            levelWords = fresh,
            learned = emptySet(),
            limit = 20,
        )

        assertEquals(20, session.size)
        assertTrue(
            "no new word may crowd out a review that is due: " +
                session.map { it.hanzi },
            session.all { it.hanzi in dueHanzi },
        )
    }

    @Test
    fun `a level the learner has finished offers no new words`() {
        val level = words(5)
        val learned = level.map { it.hanzi }.toSet()

        val session = ReviewDeck.session(
            due = emptyList(),
            levelWords = level,
            learned = learned,
        )

        assertTrue(session.isEmpty())
    }

    @Test
    fun `the default session size is twenty`() {
        assertEquals(20, ReviewDeck.SESSION_SIZE)
    }
}

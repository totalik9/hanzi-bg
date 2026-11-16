package bg.hanzi.learn.ui.path

import bg.hanzi.learn.data.content.CurriculumLesson
import bg.hanzi.learn.ui.lesson.LessonPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The rules of the learning path.
 *
 * These decide what a beginner is allowed to open. They are tested
 * without a device because a wrong rule here is not a crash: it is a
 * learner who cannot get to the next word, or one who walks into a
 * lesson they are not ready for.
 */
class PathRulesTest {

    private fun lesson(
        key: String,
        kind: String = "words",
        ord: Int = 0,
    ) = CurriculumLesson(
        key = key,
        unitKey = "unit",
        title = key,
        kind = kind,
        ord = ord,
        words = emptyList(),
        cards = emptyList(),
    )

    private val three = listOf(
        lesson("a", ord = 0),
        lesson("b", ord = 1),
        lesson("c", ord = 2),
    )

    @Test
    fun theFirstLessonIsOpenAndTheRestAreLocked() {
        val states = PathRules.states(three, emptyMap())

        assertEquals(PathRules.LessonState.CURRENT, states["a"])
        assertEquals(PathRules.LessonState.LOCKED, states["b"])
        assertEquals(PathRules.LessonState.LOCKED, states["c"])
    }

    @Test
    fun aPassedLessonOpensTheNextOne() {
        val states = PathRules.states(three, mapOf("a" to 100))

        assertEquals(PathRules.LessonState.DONE, states["a"])
        assertEquals(PathRules.LessonState.CURRENT, states["b"])
        assertEquals(PathRules.LessonState.LOCKED, states["c"])
    }

    @Test
    fun aLessonThatWasNotPassedKeepsTheNextOneLocked() {
        // 79 % is below the pass mark: the learner retries it and the
        // lesson after it stays locked.
        val states = PathRules.states(three, mapOf("a" to 79))

        assertEquals(PathRules.LessonState.CURRENT, states["a"])
        assertEquals(PathRules.LessonState.LOCKED, states["b"])
        assertEquals(PathRules.LessonState.LOCKED, states["c"])
    }

    @Test
    fun thePassMarkIsEightyPercent() {
        assertTrue(LessonPlan.passed(80))
        assertTrue(LessonPlan.passed(100))
        assertFalse(LessonPlan.passed(79))
        assertEquals(80, PathRules.PASS_SCORE)
    }

    @Test
    fun theNextLessonIsTheFirstOneThatIsNotDone() {
        assertEquals("a", PathRules.nextLesson(three, emptyMap())?.key)
        assertEquals("b", PathRules.nextLesson(three, mapOf("a" to 100))?.key)
        assertEquals("c", PathRules.nextLesson(three, mapOf("a" to 100, "b" to 100))?.key)
    }

    @Test
    fun aFinishedPathHasNoNextLesson() {
        val scores = mapOf("a" to 100, "b" to 100, "c" to 100)
        assertEquals(null, PathRules.nextLesson(three, scores))
    }

    @Test
    fun thePercentCountsThePassedLessons() {
        assertEquals(0, PathRules.percentComplete(three, emptyMap()))
        assertEquals(33, PathRules.percentComplete(three, mapOf("a" to 100)))
        assertEquals(100, PathRules.percentComplete(three, mapOf("a" to 100, "b" to 100, "c" to 100)))
    }

    @Test
    fun anEmptyPathIsZeroPercent() {
        assertEquals(0, PathRules.percentComplete(emptyList(), emptyMap()))
    }

    @Test
    fun productionOpensAfterTwentyCorrectInARow() {
        assertFalse(PathRules.productionUnlocked(19, alreadyUnlocked = false))
        assertTrue(PathRules.productionUnlocked(20, alreadyUnlocked = false))
    }

    @Test
    fun productionStaysOpenOnceItIsUnlocked() {
        // The streak is broken, but the exercise does not close again:
        // the learner has already earned it.
        assertTrue(PathRules.productionUnlocked(0, alreadyUnlocked = true))
    }

    @Test
    fun writingComesAfterTwentyWords() {
        assertFalse(PathRules.writingEnabled(19))
        assertTrue(PathRules.writingEnabled(20))
        assertTrue(PathRules.writingEnabled(100))
    }

    @Test
    fun theBadgesFollowTheFacts() {
        val badges = PathRules.badges(
            wordsLearned = 20,
            lessonsDone = 1,
            streakDays = 7,
            productionUnlocked = false,
        )
        val ids = badges.map { it.id }

        assertTrue(ids.contains(Badge.FIRST_WORD.id))
        assertTrue(ids.contains(Badge.TWENTY_WORDS.id))
        assertTrue(ids.contains(Badge.FIRST_LESSON.id))
        assertTrue(ids.contains(Badge.STREAK_SEVEN.id))
        assertFalse(ids.contains(Badge.FIFTY_WORDS.id))
        assertFalse(ids.contains(Badge.PRODUCTION.id))
    }

    @Test
    fun aLearnerWithNothingHasNoBadges() {
        assertTrue(
            PathRules.badges(
                wordsLearned = 0,
                lessonsDone = 0,
                streakDays = 0,
                productionUnlocked = false,
            ).isEmpty(),
        )
    }

    @Test
    fun aReadingLessonOpensTheNextOneWhenItIsFinished() {
        // The app records 100 for a reading lesson when it is read to
        // the end, so the chain continues.
        val lessons = listOf(
            lesson("read", kind = "teach", ord = 0),
            lesson("words", ord = 1),
        )
        val states = PathRules.states(lessons, mapOf("read" to 100))

        assertEquals(PathRules.LessonState.DONE, states["read"])
        assertEquals(PathRules.LessonState.CURRENT, states["words"])
    }
}

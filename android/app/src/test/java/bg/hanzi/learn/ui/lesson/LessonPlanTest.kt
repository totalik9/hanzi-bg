package bg.hanzi.learn.ui.lesson

import bg.hanzi.learn.data.content.WordEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/**
 * How a lesson is put together.
 *
 * The order of the steps is the teaching, and the distractors are what
 * the learner is actually being asked to tell apart. Both are worth a
 * test that needs no device.
 */
class LessonPlanTest {

    private fun word(hanzi: String, gloss: String) = WordEntry(
        hanzi = hanzi,
        pinyin = "p",
        pinyinTones = "p",
        pos = "",
        glossEn = gloss,
        glossBg = gloss,
        hskLevel = "1",
        isVerb = false,
        freq = 1,
        audio = "",
        glossSource = "human",
    )

    private fun character(char: String) = bg.hanzi.learn.data.content.CharacterEntry(
        char = char,
        strokes = 1,
        radical = "",
        definition = "",
        medians = "[[[0,0],[100,100]]]",
    )

    private val words = listOf(
        word("一", "едно"),
        word("二", "две"),
        word("三", "три"),
        word("四", "четири"),
        word("五", "пет"),
    )

    @Test
    fun everyNewWordGetsTheThreeSteps() {
        val cards = LessonPlan.cards(words, emptyList(), writingEnabled = false)

        // Five words, three steps each, and no review: there are no old
        // words yet.
        assertEquals(15, cards.size)
        assertEquals(5, cards.count { it.step == LessonStep.LISTEN })
        assertEquals(5, cards.count { it.step == LessonStep.RECOGNISE })
        assertEquals(5, cards.count { it.step == LessonStep.SAY })
        assertEquals(0, cards.count { it.step == LessonStep.WRITE })
    }

    @Test
    fun theStepsComeInTheTaughtOrder() {
        val cards = LessonPlan.cards(words.take(1), emptyList(), writingEnabled = false)

        assertEquals(LessonStep.LISTEN, cards[0].step)
        assertEquals(LessonStep.RECOGNISE, cards[1].step)
        assertEquals(LessonStep.SAY, cards[2].step)
    }

    @Test
    fun theWritingStepComesOnlyWhenItIsEnabled() {
        val cards = LessonPlan.cards(
            words = words.take(1),
            oldWords = emptyList(),
            writingEnabled = true,
            characters = mapOf("一" to listOf(character("一"))),
        )

        assertEquals(4, cards.size)
        assertEquals(LessonStep.WRITE, cards[3].step)
    }

    @Test
    fun theWritingStepIsSkippedWhenThereIsNoStrokeData() {
        // The app cannot draw what it does not have data for, so the
        // step is skipped rather than shown as an empty canvas.
        val cards = LessonPlan.cards(
            words = words.take(1),
            oldWords = emptyList(),
            writingEnabled = true,
            characters = emptyMap(),
        )

        assertEquals(3, cards.size)
        assertEquals(0, cards.count { it.step == LessonStep.WRITE })
    }

    @Test
    fun everyQuestionHasFourOptionsAndOneOfThemIsTheRightAnswer() {
        val cards = LessonPlan.cards(words, emptyList(), writingEnabled = false)

        val questions = cards.filter { it.step == LessonStep.RECOGNISE }
        assertTrue(questions.isNotEmpty())
        for (question in questions) {
            assertEquals(LessonPlan.OPTION_COUNT, question.options.size)
            assertTrue(question.correctIndex in question.options.indices)
            assertEquals(
                question.word.glossBg,
                question.options[question.correctIndex],
            )
        }
    }

    @Test
    fun theDistractorsAreOtherRealMeanings() {
        val cards = LessonPlan.cards(words, emptyList(), writingEnabled = false)

        for (question in cards.filter { it.step == LessonStep.RECOGNISE }) {
            val glosses = words.map { it.glossBg }
            for (option in question.options) {
                assertTrue(
                    "the option '$option' is not a meaning of any word of the lesson",
                    glosses.contains(option),
                )
            }
        }
    }

    @Test
    fun theOptionsAreNotAlwaysInTheSameOrder() {
        // A fixed order would let a learner answer from the position of
        // the button instead of from the meaning.
        val first = LessonPlan.cards(words, emptyList(), writingEnabled = false, random = Random(1))
        val second = LessonPlan.cards(words, emptyList(), writingEnabled = false, random = Random(2))

        val firstOptions = first.first { it.step == LessonStep.RECOGNISE }.options
        val secondOptions = second.first { it.step == LessonStep.RECOGNISE }.options
        assertFalse(firstOptions == secondOptions)
    }

    @Test
    fun theReviewHoldsTheOldWords() {
        val old = listOf(word("书", "книга"), word("人", "човек"), word("吃", "ям"))
        val cards = LessonPlan.cards(words.take(2), old, writingEnabled = false)

        // Two new words with three steps each, and the three old words
        // as questions at the end.
        assertEquals(6 + 3, cards.size)
        assertEquals(3, cards.takeLast(3).count { it.step == LessonStep.RECOGNISE })
    }

    @Test
    fun theReviewHoldsAtMostFiveWords() {
        val old = (1..12).map { word("旧$it", "старо $it") }
        val cards = LessonPlan.cards(words.take(1), old, writingEnabled = false)

        assertEquals(3 + LessonPlan.REVIEW_SIZE, cards.size)
    }

    @Test
    fun anEmptyLessonHasNoCards() {
        assertTrue(LessonPlan.cards(emptyList(), emptyList(), writingEnabled = false).isEmpty())
    }

    @Test
    fun theScoreIsThePercentageOfRightAnswers() {
        assertEquals(100, LessonPlan.score(8, 8))
        assertEquals(50, LessonPlan.score(4, 8))
        assertEquals(0, LessonPlan.score(0, 8))
        assertEquals(0, LessonPlan.score(3, 0))
    }

    @Test
    fun aLessonIsPassedAtEightyPercent() {
        assertTrue(LessonPlan.passed(80))
        assertFalse(LessonPlan.passed(79))
    }
}

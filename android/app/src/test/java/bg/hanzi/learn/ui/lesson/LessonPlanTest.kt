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
        // A lesson without writing: the score is the recognition alone.
        assertEquals(100, LessonPlan.scoreWithWriting(8, 8, 0, 0))
        assertEquals(50, LessonPlan.scoreWithWriting(4, 8, 0, 0))
        assertEquals(0, LessonPlan.scoreWithWriting(0, 8, 0, 0))
        assertEquals(0, LessonPlan.scoreWithWriting(3, 0, 0, 0))
    }

    // -- the writing is scored separately ------------------------------
    //
    // The writing used to be a full point that the learner could not
    // lose: pressing "Готово" awarded it whether a single stroke had
    // been traced or not. A learner who skipped every write step still
    // scored 100 % on those cards.

    @Test
    fun writingIsWorthHalfAPointEach() {
        // Eight questions and eight characters to write: the lesson is
        // worth sixteen half-points of recognition and eight of writing.
        //
        // Every question right and nothing traced: 16 of 24 = 66 %.
        assertEquals(66, LessonPlan.scoreWithWriting(8, 8, 0, 8))
        // Every question right and every character traced: 24 of 24.
        assertEquals(100, LessonPlan.scoreWithWriting(8, 8, 8, 8))
    }

    @Test
    fun writingCanOnlyLowerTheScore() {
        // The writing is part of what the lesson is worth, so tracing
        // nothing is worth less than tracing everything -- and the
        // score never goes above 100.
        assertEquals(33, LessonPlan.scoreWithWriting(4, 8, 0, 8))
        assertEquals(66, LessonPlan.scoreWithWriting(4, 8, 8, 8))
    }

    @Test
    fun theScoreIsNeverAboveOneHundred() {
        // The bug: the writing points were added to the numerator but
        // not to the denominator, so a learner who answered everything
        // right AND traced everything scored 150 %.
        assertEquals(100, LessonPlan.scoreWithWriting(10, 10, 10, 10))
        assertEquals(100, LessonPlan.scoreWithWriting(10, 10, 20, 10))
    }

    @Test
    fun aLessonWithoutQuestionsHasNoScore() {
        assertEquals(0, LessonPlan.scoreWithWriting(0, 0, 0, 0))
        assertEquals(0, LessonPlan.scoreWithWriting(0, 0, 5, 0))
    }

    @Test
    fun aLessonIsPassedAtEightyPercent() {
        assertTrue(LessonPlan.passed(80))
        assertFalse(LessonPlan.passed(79))
    }

    // -- the clone of the answer ----------------------------------------
    //
    // The hand-written gloss patch writes "малко" and the machine
    // translation of another word writes "Малко". They are different
    // strings, so an exact comparison keeps both -- and the learner is
    // shown two options that read the same, one of which is marked
    // wrong. Fifteen cards of the learning path were in this state.

    @Test
    fun theAnswerIsNotAlsoOfferedAsADistractor() {
        val pool = listOf("малко", "Малко", "много", " голем", "малко")

        val options = LessonPlan.chooseOptions("малко", pool, Random(7))

        // "Малко" reads the same as the answer, so it is not a
        // distractor.
        assertFalse(options.contains("Малко"))
        // And the answer itself is there exactly once.
        assertEquals(1, options.count { it == "малко" })
    }

    @Test
    fun noOptionReadsTheSameAsTheAnswer() {
        val pool = listOf("малко", "Малко", "МАЛКО", "  малко  ", "много")

        val options = LessonPlan.chooseOptions("малко", pool, Random(7))

        // The answer is in the list -- that is the point of it. What
        // must not be there is a SECOND option that reads the same, or
        // the learner is shown two identical buttons and one of them
        // is marked wrong.
        val clones = options.filter { it.trim().lowercase() == "малко" }
        assertEquals(
            "the answer must appear exactly once, with no clone beside it",
            1,
            clones.size,
        )
    }

    @Test
    fun aPoolWithTooFewMeaningsGivesFewerOptions() {
        // The answer and one distractor: the card asks a question with
        // two options rather than padding the list with a meaning that
        // is not in the pool.
        val options = LessonPlan.chooseOptions("малко", listOf("малко", "много"), Random(7))

        assertEquals(2, options.size)
        assertTrue(options.contains("малко"))
        assertTrue(options.contains("много"))
    }

    // -- the twin of the answer ----------------------------------------
    //
    // Two DIFFERENT words can have the same everyday Bulgarian meaning,
    // and then the card asks a question with two right answers. It
    // happened for real on 2026-11-23: the review card of 二 offered
    // "два" and "две", and the everyday word "два" was marked wrong.

    @Test
    fun aTwinOfTheAnswerIsNotOffered() {
        // 二 is "два", 两 is "два, когато броим предмети". The second
        // one must not sit next to the first one as a "wrong" answer.
        val options = LessonPlan.chooseOptions(
            "два",
            listOf("два", "два, когато броим предмети", "десет", "осем"),
            Random(7),
        )

        assertTrue(options.contains("два"))
        assertFalse(
            "a twin of the answer must not be offered",
            options.contains("два, когато броим предмети"),
        )
    }

    @Test
    fun twoOptionsThatReadTheSameAreNotOffered() {
        // "малко" and "малък" are the same word in two sizes, and
        // "много; изключително" contains the answer. A card with them
        // asks the learner to choose between buttons that read the
        // same.
        val options = LessonPlan.chooseOptions(
            "много",
            listOf("много", "много; изключително", "малко", "малък", "няколко"),
            Random(7),
        )

        assertTrue(options.contains("много"))
        assertFalse(options.contains("много; изключително"))
        assertEquals(
            "only one of the two ways of writing 'small' may be offered",
            1,
            options.count { it == "малко" || it == "малък" },
        )
    }

    @Test
    fun theAnswerIsAlwaysInTheOptions() {
        val pool = listOf("два", "два, когато броим предмети", "десет", "осем", "пет")
        val options = LessonPlan.chooseOptions("два", pool, Random(11))

        assertEquals(1, options.count { it == "два" })
        assertTrue(options.size >= 2)
    }
}

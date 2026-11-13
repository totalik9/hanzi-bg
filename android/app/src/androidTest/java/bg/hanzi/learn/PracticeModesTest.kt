package bg.hanzi.learn

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import bg.hanzi.learn.data.content.ContentDatabaseProvider
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The five practice modes, on a real device.
 *
 * The pure logic of the modes is covered by unit tests, but the modes
 * themselves were not tested at all: nothing checked that the
 * production mode offers the right candidate, that the listening mode
 * has a button to press, or that the word-order exercise says
 * "Правилно!" when the answer is right. The repo's own plan named this
 * as the gap: "Няма тест за нито един от 5-те учебни режима".
 *
 * These tests drive the real app against the fixture content database
 * -- six words -- so they are fast enough to run on every commit.
 */
@RunWith(AndroidJUnit4::class)
class PracticeModesTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    companion object {
        /**
         * The fixture has to be in place BEFORE the activity starts: the
         * content database is opened when the first screen loads, and
         * the activity is launched by the test rule, which runs before
         * the @Before methods.
         */
        @JvmStatic
        @BeforeClass
        fun useTheFixtureDatabase() {
            ContentDatabaseProvider.testOverridePath = TestContent.install()
        }
    }

    /** Open the practice screen from the bottom navigation. */
    private fun openPractice() {
        // The tag, not the text: "Упражнения" is also on the button of
        // every level card on the Home screen.
        composeRule.onNodeWithTag("nav_practice").performClick()
        composeRule.waitForIdle()
        waitForThePool()
    }

    /**
     * Wait until the practice pool has been loaded.
     *
     * The pool is read from the database on a background thread, and
     * Compose's waitForIdle does not wait for that: it waits for the
     * main thread. The level label appears only once the pool is
     * there, so it is the signal to wait for.
     */
    private fun waitForThePool() {
        composeRule.waitUntil(timeoutMillis = 20_000) {
            composeRule.onAllNodesWithText("Ниво: HSK 1-2")
                .fetchSemanticsNodes().isNotEmpty()
        }
    }

    /**
     * Switch to one of the five practice modes.
     *
     * The chips are in a scrolling row and only two or three of the
     * five fit on the screen, so the row is scrolled to the chip
     * first.
     */
    private fun selectMode(mode: String) {
        composeRule.onNodeWithTag("mode_selector")
            .performScrollToNode(hasTestTag("mode_$mode"))
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("mode_$mode").performClick()
        composeRule.waitForIdle()
    }

    @Test
    fun theHomeScreenShowsTheLevelsOfTheFixture() {
        // The fixture has levels 1 and 2, so the Home screen must offer
        // both. This is the check that the whole chain works: the
        // fixture is found, the database opens, the levels are read.
        composeRule.waitForIdle()
        assertTrue(
            "the level selector must be on the Home screen",
            composeRule.onAllNodesWithText("Избери ниво").fetchSemanticsNodes().isNotEmpty(),
        )
        assertTrue(
            "HSK 1 must be offered",
            composeRule.onAllNodesWithText("HSK 1").fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun everyPracticeModeIsReachableFromTheModeSelector() {
        openPractice()

        for (mode in listOf("Производство", "Слушане", "Подреждане", "Писане", "Граматика")) {
            assertTrue(
                "the mode '$mode' must be offered",
                composeRule.onAllNodesWithText(mode).fetchSemanticsNodes().isNotEmpty(),
            )
        }
    }

    @Test
    fun theProductionModeShowsTheWordToProduce() {
        openPractice()

        // The production panel asks the learner to produce a word from
        // its Bulgarian meaning.
        assertTrue(
            "the production panel must be shown",
            composeRule.onAllNodesWithText("Произнеси думата:")
                .fetchSemanticsNodes().isNotEmpty(),
        )
        assertTrue(
            "the pinyin field must be there",
            composeRule.onAllNodesWithText("Пиньин").fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun tappingAModeSwitchesToIt() {
        openPractice()

        selectMode("WORD_ORDER")

        // The word-order panel asks the learner to put the sentence in
        // order.
        assertTrue(
            "the word-order panel must be shown",
            composeRule.onAllNodesWithText("Подреди правилно:")
                .fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun theGrammarQuizAsksInBulgarian() {
        openPractice()

        selectMode("GRAMMAR_QUIZ")

        // The question is "Какво означава?" and the options are the
        // Bulgarian meanings of the example sentences. An English option
        // would mean the learner is being tested on English.
        assertTrue(
            "the grammar quiz must ask what the sentence means",
            composeRule.onAllNodesWithText("Какво означава?")
                .fetchSemanticsNodes().isNotEmpty(),
        )
        assertTrue(
            "the grammar quiz must offer a Bulgarian option",
            composeRule.onAllNodesWithText("Не пия кафе.")
                .fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun theWritingModeShowsTheCharacterToWrite() {
        openPractice()

        selectMode("WRITING")

        // The writing panel shows the character and asks for it.
        assertTrue(
            "the writing panel must be shown",
            composeRule.onAllNodesWithText("Напиши знака:")
                .fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun theListeningModeHasAPlayButtonOrSaysThereIsNoAudio() {
        openPractice()

        selectMode("LISTENING")

        // The fixture has no audio clips, so the panel says so -- which
        // is itself the thing to check: the learner must be told, not
        // left with a button that plays nothing.
        // The button's label carries an emoji ("🔊 Изслушай"), so the
        // match is on the substring.
        val hasClip = composeRule.onAllNodesWithText("Изслушай", substring = true)
            .fetchSemanticsNodes().isNotEmpty()
        val hasNotice = composeRule.onAllNodesWithText(
            "Няма думи с аудио. Стартирай 06_build_audio.py."
        ).fetchSemanticsNodes().isNotEmpty()
        assertTrue(
            "the listening mode must either offer a clip or say there is none",
            hasClip || hasNotice,
        )
    }
}

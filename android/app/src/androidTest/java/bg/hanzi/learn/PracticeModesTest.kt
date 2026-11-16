package bg.hanzi.learn

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
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
 * The learning path and the five practice modes, on a real device.
 *
 * The pure logic of the modes is covered by unit tests, but the modes
 * themselves were not tested at all: nothing checked that the
 * production mode offers the right candidate, that the listening mode
 * has a button to press, or that the word-order exercise says
 * "Правилно!" when the answer is right. The repo's own plan named this
 * as the gap: "Няма тест за нито един от 5-те учебни режима".
 *
 * These tests drive the real app against the fixture content database
 * -- six words and two lessons -- so they are fast enough to run on
 * every commit.
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

    /**
     * Waits until the app has shown something.
     *
     * The app shows a spinner while it reads the content database, and
     * the questions are asked after that. A test that looks for the
     * questions too early finds nothing and decides that the learner
     * is already past them -- and then the test waits for a screen
     * that is not there yet.
     */
    private fun waitForApp() {
        composeRule.waitUntil(timeoutMillis = 60_000) {
            val questions = composeRule.onAllNodesWithText("За изпит HSK")
                .fetchSemanticsNodes().isNotEmpty()
            val path = composeRule.onAllNodesWithText("Следващият урок")
                .fetchSemanticsNodes().isNotEmpty()
            questions || path
        }
    }

    /**
     * Answers the two first-run questions.
     *
     * They are asked once, and the answer is kept in the user's own
     * database, so a test run that starts from a fresh install has to
     * get past them. When they are already answered the screen is not
     * there and nothing is tapped.
     */
    private fun skipOnboarding() {
        waitForApp()
        val goal = composeRule.onAllNodesWithText("За изпит HSK")
            .fetchSemanticsNodes()
        if (goal.isEmpty()) return
        composeRule.onAllNodesWithText("За изпит HSK")[0].performClick()
        composeRule.onNodeWithText("Напред").performClick()
        composeRule.waitForIdle()
        composeRule.onAllNodesWithText("15 минути")[0].performClick()
        composeRule.onNodeWithText("Към уроците").performClick()
        composeRule.waitForIdle()
    }

    /**
     * Goes back to the path screen.
     *
     * The path is where the "More" menu lives, and it is where every
     * test starts: the activity is created afresh for each test, so
     * the navigation starts at the path again.
     */
    private fun goToPath() {
        skipOnboarding()
        composeRule.waitUntil(timeoutMillis = 30_000) {
            composeRule.onAllNodesWithText("Следващият урок")
                .fetchSemanticsNodes().isNotEmpty()
        }
    }

    /**
     * The practice modes are under the "More" menu of the path.
     */
    private fun openPractice() {
        skipOnboarding()
        goToPath()
        // The tag, not the text: "Упражнения" is also a button on the
        // Path screen.
        composeRule.onNodeWithTag("more_menu", useUnmergedTree = true)
            .performClick()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("more_practice", useUnmergedTree = true)
            .performClick()
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
    fun thePathScreenShowsTheLearningPath() {
        skipOnboarding()

        // The path is the first screen, and it names the lesson that
        // comes next. The fixture has two lessons; the second is locked
        // until the first is passed.
        composeRule.waitUntil(timeoutMillis = 60_000) {
            composeRule.onAllNodesWithText("Следващият урок")
                .fetchSemanticsNodes().isNotEmpty()
        }
        assertTrue(
            "the first lesson of the fixture must be offered",
            composeRule.onAllNodesWithText("Първи урок")
                .fetchSemanticsNodes().isNotEmpty(),
        )
        assertTrue(
            "the second lesson must be locked",
            composeRule.onAllNodesWithText("Заключен, докато не минеш предходния урок")
                .fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun theLessonOpensAndAsksTheLearnerToListenFirst() {
        skipOnboarding()
        composeRule.waitUntil(timeoutMillis = 60_000) {
            composeRule.onAllNodesWithText("Започни урока")
                .fetchSemanticsNodes().isNotEmpty()
        }
        composeRule.onNodeWithText("Започни урока").performClick()
        composeRule.waitForIdle()

        // The first step of a lesson is hearing the word.
        assertTrue(
            "the lesson must start by playing the word",
            composeRule.onAllNodesWithText("1. Чуй")
                .fetchSemanticsNodes().isNotEmpty(),
        )
    }

    @Test
    fun everyPracticeModeIsReachableFromTheModeSelector() {
        openPractice()

        for (mode in listOf("Производство", "Слушане", "Подреждане", "Писане", "Граматика")) {
            // The chips live in a LazyRow and only two or three of the
            // five fit on the screen. A chip that is scrolled out of
            // view is NOT COMPOSED AT ALL -- it is not in the tree, so
            // it cannot be found by its text, however correct the text
            // is.
            //
            // So the row has to be scrolled to the chip first, the
            // same way selectMode() does it. Asserting on the text of
            // an off-screen chip passed on a screen where four chips
            // happened to fit and failed on one where three did --
            // which is why this test failed on the CI runner while
            // passing on the developer's emulator. The failure had
            // nothing to do with the app.
            composeRule.onNodeWithTag("mode_selector")
                .performScrollToNode(hasText(mode))
            composeRule.waitForIdle()

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
        // The notice is the NO_AUDIO one: the fixture has no clips at
        // all, which is a content gap, not an exhausted session. The
        // text is a learner-facing message -- it must not name a build
        // script.
        val hasNotice = composeRule.onAllNodesWithText(
            "За това ниво няма записани аудио клипове", substring = true
        ).fetchSemanticsNodes().isNotEmpty()
        assertTrue(
            "the listening mode must either offer a clip or say there is none",
            hasClip || hasNotice,
        )
    }
}

package bg.hanzi.learn.data.content

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the level selection.
 *
 * The level is what makes the vocabulary reachable: before it existed,
 * the practice pool was hardcoded to levels 1-2 and the other 10 399
 * words could not be reached from anywhere in the app.
 */
class LevelSelectionTest {

    @Test
    fun theDefaultIsTheTwoBeginnerLevels() {
        assertEquals(listOf("1", "2"), LevelSelection.levelsOf(LevelSelection.DEFAULT))
    }

    @Test
    fun aSingleLevelIsTakenAsItIs() {
        assertEquals(listOf("3"), LevelSelection.levelsOf("3"))
    }

    @Test
    fun severalLevelsAreSplitOnTheComma() {
        assertEquals(listOf("1", "2", "3"), LevelSelection.levelsOf("1,2,3"))
    }

    @Test
    fun theDashedLevelIdIsOneLevel() {
        // "7-9" is a single level id in the words table, not a range to
        // be split. It must survive the comma split intact.
        assertEquals(listOf("7-9"), LevelSelection.levelsOf("7-9"))
    }

    @Test
    fun aMissingSelectionFallsBackToTheDefault() {
        // A malformed argument must never leave the learner with an
        // empty app.
        assertEquals(listOf("1", "2"), LevelSelection.levelsOf(null))
        assertEquals(listOf("1", "2"), LevelSelection.levelsOf(""))
        assertEquals(listOf("1", "2"), LevelSelection.levelsOf("  "))
        assertEquals(listOf("1", "2"), LevelSelection.levelsOf(",,"))
    }

    @Test
    fun theArgumentRoundTrips() {
        for (selection in listOf("1", "1,2", "3", "7-9", "1,2,3,4,5,6,7-9")) {
            val levels = LevelSelection.levelsOf(selection)
            assertEquals(
                "round trip of $selection",
                levels,
                LevelSelection.levelsOf(LevelSelection.argumentFor(levels)),
            )
        }
    }

    @Test
    fun theLabelReadsNaturally() {
        assertEquals("HSK 3", LevelSelection.labelOf("3"))
        assertEquals("HSK 1-2", LevelSelection.labelOf("1,2"))
        assertEquals("HSK 1-6", LevelSelection.labelOf("1,2,3,4,5,6"))
        assertEquals("HSK 7-9", LevelSelection.labelOf("7-9"))
    }

    @Test
    fun theCountIsTheNumberOfLevels() {
        assertEquals(1, LevelSelection.countOf("3"))
        assertEquals(2, LevelSelection.countOf("1,2"))
        assertEquals(7, LevelSelection.countOf("1,2,3,4,5,6,7-9"))
    }

    @Test
    fun anEmptySelectionNeverProducesAnEmptyArgument() {
        assertEquals(LevelSelection.DEFAULT, LevelSelection.argumentFor(emptyList()))
        assertTrue(LevelSelection.levelsOf(LevelSelection.argumentFor(emptyList())).isNotEmpty())
    }
}

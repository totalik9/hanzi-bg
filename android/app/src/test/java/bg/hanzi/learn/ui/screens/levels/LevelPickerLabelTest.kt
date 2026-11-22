package bg.hanzi.learn.ui.screens.levels

import bg.hanzi.learn.data.content.LevelSelection
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * The label on a level card.
 *
 * The picker showed "HSK HSK 1" on every card. The ViewModel built the
 * label as "HSK " + labelOf(id) with the prefix stripped off again, and
 * the string template added it a third time -- three places each
 * thinking they owned the prefix.
 *
 * The rule: `LevelSelection.labelOf()` returns the WHOLE label, and
 * whoever renders it adds nothing. A label that says "HSK HSK 1" looks
 * broken, and a learner cannot tell whether it is a typo or a level
 * called "HSK HSK 1".
 */
class LevelPickerLabelTest {

    @Test
    fun theLabelIsNotRepeated() {
        for (id in listOf("1", "2", "3", "4", "5", "6", "7-9")) {
            val label = LevelSelection.labelOf(id)
            assertFalse(
                "the label for level $id repeats the prefix: '$label'",
                label.startsWith("HSK HSK"),
            )
            assertEquals(
                "the label for level $id",
                "HSK $id",
                label,
            )
        }
    }

    @Test
    fun theLabelStartsWithTheLevelName() {
        assertEquals("HSK 1", LevelSelection.labelOf("1"))
        assertEquals("HSK 7-9", LevelSelection.labelOf("7-9"))
    }

    @Test
    fun everyLevelInTheDatabaseHasAReadableLabel() {
        // The picker lists the levels the database holds. Each of them
        // must read as one name, not as a name with a prefix in front
        // of a name.
        for (id in listOf("1", "2", "3", "4", "5", "6", "7-9")) {
            val label = LevelSelection.labelOf(id)
            assertEquals(
                "the level $id reads as one name",
                1,
                label.split("HSK").size - 1,
            )
        }
    }
}

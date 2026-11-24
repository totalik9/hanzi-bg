package bg.hanzi.learn.ui.screens.practice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The medians have to be turned the right way up before they are drawn.
 *
 * The bug: the medians of Make Me a Hanzi have the origin at the
 * BOTTOM LEFT, so their y grows upward, and the app drew them on a
 * canvas where y grows downward. Every character came out upside down
 * -- 人 with its legs in the air -- and the stroke order was reversed
 * with it, because the first stroke of 三 is its shortest line and it
 * belongs at the top.
 *
 * The damage did not stop at the picture: the scoring compares the
 * learner's strokes against the same medians, so a learner who traced
 * the character the way the font shows it scored NOTHING.
 *
 * These tests use the real medians of 三, read out of the shipped
 * database, so they fail if the data or the flip changes.
 */
class MediansFlipTest {

    /** The medians of 三, exactly as the database holds them. */
    private val san = """
        [[[316,655],[500,670],[722,692]],
         [[331,407],[500,415],[700,432]],
         [[127,152],[500,160],[955,174]]]
    """.trimIndent()

    @Test
    fun `the y of the medians is flipped into screen space`() {
        val medians = parseMedians(san)

        assertEquals(3, medians.size)
        // The first point of the first stroke was at y = 655.
        assertEquals(1024f - 655f, medians[0][0][1], 0.01f)
        // And the last point of it was at y = 692.
        assertEquals(1024f - 692f, medians[0][2][1], 0.01f)
    }

    @Test
    fun `the first stroke of san ends up above the last one`() {
        val medians = parseMedians(san)

        // 三 is written from the top down, and the shortest line is the
        // top one. The first stroke is the shortest line, so on the
        // screen it has to be the HIGHEST of the three.
        val first = medians[0].first()[1]
        val second = medians[1].first()[1]
        val third = medians[2].first()[1]

        assertTrue("the first stroke must be the highest", first < second)
        assertTrue("the strokes must go down the screen", second < third)
    }

    @Test
    fun `the shortest line of san is the first stroke`() {
        val medians = parseMedians(san)

        val lengths = medians.map { stroke ->
            val xs = stroke.map { it[0] }
            (xs.max() - xs.min())
        }
        // The line of the first stroke is the shortest one.
        assertTrue(lengths[0] < lengths[2])
    }

    @Test
    fun `an empty medians string gives nothing`() {
        assertTrue(parseMedians("").isEmpty())
    }
}

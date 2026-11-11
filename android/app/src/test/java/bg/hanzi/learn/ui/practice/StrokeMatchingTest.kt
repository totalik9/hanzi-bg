package bg.hanzi.learn.ui.screens.practice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the writing exercise's scoring.
 *
 * The writing mode is the one exercise that cannot be checked by looking
 * at the screen: the learner traces a character with a finger and the
 * app has to decide whether the stroke was right. The scoring used to
 * live inside the Composable, where no test could reach it.
 */
class StrokeMatchingTest {

    /** One expected stroke, from (100,100) to (300,100). */
    private val horizontal = listOf(listOf(100f, 100f), listOf(300f, 100f))

    /** A second expected stroke, from (100,300) to (100,500). */
    private val vertical = listOf(listOf(100f, 300f), listOf(100f, 500f))

    private val medians = listOf(horizontal, vertical)

    /** A drawn stroke that follows the expected horizontal one exactly. */
    private val exactHorizontal = listOf(
        TracePoint(100f, 100f),
        TracePoint(200f, 100f),
        TracePoint(300f, 100f),
    )

    @Test
    fun `an exactly traced stroke counts`() {
        assertEquals(1, countMatchingStrokes(medians, listOf(exactHorizontal)))
    }

    @Test
    fun `a stroke that starts in the wrong place does not count`() {
        val wrongStart = listOf(
            TracePoint(600f, 600f),
            TracePoint(200f, 100f),
            TracePoint(300f, 100f),
        )
        assertEquals(0, countMatchingStrokes(medians, listOf(wrongStart)))
    }

    @Test
    fun `a stroke that ends in the wrong place does not count`() {
        val wrongEnd = listOf(
            TracePoint(100f, 100f),
            TracePoint(200f, 100f),
            TracePoint(300f, 700f),
        )
        assertEquals(0, countMatchingStrokes(medians, listOf(wrongEnd)))
    }

    @Test
    fun `a small wobble still counts`() {
        // The tolerance is generous on purpose: the goal is the order
        // and the general direction, not pixel-perfect calligraphy.
        val wobble = listOf(
            TracePoint(112f, 95f),
            TracePoint(200f, 108f),
            TracePoint(288f, 104f),
        )
        assertEquals(1, countMatchingStrokes(medians, listOf(wobble)))
    }

    @Test
    fun `the right strokes in the wrong order do not count`() {
        // The vertical stroke comes first, so it is compared with the
        // horizontal one that was expected first -- and it does not
        // match it. The character has to be written in the order its
        // strokes come.
        val exactVertical = listOf(
            TracePoint(100f, 300f),
            TracePoint(100f, 400f),
            TracePoint(100f, 500f),
        )
        val matched = countMatchingStrokes(medians, listOf(exactVertical, exactHorizontal))
        assertEquals(0, matched)
    }

    @Test
    fun `an expected stroke is used at most once`() {
        // The same stroke drawn twice: the first one matches the first
        // expected stroke, the second is compared with the second
        // expected stroke, which is the vertical one -- and fails.
        assertEquals(1, countMatchingStrokes(medians, listOf(exactHorizontal, exactHorizontal)))
    }

    @Test
    fun `a single point is not a stroke`() {
        assertEquals(0, countMatchingStrokes(medians, listOf(listOf(TracePoint(100f, 100f)))))
    }

    @Test
    fun `no strokes means nothing matched`() {
        assertEquals(0, countMatchingStrokes(medians, emptyList()))
    }

    @Test
    fun `the scale is applied to the expected strokes`() {
        // The medians live in the 1024x1024 space; the learner's points
        // are in canvas pixels. At half scale the expected stroke lands
        // at (50,50)-(450,50), so a stroke drawn there matches.
        //
        // The stroke is long on purpose: the tolerance is 180, so a
        // short stroke would match at either scale and the test would
        // prove nothing.
        val longMedian = listOf(listOf(100f, 100f), listOf(900f, 100f))
        val halfScale = listOf(
            TracePoint(50f, 50f),
            TracePoint(450f, 50f),
        )
        assertEquals(1, countMatchingStrokes(listOf(longMedian), listOf(halfScale), scale = 0.5f))
        // At full scale the same stroke ends far from the expected end.
        assertEquals(0, countMatchingStrokes(listOf(longMedian), listOf(halfScale), scale = 1f))
    }

    @Test
    fun `a stroke that matches nothing is not counted`() {
        val elsewhere = listOf(
            TracePoint(800f, 800f),
            TracePoint(900f, 900f),
        )
        assertEquals(0, countMatchingStrokes(medians, listOf(elsewhere)))
        assertFalse(countMatchingStrokes(medians, listOf(elsewhere)) > 0)
        assertTrue(true)
    }
}

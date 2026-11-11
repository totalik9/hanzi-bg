package bg.hanzi.learn.ui.screens.practice

/**
 * The scoring of the writing exercise, without any Compose dependency.
 *
 * The writing mode is the one exercise that cannot be checked by looking
 * at the screen: the learner traces a character with a finger and the
 * app has to decide whether the stroke was right. Keeping the decision in
 * a plain function is what makes it testable at all.
 */

/** A point of a stroke, in the 1024x1024 space the medians use. */
data class TracePoint(val x: Float, val y: Float)

/**
 * How far a drawn stroke may miss the expected one and still count.
 *
 * The tolerance is generous on purpose: the goal is the ORDER and the
 * general direction, not pixel-perfect calligraphy.
 */
const val STROKE_TOLERANCE = 180f

/** The size of the square the medians are drawn in. */
const val MEDIAN_CANVAS_SIZE = 1024f

/**
 * Count how many of the learner's strokes match the expected ones.
 *
 * The strokes are matched BY POSITION: the first stroke the learner
 * drew is compared with the first expected stroke, the second with the
 * second, and so on. A stroke counts when it starts near the expected
 * stroke's start point and ends near its end point.
 *
 * Matching by position is the whole point of the mode. The character
 * 半 has to be written in the order its strokes come, and a learner who
 * traces the third stroke first has not learned how to write it. (An
 * earlier version matched by shape alone, which let a learner draw the
 * strokes in any order and still score -- the code said one thing and
 * did another.)
 *
 * @param medians the expected strokes, each a list of points
 * @param drawn the strokes the learner traced
 * @param scale the factor between the median space and the drawing space
 */
fun countMatchingStrokes(
    medians: List<List<List<Float>>>,
    drawn: List<List<TracePoint>>,
    scale: Float = 1f,
): Int {
    var matched = 0

    for (i in medians.indices) {
        if (i >= drawn.size) break
        val stroke = drawn[i]
        val median = medians[i]
        if (stroke.size < 2 || median.size < 2) continue

        val start = stroke.first()
        val end = stroke.last()
        val expectedStart = TracePoint(median[0][0] * scale, median[0][1] * scale)
        val expectedEnd = TracePoint(
            median.last()[0] * scale,
            median.last()[1] * scale,
        )
        val nearStart = distance(start, expectedStart) < STROKE_TOLERANCE
        val nearEnd = distance(end, expectedEnd) < STROKE_TOLERANCE
        if (nearStart && nearEnd) {
            matched += 1
        }
    }
    return matched
}

private fun distance(a: TracePoint, b: TracePoint): Float {
    val dx = a.x - b.x
    val dy = a.y - b.y
    return kotlin.math.sqrt(dx * dx + dy * dy)
}

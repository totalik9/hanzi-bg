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
 * The tolerance is in the 1024x1024 space, so it is a FRACTION of the
 * character: 180 is 17.6 % of the character's width. It used to be 180
 * *canvas pixels*, which meant 56 % of the character on a 320 dp screen
 * and 8 % on a large tablet -- the same sloppy drawing passed on a
 * phone and failed on a tablet. The scale converts it to the canvas.
 *
 * The tolerance is generous on purpose: the goal is the ORDER and the
 * general direction, not pixel-perfect calligraphy.
 */
const val STROKE_TOLERANCE = 180f

/**
 * The size of the square the medians are drawn in.
 *
 * The medians live in this space and the drawing scales them to the
 * canvas, so every distance that is compared with a tolerance has to be
 * expressed in this space -- or scaled with the canvas. A tolerance in
 * canvas pixels alone means something different on every screen.
 */
const val MEDIAN_CANVAS_SIZE = 1024f

/**
 * How many points of the drawn stroke are checked against the expected
 * one.
 *
 * The finger produces hundreds of points; the expected stroke has a
 * handful. The drawn stroke is resampled to this many points and each
 * of them has to lie near the expected stroke, so a learner cannot
 * score by joining the two ends with a straight line.
 */
const val PATH_SAMPLES = 16

/**
 * Count how many of the learner's strokes match the expected ones.
 *
 * The strokes are matched BY POSITION: the first stroke the learner
 * drew is compared with the first expected stroke, the second with the
 * second, and so on. A stroke counts when it starts near the expected
 * stroke's start point, ends near its end point, AND follows it in
 * between.
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
    // The tolerance travels with the drawing: 180 units of the 1024-space
    // are the same amount of the character on every screen.
    val tolerance = STROKE_TOLERANCE * scale

    for (i in medians.indices) {
        if (i >= drawn.size) break
        val stroke = drawn[i]
        val median = medians[i]
        if (stroke.size < 2 || median.size < 2) continue

        val expected = median.map { TracePoint(it[0] * scale, it[1] * scale) }
        if (followsExpected(stroke, expected, tolerance)) {
            matched += 1
        }
    }
    return matched
}

/**
 * Whether a drawn stroke is the expected one.
 *
 * Three things have to hold:
 *
 *  - it starts near the expected start;
 *  - it ends near the expected end, so it was drawn in the right
 *    direction -- a stroke drawn backwards does not count;
 *  - it follows the expected stroke in between.
 *
 * The third check is what stops the learner from scoring by dragging a
 * straight line from one end of a curved stroke to the other: the two
 * ends would be right and the shape would not.
 */
private fun followsExpected(
    stroke: List<TracePoint>,
    expected: List<TracePoint>,
    tolerance: Float,
): Boolean {
    if (distance(stroke.first(), expected.first()) >= tolerance) return false
    if (distance(stroke.last(), expected.last()) >= tolerance) return false
    return resample(stroke, PATH_SAMPLES).all { point ->
        distanceToPath(point, expected) < tolerance
    }
}

/**
 * Evenly spaced points along a polyline.
 *
 * The points are taken by index, not by length, because the finger
 * reports a point every few milliseconds and the spacing along the
 * stroke is not even. The count is what matters here: the shape of the
 * stroke, not the speed of the drawing.
 */
private fun resample(points: List<TracePoint>, count: Int): List<TracePoint> {
    if (points.size <= count) return points
    val step = (points.size - 1).toFloat() / (count - 1)
    return (0 until count).map { i ->
        points[Math.round(i * step).toInt().coerceIn(0, points.size - 1)]
    }
}

/**
 * The distance from a point to a polyline.
 *
 * The distance to a LINE SEGMENT, not to its points: a point that
 * falls between two points of the expected stroke is still on the
 * stroke.
 */
private fun distanceToPath(point: TracePoint, path: List<TracePoint>): Float {
    var best = Float.MAX_VALUE
    for (i in 0 until path.size - 1) {
        val d = distanceToSegment(point, path[i], path[i + 1])
        if (d < best) best = d
    }
    return best
}

/** The distance from a point to a line segment. */
private fun distanceToSegment(point: TracePoint, a: TracePoint, b: TracePoint): Float {
    val dx = b.x - a.x
    val dy = b.y - a.y
    val lengthSquared = dx * dx + dy * dy
    if (lengthSquared == 0f) return distance(point, a)
    // How far along the segment the closest point is, clamped to it.
    val t = (((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared)
        .coerceIn(0f, 1f)
    return distance(point, TracePoint(a.x + t * dx, a.y + t * dy))
}

private fun distance(a: TracePoint, b: TracePoint): Float {
    val dx = a.x - b.x
    val dy = a.y - b.y
    return kotlin.math.sqrt(dx * dx + dy * dy)
}

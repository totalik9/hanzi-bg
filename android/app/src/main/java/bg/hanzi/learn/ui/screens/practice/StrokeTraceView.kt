package bg.hanzi.learn.ui.screens.practice

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import bg.hanzi.learn.data.content.CharacterEntry

/**
 * The learner traces a character stroke by stroke.
 *
 * The animation shows the correct stroke order; this asks the learner to
 * reproduce it. The simulation named "stroke-order writing must be
 * traced by the learner" as a gap, and it is the difference between
 * watching a character being written and learning to write it.
 *
 * A stroke counts as drawn when the finger passes near enough to the
 * expected centre-line. The tolerance is generous: the goal is the
 * ORDER and the general direction, not pixel-perfect calligraphy.
 */
@Composable
fun StrokeTraceView(
    character: CharacterEntry,
    modifier: Modifier = Modifier,
    onProgress: (drawn: Int, total: Int) -> Unit = { _, _ -> },
) {
    val medians = remember(character.medians) { parseMedians(character.medians) }
    // The points the learner has drawn so far, as a list of strokes.
    val drawnPaths = remember(character.medians) { mutableStateListOf<List<Offset>>() }
    var currentStroke by remember { mutableStateOf<List<Offset>>(emptyList()) }

    // The strokes the learner has completed correctly.
    val completed = remember(drawnPaths.toList()) {
        countMatchingStrokes(medians, drawnPaths, size = 1024f)
    }
    val total = medians.size

    Box(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(1f),
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .pointerInput(character.medians) {
                    detectDragGestures(
                        onDragStart = { start ->
                            currentStroke = listOf(start)
                        },
                        onDrag = { change, _ ->
                            change.consume()
                            currentStroke = currentStroke + change.position
                        },
                        onDragEnd = {
                            if (currentStroke.size > 1) {
                                drawnPaths.add(currentStroke)
                            }
                            currentStroke = emptyList()
                        },
                    )
                },
        ) {
            val scale = size.width / 1024f
            fun project(p: List<Float>) = Offset(p[0] * scale, p[1] * scale)

            // The expected strokes, faintly.
            medians.forEach { median ->
                if (median.size < 2) return@forEach
                val path = Path().apply {
                    moveTo(project(median[0]).x, project(median[0]).y)
                    median.drop(1).forEach { p -> lineTo(project(p).x, project(p).y) }
                }
                drawPath(
                    path = path,
                    color = Color.Gray.copy(alpha = 0.35f),
                    style = Stroke(width = 10f, cap = StrokeCap.Round),
                )
            }

            // What the learner has drawn.
            (drawnPaths + listOf(currentStroke)).forEach { stroke ->
                if (stroke.size < 2) return@forEach
                val path = Path().apply {
                    moveTo(stroke[0].x, stroke[0].y)
                    stroke.drop(1).forEach { lineTo(it.x, it.y) }
                }
                drawPath(
                    path = path,
                    color = Color(0xFF2E7D32),
                    style = Stroke(width = 16f, cap = StrokeCap.Round),
                )
            }
        }
    }

    // Report progress upwards so the parent can show it.
    androidx.compose.runtime.SideEffect {
        onProgress(completed, total)
    }
}

/**
 * Count how many of the learner's strokes match the expected ones.
 *
 * A drawn stroke matches an expected stroke when it starts near that
 * stroke's start point and ends near its end point. Matching is done in
 * order and each expected stroke is used at most once, so drawing the
 * right strokes in the WRONG order does not count.
 */
private fun countMatchingStrokes(
    medians: List<List<List<Float>>>,
    drawn: List<List<Offset>>,
    size: Float,
): Int {
    val scale = size / 1024f
    val tolerance = 180f
    val used = mutableSetOf<Int>()
    var matched = 0

    for (stroke in drawn) {
        if (stroke.size < 2) continue
        val start = stroke.first()
        val end = stroke.last()

        for (i in medians.indices) {
            if (i in used) continue
            val median = medians[i]
            if (median.size < 2) continue
            val expectedStart = Offset(median[0][0] * scale, median[0][1] * scale)
            val expectedEnd = Offset(
                median.last()[0] * scale,
                median.last()[1] * scale,
            )
            val nearStart = (start - expectedStart).getDistance() < tolerance
            val nearEnd = (end - expectedEnd).getDistance() < tolerance
            if (nearStart && nearEnd) {
                used += i
                matched += 1
                break
            }
        }
    }
    return matched
}

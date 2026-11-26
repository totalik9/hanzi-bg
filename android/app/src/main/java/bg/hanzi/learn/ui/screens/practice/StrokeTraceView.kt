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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import bg.hanzi.learn.data.content.CharacterEntry

/**
 * The name the trace canvas is known by.
 *
 * The canvas draws a character and has no text of its own, so the
 * only way to point at it -- from a test, or from a tool that plays
 * the part of a learner -- is by name.
 */
const val TRACE_CANVAS_DESCRIPTION = "канавка за писане"

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
    /**
     * Bumped by the caller to throw the drawn strokes away.
     *
     * There was no way to erase a stroke before, and the scoring
     * matches the strokes BY POSITION: one stroke drawn in the wrong
     * place shifts every later stroke by one, and the character can
     * never be scored right again. The learner had no way out.
     */
    clearToken: Int = 0,
    onProgress: (drawn: Int, total: Int) -> Unit = { _, _ -> },
) {
    val medians = remember(character.medians) { parseMedians(character.medians) }
    // The points the learner has drawn so far, as a list of strokes.
    // The list is remembered by the clear token as well: when the
    // token changes, the list is new and empty, and the strokes are
    // gone.
    val drawnPaths = remember(character.medians, clearToken) {
        mutableStateListOf<List<Offset>>()
    }
    var currentStroke by remember(clearToken) { mutableStateOf<List<Offset>>(emptyList()) }

    // The strokes the learner has completed correctly. The medians live
    // in the 1024x1024 space and the learner's points are in canvas
    // pixels, so the two are compared through a factor that is only
    // known inside the Canvas.
    var traceScale by remember { mutableStateOf(1f) }
    val completed = remember(drawnPaths.toList(), traceScale) {
        countMatchingStrokes(
            medians = medians,
            drawn = drawnPaths.map { stroke -> stroke.map { TracePoint(it.x, it.y) } },
            scale = traceScale,
        )
    }
    val total = medians.size

    Box(
        modifier = modifier.aspectRatio(1f),
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                // The canvas is found by this name: it is the one
                // thing on the card that has no text, and a learner
                // (or a test) needs a way to point at it.
                .semantics { contentDescription = TRACE_CANVAS_DESCRIPTION }
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
            // The scoring compares the learner's points with the medians,
            // so it needs the same factor the drawing uses.
            traceScale = scale
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


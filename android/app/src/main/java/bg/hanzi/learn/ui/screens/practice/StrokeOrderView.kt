package bg.hanzi.learn.ui.screens.practice

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import bg.hanzi.learn.data.content.CharacterEntry
import kotlinx.serialization.json.float
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

/**
 * Draws a character stroke by stroke.
 *
 * The stroke data are the MEDIANS from Make Me a Hanzi: the centre-line
 * of each stroke, as a list of points in a 1024x1024 coordinate system.
 * Drawing them one after another shows the learner the correct ORDER of
 * the strokes, which is the thing that has to be learned -- the shape of
 * the character is only a by-product of writing it in order.
 *
 * @param strokes how many strokes to draw; the rest are shown faintly.
 * @param animate whether the strokes appear one by one.
 */
@Composable
fun StrokeOrderView(
    character: CharacterEntry,
    strokes: Int,
    modifier: Modifier = Modifier,
    animate: Boolean = true,
) {
    val medians = remember(character.medians) { parseMedians(character.medians) }
    val target = if (animate) strokes.coerceAtMost(medians.size) else medians.size

    val progress = animateFloatAsState(
        targetValue = target.toFloat(),
        animationSpec = tween(durationMillis = 350 * medians.size.coerceAtLeast(1)),
        label = "strokeProgress",
    )

    val drawn = progress.value
    val active = MaterialTheme.colorScheme.primary
    val pending = MaterialTheme.colorScheme.outlineVariant

    Box(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(1f),
    ) {
        Canvas(modifier = Modifier.fillMaxWidth().aspectRatio(1f)) {
            val scale = size.width / 1024f
            fun point(p: List<Float>) = Offset(p[0] * scale, p[1] * scale)

            medians.forEachIndexed { index, median ->
                if (median.size < 2) return@forEachIndexed
                val path = Path().apply {
                    moveTo(point(median[0]).x, point(median[0]).y)
                    median.drop(1).forEach { p ->
                        lineTo(point(p).x, point(p).y)
                    }
                }
                val isDrawn = index < drawn
                val isCurrent = index < drawn && index >= drawn - 1
                drawPath(
                    path = path,
                    color = if (isDrawn) active else pending,
                    style = Stroke(
                        width = if (isCurrent) 22f else 14f,
                        cap = StrokeCap.Round,
                    ),
                    alpha = if (isDrawn) 1f else 0.35f,
                )
            }
        }
    }
}

/**
 * Parse the JSON median data into lists of [x, y] pairs.
 *
 * The data come from the pipeline as a JSON string, so they are parsed
 * once per character and remembered.
 */
private fun parseMedians(json: String): List<List<List<Float>>> {
    if (json.isBlank()) return emptyList()
    return runCatching {
        val root = kotlinx.serialization.json.Json.parseToJsonElement(json)
        root.jsonArray.mapNotNull { stroke ->
            stroke.jsonArray.mapNotNull { point ->
                val pair = point.jsonArray
                if (pair.size >= 2) {
                    listOf(
                        pair[0].jsonPrimitive.float,
                        pair[1].jsonPrimitive.float,
                    )
                } else {
                    null
                }
            }.takeIf { it.size >= 2 }
        }
    }.getOrElse { emptyList() }
}

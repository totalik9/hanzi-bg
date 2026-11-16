package bg.hanzi.learn.ui.screens.practice

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.CharacterEntry
import bg.hanzi.learn.ui.theme.LangType

/**
 * The writing step of a lesson.
 *
 * It shows the character and asks the learner to trace it. The stroke
 * order and the tracing are the ones the practice mode already owns --
 * the lesson reuses them instead of drawing a second, worse version.
 *
 * A word of the lesson may be more than one character, so the step
 * goes through the characters one by one.
 *
 * @param hanzi the word to write
 * @param characters the characters of the word, with their stroke data
 * @param onDone called when every character has been traced
 */
@Composable
fun WritingStepContent(
    hanzi: String,
    pinyin: String,
    characters: List<CharacterEntry>,
    answered: Boolean = false,
    onDone: () -> Unit,
    onNext: () -> Unit = onDone,
) {
    var charIndex by remember(hanzi) { mutableStateOf(0) }
    var traced by remember(hanzi) { mutableStateOf(0) }
    var tracedTotal by remember(hanzi) { mutableStateOf(0) }
    var finishedChars by remember(hanzi) { mutableStateOf(0) }

    val current = characters.getOrNull(charIndex)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(R.string.lesson_step_write),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(12.dp))
        Text(
            text = hanzi,
            style = LangType.scaled(
                MaterialTheme.typography.displayMedium,
                LangType.Kind.TARGET,
            ),
            textAlign = TextAlign.Center,
        )
        if (pinyin.isNotBlank()) {
            Text(
                text = pinyin,
                style = LangType.scaled(
                    MaterialTheme.typography.headlineSmall,
                    LangType.Kind.TRANSLITERATION,
                ),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (current == null) {
            // No stroke data for this character: the learner cannot
            // trace what the app cannot draw, so the step is skipped
            // rather than shown as an empty canvas.
            Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.lesson_continue))
            }
            return@Column
        }

        Spacer(modifier = Modifier.height(16.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = stringResource(R.string.lesson_stroke_order, current.strokes),
                    style = MaterialTheme.typography.labelMedium,
                )
                StrokeOrderView(
                    character = current,
                    strokes = current.strokes,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = stringResource(R.string.lesson_trace_hint),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                StrokeTraceView(
                    character = current,
                    modifier = Modifier.fillMaxWidth(),
                    onProgress = { drawn, total ->
                        traced = drawn
                        tracedTotal = total
                    },
                )
                Text(
                    text = if (tracedTotal > 0) {
                        stringResource(R.string.lesson_strokes_ok, traced, tracedTotal)
                    } else {
                        stringResource(R.string.lesson_trace_start)
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (charIndex > 0 && !answered) {
                TextButton(
                    onClick = {
                        charIndex--
                        traced = 0
                        tracedTotal = 0
                    },
                ) {
                    Text(stringResource(R.string.lesson_previous_character))
                }
            }
            Button(
                onClick = {
                    if (answered) {
                        // The character was traced: the step is done and
                        // the lesson moves on.
                        onNext()
                    } else if (charIndex < characters.lastIndex) {
                        charIndex++
                        traced = 0
                        tracedTotal = 0
                        finishedChars++
                    } else {
                        onDone()
                    }
                },
                modifier = Modifier.weight(1f),
            ) {
                Text(
                    when {
                        answered -> stringResource(R.string.lesson_continue)
                        charIndex < characters.lastIndex ->
                            stringResource(R.string.lesson_next_character)
                        else -> stringResource(R.string.lesson_finish_writing)
                    },
                )
            }
        }
    }
}

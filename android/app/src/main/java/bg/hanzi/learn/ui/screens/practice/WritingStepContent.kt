package bg.hanzi.learn.ui.screens.practice

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
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
 * @param gloss the meaning of the word, in the learner's language
 * @param characters the characters of the word, with their stroke data
 * @param onDone called when every character has been traced. It is
 *   called with the number of characters whose strokes were traced
 *   CORRECTLY, so the lesson can score the writing: a learner who
 *   presses "Готово" without drawing anything earns nothing.
 * @param onNext called when the learner moves on to the next card
 */
@Composable
fun WritingStepContent(
    hanzi: String,
    pinyin: String,
    characters: List<CharacterEntry>,
    gloss: String = "",
    answered: Boolean = false,
    onDone: (writtenCorrectly: Int) -> Unit,
    onNext: () -> Unit = { onDone(0) },
) {
    var charIndex by remember(hanzi) { mutableStateOf(0) }
    /**
     * Bumped when the learner erases the strokes of the character.
     *
     * The canvas takes it as a key, so a new value means a new and
     * empty canvas.
     */
    var clearToken by remember(hanzi) { mutableStateOf(0) }
    // How many strokes the CURRENT character has, and how many it has
    // in total. They are keyed by the character, so moving to the next
    // character of the same word does not throw away the work on the
    // one before it -- the learner who goes back sees the strokes they
    // had already drawn.
    val tracedByChar = remember(hanzi) { mutableStateMapOf<Int, Pair<Int, Int>>() }
    val traced = tracedByChar[charIndex]?.first ?: 0
    val tracedTotal = tracedByChar[charIndex]?.second ?: 0
    // How many characters were traced correctly. A character counts
    // when every one of its strokes was drawn in the right order.
    var writtenCorrectly by remember(hanzi) { mutableStateOf(0) }
    // The characters that have already been counted. Without this, a
    // learner who goes back to a character and presses the button
    // again would have it counted twice.
    val counted = remember(hanzi) { mutableStateMapOf<Int, Boolean>() }

    val current = characters.getOrNull(charIndex)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // The header is one line: the step, the character and its
        // meaning. It used to be four blocks stacked on top of each
        // other, and with the two squares of the card below it the
        // whole card did not fit on a phone -- the learner had to
        // scroll to find the button that ends the character.
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.lesson_step_write),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = hanzi,
                style = LangType.target(
                    MaterialTheme.typography.headlineMedium,
                    hanzi.length,
                ),
                textAlign = TextAlign.Center,
            )
        }
        if (pinyin.isNotBlank()) {
            Text(
                text = pinyin,
                style = LangType.scaled(
                    MaterialTheme.typography.bodyLarge,
                    LangType.Kind.TRANSLITERATION,
                ),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        // The word behind the character, so the learner writes a word
        // and not a shape.
        if (gloss.isNotBlank()) {
            Text(
                text = gloss,
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
            )
        }

        if (current == null) {
            // No stroke data for this character: the learner cannot
            // trace what the app cannot draw, so the step is skipped
            // rather than shown as an empty canvas. Nothing was
            // written, so nothing is scored.
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = { onDone(0) }, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.lesson_continue))
            }
            return@Column
        }

        Spacer(modifier = Modifier.height(8.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(12.dp)) {
                // The stroke order and the trace canvas side by side.
                //
                // They were one on top of the other, each a square
                // that filled the width, so the card was two screens
                // tall. Beside each other they are one screen, and
                // the learner sees the order and the outline at the
                // same time -- which is the point of the card.
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Column(
                        modifier = Modifier.weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            text = stringResource(R.string.lesson_stroke_order, current.strokes),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        StrokeOrderView(
                            character = current,
                            strokes = current.strokes,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    Column(
                        modifier = Modifier.weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            text = stringResource(R.string.lesson_trace_hint),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        StrokeTraceView(
                            character = current,
                            modifier = Modifier.fillMaxWidth(),
                            clearToken = clearToken,
                            onProgress = { drawn, total ->
                                tracedByChar[charIndex] = drawn to total
                            },
                        )
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = if (tracedTotal > 0) {
                            stringResource(R.string.lesson_strokes_ok, traced, tracedTotal)
                        } else {
                            stringResource(R.string.lesson_trace_start)
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f),
                    )
                    // The strokes can be erased. Without this a learner
                    // who drew one stroke in the wrong place could not
                    // finish the character: the scoring matches the
                    // strokes by position, so one stray stroke shifted
                    // all the others.
                    TextButton(onClick = { clearToken++ }) {
                        Text(stringResource(R.string.lesson_trace_clear))
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (charIndex > 0 && !answered) {
                TextButton(
                    onClick = {
                        // The strokes of the character the learner goes
                        // back to are still there: they are kept per
                        // character.
                        charIndex--
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
                        // The character counts only when every one of
                        // its strokes was drawn correctly -- and only
                        // the first time it is confirmed.
                        val correct = tracedTotal > 0 && traced == tracedTotal
                        if (correct && counted[charIndex] != true) {
                            counted[charIndex] = true
                            writtenCorrectly++
                        }
                        charIndex++
                    } else {
                        // The last character: the count has to include
                        // it, because the learner has not pressed the
                        // button for it yet.
                        val lastCorrect = tracedTotal > 0 && traced == tracedTotal
                        val already = counted[charIndex] == true
                        if (lastCorrect && !already) {
                            counted[charIndex] = true
                            onDone(writtenCorrectly + 1)
                        } else {
                            onDone(writtenCorrectly)
                        }
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

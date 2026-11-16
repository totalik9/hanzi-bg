package bg.hanzi.learn.ui.lesson

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.R
import bg.hanzi.learn.ui.theme.LangType

/**
 * One lesson of the learning path.
 *
 * The screen shows one thing at a time and asks for one thing at a
 * time. A beginner who is shown the word, its pinyin, its meaning, its
 * audio and a question at the same time is looking at five things; a
 * beginner who is shown the word and asked "what does it mean" is
 * looking at one.
 */
@Composable
fun LessonScreen(
    lessonKey: String,
    onFinished: (Boolean) -> Unit,
    viewModel: LessonViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(lessonKey) {
        viewModel.start(lessonKey)
    }

    if (state.loading) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    if (state.finished) {
        LessonResult(
            state = state,
            onContinue = { onFinished(state.passed) },
        )
        return
    }

    Column(modifier = Modifier.fillMaxSize()) {
        LessonHeader(
            title = state.lessonTitle,
            unitTitle = state.unitTitle,
            position = state.position,
            cardCount = state.cardCount,
            progress = state.progress,
        )

        val card = state.card
        if (card == null) {
            // A reading lesson: it has cards of its own.
            ReadingLesson(
                cards = viewModel.teachCards,
                onPlay = viewModel::playTeachAudio,
                onProgress = { index ->
                    // The header counter follows the card, so the
                    // learner sees how far into the lesson they are.
                    viewModel.setReadingPosition(index + 1)
                },
                onFinish = viewModel::finishReading,
            )
            return
        }

        when (card.step) {
            LessonStep.LISTEN -> ListenStep(
                hanzi = card.word.hanzi,
                pinyin = card.word.pinyin,
                hasAudio = !card.word.audio.isNullOrBlank(),
                onPlay = { viewModel.playAudio(card.word) },
                onNext = viewModel::next,
            )

            LessonStep.RECOGNISE -> RecogniseStep(
                hanzi = card.word.hanzi,
                pinyin = card.word.pinyin,
                options = card.options,
                correctIndex = card.correctIndex,
                answered = state.answered,
                correct = state.correct,
                onAnswer = viewModel::answer,
                onNext = viewModel::next,
            )

            LessonStep.SAY -> SayStep(
                hanzi = card.word.hanzi,
                pinyin = card.word.pinyin,
                gloss = card.word.glossBg.ifBlank { card.word.glossEn },
                hasAudio = !card.word.audio.isNullOrBlank(),
                onPlay = { viewModel.playAudio(card.word) },
                onNext = viewModel::next,
            )

            LessonStep.WRITE -> WriteStep(
                hanzi = card.word.hanzi,
                pinyin = card.word.pinyin,
                characters = card.characters,
                answered = state.answered,
                onDone = viewModel::onWritingDone,
                onNext = viewModel::next,
            )

            LessonStep.REVIEW -> ReviewStep(
                position = state.position,
                cardCount = state.cardCount,
            )
        }
    }
}

@Composable
private fun LessonHeader(
    title: String,
    unitTitle: String,
    position: Int,
    cardCount: Int,
    progress: Float,
) {
    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
        if (unitTitle.isNotBlank()) {
            Text(
                text = unitTitle,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(text = title, style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.height(8.dp))
        LinearProgressIndicator(
            progress = { progress.coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
        )
        if (cardCount > 0) {
            Text(
                text = "$position от $cardCount",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun ListenStep(
    hanzi: String,
    pinyin: String,
    hasAudio: Boolean,
    onPlay: () -> Unit,
    onNext: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "1. Чуй",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(24.dp))
        Text(
            text = hanzi,
            style = LangType.scaled(
                MaterialTheme.typography.displayLarge,
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
        Spacer(modifier = Modifier.height(32.dp))
        FilledTonalButton(onClick = onPlay, enabled = hasAudio) {
            Text("🔊 " + stringResource(R.string.lesson_listen))
        }
        Spacer(modifier = Modifier.height(32.dp))
        Button(onClick = onNext, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.lesson_next_word))
        }
    }
}

@Composable
private fun RecogniseStep(
    hanzi: String,
    pinyin: String,
    options: List<String>,
    correctIndex: Int,
    answered: Boolean,
    correct: Boolean,
    onAnswer: (Int) -> Unit,
    onNext: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(16.dp))
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
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.lesson_what_means),
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(modifier = Modifier.height(16.dp))

        options.forEachIndexed { index, option ->
            // The right answer is the one the card says it is, not the
            // first option that happens to have the same text: two
            // words can share a meaning.
            val isRight = index == correctIndex
            AnswerOption(
                text = option,
                state = when {
                    !answered -> AnswerState.NONE
                    correct && isRight -> AnswerState.RIGHT
                    answered -> AnswerState.WRONG
                    else -> AnswerState.NONE
                },
                enabled = !answered,
                onClick = { onAnswer(index) },
            )
            Spacer(modifier = Modifier.height(8.dp))
        }

        Spacer(modifier = Modifier.weight(1f))

        if (answered) {
            Text(
                text = if (correct) {
                    stringResource(R.string.lesson_right)
                } else {
                    stringResource(R.string.lesson_wrong)
                },
                style = MaterialTheme.typography.titleLarge,
                color = if (correct) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.error
                },
            )
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = onNext, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.lesson_continue))
            }
        }
    }
}

/** How an answer option is drawn after the learner has answered. */
private enum class AnswerState { NONE, RIGHT, WRONG }

@Composable
private fun AnswerOption(
    text: String,
    state: AnswerState,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val colors = when (state) {
        AnswerState.RIGHT -> CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        )
        AnswerState.WRONG -> CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        )
        AnswerState.NONE -> CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        )
    }
    Card(
        colors = colors,
        modifier = Modifier.fillMaxWidth(),
    ) {
        OutlinedButton(
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(text = text, style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun SayStep(
    hanzi: String,
    pinyin: String,
    gloss: String,
    hasAudio: Boolean,
    onPlay: () -> Unit,
    onNext: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "3. Произнеси",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(24.dp))
        Text(
            text = hanzi,
            style = LangType.scaled(
                MaterialTheme.typography.displayLarge,
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
        if (gloss.isNotBlank()) {
            Text(
                text = gloss,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        Spacer(modifier = Modifier.height(32.dp))
        FilledTonalButton(onClick = onPlay, enabled = hasAudio) {
            Text("🔊 " + stringResource(R.string.lesson_listen))
        }
        Text(
            text = stringResource(R.string.lesson_say_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 12.dp),
        )
        Spacer(modifier = Modifier.height(32.dp))
        Button(onClick = onNext, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.lesson_next_word))
        }
    }
}

@Composable
private fun WriteStep(
    hanzi: String,
    pinyin: String,
    characters: List<bg.hanzi.learn.data.content.CharacterEntry>,
    answered: Boolean,
    onDone: () -> Unit,
    onNext: () -> Unit,
) {
    // The writing step is a full-screen exercise with its own canvas;
    // it is rendered by the practice package, which already owns the
    // stroke-order drawing and the finger tracing.
    bg.hanzi.learn.ui.screens.practice.WritingStepContent(
        hanzi = hanzi,
        pinyin = pinyin,
        characters = characters,
        answered = answered,
        onDone = onDone,
        onNext = onNext,
    )
}

@Composable
private fun ReviewStep(position: Int, cardCount: Int) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = stringResource(R.string.lesson_review_progress, position, cardCount),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun LessonResult(
    state: LessonUiState,
    onContinue: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = if (state.passed) {
                stringResource(R.string.lesson_result_passed)
            } else {
                stringResource(R.string.lesson_result_failed)
            },
            style = MaterialTheme.typography.headlineMedium,
            textAlign = TextAlign.Center,
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "${state.score}%",
            style = MaterialTheme.typography.displayMedium,
            color = if (state.passed) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.error
            },
        )
        Text(
            text = "${state.correctCount} от ${state.answeredCount} верни",
            style = MaterialTheme.typography.bodyLarge,
        )
        if (state.productionUnlocked) {
            Spacer(modifier = Modifier.height(24.dp))
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                ),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.lesson_production_unlocked),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = stringResource(R.string.lesson_production_hint),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
        Spacer(modifier = Modifier.height(32.dp))
        Button(onClick = onContinue, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.lesson_back_to_path))
        }
    }
}

/**
 * A reading lesson: the cards that teach the sound system.
 *
 * The card is shown one at a time, and the learner moves on when they
 * are ready. There is no right answer to give, so there is nothing to
 * score.
 */
@Composable
private fun ReadingLesson(
    cards: List<String>,
    onPlay: (String) -> Unit,
    onProgress: (Int) -> Unit,
    onFinish: () -> Unit,
) {
    var index by remember { mutableStateOf(0) }
    val payload = cards.getOrNull(index)

    LaunchedEffect(index) { onProgress(index) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text(
                text = "Урок ${index + 1} от ${cards.size}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            ReadingCard(payload = payload, onPlay = onPlay)
        }
        item {
            if (index < cards.size - 1) {
                Button(
                    onClick = { index++ },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.lesson_next_card))
                }
            } else {
                Button(
                    onClick = onFinish,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.lesson_finish_reading))
                }
            }
        }
    }
}

/**
 * One card of a reading lesson.
 *
 * The card is JSON: its kind says how it is drawn -- a text, a list of
 * examples, or a table of sounds.
 */
@Composable
private fun ReadingCard(
    payload: String?,
    onPlay: (String) -> Unit,
) {
    if (payload == null) {
        Text(
            text = stringResource(R.string.content_missing),
            style = MaterialTheme.typography.bodyMedium,
        )
        return
    }
    val card = TeachingCardParser.parse(payload)
    if (card == null) {
        Text(text = payload, style = MaterialTheme.typography.bodyMedium)
        return
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (card.title.isNotBlank()) {
            Text(text = card.title, style = MaterialTheme.typography.titleLarge)
        }
        if (card.body.isNotBlank()) {
            Text(
                text = card.body,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        card.items.forEach { item ->
            Card {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = item.hanzi,
                        style = LangType.scaled(
                            MaterialTheme.typography.headlineSmall,
                            LangType.Kind.TARGET,
                        ),
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = item.pinyin,
                            style = LangType.scaled(
                                MaterialTheme.typography.bodyMedium,
                                LangType.Kind.TRANSLITERATION,
                            ),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(text = item.text, style = MaterialTheme.typography.bodyMedium)
                    }
                    // Every example can be heard. The lesson teaches
                    // how the language sounds, so the sound has to be
                    // there and not only described.
                    androidx.compose.material3.TextButton(
                        onClick = { onPlay(item.hanzi) },
                    ) {
                        Text("🔊")
                    }
                }
            }
        }
        card.rows.forEach { row ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                row.forEach { cell ->
                    Card {
                        Text(
                            text = cell,
                            style = LangType.scaled(
                                MaterialTheme.typography.titleMedium,
                                LangType.Kind.TRANSLITERATION,
                            ),
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
            }
        }
    }
}

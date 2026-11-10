package bg.hanzi.learn.ui.screens.practice

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.ui.theme.LangType

/**
 * The practice modes.
 *
 * These exist because of a concrete finding: the A2 simulation reported
 * that 20 out of 20 students reach the vocabulary and the grammar, but
 * 0 out of 20 can PRODUCE Chinese, because the app never asks the learner
 * to produce any. The three modes below close that gap.
 */
@Composable
fun PracticeScreen(
    viewModel: PracticeViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    Column(modifier = Modifier.fillMaxSize()) {
        ModeSelector(current = state.mode, onSelect = viewModel::setMode)

        when (state.mode) {
            PracticeMode.PRODUCTION -> ProductionPanel(state, viewModel)
            PracticeMode.WORD_ORDER -> WordOrderPanel(state, viewModel)
            PracticeMode.WRITING -> WritingPanel(state, viewModel)
        }
    }
}

@Composable
private fun ModeSelector(current: PracticeMode, onSelect: (PracticeMode) -> Unit) {
    LazyRow(
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(PracticeMode.entries.toList()) { mode ->
            FilterChip(
                selected = mode == current,
                onClick = { onSelect(mode) },
                label = { Text(mode.label) },
            )
        }
    }
}

@Composable
private fun ProductionPanel(state: PracticeUiState, viewModel: PracticeViewModel) {
    val exercise = state.production
    if (exercise == null) {
        Text("Няма повече думи за упражнение.", modifier = Modifier.padding(16.dp))
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card {
            Column(Modifier.padding(16.dp)) {
                Text(
                    text = "Произнеси думата:",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = exercise.word.glossBg.ifBlank { exercise.word.glossEn },
                    style = MaterialTheme.typography.headlineSmall,
                    modifier = Modifier.padding(top = 4.dp),
                )
                Text(
                    text = "${exercise.word.hskLevel} · ${exercise.word.pos}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        OutlinedTextField(
            value = exercise.typed,
            onValueChange = viewModel::onTyped,
            label = { Text("Пиньин") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            modifier = Modifier.fillMaxWidth(),
        )

        if (exercise.candidates.isNotEmpty()) {
            Text("Възможни думи:", style = MaterialTheme.typography.labelMedium)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(exercise.candidates) { candidate ->
                    AssistChip(
                        onClick = { viewModel.onCandidatePicked(candidate) },
                        label = {
                            Column {
                                Text(
                                    text = candidate.hanzi,
                                    style = LangType.scaled(
                                        MaterialTheme.typography.titleMedium,
                                        LangType.Kind.TARGET,
                                    ),
                                )
                                Text(
                                    text = candidate.pinyin,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                        },
                    )
                }
            }
        }

        if (exercise.answered) {
            Text(
                text = if (exercise.correct) "Правилно!" else "Неправилно. Отговорът е ${exercise.word.hanzi}",
                style = MaterialTheme.typography.titleMedium,
                color = if (exercise.correct) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.error
                },
            )
            Text(
                text = "Правилен отговор: ${exercise.word.hanzi} (${exercise.word.pinyin})",
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        TextButton(onClick = viewModel::nextProduction) {
            Text("Следваща дума")
        }
        Text(
            text = "Правилни: ${state.correctCount} / ${state.totalCount}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun WordOrderPanel(state: PracticeUiState, viewModel: PracticeViewModel) {
    val exercise = state.wordOrder
    if (exercise == null) {
        Text("Няма повече изречения.", modifier = Modifier.padding(16.dp))
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Card {
            Column(Modifier.padding(16.dp)) {
                Text(
                    text = "Подреди правилно:",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = exercise.sentence.translationBg,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }

        Text("Токени:", style = MaterialTheme.typography.labelMedium)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(exercise.shuffled) { token ->
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.secondaryContainer,
                    ),
                ) {
                    Text(
                        text = token,
                        style = LangType.scaled(
                            MaterialTheme.typography.titleLarge,
                            LangType.Kind.TARGET,
                        ),
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    )
                }
            }
        }

        Text(
            text = "Правилният ред е: ${exercise.tokens.joinToString("")}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        TextButton(onClick = viewModel::nextWordOrder) {
            Text("Следващо изречение")
        }
    }
}

@Composable
private fun WritingPanel(state: PracticeUiState, viewModel: PracticeViewModel) {
    val exercise = state.writing
    if (exercise == null) {
        Text("Няма повече знаци.", modifier = Modifier.padding(16.dp))
        return
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Card {
                Column(Modifier.padding(16.dp)) {
                    Text(
                        text = "Напиши знака:",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = exercise.word.glossBg.ifBlank { exercise.word.glossEn },
                        style = MaterialTheme.typography.headlineSmall,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    Text(
                        text = "${exercise.word.pinyin} · ${exercise.word.hskLevel} ниво",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        if (exercise.character != null) {
            item {
                Column {
                    Text(
                        text = "Ред на щрихите (${exercise.character.strokes}):",
                        style = MaterialTheme.typography.labelMedium,
                    )
                    StrokeOrderView(
                        character = exercise.character,
                        strokes = exercise.character.strokes,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Отговорът е знакът, чиито щрихи се виждат отгоре.",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = viewModel::nextWriting) {
                    Text("Следващ знак")
                }
            }
        }
    }
}

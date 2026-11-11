package bg.hanzi.learn.ui.screens.review

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.stringResource
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.srs.Rating
import bg.hanzi.learn.ui.theme.LangType

@Composable
fun ReviewScreen(
    viewModel: ReviewViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val word = state.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when {
            state.loading -> Text(
                text = "…",
                style = MaterialTheme.typography.bodyMedium,
            )

            word == null -> Text(
                text = "Няма карти за преглед.",
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
            )

            else -> {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    ),
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            text = word.hanzi,
                            style = LangType.scaled(
                                MaterialTheme.typography.displayMedium,
                                LangType.Kind.TARGET,
                            ),
                            textAlign = TextAlign.Center,
                        )
                        if (word.pinyin.isNotBlank()) {
                            Text(
                                text = word.pinyin,
                                style = LangType.scaled(
                                    MaterialTheme.typography.bodyLarge,
                                    LangType.Kind.TRANSLITERATION,
                                ),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        if (word.pos.isNotBlank()) {
                            Text(
                                text = word.pos,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        if (!word.audio.isNullOrBlank()) {
                            Spacer(modifier = Modifier.height(8.dp))
                            FilledTonalButton(
                                onClick = { viewModel.playAudio(word.audio) },
                            ) {
                                Text("🔊 " + stringResource(R.string.card_play_audio))
                            }
                        }
                    }
                }

                AnimatedVisibility(visible = state.revealed) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        // Bulgarian gloss first (the learner's native language),
                        // English as a secondary anchor.
                        if (word.glossBg.isNotBlank()) {
                            Text(
                                text = word.glossBg,
                                style = MaterialTheme.typography.titleMedium,
                                textAlign = TextAlign.Center,
                            )
                            // The machine translation can be wrong, and a
                            // learner who does not know that will trust it.
                            if (!word.isHumanGloss) {
                                Text(
                                    text = stringResource(R.string.gloss_machine_note),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    textAlign = TextAlign.Center,
                                )
                            }
                        }
                        if (word.glossEn.isNotBlank()) {
                            Text(
                                text = word.glossEn,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.Center,
                            )
                        }
                    }
                }

                if (!state.revealed) {
                    Button(
                        onClick = { viewModel.reveal() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 24.dp),
                    ) {
                        Text("Покажи отговор")
                    }
                } else {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 24.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        RatingButton("Отново", Rating.AGAIN, Modifier.weight(1f), viewModel)
                        RatingButton("Трудно", Rating.HARD, Modifier.weight(1f), viewModel)
                        RatingButton("Добре", Rating.GOOD, Modifier.weight(1f), viewModel)
                        RatingButton("Лесно", Rating.EASY, Modifier.weight(1f), viewModel)
                    }
                }
            }
        }
    }
}

@Composable
private fun RatingButton(
    label: String,
    rating: Rating,
    modifier: Modifier = Modifier,
    viewModel: ReviewViewModel,
) {
    when (rating) {
        Rating.AGAIN -> OutlinedButton(
            onClick = { viewModel.grade(rating) },
            modifier = modifier,
        ) { Text(label, style = MaterialTheme.typography.labelSmall) }

        Rating.HARD -> FilledTonalButton(
            onClick = { viewModel.grade(rating) },
            modifier = modifier,
        ) { Text(label, style = MaterialTheme.typography.labelSmall) }

        Rating.GOOD -> FilledTonalButton(
            onClick = { viewModel.grade(rating) },
            modifier = modifier,
        ) { Text(label, style = MaterialTheme.typography.labelSmall) }

        Rating.EASY -> Button(
            onClick = { viewModel.grade(rating) },
            modifier = modifier,
        ) { Text(label, style = MaterialTheme.typography.labelSmall) }
    }
}

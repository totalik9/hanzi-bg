package bg.hanzi.learn.ui.screens.levels

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.LevelSelection
import bg.hanzi.learn.ui.theme.LangType

/**
 * The level picker.
 *
 * It used to be on the Home screen. When the Path screen replaced that
 * screen the picker went with it, and the review and the practice
 * screens were left with a hard-coded level -- so 95 % of the
 * vocabulary (HSK 3 to HSK 9) could not be reached at all, even
 * though it was in the database and in the APK.
 *
 * The screen asks the learner which level they want to work with and
 * sends them on to the review or the practice exercises.
 */
@Composable
fun LevelPickerScreen(
    onOpenReview: (String) -> Unit,
    onOpenPractice: (String) -> Unit,
    viewModel: LevelPickerViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.levels_title),
            style = MaterialTheme.typography.titleLarge,
        )
        Text(
            text = stringResource(R.string.levels_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        state.levels.forEach { level ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.levels_level, level.label),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = pluralStringResource(
                            R.plurals.levels_word_count,
                            level.wordCount,
                            level.wordCount,
                        ),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (!level.hasAudio) {
                        Text(
                            text = stringResource(R.string.levels_no_audio),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Button(
                            onClick = { onOpenPractice(level.id) },
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(stringResource(R.string.levels_practice))
                        }
                        TextButton(
                            onClick = { onOpenReview(level.id) },
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(stringResource(R.string.levels_review))
                        }
                    }
                }
            }
        }
    }
}

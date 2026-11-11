package bg.hanzi.learn.ui.screens.dictionary

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.ui.theme.LangType

@Composable
fun DictionaryScreen(
    viewModel: DictionaryViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var query by remember { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = {
                query = it
                viewModel.search(it)
            },
            label = { Text(stringResource(R.string.dict_search_hint)) },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
        )

        // The machine translation covers 95 % of the vocabulary, but it
        // can be wrong. This switch shows only the glosses a person
        // wrote.
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = stringResource(R.string.dict_human_only),
                style = MaterialTheme.typography.bodyMedium,
            )
            Switch(
                checked = state.humanGlossesOnly,
                onCheckedChange = { viewModel.setHumanGlossesOnly(it) },
            )
        }

        if (query.isNotBlank() && state.results.isEmpty() && !state.loading) {
            Text(
                text = stringResource(R.string.dict_empty),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.results) { word ->
                WordRow(word)
            }
        }
    }
}

@Composable
private fun WordRow(word: WordEntry) {
    Card {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
        ) {
            Text(
                text = word.hanzi,
                style = LangType.scaled(
                    MaterialTheme.typography.headlineSmall,
                    LangType.Kind.TARGET,
                ),
            )
            if (word.pinyin.isNotBlank()) {
                Text(
                    text = word.pinyin,
                    style = LangType.scaled(
                        MaterialTheme.typography.bodyMedium,
                        LangType.Kind.TRANSLITERATION,
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (word.glossBg.isNotBlank()) {
                Text(
                    text = word.glossBg,
                    style = MaterialTheme.typography.bodyLarge,
                )
                if (word.hasMachineGloss) {
                    Text(
                        text = stringResource(R.string.gloss_machine_note),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (word.glossEn.isNotBlank()) {
                Text(
                    text = word.glossEn,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            val meta = listOfNotNull(
                word.pos.takeIf { it.isNotBlank() },
                word.hskLevel.takeIf { it.isNotBlank() },
            ).joinToString(" · ")
            if (meta.isNotBlank()) {
                Text(
                    text = meta,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

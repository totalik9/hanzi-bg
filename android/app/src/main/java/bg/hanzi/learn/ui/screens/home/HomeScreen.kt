package bg.hanzi.learn.ui.screens.home
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.navigation.NavController
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.LevelSelection
import bg.hanzi.learn.ui.theme.LangType

@Composable
fun HomeScreen(
    navController: NavController,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    if (state.loading) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            CircularProgressIndicator()
            Text(
                text = stringResource(R.string.content_loading),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 16.dp),
            )
        }
        return
    }

    if (!state.contentAvailable) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.content_missing),
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        return
    }

    // The levels the learner is working with. They travel to the practice
    // and review screens as a navigation argument, so those screens know
    // which part of the vocabulary they are drawing from.
    var selectedLevels by remember { mutableStateOf(LevelSelection.DEFAULT) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = stringResource(R.string.home_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = stringResource(R.string.home_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                ),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                ) {
                    Text(
                        text = stringResource(R.string.home_due_today, state.dueCount),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Button(
                        onClick = {
                            navController.navigate("review?level=$selectedLevels") {
                                launchSingleTop = true
                            }
                        },
                        modifier = Modifier.padding(top = 12.dp),
                    ) {
                        Text(
                            text = if (state.dueCount > 0) {
                                stringResource(R.string.home_continue)
                            } else {
                                stringResource(R.string.home_no_due)
                            },
                        )
                    }
                }
            }
        }

        // The daily goal and the streak. The statistics were collected
        // but never shown, so the learner had no reason to come back.
        item {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                ),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                ) {
                    Text(
                        text = stringResource(
                            R.string.home_daily_goal,
                            state.todayReviewed,
                            state.dailyGoal,
                        ),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = stringResource(R.string.home_streak, state.streakDays),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (state.dailyGoal > 0) {
                        LinearProgressIndicator(
                            progress = {
                                (state.todayReviewed.toFloat() / state.dailyGoal)
                                    .coerceIn(0f, 1f)
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 8.dp),
                        )
                    }
                }
            }
        }

        item {
            Text(
                text = stringResource(R.string.home_pick_level),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = stringResource(R.string.home_pick_level_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                state.levels.forEach { level ->
                    val isSelected = LevelSelection.levelsOf(selectedLevels).contains(level)
                    FilterChip(
                        selected = isSelected,
                        onClick = {
                            val current =
                                LevelSelection.levelsOf(selectedLevels).toMutableList()
                            if (isSelected) {
                                // Never leave the learner with nothing
                                // selected: the last chip stays on.
                                if (current.size > 1) {
                                    current.remove(level)
                                }
                            } else {
                                current.add(level)
                                current.sortBy { it.toIntOrNull() ?: Int.MAX_VALUE }
                            }
                            selectedLevels = LevelSelection.argumentFor(current)
                        },
                        label = { Text("HSK $level") },
                    )
                }
            }
        }

        items(state.levels) { level ->
            val learned = state.learnedByLevel[level] ?: 0
            val total = state.totalByLevel[level] ?: 0
            val isSelected = LevelSelection.levelsOf(selectedLevels).contains(level)
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = if (isSelected) {
                        MaterialTheme.colorScheme.secondaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    },
                ),
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                ) {
                    Text(
                        text = stringResource(R.string.home_level_label, level),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = stringResource(R.string.home_progress, learned, total),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (total > 0) {
                        LinearProgressIndicator(
                            progress = { if (total == 0) 0f else learned.toFloat() / total },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 8.dp),
                        )
                    }
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedButton(
                            onClick = {
                                navController.navigate("practice?level=$level") {
                                    launchSingleTop = true
                                }
                            },
                        ) {
                            Text(stringResource(R.string.home_practice_this_level))
                        }
                        Button(
                            onClick = {
                                navController.navigate("review?level=$level") {
                                    launchSingleTop = true
                                }
                            },
                        ) {
                            Text(stringResource(R.string.home_review_this_level))
                        }
                    }
                }
            }
        }
    }
}

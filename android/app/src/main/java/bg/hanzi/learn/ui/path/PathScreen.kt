package bg.hanzi.learn.ui.path

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.R

/**
 * The Path screen: where the learner is, and what comes next.
 *
 * The screen is built around ONE action. The old Home screen offered a
 * list of seven HSK levels and two buttons on each of them, and a
 * beginner who arrives there has to decide what to do before they can
 * do anything. Here the next lesson is the first thing on the screen
 * and the only thing that is highlighted; the path is below it, for
 * when the learner wants to see where they are.
 */
@Composable
fun PathScreen(
    onOpenLesson: (String) -> Unit,
    onOpenReview: () -> Unit,
    viewModel: PathViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    // The path is re-read every time it comes back into view: a lesson
    // that was just finished has to unlock the next one, and without
    // this the learner is sent back to a path that still shows the
    // lesson as unfinished.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.refresh()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    if (state.loading) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    if (!state.contentAvailable) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                text = stringResource(R.string.content_missing),
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(24.dp),
            )
        }
        return
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .testTag("path_list"),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Column {
                Text(
                    text = stringResource(R.string.path_subtitle),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // The one action: the next lesson.
        item {
            NextLessonCard(
                state = state,
                onOpenLesson = onOpenLesson,
                onOpenReview = onOpenReview,
            )
        }

        item {
            ProgressCard(state = state)
        }

        item {
            BadgesCard(state = state)
        }

        item {
            Text(
                text = stringResource(R.string.path_the_path),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp),
            )
        }

        items(state.units, key = { it.unit.key }) { unit ->
            UnitCard(unit = unit, onOpenLesson = onOpenLesson)
        }
    }
}

@Composable
private fun NextLessonCard(
    state: PathUiState,
    onOpenLesson: (String) -> Unit,
    onOpenReview: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        ),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            val next = state.next
            if (next == null) {
                Text(
                    text = stringResource(R.string.path_all_done),
                    style = MaterialTheme.typography.titleLarge,
                )
                Text(
                    text = stringResource(R.string.path_all_done_hint),
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Text(
                    text = stringResource(R.string.path_next_lesson),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = next.lesson.title,
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text(
                    // A reading lesson has no words; it has cards. Saying
                    // "0 думи" under a title reads as a bug, and it is
                    // one: the learner is being told the lesson is
                    // empty.
                    text = if (next.lesson.isTeach) {
                        pluralStringResource(
                            R.plurals.path_cards_count,
                            next.lesson.cards.size,
                            next.lesson.cards.size,
                        )
                    } else {
                        pluralStringResource(
                            R.plurals.path_words_count,
                            next.wordCount,
                            next.wordCount,
                        )
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = { onOpenLesson(next.lesson.key) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Filled.PlayArrow, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(stringResource(R.string.path_start_lesson))
                }
            }

            // The reviews that are due come before the new words: they
            // are what the learner is supposed to do today.
            if (state.dueCount > 0) {
                Spacer(modifier = Modifier.height(12.dp))
                androidx.compose.material3.TextButton(
                    onClick = onOpenReview,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        pluralStringResource(
                            R.plurals.path_due_reviews,
                            state.dueCount,
                            state.dueCount,
                        ),
                    )
                }
            }
        }
    }
}

@Composable
private fun ProgressCard(state: PathUiState) {
    Card {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = stringResource(R.string.path_progress),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = "${state.percent}%",
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            LinearProgressIndicator(
                progress = { (state.percent / 100f).coerceIn(0f, 1f) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )
            Spacer(modifier = Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Stat(
                    value = state.wordsLearned.toString(),
                    label = stringResource(R.string.path_words),
                )
                Stat(
                    value = state.streakDays.toString(),
                    // "1 ден поред" and "2 дни поред": one string for
                    // both read "1 дни поред".
                    label = pluralStringResource(
                        R.plurals.path_streak_days,
                        state.streakDays,
                    ),
                )
                Stat(
                    // The counter never goes past the goal: a learner
                    // who did 37 cards against a goal of 20 read
                    // "37/20", which looks broken. The goal is shown
                    // as met and the surplus is not shown at all.
                    value = if (state.todayReviewed >= state.dailyGoal) {
                        "${state.dailyGoal}/${state.dailyGoal} ✓"
                    } else {
                        "${state.todayReviewed}/${state.dailyGoal}"
                    },
                    label = stringResource(R.string.path_today),
                )
            }
        }
    }
}

@Composable
private fun Stat(value: String, label: String) {
    Column {
        Text(text = value, style = MaterialTheme.typography.titleLarge)
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun BadgesCard(state: PathUiState) {
    if (state.badges.isEmpty()) return
    Card {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.path_badges),
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(modifier = Modifier.height(8.dp))
            state.badges.forEach { badge ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(MaterialTheme.colorScheme.secondaryContainer),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            Icons.Filled.Check,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                    }
                    Spacer(modifier = Modifier.width(12.dp))
                    Column {
                        Text(text = badge.title, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            text = badge.description,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun UnitCard(
    unit: UnitView,
    onOpenLesson: (String) -> Unit,
) {
    Card {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = unit.unit.title, style = MaterialTheme.typography.titleMedium)
            Text(
                text = stringResource(R.string.path_unit_progress, unit.doneCount, unit.lessons.size),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.height(8.dp))
            unit.lessons.forEach { lesson ->
                LessonRow(lesson = lesson, onOpenLesson = onOpenLesson)
            }
        }
    }
}

@Composable
private fun LessonRow(
    lesson: LessonView,
    onOpenLesson: (String) -> Unit,
) {
    val enabled = lesson.state != PathRules.LessonState.LOCKED
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(
                    when (lesson.state) {
                        PathRules.LessonState.DONE -> MaterialTheme.colorScheme.primaryContainer
                        PathRules.LessonState.CURRENT -> MaterialTheme.colorScheme.secondaryContainer
                        PathRules.LessonState.LOCKED -> MaterialTheme.colorScheme.surfaceVariant
                    },
                ),
            contentAlignment = Alignment.Center,
        ) {
            when (lesson.state) {
                PathRules.LessonState.DONE -> Icon(
                    Icons.Filled.Check,
                    contentDescription = stringResource(R.string.path_done),
                    modifier = Modifier.size(18.dp),
                )
                PathRules.LessonState.CURRENT -> Icon(
                    Icons.Filled.PlayArrow,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                PathRules.LessonState.LOCKED -> Icon(
                    Icons.Filled.Lock,
                    contentDescription = stringResource(R.string.path_locked),
                    modifier = Modifier.size(18.dp),
                )
            }
        }
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = lesson.lesson.title,
                style = MaterialTheme.typography.bodyLarge,
                color = if (enabled) {
                    MaterialTheme.colorScheme.onSurface
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )
            Text(
                text = when (lesson.state) {
                    PathRules.LessonState.DONE ->
                        stringResource(R.string.path_lesson_score, lesson.bestScore)
                    PathRules.LessonState.CURRENT ->
                        if (lesson.lesson.isTeach) {
                            pluralStringResource(
                                R.plurals.path_cards_count,
                                lesson.lesson.cards.size,
                                lesson.lesson.cards.size,
                            )
                        } else {
                            pluralStringResource(
                                R.plurals.path_lesson_words,
                                lesson.wordCount,
                                lesson.wordCount,
                            )
                        }
                    PathRules.LessonState.LOCKED ->
                        stringResource(R.string.path_lesson_locked)
                },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (enabled) {
            androidx.compose.material3.TextButton(
                onClick = { onOpenLesson(lesson.lesson.key) },
                modifier = Modifier.testTag("lesson_${lesson.lesson.key}"),
            ) {
                Text(
                    text = if (lesson.state == PathRules.LessonState.DONE) {
                        stringResource(R.string.path_repeat)
                    } else {
                        stringResource(R.string.path_start)
                    },
                )
            }
        }
    }
}

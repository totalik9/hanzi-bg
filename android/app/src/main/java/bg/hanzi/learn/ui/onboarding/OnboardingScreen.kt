package bg.hanzi.learn.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import bg.hanzi.learn.R

/** What the learner wants Chinese for. */
enum class LearningGoal(val key: String, val titleRes: Int, val hintRes: Int) {
    HSK("hsk", R.string.onboarding_goal_hsk, R.string.onboarding_goal_hsk_hint),
    TRAVEL("travel", R.string.onboarding_goal_travel, R.string.onboarding_goal_travel_hint),
    WORK("work", R.string.onboarding_goal_work, R.string.onboarding_goal_work_hint),
    INTEREST("interest", R.string.onboarding_goal_interest, R.string.onboarding_goal_interest_hint),
}

/** How much time the learner has a day. */
enum class DailyTime(val minutes: Int, val titleRes: Int) {
    FIVE(5, R.string.onboarding_time_5),
    FIFTEEN(15, R.string.onboarding_time_15),
    THIRTY(30, R.string.onboarding_time_30),
    SIXTY(60, R.string.onboarding_time_60),
}

/**
 * The first-run questions.
 *
 * Two questions and then the first lesson. The questions are there
 * because they change what the app does -- the goal decides what the
 * learner is told they are working towards, and the time decides the
 * size of the daily goal -- but they are deliberately few: a first-run
 * flow that asks for a name, a birthday and a favourite colour is a
 * first-run flow people quit on.
 */
@Composable
fun OnboardingScreen(
    onDone: (goal: String, dailyMinutes: Int) -> Unit,
) {
    var goal by remember { mutableStateOf<LearningGoal?>(null) }
    var time by remember { mutableStateOf<DailyTime?>(null) }
    var step by remember { mutableStateOf(0) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        Spacer(modifier = Modifier.height(24.dp))
        Text(
            text = stringResource(R.string.onboarding_welcome),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = stringResource(R.string.onboarding_intro),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )

        Spacer(modifier = Modifier.height(32.dp))

        if (step == 0) {
            Text(
                text = stringResource(R.string.onboarding_goal_question),
                style = MaterialTheme.typography.titleLarge,
            )
            Spacer(modifier = Modifier.height(16.dp))
            LearningGoal.entries.forEach { option ->
                ChoiceCard(
                    title = stringResource(option.titleRes),
                    hint = stringResource(option.hintRes),
                    selected = goal == option,
                    onClick = { goal = option },
                )
                Spacer(modifier = Modifier.height(8.dp))
            }
            Spacer(modifier = Modifier.height(24.dp))
            Button(
                onClick = { step = 1 },
                enabled = goal != null,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.onboarding_next))
            }
        } else {
            Text(
                text = stringResource(R.string.onboarding_time_question),
                style = MaterialTheme.typography.titleLarge,
            )
            Spacer(modifier = Modifier.height(16.dp))
            DailyTime.entries.forEach { option ->
                ChoiceCard(
                    title = stringResource(option.titleRes),
                    hint = null,
                    selected = time == option,
                    onClick = { time = option },
                )
                Spacer(modifier = Modifier.height(8.dp))
            }
            Spacer(modifier = Modifier.height(24.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                androidx.compose.material3.OutlinedButton(
                    onClick = { step = 0 },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.onboarding_back))
                }
                Button(
                    onClick = { onDone(goal!!.key, time!!.minutes) },
                    enabled = time != null,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.onboarding_start))
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))
        Text(
            text = stringResource(R.string.onboarding_skip_hint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun ChoiceCard(
    title: String,
    hint: String?,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (selected) {
                MaterialTheme.colorScheme.secondaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
        ),
        modifier = Modifier
            .fillMaxWidth()
            .selectable(
                selected = selected,
                onClick = onClick,
                role = Role.RadioButton,
            ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            RadioButton(selected = selected, onClick = null)
            Spacer(modifier = Modifier.padding(horizontal = 8.dp))
            Column {
                Text(text = title, style = MaterialTheme.typography.bodyLarge)
                if (!hint.isNullOrBlank()) {
                    Text(
                        text = hint,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

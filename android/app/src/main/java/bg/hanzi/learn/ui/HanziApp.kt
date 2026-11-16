package bg.hanzi.learn.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import bg.hanzi.learn.ui.onboarding.OnboardingScreen
import bg.hanzi.learn.ui.path.PathViewModel

/**
 * The root of the app.
 *
 * The first launch shows the questions; after that the learner goes
 * straight to the path. The check is read from the user's own database
 * rather than a flag in the content, because the content database is
 * read-only and replaced on every update -- a flag there would ask
 * every learner the same questions again after every update.
 */
@Composable
fun HanziApp() {
    val pathViewModel: PathViewModel = hiltViewModel()
    val state by pathViewModel.uiState.collectAsStateWithLifecycle()

    when {
        state.loading -> Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator()
        }

        !state.onboarded -> OnboardingScreen(
            onDone = { goal, minutes ->
                pathViewModel.completeOnboarding(goal, minutes)
            },
        )

        else -> HanziNavHost()
    }
}

package bg.hanzi.learn.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.db.DailyStats
import bg.hanzi.learn.data.db.DailyStatsDao
import bg.hanzi.learn.data.db.SrsCardDao
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Calendar
import javax.inject.Inject

data class HomeUiState(
    val loading: Boolean = true,
    val contentAvailable: Boolean = false,
    val levels: List<String> = emptyList(),
    val totalByLevel: Map<String, Int> = emptyMap(),
    val learnedByLevel: Map<String, Int> = emptyMap(),
    val dueCount: Int = 0,
    /** How many words the learner reviewed today. */
    val todayReviewed: Int = 0,
    /** The daily goal, in reviews. */
    val dailyGoal: Int = DEFAULT_DAILY_GOAL,
    /** How many consecutive days the learner has studied. */
    val streakDays: Int = 0,
) {
    companion object {
        /**
         * The daily goal: 20 reviews a day.
         *
         * The simulation found that 20 students who reached A2 each
         * needed a steady daily habit, so the goal is set where the
         * habit can actually form.
         */
        const val DEFAULT_DAILY_GOAL = 20
    }
}

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val content: ContentRepository,
    private val srsDao: SrsCardDao,
    private val dailyStatsDao: DailyStatsDao,
) : ViewModel() {

    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val available = content.isAvailable
            val levels = content.levels()
            val totals = levels.associateWith { content.wordCount(it) }
            val learned = mutableMapOf<String, Int>()
            for (level in levels) {
                learned[level] = srsDao.learnedCount(level)
            }
            val due = srsDao.dueCount(startOfToday()).first()

            // The daily statistics. They were collected into the
            // daily_stats table but never shown, so the learner had no
            // idea how much they had done today or how long they had
            // been at it.
            val today = DailyStats.todayKey()
            val todayStats = dailyStatsDao.forDay(today).first()
            val activeDays = dailyStatsDao.activeDays().first()
            val streak = DailyStats.streak(activeDays, today)

            _uiState.value = HomeUiState(
                loading = false,
                contentAvailable = available,
                levels = levels,
                totalByLevel = totals,
                learnedByLevel = learned,
                dueCount = due,
                todayReviewed = todayStats?.reviews ?: 0,
                dailyGoal = HomeUiState.DEFAULT_DAILY_GOAL,
                streakDays = streak,
            )
        }
    }

    private fun startOfToday(): Long = Calendar.getInstance().apply {
        set(Calendar.HOUR_OF_DAY, 0)
        set(Calendar.MINUTE, 0)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
    }.timeInMillis
}

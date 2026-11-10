package bg.hanzi.learn.ui.screens.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
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
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val content: ContentRepository,
    private val srsDao: SrsCardDao,
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

            _uiState.value = HomeUiState(
                loading = false,
                contentAvailable = available,
                levels = levels,
                totalByLevel = totals,
                learnedByLevel = learned,
                dueCount = due,
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

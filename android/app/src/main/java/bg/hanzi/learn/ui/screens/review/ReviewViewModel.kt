package bg.hanzi.learn.ui.screens.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.audio.AudioPlayer
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.db.SrsCardDao
import bg.hanzi.learn.data.db.SrsCardEntity
import bg.hanzi.learn.data.srs.Rating
import bg.hanzi.learn.data.srs.SrsScheduler
import bg.hanzi.learn.data.srs.SrsState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ReviewUiState(
    val loading: Boolean = true,
    val revealed: Boolean = false,
    val current: WordEntry? = null,
)

@HiltViewModel
class ReviewViewModel @Inject constructor(
    private val content: ContentRepository,
    private val srsDao: SrsCardDao,
    private val audioPlayer: AudioPlayer,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReviewUiState())
    val uiState: StateFlow<ReviewUiState> = _uiState.asStateFlow()

    private var queue: List<WordEntry> = emptyList()
    private var index = 0

    /** Plays the pronunciation clip for a word, if one was bundled. */
    fun playAudio(filename: String) {
        if (filename.isNotBlank()) {
            audioPlayer.play("audio/$filename")
        }
    }

    init {
        loadNext()
    }

    fun reveal() {
        _uiState.value = _uiState.value.copy(revealed = true)
    }

    fun grade(rating: Rating) {
        val word = _uiState.value.current ?: return
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            val existing = srsDao.findById(word.hanzi)?.let { card ->
                SrsState(
                    dueAt = card.dueAt,
                    stability = card.stability,
                    difficulty = card.difficulty,
                    reps = card.reps,
                    lapses = card.lapses,
                    state = card.state,
                    lastReviewAt = card.lastReviewAt,
                )
            }

            val next = SrsScheduler.schedule(existing, rating, now)
            srsDao.upsert(
                SrsCardEntity(
                    itemId = word.hanzi,
                    level = word.hskLevel,
                    dueAt = next.dueAt,
                    stability = next.stability,
                    difficulty = next.difficulty,
                    reps = next.reps,
                    lapses = next.lapses,
                    state = next.state,
                    lastReviewAt = next.lastReviewAt,
                ),
            )
            advance()
        }
    }

    private fun advance() {
        index++
        if (index >= queue.size) {
            queue = emptyList()
            index = 0
            _uiState.value = ReviewUiState(loading = false, revealed = false, current = null)
        } else {
            _uiState.value = ReviewUiState(
                loading = false,
                revealed = false,
                current = queue[index],
            )
        }
    }

    private fun loadNext() {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            val due = srsDao.dueCards(now, 20)
            val dueWords = due.mapNotNull { card ->
                content.wordByHanzi(card.itemId)
            }

            if (dueWords.isNotEmpty()) {
                queue = dueWords
                index = 0
                _uiState.value = ReviewUiState(
                    loading = false,
                    revealed = false,
                    current = queue[0],
                )
                return@launch
            }

            // Nothing due — seed the session with the first level's words so
            // the learner can still study.
            val level = content.levels().firstOrNull()
            val words = if (level != null) content.wordsForLevel(level, limit = 20) else emptyList()
            queue = words
            index = 0
            _uiState.value = ReviewUiState(
                loading = false,
                revealed = false,
                current = words.firstOrNull(),
            )
        }
    }
}

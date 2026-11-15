package bg.hanzi.learn.ui.screens.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.audio.AudioPlayer
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.LevelSelection
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.db.DailyStats
import bg.hanzi.learn.data.db.DailyStatsDao
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
    /** The levels this session is drawn from, for the screen's title. */
    val levelLabel: String = "",
)

@HiltViewModel
class ReviewViewModel @Inject constructor(
    private val content: ContentRepository,
    private val srsDao: SrsCardDao,
    private val dailyStatsDao: DailyStatsDao,
    private val audioPlayer: AudioPlayer,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReviewUiState())
    val uiState: StateFlow<ReviewUiState> = _uiState.asStateFlow()

    private var queue: List<WordEntry> = emptyList()
    private var index = 0

    /**
     * The levels this session draws from.
     *
     * It used to be the first level in the database, whichever that
     * was, so the learner could never study anything but the easiest
     * 300 words. The level now comes from the navigation.
     */
    var levelSelection: String = LevelSelection.DEFAULT
        private set

    /** Plays the pronunciation clip for a word, if one was bundled. */
    fun playAudio(filename: String) {
        if (filename.isNotBlank()) {
            audioPlayer.play("audio/$filename")
        }
    }

    init {
        loadNext()
    }

    /**
     * Point the session at a set of levels and reload it.
     */
    fun setLevel(selection: String?) {
        val levels = LevelSelection.levelsOf(selection)
        if (levels == LevelSelection.levelsOf(levelSelection)) return
        levelSelection = LevelSelection.argumentFor(levels)
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

            // The daily statistics. The table existed and nothing ever
            // wrote to it, so the Home screen had nothing to show.
            val isNew = existing == null
            dailyStatsDao.recordReview(
                day = DailyStats.todayKey(now),
                reviews = 1,
                correct = if (rating == Rating.AGAIN) 0 else 1,
                newWords = if (isNew) 1 else 0,
            )

            advance()
        }
    }

    private fun advance() {
        index++
        if (index >= queue.size) {
            queue = emptyList()
            index = 0
            _uiState.value = ReviewUiState(
                loading = false,
                revealed = false,
                current = null,
                levelLabel = LevelSelection.labelOf(levelSelection),
            )
        } else {
            _uiState.value = ReviewUiState(
                loading = false,
                revealed = false,
                current = queue[index],
                levelLabel = LevelSelection.labelOf(levelSelection),
            )
        }
    }

    private fun loadNext() {
        viewModelScope.launch {
            val now = System.currentTimeMillis()
            val levels = LevelSelection.levelsOf(levelSelection)

            // The cards that are due. They come first: they are the
            // reviews the learner is supposed to do today.
            val due = srsDao.dueCards(now, ReviewDeck.SESSION_SIZE)
            val dueWords = due.mapNotNull { card ->
                content.wordByHanzi(card.itemId)
            }

            // The words the learner has already met, so the session can
            // be filled with the ones they have NOT met: the deck used
            // to offer the same first words of the level for ever, and
            // the rest of the level was unreachable from here.
            val learned = srsDao.learnedItemIds(levels).toSet()

            // How many candidates to read: at most `learned.size` of
            // them can be learned ones, so this many always holds twenty
            // that are not. The limit is a maximum, so a level smaller
            // than that simply returns all of its words.
            val candidates = ReviewDeck.SESSION_SIZE + learned.size
            val levelWords = content.wordsForLevels(levels, limit = candidates)

            val words = ReviewDeck.session(
                due = dueWords,
                levelWords = levelWords,
                learned = learned,
            )
            queue = words
            index = 0
            _uiState.value = ReviewUiState(
                loading = false,
                revealed = false,
                current = words.firstOrNull(),
                levelLabel = LevelSelection.labelOf(levelSelection),
            )
        }
    }
}

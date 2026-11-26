package bg.hanzi.learn.ui.screens.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.audio.AudioPlayer
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.ExampleEntry
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
    /**
     * The example sentence of the word being reviewed.
     *
     * It is set only when the word is one the learner has NOT met
     * yet -- a word the session injects to move them through the
     * level. A word they know does not need a context.
     */
    val example: ExampleEntry? = null,
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
     * The words the learner has already met, in every level.
     *
     * The words that are NOT in this set are the ones the session
     * injects: the new words the learner has to meet. A word that has
     * an SRS card has been met, whatever level it is on -- and a card
     * that is due for review is always a word the learner knows.
     */
    private var metWords: Set<String> = emptySet()

    /**
     * The characters the learner already knows.
     *
     * They are what says whether an example sentence can be read by
     * this learner: a sentence built of these characters is one they
     * can work the new word out of.
     */
    private var knownCharacters: Set<String> = emptySet()

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
            loadExample(queue[index])
        }
    }

    /**
     * The example sentence of a word the learner has not met yet.
     *
     * A new word cannot be guessed from its meaning alone: the learner
     * has never seen it, so the meaning tells them nothing they can
     * use. The sentence is what helps -- it is built of words they know,
     * and the new word sits in the middle of it.
     *
     * A word the learner HAS met gets no example: they know it, and a
     * sentence around it would only be noise.
     *
     * The example is picked by how much of the sentence the learner can
     * already read, so the sentence is as close as possible to the
     * words they know.
     */
    private fun loadExample(word: WordEntry) {
        if (word.hanzi in metWords) {
            _uiState.value = _uiState.value.copy(example = null)
            return
        }
        viewModelScope.launch {
            val candidates = content.examplesFor(word.hanzi)
            val example = ReviewDeck.pickExample(candidates, knownCharacters)
            // The learner may have moved on while the sentence was
            // read: the example belongs to the word that is on the
            // screen now, not to the one that was.
            if (_uiState.value.current?.hanzi == word.hanzi) {
                _uiState.value = _uiState.value.copy(example = example)
            }
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

            // The words the learner has met at all, whatever level.
            // A card that is due for review is a word they know, so it
            // gets no example sentence.
            metWords = srsDao.allLearnedItemIds().toSet()

            // The characters they know: what an example sentence is
            // measured against.
            knownCharacters = content.knownCharacters()

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
            words.firstOrNull()?.let { loadExample(it) }
        }
    }
}

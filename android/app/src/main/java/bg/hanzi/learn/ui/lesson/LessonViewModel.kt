package bg.hanzi.learn.ui.lesson

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.audio.AudioPlayer
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.CurriculumRepository
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.db.DailyStats
import bg.hanzi.learn.data.db.DailyStatsDao
import bg.hanzi.learn.data.db.LearnerSettingDao
import bg.hanzi.learn.data.db.LessonProgressDao
import bg.hanzi.learn.data.db.LessonProgressEntity
import bg.hanzi.learn.data.db.SettingKey
import bg.hanzi.learn.data.db.SrsCardDao
import bg.hanzi.learn.data.db.SrsCardEntity
import bg.hanzi.learn.data.srs.Rating
import bg.hanzi.learn.data.srs.SrsScheduler
import bg.hanzi.learn.data.srs.SrsState
import bg.hanzi.learn.ui.path.PathRules
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LessonUiState(
    val loading: Boolean = true,
    val lessonKey: String = "",
    val lessonTitle: String = "",
    val unitTitle: String = "",
    /** The card the learner is on. */
    val card: LessonCard? = null,
    /** Where the learner is: 1..cardCount. */
    val position: Int = 0,
    val cardCount: Int = 0,
    /** Whether the question of the card has been answered. */
    val answered: Boolean = false,
    /** Whether the last answer was right. */
    val correct: Boolean = false,
    /** The right answers so far. */
    val correctCount: Int = 0,
    /** The questions so far. */
    val answeredCount: Int = 0,
    /** The lesson is over and the result is shown. */
    val finished: Boolean = false,
    /** The score of the lesson, 0..100. */
    val score: Int = 0,
    /** Whether the lesson was passed. */
    val passed: Boolean = false,
    /** Whether the production exercise was opened by this lesson. */
    val productionUnlocked: Boolean = false,
    /**
     * The audio files of the words of a reading lesson, by hanzi.
     *
     * The teaching cards name their examples as text, and the app has
     * to look the pronunciation up: a lesson that teaches how Chinese
     * sounds without a way to hear it is a lesson about letters.
     *
     * The key is whatever the card names: the hanzi of an example, or
     * the clip name of a line of a passage. The value is the file name
     * under "audio/" in the APK.
     */
    val teachAudio: Map<String, String> = emptyMap(),
) {
    val progress: Float
        get() = if (cardCount == 0) 0f else position.toFloat() / cardCount
}

/**
 * Runs one lesson of the learning path.
 *
 * A lesson is a sequence of cards: the learner hears the word, picks
 * its meaning, says it, and (later) writes it; then the lesson reviews
 * the words the learner already knew. Every word the lesson teaches
 * becomes an SRS card, so the review screen has something to review
 * from the first lesson onwards.
 */
@HiltViewModel
class LessonViewModel @Inject constructor(
    private val curriculum: CurriculumRepository,
    private val content: ContentRepository,
    private val progressDao: LessonProgressDao,
    private val srsDao: SrsCardDao,
    private val dailyStatsDao: DailyStatsDao,
    private val settingsDao: LearnerSettingDao,
    private val audioPlayer: AudioPlayer,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LessonUiState())
    val uiState: StateFlow<LessonUiState> = _uiState.asStateFlow()

    private var cards: List<LessonCard> = emptyList()
    private var index = 0
    private var correct = 0
    private var answered = 0
    private var newWords: List<WordEntry> = emptyList()
    private var writingEnabled = false

    fun start(lessonKey: String) {
        if (lessonKey == _uiState.value.lessonKey && cards.isNotEmpty()) return
        viewModelScope.launch {
            val lesson = curriculum.lesson(lessonKey)
            if (lesson == null) {
                _uiState.value = LessonUiState(loading = false, lessonKey = lessonKey)
                return@launch
            }

            val unitTitle = curriculum.units()
                .firstOrNull { unit -> unit.lessons.any { it.key == lessonKey } }
                ?.title
                .orEmpty()

            val words = lesson.words.mapNotNull { content.wordByHanzi(it) }

            // The words the learner already knows: they are the review
            // at the end of the lesson.
            val learned = srsDao.allLearnedItemIds().toSet()
            val oldWords = learned
                .mapNotNull { content.wordByHanzi(it) }
                .filter { it.hanzi !in words.map { w -> w.hanzi } }

            val wordsLearned = srsDao.totalCardsOnce()
            writingEnabled = PathRules.writingEnabled(wordsLearned)

            if (lesson.isTeach) {
                // A reading lesson: it has no cards of its own, it is
                // read to the end and then it is done.
                //
                // The examples it names are looked up in the dictionary,
                // so the learner can hear every one of them: a lesson
                // that teaches how Chinese sounds without a way to hear
                // it is a lesson about letters.
                val audio = mutableMapOf<String, String>()
                lesson.cards.forEach { payload ->
                    val card = TeachingCardParser.parse(payload) ?: return@forEach
                    card.items.forEach { item ->
                        content.wordByHanzi(item.hanzi)?.audio?.takeIf { it.isNotBlank() }?.let {
                            audio[item.hanzi] = it
                        }
                    }
                    // A line of a passage names its own clip: the text is
                    // hand-written, so there is no word in the dictionary
                    // that holds it. The clip name is the key as well,
                    // because there is nothing else to look it up by.
                    card.lines.forEach { line ->
                        line.audio.takeIf { it.isNotBlank() }?.let {
                            audio[it] = it
                        }
                    }
                }
                _uiState.value = LessonUiState(
                    loading = false,
                    lessonKey = lessonKey,
                    lessonTitle = lesson.title,
                    unitTitle = unitTitle,
                    cardCount = lesson.cards.size,
                    position = 0,
                    finished = false,
                    teachAudio = audio,
                )
                teachCards = lesson.cards
                return@launch
            }

            newWords = words
            val characterData = words.associate { word ->
                word.hanzi to word.hanzi.mapNotNull { ch -> content.character(ch.toString()) }
            }
            cards = LessonPlan.cards(words, oldWords, writingEnabled, characterData)
            index = 0
            correct = 0
            answered = 0

            _uiState.value = LessonUiState(
                loading = false,
                lessonKey = lessonKey,
                lessonTitle = lesson.title,
                unitTitle = unitTitle,
                card = cards.firstOrNull(),
                position = if (cards.isEmpty()) 0 else 1,
                cardCount = cards.size,
            )
        }
    }

    /** The teaching cards of a reading lesson. */
    var teachCards: List<String> = emptyList()
        private set

    /** Plays the pronunciation clip of a word, if one was bundled. */
    fun playAudio(word: WordEntry) {
        val file = word.audio
        if (!file.isNullOrBlank()) {
            audioPlayer.play("audio/$file")
        }
    }

    /** Plays the pronunciation clip of a reading lesson's example. */
    fun playTeachAudio(hanzi: String) {
        val file = _uiState.value.teachAudio[hanzi] ?: return
        if (file.isNotBlank()) {
            audioPlayer.play("audio/$file")
        }
    }

    /**
     * Moves the counter of a reading lesson.
     *
     * A reading lesson has no cards of its own, so the counter of the
     * header would stay at zero for the whole lesson and the learner
     * would have no idea how much is left.
     */
    fun setReadingPosition(index: Int) {
        _uiState.value = _uiState.value.copy(position = index)
    }

    /**
     * Answers the current question.
     *
     * @param index the index of the chosen option
     */
    fun answer(index: Int) {
        val state = _uiState.value
        if (state.answered || state.card == null) return
        val card = state.card
        val right = card.step == LessonStep.RECOGNISE && index == card.correctIndex

        if (card.step == LessonStep.RECOGNISE) {
            answered++
            if (right) correct++
            viewModelScope.launch {
                recordAnswer(card.word, right)
            }
        }

        _uiState.value = state.copy(
            answered = true,
            correct = right,
            correctCount = correct,
            answeredCount = answered,
        )
    }

    /**
     * Moves to the next card, and finishes the lesson at the end.
     *
     * A question has to be answered before the learner moves on from
     * it. The other steps -- listening, saying, writing -- are not
     * questions, so they move on by themselves: the LISTEN step has
     * nothing to answer and it would have been a dead button.
     */
    fun next() {
        val state = _uiState.value
        val card = state.card
        if (card == null) return
        if (card.step == LessonStep.RECOGNISE && !state.answered) return

        index++
        if (index >= cards.size) {
            finish()
            return
        }
        _uiState.value = state.copy(
            card = cards[index],
            position = index + 1,
            answered = false,
            correct = false,
        )
    }

    /** Records that the writing step was traced correctly. */
    fun onWritingDone() {
        val state = _uiState.value
        if (state.answered) return
        answered++
        correct++
        _uiState.value = state.copy(
            answered = true,
            correct = true,
            correctCount = correct,
            answeredCount = answered,
        )
    }

    /** Finishes a reading lesson: it was read to the end, so it is done. */
    fun finishReading() {
        viewModelScope.launch {
            val key = _uiState.value.lessonKey
            progressDao.upsert(
                LessonProgressEntity(
                    lessonKey = key,
                    bestScore = 100,
                    attempts = 1,
                    completedAt = System.currentTimeMillis(),
                ),
            )
            _uiState.value = _uiState.value.copy(
                finished = true,
                score = 100,
                passed = true,
            )
        }
    }

    private fun finish() {
        viewModelScope.launch {
            val score = LessonPlan.score(correct, answered)
            val passed = LessonPlan.passed(score)
            val key = _uiState.value.lessonKey

            val previous = progressDao.find(key)
            progressDao.upsert(
                LessonProgressEntity(
                    lessonKey = key,
                    bestScore = maxOf(score, previous?.bestScore ?: 0),
                    attempts = (previous?.attempts ?: 0) + 1,
                    completedAt = System.currentTimeMillis(),
                ),
            )

            _uiState.value = _uiState.value.copy(
                finished = true,
                score = score,
                passed = passed,
            )
        }
    }

    /**
     * Records one answer.
     *
     * The word becomes an SRS card, so the review screen has something
     * to review from the first lesson onwards. The streak of correct
     * answers is kept, and at 20 in a row the production exercise
     * opens -- the simulation says that without it only 2 of 20
     * learners reach the vocabulary.
     */
    private suspend fun recordAnswer(word: WordEntry, right: Boolean) {
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
        val next = SrsScheduler.schedule(existing, Rating.GOOD, now)
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

        dailyStatsDao.recordReview(
            day = DailyStats.todayKey(now),
            reviews = 1,
            correct = if (right) 1 else 0,
            newWords = if (existing == null) 1 else 0,
        )

        // The streak of correct answers, and the production exercise it
        // unlocks.
        val streak = settingsDao.get(SettingKey.CORRECT_STREAK)?.toIntOrNull() ?: 0
        val newStreak = if (right) streak + 1 else 0
        settingsDao.put(
            bg.hanzi.learn.data.db.LearnerSettingEntity(
                SettingKey.CORRECT_STREAK,
                newStreak.toString(),
            ),
        )
        val alreadyUnlocked = settingsDao.get(SettingKey.PRODUCTION_UNLOCKED) == "true"
        val unlocked = PathRules.productionUnlocked(newStreak, alreadyUnlocked)
        if (unlocked && !alreadyUnlocked) {
            settingsDao.put(
                bg.hanzi.learn.data.db.LearnerSettingEntity(
                    SettingKey.PRODUCTION_UNLOCKED,
                    "true",
                ),
            )
            _uiState.value = _uiState.value.copy(productionUnlocked = true)
        }
    }
}

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
    /**
     * The option the learner picked, and -1 when the card is not
     * answered yet.
     *
     * The screen needs it to mark the answer the learner gave as
     * wrong: without it, every option was marked wrong together with
     * the right one.
     */
    val chosenIndex: Int = -1,
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
    /**
     * Whether the lesson only TAUGHT and did not test.
     *
     * It is true for the first vocabulary lesson of the path -- the one
     * with no batch before it -- and for every reading lesson. Such a
     * lesson has no question in it, so there is nothing to score: it is
     * recorded as passed with 100, and the result screen says that the
     * words were taught and will be tested later.
     */
    val taughtOnly: Boolean = false,
    /**
     * Whether the lesson is a READING lesson.
     *
     * A reading lesson teaches the sound system with cards and asks
     * nothing. It is not a vocabulary lesson that only taught: it
     * taught no new words, and the result screen says so differently.
     */
    val isReadingLesson: Boolean = false,
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
    /**
     * The characters whose strokes were traced correctly.
     *
     * The writing is worth half a point each, so it is counted apart
     * from the questions.
     */
    private var written = 0
    private var newWords: List<WordEntry> = emptyList()
    private var writingEnabled = false

    /**
     * The words of this lesson whose SRS card was already created.
     *
     * The card is created when the word is taught, and a word is
     * taught once. The set keeps the lesson from creating a second
     * card for the same word.
     */
    private val taught: MutableSet<String> = mutableSetOf()

    fun start(lessonKey: String) {
        if (lessonKey == _uiState.value.lessonKey && cards.isNotEmpty()) return
        viewModelScope.launch {
            // The path in order. The lessons come back in the order the
            // learner walks them, and the batch of a lesson is found by
            // looking at the lesson before it.
            val lessons = curriculum.lessons()
            val lesson = lessons.firstOrNull { it.key == lessonKey }
            if (lesson == null) {
                _uiState.value = LessonUiState(loading = false, lessonKey = lessonKey)
                return@launch
            }

            val unitTitle = curriculum.units()
                .firstOrNull { unit -> unit.lessons.any { it.key == lessonKey } }
                ?.title
                .orEmpty()

            val words = lesson.words.mapNotNull { content.wordByHanzi(it) }

            // The batch this lesson TESTS: the words of the previous
            // lesson that had words. A reading lesson ("teach") carries
            // no words, so it is skipped and the batch of the lesson
            // before it is tested again.
            val testWords = LessonBatch.testBatch(lessons, lessonKey)
                .mapNotNull { content.wordByHanzi(it) }

            // The words the learner already knows: they are the pool the
            // distractors are drawn from. They are not cards of the
            // lesson any more -- the test of the lesson is the previous
            // batch.
            val learned = srsDao.allLearnedItemIds().toSet()
            val knownWords = learned
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
                    // A reading lesson asks nothing: it only teaches.
                    taughtOnly = true,
                    isReadingLesson = true,
                )
                teachCards = lesson.cards
                return@launch
            }

            newWords = words
            val characterData = words.associate { word ->
                word.hanzi to word.hanzi.mapNotNull { ch -> content.character(ch.toString()) }
            }

            // The example sentence of every word of the lesson, so the
            // test card can show the word inside a sentence. A word
            // without one simply has no example: the card works
            // without it.
            val examples = (words + testWords)
                .mapNotNull { word ->
                    content.examplesFor(word.hanzi).firstOrNull()
                        ?.let { word.hanzi to it }
                }
                .toMap()

            cards = LessonPlan.cards(
                words = words,
                testWords = testWords,
                writingEnabled = writingEnabled,
                characters = characterData,
                examples = examples,
                knownWords = knownWords,
            )
            index = 0
            correct = 0
            answered = 0
            written = 0

            _uiState.value = LessonUiState(
                loading = false,
                lessonKey = lessonKey,
                lessonTitle = lesson.title,
                unitTitle = unitTitle,
                card = cards.firstOrNull(),
                position = if (cards.isEmpty()) 0 else 1,
                cardCount = cards.size,
                // The first vocabulary lesson of the path has no batch
                // before it, so it teaches and does not test.
                taughtOnly = !LessonPlan.hasTestCards(cards),
            )

            // The first card is the teaching of the first word: the
            // word enters the review queue now.
            cards.firstOrNull()?.let { card ->
                if (card.step == LessonStep.LISTEN) ensureTaughtCard(card.word)
            }
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
            chosenIndex = index,
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
            chosenIndex = -1,
        )
        onCardShown(cards[index])
    }

    /**
     * The word enters the review queue when it is TAUGHT.
     *
     * The card is created here and not when the word is first
     * answered: the test of a batch happens in the NEXT lesson, and if
     * the card only appeared with the answer, the review of the next
     * morning would have nothing to review.
     *
     * The card is due at the start of tomorrow, so the daily review
     * picks the word up the next day -- the learner has met it by
     * then, and can answer a question about it.
     *
     * A word that already has a card keeps it: the learner may be
     * repeating a lesson, and a card that has been answered before
     * must not lose its history.
     */
    private suspend fun ensureTaughtCard(word: WordEntry) {
        if (!taught.add(word.hanzi)) return
        val now = System.currentTimeMillis()
        if (srsDao.findById(word.hanzi) != null) return
        srsDao.upsert(LessonBatch.taughtCard(word, now))
        // The word is a new word of the day: it is counted here and
        // not when it is answered, because the answer happens in the
        // next lesson and the card exists by then.
        dailyStatsDao.recordReview(
            day = DailyStats.todayKey(now),
            reviews = 0,
            correct = 0,
            newWords = 1,
        )
    }

    /**
     * The card the learner is on: a word that is being TAUGHT enters
     * the review queue when its LISTEN card is shown.
     */
    private fun onCardShown(card: LessonCard) {
        if (card.step != LessonStep.LISTEN) return
        viewModelScope.launch {
            ensureTaughtCard(card.word)
        }
    }

    /**
     * Records the writing step.
     *
     * The writing is worth half a point per character, and only the
     * characters whose strokes were traced correctly earn it. It used
     * to be a full point that the learner could not lose: pressing
     * "Готово" awarded it whether anything had been drawn or not.
     *
     * @param writtenCorrectly how many characters were traced correctly
     */
    fun onWritingDone(writtenCorrectly: Int) {
        val state = _uiState.value
        if (state.answered) return
        written += writtenCorrectly
        _uiState.value = state.copy(
            answered = true,
            correct = writtenCorrectly > 0,
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
            // The writing is worth half a point per character, and the
            // characters the lesson offered are part of what the lesson
            // is worth: the score cannot be above 100, and a lesson
            // without writing is not punished for it.
            val writable = cards
                .filter { it.step == LessonStep.WRITE }
                .sumOf { it.characters.size }

            // A lesson that only taught has no question in it, so there
            // is nothing to score. It is recorded as passed with 100:
            // the learner did what the lesson asked of them, and the
            // test of these words comes in the next lesson.
            val taughtOnly = !LessonPlan.hasTestCards(cards)
            val score = if (taughtOnly) {
                100
            } else {
                LessonPlan.scoreWithWriting(correct, answered, written, writable)
            }
            val passed = if (taughtOnly) true else LessonPlan.passed(score)
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
                taughtOnly = taughtOnly,
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

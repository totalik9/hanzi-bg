package bg.hanzi.learn.ui.screens.practice

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.audio.AudioPlayer
import bg.hanzi.learn.data.content.CharacterEntry
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.ImeIndex
import bg.hanzi.learn.data.content.SentenceEntry
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.ime.PinyinIme
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import javax.inject.Inject
import kotlin.random.Random

/** The five exercises the A2 simulation says are missing. */
enum class PracticeMode(val label: String) {
    PRODUCTION("Производство"),
    LISTENING("Слушане"),
    WORD_ORDER("Подреждане"),
    WRITING("Писане"),
    GRAMMAR_QUIZ("Граматика"),
}

/** A listening exercise: hear the word, pick the right one. */
data class ListeningExercise(
    val word: WordEntry,
    val options: List<WordEntry>,
    val answered: Boolean = false,
    val correct: Boolean = false,
)

/** One example that came with a grammar point. */
data class GrammarExample(
    val pointTitle: String,
    val level: String,
    val zh: String,
    val pinyin: String,
    val en: String,
)

/**
 * A grammar quiz: the learner sees a Chinese example and has to pick its
 * meaning.
 *
 * The simulation found that the grammar is REACHED by every student but
 * only as reference text -- nothing tests it. The 3 286 examples that
 * came with the grammar points are the material for that test.
 */
data class GrammarQuizExercise(
    val pointTitle: String,
    val level: String,
    val exampleZh: String,
    val examplePinyin: String,
    val options: List<String>,
    val correctAnswer: String,
    val answered: Boolean = false,
    val correct: Boolean = false,
)

/** A word-order exercise: the tokens to arrange and the right answer. */
data class WordOrderExercise(
    val sentence: SentenceEntry,
    val tokens: List<String>,
    val shuffled: List<String>,
    /** The tokens the learner has placed so far, in the order they placed them. */
    val picked: List<String> = emptyList(),
    val answered: Boolean = false,
    val correct: Boolean = false,
)

/** A production exercise: show the meaning, the learner types the pinyin. */
data class ProductionExercise(
    val word: WordEntry,
    val typed: String = "",
    val candidates: List<PinyinIme.Candidate> = emptyList(),
    val answered: Boolean = false,
    val correct: Boolean = false,
)

/** A writing exercise: a character and its stroke order. */
data class WritingExercise(
    val word: WordEntry,
    val character: CharacterEntry?,
)

data class PracticeUiState(
    val loading: Boolean = true,
    val mode: PracticeMode = PracticeMode.PRODUCTION,
    val production: ProductionExercise? = null,
    val listening: ListeningExercise? = null,
    val wordOrder: WordOrderExercise? = null,
    val writing: WritingExercise? = null,
    val grammarQuiz: GrammarQuizExercise? = null,
    val finished: Boolean = false,
    val correctCount: Int = 0,
    val totalCount: Int = 0,
)

/**
 * The practice modes the A2 simulation says the app is missing.
 *
 * The simulation is blunt about this: the vocabulary can be reached and
 * the grammar can be read, but PRODUCTION is 0/20 because nothing in the
 * app ever asks the learner to produce Chinese. These four modes are
 * the answer to that finding.
 */
@HiltViewModel
class PracticeViewModel @Inject constructor(
    private val content: ContentRepository,
    private val audioPlayer: AudioPlayer,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PracticeUiState())
    val uiState: StateFlow<PracticeUiState> = _uiState.asStateFlow()

    private var imeIndex: ImeIndex = ImeIndex(emptyMap(), emptyMap(), emptyMap())
    private var wordPool: List<WordEntry> = emptyList()
    private var sentencePool: List<SentenceEntry> = emptyList()
    // (point title, level, chinese, pinyin, english) for every example
    // that came with a grammar point.
    private var grammarExamples: List<GrammarExample> = emptyList()
    private var usedWords = mutableSetOf<String>()
    private var usedSentences = mutableSetOf<Long>()
    private val random = Random(42)

    /** Plays the pronunciation of a word. */
    fun playAudio(fileName: String) {
        if (fileName.isNotBlank()) {
            audioPlayer.play("audio/$fileName")
        }
    }

    init {
        viewModelScope.launch {
            val loaded = withContext(Dispatchers.IO) {
                val index = content.imeIndex()
                // The practice pool is the vocabulary that has a Bulgarian
                // gloss: a production exercise without a meaning to
                // produce would be guesswork.
                val words = content.wordsForLevel("1", limit = 300) +
                    content.wordsForLevel("2", limit = 200)
                val sentences = content.sentencesWithBulgarian(limit = 60)
                val examples = parseGrammarExamples(content.grammarWithExamples())
                Triple(index, words, sentences) to examples
            }
            imeIndex = loaded.first.first
            wordPool = loaded.first.second.filter { it.glossBg.isNotBlank() }
            sentencePool = loaded.first.third
            grammarExamples = loaded.second
            _uiState.value = _uiState.value.copy(loading = false)
            nextProduction()
        }
    }

    /**
     * Flatten the grammar points into a list of examples.
     *
     * The examples come from the wiki as JSON inside the grammar table.
     * They are the material for the grammar quiz: the simulation found
     * that the grammar is reached by every student but never tested.
     */
    private fun parseGrammarExamples(
        points: List<bg.hanzi.learn.data.content.GrammarEntry>,
    ): List<GrammarExample> {
        val out = mutableListOf<GrammarExample>()
        for (point in points) {
            if (point.examples.isBlank()) continue
            val parsed = runCatching {
                kotlinx.serialization.json.Json.parseToJsonElement(point.examples).jsonArray
            }.getOrNull() ?: continue
            for (element in parsed) {
                val obj = element.jsonObject
                val zh = obj["zh"]?.jsonPrimitive?.content.orEmpty()
                val pinyin = obj["pinyin"]?.jsonPrimitive?.content.orEmpty()
                val en = obj["en"]?.jsonPrimitive?.content.orEmpty()
                if (zh.isNotBlank() && en.isNotBlank()) {
                    out.add(
                        GrammarExample(
                            pointTitle = point.title,
                            level = point.level,
                            zh = zh,
                            pinyin = pinyin,
                            en = en,
                        ),
                    )
                }
            }
        }
        return out
    }

    fun setMode(mode: PracticeMode) {
        _uiState.value = _uiState.value.copy(mode = mode, finished = false)
        when (mode) {
            PracticeMode.PRODUCTION -> nextProduction()
            PracticeMode.LISTENING -> nextListening()
            PracticeMode.WORD_ORDER -> nextWordOrder()
            PracticeMode.WRITING -> nextWriting()
            PracticeMode.GRAMMAR_QUIZ -> nextGrammarQuiz()
        }
    }

    /**
     * The next grammar question.
     *
     * The learner sees a Chinese example and picks its meaning. The
     * distractors are other examples' translations, so they are about the
     * same length and equally plausible -- a distractor that is obviously
     * wrong teaches nothing.
     */
    fun nextGrammarQuiz() {
        val pool = grammarExamples.filter { it.en.isNotBlank() }
        if (pool.isEmpty()) {
            _uiState.value = _uiState.value.copy(finished = true, grammarQuiz = null)
            return
        }
        val index = random.nextInt(pool.size)
        val example = pool[index]

        val distractors = pool
            .filterIndexed { i, e -> i != index && e.en != example.en }
            .shuffled(random)
            .take(3)
            .map { it.en }
        val options = (distractors + example.en).shuffled(random)

        _uiState.value = _uiState.value.copy(
            grammarQuiz = GrammarQuizExercise(
                pointTitle = example.pointTitle,
                level = example.level,
                exampleZh = example.zh,
                examplePinyin = example.pinyin,
                options = options,
                correctAnswer = example.en,
            ),
            finished = false,
        )
    }

    /** The learner picked an answer in the grammar quiz. */
    fun onGrammarAnswer(picked: String) {
        val current = _uiState.value.grammarQuiz ?: return
        val correct = picked == current.correctAnswer
        _uiState.value = _uiState.value.copy(
            grammarQuiz = current.copy(answered = true, correct = correct),
            correctCount = _uiState.value.correctCount + if (correct) 1 else 0,
            totalCount = _uiState.value.totalCount + 1,
        )
    }

    /**
     * The next listening exercise.
     *
     * Only words that HAVE a pronunciation clip can be used, otherwise
     * the exercise would ask the learner to listen to silence. The three
     * distractors are drawn from the same pool, so they are equally
     * likely to be familiar.
     */
    fun nextListening() {
        val pool = wordPool.filter { it.audio != null && it.hanzi !in usedWords }
        if (pool.isEmpty()) {
            _uiState.value = _uiState.value.copy(finished = true, listening = null)
            return
        }
        val word = pool[random.nextInt(pool.size)]
        usedWords += word.hanzi

        val distractors = wordPool
            .filter { it.hanzi != word.hanzi && it.hanzi !in usedWords }
            .shuffled(random)
            .take(3)
        val options = (distractors + word).shuffled(random)

        _uiState.value = _uiState.value.copy(
            listening = ListeningExercise(word = word, options = options),
            finished = false,
        )
    }

    /** The learner picked an option in the listening exercise. */
    fun onListeningAnswer(picked: WordEntry) {
        val current = _uiState.value.listening ?: return
        val correct = picked.hanzi == current.word.hanzi
        _uiState.value = _uiState.value.copy(
            listening = current.copy(answered = true, correct = correct),
            correctCount = _uiState.value.correctCount + if (correct) 1 else 0,
            totalCount = _uiState.value.totalCount + 1,
        )
    }

    /** The learner typed pinyin; refresh the candidates. */
    fun onTyped(text: String) {
        val current = _uiState.value.production ?: return
        val candidates = PinyinIme.candidates(
            typed = text,
            syllableToWords = imeIndex.syllableToWords,
            wordToPinyin = imeIndex.wordToPinyin,
            wordToGloss = imeIndex.wordToGloss,
        )
        _uiState.value = _uiState.value.copy(
            production = current.copy(typed = text, candidates = candidates),
        )
    }

    /** The learner picked a candidate. */
    fun onCandidatePicked(candidate: PinyinIme.Candidate) {
        val current = _uiState.value.production ?: return
        val correct = candidate.hanzi == current.word.hanzi
        _uiState.value = _uiState.value.copy(
            production = current.copy(
                typed = candidate.hanzi,
                candidates = emptyList(),
                answered = true,
                correct = correct,
            ),
            correctCount = _uiState.value.correctCount + if (correct) 1 else 0,
            totalCount = _uiState.value.totalCount + 1,
        )
    }

    fun nextProduction() {
        val pool = wordPool.filter { it.hanzi !in usedWords }
        if (pool.isEmpty()) {
            _uiState.value = _uiState.value.copy(finished = true, production = null)
            return
        }
        val word = pool[random.nextInt(pool.size)]
        usedWords += word.hanzi
        _uiState.value = _uiState.value.copy(
            production = ProductionExercise(word = word),
            finished = false,
        )
    }

    /**
     * The learner picked a token for the word-order answer.
     *
     * Tapping a token in the tray appends it to the answer; tapping a
     * token in the answer removes it again. The exercise is SCORED: the
     * simulation named "word order must be scored, not just displayed"
     * as a gap.
     */
    fun onWordOrderPick(token: String) {
        val current = _uiState.value.wordOrder ?: return
        if (current.answered) return
        if (current.picked.count { it == token } >= current.shuffled.count { it == token }) {
            // That token is already used up.
            return
        }
        _uiState.value = _uiState.value.copy(
            wordOrder = current.copy(picked = current.picked + token),
        )
    }

    /** The learner removed a token from the answer. */
    fun onWordOrderRemove(index: Int) {
        val current = _uiState.value.wordOrder ?: return
        if (current.answered) return
        _uiState.value = _uiState.value.copy(
            wordOrder = current.copy(picked = current.picked.filterIndexed { i, _ -> i != index }),
        )
    }

    /** The learner submitted the word-order answer. */
    fun onWordOrderSubmit() {
        val current = _uiState.value.wordOrder ?: return
        if (current.answered || current.picked.isEmpty()) return
        val correct = current.picked == current.tokens
        _uiState.value = _uiState.value.copy(
            wordOrder = current.copy(answered = true, correct = correct),
            correctCount = _uiState.value.correctCount + if (correct) 1 else 0,
            totalCount = _uiState.value.totalCount + 1,
        )
    }

    fun nextWordOrder() {
        val pool = sentencePool.filter { it.id !in usedSentences }
        if (pool.isEmpty()) {
            _uiState.value = _uiState.value.copy(finished = true, wordOrder = null)
            return
        }
        val sentence = pool[random.nextInt(pool.size)]
        usedSentences += sentence.id

        // Split the Chinese sentence into its words. The Tatoeba corpus
        // does not segment, so the sentence is split on the characters
        // that CC-CEDICT knows as words -- a single character is a word
        // too often in Chinese for this to be simple.
        val tokens = segment(sentence.hanzi)
        _uiState.value = _uiState.value.copy(
            wordOrder = WordOrderExercise(
                sentence = sentence,
                tokens = tokens,
                shuffled = tokens.shuffled(random),
            ),
            finished = false,
        )
    }

    fun nextWriting() {
        val pool = wordPool.filter {
            it.hanzi.length == 1 && it.hanzi !in usedWords
        }
        if (pool.isEmpty()) {
            _uiState.value = _uiState.value.copy(finished = true, writing = null)
            return
        }
        val word = pool[random.nextInt(pool.size)]
        usedWords += word.hanzi
        viewModelScope.launch {
            val character = withContext(Dispatchers.IO) { content.character(word.hanzi) }
            _uiState.value = _uiState.value.copy(
                writing = WritingExercise(word = word, character = character),
                finished = false,
            )
        }
    }

    /**
     * Split a Chinese sentence into words.
     *
     * The corpus carries no word boundaries. Each CJK character is its own
     * token, which is the safest split: the learner rearranges characters
     * and the answer is the character order. Word-level segmentation would
     * need a dictionary the app does not carry.
     */
    private fun segment(hanzi: String): List<String> =
        hanzi.filter { it.code in 0x4E00..0x9FFF }.map { it.toString() }
}

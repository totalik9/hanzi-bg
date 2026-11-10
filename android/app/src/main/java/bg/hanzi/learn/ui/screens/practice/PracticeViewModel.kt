package bg.hanzi.learn.ui.screens.practice

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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
import javax.inject.Inject
import kotlin.random.Random

/** The three exercises the A2 simulation says are missing. */
enum class PracticeMode(val label: String) {
    PRODUCTION("Производство"),
    WORD_ORDER("Подреждане"),
    WRITING("Писане"),
}

/** A word-order exercise: the tokens to arrange and the right answer. */
data class WordOrderExercise(
    val sentence: SentenceEntry,
    val tokens: List<String>,
    val shuffled: List<String>,
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
    val wordOrder: WordOrderExercise? = null,
    val writing: WritingExercise? = null,
    val finished: Boolean = false,
    val correctCount: Int = 0,
    val totalCount: Int = 0,
)

/**
 * The practice modes the A2 simulation says the app is missing.
 *
 * The simulation is blunt about this: the vocabulary can be reached and
 * the grammar can be read, but PRODUCTION is 0/20 because nothing in the
 * app ever asks the learner to produce Chinese. These three modes are
 * the answer to that finding.
 */
@HiltViewModel
class PracticeViewModel @Inject constructor(
    private val content: ContentRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PracticeUiState())
    val uiState: StateFlow<PracticeUiState> = _uiState.asStateFlow()

    private var imeIndex: ImeIndex = ImeIndex(emptyMap(), emptyMap(), emptyMap())
    private var wordPool: List<WordEntry> = emptyList()
    private var sentencePool: List<SentenceEntry> = emptyList()
    private var usedWords = mutableSetOf<String>()
    private var usedSentences = mutableSetOf<Long>()
    private val random = Random(42)

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
                Triple(index, words, sentences)
            }
            imeIndex = loaded.first
            wordPool = loaded.second.filter { it.glossBg.isNotBlank() }
            sentencePool = loaded.third
            _uiState.value = _uiState.value.copy(loading = false)
            nextProduction()
        }
    }

    fun setMode(mode: PracticeMode) {
        _uiState.value = _uiState.value.copy(mode = mode, finished = false)
        when (mode) {
            PracticeMode.PRODUCTION -> nextProduction()
            PracticeMode.WORD_ORDER -> nextWordOrder()
            PracticeMode.WRITING -> nextWriting()
        }
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

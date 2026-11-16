package bg.hanzi.learn.ui.lesson

import bg.hanzi.learn.data.content.CharacterEntry
import bg.hanzi.learn.data.content.WordEntry
import kotlin.random.Random

/**
 * The steps of a lesson, in the order the learner walks through them.
 *
 * The order is the teaching. It was decided with the learner, and each
 * step answers a different question:
 *
 *   LISTEN    what does it sound like?
 *   RECOGNISE what does it mean?  (the learner picks the Bulgarian
 *                                  meaning out of four)
 *   SAY       can I say it?      (the learner repeats it out loud;
 *                                  there is no microphone yet)
 *   WRITE     can I write it?    (the learner traces the strokes; this
 *                                  step joins only after 20 words)
 *
 * Then the lesson ends with a short review of what was learned before,
 * because a lesson that only adds words and never consolidates them
 * loses them.
 */
enum class LessonStep {
    LISTEN,
    RECOGNISE,
    SAY,
    WRITE,
    REVIEW,
}

/**
 * One card of a lesson: a word and the step the learner is on.
 */
data class LessonCard(
    val word: WordEntry,
    val step: LessonStep,
    /** For a RECOGNISE card: the four Bulgarian meanings. */
    val options: List<String> = emptyList(),
    /** For a RECOGNISE card: the index of the right answer. */
    val correctIndex: Int = 0,
    /**
     * For a WRITE card: the characters of the word, with their stroke
     * data. It is empty when the app has no stroke data for the word,
     * and the writing step is skipped then.
     */
    val characters: List<CharacterEntry> = emptyList(),
)

/**
 * How a lesson is put together.
 *
 * The rules are plain functions so they can be tested without a device:
 * a lesson that asks the wrong question, or one whose distractors are
 * wrong, is a lesson that teaches the wrong thing.
 */
object LessonPlan {

    /** How many meanings a RECOGNISE card offers. */
    const val OPTION_COUNT = 4

    /** How many old words the review at the end of the lesson holds. */
    const val REVIEW_SIZE = 5

    /**
     * The cards of a lesson.
     *
     * @param words the new words of the lesson, in the order they are met
     * @param oldWords the words the learner already knows, for the review
     * @param writingEnabled whether the WRITE step is in the lesson yet
     * @param characters the stroke data of the characters, by word
     * @param random the source of the distractors' order
     */
    fun cards(
        words: List<WordEntry>,
        oldWords: List<WordEntry>,
        writingEnabled: Boolean,
        characters: Map<String, List<CharacterEntry>> = emptyMap(),
        random: Random = Random.Default,
    ): List<LessonCard> {
        if (words.isEmpty()) return emptyList()

        val pool = (words + oldWords)
            .map { it.glossBg.ifBlank { it.glossEn } }
            .filter { it.isNotBlank() }
            .distinct()

        val cards = mutableListOf<LessonCard>()

        for (word in words) {
            val gloss = word.glossBg.ifBlank { word.glossEn }

            cards += LessonCard(word, LessonStep.LISTEN)

            // The distractors are the meanings of the OTHER words of the
            // lesson and of the words the learner already knows. They
            // have to be real meanings of real words: a made-up
            // distractor is a coin the learner can lose on by guessing.
            val distractors = pool
                .filter { it != gloss }
                .shuffled(random)
                .take(OPTION_COUNT - 1)
            val options = (distractors + gloss).shuffled(random)
            cards += LessonCard(
                word = word,
                step = LessonStep.RECOGNISE,
                options = options,
                correctIndex = options.indexOf(gloss),
            )

            cards += LessonCard(word, LessonStep.SAY)

            if (writingEnabled) {
                // The writing step needs the stroke data of the
                // characters. A word without them is skipped: the app
                // cannot show what it cannot draw.
                val chars = characters[word.hanzi].orEmpty()
                if (chars.isNotEmpty()) {
                    cards += LessonCard(
                        word = word,
                        step = LessonStep.WRITE,
                        characters = chars,
                    )
                }
            }
        }

        // The review: the words the learner already knows, so that the
        // lesson ends by using what it has taught and what it taught
        // before.
        val review = oldWords.shuffled(random).take(REVIEW_SIZE)
        for (word in review) {
            val gloss = word.glossBg.ifBlank { word.glossEn }
            val distractors = pool
                .filter { it != gloss }
                .shuffled(random)
                .take(OPTION_COUNT - 1)
            val options = (distractors + gloss).shuffled(random)
            cards += LessonCard(
                word = word,
                step = LessonStep.RECOGNISE,
                options = options,
                correctIndex = options.indexOf(gloss),
            )
        }

        return cards
    }

    /**
     * The score of a lesson, as a percentage.
     *
     * Only the RECOGNISE cards are counted: the LISTEN, SAY and WRITE
     * steps are not questions with a right answer. The WRITE step is
     * scored separately and counts as half a point when the strokes
     * were traced correctly, because writing a character is a different
     * skill from recognising it.
     *
     * @param correct the number of right answers
     * @param total the number of questions
     */
    fun score(correct: Int, total: Int): Int {
        if (total <= 0) return 0
        return (correct * 100) / total
    }

    /**
     * Whether the lesson is passed.
     */
    fun passed(score: Int): Boolean = score >= bg.hanzi.learn.ui.path.PathRules.PASS_SCORE
}

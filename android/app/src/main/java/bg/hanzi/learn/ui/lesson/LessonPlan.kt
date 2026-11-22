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
            val options = chooseOptions(gloss, pool, random)
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
            val options = chooseOptions(gloss, pool, random)
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
     * The meanings of a RECOGNISE card: the right one and the wrong ones.
     *
     * THE CLONE OF THE ANSWER
     *
     * Two words can carry the same meaning written differently. The
     * hand-written gloss patch writes "малко" and the machine
     * translation of another word writes "Малко" -- the same Bulgarian
     * word with a capital letter. The pool of meanings holds both,
     * because they are different strings.
     *
     * The old code removed the answer from the pool with an exact
     * comparison (`it != gloss`), so the capitalised twin SURVIVED
     * and was handed to the learner as a distractor. The card then
     * showed two options that look identical on the screen:
     *
     *     малко        <- the answer
     *     Малко        <- the "wrong" one
     *
     * The learner cannot tell them apart by looking, and the app
     * marks the one with the capital letter wrong. Fifteen cards of
     * the learning path were in this state.
     *
     * So the comparison is made the way a reader makes it: the case
     * and the surrounding spaces are ignored. A distractor that
     * reads the same as the answer is not a distractor.
     *
     * The answer itself is added LAST and exactly once, so it cannot
     * be in the list twice either.
     *
     * When the pool holds fewer meanings than the card needs -- which
     * happens when a lesson teaches four characters that all mean
     * "child" -- the card offers fewer options rather than padding
     * the list with a meaning that is not in the pool. A card with
     * three options is still a question; a card with the answer
     * twice, or with a clone of it, is not.
     *
     * @param gloss the right answer
     * @param pool every meaning the lesson can draw on
     * @param random the source of the distractors' order
     */
    fun chooseOptions(
        gloss: String,
        pool: List<String>,
        random: Random = Random.Default,
    ): List<String> {
        if (gloss.isBlank()) return emptyList()
        val answerKey = gloss.trim().lowercase()
        val distractors = pool
            .filter { it.trim().lowercase() != answerKey }
            .shuffled(random)
            .take((OPTION_COUNT - 1).coerceAtLeast(0))
        return (distractors + gloss).shuffled(random)
    }

    /**
     * The score of a lesson that has writing in it.
     *
     * The writing is worth half a point per character, and only the
     * characters whose strokes were traced correctly earn it. The
     * writing is part of what the lesson is WORTH, so it is in the
     * denominator as well as in the numerator: a learner who answers
     * every question right and traces nothing scores less than one who
     * traces everything, which is the whole point of scoring the
     * writing at all.
     *
     * A lesson WITHOUT writing is not punished for it: when there are
     * no characters to write, [writable] is zero and the score is the
     * recognition score, unchanged.
     *
     * The arithmetic is in half points, so it is done in integers: the
     * recognition is worth two per question and the writing one per
     * character.
     *
     * @param correct the right answers among the questions
     * @param total the questions
     * @param written the characters whose strokes were traced correctly
     * @param writable the characters the lesson offered to write
     */
    fun scoreWithWriting(correct: Int, total: Int, written: Int, writable: Int): Int {
        if (total <= 0 && writable <= 0) return 0
        val earned = correct * 2 + written
        val possible = total * 2 + writable
        if (possible <= 0) return 0
        // The score cannot be above 100: the writing is worth points,
        // not a bonus on top of a full score.
        return ((earned * 100) / possible).coerceIn(0, 100)
    }

    /**
     * Whether the lesson is passed.
     */
    fun passed(score: Int): Boolean = score >= bg.hanzi.learn.ui.path.PathRules.PASS_SCORE
}

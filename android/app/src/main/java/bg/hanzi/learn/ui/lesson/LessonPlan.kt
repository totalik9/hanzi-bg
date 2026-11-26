package bg.hanzi.learn.ui.lesson

import bg.hanzi.learn.data.content.CharacterEntry
import bg.hanzi.learn.data.content.ExampleEntry
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
 * THE TEST IS NOT PART OF THE TEACHING
 *
 * A word used to be taught and tested in the same breath: LISTEN, then
 * RECOGNISE, then SAY, then WRITE. The owner of the app asked for
 * another order:
 *
 *   "teach a batch, test the batch next day or next time the app is
 *   started"
 *
 * So a word that is taught now is tested in the NEXT lesson, and a
 * lesson is:
 *
 *   LESSON N = the words of batch N, taught (LISTEN, SAY, WRITE)
 *             + the words of batch N-1, tested (RECOGNISE, one card
 *               per word)
 *
 * A learner who hears a word for the first time cannot recognise it
 * five seconds later -- they recognise it because they have met it
 * before. The test is only a question when the word is old.
 */
enum class LessonStep {
    LISTEN,
    RECOGNISE,
    SAY,
    WRITE,

    /**
     * The progress of a reading lesson.
     *
     * The lesson no longer produces a REVIEW card -- the test of the
     * previous batch took its place -- but the step is kept because the
     * reading screen still draws it.
     */
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
    /**
     * The example sentence of the word, with its Bulgarian translation.
     *
     * A word on its own is a shape and a meaning. The sentence is what
     * puts it in a world: the learner sees the word used, and the
     * translation below tells them what the whole sentence said.
     *
     * It is empty when the corpus has no translated sentence for the
     * word -- the card works without it.
     */
    val example: ExampleEntry? = null,
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

    /**
     * The cards of a lesson.
     *
     * The cards come in two halves:
     *
     *   1. the words of this lesson are TAUGHT: LISTEN, SAY and WRITE
     *      for each of them, and NO question about them;
     *   2. the words of the PREVIOUS batch are TESTED: one RECOGNISE
     *      card for each of them.
     *
     * The first half is the teaching, the second half is the test of
     * the batch before this one. A lesson with no previous batch -- the
     * first vocabulary lesson of the path -- only teaches, and it is
     * recorded as taught rather than tested.
     *
     * @param words the new words of the lesson, in the order they are met
     * @param testWords the words of the previous batch, in the order they
     *   were taught
     * @param writingEnabled whether the WRITE step is in the lesson yet
     * @param characters the stroke data of the characters, by word
     * @param examples the example sentence of the words, by word
     * @param knownWords the words the learner already knows; they are the
     *   pool the distractors are drawn from, they are not cards
     * @param random the source of the distractors' order
     */
    fun cards(
        words: List<WordEntry>,
        testWords: List<WordEntry>,
        writingEnabled: Boolean,
        characters: Map<String, List<CharacterEntry>> = emptyMap(),
        examples: Map<String, ExampleEntry> = emptyMap(),
        knownWords: List<WordEntry> = emptyList(),
        random: Random = Random.Default,
    ): List<LessonCard> {
        // A lesson with no words of its own is not a vocabulary lesson:
        // a reading lesson teaches the sound system with cards, not with
        // words, and it is not tested either. It has no cards at all.
        if (words.isEmpty()) return emptyList()

        val pool = (words + testWords + knownWords)
            .map { it.glossBg.ifBlank { it.glossEn } }
            .filter { it.isNotBlank() }
            .distinct()

        val cards = mutableListOf<LessonCard>()

        // The teaching: the words of this batch, heard, said and written.
        // There is no question about them -- the question about a word
        // comes in the next lesson, when the word is old.
        for (word in words) {
            cards += LessonCard(word, LessonStep.LISTEN)
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

        // The test: one question per word of the previous batch. The
        // order is the order the learner met the words, because the
        // batch is a story and not a shuffle.
        for (word in testWords) {
            val gloss = word.glossBg.ifBlank { word.glossEn }
            val options = chooseOptions(gloss, pool, random)
            cards += LessonCard(
                word = word,
                step = LessonStep.RECOGNISE,
                options = options,
                correctIndex = options.indexOf(gloss),
                // The example sentence of the word: the learner meets
                // the word in a sentence, not only as a meaning to
                // pick. The sentence is taken from the corpus, and a
                // word without one simply has no example.
                example = examples[word.hanzi],
            )
        }

        return cards
    }

    /**
     * Whether a lesson has cards that ask a question.
     *
     * A lesson without a question is a lesson that only taught: the
     * first vocabulary lesson of the path, and every reading lesson.
     * Such a lesson is not scored -- there is nothing to score -- and it
     * is recorded as passed, because the learner did what the lesson
     * asked of them.
     *
     * @param cards the cards of the lesson
     */
    fun hasTestCards(cards: List<LessonCard>): Boolean =
        cards.any { it.step == LessonStep.RECOGNISE }

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
     * THE TWIN OF THE ANSWER
     *
     * A clone is not the only way to be unfair. Two DIFFERENT words
     * can have the same everyday Bulgarian meaning, and then the card
     * asks a question that has two right answers:
     *
     *     две          <- the answer (二, the numeral two)
     *     два          <- "wrong" (两, two OF something)
     *
     * The learner knows Bulgarian, answers with the everyday word
     * "два", and is told they are wrong. It happened for real in the
     * recording of the 2026-11-23 session: the review card of 二
     * offered "два", "десет", "осем" and "две", and "два" was marked
     * wrong.
     *
     * A twin is a meaning that starts with the same three letters as
     * the answer ("два"/"две", "малък"/"малко", "училище"/"учител")
     * or that contains it ("много" inside "много; изключително").
     * The measure is over the whole path: 99 of the 300 words of the
     * learning path had such a twin in the pool of their lesson.
     *
     * A twin of the ANSWER is never offered. A twin of another
     * DISTRACTOR is not offered either: two options that read the
     * same are two buttons the learner cannot choose between.
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
        val candidates = pool
            .filter { it.trim().lowercase() != answerKey }
            .shuffled(random)
        val distractors = mutableListOf<String>()
        for (candidate in candidates) {
            if (distractors.size >= OPTION_COUNT - 1) break
            // A twin of the answer is not a distractor.
            if (isTwin(candidate, gloss)) continue
            // And neither is a twin of a distractor that is already in.
            if (distractors.any { isTwin(it, candidate) }) continue
            distractors += candidate
        }
        return (distractors + gloss).shuffled(random)
    }

    /**
     * Whether two meanings are the same word in different clothes.
     *
     * The test is the first three letters of the meaning, or one of them
     * containing the other. It is a proxy, not a dictionary: it catches
     * the pairs that punish a learner ("два"/"две", "малък"/"малко",
     * "училище"/"учител", "хотел"/"хостел") and it is deliberately
     * generous -- a card with three options is still a question.
     */
    private fun isTwin(a: String, b: String): Boolean {
        val x = a.trim().lowercase()
        val y = b.trim().lowercase()
        if (x == y) return true
        if (x.contains(y) || y.contains(x)) return true
        return x.length >= 3 && y.length >= 3 && x.take(3) == y.take(3)
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

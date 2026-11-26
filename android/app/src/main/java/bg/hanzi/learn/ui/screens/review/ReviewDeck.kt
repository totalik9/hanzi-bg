package bg.hanzi.learn.ui.screens.review

import bg.hanzi.learn.data.content.ExampleEntry
import bg.hanzi.learn.data.content.WordEntry

/**
 * How a review session is put together.
 *
 * The deck used to seed itself with the first twenty words of the
 * selected level, every time, in the same order. The learner met the
 * same twenty words for ever and the other 280 words of HSK 1 were
 * unreachable from the review screen -- the screen that exists to
 * work through the vocabulary.
 *
 * A session is now built from two parts:
 *
 *   * the cards that are DUE -- those are the reviews the learner is
 *     supposed to do today, and they come first;
 *   * the words of the level the learner has NOT met yet -- those are
 *     what moves the learner through the level.
 *
 * The class is pure on purpose: the rule is worth a unit test, and a
 * ViewModel test would need a device.
 */
object ReviewDeck {

    /** How many words a session holds. */
    const val SESSION_SIZE = 20

    /**
     * The queue of a review session.
     *
     * @param due the cards that are due, oldest first
     * @param levelWords the words of the selected levels, in the order
     *   the learner should meet them
     * @param learned the words the learner has already met
     * @param limit the size of the session
     */
    fun session(
        due: List<WordEntry>,
        levelWords: List<WordEntry>,
        learned: Set<String>,
        limit: Int = SESSION_SIZE,
    ): List<WordEntry> {
        if (limit <= 0) return emptyList()

        // The due reviews take as much of the session as they need.
        val reviews = due.take(limit)

        // The rest is filled with words the learner has not met yet.
        // Without this the session is the same twenty words for ever.
        val fresh = levelWords
            .filterNot { it.hanzi in learned }
            .take(limit - reviews.size)

        return reviews + fresh
    }

    /**
     * The example sentence that helps the learner most.
     *
     * A word the learner has never met cannot be guessed from a
     * meaning alone. It can be worked out from a SENTENCE: the
     * sentence is built of words the learner knows, and the new word
     * sits in the middle of it. The owner of the app asked for exactly
     * this: "learn through older words new words too".
     *
     * So the examples are ranked by how much of the sentence the
     * learner can already read: the candidate with the most characters
     * they know wins. A tie is broken by the SHORTER sentence -- the
     * shorter one has less left to guess at.
     *
     * The characters are counted once each: a sentence that repeats
     * the same known character five times is not five times easier to
     * read, it is one character easier.
     *
     * @param candidates the example sentences of the word
     * @param knownCharacters the characters the learner already knows
     */
    fun pickExample(
        candidates: List<ExampleEntry>,
        knownCharacters: Set<String>,
    ): ExampleEntry? {
        if (candidates.isEmpty()) return null
        return candidates
            .map { candidate ->
                val known = candidate.sentence
                    .toSet()
                    .count { it.toString() in knownCharacters }
                candidate to known
            }
            // The most known characters first, and the shorter sentence
            // when they are equal. The sort is stable, so two sentences
            // that are equal in both keep the order the table gave them.
            .sortedWith(
                compareByDescending<Pair<ExampleEntry, Int>> { it.second }
                    .thenBy { it.first.sentence.length },
            )
            .first()
            .first
    }
}

package bg.hanzi.learn.ui.lesson

import bg.hanzi.learn.data.content.CurriculumLesson
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.db.SrsCardEntity
import bg.hanzi.learn.data.srs.SrsScheduler
import java.time.Instant
import java.time.ZoneId

/**
 * The batches of the learning path: which batch a lesson teaches, which
 * batch it tests, and when a taught word comes back for review.
 *
 * The rules are plain functions so they can be tested without a device:
 * a batch that is tested in the wrong lesson is a batch the learner
 * meets twice or never.
 *
 * WHY THE BATCHES ARE SEPARATED
 *
 * The owner of the app asked for this:
 *
 *   "teach a batch, test the batch next day or next time the app is
 *   started"
 *
 * and
 *
 *   "inject new words through repetitions - learn through older words
 *   new words too"
 *
 * So a lesson is no longer a walk through its own words with a
 * question about each of them. It is:
 *
 *   LESSON N = teach the words of batch N (listen, say, write)
 *             + test the words of batch N-1 (one question per word)
 *
 * The first vocabulary lesson has no batch before it, so it only
 * teaches.
 */
object LessonBatch {

    /**
     * The stability a taught word starts with.
     *
     * A taught word has never been answered, so its card holds no
     * memory yet: 1.0 is the floor the scheduler itself uses for a card
     * that has just been seen ("max(1.0, ...)" in [SrsScheduler]). The
     * first answer then moves it like any other card.
     */
    const val TAUGHT_STABILITY = 1.0

    /**
     * The difficulty a taught word starts with.
     *
     * It is the difficulty the scheduler gives a new card that was
     * answered well (5.0 in the scheduler's first review), so a taught
     * word is neither easier nor harder than the words the app has
     * always made.
     */
    const val TAUGHT_DIFFICULTY = 5.0

    /**
     * The words the given lesson TESTS.
     *
     * A reading lesson ("teach") is not tested: it teaches the sound
     * system and it is read to the end. So its batch is empty.
     *
     * A vocabulary lesson tests the batch before it -- see
     * [previousBatch].
     *
     * @param lessons the path, in order
     * @param lessonKey the key of the lesson
     */
    fun testBatch(lessons: List<CurriculumLesson>, lessonKey: String): List<String> {
        val lesson = lessons.firstOrNull { it.key == lessonKey } ?: return emptyList()
        if (lesson.isTeach) return emptyList()
        return previousBatch(lessons, lessonKey)
    }

    /**
     * The words of the batch that the given lesson's batch follows.
     *
     * The batch is the previous lesson of the path that has words. A
     * reading lesson ("teach") carries no words, so it is skipped: the
     * batch the learner meets in the next vocabulary lesson is the one
     * before the reading lesson, not the reading lesson itself.
     *
     * The words are returned as the hanzi of the words, in the order
     * the learner met them. The lesson turns them into words of the
     * dictionary.
     *
     * @param lessons the path, in order
     * @param lessonKey the key of the lesson
     */
    fun previousBatch(lessons: List<CurriculumLesson>, lessonKey: String): List<String> {
        val index = lessons.indexOfFirst { it.key == lessonKey }
        if (index <= 0) return emptyList()
        for (i in index - 1 downTo 0) {
            val lesson = lessons[i]
            // A reading lesson carries no words, so there is no batch
            // of its own to test.
            if (lesson.isTeach) continue
            val words = lesson.words
            if (words.isNotEmpty()) return words
        }
        return emptyList()
    }

    /**
     * When a taught word is due for review: the start of tomorrow.
     *
     * The owner asked for the batch to be tested "the next day or the
     * next time the app is started". A card that is due at the start of
     * tomorrow is picked up by the daily review of the next day, and it
     * is NOT due today: a word the learner has just heard for the
     * first time cannot be recalled on the same evening.
     *
     * The start of the day is computed in the time zone of the device,
     * so "tomorrow" is the learner's tomorrow and not the one of the
     * server.
     *
     * @param now the current time, in milliseconds since the epoch
     * @param zone the time zone the learner lives in
     */
    fun dueTomorrow(now: Long, zone: ZoneId = ZoneId.systemDefault()): Long {
        val local = Instant.ofEpochMilli(now).atZone(zone)
        return local.toLocalDate()
            .plusDays(1)
            .atStartOfDay(zone)
            .toInstant()
            .toEpochMilli()
    }

    /**
     * The SRS card of a word that has just been TAUGHT.
     *
     * The card is created when the word is taught, not when it is first
     * tested. Without it the word would never enter the review queue:
     * the test of a batch happens in the NEXT lesson, and if the card
     * only appeared with the answer, the review of the next morning
     * would have nothing to review.
     *
     * The card starts in the LEARNING state with no repetitions: the
     * learner has met the word, they have not been asked about it yet.
     * When the batch is tested, the answer moves the card on with the
     * scheduler, as it does for every other card.
     *
     * @param word the word that was taught
     * @param now the moment the word was taught
     * @param zone the time zone the learner lives in
     */
    fun taughtCard(
        word: WordEntry,
        now: Long,
        zone: ZoneId = ZoneId.systemDefault(),
    ): SrsCardEntity = SrsCardEntity(
        itemId = word.hanzi,
        level = word.hskLevel,
        dueAt = dueTomorrow(now, zone),
        stability = TAUGHT_STABILITY,
        difficulty = TAUGHT_DIFFICULTY,
        reps = 0,
        lapses = 0,
        state = SrsScheduler.STATE_LEARNING,
        lastReviewAt = null,
    )
}

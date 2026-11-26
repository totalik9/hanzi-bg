package bg.hanzi.learn.ui.lesson

import bg.hanzi.learn.data.content.CurriculumLesson
import bg.hanzi.learn.data.content.WordEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * Which batch a lesson teaches and which batch it tests.
 *
 * The rules are about what the learner meets and when, so they are
 * plain functions with a unit test: a batch tested in the wrong lesson
 * is a batch the learner meets twice or never.
 */
class LessonBatchTest {

    private fun lesson(
        key: String,
        words: List<String> = emptyList(),
        kind: String = "words",
    ) = CurriculumLesson(
        key = key,
        unitKey = "u",
        title = key,
        kind = kind,
        ord = 0,
        words = words,
        cards = emptyList(),
    )

    private val path = listOf(
        lesson("intro", kind = "teach"),
        lesson("numbers-1", words = listOf("一", "二")),
        lesson("numbers-2", words = listOf("三", "四", "五")),
        lesson("numbers-3", words = listOf("六")),
    )

    @Test
    fun thePreviousBatchOfTheThirdLessonIsTheSecondLesson() {
        assertEquals(
            listOf("三", "四", "五"),
            LessonBatch.previousBatch(path, "numbers-3"),
        )
    }

    @Test
    fun thePreviousBatchOfTheFirstLessonIsEmpty() {
        assertTrue(LessonBatch.previousBatch(path, "intro").isEmpty())
    }

    @Test
    fun aReadingLessonInBetweenIsSkipped() {
        // The reading lesson carries no words, so the batch of the
        // lesson before it is tested again.
        val withReading = listOf(
            lesson("numbers-1", words = listOf("一", "二")),
            lesson("reading", kind = "teach"),
            lesson("numbers-2", words = listOf("三")),
        )

        assertEquals(
            listOf("一", "二"),
            LessonBatch.previousBatch(withReading, "numbers-2"),
        )
    }

    @Test
    fun aReadingLessonIsNotTested() {
        // A reading lesson teaches the sound system and is read to the
        // end: it has no question in it.
        assertTrue(LessonBatch.testBatch(path, "intro").isEmpty())
    }

    @Test
    fun aVocabularyLessonTestsTheBatchBeforeIt() {
        assertEquals(
            listOf("一", "二"),
            LessonBatch.testBatch(path, "numbers-2"),
        )
    }

    @Test
    fun theFirstVocabularyLessonHasNothingToTest() {
        // The first vocabulary lesson of the path: there is no batch
        // before it, so it only teaches.
        assertTrue(LessonBatch.testBatch(path, "numbers-1").isEmpty())
    }

    @Test
    fun anUnknownLessonHasNothingToTest() {
        assertTrue(LessonBatch.testBatch(path, "no-such-lesson").isEmpty())
    }

    // -- the card of a taught word ------------------------------------

    private fun word(hanzi: String) = WordEntry(
        hanzi = hanzi,
        pinyin = "yi",
        pinyinTones = "yī",
        pos = "",
        glossEn = "one",
        glossBg = "едно",
        hskLevel = "1",
        isVerb = false,
        freq = 1,
        audio = "",
        glossSource = "human",
    )

    @Test
    fun aTaughtWordIsDueAtTheStartOfTomorrow() {
        val zone = ZoneId.of("Europe/Sofia")
        val now = ZonedDateTime.of(2026, 3, 10, 21, 30, 0, 0, zone)
            .toInstant()
            .toEpochMilli()

        val due = LessonBatch.dueTomorrow(now, zone)

        val dueAt = ZonedDateTime.ofInstant(
            java.time.Instant.ofEpochMilli(due),
            zone,
        )
        assertEquals(2026, dueAt.year)
        assertEquals(3, dueAt.monthValue)
        assertEquals(11, dueAt.dayOfMonth)
        assertEquals(0, dueAt.hour)
        assertEquals(0, dueAt.minute)
        // The card is due LATER than the moment the word was taught.
        assertTrue(due > now)
    }

    @Test
    fun aTaughtWordIsDueInTheLearnersOwnTomorrow() {
        // Twenty-three thirty in Sofia is already the next day in
        // Tokyo. The word is due when the LEARNER starts the day, not
        // when the clock of another country does: the learner in
        // Sofia gets it on the 11th, the learner in Tokyo on the 12th.
        val sofia = ZoneId.of("Europe/Sofia")
        val tokyo = ZoneId.of("Asia/Tokyo")
        val now = ZonedDateTime.of(2026, 3, 10, 23, 30, 0, 0, sofia)
            .toInstant()
            .toEpochMilli()

        val dueInSofia = ZonedDateTime.ofInstant(
            java.time.Instant.ofEpochMilli(LessonBatch.dueTomorrow(now, sofia)),
            sofia,
        )
        val dueInTokyo = ZonedDateTime.ofInstant(
            java.time.Instant.ofEpochMilli(LessonBatch.dueTomorrow(now, tokyo)),
            tokyo,
        )

        assertEquals(11, dueInSofia.dayOfMonth)
        assertEquals(12, dueInTokyo.dayOfMonth)
    }

    @Test
    fun aTaughtWordStartsInTheLearningStateWithNoRepetitions() {
        val now = System.currentTimeMillis()

        val card = LessonBatch.taughtCard(word("一"), now)

        assertEquals("一", card.itemId)
        assertEquals(0, card.reps)
        assertEquals(0, card.lapses)
        assertEquals(bg.hanzi.learn.data.srs.SrsScheduler.STATE_LEARNING, card.state)
        assertEquals(null, card.lastReviewAt)
        assertTrue(card.dueAt > now)
    }
}

package bg.hanzi.learn.data.db

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the daily statistics.
 *
 * The daily_stats table existed and nothing ever wrote to it, so the
 * Home screen had nothing to show. These tests cover the day keys and
 * the streak arithmetic, which are the parts that can go wrong.
 */
class DailyStatsTest {

    @Test
    fun theDayKeyIsTheLocalDate() {
        // The key is the LOCAL date, so the test cannot name a fixed
        // instant and expect one answer: the same moment is a different
        // day on the other side of the date line. What has to hold
        // everywhere is the format and the ordering.
        val millis = 1_794_571_200_000L  // 2026-11-13T12:00:00Z
        val key = DailyStats.dayKeyAt(millis)
        assertTrue("unexpected day key: $key", key.matches(Regex("\\d{4}-\\d{2}-\\d{2}")))
        // Two days back from the day after tomorrow is today.
        assertEquals(
            "the day arithmetic must agree with the clock",
            key,
            DailyStats.previousDay(
                DailyStats.previousDay(DailyStats.dayKeyAt(millis + 2 * 24 * 3600 * 1000L)),
            ),
        )
    }

    @Test
    fun consecutiveDaysAreConsecutive() {
        // 24 hours apart is the next day, whatever the time zone.
        val millis = 1_794_571_200_000L
        val today = DailyStats.dayKeyAt(millis)
        val tomorrow = DailyStats.dayKeyAt(millis + 24 * 3600 * 1000L)
        assertEquals(today, DailyStats.previousDay(tomorrow))
    }

    @Test
    fun thePreviousDayStepsBackOneDay() {
        assertEquals("2026-11-12", DailyStats.previousDay("2026-11-13"))
        assertEquals("2026-11-01", DailyStats.previousDay("2026-11-02"))
    }

    @Test
    fun thePreviousDayCrossesTheMonthBoundary() {
        assertEquals("2026-10-31", DailyStats.previousDay("2026-11-01"))
        assertEquals("2026-02-28", DailyStats.previousDay("2026-03-01"))
    }

    @Test
    fun thePreviousDayCrossesTheYearBoundary() {
        assertEquals("2025-12-31", DailyStats.previousDay("2026-01-01"))
    }

    @Test
    fun aStreakCountsTheConsecutiveDays() {
        val days = listOf("2026-11-13", "2026-11-12", "2026-11-11")
        assertEquals(3, DailyStats.streak(days, "2026-11-13"))
    }

    @Test
    fun aStreakOfOneDayIsOne() {
        assertEquals(1, DailyStats.streak(listOf("2026-11-13"), "2026-11-13"))
    }

    @Test
    fun yesterdayStillCountsBecauseTheDayIsNotOver() {
        // The learner studied yesterday but has not opened the app yet
        // today. The streak is not broken by a day that is not over.
        val days = listOf("2026-11-12", "2026-11-11")
        assertEquals(2, DailyStats.streak(days, "2026-11-13"))
    }

    @Test
    fun aGapBreaksTheStreak() {
        // The 12th is missing: the streak is 1, not 3.
        val days = listOf("2026-11-13", "2026-11-11", "2026-11-10")
        assertEquals(1, DailyStats.streak(days, "2026-11-13"))
    }

    @Test
    fun aLongGapMeansNoStreak() {
        val days = listOf("2026-11-01", "2026-10-31")
        assertEquals(0, DailyStats.streak(days, "2026-11-13"))
    }

    @Test
    fun noDaysMeansNoStreak() {
        assertEquals(0, DailyStats.streak(emptyList(), "2026-11-13"))
    }

    @Test
    fun theOrderOfTheDaysDoesNotMatter() {
        // The database returns them newest first, but the streak must
        // not depend on that.
        val days = listOf("2026-11-11", "2026-11-13", "2026-11-12")
        assertEquals(3, DailyStats.streak(days, "2026-11-13"))
    }
}

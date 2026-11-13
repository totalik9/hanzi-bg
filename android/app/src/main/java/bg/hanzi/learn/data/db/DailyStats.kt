package bg.hanzi.learn.data.db

import java.util.Calendar

/**
 * The day keys and the streak arithmetic.
 *
 * A day is a local "yyyy-MM-dd" string. The streak is the number of
 * consecutive days with at least one review, counting back from today.
 *
 * The functions are pure and take the day keys as arguments so that
 * they can be tested without a database and without a clock.
 */
object DailyStats {

    /** Today's day key, in the device's own time zone. */
    fun todayKey(now: Long = System.currentTimeMillis()): String =
        dayKeyAt(now)

    /** The day key of a timestamp. */
    fun dayKeyAt(now: Long): String {
        val cal = Calendar.getInstance().apply { timeInMillis = now }
        val year = cal.get(Calendar.YEAR)
        val month = cal.get(Calendar.MONTH) + 1
        val day = cal.get(Calendar.DAY_OF_MONTH)
        return "%04d-%02d-%02d".format(year, month, day)
    }

    /** The day key of the day before the given one. */
    fun previousDay(dayKey: String): String {
        val parts = dayKey.split("-")
        if (parts.size != 3) return dayKey
        val year = parts[0].toIntOrNull() ?: return dayKey
        val month = parts[1].toIntOrNull() ?: return dayKey
        val day = parts[2].toIntOrNull() ?: return dayKey
        val cal = Calendar.getInstance().apply {
            clear()
            set(year, month - 1, day, 12, 0, 0)
            // Noon, not midnight: in a few time zones midnight does not
            // exist on the day the clocks change, and Calendar would
            // silently move the date to the day before.
        }
        cal.add(Calendar.DAY_OF_MONTH, -1)
        return dayKeyAt(cal.timeInMillis)
    }

    /**
     * How many consecutive days have at least one review.
     *
     * [activeDays] is the list of day keys with reviews, newest first.
     * The streak counts back from [today]: a learner who studied today
     * has a streak of at least 1, a learner who studied yesterday but
     * not yet today has the streak of yesterday (the day is not over
     * yet), and a learner who has not studied for a week has none.
     */
    fun streak(activeDays: List<String>, today: String = todayKey()): Int {
        if (activeDays.isEmpty()) return 0
        val days = activeDays.toHashSet()

        // The streak is anchored on the most recent active day, which is
        // either today or yesterday. A gap of two days ends it.
        var anchor = when {
            days.contains(today) -> today
            days.contains(previousDay(today)) -> previousDay(today)
            else -> return 0
        }

        var streak = 0
        while (days.contains(anchor)) {
            streak++
            anchor = previousDay(anchor)
        }
        return streak
    }
}

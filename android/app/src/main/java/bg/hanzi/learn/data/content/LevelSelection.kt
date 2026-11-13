package bg.hanzi.learn.data.content

/**
 * Which HSK levels a screen works with.
 *
 * The vocabulary is graded, and the levels are not all the same size:
 *
 *     HSK 1        300 words
 *     HSK 2        197 words
 *     HSK 3        491 words
 *     HSK 4        990 words
 *     HSK 5      1 579 words
 *     HSK 6      1 777 words
 *     HSK 7-9    5 562 words
 *
 * The practice pool used to be hardcoded to the first two levels, which
 * left 95 % of the vocabulary in the database but out of reach. The
 * level now travels through the navigation as an argument, and this
 * object turns that argument back into the level ids the database uses.
 *
 * The argument is a comma-separated list of level ids, exactly as they
 * are stored in the words table ("1", "2", "7-9"). That keeps the
 * mapping unambiguous: "7-9" is one level id with a dash in it, and
 * "1,2" is two of them.
 */
object LevelSelection {

    /**
     * The default selection: the two beginner levels together.
     *
     * This is what the app worked with before the level selector
     * existed, so the first-run behaviour is unchanged.
     */
    const val DEFAULT = "1,2"

    /** The argument name, shared by every route that takes a level. */
    const val ARGUMENT = "level"

    /**
     * The level ids a selection covers.
     *
     * An empty or blank selection falls back to [DEFAULT], so a
     * malformed argument never leaves the learner with an empty app.
     */
    fun levelsOf(selection: String?): List<String> {
        val levels = selection.orEmpty()
            .split(',')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
        return levels.ifEmpty { DEFAULT.split(',') }
    }

    /**
     * The selection as the argument value, for navigating.
     */
    fun argumentFor(levels: List<String>): String =
        levels.filter { it.isNotBlank() }.joinToString(",").ifEmpty { DEFAULT }

    /**
     * How many levels the selection covers -- for the label on the
     * screen ("2 нива" / "1 ниво").
     */
    fun countOf(selection: String?): Int = levelsOf(selection).size

    /**
     * A short label for the selection.
     *
     * A single level reads "HSK 3"; several read "HSK 1-2" when they
     * are consecutive and "HSK 1, 3" when they are not.
     */
    fun labelOf(selection: String?): String {
        val levels = levelsOf(selection)
        if (levels.size == 1) return "HSK ${levels[0]}"
        val numeric = levels.mapNotNull { it.toIntOrNull() }
        val consecutive = numeric.size == levels.size &&
            numeric.zipWithNext().all { (a, b) -> b == a + 1 }
        return if (consecutive) {
            "HSK ${numeric.first()}-${numeric.last()}"
        } else {
            "HSK " + levels.joinToString(", ")
        }
    }
}

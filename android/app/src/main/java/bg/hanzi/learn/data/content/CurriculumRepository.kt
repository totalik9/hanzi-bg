package bg.hanzi.learn.data.content

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The learning path: units, lessons and the words in them.
 *
 * The order the learner meets the words in is a TEACHING decision, so it
 * is written by hand, in the curriculum folder, and read back here.
 * Nothing in this file derives the order from the corpus.
 *
 * The path is what turns a dictionary into a course. Before it existed
 * the app had 10 896 words and no way to walk through them: the Home
 * screen offered HSK levels, and the simulation showed that 20 of 20
 * learners reached the grammar while only 2 of 20 reached the
 * vocabulary.
 */
data class CurriculumUnit(
    val key: String,
    val title: String,
    val ord: Int,
    val lessons: List<CurriculumLesson>,
)

data class CurriculumLesson(
    val key: String,
    val unitKey: String,
    val title: String,
    /**
     * "teach" lessons teach the sound system and carry cards instead of
     * words; "words" lessons carry the vocabulary.
     */
    val kind: String,
    val ord: Int,
    /** The words of the lesson, in the order the learner meets them. */
    val words: List<String>,
    /** The teaching cards of a "teach" lesson, as raw JSON. */
    val cards: List<String>,
) {
    val isTeach: Boolean get() = kind == "teach"
}

/**
 * Reads the learning path from the bundled content database.
 *
 * It is a separate repository from [ContentRepository] because the path
 * and the words are different things: the words are the corpus, and the
 * path is the course through it.
 */
@Singleton
class CurriculumRepository @Inject constructor(
    private val provider: ContentDatabaseProvider,
) {

    /** The whole path, in order. */
    fun units(): List<CurriculumUnit> {
        val db = provider.database ?: return emptyList()

        val lessonsByUnit = lessonRows(db).groupBy { it.unitKey }
        val words = wordsByLesson(db)
        val cards = cardsByLesson(db)
        return unitRows(db).map { unit ->
            CurriculumUnit(
                key = unit.key,
                title = unit.title,
                ord = unit.ord,
                lessons = lessonsByUnit[unit.key].orEmpty().map { lesson ->
                    lesson.toLesson(
                        words = words[lesson.key].orEmpty(),
                        cards = cards[lesson.key].orEmpty(),
                    )
                },
            )
        }
    }

    /** Every lesson of the path, in order. */
    fun lessons(): List<CurriculumLesson> {
        val db = provider.database ?: return emptyList()
        val words = wordsByLesson(db)
        val cards = cardsByLesson(db)
        return lessonRows(db).map { lesson ->
            lesson.toLesson(
                words = words[lesson.key].orEmpty(),
                cards = cards[lesson.key].orEmpty(),
            )
        }
    }

    /** The lesson with this key, or null. */
    fun lesson(key: String): CurriculumLesson? = lessons().firstOrNull { it.key == key }

    private data class UnitRow(val key: String, val title: String, val ord: Int)

    private data class LessonRow(
        val key: String,
        val unitKey: String,
        val title: String,
        val kind: String,
        val ord: Int,
    ) {
        fun toLesson(words: List<String>, cards: List<String>) = CurriculumLesson(
            key = key,
            unitKey = unitKey,
            title = title,
            kind = kind,
            ord = ord,
            words = words,
            cards = cards,
        )
    }

    private fun unitRows(db: SQLiteDatabase): List<UnitRow> =
        db.rawQuery(
            "SELECT key, title, ord FROM curriculum_units ORDER BY ord",
            null,
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(UnitRow(c.str("key"), c.str("title"), c.int("ord")))
                }
            }
        }

    private fun lessonRows(db: SQLiteDatabase): List<LessonRow> =
        db.rawQuery(
            "SELECT key, unit_key, title, kind, ord FROM curriculum_lessons ORDER BY ord",
            null,
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        LessonRow(
                            key = c.str("key"),
                            unitKey = c.str("unit_key"),
                            title = c.str("title"),
                            kind = c.str("kind"),
                            ord = c.int("ord"),
                        ),
                    )
                }
            }
        }

    private fun wordsByLesson(db: SQLiteDatabase): Map<String, List<String>> {
        val grouped = mutableMapOf<String, MutableList<String>>()
        db.rawQuery(
            "SELECT lesson_key, hanzi FROM curriculum_words ORDER BY lesson_key, ord",
            null,
        ).use { c ->
            while (c.moveToNext()) {
                grouped.getOrPut(c.str("lesson_key")) { mutableListOf() }.add(c.str("hanzi"))
            }
        }
        return grouped
    }

    private fun cardsByLesson(db: SQLiteDatabase): Map<String, List<String>> {
        val grouped = mutableMapOf<String, MutableList<String>>()
        db.rawQuery(
            "SELECT lesson_key, payload FROM curriculum_cards ORDER BY lesson_key, ord",
            null,
        ).use { c ->
            while (c.moveToNext()) {
                grouped.getOrPut(c.str("lesson_key")) { mutableListOf() }.add(c.str("payload"))
            }
        }
        return grouped
    }
}

private fun Cursor.str(name: String): String = getString(getColumnIndexOrThrow(name)) ?: ""

private fun Cursor.int(name: String): Int = getInt(getColumnIndexOrThrow(name))

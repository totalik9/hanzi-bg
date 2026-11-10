package bg.hanzi.learn.data.content

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import javax.inject.Inject
import javax.inject.Singleton

data class WordEntry(
    val hanzi: String,
    val pinyin: String,
    val pinyinTones: String,
    val pos: String,
    val glossEn: String,
    val glossBg: String,
    val hskLevel: String,
    val isVerb: Boolean,
    val freq: Int?,
    val audio: String? = null,
)

data class GrammarEntry(
    val id: Long,
    val title: String,
    val titleBg: String,
    val level: String,
    val category: String,
    val summary: String,
    val body: String,
    val examples: String,
)

data class SentenceEntry(
    val id: Long,
    val hanzi: String,
    val pinyin: String,
    val translationEn: String,
    val translationBg: String,
    val audioPath: String?,
)

data class LessonEntry(
    val id: Long,
    val title: String,
    val titleBg: String,
    val level: String,
    val ord: Int,
)

/**
 * Read-only access to the bundled content database. All reads are cursor
 * based and close their cursors; nothing is cached in memory beyond the
 * SQLite page cache, which keeps the footprint small on 8 GB devices.
 */
@Singleton
class ContentRepository @Inject constructor(
    private val provider: ContentDatabaseProvider,
) {

    val isAvailable: Boolean get() = provider.database != null

    private fun <T> read(block: (SQLiteDatabase) -> T): T? {
        val db = provider.database ?: return null
        return try {
            block(db)
        } catch (e: IllegalStateException) {
            null
        }
    }

    fun levels(): List<String> = read { db ->
        db.rawQuery(
            "SELECT DISTINCT hsk_level FROM words WHERE hsk_level IS NOT NULL AND hsk_level != '' ORDER BY hsk_level",
            null,
        ).use { c -> c.collectStrings("hsk_level") }
    } ?: emptyList()

    fun wordCount(level: String): Int = read { db ->
        db.rawQuery("SELECT COUNT(*) FROM words WHERE hsk_level = ?", arrayOf(level)).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }
    } ?: 0

    fun wordsForLevel(level: String, limit: Int = 200, offset: Int = 0): List<WordEntry> =
        read { db ->
            // LIMIT/OFFSET are inlined as integers: rawQuery binds every
            // argument as a string, which SQLite rejects for LIMIT.
            db.rawQuery(
                """
                SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio
                FROM words
                WHERE hsk_level = ?
                ORDER BY (freq IS NULL), freq, hanzi
                LIMIT $limit OFFSET $offset
                """.trimIndent(),
                arrayOf(level),
            ).use { c ->
                buildList {
                    while (c.moveToNext()) {
                        add(
                            WordEntry(
                                hanzi = c.str("hanzi"),
                                pinyin = c.str("pinyin"),
                                pinyinTones = c.str("pinyin_tones"),
                                pos = c.str("pos"),
                                glossEn = c.str("gloss_en"),
                                glossBg = c.str("gloss_bg"),
                                hskLevel = c.str("hsk_level"),
                                isVerb = c.int("is_verb") == 1,
                                freq = if (c.isNull("freq")) null else c.getInt("freq"),
                                audio = c.strOrNull("audio"),
                            ),
                        )
                    }
                }
            }
        } ?: emptyList()

    fun verbsForLevel(level: String, limit: Int = 100): List<WordEntry> = read { db ->
        db.rawQuery(
            """
            SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio
            FROM words
            WHERE hsk_level = ? AND is_verb = 1
            ORDER BY (freq IS NULL), freq, hanzi
            LIMIT $limit
            """.trimIndent(),
            arrayOf(level),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        WordEntry(
                            hanzi = c.str("hanzi"),
                            pinyin = c.str("pinyin"),
                            pinyinTones = c.str("pinyin_tones"),
                            pos = c.str("pos"),
                            glossEn = c.str("gloss_en"),
                            glossBg = c.str("gloss_bg"),
                            hskLevel = c.str("hsk_level"),
                            isVerb = true,
                            freq = if (c.isNull("freq")) null else c.getInt("freq"),
                            audio = c.strOrNull("audio"),
                        ),
                    )
                }
            }
        }
    } ?: emptyList()

    fun wordByHanzi(hanzi: String): WordEntry? = read { db ->
        db.rawQuery(
            """
            SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio
            FROM words WHERE hanzi = ? LIMIT 1
            """.trimIndent(),
            arrayOf(hanzi),
        ).use { c ->
            if (!c.moveToFirst()) {
                null
            } else {
                WordEntry(
                    hanzi = c.str("hanzi"),
                    pinyin = c.str("pinyin"),
                    pinyinTones = c.str("pinyin_tones"),
                    pos = c.str("pos"),
                    glossEn = c.str("gloss_en"),
                    glossBg = c.str("gloss_bg"),
                    hskLevel = c.str("hsk_level"),
                    isVerb = c.int("is_verb") == 1,
                    freq = if (c.isNull("freq")) null else c.getInt("freq"),
                    audio = c.strOrNull("audio"),
                )
            }
        }
    }

    fun search(query: String, limit: Int = 50): List<WordEntry> {
        if (query.isBlank()) return emptyList()
        return read { db ->
            db.rawQuery(
                """
                SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio
                FROM words
                WHERE hanzi LIKE ? OR pinyin LIKE ? OR gloss_en LIKE ?
                ORDER BY (freq IS NULL), freq, hanzi
                LIMIT $limit
                """.trimIndent(),
                arrayOf("%$query%", "%$query%", "%$query%"),
            ).use { c ->
                buildList {
                    while (c.moveToNext()) {
                        add(
                            WordEntry(
                                hanzi = c.str("hanzi"),
                                pinyin = c.str("pinyin"),
                                pinyinTones = c.str("pinyin_tones"),
                                pos = c.str("pos"),
                                glossEn = c.str("gloss_en"),
                                glossBg = c.str("gloss_bg"),
                                hskLevel = c.str("hsk_level"),
                                isVerb = c.int("is_verb") == 1,
                                freq = if (c.isNull("freq")) null else c.getInt("freq"),
                                audio = c.strOrNull("audio"),
                            ),
                        )
                    }
                }
            }
        } ?: emptyList()
    }

    fun grammar(level: String? = null): List<GrammarEntry> = read { db ->
        val sql = if (level == null) {
            "SELECT id, title, title_bg, level, category, summary, body, examples FROM grammar ORDER BY level, id"
        } else {
            "SELECT id, title, title_bg, level, category, summary, body, examples FROM grammar WHERE level = ? ORDER BY id"
        }
        val args = level?.let { arrayOf(it) } ?: emptyArray()
        db.rawQuery(sql, args).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        GrammarEntry(
                            id = c.getLong("id"),
                            title = c.str("title"),
                            titleBg = c.str("title_bg"),
                            level = c.str("level"),
                            category = c.str("category"),
                            summary = c.str("summary"),
                            body = c.str("body"),
                            examples = c.str("examples"),
                        ),
                    )
                }
            }
        }
    } ?: emptyList()

    fun lessons(level: String): List<LessonEntry> = read { db ->
        db.rawQuery(
            "SELECT id, title, title_bg, level, ord FROM lessons WHERE level = ? ORDER BY ord",
            arrayOf(level),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        LessonEntry(
                            id = c.getLong("id"),
                            title = c.str("title"),
                            titleBg = c.str("title_bg"),
                            level = c.str("level"),
                            ord = c.getInt("ord"),
                        ),
                    )
                }
            }
        }
    } ?: emptyList()

    fun sentences(limit: Int = 100): List<SentenceEntry> = read { db ->
        db.rawQuery(
            """
            SELECT s.id, s.hanzi, s.pinyin, s.translation_en, s.translation_bg, s.audio_path
            FROM sentences s
            LIMIT $limit
            """.trimIndent(),
            null,
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        SentenceEntry(
                            id = c.getLong("id"),
                            hanzi = c.str("hanzi"),
                            pinyin = c.str("pinyin"),
                            translationEn = c.str("translation_en"),
                            translationBg = c.str("translation_bg"),
                            audioPath = c.strOrNull("audio_path"),
                        ),
                    )
                }
            }
        }
    } ?: emptyList()

    fun manifestValue(key: String): String? = read { db ->
        db.rawQuery("SELECT value FROM manifest WHERE key = ?", arrayOf(key)).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
    }
}

private fun Cursor.str(name: String): String = getString(getColumnIndexOrThrow(name)) ?: ""

private fun Cursor.strOrNull(name: String): String? {
    val idx = getColumnIndex(name)
    return if (idx < 0 || isNull(idx)) null else getString(idx)
}

private fun Cursor.int(name: String): Int = getInt(getColumnIndexOrThrow(name))

// The platform Cursor accessors take an Int column index. These overloads
// take the column NAME instead: the member getInt(Int) is not applicable to
// a String argument, so the call site resolves to the extension. Using the
// name keeps the SQL in one place instead of repeating column indexes.
private fun Cursor.getInt(name: String): Int = getInt(getColumnIndexOrThrow(name))

private fun Cursor.getLong(name: String): Long = getLong(getColumnIndexOrThrow(name))

private fun Cursor.isNull(name: String): Boolean = isNull(getColumnIndexOrThrow(name))

private inline fun Cursor.collectStrings(column: String): List<String> = buildList {
    val idx = getColumnIndex(column)
    if (idx >= 0) {
        while (moveToNext()) {
            add(getString(idx) ?: "")
        }
    }
}

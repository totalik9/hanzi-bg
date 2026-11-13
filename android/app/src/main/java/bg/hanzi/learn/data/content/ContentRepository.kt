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
    /**
     * Where the Bulgarian gloss came from: "human" for the ones a person
     * wrote, "machine" for the machine translation, "human+machine" when
     * a human gloss leads and the machine senses follow it, and "" when
     * there is no Bulgarian gloss at all.
     *
     * The app shows this so the learner knows which glosses are worth
     * trusting -- a machine translation can be wrong, and a learner who
     * does not know that will trust it.
     */
    val glossSource: String = "",
) {
    /** True when a person wrote part of the Bulgarian gloss. */
    val isHumanGloss: Boolean get() = glossSource.startsWith("human")

    /**
     * True when the gloss contains a machine translation the learner
     * should treat with care.
     */
    val hasMachineGloss: Boolean get() = glossSource.contains("machine")
}

data class GrammarEntry(
    val id: Long,
    val title: String,
    val titleBg: String,
    val level: String,
    val category: String,
    val summary: String,
    /**
     * The Bulgarian summary.
     *
     * The app is for Bulgarian learners of Chinese, so this is what the
     * screen shows; the English [summary] is the fallback and the
     * source of the translation.
     */
    val summaryBg: String = "",
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
 * A character with its stroke-order data.
 *
 * [medians] holds the centre-line of each stroke as a JSON array of
 * [x, y] pairs in a 1024x1024 coordinate system. Drawing them in order
 * is how the writing mode animates the correct stroke sequence.
 */
data class CharacterEntry(
    val char: String,
    val strokes: Int,
    val radical: String,
    val definition: String,
    val medians: String,
)

/**
 * The pinyin IME index, loaded once and kept in memory.
 *
 * A pinyin IME has to answer on every keystroke, so the index cannot be
 * queried from SQLite each time. It is a few thousand entries, which is
 * a few hundred kilobytes.
 */
data class ImeIndex(
    val syllableToWords: Map<String, List<String>>,
    val wordToPinyin: Map<String, String>,
    val wordToGloss: Map<String, String>,
    /**
     * The corpus frequency rank of each word, lower is commoner.
     *
     * The IME needs it to order the candidates: a syllable like "jian"
     * matches sixteen words and only twelve fit on the screen, so
     * without a frequency order the common ones fall off the end.
     */
    val wordToFreq: Map<String, Int> = emptyMap(),
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
                SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source
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
                                glossSource = c.str("gloss_source"),
                            ),
                        )
                    }
                }
            }
        } ?: emptyList()

    /**
     * The words of several levels at once, in level order.
     *
     * A limit of 0 means "all of them". The level groups are not all the
     * same size -- HSK 1 has 300 words and HSK 7-9 has 5 562 -- so a
     * fixed limit would either starve the big levels or cut the small
     * ones off.
     */
    fun wordsForLevels(levels: List<String>, limit: Int = 0): List<WordEntry> = read { db ->
        if (levels.isEmpty()) return@read emptyList()
        // The levels are bound as parameters, but LIMIT cannot be bound
        // (SQLite rejects a bound LIMIT), so it is inlined as an integer.
        val limitClause = if (limit > 0) "LIMIT $limit" else ""
        val placeholders = levels.joinToString(",") { "?" }
        db.rawQuery(
            """
            SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source
            FROM words
            WHERE hsk_level IN ($placeholders)
            ORDER BY hsk_level, (freq IS NULL), freq, hanzi
            $limitClause
            """.trimIndent(),
            levels.toTypedArray(),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(c.toWordEntry())
                }
            }
        }
    } ?: emptyList()

    fun verbsForLevel(level: String, limit: Int = 100): List<WordEntry> = read { db ->
        db.rawQuery(
            """
            SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source
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
                            glossSource = c.str("gloss_source"),
                        ),
                    )
                }
            }
        }
    } ?: emptyList()

    fun wordByHanzi(hanzi: String): WordEntry? = read { db ->
        db.rawQuery(
            """
            SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source
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
                    glossSource = c.str("gloss_source"),
                )
            }
        }
    }

    /**
     * Search the dictionary.
     *
     * The pinyin is searched in its TONELESS form: a learner typing
     * "hao" has no reason to know that the character is written "hǎo",
     * and searching the tone-marked column would miss every such word.
     * The tone-marked form is still matched, for anyone who does type it.
     *
     * This is also the pinyin-prefix search the dictionary uses: the
     * query is matched against `pinyin_plain`, which is the toneless
     * form, and the results are ordered by the corpus frequency so the
     * commonest word comes first.
     */
    fun search(query: String, limit: Int = 50): List<WordEntry> {
        if (query.isBlank()) return emptyList()
        val like = "%$query%"
        return read { db ->
            db.rawQuery(
                """
                SELECT hanzi, pinyin, pinyin_tones, pos, gloss_en, gloss_bg, hsk_level, is_verb, freq, audio, gloss_source
                FROM words
                WHERE hanzi LIKE ? OR pinyin LIKE ? OR pinyin_plain LIKE ? OR gloss_en LIKE ? OR gloss_bg LIKE ?
                ORDER BY (freq IS NULL), freq, hanzi
                LIMIT $limit
                """.trimIndent(),
                arrayOf(like, like, like, like, like),
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
                                glossSource = c.str("gloss_source"),
                            ),
                        )
                    }
                }
            }
        } ?: emptyList()
    }

    /**
     * The grammar points, with their examples.
     *
     * The grammar mode needs the example sentences to quiz the learner on;
     * without them the grammar screen can only be read, which the
     * simulation shows is not learning.
     *
     * This used to exist twice -- once as `grammar()` and once as
     * `grammarWithExamples()` -- with the same body, and only one of
     * them was ever called. There is one function now.
     */
    fun grammar(level: String? = null): List<GrammarEntry> = read { db ->
        val sql = if (level == null) {
            "SELECT id, title, title_bg, level, category, summary, summary_bg, body, examples FROM grammar ORDER BY level, id"
        } else {
            "SELECT id, title, title_bg, level, category, summary, summary_bg, body, examples FROM grammar WHERE level = ? ORDER BY id"
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
                            summaryBg = c.str("summary_bg"),
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

    fun manifestValue(key: String): String? = read { db ->
        db.rawQuery("SELECT value FROM manifest WHERE key = ?", arrayOf(key)).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
    }

    /**
     * The syllables the IME index knows, and the words each one appears in.
     *
     * The whole index is a few thousand rows, so it is loaded once and
     * kept in memory: a pinyin IME has to answer on every keystroke.
     */
    fun imeIndex(): ImeIndex = read { db ->
        val syllableToWords = mutableMapOf<String, MutableList<String>>()
        db.rawQuery("SELECT syllable, hanzi FROM ime", null).use { c ->
            while (c.moveToNext()) {
                syllableToWords.getOrPut(c.str("syllable")) { mutableListOf() }
                    .add(c.str("hanzi"))
            }
        }

        val wordToPinyin = mutableMapOf<String, String>()
        val wordToGloss = mutableMapOf<String, String>()
        val wordToFreq = mutableMapOf<String, Int>()
        db.rawQuery(
            "SELECT hanzi, pinyin_plain, pinyin, gloss_bg, gloss_en, freq FROM words",
            null,
        ).use { c ->
            while (c.moveToNext()) {
                val hanzi = c.str("hanzi")
                // The IME matches against the TONELESS pinyin: the learner
                // types letters, not tone marks.
                wordToPinyin[hanzi] = c.str("pinyin_plain").ifBlank { c.str("pinyin") }
                wordToGloss[hanzi] = c.str("gloss_bg").ifBlank { c.str("gloss_en") }
                if (!c.isNull("freq")) {
                    wordToFreq[hanzi] = c.getInt("freq")
                }
            }
        }

        ImeIndex(syllableToWords, wordToPinyin, wordToGloss, wordToFreq)
    } ?: ImeIndex(emptyMap(), emptyMap(), emptyMap())

    /** A character with its stroke-order data, for the writing mode. */
    fun character(char: String): CharacterEntry? = read { db ->
        db.rawQuery(
            "SELECT char, strokes, radical, definition, medians FROM characters WHERE char = ? LIMIT 1",
            arrayOf(char),
        ).use { c ->
            if (!c.moveToFirst()) return@read null
            CharacterEntry(
                char = c.str("char"),
                strokes = c.int("strokes"),
                radical = c.str("radical"),
                definition = c.str("definition"),
                medians = c.str("medians"),
            )
        }
    }

    /**
     * Sentences that carry a Bulgarian translation.
     *
     * These are the sentences the word-order mode works on: the learner
     * rearranges the Chinese characters into the right order, and the
     * Bulgarian translation is what they are aiming at.
     *
     * The result is SHUFFLED. The query used to sort by length and take
     * the first N, which meant the learner always met the same handful
     * of shortest sentences -- "Изгаси лампата." over and over -- and
     * then ran into "Няма повече изречения" after a few dozen exercises.
     *
     * The shuffle happens in SQL so that the whole set is available and
     * the order is decided by the database rather than by a LIMIT
     * applied to a length-sorted list. The learner gets a different
     * sentence every time.
     */
    fun sentencesWithBulgarian(limit: Int = 50): List<SentenceEntry> = read { db ->
        db.rawQuery(
            """
            SELECT s.id, s.hanzi, s.pinyin, s.translation_en, s.translation_bg, s.audio_path
            FROM sentences s
            WHERE s.translation_bg != ''
            ORDER BY RANDOM()
            LIMIT $limit
            """.trimIndent(),
            null,
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(c.toSentenceEntry())
                }
            }
        }
    } ?: emptyList()

}

private fun Cursor.toWordEntry() = WordEntry(
    hanzi = str("hanzi"),
    pinyin = str("pinyin"),
    pinyinTones = str("pinyin_tones"),
    pos = str("pos"),
    glossEn = str("gloss_en"),
    glossBg = str("gloss_bg"),
    hskLevel = str("hsk_level"),
    isVerb = int("is_verb") == 1,
    freq = if (isNull("freq")) null else getInt("freq"),
    audio = strOrNull("audio"),
    glossSource = str("gloss_source"),
)

private fun Cursor.toSentenceEntry() = SentenceEntry(
    id = getLong("id"),
    hanzi = str("hanzi"),
    pinyin = str("pinyin"),
    translationEn = str("translation_en"),
    translationBg = str("translation_bg"),
    audioPath = strOrNull("audio_path"),
)

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

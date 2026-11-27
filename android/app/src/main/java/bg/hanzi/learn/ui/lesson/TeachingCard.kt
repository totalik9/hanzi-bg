package bg.hanzi.learn.ui.lesson

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * A teaching card of a reading lesson.
 *
 * The cards are hand-written JSON in curriculum/, so they are parsed
 * rather than generated: the teaching text is content, not code.
 */
data class TeachingCard(
    val kind: String,
    val title: String,
    val body: String,
    /** The examples of an "items" card. */
    val items: List<TeachingItem>,
    /** The rows of a "table" card. */
    val rows: List<List<String>>,
    /** The lines of a "reading" card: a short passage. */
    val lines: List<TeachingLine>,
    /** The comprehension question of a "reading" card. */
    val question: TeachingQuestion?,
)

/** One example on a teaching card. */
data class TeachingItem(
    val hanzi: String,
    val pinyin: String,
    val text: String,
    /**
     * The name of the clip of this example, e.g. "x_order_0.ogg".
     *
     * It is empty when the example is a WORD that the dictionary
     * holds: the clip of a word comes from the corpus. A SENTENCE is
     * hand-written and exists nowhere else, so it has to name its own
     * clip -- the same contract a passage line has.
     */
    val audio: String = "",
)

/**
 * One line of a passage.
 *
 * The Bulgarian translation is the joker: the learner reads the line and
 * opens its meaning only when they need it, so the passage itself is
 * what tests what they have learned.
 */
data class TeachingLine(
    val hanzi: String,
    val pinyin: String,
    /** The Bulgarian meaning of the line. */
    val bg: String,
    /** The name of the clip of the line, e.g. "reading_market_0.ogg". */
    val audio: String,
)

/**
 * The question of a passage: what the passage is about.
 *
 * The options are in the learner's language, because the question asks
 * for the meaning -- the Chinese side of the answer is the passage
 * itself.
 */
data class TeachingQuestion(
    val text: String,
    val options: List<String>,
    /** The index of the right option. */
    val answer: Int,
)

/**
 * Reads a teaching card.
 *
 * It returns null when the JSON is not a card: a card that cannot be
 * read is shown as the raw text, so the learner still sees something
 * instead of a blank screen.
 */
object TeachingCardParser {

    private val json = Json { ignoreUnknownKeys = true }

    fun parse(payload: String): TeachingCard? = try {
        val obj = json.parseToJsonElement(payload).jsonObject
        TeachingCard(
            kind = obj.string("kind") ?: "text",
            title = obj.string("title").orEmpty(),
            body = obj.string("body").orEmpty(),
            items = obj.array("items").map { TeachingItem(
                hanzi = it.string("hanzi").orEmpty(),
                pinyin = it.string("pinyin").orEmpty(),
                text = it.string("text").orEmpty(),
                audio = it.string("audio").orEmpty(),
            ) },
            rows = obj.arrayOfArrays("rows"),
            lines = obj.array("lines").map { TeachingLine(
                hanzi = it.string("hanzi").orEmpty(),
                pinyin = it.string("pinyin").orEmpty(),
                bg = it.string("bg").orEmpty(),
                audio = it.string("audio").orEmpty(),
            ) },
            question = (obj["question"] as? JsonObject)?.let { q ->
                TeachingQuestion(
                    text = q.string("text").orEmpty(),
                    options = q.arrayOfStrings("options"),
                    answer = q.int("answer") ?: 0,
                )
            },
        )
    } catch (e: Exception) {
        null
    }
}

private fun JsonObject.string(key: String): String? =
    this[key]?.let { element ->
        (element as? JsonPrimitive)?.takeIf { it.isString }?.content
    }

private fun JsonObject.array(key: String): List<JsonObject> =
    (this[key] as? JsonArray).orEmpty()
        .mapNotNull { element -> element as? JsonObject }

private fun JsonObject.arrayOfStrings(key: String): List<String> =
    (this[key] as? JsonArray).orEmpty()
        .mapNotNull { element -> (element as? JsonPrimitive)?.content }

/**
 * Reads a table: a list of rows, each row a list of cells.
 *
 * The rows are ARRAYS and not objects, so they cannot be read with
 * [array]: that helper keeps the objects and drops everything else,
 * and a table read that way is an empty table. The two table cards of
 * the sound system lesson were blank because of it.
 */
private fun JsonObject.arrayOfArrays(key: String): List<List<String>> =
    (this[key] as? JsonArray).orEmpty()
        .map { row ->
            (row as? JsonArray).orEmpty()
                .mapNotNull { cell -> (cell as? JsonPrimitive)?.content }
        }

/**
 * Reads an integer that may be missing or of the wrong type.
 *
 * The answer of a question is an index into the options, so a card that
 * names a wrong index must not crash the lesson: a question with no
 * right answer is a question that is never marked wrong.
 */
private fun JsonObject.int(key: String): Int? =
    (this[key] as? JsonPrimitive)?.let { element ->
        element.content.trim().toIntOrNull()
    }

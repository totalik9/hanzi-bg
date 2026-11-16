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
)

/** One example on a teaching card. */
data class TeachingItem(
    val hanzi: String,
    val pinyin: String,
    val text: String,
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
            ) },
            rows = obj.array("rows").map { row ->
                row.jsonArray.map { it.jsonPrimitive.content }
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

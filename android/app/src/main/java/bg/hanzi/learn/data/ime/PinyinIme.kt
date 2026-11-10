package bg.hanzi.learn.data.ime

/**
 * A pinyin IME for the production mode.
 *
 * The learner types plain letters ("nihao"); the engine offers the
 * Chinese words those letters could mean. It is deliberately simple --
 * a syllable index over the app's own vocabulary -- because a full IME
 * needs a general dictionary, and this app already knows the 10 896 words
 * it teaches.
 *
 * The matching is syllable by syllable, the way a real IME works: the
 * typed letters are split into syllables by the longest-prefix rule over
 * the syllables that exist in the index, and a candidate is a word whose
 * pinyin is exactly that syllable sequence.
 */
object PinyinIme {

    /** One candidate offered to the learner. */
    data class Candidate(
        val hanzi: String,
        val pinyin: String,
        val gloss: String,
    )

    /**
     * Split typed letters into syllables.
     *
     * The syllables come from the index, so only real Mandarin syllables
     * can be produced. The longest match wins, which is what makes "nihao"
     * split into "ni" + "hao" rather than "n" + "i" + "hao".
     */
    fun splitIntoSyllables(typed: String, known: Set<String>): List<String> {
        val out = mutableListOf<String>()
        var rest = typed.lowercase()
        while (rest.isNotEmpty()) {
            // The longest prefix that is a known syllable wins, so
            // "nihao" splits into "ni" + "hao" rather than "n" + "i" + ...
            val length = (rest.length downTo 1)
                .firstOrNull { len -> rest.substring(0, len) in known }
            if (length == null) {
                // No syllable matches the start of the remainder. Keep the
                // rest as one piece so the caller can show the learner
                // that the input is not understood yet.
                out += rest
                break
            }
            out += rest.substring(0, length)
            rest = rest.substring(length)
        }
        return out
    }

    /**
     * The candidates for a typed pinyin string.
     *
     * [syllableToWords] maps a syllable to the words that contain it -- a
     * word appears under each of its syllables, so "你好" is listed under
     * both "ni" and "hao".
     *
     * A candidate is a word whose pinyin EQUALS the typed syllables, or
     * STARTS WITH them: the second case is what makes the word appear
     * while the learner is still typing ("nih" already offers "你好").
     */
    fun candidates(
        typed: String,
        syllableToWords: Map<String, List<String>>,
        wordToPinyin: Map<String, String>,
        wordToGloss: Map<String, String>,
    ): List<Candidate> {
        val clean = typed.lowercase().filter { it.isLetter() }
        if (clean.isEmpty()) return emptyList()

        val known = syllableToWords.keys
        val syllables = splitIntoSyllables(clean, known)
        if (syllables.isEmpty()) return emptyList()
        val joined = syllables.joinToString("")

        // The pool: every word that contains any of the syllables typed
        // so far. Drawing from all of them, not just the last, is what
        // lets "nihao" find "你好" -- the word is listed under "ni" too.
        val pool = LinkedHashSet<String>()
        syllables.forEach { syllable ->
            syllableToWords[syllable]?.forEach { pool += it }
        }

        fun plainPinyin(word: String): String =
            wordToPinyin[word]?.lowercase()?.replace(" ", "").orEmpty()

        val exact = pool.filter { plainPinyin(it) == joined }
        val prefix = pool.filter {
            val p = plainPinyin(it)
            p.isNotEmpty() && p.startsWith(joined)
        }

        return (exact + prefix)
            .distinct()
            .sortedBy { word -> wordToGloss[word].isNullOrBlank() } // glossed words first
            .take(12)
            .map { word ->
                Candidate(
                    hanzi = word,
                    pinyin = wordToPinyin[word].orEmpty(),
                    gloss = wordToGloss[word].orEmpty(),
                )
            }
    }
}

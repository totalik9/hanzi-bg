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
     * Normalise typed pinyin to the form the index is keyed by.
     *
     * The learner types plain letters, and no phone keyboard produces
     * the umlaut: "lü" (绿, green) can only be typed as "lu", "lv" or
     * "lu:" depending on the keyboard, and a learner who types "lu"
     * must still find the word.
     *
     * So the umlaut is folded to "u" on both sides of the comparison:
     * "lü" and "lu" name the same syllable, and the word's stored pinyin
     * is folded the same way before it is compared with what was typed.
     *
     * "v" is folded to "u" as well, because that is the other
     * convention Chinese input methods use ("lv" for "lü"), and "v"
     * never appears in a Mandarin syllable in its own right.
     *
     * >>> normalise("lü")
     * 'lu'
     * >>> normalise("LV")
     * 'lu'
     * >>> normalise("lu:")
     * 'lu'
     * >>> normalise("nü3")
     * 'nu3'
     */
    fun normalise(text: String): String = text
        .lowercase()
        .replace("ü", "u")
        .replace("u:", "u")
        .replace("v", "u")

    /**
     * Split typed letters into syllables.
     *
     * The syllables come from the index, so only real Mandarin syllables
     * can be produced. The longest match wins, which is what makes "nihao"
     * split into "ni" + "hao" rather than "n" + "i" + "hao".
     *
     * A SPACE separates syllables and is kept: "qu nian" is two
     * syllables, and reading it as one string ("qunian") makes the
     * greedy splitter pick "qun" + "ian", which are real syllables too.
     * The word is then never in the candidate pool and the learner
     * cannot produce it at all.
     *
     * The typed text is normalised first, so "lü" is split as "lu" and
     * the index -- which is keyed by the normalised form -- is found.
     */
    fun splitIntoSyllables(typed: String, known: Set<String>): List<String> {
        val out = mutableListOf<String>()
        for (chunk in normalise(typed).split(' ').filter { it.isNotEmpty() }) {
            var rest = chunk
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
     *
     * [wordToFreq] holds the corpus frequency rank of each word. It is
     * what decides the order: sixteen words are pronounced "jian" and
     * only twelve fit in the list, so without a frequency order the
     * common ones fall off the end and the learner cannot produce them.
     */
    fun candidates(
        typed: String,
        syllableToWords: Map<String, List<String>>,
        wordToPinyin: Map<String, String>,
        wordToGloss: Map<String, String>,
        wordToFreq: Map<String, Int> = emptyMap(),
    ): List<Candidate> {
        // The letters and the spaces are kept: the space is what tells
        // "qu nian" from "qunian", and the pinyin of a word is written
        // with spaces too.
        val clean = typed.lowercase().filter { it.isLetter() || it == ' ' }
        if (clean.isBlank()) return emptyList()

        val known = syllableToWords.keys
        val syllables = splitIntoSyllables(clean, known)
        if (syllables.isEmpty()) return emptyList()
        val joined = syllables.joinToString(" ")
        val joinedFlat = joined.replace(" ", "")

        // The pool: every word that contains any of the syllables typed
        // so far. Drawing from all of them, not just the last, is what
        // lets "nihao" find "你好" -- the word is listed under "ni" too.
        val pool = LinkedHashSet<String>()
        syllables.forEach { syllable ->
            syllableToWords[syllable]?.forEach { pool += it }
        }

        // The stored pinyin is normalised the same way the typed text
        // is, so that "lu" finds the word whose pinyin is "lü". Without
        // this the 76 words that carry the umlaut are unreachable: the
        // learner types "lu", gets nothing, and concludes the app is
        // broken.
        fun plainPinyin(word: String): String =
            normalise(wordToPinyin[word]?.replace(" ", "") ?: "")

        val exact = pool.filter { plainPinyin(it) == joinedFlat }
        val prefix = pool.filter {
            val p = plainPinyin(it)
            p.isNotEmpty() && p.startsWith(joinedFlat)
        }

        return (exact + prefix)
            .distinct()
            // The order matters twice over. An EXACT match comes before a
            // word that merely starts with the same letters: "wei" is
            // nine words, but the list also holds ninety-two that begin
            // with "wei", and without this rule the exact ones fall off
            // the end of the list.
            //
            // Within each group the commonest word comes first, the way a
            // real IME orders its candidates. Words with a gloss come
            // before words without one, because a learner cannot choose a
            // word they cannot read.
            .sortedWith(
                compareBy(
                    { word: String -> if (word in exact) 0 else 1 },
                    { word: String -> wordToFreq[word] ?: Int.MAX_VALUE },
                    { word: String -> wordToGloss[word].isNullOrBlank() },
                )
            )
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

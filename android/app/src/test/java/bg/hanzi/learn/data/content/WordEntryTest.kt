package bg.hanzi.learn.data.content

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the gloss provenance.
 *
 * The column `gloss_source` says whether a Bulgarian gloss was written
 * by a person or by the machine. The app shows that to the learner,
 * because a machine translation can be wrong and a learner who does not
 * know that will trust it.
 */
class WordEntryTest {

    private fun word(source: String) = WordEntry(
        hanzi = "和",
        pinyin = "hé",
        pinyinTones = "he2",
        pos = "conj.",
        glossEn = "and; together with",
        glossBg = "и",
        hskLevel = "1",
        isVerb = false,
        freq = 42,
        audio = null,
        glossSource = source,
    )

    @Test
    fun `a human gloss is marked as human`() {
        assertTrue(word("human").isHumanGloss)
    }

    @Test
    fun `a machine gloss is not marked as human`() {
        assertFalse(word("machine").isHumanGloss)
    }

    @Test
    fun `a word with no Bulgarian gloss is not marked as human`() {
        // The source is empty when there is no Bulgarian gloss at all, so
        // an empty source must not be read as "a person wrote this".
        assertFalse(word("").isHumanGloss)
    }

    @Test
    fun `the source is kept verbatim`() {
        assertEquals("machine", word("machine").glossSource)
    }
}

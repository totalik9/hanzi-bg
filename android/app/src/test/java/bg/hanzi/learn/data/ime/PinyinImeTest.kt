package bg.hanzi.learn.data.ime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the pinyin IME.
 *
 * The IME is the answer to the simulation's finding that production was
 * 0/20: it is the only part of the app that lets the learner OUTPUT
 * Chinese, so a wrong syllable split means the mode does not work.
 */
class PinyinImeTest {

    /** The syllables of a small vocabulary, with one word each. */
    private val syllables = setOf("ni", "hao", "shi", "jie", "guo", "ren", "ma")

    private val syllableToWords = mapOf(
        "ni" to listOf("你", "泥", "你好"),
        "hao" to listOf("好", "你好"),
        "shi" to listOf("是", "市"),
        "jie" to listOf("姐"),
        "guo" to listOf("过", "国"),
        "ren" to listOf("人"),
        "ma" to listOf("吗"),
    )

    private val wordToPinyin = mapOf(
        "你" to "ni",
        "泥" to "ni",
        "好" to "hao",
        "是" to "shi",
        "市" to "shi",
        "姐" to "jie",
        "过" to "guo",
        "国" to "guo",
        "人" to "ren",
        "吗" to "ma",
        "你好" to "ni hao",
    )

    private val wordToGloss = mapOf(
        "你" to "ти",
        "泥" to "кал",
        "好" to "добър",
        "是" to "е",
        "市" to "град",
        "姐" to "сестра",
        "过" to "минавам",
        "国" to "държава",
        "人" to "човек",
        "吗" to "ли",
        "你好" to "здравей",
    )

    @Test
    fun splitsIntoTheLongestKnownSyllable() {
        assertEquals(listOf("ni", "hao"), PinyinIme.splitIntoSyllables("nihao", syllables))
        assertEquals(listOf("shi"), PinyinIme.splitIntoSyllables("shi", syllables))
        assertEquals(listOf("guo", "ren"), PinyinIme.splitIntoSyllables("guoren", syllables))
    }

    @Test
    fun keepsAnUnknownTailAsOnePiece() {
        // "xyz" is not a syllable: it must not be split into pieces.
        assertEquals(listOf("xyz"), PinyinIme.splitIntoSyllables("xyz", syllables))
    }

    @Test
    fun offersTheWordForACompleteSyllable() {
        val candidates = PinyinIme.candidates(
            typed = "hao",
            syllableToWords = syllableToWords,
            wordToPinyin = wordToPinyin,
            wordToGloss = wordToGloss,
        )
        assertTrue("expected 好 among $candidates", candidates.any { it.hanzi == "好" })
    }

    @Test
    fun offersTheMultiSyllableWord() {
        val candidates = PinyinIme.candidates(
            typed = "nihao",
            syllableToWords = syllableToWords,
            wordToPinyin = wordToPinyin,
            wordToGloss = wordToGloss,
        )
        assertTrue(
            "expected 你好 among $candidates",
            candidates.any { it.hanzi == "你好" },
        )
    }

    @Test
    fun offersAPrefixWhileTheLearnerIsStillTyping() {
        // "ni" is the start of "nihao": the word must appear before the
        // learner has typed the whole thing.
        val candidates = PinyinIme.candidates(
            typed = "nih",
            syllableToWords = syllableToWords,
            wordToPinyin = wordToPinyin,
            wordToGloss = wordToGloss,
        )
        assertTrue(
            "expected 你好 among $candidates",
            candidates.any { it.hanzi == "你好" },
        )
    }

    @Test
    fun doesNotOfferAWordThatDoesNotMatch() {
        val candidates = PinyinIme.candidates(
            typed = "ma",
            syllableToWords = syllableToWords,
            wordToPinyin = wordToPinyin,
            wordToGloss = wordToGloss,
        )
        assertTrue(
            "国 must not be offered for 'ma': $candidates",
            candidates.none { it.hanzi == "国" },
        )
    }

    @Test
    fun ignoresTonesAndCase() {
        val candidates = PinyinIme.candidates(
            typed = "HAO",
            syllableToWords = syllableToWords,
            wordToPinyin = wordToPinyin,
            wordToGloss = wordToGloss,
        )
        assertTrue("expected 好 among $candidates", candidates.any { it.hanzi == "好" })
    }
}

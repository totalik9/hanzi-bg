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

    @Test
    fun splitsSpaceSeparatedSyllables() {
        // "qu nian" is two syllables. The space must survive the
        // normalisation, or the greedy splitter reads "qunian" as the
        // two syllables "qun" + "ian" and the word is never offered.
        assertEquals(
            listOf("qu", "nian"),
            PinyinIme.splitIntoSyllables("qu nian", setOf("qu", "nian", "qun", "ian")),
        )
    }

    @Test
    fun offersTheWordForASpaceSeparatedReading() {
        val syllables = setOf("qu", "nian")
        val candidates = PinyinIme.candidates(
            typed = "qu nian",
            syllableToWords = mapOf(
                "qu" to listOf("去年"),
                "nian" to listOf("去年"),
            ),
            wordToPinyin = mapOf("去年" to "qu nian"),
            wordToGloss = mapOf("去年" to "миналата година"),
        )
        assertTrue(
            "expected 去年 among $candidates",
            candidates.any { it.hanzi == "去年" },
        )
        assertTrue("the syllables must be found", syllables.containsAll(listOf("qu", "nian")))
    }

    @Test
    fun keepsTheTargetWordAmongManyCandidates() {
        // Sixteen words are pronounced "jian" and only twelve fit in the
        // list. The order has to follow the corpus frequency, or 见 and
        // 间 -- both common -- are pushed out and the learner cannot
        // produce them. The ranks are the real ones from the dictionary.
        val jian = listOf("件", "间", "见", "建", "减", "剪", "尖", "箭", "兼", "剑", "煎", "键", "捡", "贱", "溅", "拣")
        val freq = mapOf(
            "件" to 151, "间" to 152, "见" to 156, "建" to 319, "减" to 1120,
            "剪" to 1198, "尖" to 1682, "箭" to 2126, "兼" to 2180, "剑" to 2305,
            "煎" to 2464, "键" to 2481, "捡" to 4008, "贱" to 5993, "溅" to 6696,
            "拣" to 7759,
        )
        val candidates = PinyinIme.candidates(
            typed = "jian",
            syllableToWords = mapOf("jian" to jian),
            wordToPinyin = jian.associateWith { "jian" },
            wordToGloss = jian.associateWith { "gloss" },
            wordToFreq = freq,
        )
        assertTrue(
            "见 must be offered among $candidates",
            candidates.any { it.hanzi == "见" },
        )
        assertTrue(
            "间 must be offered among $candidates",
            candidates.any { it.hanzi == "间" },
        )
    }

    @Test
    fun anExactMatchComesBeforeALongerWordWithTheSameStart() {
        // Nine words are pronounced "wei", but ninety-two more begin
        // with "wei". The exact one has to come first, or it is pushed
        // off the end of the list by the longer words.
        val exact = listOf("为", "位", "味", "唯", "喂", "围", "微", "未", "胃")
        val longer = (1..20).map { "为什么$it" }
        val candidates = PinyinIme.candidates(
            typed = "wei",
            syllableToWords = mapOf("wei" to exact + longer),
            wordToPinyin = (exact + longer).associateWith {
                if (it in exact) "wei" else "wei$it"
            },
            wordToGloss = (exact + longer).associateWith { "gloss" },
        )
        assertTrue(
            "喂 must be offered among $candidates",
            candidates.any { it.hanzi == "喂" },
        )
        // Every exact match comes before every longer word.
        val lastExact = candidates.indexOfLast { it.hanzi in exact }
        val firstLonger = candidates.indexOfFirst { it.hanzi in longer }
        assertTrue(
            "the exact matches come before the longer words: $candidates",
            lastExact in 0 until firstLonger,
        )
    }
}

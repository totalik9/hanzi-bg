package bg.hanzi.learn.ui.screens.practice

import bg.hanzi.learn.data.content.WordEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Tests for the pool of the listening mode.
 *
 * The listening mode asks the learner to hear a word and pick it, so
 * only a word with a pronunciation clip can be used.
 *
 * The bug these tests pin down: the level selector lets the learner
 * pick HSK 7-9, which has 5 562 words and NO audio, and the mode
 * answered with the same empty panel as a finished session. The
 * learner could not tell a missing content file from an exercise that
 * was over, so the two are told apart now.
 */
class ListeningPoolTest {

    private fun word(hanzi: String, audio: String?) = WordEntry(
        hanzi = hanzi,
        pinyin = "",
        pinyinTones = "",
        pos = "",
        glossEn = "",
        glossBg = "смисъл",
        hskLevel = "1",
        isVerb = false,
        freq = null,
        audio = audio,
    )

    @Test
    fun aLevelWithNoAudioIsReportedAsMissingAudio() {
        // HSK 7-9: every word has no clip.
        val words = listOf(word("告", null), word("文", null), word("经", null))

        assertEquals(
            ListeningEmptyReason.NO_AUDIO,
            ListeningPool.emptyReason(words, emptySet()),
        )
    }

    @Test
    fun aLevelWithNoAudioHasNothingToPlay() {
        val words = listOf(word("告", null), word("文", ""))

        assertEquals(emptyList<WordEntry>(), ListeningPool.available(words, emptySet()))
    }

    @Test
    fun anEmptyStringCountsAsNoAudio() {
        // The column can hold "" for a word that has no clip yet, and
        // such a word would put the learner in front of a button that
        // plays nothing.
        val words = listOf(word("告", ""), word("文", ""))

        assertEquals(
            ListeningEmptyReason.NO_AUDIO,
            ListeningPool.emptyReason(words, emptySet()),
        )
    }

    @Test
    fun aUsedUpLevelIsReportedAsExhausted() {
        val words = listOf(word("好", "hao.ogg"), word("你", "ni.ogg"))

        assertEquals(
            ListeningEmptyReason.EXHAUSTED,
            ListeningPool.emptyReason(words, setOf("好", "你")),
        )
    }

    @Test
    fun aLevelWithAudioIsNotEmpty() {
        val words = listOf(word("好", "hao.ogg"), word("你", "ni.ogg"))

        assertNull(ListeningPool.emptyReason(words, emptySet()))
        assertNull(ListeningPool.emptyReason(words, setOf("好")))
    }

    @Test
    fun usedWordsAreNotOfferedAgain() {
        val words = listOf(word("好", "hao.ogg"), word("你", "ni.ogg"))

        assertEquals(
            listOf("你"),
            ListeningPool.available(words, setOf("好")).map { it.hanzi },
        )
    }

    @Test
    fun aWordWithoutAGlossIsStillPlayable() {
        // The pool of the practice screen is the words WITH a Bulgarian
        // gloss, so this cannot happen in the app -- but the rule
        // itself is about the audio, not about the gloss, and a test
        // that pins it down keeps the two apart.
        val words = listOf(word("好", "hao.ogg"))

        assertEquals(
            listOf("好"),
            ListeningPool.available(words, emptySet()).map { it.hanzi },
        )
    }
}

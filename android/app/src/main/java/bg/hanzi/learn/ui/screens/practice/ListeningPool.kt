package bg.hanzi.learn.ui.screens.practice

import bg.hanzi.learn.data.content.WordEntry

/**
 * The pool the listening mode draws from.
 *
 * The listening mode asks the learner to hear a word and pick it. That
 * only works for a word that HAS a pronunciation clip, so the pool is
 * the words with audio.
 *
 * There are two ways the pool can be empty, and they are not the same
 * thing:
 *
 *   NO_AUDIO   the level has no clips at all. HSK 7-9 is in this
 *              state -- 5 562 words and no audio, because the clips
 *              for that level were never generated. The mode cannot
 *              work there, and no amount of tapping will change that.
 *
 *   EXHAUSTED  every word that has a clip has already been used in
 *              this session. The mode works; the session is over.
 *
 * The old code merged the two: both produced an empty panel, and the
 * message named a build script. A learner who picked HSK 7-9 and
 * tapped "Слушане" was told the same thing as a learner who had
 * finished the session, and neither of them could tell what to do.
 */
object ListeningPool {

    /**
     * The words that can be used for a listening exercise.
     *
     * A word with no clip is left out, and so is a word that has
     * already been used in this session.
     */
    fun available(
        words: List<WordEntry>,
        used: Set<String>,
    ): List<WordEntry> = words.filter { !it.audio.isNullOrBlank() && it.hanzi !in used }

    /**
     * Why the pool is empty.
     *
     * Null when the pool is NOT empty: the mode has something to show.
     */
    fun emptyReason(
        words: List<WordEntry>,
        used: Set<String>,
    ): ListeningEmptyReason? {
        val withAudio = words.filter { !it.audio.isNullOrBlank() }
        if (withAudio.isEmpty()) return ListeningEmptyReason.NO_AUDIO
        if (withAudio.none { it.hanzi !in used }) return ListeningEmptyReason.EXHAUSTED
        return null
    }
}

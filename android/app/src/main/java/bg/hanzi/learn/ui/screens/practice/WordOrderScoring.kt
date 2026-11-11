package bg.hanzi.learn.ui.screens.practice

/**
 * The scoring of the word-order exercise, without any Android dependency.
 *
 * The simulation named "word order must be scored, not just displayed"
 * as a gap, and the scoring is what closed it. But the score was buried
 * inside the ViewModel, where no test can reach it -- so it lives here.
 */

/**
 * True when the learner's tokens are in the right order.
 *
 * The comparison is exact: the learner has to place every token, in the
 * right order, and no token may be left out or repeated.
 */
fun scoreWordOrder(picked: List<String>, correct: List<String>): Boolean =
    picked == correct

/**
 * Splits a Chinese sentence into the tokens the word-order exercise
 * works with.
 *
 * The Tatoeba corpus does not segment its sentences, so the sentence is
 * split on the Han characters: one token per character. A single
 * character is a word far too often in Chinese for this to be simple,
 * but the exercise is about the ORDER of the words, and one character per
 * token is the only split that never gets the boundaries wrong.
 *
 * Punctuation is dropped: it is not part of the order the learner is
 * being asked to reproduce.
 */
fun segmentForWordOrder(hanzi: String): List<String> =
    hanzi.filter { it.code in 0x4E00..0x9FFF }.map { it.toString() }

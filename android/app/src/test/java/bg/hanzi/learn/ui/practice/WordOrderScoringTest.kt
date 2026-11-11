package bg.hanzi.learn.ui.screens.practice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests for the word-order exercise's scoring and segmentation.
 *
 * The simulation named "word order must be scored, not just displayed"
 * as a gap. Before the scoring was pulled out of the ViewModel, nothing
 * could check it.
 */
class WordOrderScoringTest {

    @Test
    fun `the right order scores`() {
        assertTrue(scoreWordOrder(listOf("我", "爱", "学"), listOf("我", "爱", "学")))
    }

    @Test
    fun `the wrong order does not score`() {
        assertFalse(scoreWordOrder(listOf("爱", "我", "学"), listOf("我", "爱", "学")))
    }

    @Test
    fun `a missing token does not score`() {
        assertFalse(scoreWordOrder(listOf("我", "学"), listOf("我", "爱", "学")))
    }

    @Test
    fun `an extra token does not score`() {
        assertFalse(scoreWordOrder(listOf("我", "爱", "学", "了"), listOf("我", "爱", "学")))
    }

    @Test
    fun `nothing picked does not score`() {
        assertFalse(scoreWordOrder(emptyList(), listOf("我", "爱")))
    }

    @Test
    fun `repeated tokens have to be repeated`() {
        // The learner placed the two 一 in the wrong order.
        assertFalse(scoreWordOrder(listOf("一", "一", "人"), listOf("一", "人", "一")))
        assertTrue(scoreWordOrder(listOf("一", "人", "一"), listOf("一", "人", "一")))
    }

    @Test
    fun `the sentence is split into one token per character`() {
        assertEquals(listOf("我", "爱", "学"), segmentForWordOrder("我爱学"))
    }

    @Test
    fun `punctuation is dropped`() {
        assertEquals(listOf("关", "灯"), segmentForWordOrder("关灯。"))
        assertEquals(listOf("早", "上", "好"), segmentForWordOrder("早上好！"))
    }

    @Test
    fun `an empty sentence gives no tokens`() {
        assertEquals(emptyList<String>(), segmentForWordOrder(""))
        assertEquals(emptyList<String>(), segmentForWordOrder("!!!"))
    }

    @Test
    fun `latin text in a sentence is dropped`() {
        // The corpus is Chinese, but a stray latin character must not
        // become a token the learner has to place.
        assertEquals(listOf("好"), segmentForWordOrder("好abc"))
    }
}

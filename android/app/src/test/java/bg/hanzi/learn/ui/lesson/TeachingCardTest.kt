package bg.hanzi.learn.ui.lesson

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * How a teaching card is read.
 *
 * The cards are hand-written JSON, and a card that is read wrongly is
 * a card the learner sees empty: the two table cards of the sound
 * system lesson showed their title and nothing else, because the rows
 * are arrays and the reader kept only the objects. A test needs no
 * device, and this one has to exist.
 */
class TeachingCardTest {

    @Test
    fun aTableCardKeepsItsRows() {
        val card = TeachingCardParser.parse(
            """
            {"kind":"table","title":"Начални съгласни","body":"",
             "rows":[["b","p","m","f"],["d","t","n","l"]]}
            """.trimIndent()
        )

        assertNotNull(card)
        assertEquals("table", card!!.kind)
        assertEquals(2, card.rows.size)
        assertEquals(listOf("b", "p", "m", "f"), card.rows[0])
        assertEquals(listOf("d", "t", "n", "l"), card.rows[1])
    }

    @Test
    fun anItemsCardKeepsItsExamples() {
        val card = TeachingCardParser.parse(
            """
            {"kind":"items","title":"Една дума, два записа","body":"",
             "items":[{"hanzi":"你好","pinyin":"nǐ hǎo","text":"здравей"}]}
            """.trimIndent()
        )

        assertNotNull(card)
        assertEquals(1, card!!.items.size)
        assertEquals("你好", card.items[0].hanzi)
        assertEquals("nǐ hǎo", card.items[0].pinyin)
        assertEquals("здравей", card.items[0].text)
        // A WORD takes its clip from the corpus, so it names none.
        assertEquals("", card.items[0].audio)
    }

    @Test
    fun anExampleThatNamesItsOwnClipKeepsIt() {
        // A SENTENCE is hand-written and exists nowhere else, so it
        // names its own clip -- the same contract a passage line has.
        val card = TeachingCardParser.parse(
            """
            {"kind":"items","title":"Редът на думите","body":"",
             "items":[{"hanzi":"我吃苹果","pinyin":"Wǒ chī píngguǒ",
                       "text":"Аз ям ябълки","audio":"x_order_i0.ogg"}]}
            """.trimIndent()
        )

        assertNotNull(card)
        assertEquals(1, card!!.items.size)
        assertEquals("我吃苹果", card.items[0].hanzi)
        assertEquals("x_order_i0.ogg", card.items[0].audio)
    }

    @Test
    fun aReadingCardKeepsItsLinesAndItsQuestion() {
        val card = TeachingCardParser.parse(
            """
            {"kind":"reading","title":"На пазара","body":"Прочети.",
             "lines":[{"hanzi":"我要三个苹果。","pinyin":"Wǒ yào sān gè píngguǒ.",
                       "bg":"Искам три ябъка.","audio":"reading_market_1.ogg"}],
             "question":{"text":"Какво иска купувачът?",
                         "options":["Три ябъка","Пет мандарина"],"answer":0}}
            """.trimIndent()
        )

        assertNotNull(card)
        assertEquals("reading", card!!.kind)
        assertEquals(1, card.lines.size)
        assertEquals("我要三个苹果。", card.lines[0].hanzi)
        assertEquals("Искам три ябъка.", card.lines[0].bg)
        assertEquals("reading_market_1.ogg", card.lines[0].audio)

        val question = card.question
        assertNotNull(question)
        assertEquals("Какво иска купувачът?", question!!.text)
        assertEquals(2, question.options.size)
        assertEquals(0, question.answer)
    }

    @Test
    fun aCardThatCannotBeReadIsNull() {
        assertEquals(null, TeachingCardParser.parse("not json at all"))
    }

    @Test
    fun aQuestionWithoutAnAnswerFallsBackToTheFirstOption() {
        val card = TeachingCardParser.parse(
            """
            {"kind":"reading","question":{"text":"Какво?","options":["А","Б"]}}
            """.trimIndent()
        )

        assertNotNull(card)
        assertTrue(card!!.question!!.answer >= 0)
    }
}

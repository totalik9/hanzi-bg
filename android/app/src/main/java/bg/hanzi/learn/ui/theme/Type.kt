package bg.hanzi.learn.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * CJK glyphs are visually ~1.8x denser than Latin text. Learners memorise
 * stroke shape and radical structure, so the target script must be rendered
 * large enough to actually read the strokes. Latin/Bulgarian UI text stays
 * at the Material default.
 */
object LangType {

    const val TARGET_SCALE = 1.8f
    const val TRANSLITERATION_SCALE = 0.85f

    enum class Kind { TARGET, TRANSLITERATION, NATIVE, UI }

    /**
     * Scale a style for a given script.
     *
     * The LINE HEIGHT has to be scaled as well. Scaling only the font size
     * leaves the line box at its original height, and the CJK glyphs then
     * overflow it and overlap the next line -- which is what the grammar
     * quiz looked like on the emulator.
     */
    fun scaled(style: TextStyle, kind: Kind): TextStyle {
        val factor = when (kind) {
            Kind.TARGET -> TARGET_SCALE
            Kind.TRANSLITERATION -> TRANSLITERATION_SCALE
            Kind.NATIVE, Kind.UI -> 1.0f
        }
        return style.copy(
            fontSize = (style.fontSize.value * factor).sp,
            lineHeight = (style.lineHeight.value * factor).sp,
        )
    }

    /**
     * A style for a TARGET word that fits on ONE line.
     *
     * A CJK glyph is about one em wide, so a word of n characters
     * needs n * size to fit the card. The full TARGET_SCALE is right
     * for one character and for two, but a three-character word at
     * that size is 308 sp wide -- wider than a 320 dp screen -- so it
     * wraps, and the wrapped word pushes the button of the card below
     * the bottom of the screen. The learner then cannot leave the
     * card at all: the lesson stops on the word.
     *
     * The sizes below are measured against the 272 dp of usable width
     * on a 320 dp screen (320 minus 24 dp of padding on each side).
     *
     * @param style the base style
     * @param characters how many characters the word has
     */
    fun target(style: TextStyle, characters: Int): TextStyle {
        val factor = when {
            characters <= 2 -> TARGET_SCALE
            characters == 3 -> 1.5f
            characters == 4 -> 1.15f
            else -> 0.9f
        }
        return style.copy(
            fontSize = (style.fontSize.value * factor).sp,
            lineHeight = (style.lineHeight.value * factor).sp,
        )
    }
}

/**
 * FontFamily.SansSerif resolves to Roboto for Latin/Cyrillic and falls
 * through to the system Noto Sans CJK for Chinese code points. Never use
 * FontFamily.Default here — that maps to Roboto, which has no CJK glyphs.
 */
private val AppFontFamily = FontFamily.SansSerif

val HanziTypography = Typography(
    displayLarge = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 57.sp,
        lineHeight = 64.sp,
    ),
    displayMedium = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 45.sp,
        lineHeight = 52.sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 32.sp,
        lineHeight = 40.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 28.sp,
        lineHeight = 36.sp,
    ),
    headlineSmall = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 24.sp,
        lineHeight = 32.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        lineHeight = 24.sp,
    ),
    titleSmall = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = AppFontFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 16.sp,
    ),
)

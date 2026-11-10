package bg.hanzi.learn.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val LightColors = lightColorScheme(
    primary = Color(0xFF8E2A2A),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFF9DEDC),
    onPrimaryContainer = Color(0xFF3B0908),
    secondary = Color(0xFF2E6E5B),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFB8EBD9),
    onSecondaryContainer = Color(0xFF002019),
    tertiary = Color(0xFF7A5900),
    background = Color(0xFFFFFBF7),
    onBackground = Color(0xFF241C18),
    surface = Color(0xFFFFFBF7),
    onSurface = Color(0xFF241C18),
    surfaceVariant = Color(0xFFF5DDD9),
    onSurfaceVariant = Color(0xFF534341),
    outline = Color(0xFF857370),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFF2B8B5),
    onPrimary = Color(0xFF561918),
    primaryContainer = Color(0xFF722322),
    onPrimaryContainer = Color(0xFFF9DEDC),
    secondary = Color(0xFF9CCFBE),
    onSecondary = Color(0xFF00382C),
    secondaryContainer = Color(0xFF125142),
    onSecondaryContainer = Color(0xFFB8EBD9),
    tertiary = Color(0xFFF0C048),
    background = Color(0xFF1C1512),
    onBackground = Color(0xFFEDE0DC),
    surface = Color(0xFF1C1512),
    onSurface = Color(0xFFEDE0DC),
    surfaceVariant = Color(0xFF534341),
    onSurfaceVariant = Color(0xFFD8C2BE),
    outline = Color(0xFFA08C89),
)

@Composable
fun HanziTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)

        darkTheme -> DarkColors
        else -> LightColors
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = HanziTypography,
        content = content,
    )
}

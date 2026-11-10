package bg.hanzi.learn

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import bg.hanzi.learn.ui.HanziNavHost
import bg.hanzi.learn.ui.theme.HanziTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        // Android 16 (API 36) enforces edge-to-edge for apps targeting 36;
        // opting out is no longer possible, so insets are handled in the
        // Compose tree via Scaffold.
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            HanziTheme {
                HanziNavHost()
            }
        }
    }
}

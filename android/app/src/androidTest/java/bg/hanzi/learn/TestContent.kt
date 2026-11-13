package bg.hanzi.learn

import android.content.Context
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File

/**
 * Points the app at the fixture content database.
 *
 * The instrumented tests run against a small database with six words
 * instead of the 19.7 MB one that ships in the APK. The fixture is
 * copied out of the test assets first, because SQLite cannot open a
 * file that is inside the APK's zip.
 */
object TestContent {

    /**
     * The fixture, copied out of the test assets and ready to open.
     *
     * The fixture is read from the TEST APK's assets, never from the
     * app's: the app's assets hold the real content.db, which the
     * build copies in, and reading that would silently run the tests
     * against the shipping database instead of the fixture.
     */
    fun install(): String {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val appContext: Context = instrumentation.targetContext
        val testContext: Context = instrumentation.context
        val assetName = "content/content.db"

        val asset = testContext.assets.open(assetName)

        val dir = File(appContext.filesDir, "test-content").apply { mkdirs() }
        val target = File(dir, "content.db")
        asset.use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        }
        return target.absolutePath
    }
}

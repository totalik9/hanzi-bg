package bg.hanzi.learn.data.content

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Opens the bundled, read-only content database (content.db).
 *
 * The file ships inside the APK as an asset. Assets cannot be opened by
 * SQLite directly, so it is copied once into internal storage on first
 * launch and reopened from there afterwards.
 *
 * The copy is versioned by the stamp that ships NEXT to the database --
 * the hash of its bytes. It used to be versioned by the asset's length,
 * and that is not enough: a rebuilt database with two more lessons in it
 * came out exactly as long as the old one, so the app kept the old
 * content and the new lessons never appeared. The timestamp of the asset
 * cannot be used either: the APK normalises every zip entry to
 * 1981-01-01, so every build looks the same.
 */
@Singleton
class ContentDatabaseProvider @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    private var cached: SQLiteDatabase? = null

    /**
     * The file the database is opened from, when it is set directly.
     *
     * The instrumented tests point this at a fixture database instead
     * of the 19.7 MB one that ships in the APK: the tests assert on
     * what the screens show, and a fixture holding six words says
     * everything they need to. It is also what makes the tests fast
     * enough to run in CI.
     *
     * It is set by the test before the app starts, and it is null in
     * the app itself.
     */
    @Volatile
    var overridePath: String? = null

    val database: SQLiteDatabase?
        get() = cached ?: open().also { cached = it }

    private fun open(): SQLiteDatabase? = try {
        val override = overridePath ?: testOverridePath
        if (override != null) {
            SQLiteDatabase.openDatabase(
                override,
                null,
                SQLiteDatabase.OPEN_READONLY,
            )
        } else {
            val target = ensureCopied()
            if (target != null) {
                SQLiteDatabase.openDatabase(
                    target.absolutePath,
                    null,
                    SQLiteDatabase.OPEN_READONLY,
                )
            } else {
                null
            }
        }
    } catch (e: IOException) {
        Log.e(TAG, "Unable to open content database", e)
        null
    } catch (e: IllegalStateException) {
        Log.e(TAG, "Content database is corrupt", e)
        null
    }

    /**
     * Returns the copied content.db path, or null when the asset is absent
     * (the app then shows a "run the extraction pipeline" state).
     */
    private fun ensureCopied(): File? {
        val assetFd = try {
            context.assets.openFd(ASSET_NAME)
        } catch (e: IOException) {
            Log.w(TAG, "Asset $ASSET_NAME not present in the APK", e)
            return null
        }

        assetFd.use { fd ->
            val length = fd.length

            val dir = File(context.filesDir, "content").apply { mkdirs() }
            val target = File(dir, "content.db")
            val marker = File(dir, "content.db.version")

            // The stamp of this build. The hash of the bytes when the
            // build ships one, and the length when it does not -- a
            // database built by hand, or the test fixture.
            val stamp = readVersionAsset() ?: "size:$length"

            val needsCopy = !target.exists() ||
                marker.readTextOrNull() != stamp

            if (needsCopy) {
                Log.i(TAG, "Copying content.db ($length bytes) into internal storage")
                context.assets.open(ASSET_NAME).use { input ->
                    target.outputStream().use { output -> input.copyTo(output) }
                }
                marker.writeText(stamp)
            }
            return target
        }
    }

    /**
     * The stamp that ships next to the database, or null when the APK
     * does not carry one.
     */
    private fun readVersionAsset(): String? = try {
        context.assets.open(VERSION_ASSET).use { input ->
            input.readBytes().toString(Charsets.UTF_8).trim().ifBlank { null }
        }
    } catch (e: IOException) {
        null
    }

    private fun File.readTextOrNull(): String? = try {
        if (exists()) readText() else null
    } catch (e: IOException) {
        null
    }

    companion object {
        /**
         * The database the instrumented tests run against.
         *
         * The provider is created by Hilt before any test code runs, so
         * the path has to be reachable without an instance. It is null
         * in the app, and it is set by the test runner's setup.
         */
        @Volatile
        @JvmStatic
        var testOverridePath: String? = null
    }
}

private const val TAG = "ContentDb"
private const val ASSET_NAME = "content/content.db"

/**
 * The stamp of the database, written by the pipeline next to it.
 *
 * It is a hash of the bytes and not the length: a rebuild that does not
 * change the length of the database is still a new database.
 */
private const val VERSION_ASSET = "content/version.txt"

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "bg.hanzi.learn"
    compileSdk = 36

    defaultConfig {
        applicationId = "bg.hanzi.learn"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true

        // Content DB + audio are shipped as assets and copied to internal
        // storage on first launch (assets are read-only and cannot be queried).
        ksp { arg("room.schemaLocation", "$projectDir/schemas") }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            // No native code in this app -> 16 KB page size requirement is
            // satisfied trivially. Kept explicit so it stays true if a
            // native dependency is ever added.
            ndk { debugSymbolLevel = "NONE" }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    buildFeatures {
        compose = true
    }

    packaging {
        jniLibs {
            // Required for 16 KB page-size alignment on Android 15+ devices.
            useLegacyPackaging = false
        }
        resources {
            excludes += setOf(
                "/META-INF/{AL2.0,LGPL2.1}",
                "META-INF/DEPENDENCIES",
            )
        }
    }

    androidResources {
        // The .db must stay uncompressed: it is copied out of the APK
        // byte-for-byte on first launch, so a compressed entry would
        // break the copy. Audio stays compressed to keep the APK small —
        // Media3 reads it through AssetDataSource, which streams
        // transparently.
        noCompress += listOf("db")
    }
}

/**
 * Release signing.
 *
 * The release build is UNSIGNED unless a keystore is supplied, because a
 * signing key is a secret and a secret does not belong in a repository.
 * An unsigned APK cannot be installed, so a release that is meant to be
 * handed to somebody needs a key -- and the key has to be the SAME one
 * for every version, because Android identifies an app by its signing
 * certificate and not by its package name. A new key means the user has
 * to uninstall the old app first, which loses their review history.
 *
 * Two ways to supply the key, in this order:
 *
 *   1. `android/keystore.properties` -- the Android Studio convention.
 *      The file is gitignored; a copy of it lives outside the
 *      repository together with the key itself.
 *   2. Environment variables: HANZI_KEYSTORE, HANZI_KEYSTORE_PASSWORD,
 *      HANZI_KEY_ALIAS, HANZI_KEY_PASSWORD. This is the form a CI
 *      runner uses.
 *
 * The properties file is read at configuration time, and the signing
 * config is only created when all four values are there. A half-filled
 * file fails the build loudly rather than quietly producing an unsigned
 * APK that looks signed in a filename.
 */
/**
 * The properties file is parsed by hand rather than with
 * java.util.Properties, because Properties treats a backslash as an
 * escape character: a Windows path like C:\Users\me\key.jks comes out
 * of Properties as C:Usersmekey.jks and the build then says the
 * keystore "was not found" for a file that is sitting right there.
 * A hand-written parser keeps the path exactly as the user wrote it.
 */
val keystoreProperties = mutableMapOf<String, String>()
val keystorePropertiesFile = rootProject.file("keystore.properties")
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.forEachLine { rawLine ->
        val line = rawLine.trim()
        if (line.isEmpty() || line.startsWith("#") || line.startsWith("!")) {
            return@forEachLine
        }
        val separator = line.indexOf('=')
        if (separator <= 0) {
            return@forEachLine
        }
        keystoreProperties[line.substring(0, separator).trim()] =
            line.substring(separator + 1).trim()
    }
}

fun signingValue(property: String, environmentVariable: String): String? =
    (keystoreProperties[property] ?: System.getenv(environmentVariable))
        ?.takeIf { it.isNotBlank() }

val releaseStoreFile = signingValue("storeFile", "HANZI_KEYSTORE")
val releaseStorePassword = signingValue("storePassword", "HANZI_KEYSTORE_PASSWORD")
val releaseKeyAlias = signingValue("keyAlias", "HANZI_KEY_ALIAS")
val releaseKeyPassword = signingValue("keyPassword", "HANZI_KEY_PASSWORD")

val releaseSigningValues = mapOf(
    "storeFile" to releaseStoreFile,
    "storePassword" to releaseStorePassword,
    "keyAlias" to releaseKeyAlias,
    "keyPassword" to releaseKeyPassword,
)
val missingSigningValues = releaseSigningValues.filterValues { it == null }.keys
if (missingSigningValues.isNotEmpty() && missingSigningValues.size != releaseSigningValues.size) {
    error(
        "The release signing key is only half configured: " +
            "${missingSigningValues.joinToString(", ")} missing. " +
            "Either fill in android/keystore.properties completely, or remove it.",
    )
}
val hasReleaseSigning = missingSigningValues.isEmpty()

if (hasReleaseSigning) {
    android {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                // minSdk is 26, so the v1 (JAR) signature is still needed
                // for the oldest supported devices; v2 covers 24+ and v3
                // adds the rotation support of 28+.
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
        buildTypes {
            getByName("release") {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
    logger.lifecycle("Release signing: enabled (${releaseStoreFile})")
} else {
    logger.warn(
        "Release signing: DISABLED -- the release APK will be UNSIGNED and " +
            "cannot be installed. Put a keystore.properties in android/ or set " +
            "HANZI_KEYSTORE, HANZI_KEYSTORE_PASSWORD, HANZI_KEY_ALIAS and " +
            "HANZI_KEY_PASSWORD.",
    )
}

/**
 * Copies the generated content artefacts into the APK assets.
 *
 * The content database is a build artefact: 08_build_content_db.py
 * regenerates it from the pipeline, and it is far too large to keep in
 * version control. The copy is skipped when the artefact is missing, so
 * a fresh clone can still build the app -- it just ships without
 * content, and the app shows its "run the extraction pipeline" state.
 *
 * The assets go into a GENERATED directory, not into src/main/assets.
 * Writing into the source tree makes Gradle's lint tasks see the assets
 * folder as both an input and the output of another task, and the
 * release build fails with "uses this output of task ':app:syncContentDb'
 * without declaring an explicit or implicit dependency". A generated
 * directory has no such conflict.
 *
 * The paths are resolved to plain Files at configuration time: the
 * configuration cache cannot serialise a Gradle script object captured
 * by a task predicate.
 */
val contentDbFile = rootProject.layout.projectDirectory.file("../data/content.db").asFile
val audioSourceDir = rootProject.layout.projectDirectory.dir("../data/audio").asFile
val generatedAssetDir = layout.buildDirectory.dir("generated/assets").get().asFile
val contentAssetDir = File(generatedAssetDir, "content")
val audioAssetDir = File(generatedAssetDir, "audio")

val syncContentDb by tasks.registering(Copy::class) {
    from(contentDbFile)
    into(contentAssetDir)
    // The predicate reads the task's own inputs rather than a script
    // property: a lambda that captures the Gradle script cannot be
    // serialised into the configuration cache.
    onlyIf { task -> task.inputs.files.files.any { f -> f.exists() } }
}

// Sync, not Copy: a Copy task leaves behind whatever was in the
// destination before, so a corpus that was MP3 and is now Opus would
// ship BOTH -- 97 MB of assets instead of 14 MB. Sync removes the
// files that are no longer in the source.
val syncAudio by tasks.registering(Sync::class) {
    from(audioSourceDir) {
        // The clips are Opus in an Ogg container: the Edge TTS MP3s were
        // a fixed 11 232 bytes each, 83 % of them digital silence, and
        // an MP3 cannot be compressed again in the APK. Media3 plays Ogg
        // through the platform decoder, which has had Opus since
        // Android 5.0, so no extra dependency is needed.
        include("*.ogg")
    }
    into(audioAssetDir)
    onlyIf { task -> task.inputs.files.files.any { f -> f.exists() } }
}

// The generated assets are part of the app's assets, and every task that
// packages them has to run after the copies.
android.sourceSets.getByName("main").assets.srcDir(generatedAssetDir)

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(syncContentDb, syncAudio)
}

// The lint tasks read the assets folder, and that folder is the output of
// the two copy tasks above. Gradle refuses to guess the order and fails
// the release build with "uses this output of task ':app:syncContentDb'
// without declaring an explicit or implicit dependency", so the order is
// declared here.
tasks.matching { it.name.contains("Lint") || it.name.contains("lint") }.configureEach {
    dependsOn(syncContentDb, syncAudio)
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.splashscreen)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.androidx.hilt.navigation.compose)

    implementation(libs.media3.exoplayer)
    implementation(libs.media3.common)

    implementation(libs.kotlinx.serialization.json)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.serialization.json)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
}

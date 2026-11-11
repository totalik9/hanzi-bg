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
        versionCode = 1
        versionName = "0.1.0"

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

val syncAudio by tasks.registering(Copy::class) {
    from(audioSourceDir) {
        include("*.mp3")
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

    implementation(libs.coil.compose)
    implementation(libs.datastore.preferences)
    implementation(libs.kotlinx.serialization.json)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.serialization.json)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
}

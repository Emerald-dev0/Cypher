import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}

// ─────────────────────────────────────────────────────────────
// Application identity
//
// Reverse-domain id derived from the GitHub org so it is globally unique and
// cannot be squatted. If the project later acquires a domain (e.g. cypher.app),
// change `applicationId` here AND the `namespace`, then move MainActivity.kt to
// the matching package directory. Changing it after a Play Store upload breaks
// update continuity, so settle it before the first public release.
// ─────────────────────────────────────────────────────────────
val cypherApplicationId = "io.github.emerald_dev0.cypher"

// ─────────────────────────────────────────────────────────────
// Release signing
//
// Reads android/key.properties (git-ignored) or the ANDROID_SIGNING_* env vars
// injected by CI. Falls back to the debug keystore ONLY for local dev builds so
// `flutter run --release` keeps working. A release published to the Play Store
// or attached to a GitHub Release MUST be signed with the real key — CI fails
// the build if it is missing (see .github/workflows/release-mobile.yml).
// ─────────────────────────────────────────────────────────────
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

fun signingValue(key: String): String? =
    keystoreProperties.getProperty(key) ?: System.getenv("ANDROID_SIGNING_${key.uppercase()}")

val hasReleaseSigning = !signingValue("storeFile").isNullOrEmpty()

android {
    namespace = cypherApplicationId
    compileSdk = flutter.compileSdkVersion
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    defaultConfig {
        applicationId = cypherApplicationId
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        resourceConfigurations += listOf("en")
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(signingValue("storeFile")!!)
                storePassword = signingValue("storePassword")
                keyAlias = signingValue("keyAlias")
                keyPassword = signingValue("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("release")
            } else {
                logger.warn(
                    "CYPHER: no release signing key found — falling back to the debug " +
                    "keystore. This build CANNOT be published. Provide android/key.properties " +
                    "or the ANDROID_SIGNING_* environment variables."
                )
                signingConfigs.getByName("debug")
            }
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    packaging {
        resources {
            excludes += listOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*")
        }
    }

    dependenciesInfo {
        // Never embed the Play dependency metadata block: it forces a Play
        // signature check and breaks direct APK distribution via GitHub Releases.
        includeInApk = false
        includeInBundle = true
    }
}

// ─────────────────────────────────────────────────────────────
// AGP 8.7.2 compatibility pins.
// Some transitive AndroidX artefacts request versions that need AGP 8.9+, which
// hangs on Windows. Pin the two offenders until the AGP upgrade lands
// (docs/plans/rebuild-mobile-ui.md · P2-M9).
// ─────────────────────────────────────────────────────────────
configurations.all {
    resolutionStrategy.eachDependency {
        if (requested.group == "androidx.core") useVersion("1.13.1")
        if (requested.group == "androidx.browser") useVersion("1.8.0")
    }
}

kotlin {
    jvmToolchain(17)
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

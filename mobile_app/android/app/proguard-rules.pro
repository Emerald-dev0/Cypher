# ─────────────────────────────────────────────────────────────
# CYPHER Android ProGuard / R8 rules
#
# R8 full mode is aggressive with reflection-heavy Flutter plugins. These rules
# keep the platform-channel and JSON-serialization surfaces intact.
# ─────────────────────────────────────────────────────────────

# Flutter engine + platform channels
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
-keepclassmembers class * {
    @io.flutter.plugin.common.MethodChannel$MethodCallHandler *;
}

# CYPHER native share-sheet bridge (MainActivity.kt)
-keep class io.github.emerald_dev0.cypher.** { *; }

# Keep native method names used over MethodChannel
-keepclasseswithmembernames class * {
    native <methods>;
}

# Plugin registrants are generated and referenced by name
-keep class * extends io.flutter.plugin.common.PluginRegistrant

# Common plugin keep rules
-keep class androidx.** { *; }
-dontwarn androidx.**

# OkHttp / Kotlin coroutines warnings surfaced by transitive deps
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# Flutter's engine references Google Play Core (splitinstall / SplitCompat)
# so deferred-component loading works when the app is installed from Play.
# This project ships APKs via GitHub Releases and explicitly sets
# `dependenciesInfo.includeInApk = false` in app/build.gradle.kts, so those
# classes are not on the classpath. AGP 8 + R8 full mode treats a missing class
# as an error (`minifyReleaseWithR8` / "Compilation failed to complete") unless
# it is told the reference is intentional.
#
# `-dontwarn`, not `-keep`: we do not want to pull Play Core in as a
# dependency just to satisfy a shrinker, and we do not want to keep classes
# that are not there. The engine already degrades to "deferred components are
# unavailable" when SplitInstallManager is missing at runtime.
-dontwarn com.google.android.play.core.splitinstall.**
-dontwarn com.google.android.play.core.splitcompat.**

# Kotlin metadata
-keep class kotlin.Metadata { *; }
-dontwarn kotlin.**

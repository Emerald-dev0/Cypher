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

# Kotlin metadata
-keep class kotlin.Metadata { *; }
-dontwarn kotlin.**

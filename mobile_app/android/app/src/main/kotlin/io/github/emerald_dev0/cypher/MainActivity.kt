package io.github.emerald_dev0.cypher

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private val CHANNEL = "app/share"
    private var sharedFiles: List<String>? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "getSharedFiles") {
                result.success(sharedFiles)
                sharedFiles = null // Clear after consumed
            } else {
                result.notImplemented()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent) {
        val action = intent.action
        val type = intent.type

        if (Intent.ACTION_SEND == action && type != null) {
            val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
            if (uri != null) {
                sharedFiles = listOf(uri.toString())
                // Notify Flutter if engine is already running
                flutterEngine?.dartExecutor?.binaryMessenger?.let {
                    MethodChannel(it, CHANNEL).invokeMethod("onSharedFiles", sharedFiles)
                }
            }
        } else if (Intent.ACTION_SEND_MULTIPLE == action && type != null) {
            val uris = intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)
            if (uris != null) {
                sharedFiles = uris.map { it.toString() }
                flutterEngine?.dartExecutor?.binaryMessenger?.let {
                    MethodChannel(it, CHANNEL).invokeMethod("onSharedFiles", sharedFiles)
                }
            }
        }
    }
}

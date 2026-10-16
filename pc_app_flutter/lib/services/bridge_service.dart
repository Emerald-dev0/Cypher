import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;

class BridgeService {
  static const String baseUrl = "http://127.0.0.1:5000";

  /// Loopback token the desktop shell uses to talk to its own node.
  ///
  /// SECURITY: this used to be the hardcoded literal
  /// `"cypher-internal-pc-app-token-2024"`, duplicated in both Dart and Python
  /// and committed to a public repository. Anyone on the same LAN could read it
  /// from GitHub and take full control of the node.
  ///
  /// The node now generates a per-install token and writes it to
  /// `<appData>/Cypher/internal_token` (0600). This mirrors
  /// `_get_internal_token()` in backend/core/server.py — keep the two in sync.
  ///
  /// `static final` is lazily evaluated on first access, so all existing
  /// synchronous call sites keep working unchanged.
  static final String internalToken = _readInternalToken();

  /// Resolves the same directory as `get_app_data_dir()` in backend/core/utils.py.
  static String _appDataDir() {
    if (Platform.isWindows) {
      final base = Platform.environment['APPDATA'] ??
          p.join(Platform.environment['USERPROFILE'] ?? '', 'AppData', 'Roaming');
      return p.join(base, 'Cypher');
    }
    if (Platform.isMacOS) {
      return p.join(Platform.environment['HOME'] ?? '', 'Library', 'Application Support', 'Cypher');
    }
    // Linux: honour XDG_CONFIG_HOME, fall back to ~/.config, matching the
    // convention the node will adopt for Linux support (roadmap Phase 3).
    final xdg = Platform.environment['XDG_CONFIG_HOME'];
    if (xdg != null && xdg.isNotEmpty) return p.join(xdg, 'cypher');
    return p.join(Platform.environment['HOME'] ?? '', '.config', 'cypher');
  }

  static String _readInternalToken() {
    try {
      final file = File(p.join(_appDataDir(), 'internal_token'));
      if (file.existsSync()) {
        final token = file.readAsStringSync().trim();
        if (token.length >= 32) return token;
      }
    } catch (e) {
      debugPrint('CYPHER: could not read internal token: $e');
    }
    // Empty token => every bridge call is rejected with 401 until the node has
    // finished first-run setup. That is the safe failure mode: the shell shows
    // "node not ready" rather than silently operating unauthenticated.
    debugPrint('CYPHER: internal token not found — waiting for node first run.');
    return '';
  }

  // [ZERO LATENCY FIX] Get the pairing code from disk if backend is still starting
  Future<String> getConnectCode() async {
    // 1. Try Network first
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/connect-code"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        return data['code'] ?? "------";
      }
    } catch (_) {}

    // 2. Fallback: Read from local storage (Persistent between restarts)
    try {
      String appData = Platform.environment['APPDATA'] ?? "";
      if (appData.isEmpty) {
        // Fallback for dev environment or if APPDATA is missing
        final home = Platform.environment['USERPROFILE'] ?? "";
        appData = p.join(home, 'AppData', 'Roaming');
      }

      final file = File(p.join(appData, "Cypher", "pairing_code.txt"));
      if (await file.exists()) {
        return await file.readAsString();
      }
    } catch (_) {}

    return "------";
  }

  // Rotate the pairing code
  Future<String> refreshConnectCode() async {
    try {
      final res = await http.post(
        Uri.parse("$baseUrl/connect-code"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 2));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        return data['code'] ?? "------";
      }
    } catch (_) {}
    return "------";
  }

  // Get linked devices
  Future<List<dynamic>> getPairedDevices() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/paired-devices"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return [];
  }

  // Get real system stats (CPU, RAM, etc)
  Future<Map<String, dynamic>> getSystemStats() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/system-stats"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        return Map<String, dynamic>.from(jsonDecode(res.body));
      }
    } catch (e) {
      debugPrint("Stats Fetch Error: $e");
    }
    return {}; // Return empty to indicate failure
  }

  // Get Network info (IP, Hostname)
  Future<Map<String, dynamic>> getNetworkInfo() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/network"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 2));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return {"pc_ip": "127.0.0.1", "hostname": "localhost"};
  }

  // Get current active file transfers
  Future<Map<String, dynamic>> getTransfers() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/files/transfers"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) return Map<String, dynamic>.from(jsonDecode(res.body));
    } catch (_) {}
    return {};
  }

  // Get shared folders
  Future<List<dynamic>> getSharedFolders() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/files/shared"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return [];
  }

  // Get security sessions
  Future<List<dynamic>> getSecuritySessions() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/guest/sessions"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        return data['sessions'] ?? [];
      }
    } catch (_) {}
    return [];
  }

  // Get dynamic activity log
  Future<List<dynamic>> getActivityLog() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/system/activity"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 2));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return [];
  }

  // Create Guest Session
  Future<Map<String, dynamic>?> createGuestSession(List<String> folders, int durationMinutes) async {
    try {
      final res = await http.post(
        Uri.parse("$baseUrl/guest/create"),
        headers: {
          "X-Auth-Token": internalToken,
          "Content-Type": "application/json",
        },
        body: jsonEncode({
          "folders": folders,
          "duration_minutes": durationMinutes,
        }),
      ).timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return null;
  }

  // End Guest Session
  Future<bool> endGuestSession(String guestToken) async {
    try {
      final res = await http.post(
        Uri.parse("$baseUrl/guest/end"),
        headers: {
          "X-Auth-Token": internalToken,
          "Content-Type": "application/json",
        },
        body: jsonEncode({"guest_token": guestToken}),
      ).timeout(const Duration(seconds: 2));
      return res.statusCode == 200;
    } catch (_) {}
    return false;
  }

  // Optimize system — returns freed MB and action list, or null on failure
  Future<Map<String, dynamic>?> optimizeSystem() async {
    try {
      final res = await http.post(
        Uri.parse("$baseUrl/system/optimize"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return null;
  }

  // Get all settings
  Future<Map<String, dynamic>> getSettings() async {
    try {
      final res = await http.get(
        Uri.parse("$baseUrl/settings"),
        headers: {"X-Auth-Token": internalToken},
      ).timeout(const Duration(seconds: 1));
      if (res.statusCode == 200) return Map<String, dynamic>.from(jsonDecode(res.body));
    } catch (_) {}
    return {};
  }

  // Save specific settings
  Future<bool> saveSettings(Map<String, dynamic> settings) async {
    try {
      final res = await http.post(
        Uri.parse("$baseUrl/settings"),
        headers: {
          "X-Auth-Token": internalToken,
          "Content-Type": "application/json",
        },
        body: jsonEncode(settings),
      ).timeout(const Duration(seconds: 2));
      return res.statusCode == 200;
    } catch (_) {}
    return false;
  }
}

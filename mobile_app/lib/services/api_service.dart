import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'storage_service.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, [this.statusCode]);
  @override
  String toString() => message;
}

/// Thrown when a call would send credentials or cleartext traffic to a
/// destination outside the local network.
///
/// Subclasses [ApiException] so it is handled by the existing error paths: every
/// caller already has to cope with [ApiException] because [_handleResponse]
/// throws it for any non-2xx status.
class PrivateNetworkRequiredException extends ApiException {
  final String host;
  PrivateNetworkRequiredException(this.host)
      : super(
          'Refusing to contact "$host" over cleartext HTTP. CYPHER only talks to '
          'a node on your local network. Public and internet destinations '
          'require TLS (roadmap P2-S1).',
        );
}

class ApiService {
  ApiService._();

  // ── Private-network enforcement ───────────────────────────────
  //
  // WHY THIS EXISTS
  // ───────────────
  // android/app/src/main/res/xml/network_security_config.xml sets
  // cleartextTrafficPermitted="true" globally, because Android's network
  // security config matches on *hostnames only* — it has no CIDR or IP-range
  // syntax, so the exception cannot be scoped to RFC1918 declaratively.
  //
  // Permitting cleartext globally with no compensation would mean a paired token
  // (sent as X-Auth-Token) could travel in plaintext to any host on the internet
  // if the stored address were ever replaced — by a bug, a malicious QR code, a
  // compromised mDNS response, or a user pasting a public IP. That file's
  // comment names this function as the compensating control; before this commit
  // the function did not exist, so the control was missing entirely.
  //
  // This is defence in depth, not the primary control. TLS (P2-S1) is the real
  // fix and will let cleartextTrafficPermitted flip to false.

  /// Whether [host] is a destination this app may contact over cleartext HTTP.
  ///
  /// Permitted: IPv4 loopback/link-local/RFC1918, IPv6 loopback/link-local/ULA
  /// (fc00::/7), `localhost`, and mDNS `.local` names — which are
  /// link-local-scoped by definition and are how DiscoveryService finds nodes.
  ///
  /// Everything else is refused. Note what is deliberately NOT permitted:
  /// CGNAT (100.64.0.0/10) is carrier infrastructure rather than a LAN, and a
  /// public hostname is exactly the case this guard exists to stop.
  static bool isPermittedTarget(String host) {
    final normalized = host.trim().toLowerCase().replaceAll(RegExp(r'^\[|\]$'), '');
    if (normalized.isEmpty) return false;

    if (normalized == 'localhost') return true;
    // mDNS names resolve only within the local link.
    if (normalized.endsWith('.local')) return true;

    final addr = InternetAddress.tryParse(normalized);
    if (addr == null) {
      // Not an IP literal and not an mDNS name. A routable hostname would need
      // DNS resolution to classify, and resolving it here would leak the query;
      // refuse instead and let TLS handle remote nodes.
      return false;
    }

    if (addr.isLoopback || addr.isLinkLocal) return true;

    final bytes = addr.rawAddress;

    if (addr.type == InternetAddressType.IPv4 && bytes.length == 4) {
      if (bytes[0] == 10) return true; // 10.0.0.0/8
      if (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) {
        return true; // 172.16.0.0/12
      }
      if (bytes[0] == 192 && bytes[1] == 168) return true; // 192.168.0.0/16
      return false;
    }

    if (addr.type == InternetAddressType.IPv6 && bytes.length == 16) {
      // fc00::/7 — unique local addresses, the IPv6 analogue of RFC1918.
      return bytes[0] == 0xfc || bytes[0] == 0xfd;
    }

    return false;
  }

  /// Throws [PrivateNetworkRequiredException] unless [host] is on the local
  /// network. Called by [_baseUrl], which every request in this class goes
  /// through, so there is exactly one place to get this right.
  static void assertPrivateTarget(String host) {
    if (!isPermittedTarget(host)) {
      throw PrivateNetworkRequiredException(host);
    }
  }

  /// The policy actually intended by network_security_config.xml, expressed for a
  /// parsed [Uri]: **cleartext HTTP only to a private host; TLS to anywhere.**
  ///
  /// Use this wherever a URL is built or consumed outside [_baseUrl] — guest
  /// share links, preview/thumbnail URLs handed to [Image.network], and any
  /// future WebView target. An `https:` URI is permitted regardless of host,
  /// which is why the GitHub release check in `update_service.dart` is unaffected.
  static void assertPrivateUri(Uri uri) {
    if (uri.scheme != 'http') return;
    assertPrivateTarget(uri.host);
  }

  static String _baseUrl(String ip) {
    assertPrivateTarget(ip);
    return 'http://$ip:5000';
  }

  static Future<Map<String, String>> _headers({bool withToken = true}) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (withToken) {
      final token = await StorageService.getToken();
      if (token != null) headers['X-Auth-Token'] = token;
    }
    return headers;
  }

  static Future<Map<String, dynamic>> _handleResponse(http.Response res) {
    if (res.statusCode == 200 || res.statusCode == 201) {
      final decoded = jsonDecode(res.body);
      if (decoded is Map<String, dynamic>) return Future.value(decoded);
      return Future.value({'data': decoded});
    }
    if (res.statusCode == 401) throw ApiException('Unauthorized — re-pair device', 401);
    if (res.statusCode == 403) throw ApiException('Access denied', 403);
    if (res.statusCode == 404) throw ApiException('Not found', 404);
    try {
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(body['error'] ?? 'Request failed (${res.statusCode})', res.statusCode);
    } catch (_) {
      throw ApiException('Request failed (${res.statusCode})', res.statusCode);
    }
  }

  // ── Connection ────────────────────────────────────────────────
  static Future<bool> ping(String ip) async {
    try {
      final res = await http.get(
        Uri.parse('${_baseUrl(ip)}/ping'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 4));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static Future<Map<String, dynamic>> getStatus(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/status'),
      headers: await _headers(withToken: false),
    ).timeout(const Duration(seconds: 6));
    return _handleResponse(res);
  }

  // ── Pairing ───────────────────────────────────────────────────
  static Future<Map<String, dynamic>> pairDevice({
    required String ip,
    required String code,
    required String deviceId,
    required String deviceName,
  }) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/pair_device'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'pairing_code': code,
        'device_id':    deviceId,
        'device_name':  deviceName,
      }),
    ).timeout(const Duration(seconds: 10));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getConnectCode(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/connect-code'),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  // ── System Stats ──────────────────────────────────────────────
  static Future<Map<String, dynamic>> getSystemStats(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/system-stats'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getNetwork(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/network'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getActiveWindow(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/activewindow'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getBattery(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/battery/status'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getUptime(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/uptime'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  // ── Files ─────────────────────────────────────────────────────
  static Future<List<dynamic>> getRootFiles(String ip) async {
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/files'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 8));
    final data = await _handleResponse(res);
    return data['data'] as List<dynamic>? ?? (jsonDecode(res.body) as List<dynamic>);
  }

  static Future<List<dynamic>> browseFiles(String ip, String path) async {
    final uri = Uri.parse('${_baseUrl(ip)}/files/browse').replace(
      queryParameters: {'path': path},
    );
    final res = await http.get(uri, headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return (body as Map<String, dynamic>)['data'] as List<dynamic>? ?? [];
  }

  static Future<List<dynamic>> listFilesForPicker(String ip, [String? path]) async {
    final uri = Uri.parse('${_baseUrl(ip)}/files/list').replace(
      queryParameters: path != null ? {'path': path} : {},
    );
    final res = await http.get(uri, headers: await _headers()).timeout(const Duration(seconds: 8));
    final data = _handleResponse(res);
    return ((await data)['contents'] as List<dynamic>?) ?? [];
  }

  // ── File Download ─────────────────────────────────────────────
  static Future<String> downloadFile(
    String ip,
    String remotePath,
    String fileName, {
    void Function(int received, int total)? onProgress,
  }) async {
    final token = await StorageService.getToken();
    final uri = Uri.parse('${_baseUrl(ip)}/files/download/chunked').replace(
      queryParameters: {'path': remotePath},
    );

    final request = http.Request('GET', uri)
      ..headers['X-Auth-Token'] = token ?? '';

    final streamedRes = await request.send().timeout(const Duration(minutes: 30));

    if (streamedRes.statusCode != 200) {
      throw ApiException('Download failed (${streamedRes.statusCode})', streamedRes.statusCode);
    }

    // Get actual user-visible Downloads directory
    // getDownloadsDirectory() returns app-specific cache, not user Downloads
    // So we need to construct the path manually to the public Downloads folder
    Directory downloadDir;

    try {
      // Try to get external storage directory (works on Android 10+)
      final external = await getExternalStorageDirectory();
      if (external != null) {
        // Navigate up to parent and into actual Downloads folder
        // Path is usually /storage/emulated/0/
        final parts = external.path.split('/');
        final storageIndex = parts.indexOf('storage');
        if (storageIndex >= 0) {
          final publicPath = parts.sublist(0, storageIndex + 2).join('/') + '/Download';
          downloadDir = Directory(publicPath);
        } else {
          downloadDir = external;
        }
      } else {
        downloadDir = await getApplicationDocumentsDirectory();
      }
    } catch (_) {
      downloadDir = await getApplicationDocumentsDirectory();
    }

    // Ensure directory exists
    await downloadDir.create(recursive: true);

    final savePath = p.join(downloadDir.path, fileName);

    final total = streamedRes.contentLength ?? 0;
    int received = 0;

    final file = File(savePath);
    final sink = file.openWrite();
    await for (final chunk in streamedRes.stream) {
      sink.add(chunk);
      received += chunk.length;
      onProgress?.call(received, total);
    }
    await sink.flush();
    await sink.close();

    return savePath;
  }

  // ── Upload Destinations ───────────────────────────────────────
  static Future<List<Map<String, dynamic>>> getUploadDestinations(String ip) async {
    final token = await StorageService.getToken();
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/files/upload-destinations'),
      headers: {'X-Auth-Token': token ?? ''},
    ).timeout(const Duration(seconds: 5));

    if (res.statusCode == 200) {
      final data = jsonDecode(res.body);
      return List<Map<String, dynamic>>.from(data['destinations'] ?? []);
    }
    return [];
  }

  // ── Browse Folders ────────────────────────────────────────────
  static Future<Map<String, dynamic>> browseFolders(String ip, {String? path}) async {
    final token = await StorageService.getToken();
    final uri = Uri.parse('${_baseUrl(ip)}/files/browse-folders');
    final queryUri = path != null ? uri.replace(queryParameters: {'path': path}) : uri;

    final res = await http.get(queryUri, headers: {'X-Auth-Token': token ?? ''}).timeout(const Duration(seconds: 5));

    if (res.statusCode == 200) {
      return jsonDecode(res.body);
    }
    return {"success": false, "folders": []};
  }

  // ── File Upload ───────────────────────────────────────────────
  static Future<Map<String, dynamic>> uploadFile(
    String ip,
    String filePath,
    String destination, {
    void Function(int sent, int total)? onProgress,
  }) async {
    final token = await StorageService.getToken();
    final file = File(filePath);
    final fileSize = await file.length();
    final fileName = p.basename(filePath);

    final uri = Uri.parse('${_baseUrl(ip)}/files/upload');
    final request = http.MultipartRequest('POST', uri)
      ..headers['X-Auth-Token'] = token ?? ''
      ..fields['destination'] = destination
      ..files.add(await http.MultipartFile.fromPath('file', filePath));

    final streamedRes = await request.send().timeout(const Duration(minutes: 60));
    final res = await http.Response.fromStream(streamedRes);
    return _handleResponse(res);
  }

  // ── File Delete ───────────────────────────────────────────────
  static Future<void> deleteFile(String ip, String path) async {
    final uri = Uri.parse('${_baseUrl(ip)}/files/delete').replace(
      queryParameters: {'path': path},
    );
    final res = await http.delete(uri, headers: await _headers()).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  // ── File Transfer Cancel ───────────────────────────────────────
  static Future<void> cancelDownloads(String ip) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/files/download/cancel'),
      headers: await _headers(),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  // ── Power Control ─────────────────────────────────────────────
  static Future<void> shutdown(String ip)  async => _postVoid(ip, '/power/shutdown');
  static Future<void> restart(String ip)   async => _postVoid(ip, '/power/restart');
  static Future<void> sleep(String ip)     async => _postVoid(ip, '/power/sleep');
  static Future<void> hibernate(String ip) async => _postVoid(ip, '/power/hibernate');
  static Future<void> lock(String ip)      async => _postVoid(ip, '/power/lock');

  // ── Media Controls ────────────────────────────────────────────
  static Future<void> mediaPlayPause(String ip) async => _postVoid(ip, '/media/playpause');
  static Future<void> mediaNext(String ip)      async => _postVoid(ip, '/media/next');
  static Future<void> mediaPrev(String ip)      async => _postVoid(ip, '/media/prev');
  static Future<void> mediaStop(String ip)      async => _postVoid(ip, '/media/stop');
  static Future<void> mediaMute(String ip)      async => _postVoid(ip, '/media/mute');
  static Future<void> volumeUp(String ip)       async => _postVoid(ip, '/media/volumeup');
  static Future<void> volumeDown(String ip)     async => _postVoid(ip, '/media/volumedown');

  static Future<int> getVolume(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/media/volume/get'), headers: await _headers()).timeout(const Duration(seconds: 5));
    final data = await _handleResponse(res);
    return (data['level'] as num?)?.toInt() ?? 50;
  }

  static Future<void> setVolume(String ip, int level) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/media/volume/set'),
      headers: await _headers(),
      body: jsonEncode({'level': level}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  // ── Remote Input ──────────────────────────────────────────────
  static Future<void> remoteType(String ip, String text) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/type'),
      headers: await _headers(),
      body: jsonEncode({'text': text}),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  static Future<void> remoteHotkey(String ip, List<String> keys) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/keyboard/hotkey'),
      headers: await _headers(),
      body: jsonEncode({'keys': keys}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  static Future<void> mouseMove(String ip, double dx, double dy) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/mouse/move'),
      headers: await _headers(),
      body: jsonEncode({'x': dx, 'y': dy}),
    ).timeout(const Duration(seconds: 3));
    await _handleResponse(res);
  }

  static Future<void> mouseClick(String ip, {String button = 'left'}) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/mouse/click'),
      headers: await _headers(),
      body: jsonEncode({'button': button}),
    ).timeout(const Duration(seconds: 3));
    await _handleResponse(res);
  }

  // ── Screenshot ────────────────────────────────────────────────
  static Future<Uint8List> getScreenshot(String ip) async {
    final token = await StorageService.getToken();
    final res = await http.get(
      Uri.parse('${_baseUrl(ip)}/screenshot'),
      headers: {'X-Auth-Token': token ?? ''},
    ).timeout(const Duration(seconds: 15));
    if (res.statusCode == 200) return res.bodyBytes;
    throw ApiException('Screenshot failed (${res.statusCode})', res.statusCode);
  }

  // ── Screen Recording ──────────────────────────────────────────
  static Future<Map<String, dynamic>> startRecording(
    String ip, {
    String source = 'fullscreen',
    String quality = 'medium',
    int fps = 30,
    bool audio = false,
  }) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/recording/start'),
      headers: await _headers(),
      body: jsonEncode({'source': source, 'quality': quality, 'fps': fps, 'audio': audio}),
    ).timeout(const Duration(seconds: 8));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getRecordingStatus(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/recording/status'), headers: await _headers()).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> pauseRecording(String ip) async {
    final res = await http.post(Uri.parse('${_baseUrl(ip)}/recording/pause'), headers: await _headers()).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<Map<String, dynamic>> stopRecording(String ip) async {
    final res = await http.post(Uri.parse('${_baseUrl(ip)}/recording/stop'), headers: await _headers()).timeout(const Duration(seconds: 10));
    return _handleResponse(res);
  }

  static Future<String> downloadRecording(String ip, String filename) async {
    return downloadFile(ip, filename, filename);
  }

  // ── Clipboard ─────────────────────────────────────────────────
  static Future<Map<String, dynamic>> getPcClipboard(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/clipboard/pc'), headers: await _headers()).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<void> setPcClipboard(String ip, String text) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/clipboard'),
      headers: await _headers(),
      body: jsonEncode({'content': text}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  static Future<void> savePhoneClipboard(String ip, String text) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/clipboard/phone'),
      headers: await _headers(),
      body: jsonEncode({'text': text}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getPhoneClipboard(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/clipboard/phone'), headers: await _headers()).timeout(const Duration(seconds: 5));
    return _handleResponse(res);
  }

  static Future<void> pasteFromPhone(String ip) async => _postVoid(ip, '/clipboard/paste-from-phone');

  static Future<void> pasteClipboard(String ip, String text) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/clipboard/paste-from-phone'),
      headers: await _headers(),
      body: jsonEncode({'text': text}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  static Future<void> openLink(String ip, String url) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/open-link'),
      headers: await _headers(),
      body: jsonEncode({'url': url}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  // ── Processes ─────────────────────────────────────────────────
  static Future<List<dynamic>> getProcesses(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/processes'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return (body as Map<String, dynamic>)['data'] as List<dynamic>? ?? [];
  }

  static Future<void> killProcess(String ip, int pid) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/processes/kill'),
      headers: await _headers(),
      body: jsonEncode({'pid': pid}),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  // ── App Launcher ──────────────────────────────────────────────
  static Future<List<dynamic>> getInstalledApps(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/apps'), headers: await _headers()).timeout(const Duration(seconds: 10));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return (body as Map<String, dynamic>)['data'] as List<dynamic>? ?? [];
  }

  static Future<void> launchApp(String ip, String path) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/apps/launch'),
      headers: await _headers(),
      body: jsonEncode({'path': path}),
    ).timeout(const Duration(seconds: 10));
    await _handleResponse(res);
  }

  static Future<void> closeApp(String ip, {String? name, int? windowId}) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/apps/close'),
      headers: await _headers(),
      body: jsonEncode({
        if (name != null) 'name': name,
        if (windowId != null) 'id': windowId,
      }),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  static Future<Map<String, dynamic>> getActiveWindows(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/system/active-windows'), headers: await _headers()).timeout(const Duration(seconds: 8));
    return _handleResponse(res);
  }

  static Future<void> focusWindow(String ip, int hwnd) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/windows/focus'),
      headers: await _headers(),
      body: jsonEncode({'id': hwnd}),
    ).timeout(const Duration(seconds: 5));
    await _handleResponse(res);
  }

  // ── Activity & History ────────────────────────────────────────
  static Future<List<dynamic>> getActivity(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/system/activity'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return (body as Map<String, dynamic>)['data'] as List<dynamic>? ?? [];
  }

  static Future<List<dynamic>> getHistory(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/history'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return [];
  }

  // ── Notifications ─────────────────────────────────────────────
  static Future<List<dynamic>> getNotifications(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/notifications'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return [];
  }

  // ── Settings ──────────────────────────────────────────────────
  static Future<Map<String, dynamic>> getSettings(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/settings'), headers: await _headers()).timeout(const Duration(seconds: 8));
    return _handleResponse(res);
  }

  static Future<void> updateSettings(String ip, Map<String, dynamic> settings) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/settings'),
      headers: await _headers(),
      body: jsonEncode(settings),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  // ── Guest Access ──────────────────────────────────────────────
  static Future<Map<String, dynamic>> createGuestSession(
    String ip, {
    required List<String> folders,
    required int durationMinutes,
  }) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/guest/create'),
      headers: await _headers(),
      body: jsonEncode({'folders': folders, 'duration_minutes': durationMinutes}),
    ).timeout(const Duration(seconds: 10));
    return _handleResponse(res);
  }

  static Future<List<dynamic>> getGuestSessions(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/guest/sessions'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final data = await _handleResponse(res);
    return data['sessions'] as List<dynamic>? ?? [];
  }

  static Future<void> endGuestSession(String ip, String guestToken) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/guest/end'),
      headers: await _headers(),
      body: jsonEncode({'guest_token': guestToken}),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  // ── Paired Devices ────────────────────────────────────────────
  static Future<List<dynamic>> getPairedDevices(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/paired-devices'), headers: await _headers()).timeout(const Duration(seconds: 8));
    final body = jsonDecode(res.body);
    if (body is List) return body;
    return [];
  }

  static Future<void> unpairDevice(String ip, String deviceId) async {
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}/unpair'),
      headers: await _headers(),
      body: jsonEncode({'device_id': deviceId}),
    ).timeout(const Duration(seconds: 8));
    await _handleResponse(res);
  }

  // ── System ────────────────────────────────────────────────────
  static Future<void> optimizeSystem(String ip) async => _postVoid(ip, '/system/optimize');

  static Future<Map<String, dynamic>> getResourceTrends(String ip) async {
    final res = await http.get(Uri.parse('${_baseUrl(ip)}/system/resource-trends'), headers: await _headers()).timeout(const Duration(seconds: 8));
    return _handleResponse(res);
  }

  // ── Drop Zone (Phone → Phone via PC) ──────────────────────────
  static Future<Map<String, dynamic>> uploadToDrop(
    String ip,
    String filePath, {
    void Function(int sent, int total)? onProgress,
  }) async {
    final token = await StorageService.getToken();
    final uri = Uri.parse('${_baseUrl(ip)}/files/upload');
    final request = http.MultipartRequest('POST', uri)
      ..headers['X-Auth-Token'] = token ?? ''
      ..fields['destination'] = 'CypherDrop'
      ..files.add(await http.MultipartFile.fromPath('file', filePath));
    final streamedRes = await request.send().timeout(const Duration(minutes: 10));
    final res = await http.Response.fromStream(streamedRes);
    return _handleResponse(res);
  }

  // ── Internal ──────────────────────────────────────────────────
  static Future<void> _postVoid(String ip, String path, [Map<String, dynamic>? body]) async {
    final headers = await _headers();
    final res = await http.post(
      Uri.parse('${_baseUrl(ip)}$path'),
      headers: headers,
      body: body != null ? jsonEncode(body) : null,
    ).timeout(const Duration(seconds: 10));
    await _handleResponse(res);
  }

  // Preview URL (used in video/audio player)
  static Future<String> getPreviewUrl(String ip, String remotePath) async {
    final token = await StorageService.getToken();
    return '${_baseUrl(ip)}/files/preview?path=${Uri.encodeComponent(remotePath)}&token=$token';
  }

  static Future<String> getThumbnailUrl(String ip, String remotePath) async {
    final token = await StorageService.getToken();
    return '${_baseUrl(ip)}/files/thumbnail?path=${Uri.encodeComponent(remotePath)}&token=$token';
  }

  // ── Wake-on-LAN ────────────────────────────────────────────────
  static Future<bool> sendWol(String ip, String mac) async {
    try {
      final res = await http.post(
        Uri.parse('${_baseUrl(ip)}/wol'),
        headers: await _headers(),
        body: jsonEncode({'mac': mac}),
      ).timeout(const Duration(seconds: 6));
      final data = await _handleResponse(res);
      return data['success'] as bool? ?? false;
    } catch (_) {
      return false;
    }
  }
}

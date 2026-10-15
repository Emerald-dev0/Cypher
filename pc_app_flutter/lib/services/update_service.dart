import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

class UpdateResult {
  final String latestVersion;
  final String downloadUrl;
  const UpdateResult({required this.latestVersion, required this.downloadUrl});
}

class UpdateService {
  static const String currentVersion = '2.0.0';
  static const String _apiUrl =
      'https://api.github.com/repos/Emerald-dev0/Cypher/releases/latest';
  static const String _releasesPage =
      'https://github.com/Emerald-dev0/Cypher/releases/latest';

  static Future<UpdateResult?> check() async {
    try {
      final res = await http
          .get(Uri.parse(_apiUrl), headers: {'Accept': 'application/vnd.github+json'})
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return null;
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final tag = (data['tag_name'] as String? ?? '').replaceFirst('v', '');
      if (tag.isEmpty) return null;
      if (_isNewer(tag, currentVersion)) {
        return UpdateResult(
          latestVersion: tag,
          downloadUrl: data['html_url'] as String? ?? _releasesPage,
        );
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  static bool _isNewer(String remote, String current) {
    final r = _parts(remote);
    final c = _parts(current);
    for (int i = 0; i < 3; i++) {
      if (r[i] > c[i]) return true;
      if (r[i] < c[i]) return false;
    }
    return false;
  }

  static List<int> _parts(String v) {
    final parts = v.split('.');
    while (parts.length < 3) parts.add('0');
    return parts.map((p) => int.tryParse(p) ?? 0).toList();
  }

  static Future<void> openReleasePage([String? url]) async {
    final uri = Uri.parse(url ?? _releasesPage);
    if (await canLaunchUrl(uri)) await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

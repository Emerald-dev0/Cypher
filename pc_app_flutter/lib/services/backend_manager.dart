import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;

/// Locates and starts the CYPHER node.
///
/// P1-D2. Paths are resolved from [Platform.resolvedExecutable] (and, in debug,
/// [Directory.current]), never from a hardcoded user home. The previous
/// implementation searched `C:\Users\hp\...\python.exe` — one developer's
/// machine — and used `Directory.current`, which is the user's cwd when they
/// launch the .exe from a shortcut, not the install directory.
class BackendManager {
  static final BackendManager _instance = BackendManager._internal();
  factory BackendManager() => _instance;
  BackendManager._internal();

  Process? _process;
  String _errorLog = "";
  bool _isReady = false;
  String? _usedInterpreter;

  bool get isReady => _isReady;
  String get errorLog => _errorLog;
  /// Which python/exe actually started. Surfaced on the error screen.
  String? get usedInterpreter => _usedInterpreter;

  Future<bool> start() async {
    _errorLog = "";
    _usedInterpreter = null;
    _isReady = false;

    for (final backendDir in backendSearchRoots()) {
      final packaged = await _startPackaged(backendDir);
      if (packaged) return true;
      final script = await _startFromScript(backendDir);
      if (script) return true;
    }
    if (_errorLog.isEmpty) {
      _errorLog =
          "Could not find the CYPHER node. Looked next to the app and in "
          "the project `backend/` folder. Searched Python on PATH: "
          "${pythonCommands().join(', ')}.";
    }
    return false;
  }

  /// Directories that may contain `service.py` or `dist/cypher_node*`.
  ///
  /// Pure function so tests can pin the search order without spawning a process.
  static List<String> backendSearchRoots({
    String? resolvedExecutable,
    String? currentDirectory,
  }) {
    final exe = resolvedExecutable ?? Platform.resolvedExecutable;
    final cwd = currentDirectory ?? Directory.current.path;
    final exeDir = p.dirname(exe);
    final roots = <String>[
      // Packaged install: node sits next to the desktop shell.
      p.join(exeDir, 'backend'),
      exeDir,
      // `flutter run` from pc_app_flutter/: cwd is the project.
      p.join(cwd, 'backend'),
      cwd,
      // `flutter run` from the repo root.
      p.join(cwd, 'pc_app_flutter', 'backend'),
    ];
    final seen = <String>{};
    final out = <String>[];
    for (final r in roots) {
      final n = p.normalize(r);
      if (seen.add(n)) out.add(n);
    }
    return out;
  }

  /// Interpreters to try, in order. Never a hardcoded user path.
  static List<String> pythonCommands({String? pathEnv}) {
    final commands = <String>[];
    if (Platform.isWindows) {
      commands.addAll(['py', 'python', 'python3', 'python.exe']);
    } else {
      commands.addAll(['python3', 'python']);
    }
    final path = pathEnv ?? Platform.environment['PATH'] ?? '';
    final sep = Platform.isWindows ? ';' : ':';
    for (final dir in path.split(sep)) {
      if (dir.isEmpty) continue;
      for (final name in Platform.isWindows
          ? ['python.exe', 'python3.exe', 'py.exe']
          : ['python3', 'python']) {
        final candidate = p.join(dir, name);
        if (!commands.contains(candidate)) {
          commands.add(candidate);
        }
      }
    }
    return commands;
  }

  Future<bool> _startPackaged(String backendDir) async {
    for (final name in ['cypher_node.exe', 'cypher_node']) {
      final exePath = p.join(backendDir, 'dist', name);
      if (!await File(exePath).exists()) {
        // Also accept the binary sitting in backendDir itself.
        final alt = p.join(backendDir, name);
        if (!await File(alt).exists()) continue;
        return _spawn(alt, const [], backendDir, label: alt);
      }
      return _spawn(exePath, const [], backendDir, label: exePath);
    }
    return false;
  }

  Future<bool> _startFromScript(String backendDir) async {
    final scriptPath = p.join(backendDir, 'service.py');
    if (!await File(scriptPath).exists()) return false;

    for (final cmd in pythonCommands()) {
      final ok = await _spawn(
        cmd,
        ['-u', scriptPath],
        backendDir,
        label: '$cmd $scriptPath',
      );
      if (ok) return true;
    }
    return false;
  }

  Future<bool> _spawn(
    String executable,
    List<String> arguments,
    String workingDirectory, {
    required String label,
  }) async {
    try {
      debugPrint('Attempting start via $label');
      // No runInShell: a shell would reintroduce the injection surface that
      // removing shell=True from the Python service closed.
      final process = await Process.start(
        executable,
        arguments,
        workingDirectory: workingDirectory,
      );
      _process = process;
      _setupProcessPiping();
      await Future.delayed(const Duration(milliseconds: 400));
      if (await waitForBackendReady(maxAttempts: 10)) {
        _usedInterpreter = label;
        return true;
      }
      process.kill();
      _process = null;
      _errorLog += 'Started $label but /ping never answered.\n';
    } catch (e) {
      _errorLog += 'Failed with $label: $e\n';
    }
    return false;
  }

  void _setupProcessPiping() {
    if (_process == null) return;

    _process!.stdout.transform(utf8.decoder).listen((data) {
      debugPrint("Node Output: $data");
      if (data.contains("already running")) {
        _errorLog = "CYPHER is already running in another process.";
      }
    });

    _process!.stderr.transform(utf8.decoder).listen((data) {
      debugPrint("Node Error: $data");
      _errorLog += data;
    });

    _process!.exitCode.then((code) {
      if (code != 0) _isReady = false;
    });
  }

  Future<bool> waitForBackendReady({
    int maxAttempts = 20,
    Duration interval = const Duration(milliseconds: 500),
  }) async {
    for (int i = 0; i < maxAttempts; i++) {
      try {
        final response = await http.get(
          Uri.parse('http://127.0.0.1:5000/ping'),
        ).timeout(const Duration(seconds: 1));

        if (response.statusCode == 200) {
          debugPrint('Backend ready');
          _isReady = true;
          return true;
        }
      } catch (_) {}
      await Future.delayed(interval);
    }
    return false;
  }

  void stop() {
    _process?.kill();
    _process = null;
    _isReady = false;
    _usedInterpreter = null;
  }
}

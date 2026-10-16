import 'package:cypher_pc/services/backend_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

void main() {
  group('backendSearchRoots', () {
    test('prefers the directory next to the packaged executable', () {
      final roots = BackendManager.backendSearchRoots(
        resolvedExecutable: r'C:\Program Files\CYPHER\cypher.exe',
        currentDirectory: r'D:\unrelated',
      );
      expect(roots.first, p.normalize(r'C:\Program Files\CYPHER\backend'));
      expect(roots, isNot(contains(r'C:\Users\hp')));
    });

    test('never contains a hardcoded developer home', () {
      final roots = BackendManager.backendSearchRoots(
        resolvedExecutable: '/opt/cypher/cypher',
        currentDirectory: '/tmp',
      );
      for (final r in roots) {
        expect(r.toLowerCase(), isNot(contains(r'c:\users\hp')));
      }
    });
  });

  group('protocol', () {
    test('shell and node share protocol version 1', () {
      expect(BackendManager.expectedProtocolVersion, 1);
    });
  });

  group('pythonCommands', () {
    test('does not include a hardcoded python.exe path', () {
      final cmds = BackendManager.pythonCommands(pathEnv: '/usr/bin:/usr/local/bin');
      for (final c in cmds) {
        expect(c.toLowerCase(), isNot(contains(r'c:\users\hp')));
      }
    });
  });
}

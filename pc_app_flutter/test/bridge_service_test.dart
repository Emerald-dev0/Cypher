// Security regression tests for the desktop shell's loopback bridge.
//
// These replace the previous `widget_test.dart`, which was the unmodified
// `flutter create` counter test — it asserted `find.text('0')` against an app
// that has no counter, so `flutter test` was failing (or was never run). See
// docs/AUDIT.md A-03.
//
// Deliberately no widget pumping here. `CypherPC` -> `StartupScreen.initState`
// spawns the real Python node and polls /ping, which must not happen in CI.
// Testing the shell's process supervision needs a fake BackendManager
// (roadmap P1-D2/P1-T2).

import 'package:cypher_pc/services/bridge_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('loopback bridge', () {
    test('only ever talks to the loopback interface', () {
      // The shell is a local supervisor, not a remote client. If this URL ever
      // becomes configurable or non-local, the trust model in
      // docs/plans/security-hardening.md §2 changes and needs review.
      final uri = Uri.parse(BridgeService.baseUrl);
      expect(uri.host, anyOf('127.0.0.1', 'localhost'));
      expect(uri.scheme, 'http'); // becomes https under P2-S1
    });

    test('does not hardcode the published internal token', () {
      // Audit S-01: this literal was committed to a public repository and
      // granted full remote control of every installed node. A CI job also
      // greps for it; this asserts the runtime value is not the literal even if
      // the grep is ever relaxed.
      const publishedLiterals = <String>{
        'cypher-internal-pc-app-token-2024',
        'cypher-internal-pc-app-token',
        'internal-token',
      };
      expect(publishedLiterals.contains(BridgeService.internalToken), isFalse);
    });

    test('never falls back to a short or guessable token', () {
      // If the node has not been set up, <appData>/Cypher/internal_token is
      // absent and the getter returns '' — which makes every bridge call 401.
      // That is the intended safe failure mode: the shell reports "node not
      // ready" rather than operating unauthenticated.
      //
      // If the node HAS been set up (a developer's own machine), the value is a
      // 48-byte urlsafe token. Either way it must never be a short literal, so
      // this holds on CI and on a workstation alike.
      final token = BridgeService.internalToken;
      expect(token.isEmpty || token.length >= 32, isTrue,
          reason: 'internalToken must be empty (fail closed) or a real '
              'high-entropy token; got ${token.length} chars');
    });

    test('is a singleton-friendly static surface', () {
      // Reading the token twice must not regenerate or change it.
      expect(BridgeService.internalToken, BridgeService.internalToken);
    });
  });
}

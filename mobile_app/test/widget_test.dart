// Tests for the mobile client's local storage — which holds the auth token.
//
// This replaces the previous `widget_test.dart`, which pumped `CypherApp` and
// asserted `find.text('C')` and `find.text('Y')`. The splash screen renders
// 'CYPHER' as a single Text widget, so both assertions failed; it also awaited
// 1.8 s of `Future.delayed`, which makes `pumpAndSettle` time out. The test had
// never passed. See docs/AUDIT.md A-03 and roadmap P1-T2.
//
// Storage is tested directly instead: it is the component that holds the paired
// device token, so its correctness is a security property, not a detail.

import 'package:cypher/services/storage_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    // Isolate every test with an empty in-memory preference store. Without this,
    // state leaks between tests and a token from one case can satisfy another.
    SharedPreferences.setMockInitialValues({});
  });

  group('auth token storage', () {
    test('returns null when no device has been paired', () async {
      expect(await StorageService.getToken(), isNull);
      expect(await StorageService.getIsPaired(), isFalse);
    });

    test('round-trips a token', () async {
      const token = 'a' * 64; // matches secrets.token_hex(32) on the node
      await StorageService.saveToken(token);
      expect(await StorageService.getToken(), token);
    });

    test('overwriting a token replaces it rather than appending', () async {
      await StorageService.saveToken('first-token');
      await StorageService.saveToken('second-token');
      expect(await StorageService.getToken(), 'second-token');
    });

    test('clearPairing removes the token', () async {
      // Revoking on the client side must not leave a usable credential behind.
      await StorageService.saveToken('a-token');
      await StorageService.saveIp('192.168.1.24');
      await StorageService.setIsPaired(true);
      await StorageService.savePcName('My PC');

      await StorageService.clearPairing();

      expect(await StorageService.getToken(), isNull);
      expect(await StorageService.getIp(), isNull);
      expect(await StorageService.getIsPaired(), isFalse);
      expect(await StorageService.getPcName(), isNull);
    });

    test('clearPairing keeps the device identity so re-pairing is smooth', () async {
      // The phone's own device_id and name are not secrets and should survive an
      // unpair, so the node can recognise the device when it re-pairs.
      await StorageService.saveDeviceId('device-123');
      await StorageService.saveDeviceName('Pixel');
      await StorageService.saveToken('a-token');

      await StorageService.clearPairing();

      expect(await StorageService.getDeviceId(), 'device-123');
      expect(await StorageService.getDeviceName(), 'Pixel');
      expect(await StorageService.getToken(), isNull);
    });
  });

  group('connection data', () {
    test('getConnectionData returns both token and address', () async {
      await StorageService.saveToken('tok');
      await StorageService.saveIp('192.168.43.1');

      final data = await StorageService.getConnectionData();

      expect(data['token'], 'tok');
      expect(data['ip'], '192.168.43.1');
    });

    test('getConnectionData is null-safe before pairing', () async {
      final data = await StorageService.getConnectionData();
      expect(data['token'], isNull);
      expect(data['ip'], isNull);
    });

    test('onboarding state persists independently of pairing', () async {
      await StorageService.setOnboarded(true);
      await StorageService.clearPairing();
      expect(await StorageService.getOnboarded(), isTrue,
          reason: 'unpairing should not send a returning user through onboarding');
    });
  });

  group('json storage', () {
    test('round-trips a map', () async {
      await StorageService.saveJson('shared', {'folders': ['Desktop', 'Documents']});
      final decoded = await StorageService.getJson('shared') as Map<String, dynamic>;
      expect(decoded['folders'], ['Desktop', 'Documents']);
    });

    test('round-trips a list', () async {
      await StorageService.saveJson('history', ['a', 'b']);
      expect(await StorageService.getJson('history'), ['a', 'b']);
    });

    test('returns null for a missing key', () async {
      expect(await StorageService.getJson('nope'), isNull);
    });

    test('returns null rather than throwing on corrupt data', () async {
      // A malformed value must not crash app start. getJson swallows the decode
      // error and reports "nothing stored", which callers already handle.
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('corrupt', '{not valid json');

      expect(await StorageService.getJson('corrupt'), isNull);
    });
  });
}

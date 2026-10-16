// Tests for the private-network guard that compensates for cleartext HTTP being
// permitted globally in network_security_config.xml.
//
// Android's network security config matches on hostnames only — it has no CIDR
// syntax — so the cleartext exception cannot be scoped to RFC1918 declaratively.
// `ApiService.isPermittedTarget` is the compensating control. It is a pure
// function with no I/O and no plugin dependencies, so it is tested directly.
//
// These tests matter more than most: the guard's whole job is to fail closed on
// anything unexpected, and a guard that silently returns true for a public host
// is worse than no guard at all, because the XML comment tells the next reader
// the risk is handled.

import 'package:cypher/services/api_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  bool permitted(String host) => ApiService.isPermittedTarget(host);

  group('RFC 1918 is permitted', () {
    test('10.0.0.0/8', () {
      expect(permitted('10.0.0.1'), isTrue);
      expect(permitted('10.255.255.254'), isTrue);
    });

    test('172.16.0.0/12 — including both boundaries', () {
      expect(permitted('172.16.0.1'), isTrue);
      expect(permitted('172.31.255.254'), isTrue);
      expect(permitted('172.20.10.2'), isTrue); // typical iPhone hotspot
    });
  });

  group('172.16.0.0/12 boundaries are exact', () {
    // A common off-by-one: writing `bytes[1] <= 32` or forgetting the lower
    // bound would widen this to 172.0.0.0/8 or 172.16.0.0/11.
    test('just below the range is refused', () {
      expect(permitted('172.15.255.255'), isFalse);
      expect(permitted('172.0.0.1'), isFalse);
    });

    test('just above the range is refused', () {
      expect(permitted('172.32.0.1'), isFalse);
      expect(permitted('172.33.0.1'), isFalse);
    });
  });

  group('192.168.0.0/16 is permitted', () {
    test('common LAN and tethering gateways', () {
      expect(permitted('192.168.1.24'), isTrue);
      expect(permitted('192.168.0.1'), isTrue);
      expect(permitted('192.168.43.1'), isTrue); // Android Wi-Fi hotspot
      expect(permitted('192.168.42.129'), isTrue); // Android USB tethering
      expect(permitted('192.168.49.1'), isTrue); // Wi-Fi Direct
    });

    test('192.169.x is NOT the same range', () {
      expect(permitted('192.169.1.1'), isFalse);
    });
  });

  group('loopback and link-local are permitted', () {
    test('IPv4 loopback', () {
      expect(permitted('127.0.0.1'), isTrue);
      expect(permitted('127.5.5.5'), isTrue);
    });

    test('IPv4 link-local', () {
      expect(permitted('169.254.1.1'), isTrue);
    });

    test('IPv6 loopback and link-local', () {
      expect(permitted('::1'), isTrue);
      expect(permitted('fe80::1'), isTrue);
      // fe80::/10 spans fe80:: through febf::. `febf::1` is the upper boundary and
      // is the exact address the SDK's InternetAddress.isLinkLocal refused, which
      // is why this function classifies on raw bytes instead.
      expect(permitted('febf::1'), isTrue);
      expect(permitted('fe80::abcd:1234'), isTrue);
    });

    test('IPv6 addresses adjacent to link-local are refused', () {
      // fec0::/10 is the retired site-local range. It differs from fe80::/10 by
      // two bits, so it is the boundary most likely to be got wrong by a
      // hand-rolled prefix check — and permitting it would treat a routable
      // address as local.
      expect(permitted('fec0::1'), isFalse);
      expect(permitted('fe00::1'), isFalse);
      expect(permitted('ff02::1'), isFalse, reason: 'multicast is not a peer');
      // ::2 is not loopback; only ::1 is.
      expect(permitted('::2'), isFalse);
    });

    test('IPv6 unique-local fc00::/7', () {
      expect(permitted('fc00::1'), isTrue);
      expect(permitted('fd12:3456:789a::1'), isTrue);
    });

    test('bracketed IPv6 literals are handled', () {
      // Uri.host strips brackets, but a pasted address may not.
      expect(permitted('[::1]'), isTrue);
      expect(permitted('[fe80::1]'), isTrue);
      expect(permitted('[2001:db8::1]'), isFalse);
    });
  });

  group('localhost and mDNS are permitted', () {
    test('localhost', () {
      expect(permitted('localhost'), isTrue);
      expect(permitted('LOCALHOST'), isTrue);
    });

    test('.local names — link-local scoped by definition', () {
      // DiscoveryService finds nodes over mDNS, so these must be allowed or
      // discovery would break.
      expect(permitted('cypher-pc.local'), isTrue);
      expect(permitted('CYPHER-PC.LOCAL'), isTrue);
    });
  });

  group('public destinations are refused', () {
    test('public IPv4', () {
      expect(permitted('8.8.8.8'), isFalse);
      expect(permitted('1.1.1.1'), isFalse);
      expect(permitted('93.184.216.34'), isFalse); // example.com
      expect(permitted('203.0.113.1'), isFalse); // TEST-NET-3
    });

    test('public IPv6', () {
      expect(permitted('2001:4860:4860::8888'), isFalse);
      expect(permitted('2606:2800:220:1:248:1893:25c8:1946'), isFalse);
      expect(permitted('fe00::1'), isFalse); // just outside fe80::/10
    });

    test('public hostnames', () {
      expect(permitted('example.com'), isFalse);
      expect(permitted('attacker.invalid'), isFalse);
      // The decisive case: a hostname that is not an IP literal and not mDNS.
      // Classifying it would require a DNS lookup, which would itself leak the
      // query — so refuse and let TLS handle remote nodes.
      expect(permitted('cypher-relay.example.org'), isFalse);
    });

    test('CGNAT is deliberately refused', () {
      // 100.64.0.0/10 is carrier infrastructure, not a LAN. Permitting it would
      // mean sending a paired token in cleartext across an ISP network.
      expect(permitted('100.64.0.1'), isFalse);
      expect(permitted('100.100.100.100'), isFalse);
    });

    test('broadcast and multicast are refused', () {
      expect(permitted('255.255.255.255'), isFalse);
      expect(permitted('224.0.0.251'), isFalse); // mDNS multicast group
      expect(permitted('0.0.0.0'), isFalse);
    });
  });

  group('malformed input fails closed', () {
    test('empty and whitespace', () {
      expect(permitted(''), isFalse);
      expect(permitted('   '), isFalse);
    });

    test('partial or out-of-range IPv4', () {
      expect(permitted('192.168.1'), isFalse);
      expect(permitted('192.168.1.256'), isFalse);
      expect(permitted('999.1.1.1'), isFalse);
      expect(permitted('192.168.1.1.1'), isFalse);
    });

    test('an IP with a port or scheme attached is not accepted', () {
      // Callers pass a bare host. If a full URL ever reaches here it must fail
      // closed rather than be partially parsed into something permissive.
      expect(permitted('192.168.1.24:5000'), isFalse);
      expect(permitted('http://192.168.1.24'), isFalse);
    });

    test('surrounding whitespace is tolerated on an otherwise valid host', () {
      expect(permitted('  192.168.1.24  '), isTrue);
      expect(permitted('  8.8.8.8  '), isFalse);
    });
  });

  group('assertPrivateTarget', () {
    test('is silent for a LAN host', () {
      expect(() => ApiService.assertPrivateTarget('192.168.1.24'), returnsNormally);
      expect(() => ApiService.assertPrivateTarget('cypher-pc.local'), returnsNormally);
    });

    test('throws for a public host', () {
      expect(
        () => ApiService.assertPrivateTarget('8.8.8.8'),
        throwsA(isA<PrivateNetworkRequiredException>()),
      );
    });

    test('the exception is an ApiException so existing handlers catch it', () {
      // Every caller already copes with ApiException, because _handleResponse
      // throws it for any non-2xx status. Subclassing it means this new failure
      // mode does not need new error handling anywhere.
      expect(
        () => ApiService.assertPrivateTarget('example.com'),
        throwsA(isA<ApiException>()),
      );
    });

    test('the exception message names the refused host', () {
      try {
        ApiService.assertPrivateTarget('203.0.113.7');
        fail('expected a throw');
      } on PrivateNetworkRequiredException catch (e) {
        expect(e.host, '203.0.113.7');
        expect(e.message, contains('203.0.113.7'));
        expect(e.toString(), contains('203.0.113.7'));
      }
    });
  });

  group('assertPrivateUri', () {
    test('permits cleartext to a private host', () {
      expect(
        () => ApiService.assertPrivateUri(Uri.parse('http://192.168.1.24:5000/ping')),
        returnsNormally,
      );
    });

    test('refuses cleartext to a public host', () {
      expect(
        () => ApiService.assertPrivateUri(Uri.parse('http://example.com/steal')),
        throwsA(isA<PrivateNetworkRequiredException>()),
      );
    });

    test('permits TLS to a public host', () {
      // This is the policy the network security config intends: cleartext only
      // on the LAN, TLS anywhere. It is also why the GitHub release check in
      // update_service.dart keeps working.
      expect(
        () => ApiService.assertPrivateUri(
          Uri.parse('https://api.github.com/repos/Emerald-dev0/Cypher/releases/latest'),
        ),
        returnsNormally,
      );
    });

    test('reads the host out of the URI rather than the whole string', () {
      // A public host hidden in the path or query must not be mistaken for the
      // destination, and a private host in the query must not whitelist a public
      // destination.
      expect(
        () => ApiService.assertPrivateUri(
          Uri.parse('http://example.com/?next=192.168.1.24'),
        ),
        throwsA(isA<PrivateNetworkRequiredException>()),
      );
      expect(
        () => ApiService.assertPrivateUri(
          Uri.parse('http://192.168.1.24:5000/guest/access?redirect=https://example.com'),
        ),
        returnsNormally,
      );
    });
  });
}

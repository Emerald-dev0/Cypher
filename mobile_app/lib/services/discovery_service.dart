import 'dart:async';
import 'dart:io';
import 'package:nsd/nsd.dart';
import 'api_service.dart';

enum DiscoveryState { idle, scanning, found, failed }

class DiscoveredPc {
  final String ip;
  final String name;
  final int port;
  DiscoveredPc({required this.ip, required this.name, this.port = 5000});
}

class DiscoveryService {
  DiscoveryService._();

  static const _serviceType = '_cypher._tcp';

  // ── mDNS Discovery ───────────────────────────────────────────
  static Future<List<DiscoveredPc>> discoverViaMdns({
    Duration timeout = const Duration(seconds: 8),
  }) async {
    final found = <DiscoveredPc>[];
    Discovery? disc;

    try {
      disc = await startDiscovery(_serviceType);

      disc.addServiceListener((service, status) {
        if (status == ServiceStatus.found && service.host != null) {
          final host = service.host!;
          final port = service.port ?? 5000;
          final name = service.name ?? 'CYPHER PC';
          found.add(DiscoveredPc(ip: host, name: name, port: port));
        }
      });

      await Future.delayed(timeout);
    } catch (_) {
      // mDNS not available — fall through to subnet scan
    } finally {
      if (disc != null) await stopDiscovery(disc);
    }

    return found;
  }

  // ── Subnet Scan ───────────────────────────────────────────────
  // Tries common phone-hotspot ranges to find the PC
  static Future<List<DiscoveredPc>> scanSubnet({
    Duration perHostTimeout = const Duration(milliseconds: 800),
  }) async {
    final candidates = await _getCandidateIps();
    final found = <DiscoveredPc>[];

    await Future.wait(
      candidates.map((ip) async {
        try {
          final alive = await ApiService.ping(ip);
          if (alive) {
            final status = await ApiService.getStatus(ip);
            found.add(DiscoveredPc(
              ip: ip,
              name: status['pc_name'] as String? ?? 'CYPHER PC',
            ));
          }
        } catch (_) {}
      }),
      eagerError: false,
    );

    return found;
  }

  // ── Full Discovery (mDNS → Subnet → Manual) ──────────────────
  static Future<List<DiscoveredPc>> discover() async {
    // 1. Try mDNS first (fastest)
    final mdnsResults = await discoverViaMdns(timeout: const Duration(seconds: 5));
    if (mdnsResults.isNotEmpty) return mdnsResults;

    // 2. Subnet scan for all 4 network scenarios
    final subnetResults = await scanSubnet();
    return subnetResults;
  }

  // ── Candidate IP Generation ───────────────────────────────────
  static Future<List<String>> _getCandidateIps() async {
    final candidates = <String>[];

    // Android hotspot: Phone=192.168.43.1, PC gets 192.168.43.x
    for (int i = 2; i <= 20; i++) {
      candidates.add('192.168.43.$i');
    }

    // Windows Mobile Hotspot: PC=192.168.137.1, Phone gets .x
    candidates.add('192.168.137.1');
    for (int i = 2; i <= 10; i++) {
      candidates.add('192.168.137.$i');
    }

    // USB tethering range
    for (int i = 1; i <= 5; i++) {
      candidates.add('192.168.42.$i');
    }

    // Try to get our own IP and scan our subnet
    try {
      final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4);
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          final parts = addr.address.split('.');
          if (parts.length == 4 && addr.address != '127.0.0.1' && !addr.address.startsWith('169.254')) {
            final base = '${parts[0]}.${parts[1]}.${parts[2]}';
            // Scan first 50 addresses on our subnet
            for (int i = 1; i <= 50; i++) {
              final candidate = '$base.$i';
              if (!candidates.contains(candidate)) candidates.add(candidate);
            }
            break;
          }
        }
      }
    } catch (_) {}

    return candidates;
  }

  // ── Quick Reconnect Check ─────────────────────────────────────
  static Future<bool> isReachable(String ip) => ApiService.ping(ip);
}

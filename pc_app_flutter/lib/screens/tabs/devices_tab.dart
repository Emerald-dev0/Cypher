import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../widgets/glass_container.dart';

/// Paired phones: identity, last seen, revoke lives on Security for guests.
class DevicesTab extends StatelessWidget {
  final List<dynamic> devices;
  final bool isDark;
  final Color accent;

  const DevicesTab({
    super.key,
    required this.devices,
    required this.isDark,
    required this.accent,
  });

  @override
  Widget build(BuildContext context) {
    final fg = isDark ? Colors.white : Colors.black;
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Devices',
              style: GoogleFonts.inter(
                  fontSize: 22, fontWeight: FontWeight.w700, color: fg)),
          const SizedBox(height: 8),
          Text(
            'Phones and tablets that have completed pairing. Revoke a guest link from Security.',
            style: GoogleFonts.inter(
                fontSize: 13, color: fg.withOpacity(0.5), height: 1.4),
          ),
          const SizedBox(height: 24),
          if (devices.isEmpty)
            GlassContainer(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'No paired devices yet. Use the code in the sidebar.',
                  style: GoogleFonts.inter(color: fg.withOpacity(0.6)),
                ),
              ),
            )
          else
            Expanded(
              child: ListView.separated(
                itemCount: devices.length,
                separatorBuilder: (_, __) => const SizedBox(height: 10),
                itemBuilder: (_, i) {
                  final d = devices[i] as Map<String, dynamic>? ?? {};
                  final name = d['device_name']?.toString() ?? d['name']?.toString() ?? 'Device';
                  final id = d['device_id']?.toString() ?? '';
                  return GlassContainer(
                    child: ListTile(
                      leading: Icon(Icons.smartphone_rounded, color: accent),
                      title: Text(name, style: GoogleFonts.inter(fontWeight: FontWeight.w600, color: fg)),
                      subtitle: Text(id, style: GoogleFonts.inter(fontSize: 12, color: fg.withOpacity(0.45))),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

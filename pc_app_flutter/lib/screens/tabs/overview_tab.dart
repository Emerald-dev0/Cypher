import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'home_tab.dart';

/// Home + vitals on one surface (rebuild plan §3.1).
class OverviewTab extends StatelessWidget {
  final String pairingCode;
  final List<dynamic> devices;
  final Map<String, dynamic> stats;
  final bool isDark;
  final Color accent;
  final VoidCallback onRefreshCode;
  final Animation<double> waveAnimation;
  final VoidCallback onOptimize;
  final bool isOptimizing;

  const OverviewTab({
    super.key,
    required this.pairingCode,
    required this.devices,
    required this.stats,
    required this.isDark,
    required this.accent,
    required this.onRefreshCode,
    required this.waveAnimation,
    required this.onOptimize,
    required this.isOptimizing,
  });

  @override
  Widget build(BuildContext context) {
    final cpu = (stats['cpu_percent'] as num?)?.toDouble() ?? 0;
    final ram = (stats['ram_percent'] as num?)?.toDouble() ?? 0;
    final disk = (stats['disk_percent'] as num?)?.toDouble() ?? 0;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 20, 32, 0),
          child: Row(
            children: [
              _chip('CPU', cpu, const Color(0xFFF43F5E)),
              const SizedBox(width: 12),
              _chip('RAM', ram, accent),
              const SizedBox(width: 12),
              _chip('Disk', disk, const Color(0xFFF59E0B)),
              const Spacer(),
              TextButton(
                onPressed: onOptimize,
                child: Text(isOptimizing ? 'Optimizing…' : 'Optimize',
                    style: GoogleFonts.inter(fontWeight: FontWeight.w600, color: accent)),
              ),
            ],
          ),
        ),
        Expanded(
          child: HomeTab(
            pairingCode: pairingCode,
            devices: devices,
            stats: stats,
            isDark: isDark,
            accent: accent,
            onRefreshCode: onRefreshCode,
          ),
        ),
      ],
    );
  }

  Widget _chip(String label, double value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        '$label ${value.toStringAsFixed(0)}%',
        style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }
}

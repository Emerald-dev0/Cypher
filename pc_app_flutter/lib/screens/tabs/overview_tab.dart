import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../widgets/glass_container.dart';

/// Overview: vitals · right now · recent (rebuild plan §4.1).
class OverviewTab extends StatelessWidget {
  final String pairingCode;
  final List<dynamic> devices;
  final Map<String, dynamic> stats;
  final Map<String, dynamic> transfers;
  final List<dynamic> activityLog;
  final bool isDark;
  final Color accent;
  final VoidCallback onRefreshCode;
  final Animation<double> waveAnimation;
  final VoidCallback onOptimize;
  final bool isOptimizing;
  final VoidCallback? onOpenTransfers;
  final VoidCallback? onOpenSecurity;

  const OverviewTab({
    super.key,
    required this.pairingCode,
    required this.devices,
    required this.stats,
    required this.transfers,
    required this.activityLog,
    required this.isDark,
    required this.accent,
    required this.onRefreshCode,
    required this.waveAnimation,
    required this.onOptimize,
    required this.isOptimizing,
    this.onOpenTransfers,
    this.onOpenSecurity,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, box) {
        final wide = box.maxWidth >= 980;
        final vitals = _VitalsColumn(
          stats: stats,
          isDark: isDark,
          accent: accent,
          onOptimize: onOptimize,
          isOptimizing: isOptimizing,
        );
        final now = _NowColumn(
          devices: devices,
          transfers: transfers,
          isDark: isDark,
          accent: accent,
          onOpenTransfers: onOpenTransfers,
        );
        final recent = _RecentColumn(
          activityLog: activityLog,
          isDark: isDark,
          accent: accent,
          onOpenSecurity: onOpenSecurity,
        );
        if (wide) {
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 3, child: vitals),
                const SizedBox(width: 16),
                Expanded(flex: 3, child: now),
                const SizedBox(width: 16),
                Expanded(flex: 4, child: recent),
              ],
            ),
          );
        }
        return ListView(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
          children: [
            vitals,
            const SizedBox(height: 16),
            now,
            const SizedBox(height: 16),
            SizedBox(height: 320, child: recent),
          ],
        );
      },
    );
  }
}

class _VitalsColumn extends StatelessWidget {
  final Map<String, dynamic> stats;
  final bool isDark;
  final Color accent;
  final VoidCallback onOptimize;
  final bool isOptimizing;

  const _VitalsColumn({
    required this.stats,
    required this.isDark,
    required this.accent,
    required this.onOptimize,
    required this.isOptimizing,
  });

  @override
  Widget build(BuildContext context) {
    final cpu = (stats['cpu_percent'] as num?)?.toDouble() ?? 0;
    final ram = (stats['ram_percent'] as num?)?.toDouble() ?? 0;
    final disk = (stats['disk_percent'] as num?)?.toDouble() ?? 0;
    final batt = (stats['battery_percent'] as num?)?.toDouble();
    final fg = isDark ? Colors.white : Colors.black;
    return GlassContainer(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Vitals', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: fg)),
          const SizedBox(height: 16),
          _bar('CPU', cpu, const Color(0xFFF43F5E), isDark),
          const SizedBox(height: 12),
          _bar('RAM', ram, accent, isDark),
          const SizedBox(height: 12),
          _bar('Disk', disk, const Color(0xFFF59E0B), isDark),
          if (batt != null) ...[
            const SizedBox(height: 12),
            _bar('Battery', batt, const Color(0xFF10B981), isDark),
          ],
          const SizedBox(height: 16),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: onOptimize,
              child: Text(isOptimizing ? 'Optimizing…' : 'Optimize memory',
                  style: GoogleFonts.inter(fontWeight: FontWeight.w600, color: accent)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _bar(String label, double value, Color color, bool isDark) {
    final v = value.clamp(0, 100) / 100;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label, style: GoogleFonts.inter(fontSize: 12, color: isDark ? Colors.white70 : Colors.black54)),
            const Spacer(),
            Text('${value.toStringAsFixed(0)}%',
                style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: color)),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: v,
            minHeight: 6,
            backgroundColor: color.withOpacity(0.12),
            color: color,
          ),
        ),
      ],
    );
  }
}

class _NowColumn extends StatelessWidget {
  final List<dynamic> devices;
  final Map<String, dynamic> transfers;
  final bool isDark;
  final Color accent;
  final VoidCallback? onOpenTransfers;

  const _NowColumn({
    required this.devices,
    required this.transfers,
    required this.isDark,
    required this.accent,
    this.onOpenTransfers,
  });

  @override
  Widget build(BuildContext context) {
    final fg = isDark ? Colors.white : Colors.black;
    final active = transfers.entries.toList();
    return GlassContainer(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Right now', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: fg)),
          const SizedBox(height: 12),
          Text('${devices.length} paired device${devices.length == 1 ? '' : 's'}',
              style: GoogleFonts.inter(fontSize: 13, color: fg.withOpacity(0.7))),
          const SizedBox(height: 12),
          if (active.isEmpty)
            Text('No transfers in flight',
                style: GoogleFonts.inter(fontSize: 13, color: fg.withOpacity(0.45)))
          else
            ...active.take(4).map((e) {
              final m = e.value is Map ? Map<String, dynamic>.from(e.value as Map) : <String, dynamic>{};
              final name = m['name']?.toString() ?? e.key.toString();
              final pct = (m['progress'] as num?)?.toDouble() ?? 0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(fontSize: 12, color: fg)),
                    const SizedBox(height: 4),
                    LinearProgressIndicator(value: pct.clamp(0, 1), color: accent, minHeight: 4,
                        backgroundColor: accent.withOpacity(0.12)),
                  ],
                ),
              );
            }),
          if (onOpenTransfers != null)
            TextButton(
              onPressed: onOpenTransfers,
              child: Text('Transfers', style: GoogleFonts.inter(color: accent, fontWeight: FontWeight.w600)),
            ),
        ],
      ),
    );
  }
}

class _RecentColumn extends StatelessWidget {
  final List<dynamic> activityLog;
  final bool isDark;
  final Color accent;
  final VoidCallback? onOpenSecurity;

  const _RecentColumn({
    required this.activityLog,
    required this.isDark,
    required this.accent,
    this.onOpenSecurity,
  });

  @override
  Widget build(BuildContext context) {
    final fg = isDark ? Colors.white : Colors.black;
    final items = activityLog.take(10).toList();
    return GlassContainer(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Recent', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: fg)),
              const Spacer(),
              if (onOpenSecurity != null)
                TextButton(
                  onPressed: onOpenSecurity,
                  child: Text('Security', style: GoogleFonts.inter(color: accent, fontWeight: FontWeight.w600)),
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (items.isEmpty)
            Text('Nothing yet. Pair a phone to see activity.',
                style: GoogleFonts.inter(fontSize: 13, color: fg.withOpacity(0.45)))
          else
            ...items.map((raw) {
              final m = raw is Map ? Map<String, dynamic>.from(raw) : {'title': raw.toString()};
              final title = m['title']?.toString() ?? m['type']?.toString() ?? 'Event';
              final desc = m['description']?.toString() ?? m['desc']?.toString() ?? '';
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: fg)),
                    if (desc.isNotEmpty)
                      Text(desc, maxLines: 2, overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(fontSize: 12, color: fg.withOpacity(0.5))),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

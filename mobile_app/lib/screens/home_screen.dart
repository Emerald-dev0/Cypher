import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/system_provider.dart';
import '../theme/colors.dart';
import '../widgets/stat_ring.dart';
import '../widgets/cypher_card.dart';
import '../widgets/sliver_sized_box.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _activeTab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final cp = context.read<ConnectionProvider>();
      if (cp.ip != null) {
        context.read<SystemProvider>()
          ..startPolling(cp.ip!)
          ..fetchActivity(cp.ip!);
      }
    });
  }

  @override
  void dispose() {
    context.read<SystemProvider>().stopPolling();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cp = context.watch<ConnectionProvider>();
    final sp = context.watch<SystemProvider>();

    if (!cp.isConnected) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.wifi_off_rounded, size: 48, color: CypherColors.textMuted),
              const SizedBox(height: 12),
              const Text('Disconnected', style: TextStyle(color: CypherColors.textSecondary, fontSize: 16)),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            IndexedStack(
              index: _activeTab,
              children: [
                _HomeTab(cp: cp, sp: sp),
                _MoreTab(),
              ],
            ),
            _BottomNav(activeTab: _activeTab, onTab: (i) => setState(() => _activeTab = i)),
          ],
        ),
      ),
    );
  }
}

// ── HOME TAB ──────────────────────────────────────────────────
class _HomeTab extends StatelessWidget {
  final ConnectionProvider cp;
  final SystemProvider sp;
  const _HomeTab({required this.cp, required this.sp});

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        // Header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _getGreeting(),
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: CypherColors.textMuted,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      cp.pcName ?? 'CYPHER PC',
                      style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        color: CypherColors.textPrimary,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: const BoxDecoration(
                            color: CypherColors.battery,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Text(
                          'Connected',
                          style: TextStyle(
                            fontSize: 12,
                            color: CypherColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                IconButton(
                  icon: const Icon(Icons.notifications_outlined, color: CypherColors.textSecondary),
                  onPressed: () => Navigator.pushNamed(context, '/notifications'),
                ),
              ],
            ),
          ),
        ),

        // Stat Gauges (2x2 grid)
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              mainAxisSpacing: 16,
              crossAxisSpacing: 16,
              childAspectRatio: 1,
              children: [
                _StatCard(
                  ring: StatRing(
                    value: sp.cpu / 100,
                    label: 'CPU',
                    icon: Icons.speed_rounded,
                    color: CypherColors.cpu,
                    size: 110,
                  ),
                ),
                _StatCard(
                  ring: StatRing(
                    value: sp.ram / 100,
                    label: 'RAM',
                    icon: Icons.memory_rounded,
                    color: CypherColors.ram,
                    size: 110,
                  ),
                ),
                _StatCard(
                  ring: StatRing(
                    value: sp.disk / 100,
                    label: 'Storage',
                    icon: Icons.storage_rounded,
                    color: CypherColors.storage,
                    size: 110,
                  ),
                ),
                _StatCard(
                  ring: StatRing(
                    value: (sp.battery['percent'] as num?)?.toDouble() ?? 0 / 100,
                    label: 'Battery',
                    icon: Icons.battery_full_rounded,
                    color: CypherColors.battery,
                    size: 110,
                  ),
                ),
              ],
            ),
          ),
        ),

        const SliverSizedBox(height: 24),

        // Quick Controls (2x2)
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              children: [
                _QuickControlTile(
                  icon: Icons.folder_open_rounded,
                  label: 'Get Files',
                  subtitle: 'from PC',
                  color: CypherColors.storage,
                  onTap: () => Navigator.pushNamed(context, '/browser'),
                ),
                _QuickControlTile(
                  icon: Icons.send_rounded,
                  label: 'Send Files',
                  subtitle: 'to PC',
                  color: CypherColors.accent,
                  onTap: () => Navigator.pushNamed(context, '/send'),
                ),
                _QuickControlTile(
                  icon: Icons.screenshot_monitor_rounded,
                  label: 'Screenshot',
                  subtitle: 'capture screen',
                  color: CypherColors.info,
                  onTap: () => _takeScreenshot(context),
                ),
                _QuickControlTile(
                  icon: Icons.lock_rounded,
                  label: 'Lock PC',
                  subtitle: 'secure now',
                  color: CypherColors.error,
                  onTap: () => context.read<SystemProvider>().lock(Provider.of<ConnectionProvider>(context, listen: false).ip!),
                ),
              ],
            ),
          ),
        ),

        const SliverSizedBox(height: 24),

        // Recent Activity
        if (sp.activity.isNotEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Recent Activity',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: CypherColors.textMuted,
                          letterSpacing: 0.5,
                        ),
                      ),
                      GestureDetector(
                        onTap: () => Navigator.pushNamed(context, '/activity'),
                        child: const Text(
                          'See all',
                          style: TextStyle(
                            fontSize: 12,
                            color: CypherColors.accentLight,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  ...List.generate(
                    (sp.activity.length).clamp(0, 3),
                    (i) {
                      final item = sp.activity[i] as Map<String, dynamic>? ?? {};
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: CypherCard(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          child: Row(
                            children: [
                              Icon(Icons.history_rounded, size: 14, color: CypherColors.accentLight),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  item['name'] ?? item['action'] ?? 'Action',
                                  style: const TextStyle(fontSize: 12, color: CypherColors.textPrimary),
                                ),
                              ),
                              Text(
                                item['time'] ?? '',
                                style: const TextStyle(fontSize: 10, color: CypherColors.textMuted),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),

        const SliverSizedBox(height: 100),
      ],
    );
  }

  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  }

  void _takeScreenshot(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Taking screenshot...')),
    );
  }
}

// ── STAT CARD ─────────────────────────────────────────────────
class _StatCard extends StatelessWidget {
  final StatRing ring;
  const _StatCard({required this.ring});

  @override
  Widget build(BuildContext context) {
    return CypherCard(
      padding: const EdgeInsets.all(16),
      child: Center(child: ring),
    );
  }
}

// ── QUICK CONTROL TILE ────────────────────────────────────────
class _QuickControlTile extends StatefulWidget {
  final IconData icon;
  final String label;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const _QuickControlTile({
    required this.icon,
    required this.label,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  State<_QuickControlTile> createState() => _QuickControlTileState();
}

class _QuickControlTileState extends State<_QuickControlTile> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.95 : 1.0,
        duration: const Duration(milliseconds: 100),
        child: Container(
          decoration: BoxDecoration(
            color: widget.color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: widget.color.withOpacity(0.2),
              width: 1.5,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(widget.icon, color: widget.color, size: 32),
              const SizedBox(height: 8),
              Text(
                widget.label,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: CypherColors.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 2),
              Text(
                widget.subtitle,
                style: const TextStyle(
                  fontSize: 10,
                  color: CypherColors.textMuted,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── MORE TAB ──────────────────────────────────────────────────
class _MoreTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 120),
      children: [
        _SectionHeader(title: 'Files & Transfer'),
        const SizedBox(height: 10),
        _MoreItem(icon: Icons.folder_rounded, title: 'Browse Files', subtitle: 'PC files', onTap: () => Navigator.pushNamed(context, '/browser')),
        _MoreItem(icon: Icons.send_rounded, title: 'Send to PC', subtitle: 'Upload files', onTap: () => Navigator.pushNamed(context, '/send')),
        const SizedBox(height: 20),
        _SectionHeader(title: 'Control & Commands'),
        const SizedBox(height: 10),
        _MoreItem(icon: Icons.keyboard_rounded, title: 'Remote Control', subtitle: 'Type & hotkeys', onTap: () => Navigator.pushNamed(context, '/controls')),
        _MoreItem(icon: Icons.screenshot_monitor_rounded, title: 'Screenshot', subtitle: 'Capture screen', onTap: () => Navigator.pushNamed(context, '/recorder')),
        const SizedBox(height: 20),
        _SectionHeader(title: 'System'),
        const SizedBox(height: 10),
        _MoreItem(icon: Icons.settings_rounded, title: 'Settings', subtitle: 'Configuration', onTap: () => Navigator.pushNamed(context, '/settings')),
        _MoreItem(icon: Icons.history_rounded, title: 'Activity', subtitle: 'Recent actions', onTap: () => Navigator.pushNamed(context, '/activity')),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title.toUpperCase(),
      style: const TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: CypherColors.textMuted,
        letterSpacing: 0.8,
      ),
    );
  }
}

class _MoreItem extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MoreItem({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: CypherCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: CypherColors.bgOverlay,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, size: 20, color: CypherColors.textSecondary),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: CypherColors.textPrimary)),
                  Text(subtitle, style: const TextStyle(fontSize: 12, color: CypherColors.textMuted)),
                ],
              ),
            ),
            const Icon(Icons.arrow_forward_ios_rounded, size: 13, color: CypherColors.textMuted),
          ],
        ),
      ),
    );
  }
}

// ── BOTTOM NAV ────────────────────────────────────────────────
class _BottomNav extends StatelessWidget {
  final int activeTab;
  final void Function(int) onTab;

  const _BottomNav({required this.activeTab, required this.onTab});

  @override
  Widget build(BuildContext context) {
    return Positioned(
      bottom: 20,
      left: 20,
      right: 20,
      child: Container(
        height: 64,
        decoration: BoxDecoration(
          color: CypherColors.bgCard,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: CypherColors.border),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _NavItem(index: 0, active: activeTab, icon: Icons.home_rounded, label: 'Home', onTap: onTab),
            _NavItem(index: -1, active: -1, icon: Icons.send_rounded, label: 'Send', onTap: (_) => Navigator.pushNamed(context, '/send')),
            _NavItem(index: -2, active: -1, icon: Icons.keyboard_rounded, label: 'Control', onTap: (_) => Navigator.pushNamed(context, '/controls')),
            _NavItem(index: 1, active: activeTab, icon: Icons.more_horiz_rounded, label: 'More', onTap: onTab),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final int index;
  final int active;
  final IconData icon;
  final String label;
  final void Function(int) onTap;

  const _NavItem({
    required this.index,
    required this.active,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isActive = index >= 0 && index == active;
    return GestureDetector(
      onTap: () => onTap(index),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: isActive ? CypherColors.accent : CypherColors.textMuted, size: 22),
          const SizedBox(height: 4),
          Text(label, style: TextStyle(fontSize: 9, fontWeight: isActive ? FontWeight.w600 : FontWeight.w400, color: isActive ? CypherColors.accent : CypherColors.textMuted)),
        ],
      ),
    );
  }
}

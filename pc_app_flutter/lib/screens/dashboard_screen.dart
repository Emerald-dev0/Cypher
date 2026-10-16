import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:window_manager/window_manager.dart';
import 'package:provider/provider.dart';
import 'package:file_picker/file_picker.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../services/bridge_service.dart';
import '../services/theme_service.dart';
import '../services/update_service.dart';

// Tab Modules
import 'tabs/transfers_tab.dart';
import 'tabs/files_tab.dart';
import 'tabs/security_tab.dart';
import 'tabs/activity_tab.dart';
import 'tabs/settings_tab.dart';
import 'tabs/devices_tab.dart';
import 'tabs/overview_tab.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> with TickerProviderStateMixin {
  String _activeTab = "Overview";
  final BridgeService _bridge = BridgeService();
  Timer? _syncTimer;
  late AnimationController _waveController;

  // Live Data State
  String _pairingCode = "------";
  String _pcIp = "127.0.0.1";
  bool _isSystemActive = true;
  bool _isOptimizing = false;
  List<dynamic> _devices = [];
  List<dynamic> _sharedFolders = [];
  List<dynamic> _securitySessions = [];
  List<dynamic> _activityLog = [];
  Map<String, dynamic> _stats = {
    "cpu_percent": 0.0,
    "ram_percent": 0.0,
    "disk_percent": 0.0,
    "ram_used": 0.0,
    "ram_total": 0.0,
  };
  Map<String, dynamic> _activeTransfers = {};
  Map<String, dynamic> _settings = {};
  UpdateResult? _updateResult;
  bool _updateBannerDismissed = false;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
    _startSync();
    _loadSettings();
    _checkForUpdate();
  }

  Future<void> _checkForUpdate() async {
    final result = await UpdateService.check();
    if (mounted) setState(() => _updateResult = result);
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    _waveController.dispose();
    super.dispose();
  }

  void _startSync() {
    _syncTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      if (!mounted) return;

      try {
        // Parallel fetching to avoid sequential bottlenecks
        final results = await Future.wait([
          _bridge.getConnectCode(),
          _bridge.getPairedDevices(),
          _bridge.getSystemStats(),
          _bridge.getTransfers(),
          _bridge.getSharedFolders(),
          _bridge.getSecuritySessions(),
          _bridge.getActivityLog(),
          _bridge.getNetworkInfo(),
        ]).timeout(const Duration(seconds: 5));

        if (mounted) {
          setState(() {
            _pairingCode = results[0] as String;
            _devices = results[1] as List<dynamic>;
            final stats = results[2] as Map<String, dynamic>;
            if (stats.isNotEmpty) _stats = stats;
            _activeTransfers = results[3] as Map<String, dynamic>;
            _sharedFolders = results[4] as List<dynamic>;
            _securitySessions = results[5] as List<dynamic>;
            _activityLog = results[6] as List<dynamic>;
            final netInfo = results[7] as Map<String, dynamic>;
            _pcIp = netInfo['pc_ip'] ?? "127.0.0.1";
            _isSystemActive = true;
          });
        }

        // Special case: Polling for settings changes every 10 ticks (20s)
        if (timer.tick % 10 == 0) {
          _loadSettings();
        }

      } catch (e) {
        // Only trigger disconnect state if multiple consecutive failures occur
        if (mounted && timer.tick > 5) {
           setState(() => _isSystemActive = false);
        }
      }
    });
  }

  Future<void> _loadSettings() async {
    try {
      final s = await _bridge.getSettings();
      if (mounted) setState(() => _settings = s);
    } catch (_) {}
  }

  Future<void> _updateSetting(String key, dynamic value) async {
    try {
      final success = await _bridge.saveSettings({key: value});
      if (success) {
        _loadSettings();
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Failed to update system setting.")));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Setting Update Error: $e")));
    }
  }

  Future<void> _optimizeSystem() async {
    if (_isOptimizing) return;
    setState(() => _isOptimizing = true);
    try {
      final result = await _bridge.optimizeSystem();
      if (mounted) {
        if (result != null && result['success'] == true) {
          final mb = result['freed_mb'] ?? 0;
          final msg = mb > 0 ? "Optimization complete — ${mb} MB freed" : "Optimization complete";
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        } else {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Optimization failed — check backend logs.")));
        }
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Optimization error: $e")));
    } finally {
      if (mounted) setState(() => _isOptimizing = false);
    }
  }

  Future<void> _refreshCode() async {
    try {
      final newCode = await _bridge.refreshConnectCode();
      if (mounted) {
        setState(() => _pairingCode = newCode);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Pairing code rotated successfully.")));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Failed to refresh code.")));
    }
  }

  Future<void> _addSharedFolder() async {
    try {
      String? result = await FilePicker.platform.getDirectoryPath();
      if (result != null) {
        final currentPaths = _sharedFolders.map((f) => f['path'] as String).toList();
        if (!currentPaths.contains(result)) {
          currentPaths.add(result);
          final success = await _bridge.saveSettings({"shared_folders": currentPaths});
          if (success) {
            if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("New folder shared.")));
            // Sync will pick it up naturally
          }
        }
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("File Picker Error: $e")));
    }
  }

  Future<void> _removeSharedFolder(String path) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1E),
        title: const Text("Remove Shared Folder?", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        content: Text("Stop sharing access to: $path", style: const TextStyle(color: Colors.white60)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text("CANCEL", style: TextStyle(color: Colors.white24))),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
            child: const Text("REMOVE ACCESS"),
          ),
        ],
      ),
    ) ?? false;

    if (!confirmed) return;

    try {
      final currentPaths = _sharedFolders.map((f) => f['path'] as String).toList();
      currentPaths.remove(path);
      final success = await _bridge.saveSettings({"shared_folders": currentPaths});
      if (success) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Folder unshared.")));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Error removing folder: $e")));
    }
  }

  Future<void> _revokeGuestSession(String token) async {
    try {
      final success = await _bridge.endGuestSession(token);
      if (success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Guest Access Revoked")));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Revoke Error: $e")));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Provider.of<ThemeService>(context);
    final isDark = theme.isDarkMode;
    final accent = const Color(0xFF7C3AED);

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Row(
        children: [
          _buildSidebar(accent, isDark, theme),
          Expanded(
            child: Column(
              children: [
                _buildTopBar(accent, isDark),
                if (_updateResult != null && !_updateBannerDismissed)
                  _buildUpdateBanner(accent),
                Expanded(
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 600),
                    child: _isSystemActive
                        ? IndexedStack(
                            key: const ValueKey("active_stack"),
                            index: _getTabIndex(_activeTab),
                            children: [
                              OverviewTab(
                                pairingCode: _pairingCode,
                                devices: _devices,
                                stats: _stats,
                                transfers: _activeTransfers,
                                activityLog: _activityLog,
                                isDark: isDark,
                                accent: accent,
                                onRefreshCode: _refreshCode,
                                waveAnimation: _waveController,
                                onOptimize: _optimizeSystem,
                                isOptimizing: _isOptimizing,
                                onOpenTransfers: () => setState(() => _activeTab = 'Transfers'),
                                onOpenSecurity: () => setState(() => _activeTab = 'Security'),
                              ),
                              FilesTab(
                                isDark: isDark,
                                accent: accent,
                                sharedFolders: _sharedFolders,
                                onAddFolder: _addSharedFolder,
                                onRemoveFolder: _removeSharedFolder,
                              ),
                              TransfersTab(activeTransfers: _activeTransfers, activityLog: _activityLog, isDark: isDark, accent: accent),
                              DevicesTab(devices: _devices, isDark: isDark, accent: accent),
                              Column(
                                children: [
                                  Expanded(flex: 3, child: SecurityTab(isDark: isDark, accent: accent, sessions: _securitySessions, pcIp: _pcIp, onRevokeSession: _revokeGuestSession)),
                                  Expanded(flex: 2, child: ActivityTab(isDark: isDark, accent: accent, logs: _activityLog)),
                                ],
                              ),
                              SettingsTab(
                                  settings: _settings,
                                  isDark: isDark,
                                  accent: accent,
                                  themeService: theme,
                                  onUpdateSetting: _updateSetting),
                            ],
                          )
                        : _buildConnectionLostState(accent),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  int _getTabIndex(String tab) {
    switch (tab) {
      case "Overview": return 0;
      case "Files": return 1;
      case "Transfers": return 2;
      case "Devices": return 3;
      case "Security": return 4;
      case "Settings": return 5;
      default: return 0;
    }
  }

  Widget _buildUpdateBanner(Color accent) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF59E0B).withOpacity(0.08),
        border: Border(bottom: BorderSide(color: const Color(0xFFF59E0B).withOpacity(0.2))),
      ),
      child: Row(
        children: [
          const Icon(Icons.system_update_rounded, color: Color(0xFFF59E0B), size: 15),
          const SizedBox(width: 10),
          Text(
            'CYPHER v${_updateResult!.latestVersion} is available',
            style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: const Color(0xFFF59E0B)),
          ),
          const SizedBox(width: 16),
          GestureDetector(
            onTap: () => UpdateService.openReleasePage(_updateResult!.downloadUrl),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text('Download', style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.black)),
            ),
          ),
          const Spacer(),
          GestureDetector(
            onTap: () => setState(() => _updateBannerDismissed = true),
            child: const Icon(Icons.close_rounded, size: 15, color: Color(0xFFF59E0B)),
          ),
        ],
      ),
    );
  }

  Widget _buildSidebar(Color accent, bool isDark, ThemeService theme) {
    return Container(
      width: 230,
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF0A0A0C) : const Color(0xFFF0F0F5),
        border: Border(right: BorderSide(color: isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.07))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Logo
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
            child: Row(
              children: [
                Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    color: accent.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: accent.withOpacity(0.3), width: 1),
                    boxShadow: [BoxShadow(color: accent.withOpacity(0.2), blurRadius: 12, spreadRadius: -2)],
                  ),
                  child: Icon(Icons.shield_rounded, color: accent, size: 18),
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('CYPHER', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w800, color: isDark ? Colors.white : Colors.black, letterSpacing: 0.5)),
                    Text('Control Tower', style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w500, color: isDark ? Colors.white30 : Colors.black38)),
                  ],
                ),
              ],
            ),
          ),

          // Nav groups
          _sectionLabel('MAIN', isDark),
          _navItem('Overview', Icons.dashboard_rounded, accent, isDark),
          _navItem('Files', Icons.folder_shared_rounded, accent, isDark),
          _navItem('Transfers', Icons.sync_alt_rounded, accent, isDark),

          const SizedBox(height: 12),
          _sectionLabel('ACCESS', isDark),
          _navItem('Devices', Icons.devices_rounded, accent, isDark),
          _navItem('Security', Icons.shield_rounded, accent, isDark),

          const Spacer(),

          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('PAIRING', style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w700, color: isDark ? Colors.white24 : Colors.black26, letterSpacing: 1.8)),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(10, 10, 10, 8),
                  decoration: BoxDecoration(
                    color: accent.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: accent.withOpacity(0.25)),
                  ),
                  child: Column(
                    children: [
                      if (_pairingCode.length == 6 && _pairingCode != '------')
                        QrImageView(
                          data: 'cypher://pair?ip=$_pcIp&code=$_pairingCode',
                          size: 108,
                          backgroundColor: Colors.white,
                        ),
                      const SizedBox(height: 8),
                      Text(_pairingCode, style: GoogleFonts.jetBrainsMono(fontSize: 18, fontWeight: FontWeight.w700, color: accent, letterSpacing: 3)),
                      const SizedBox(height: 4),
                      GestureDetector(
                        onTap: _refreshCode,
                        child: Text('Regenerate', style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, color: isDark ? Colors.white54 : Colors.black54)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Status pill
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: (_isSystemActive ? const Color(0xFF10B981) : Colors.amber).withOpacity(0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: (_isSystemActive ? const Color(0xFF10B981) : Colors.amber).withOpacity(0.2)),
              ),
              child: Row(
                children: [
                  Container(
                    width: 7, height: 7,
                    decoration: BoxDecoration(
                      color: _isSystemActive ? const Color(0xFF10B981) : Colors.amber,
                      shape: BoxShape.circle,
                      boxShadow: [BoxShadow(color: (_isSystemActive ? const Color(0xFF10B981) : Colors.amber).withOpacity(0.6), blurRadius: 6, spreadRadius: 1)],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _isSystemActive ? 'System Secure' : 'Reconnecting...',
                      style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: _isSystemActive ? const Color(0xFF10B981) : Colors.amber),
                    ),
                  ),
                ],
              ),
            ),
          ),

          _buildThemeToggle(theme, isDark, accent),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Divider(height: 1, color: isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.07)),
          ),
          const SizedBox(height: 8),
          _navItem('Settings', Icons.settings_rounded, accent, isDark),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _sectionLabel(String label, bool isDark) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 4),
      child: Text(label, style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w700, color: isDark ? Colors.white24 : Colors.black26, letterSpacing: 1.8)),
    );
  }

  Widget _navItem(String title, IconData icon, Color accent, bool isDark) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 1),
      child: _NavItem(
        title: title,
        icon: icon,
        active: _activeTab == title,
        accent: accent,
        isDark: isDark,
        onTap: () => setState(() => _activeTab = title),
      ),
    );
  }

  Widget _buildTopBar(Color accent, bool isDark) {
    return GestureDetector(
      onPanStart: (_) => windowManager.startDragging(),
      child: Container(
        height: 52,
        decoration: BoxDecoration(
          color: !_isSystemActive
              ? const Color(0xFF3F1D1D)
              : (isDark ? const Color(0xFF0F0F11) : const Color(0xFFF2F2F7)),
          border: Border(bottom: BorderSide(color: isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.06))),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Row(
          children: [
            Container(
              width: 8, height: 8,
              decoration: BoxDecoration(
                color: _isSystemActive ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              _isSystemActive ? 'Node ready' : 'Node down',
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: _isSystemActive ? const Color(0xFF10B981) : const Color(0xFFEF4444),
              ),
            ),
            const SizedBox(width: 12),
            Text(
              (_settings['device_name'] ?? 'This PC').toString(),
              style: GoogleFonts.inter(fontSize: 11, color: isDark ? Colors.white54 : Colors.black54),
            ),
            const SizedBox(width: 8),
            Text('·', style: GoogleFonts.inter(color: isDark ? Colors.white24 : Colors.black26)),
            const SizedBox(width: 8),
            Text('$_pcIp:5000', style: GoogleFonts.inter(fontSize: 11, color: isDark ? Colors.white38 : Colors.black45)),
            const SizedBox(width: 16),
            Text(_activeTab, style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: accent)),
            const Spacer(),
            // Window controls
            _windowBtn(Icons.remove_rounded, () => windowManager.minimize(), isDark),
            _windowBtn(Icons.check_box_outline_blank_rounded, () async {
              if (await windowManager.isMaximized()) windowManager.unmaximize();
              else windowManager.maximize();
            }, isDark),
            _windowBtn(Icons.close_rounded, () => windowManager.close(), isDark, isClose: true),
          ],
        ),
      ),
    );
  }

  Widget _windowBtn(IconData icon, VoidCallback tap, bool isDark, {bool isClose = false}) {
    return _WindowButton(icon: icon, onTap: tap, isDark: isDark, isClose: isClose);
  }

  Widget _buildConnectionLostState(Color accent) {
    return Container(
      color: const Color(0xFF0F0F11),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0.0, end: 1.0),
              duration: const Duration(seconds: 2),
              builder: (context, value, child) {
                return Opacity(
                  opacity: value,
                  child: Transform.scale(
                    scale: 0.8 + (0.2 * value),
                    child: child,
                  ),
                );
              },
              child: Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: accent.withOpacity(0.05),
                  shape: BoxShape.circle,
                  border: Border.all(color: accent.withOpacity(0.1), width: 1),
                ),
                child: Icon(Icons.shield_moon_outlined, color: accent, size: 64),
              ),
            ),
            const SizedBox(height: 48),
            Text(
              "CONNECTION LOST",
              style: GoogleFonts.inter(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: Colors.white,
                letterSpacing: 8,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              "CHECK IF MOBILE APP IS RUNNING ON THE SAME NETWORK",
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(
                fontSize: 10,
                color: Colors.white24,
                letterSpacing: 2,
              ),
            ),
            const SizedBox(height: 48),
            SizedBox(
              width: 280,
              child: Column(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(100),
                    child: LinearProgressIndicator(
                      backgroundColor: Colors.white.withOpacity(0.03),
                      valueColor: AlwaysStoppedAnimation(accent),
                      minHeight: 2,
                    ),
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: () => setState(() => _isSystemActive = true),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: accent,
                      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text("RETRY CONNECTION", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildThemeToggle(ThemeService theme, bool isDark, Color accent) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: theme.toggleTheme,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isDark ? Colors.white.withOpacity(0.04) : Colors.black.withOpacity(0.04),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.06)),
            ),
            child: Row(
              children: [
                Icon(isDark ? Icons.light_mode_rounded : Icons.dark_mode_rounded, color: isDark ? Colors.white38 : Colors.black38, size: 15),
                const SizedBox(width: 10),
                Text(isDark ? 'Light Mode' : 'Dark Mode', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500, color: isDark ? Colors.white38 : Colors.black45)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Sidebar nav item with hover + active state ──────────────────
class _NavItem extends StatefulWidget {
  final String title;
  final IconData icon;
  final bool active;
  final Color accent;
  final bool isDark;
  final VoidCallback onTap;

  const _NavItem({
    required this.title,
    required this.icon,
    required this.active,
    required this.accent,
    required this.isDark,
    required this.onTap,
  });

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          decoration: BoxDecoration(
            color: widget.active
                ? widget.accent.withOpacity(0.1)
                : _hovered
                    ? (widget.isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.04))
                    : Colors.transparent,
            borderRadius: BorderRadius.circular(9),
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 140),
                width: 3, height: 38,
                decoration: BoxDecoration(
                  color: widget.active ? widget.accent : Colors.transparent,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(widget.icon,
                          size: 17,
                          color: widget.active
                              ? widget.accent
                              : (widget.isDark ? Colors.white38 : Colors.black38)),
                      const SizedBox(width: 11),
                      Text(widget.title,
                          style: GoogleFonts.inter(
                              fontSize: 13,
                              fontWeight: widget.active ? FontWeight.w600 : FontWeight.w400,
                              color: widget.active
                                  ? (widget.isDark ? Colors.white : Colors.black)
                                  : (widget.isDark ? Colors.white54 : Colors.black54))),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Window control button with hover ───────────────────────────
class _WindowButton extends StatefulWidget {
  final IconData icon;
  final VoidCallback onTap;
  final bool isDark;
  final bool isClose;

  const _WindowButton({required this.icon, required this.onTap, required this.isDark, this.isClose = false});

  @override
  State<_WindowButton> createState() => _WindowButtonState();
}

class _WindowButtonState extends State<_WindowButton> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final hoverBg = widget.isClose
        ? Colors.redAccent.withOpacity(0.15)
        : (widget.isDark ? Colors.white.withOpacity(0.07) : Colors.black.withOpacity(0.06));

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          width: 46, height: 52,
          color: _hovered ? hoverBg : Colors.transparent,
          child: Icon(widget.icon,
              size: 15,
              color: widget.isClose
                  ? (_hovered ? Colors.redAccent : Colors.redAccent.withOpacity(0.45))
                  : (widget.isDark ? Colors.white30 : Colors.black38)),
        ),
      ),
    );
  }
}

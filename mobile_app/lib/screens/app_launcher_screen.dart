import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/system_provider.dart';
import '../theme/colors.dart';
import '../widgets/shimmer_box.dart';

class AppLauncherScreen extends StatefulWidget {
  const AppLauncherScreen({super.key});

  @override
  State<AppLauncherScreen> createState() => _AppLauncherScreenState();
}

class _AppLauncherScreenState extends State<AppLauncherScreen> {
  String _searchQuery = '';
  final _searchCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ip = context.read<ConnectionProvider>().ip ?? '';
      if (ip.isNotEmpty) context.read<SystemProvider>().fetchApps(ip);
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  List _filtered(List apps) {
    if (_searchQuery.isEmpty) return apps;
    final q = _searchQuery.toLowerCase();
    return apps.where((a) => (a['name']?.toString().toLowerCase() ?? '').contains(q)).toList();
  }

  Future<void> _closeApp(Map app) async {
    final name = app['name']?.toString() ?? 'Unknown';
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Close App?'),
        content: Text('Close $name?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Close', style: TextStyle(color: CypherColors.error, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );

    if (confirm == true && mounted) {
      final ip = context.read<ConnectionProvider>().ip ?? '';
      final ok = await context.read<SystemProvider>().closeApp(ip, name);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok ? 'App closed' : 'Failed to close app'),
        backgroundColor: ok ? CypherColors.accent : CypherColors.error,
      ));
    }
  }

  IconData _iconFor(String name) {
    final n = name.toLowerCase();
    if (n.contains('chrome'))   return Icons.public_rounded;
    if (n.contains('spotify'))  return Icons.music_note_rounded;
    if (n.contains('vlc'))      return Icons.video_library_rounded;
    if (n.contains('word'))     return Icons.description_rounded;
    if (n.contains('excel'))    return Icons.table_chart_rounded;
    if (n.contains('discord'))  return Icons.chat_bubble_rounded;
    if (n.contains('code') || n.contains('visual')) return Icons.code_rounded;
    if (n.contains('steam'))    return Icons.videogame_asset_rounded;
    if (n.contains('notepad'))  return Icons.edit_note_rounded;
    if (n.contains('explorer')) return Icons.folder_rounded;
    return Icons.apps_rounded;
  }

  @override
  Widget build(BuildContext context) {
    final sp   = context.watch<SystemProvider>();
    final ip   = context.read<ConnectionProvider>().ip ?? '';
    final list = _filtered(sp.apps);

    return Scaffold(
      appBar: AppBar(
        title: const Text('App Launcher'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: () => sp.fetchApps(ip),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _searchCtrl,
              onChanged: (v) => setState(() => _searchQuery = v),
              decoration: const InputDecoration(
                hintText: 'Search apps...',
                prefixIcon: Icon(Icons.search_rounded, size: 18),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: sp.isLoading
              ? GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3, childAspectRatio: 0.85, mainAxisSpacing: 16, crossAxisSpacing: 16),
                  itemCount: 12,
                  itemBuilder: (_, __) => const ShimmerBox(width: double.infinity, height: double.infinity, radius: 12),
                )
              : list.isEmpty
                ? const Center(child: Text('No apps found', style: TextStyle(color: CypherColors.textMuted)))
                : GridView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      childAspectRatio: 0.85,
                      mainAxisSpacing: 16,
                      crossAxisSpacing: 16,
                    ),
                    itemCount: list.length,
                    itemBuilder: (_, i) {
                      final app  = list[i] as Map;
                      final name = app['name']?.toString() ?? '';

                      return GestureDetector(
                        onTap: () async {
                          HapticFeedback.mediumImpact();
                          await sp.launchApp(ip, app['path']?.toString() ?? '');
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                              content: Text('Launching $name…'),
                              backgroundColor: CypherColors.accent,
                            ));
                          }
                        },
                        onLongPress: () {
                          HapticFeedback.heavyImpact();
                          _closeApp(app);
                        },
                        child: Column(
                          children: [
                            Container(
                              width: 60, height: 60,
                              decoration: BoxDecoration(
                                color: CypherColors.bgCard,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(color: CypherColors.border),
                              ),
                              child: Icon(_iconFor(name), color: CypherColors.accentLight, size: 28),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              name,
                              textAlign: TextAlign.center,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w400, color: CypherColors.textSecondary),
                            ),
                          ],
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

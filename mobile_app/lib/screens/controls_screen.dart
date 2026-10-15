import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/system_provider.dart';
import '../services/api_service.dart';
import '../theme/colors.dart';
import '../theme/app_theme.dart';
import '../widgets/cypher_button.dart';
import '../widgets/cypher_card.dart';
import '../widgets/control_button.dart';

class ControlsScreen extends StatefulWidget {
  const ControlsScreen({super.key});

  @override
  State<ControlsScreen> createState() => _ControlsScreenState();
}

class _ControlsScreenState extends State<ControlsScreen> {
  Timer? _statusTimer;
  Uint8List? _screenshotBytes;
  bool _isTakingScreenshot = false;
  final _typeCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ip = context.read<ConnectionProvider>().ip ?? '';
      if (ip.isNotEmpty) {
        context.read<SystemProvider>().fetchActiveWindow(ip);
        context.read<SystemProvider>().fetchVolume(ip);
        _statusTimer = Timer.periodic(const Duration(seconds: 5), (_) {
          if (mounted) context.read<SystemProvider>().fetchActiveWindow(ip);
        });
      }
    });
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    _typeCtrl.dispose();
    super.dispose();
  }

  void _toast(String msg, {bool err = false}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: err ? CypherColors.error : CypherColors.accent,
    ));
  }

  Future<void> _takeScreenshot() async {
    final ip = context.read<ConnectionProvider>().ip ?? '';
    setState(() => _isTakingScreenshot = true);
    try {
      final bytes = await ApiService.getScreenshot(ip);
      setState(() { _screenshotBytes = bytes; _isTakingScreenshot = false; });
      _toast('Screenshot captured');
    } catch (_) {
      setState(() => _isTakingScreenshot = false);
      _toast('Failed to capture screen', err: true);
    }
  }

  Future<void> _saveScreenshot() async {
    if (_screenshotBytes == null) return;
    try {
      // Get user-visible Downloads folder (not app cache)
      Directory downloadDir;
      try {
        final external = await getExternalStorageDirectory();
        if (external != null) {
          final parts = external.path.split('/');
          final storageIndex = parts.indexOf('storage');
          if (storageIndex >= 0) {
            final publicPath = parts.sublist(0, storageIndex + 2).join('/') + '/Download';
            downloadDir = Directory(publicPath);
          } else {
            downloadDir = external;
          }
        } else {
          downloadDir = await getApplicationDocumentsDirectory();
        }
      } catch (_) {
        downloadDir = await getApplicationDocumentsDirectory();
      }

      await downloadDir.create(recursive: true);

      final fileName = 'Screenshot_${DateTime.now().millisecondsSinceEpoch}.png';
      final filePath = '${downloadDir.path}/$fileName';
      final file = File(filePath);
      await file.writeAsBytes(_screenshotBytes!);
      _toast('Saved to Downloads folder');
    } catch (e) {
      _toast('Failed to save screenshot', err: true);
    }
  }

  Future<void> _sendType() async {
    final text = _typeCtrl.text.trim();
    if (text.isEmpty) return;
    final ip = context.read<ConnectionProvider>().ip ?? '';
    try {
      await ApiService.remoteType(ip, text);
      _typeCtrl.clear();
      FocusScope.of(context).unfocus();
    } catch (_) {
      _toast('Type failed', err: true);
    }
  }

  Future<void> _hotkey(List<String> keys) async {
    final ip = context.read<ConnectionProvider>().ip ?? '';
    try { await ApiService.remoteHotkey(ip, keys); } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final sp = context.watch<SystemProvider>();
    final ip = context.read<ConnectionProvider>().ip ?? '';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Controls'),
        actions: [
          if (sp.activeWindow.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(child: Text(sp.activeWindow, style: AppTheme.caption(context), overflow: TextOverflow.ellipsis)),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Screenshot
            CypherSectionHeader(title: 'Screenshot'),
            const SizedBox(height: 8),
            CypherCard(
              child: Column(
                children: [
                  Container(
                    width: double.infinity, height: 180,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                      color: CypherColors.bgDeep,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: _isTakingScreenshot
                        ? const Center(child: CircularProgressIndicator(color: CypherColors.accent))
                        : _screenshotBytes != null
                            ? InteractiveViewer(child: Image.memory(_screenshotBytes!, fit: BoxFit.contain))
                            : const Center(child: Icon(Icons.monitor_rounded, color: CypherColors.textMuted, size: 40)),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: CypherButton(label: 'Capture Screen', onTap: _takeScreenshot, loading: _isTakingScreenshot),
                      ),
                      if (_screenshotBytes != null) ...[
                        const SizedBox(width: 8),
                        Expanded(
                          child: CypherButton(
                            label: 'Save',
                            onTap: _saveScreenshot,
                            variant: CypherButtonVariant.success,
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),

            // Remote keyboard
            const SizedBox(height: 20),
            const CypherSectionHeader(title: 'Remote Keyboard'),
            const SizedBox(height: 8),
            CypherCard(
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _typeCtrl,
                      decoration: const InputDecoration(hintText: 'Type on PC...'),
                      onSubmitted: (_) => _sendType(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.send_rounded, color: CypherColors.accent),
                    onPressed: _sendType,
                  ),
                ],
              ),
            ),

            // Hotkeys
            const SizedBox(height: 20),
            const CypherSectionHeader(title: 'Hotkeys'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8, runSpacing: 8,
              children: [
                _HotkeyChip('Copy',       () => _hotkey(['ctrl', 'c'])),
                _HotkeyChip('Paste',      () => _hotkey(['ctrl', 'v'])),
                _HotkeyChip('Select All', () => _hotkey(['ctrl', 'a'])),
                _HotkeyChip('Undo',       () => _hotkey(['ctrl', 'z'])),
                _HotkeyChip('Redo',       () => _hotkey(['ctrl', 'y'])),
                _HotkeyChip('Close App',  () => _hotkey(['alt', 'f4'])),
                _HotkeyChip('Task Mgr',   () => _hotkey(['ctrl', 'shift', 'esc'])),
                _HotkeyChip('Desktop',    () => _hotkey(['win', 'd'])),
                _HotkeyChip('Alt+Tab',    () => _hotkey(['alt', 'tab'])),
                _HotkeyChip('File Exp',   () => _hotkey(['win', 'e'])),
              ],
            ),

            // Media
            const SizedBox(height: 20),
            const CypherSectionHeader(title: 'Media'),
            const SizedBox(height: 8),
            CypherCard(
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      ControlButton(icon: Icons.skip_previous_rounded, label: 'Prev',  onTap: () => sp.prevTrack(ip)),
                      ControlButton(icon: Icons.play_arrow_rounded,    label: 'Play',  onTap: () => sp.togglePlayPause(ip), active: sp.isPlaying, size: 64),
                      ControlButton(icon: Icons.skip_next_rounded,     label: 'Next',  onTap: () => sp.nextTrack(ip)),
                      ControlButton(icon: Icons.volume_off_rounded,    label: 'Mute',  onTap: () => sp.toggleMute(ip)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Icon(Icons.volume_mute_rounded, size: 16, color: CypherColors.textMuted),
                      Expanded(
                        child: Slider(
                          value: sp.volume.toDouble(),
                          min: 0, max: 100,
                          onChangeEnd: (v) => sp.setVolume(ip, v.toInt()),
                          onChanged: (v) => sp.setVolume(ip, v.toInt()),
                        ),
                      ),
                      const Icon(Icons.volume_up_rounded, size: 16, color: CypherColors.textMuted),
                      const SizedBox(width: 4),
                      Text('${sp.volume}%', style: AppTheme.caption(context)),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HotkeyChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _HotkeyChip(this.label, this.onTap);

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: CypherColors.bgCard,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: CypherColors.border),
        ),
        child: Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: CypherColors.textSecondary)),
      ),
    );
  }
}
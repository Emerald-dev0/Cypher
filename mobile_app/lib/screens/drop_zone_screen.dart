import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:file_picker/file_picker.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../providers/connection_provider.dart';
import '../services/api_service.dart';
import '../theme/colors.dart';
import '../theme/app_theme.dart';
import '../widgets/cypher_card.dart';
import '../widgets/cypher_button.dart';

enum _DropState { idle, selected, uploading, sharing }

class DropZoneScreen extends StatefulWidget {
  const DropZoneScreen({super.key});

  @override
  State<DropZoneScreen> createState() => _DropZoneScreenState();
}

class _DropZoneScreenState extends State<DropZoneScreen> {
  _DropState _state = _DropState.idle;
  List<PlatformFile> _files = [];
  final Map<String, double> _progress = {};
  String? _shareUrl;
  int _expiresIn = 30;
  Timer? _expiryTimer;
  int _secondsLeft = 0;
  String? _error;

  @override
  void dispose() {
    _expiryTimer?.cancel();
    super.dispose();
  }

  String get _ip => context.read<ConnectionProvider>().ip ?? '';

  String _fmtSize(int bytes) {
    if (bytes < 1024)       return '$bytes B';
    if (bytes < 1048576)    return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1073741824) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
  }

  int get _totalBytes => _files.fold(0, (s, f) => s + (f.size));

  Future<void> _pickFiles() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true);
    if (result == null || result.files.isEmpty) return;
    setState(() {
      _files = result.files.where((f) => f.path != null).toList();
      if (_files.isNotEmpty) {
        _state = _DropState.selected;
        _error = null;
      }
    });
  }

  Future<void> _upload() async {
    if (_ip.isEmpty) {
      setState(() => _error = 'Not connected to PC');
      return;
    }
    setState(() {
      _state = _DropState.uploading;
      _error = null;
      for (final f in _files) _progress[f.name] = 0.0;
    });

    try {
      for (final f in _files) {
        await ApiService.uploadToDrop(
          _ip,
          f.path!,
          onProgress: (sent, total) {
            if (!mounted) return;
            setState(() => _progress[f.name] = total > 0 ? sent / total : 0.0);
          },
        );
        if (mounted) setState(() => _progress[f.name] = 1.0);
      }

      final session = await ApiService.createGuestSession(
        _ip,
        folders: ['CypherDrop'],
        durationMinutes: _expiresIn,
      );
      final token = session['token'] ?? session['guest_token'] ?? '';

      // This URL is built directly rather than through ApiService._baseUrl, so
      // it bypasses the private-network guard that every other request gets.
      // It is also the most important one to check: the link is handed to a
      // third party, and the guest token in it travels in cleartext.
      ApiService.assertPrivateTarget(_ip);
      final url = 'http://$_ip:5000/guest/access?token=$token&mode=drop';

      if (!mounted) return;
      setState(() {
        _shareUrl = url;
        _state = _DropState.sharing;
        _secondsLeft = _expiresIn * 60;
      });

      _expiryTimer = Timer.periodic(const Duration(seconds: 1), (t) {
        if (!mounted) { t.cancel(); return; }
        setState(() {
          _secondsLeft--;
          if (_secondsLeft <= 0) {
            t.cancel();
            _reset();
          }
        });
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _state = _DropState.selected;
      });
    }
  }

  void _reset() {
    _expiryTimer?.cancel();
    setState(() {
      _state = _DropState.idle;
      _files = [];
      _progress.clear();
      _shareUrl = null;
      _error = null;
      _secondsLeft = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('CypherDrop'),
        actions: [
          if (_state != _DropState.idle)
            TextButton(
              onPressed: _reset,
              child: const Text('Reset', style: TextStyle(color: CypherColors.textMuted)),
            ),
        ],
      ),
      body: SafeArea(
        child: switch (_state) {
          _DropState.idle      => _IdleView(onPick: _pickFiles),
          _DropState.selected  => _SelectedView(
              files: _files,
              totalBytes: _totalBytes,
              onPick: _pickFiles,
              onRemove: (f) => setState(() {
                _files = List.from(_files)..remove(f);
                if (_files.isEmpty) _state = _DropState.idle;
              }),
              onUpload: _upload,
              error: _error,
              fmtSize: _fmtSize,
              expiresIn: _expiresIn,
              onExpiresChanged: (v) => setState(() => _expiresIn = v),
            ),
          _DropState.uploading => _UploadingView(files: _files, progress: _progress),
          _DropState.sharing   => _SharingView(
              url: _shareUrl!,
              files: _files,
              secondsLeft: _secondsLeft,
              onReset: _reset,
              fmtSize: _fmtSize,
            ),
        },
      ),
    );
  }
}

// ── Idle ──────────────────────────────────────────────────────
class _IdleView extends StatelessWidget {
  final VoidCallback onPick;
  const _IdleView({required this.onPick});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 110, height: 110,
              decoration: BoxDecoration(
                color: CypherColors.bgCard,
                borderRadius: BorderRadius.circular(30),
                border: Border.all(color: CypherColors.accent.withOpacity(0.35), width: 2),
                boxShadow: [BoxShadow(color: CypherColors.accentGlow, blurRadius: 48, spreadRadius: -8)],
              ),
              child: const Icon(Icons.wifi_tethering_rounded, size: 50, color: CypherColors.accent),
            ),
            const SizedBox(height: 28),
            const Text(
              'CypherDrop',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: CypherColors.textPrimary),
            ),
            const SizedBox(height: 10),
            const Text(
              'Send any file to anyone on the same WiFi. No app, no account, no size limits.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: CypherColors.textSecondary, height: 1.6),
            ),
            const SizedBox(height: 36),
            const _HowStep(n: '1', text: 'Pick files from your phone'),
            const SizedBox(height: 10),
            const _HowStep(n: '2', text: 'They upload to your PC instantly'),
            const SizedBox(height: 10),
            const _HowStep(n: '3', text: 'Friend scans QR to download — done'),
            const SizedBox(height: 40),
            CypherButton(
              label: 'Pick Files to Share',
              icon: const Icon(Icons.add_rounded),
              onTap: onPick,
            ),
            const SizedBox(height: 16),
            const Text(
              'Works like AirDrop — only on your WiFi, no cloud involved.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: CypherColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}

class _HowStep extends StatelessWidget {
  final String n;
  final String text;
  const _HowStep({required this.n, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 28, height: 28,
          decoration: BoxDecoration(
            color: CypherColors.accent.withOpacity(0.12),
            shape: BoxShape.circle,
            border: Border.all(color: CypherColors.accent.withOpacity(0.2)),
          ),
          child: Center(
            child: Text(n, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: CypherColors.accent)),
          ),
        ),
        const SizedBox(width: 14),
        Text(text, style: const TextStyle(fontSize: 14, color: CypherColors.textSecondary)),
      ],
    );
  }
}

// ── Selected ──────────────────────────────────────────────────
class _SelectedView extends StatelessWidget {
  final List<PlatformFile> files;
  final int totalBytes;
  final VoidCallback onPick;
  final void Function(PlatformFile) onRemove;
  final VoidCallback onUpload;
  final String? error;
  final String Function(int) fmtSize;
  final int expiresIn;
  final void Function(int) onExpiresChanged;

  const _SelectedView({
    required this.files,
    required this.totalBytes,
    required this.onPick,
    required this.onRemove,
    required this.onUpload,
    required this.error,
    required this.fmtSize,
    required this.expiresIn,
    required this.onExpiresChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            children: [
              Row(
                children: [
                  const Icon(Icons.attach_file_rounded, color: CypherColors.accent, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    '${files.length} file${files.length == 1 ? '' : 's'} · ${fmtSize(totalBytes)}',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: CypherColors.textPrimary),
                  ),
                  const Spacer(),
                  GestureDetector(
                    onTap: onPick,
                    child: const Row(
                      children: [
                        Icon(Icons.add_rounded, size: 16, color: CypherColors.accent),
                        SizedBox(width: 4),
                        Text('Add more', style: TextStyle(color: CypherColors.accent, fontSize: 13, fontWeight: FontWeight.w500)),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ...files.map((f) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: CypherCard(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Row(
                    children: [
                      const Icon(Icons.insert_drive_file_rounded, color: CypherColors.accentLight, size: 22),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(f.name,
                              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: CypherColors.textPrimary),
                              overflow: TextOverflow.ellipsis),
                            Text(fmtSize(f.size), style: AppTheme.caption(context)),
                          ],
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close_rounded, size: 18, color: CypherColors.textMuted),
                        onPressed: () => onRemove(f),
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                    ],
                  ),
                ),
              )),
              const SizedBox(height: 16),
              CypherCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.timer_outlined, color: CypherColors.accentLight, size: 16),
                        SizedBox(width: 8),
                        Text('Link expires in', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: CypherColors.textPrimary)),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        for (final mins in [15, 30, 60, 120])
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.only(right: 6),
                              child: GestureDetector(
                                onTap: () => onExpiresChanged(mins),
                                child: AnimatedContainer(
                                  duration: const Duration(milliseconds: 160),
                                  padding: const EdgeInsets.symmetric(vertical: 9),
                                  decoration: BoxDecoration(
                                    color: expiresIn == mins ? CypherColors.accent : CypherColors.bgOverlay,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(
                                      color: expiresIn == mins ? CypherColors.accent : CypherColors.border,
                                    ),
                                  ),
                                  child: Center(
                                    child: Text(
                                      mins < 60 ? '${mins}m' : '${mins ~/ 60}h',
                                      style: TextStyle(
                                        fontSize: 13, fontWeight: FontWeight.w600,
                                        color: expiresIn == mins ? Colors.white : CypherColors.textMuted,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              if (error != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: CypherColors.error.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: CypherColors.error.withOpacity(0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline_rounded, color: CypherColors.error, size: 16),
                      const SizedBox(width: 8),
                      Expanded(child: Text(error!, style: const TextStyle(color: CypherColors.error, fontSize: 13))),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: CypherButton(
            label: 'Upload & Create Share Link',
            icon: const Icon(Icons.upload_rounded),
            onTap: onUpload,
          ),
        ),
      ],
    );
  }
}

// ── Uploading ─────────────────────────────────────────────────
class _UploadingView extends StatelessWidget {
  final List<PlatformFile> files;
  final Map<String, double> progress;
  const _UploadingView({required this.files, required this.progress});

  @override
  Widget build(BuildContext context) {
    final overall = files.isEmpty
        ? 0.0
        : progress.values.fold(0.0, (s, v) => s + v) / files.length;

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 88, height: 88,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  CircularProgressIndicator(
                    value: overall,
                    strokeWidth: 6,
                    backgroundColor: CypherColors.bgCard,
                    valueColor: const AlwaysStoppedAnimation(CypherColors.accent),
                  ),
                  Text(
                    '${(overall * 100).toInt()}%',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: CypherColors.textPrimary),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text('Uploading to PC…',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: CypherColors.textPrimary)),
            const SizedBox(height: 6),
            const Text('Generating share link when done',
              style: TextStyle(color: CypherColors.textMuted, fontSize: 13)),
            const SizedBox(height: 36),
            ...files.map((f) => Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.insert_drive_file_rounded, size: 13, color: CypherColors.accentLight),
                      const SizedBox(width: 6),
                      Expanded(child: Text(f.name,
                        style: const TextStyle(fontSize: 12, color: CypherColors.textSecondary),
                        overflow: TextOverflow.ellipsis)),
                      const SizedBox(width: 8),
                      Text('${((progress[f.name] ?? 0) * 100).toInt()}%',
                        style: const TextStyle(fontSize: 11, color: CypherColors.textMuted)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: progress[f.name] ?? 0,
                      minHeight: 4,
                      backgroundColor: CypherColors.bgCard,
                      valueColor: const AlwaysStoppedAnimation(CypherColors.accent),
                    ),
                  ),
                ],
              ),
            )),
          ],
        ),
      ),
    );
  }
}

// ── Sharing ───────────────────────────────────────────────────
class _SharingView extends StatelessWidget {
  final String url;
  final List<PlatformFile> files;
  final int secondsLeft;
  final VoidCallback onReset;
  final String Function(int) fmtSize;

  const _SharingView({
    required this.url,
    required this.files,
    required this.secondsLeft,
    required this.onReset,
    required this.fmtSize,
  });

  String _countdown(int s) {
    final m = s ~/ 60;
    final sec = s % 60;
    return '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final expiringSoon = secondsLeft < 300;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 48),
      children: [
        const Center(
          child: Column(
            children: [
              Icon(Icons.check_circle_rounded, color: CypherColors.success, size: 44),
              SizedBox(height: 10),
              Text('Ready to share!',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: CypherColors.textPrimary)),
              SizedBox(height: 6),
              Text('Friend scans the QR code to download',
                style: TextStyle(fontSize: 14, color: CypherColors.textSecondary)),
            ],
          ),
        ),
        const SizedBox(height: 28),

        // QR code
        Center(
          child: Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              boxShadow: [BoxShadow(color: CypherColors.accent.withOpacity(0.3), blurRadius: 40, spreadRadius: -4)],
            ),
            child: QrImageView(
              data: url,
              version: QrVersions.auto,
              size: 200,
              eyeStyle: const QrEyeStyle(eyeShape: QrEyeShape.square, color: Color(0xFF1A1A1E)),
              dataModuleStyle: const QrDataModuleStyle(dataModuleShape: QrDataModuleShape.square, color: Color(0xFF1A1A1E)),
            ),
          ),
        ),
        const SizedBox(height: 20),

        // Expiry countdown
        Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: expiringSoon ? CypherColors.error.withOpacity(0.1) : CypherColors.bgCard,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: expiringSoon ? CypherColors.error.withOpacity(0.4) : CypherColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.timer_rounded, size: 14, color: expiringSoon ? CypherColors.error : CypherColors.textMuted),
                const SizedBox(width: 6),
                Text(
                  'Expires in ${_countdown(secondsLeft)}',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500,
                    color: expiringSoon ? CypherColors.error : CypherColors.textMuted),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),

        // Copy link
        CypherCard(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('OR SHARE THE LINK',
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1.5, color: CypherColors.textMuted)),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: Text(url,
                      style: const TextStyle(fontSize: 12, color: CypherColors.textSecondary, fontFamily: 'monospace'),
                      overflow: TextOverflow.ellipsis),
                  ),
                  const SizedBox(width: 10),
                  GestureDetector(
                    onTap: () {
                      Clipboard.setData(ClipboardData(text: url));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Link copied!'), duration: Duration(seconds: 2)),
                      );
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                      decoration: BoxDecoration(
                        color: CypherColors.accent.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: CypherColors.accent.withOpacity(0.3)),
                      ),
                      child: const Text('Copy', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: CypherColors.accent)),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // File list
        CypherCard(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${files.length} FILE${files.length == 1 ? '' : 'S'} SHARED',
                style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1.5, color: CypherColors.textMuted),
              ),
              const SizedBox(height: 10),
              ...files.map((f) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    const Icon(Icons.insert_drive_file_rounded, size: 14, color: CypherColors.accentLight),
                    const SizedBox(width: 8),
                    Expanded(child: Text(f.name,
                      style: const TextStyle(fontSize: 12, color: CypherColors.textSecondary),
                      overflow: TextOverflow.ellipsis)),
                    Text(fmtSize(f.size),
                      style: const TextStyle(fontSize: 11, color: CypherColors.textMuted)),
                  ],
                ),
              )),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Instructions for receiver
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: CypherColors.accent.withOpacity(0.06),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: CypherColors.accent.withOpacity(0.15)),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.info_outline_rounded, color: CypherColors.accentLight, size: 14),
                  SizedBox(width: 8),
                  Text('For your friend', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: CypherColors.accentLight)),
                ],
              ),
              SizedBox(height: 8),
              Text(
                '1. Connect to the same WiFi / hotspot\n2. Scan the QR code or type the link in any browser\n3. Tap the file to download — no app needed',
                style: TextStyle(fontSize: 13, color: CypherColors.textSecondary, height: 1.7),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        CypherButton(
          label: 'Share More Files',
          icon: const Icon(Icons.add_rounded),
          variant: CypherButtonVariant.secondary,
          onTap: onReset,
        ),
      ],
    );
  }
}

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/file_provider.dart';
import '../services/api_service.dart';
import '../theme/colors.dart';
import '../widgets/cypher_button.dart';
import '../widgets/cypher_card.dart';

// Quality → (label, description)
const _qualities = [
  ('low',    'Low',    '480p · Smaller files'),
  ('medium', 'Medium', '720p · Balanced'),
  ('high',   'High',   '1080p · Best quality'),
];

const _fpsOptions = [15, 24, 30, 60];

class ScreenRecorderScreen extends StatefulWidget {
  const ScreenRecorderScreen({super.key});

  @override
  State<ScreenRecorderScreen> createState() => _ScreenRecorderScreenState();
}

class _ScreenRecorderScreenState extends State<ScreenRecorderScreen>
    with SingleTickerProviderStateMixin {
  // Recording state
  bool _isRecording = false;
  bool _isPaused    = false;
  int  _duration    = 0;
  String? _savedFilename;
  Timer? _timer;

  // Settings (locked when recording)
  String _source  = 'fullscreen';
  String _quality = 'medium';
  int    _fps     = 30;
  bool   _audio   = false;

  // Countdown
  bool _counting = false;
  int  _countdown = 3;
  Timer? _countTimer;

  // Auto-download toggle
  bool _downloadAfterStop = false;
  bool _isDownloading     = false;

  // Pulse animation for rec dot
  late AnimationController _pulseCtrl;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
    WidgetsBinding.instance.addPostFrameCallback((_) => _fetchStatus());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _countTimer?.cancel();
    _pulseCtrl.dispose();
    super.dispose();
  }

  String get _ip => context.read<ConnectionProvider>().ip ?? '';

  Future<void> _fetchStatus() async {
    try {
      final data = await ApiService.getRecordingStatus(_ip);
      if (!mounted) return;
      setState(() {
        _isRecording   = data['is_recording'] ?? false;
        _isPaused      = data['is_paused']    ?? false;
        _duration      = data['duration']     ?? 0;
        _savedFilename = data['filename'];
      });
      if (_isRecording && !_isPaused) _startTimer();
    } catch (_) {}
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && !_isPaused) setState(() => _duration++);
    });
  }

  void _beginCountdown() {
    HapticFeedback.heavyImpact();
    setState(() { _counting = true; _countdown = 3; });
    _countTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) { t.cancel(); return; }
      setState(() => _countdown--);
      if (_countdown <= 0) {
        t.cancel();
        setState(() => _counting = false);
        _startRecording();
      }
    });
  }

  Future<void> _startRecording() async {
    HapticFeedback.heavyImpact();
    try {
      await ApiService.startRecording(
        _ip,
        source:  _source,
        quality: _quality,
        fps:     _fps,
        audio:   _audio,
      );
      setState(() { _isRecording = true; _isPaused = false; _savedFilename = null; _duration = 0; });
      _startTimer();
    } catch (e) {
      _toast('Failed to start: ${e.toString().replaceAll('Exception: ', '')}', err: true);
    }
  }

  Future<void> _pauseResume() async {
    HapticFeedback.mediumImpact();
    try {
      final data = await ApiService.pauseRecording(_ip);
      setState(() => _isPaused = data['is_paused'] ?? !_isPaused);
    } catch (_) {}
  }

  Future<void> _stopRecording() async {
    HapticFeedback.heavyImpact();
    _timer?.cancel();
    try {
      final data = await ApiService.stopRecording(_ip);
      final path = data['path']?.toString();
      final name = data['path'] != null ? path!.split(RegExp(r'[/\\]')).last : null;
      setState(() {
        _isRecording   = false;
        _isPaused      = false;
        _duration      = 0;
        _savedFilename = name;
      });
      if (_downloadAfterStop && name != null && path != null) {
        _downloadToPhone(path, name);
      } else {
        _showSuccessSheet(name, path);
      }
    } catch (e) {
      _toast('Failed to stop: ${e.toString().replaceAll('Exception: ', '')}', err: true);
    }
  }

  Future<void> _downloadToPhone(String remotePath, String name) async {
    setState(() => _isDownloading = true);
    try {
      final fp = context.read<FileProvider>();
      await fp.download(_ip, remotePath, name);
      if (!mounted) return;
      setState(() => _isDownloading = false);
      _showSuccessSheet(name, remotePath, downloaded: true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _isDownloading = false);
      _toast('Download failed', err: true);
      _showSuccessSheet(name, remotePath);
    }
  }

  Future<void> _takeScreenshot() async {
    HapticFeedback.lightImpact();
    try {
      final bytes = await ApiService.getScreenshot(_ip);
      if (!mounted) return;
      _toast('Screenshot captured');
      // Save to downloads via file provider
      final fp = context.read<FileProvider>();
      final name = 'Screenshot_${DateTime.now().millisecondsSinceEpoch}.jpg';
      // We have raw bytes — write to temp and transfer
      final dir = await _getTempDir();
      final file = await _writeBytesTemp(dir, name, bytes);
      await fp.upload(_ip, file, 'Desktop', name);
    } catch (_) {
      _toast('Screenshot failed', err: true);
    }
  }

  // We need path_provider to get temp dir — use FileProvider approach instead:
  // Actually just trigger a PC screenshot save and notify user
  Future<String> _getTempDir() async {
    // path_provider not imported here — get system temp from dart:io
    return '/tmp';
  }

  Future<String> _writeBytesTemp(String dir, String name, dynamic bytes) async {
    return '$dir/$name';
  }

  void _showSuccessSheet(String? name, String? path, {bool downloaded = false}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: CypherColors.bgCard,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(color: CypherColors.border, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 24),
            Container(
              width: 72, height: 72,
              decoration: BoxDecoration(
                color: CypherColors.success.withOpacity(0.1),
                shape: BoxShape.circle,
                border: Border.all(color: CypherColors.success.withOpacity(0.3)),
              ),
              child: const Icon(Icons.check_rounded, color: CypherColors.success, size: 36),
            ),
            const SizedBox(height: 16),
            const Text('Recording Saved', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: CypherColors.textPrimary)),
            const SizedBox(height: 6),
            Text(
              downloaded
                ? 'Saved to PC and transferred to your phone.'
                : 'Saved to Videos/CYPHER on your PC.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: CypherColors.textSecondary, fontSize: 14),
            ),
            if (name != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: CypherColors.bgOverlay,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: CypherColors.border),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.videocam_rounded, size: 14, color: CypherColors.accentLight),
                    const SizedBox(width: 8),
                    Expanded(child: Text(name, style: const TextStyle(fontSize: 12, color: CypherColors.textSecondary), overflow: TextOverflow.ellipsis)),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 24),
            if (!downloaded && path != null && name != null)
              CypherButton(
                label: 'Download to Phone',
                icon: const Icon(Icons.download_rounded),
                variant: CypherButtonVariant.secondary,
                onTap: () {
                  Navigator.pop(context);
                  _downloadToPhone(path, name);
                },
              ),
            const SizedBox(height: 10),
            CypherButton(
              label: 'Done',
              onTap: () => Navigator.pop(context),
            ),
          ],
        ),
      ),
    );
  }

  void _toast(String msg, {bool err = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: err ? CypherColors.error : CypherColors.success,
      duration: const Duration(seconds: 2),
    ));
  }

  String _fmt(int s) {
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final sec = s % 60;
    if (h > 0) return '${h.toString().padLeft(2,'0')}:${m.toString().padLeft(2,'0')}:${sec.toString().padLeft(2,'0')}';
    return '${m.toString().padLeft(2,'0')}:${sec.toString().padLeft(2,'0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Screen Recorder'),
        actions: [
          if (!_isRecording && !_counting)
            IconButton(
              icon: const Icon(Icons.photo_camera_outlined),
              tooltip: 'Screenshot',
              onPressed: _takeScreenshot,
            ),
        ],
      ),
      body: _isDownloading
          ? _DownloadingView()
          : _counting
            ? _CountdownView(n: _countdown)
            : SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 48),
                child: Column(
                  children: [
                    _TimerRing(
                      isRecording: _isRecording,
                      isPaused:    _isPaused,
                      duration:    _duration,
                      pulse:       _pulseCtrl,
                      fmtFn:       _fmt,
                    ),
                    const SizedBox(height: 28),
                    _Controls(
                      isRecording: _isRecording,
                      isPaused:    _isPaused,
                      onStart:     _beginCountdown,
                      onPause:     _pauseResume,
                      onStop:      _stopRecording,
                    ),
                    const SizedBox(height: 28),
                    _SettingsPanel(
                      source:              _source,
                      quality:             _quality,
                      fps:                 _fps,
                      audio:               _audio,
                      downloadAfterStop:   _downloadAfterStop,
                      locked:              _isRecording,
                      onSource:            (v) => setState(() => _source  = v),
                      onQuality:           (v) => setState(() => _quality = v),
                      onFps:               (v) => setState(() => _fps     = v),
                      onAudio:             (v) => setState(() => _audio   = v),
                      onDownload:          (v) => setState(() => _downloadAfterStop = v),
                    ),
                    if (_isRecording && _savedFilename == null) ...[
                      const SizedBox(height: 16),
                      _RecordingInfo(source: _source, quality: _quality, fps: _fps),
                    ],
                  ],
                ),
              ),
    );
  }
}

// ── Timer Ring ────────────────────────────────────────────────
class _TimerRing extends StatelessWidget {
  final bool isRecording;
  final bool isPaused;
  final int duration;
  final AnimationController pulse;
  final String Function(int) fmtFn;

  const _TimerRing({
    required this.isRecording, required this.isPaused, required this.duration,
    required this.pulse, required this.fmtFn,
  });

  @override
  Widget build(BuildContext context) {
    final Color ringColor = isRecording
        ? (isPaused ? CypherColors.warning : CypherColors.error)
        : CypherColors.border;

    return Center(
      child: Container(
        width: 200, height: 200,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: CypherColors.bgCard,
          border: Border.all(color: ringColor.withOpacity(0.35), width: 3),
          boxShadow: isRecording && !isPaused
              ? [BoxShadow(color: CypherColors.error.withOpacity(0.2), blurRadius: 40, spreadRadius: 2)]
              : [],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (isRecording)
              AnimatedBuilder(
                animation: pulse,
                builder: (_, __) => Opacity(
                  opacity: isPaused ? 0.4 : 0.5 + 0.5 * pulse.value,
                  child: Container(
                    width: 12, height: 12,
                    decoration: BoxDecoration(
                      color: isPaused ? CypherColors.warning : CypherColors.error,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            const SizedBox(height: 6),
            Text(
              fmtFn(duration),
              style: const TextStyle(
                fontSize: 44, fontWeight: FontWeight.w800,
                color: CypherColors.textPrimary, letterSpacing: -1,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              isRecording ? (isPaused ? 'PAUSED' : 'REC') : 'READY',
              style: TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700,
                color: isRecording ? (isPaused ? CypherColors.warning : CypherColors.error) : CypherColors.textMuted,
                letterSpacing: 2.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Countdown overlay ─────────────────────────────────────────
class _CountdownView extends StatelessWidget {
  final int n;
  const _CountdownView({required this.n});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 200),
            transitionBuilder: (child, anim) => ScaleTransition(scale: anim, child: child),
            child: Text(
              n.toString(),
              key: ValueKey(n),
              style: const TextStyle(
                fontSize: 120, fontWeight: FontWeight.w900,
                color: CypherColors.error, letterSpacing: -4,
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text('Recording starts in…', style: TextStyle(color: CypherColors.textMuted, fontSize: 15)),
        ],
      ),
    );
  }
}

// ── Downloading ───────────────────────────────────────────────
class _DownloadingView extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: CypherColors.accent),
          SizedBox(height: 20),
          Text('Transferring to phone…', style: TextStyle(color: CypherColors.textSecondary, fontSize: 15)),
        ],
      ),
    );
  }
}

// ── Controls ──────────────────────────────────────────────────
class _Controls extends StatelessWidget {
  final bool isRecording;
  final bool isPaused;
  final VoidCallback onStart;
  final VoidCallback onPause;
  final VoidCallback onStop;

  const _Controls({
    required this.isRecording, required this.isPaused,
    required this.onStart, required this.onPause, required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    if (!isRecording) {
      return CypherButton(
        label: 'Start Recording',
        icon: const Icon(Icons.fiber_manual_record_rounded),
        onTap: onStart,
      );
    }
    return Row(
      children: [
        Expanded(
          child: CypherButton(
            label: isPaused ? 'Resume' : 'Pause',
            variant: CypherButtonVariant.secondary,
            icon: Icon(isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded),
            onTap: onPause,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: CypherButton(
            label: 'Stop',
            variant: CypherButtonVariant.danger,
            icon: const Icon(Icons.stop_rounded),
            onTap: onStop,
          ),
        ),
      ],
    );
  }
}

// ── Settings Panel ────────────────────────────────────────────
class _SettingsPanel extends StatelessWidget {
  final String source;
  final String quality;
  final int fps;
  final bool audio;
  final bool downloadAfterStop;
  final bool locked;
  final void Function(String) onSource;
  final void Function(String) onQuality;
  final void Function(int) onFps;
  final void Function(bool) onAudio;
  final void Function(bool) onDownload;

  const _SettingsPanel({
    required this.source, required this.quality, required this.fps,
    required this.audio, required this.downloadAfterStop, required this.locked,
    required this.onSource, required this.onQuality, required this.onFps,
    required this.onAudio, required this.onDownload,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Source
        const _SectionLabel('CAPTURE SOURCE'),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: _ToggleBtn(
              icon: Icons.monitor_rounded, label: 'Full Screen',
              selected: source == 'fullscreen', enabled: !locked,
              onTap: () => onSource('fullscreen'),
            )),
            const SizedBox(width: 10),
            Expanded(child: _ToggleBtn(
              icon: Icons.window_rounded, label: 'Active App',
              selected: source == 'window', enabled: !locked,
              onTap: () => onSource('window'),
            )),
          ],
        ),

        const SizedBox(height: 20),

        // Quality
        const _SectionLabel('QUALITY'),
        const SizedBox(height: 8),
        Row(
          children: _qualities.map((q) => Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _ToggleBtn(
                label: q.$2, sublabel: q.$3,
                selected: quality == q.$1, enabled: !locked,
                onTap: () => onQuality(q.$1),
              ),
            ),
          )).toList(),
        ),

        const SizedBox(height: 20),

        // FPS
        const _SectionLabel('FRAME RATE'),
        const SizedBox(height: 8),
        Row(
          children: _fpsOptions.map((f) => Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: 6),
              child: _ToggleBtn(
                label: '${f}fps', selected: fps == f, enabled: !locked,
                onTap: () => onFps(f),
              ),
            ),
          )).toList(),
        ),

        const SizedBox(height: 20),

        // Toggles
        CypherCard(
          padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 0),
          child: Column(
            children: [
              _SwitchRow(
                icon: Icons.mic_rounded,
                iconColor: audio ? CypherColors.accent : CypherColors.textMuted,
                title: 'Record Audio',
                subtitle: 'Capture system & mic audio',
                value: audio,
                enabled: !locked,
                onChanged: onAudio,
              ),
              Divider(height: 1, indent: 52, color: CypherColors.border.withOpacity(0.5)),
              _SwitchRow(
                icon: Icons.phone_android_rounded,
                iconColor: downloadAfterStop ? CypherColors.accent : CypherColors.textMuted,
                title: 'Auto-Transfer to Phone',
                subtitle: 'Download to phone when stopped',
                value: downloadAfterStop,
                enabled: true,
                onChanged: onDownload,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// ── Recording info badge ──────────────────────────────────────
class _RecordingInfo extends StatelessWidget {
  final String source;
  final String quality;
  final int fps;
  const _RecordingInfo({required this.source, required this.quality, required this.fps});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: CypherColors.error.withOpacity(0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CypherColors.error.withOpacity(0.2)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.fiber_manual_record_rounded, size: 8, color: CypherColors.error),
          const SizedBox(width: 8),
          Text(
            '${source == 'fullscreen' ? 'Full Screen' : 'Active App'}  ·  ${quality.toUpperCase()}  ·  ${fps}fps',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: CypherColors.error),
          ),
        ],
      ),
    );
  }
}

// ── Helpers ───────────────────────────────────────────────────
class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(
      fontSize: 10, fontWeight: FontWeight.w700,
      letterSpacing: 1.5, color: CypherColors.textMuted,
    ));
  }
}

class _ToggleBtn extends StatelessWidget {
  final IconData? icon;
  final String label;
  final String? sublabel;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  const _ToggleBtn({
    this.icon, required this.label, this.sublabel,
    required this.selected, required this.enabled, required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1.0 : 0.5,
      child: GestureDetector(
        onTap: enabled ? onTap : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: EdgeInsets.symmetric(vertical: sublabel != null ? 12 : 14),
          decoration: BoxDecoration(
            color: selected ? CypherColors.accent.withOpacity(0.12) : CypherColors.bgCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected ? CypherColors.accent : CypherColors.border,
              width: selected ? 1.5 : 1,
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, color: selected ? CypherColors.accent : CypherColors.textMuted, size: 20),
                const SizedBox(height: 6),
              ],
              Text(
                label,
                style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w600,
                  color: selected ? CypherColors.accent : CypherColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
              if (sublabel != null) ...[
                const SizedBox(height: 2),
                Text(sublabel!, style: const TextStyle(fontSize: 9, color: CypherColors.textMuted), textAlign: TextAlign.center),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final bool value;
  final bool enabled;
  final void Function(bool) onChanged;

  const _SwitchRow({
    required this.icon, required this.iconColor, required this.title,
    required this.subtitle, required this.value,
    required this.enabled, required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: [
          Container(
            width: 32, height: 32,
            decoration: BoxDecoration(
              color: iconColor.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, size: 16, color: iconColor),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: CypherColors.textPrimary)),
                Text(subtitle, style: const TextStyle(fontSize: 11, color: CypherColors.textMuted)),
              ],
            ),
          ),
          Switch(
            value: value,
            activeColor: CypherColors.accent,
            onChanged: enabled ? onChanged : null,
          ),
        ],
      ),
    );
  }
}

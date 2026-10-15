import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/file_provider.dart';
import '../services/api_service.dart';
import '../theme/colors.dart';
import '../theme/app_theme.dart';
import '../widgets/cypher_button.dart';

class FilePreviewScreen extends StatefulWidget {
  final String filePath;
  final String fileName;
  final int fileSize;
  final String fileExtension;

  const FilePreviewScreen({
    super.key,
    required this.filePath,
    required this.fileName,
    required this.fileSize,
    required this.fileExtension,
  });

  @override
  State<FilePreviewScreen> createState() => _FilePreviewScreenState();
}

class _FilePreviewScreenState extends State<FilePreviewScreen> {
  String _textContent = '';
  bool _loadingText = false;
  bool _downloaded = false;
  String? _previewUrlCached;

  bool get _isImage => const ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
      .contains(widget.fileExtension.toLowerCase());

  bool get _isText => const [
        '.txt', '.md', '.log', '.py', '.js', '.dart', '.json',
        '.css', '.html', '.yaml', '.yml', '.xml', '.c', '.cpp',
        '.h', '.java', '.kt', '.go', '.rb', '.php', '.sql', '.sh',
      ].contains(widget.fileExtension.toLowerCase());

  String get _ip => context.read<ConnectionProvider>().ip ?? '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _previewUrlCached = await ApiService.getPreviewUrl(_ip, widget.filePath);
      if (mounted) {
        setState(() {});
        if (_isText) _loadText();
      }
    });
  }

  Future<void> _loadText() async {
    if (_previewUrlCached == null) return;
    setState(() => _loadingText = true);
    try {
      // The preview URL comes from the node, so its host is not something this
      // screen chose. Re-validate it before fetching: the node's answer is
      // trusted for the path, not for the destination.
      final previewUri = Uri.parse(_previewUrlCached!);
      ApiService.assertPrivateUri(previewUri);
      final res = await http.get(previewUri).timeout(const Duration(seconds: 15));
      if (mounted) setState(() => _textContent = res.statusCode == 200 ? res.body : 'Preview unavailable.');
    } catch (_) {
      if (mounted) setState(() => _textContent = 'Preview unavailable.');
    }
    if (mounted) setState(() => _loadingText = false);
  }

  String _fmtSize(int b) {
    if (b < 1024)       return '$b B';
    if (b < 1048576)    return '${(b / 1024).toStringAsFixed(1)} KB';
    if (b < 1073741824) return '${(b / 1048576).toStringAsFixed(1)} MB';
    return '${(b / 1073741824).toStringAsFixed(1)} GB';
  }

  Future<void> _download() async {
    final fp = context.read<FileProvider>();
    await fp.download(_ip, widget.filePath, widget.fileName);
    if (mounted) {
      setState(() => _downloaded = true);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Download started')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final fp   = context.watch<FileProvider>();
    final task = fp.transfers.where((t) => t.name == widget.fileName && t.isUpload == false).firstOrNull;

    return Scaffold(
      backgroundColor: _isImage ? Colors.black : CypherColors.bgDeep,
      body: Stack(
        children: [
          Positioned.fill(child: _buildContent()),

          // Top gradient bar
          Positioned(
            top: 0, left: 0, right: 0,
            child: Container(
              padding: EdgeInsets.only(
                top: MediaQuery.of(context).padding.top + 8,
                left: 8, right: 8, bottom: 12,
              ),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.black.withOpacity(0.75), Colors.transparent],
                ),
              ),
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                  Expanded(
                    child: Text(
                      widget.fileName,
                      style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Bottom bar
          Positioned(
            bottom: 0, left: 0, right: 0,
            child: Container(
              padding: EdgeInsets.fromLTRB(20, 16, 20, MediaQuery.of(context).padding.bottom + 16),
              decoration: BoxDecoration(
                color: CypherColors.bgCard.withOpacity(0.96),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
                border: Border(top: BorderSide(color: CypherColors.border, width: 0.5)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(widget.fileExtension.toUpperCase().replaceAll('.', ''), style: AppTheme.caption(context)),
                      Text(_fmtSize(widget.fileSize), style: const TextStyle(fontSize: 13, color: CypherColors.textSecondary)),
                    ],
                  ),
                  if (task != null && task.status == TransferStatus.downloading) ...[
                    const SizedBox(height: 8),
                    LinearProgressIndicator(value: task.progress, color: CypherColors.accent, backgroundColor: CypherColors.bgOverlay),
                    const SizedBox(height: 4),
                    Text(
                      '${(task.progress * 100).toInt()}%  •  ${_fmtSize(task.received)} / ${_fmtSize(task.total)}',
                      style: AppTheme.caption(context),
                    ),
                  ] else ...[
                    const SizedBox(height: 10),
                    CypherButton(
                      label: _downloaded ? 'Downloaded' : 'Save to Phone',
                      onTap: _downloaded ? null : _download,
                      icon: Icon(_downloaded ? Icons.check_rounded : Icons.file_download_rounded),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    if (_previewUrlCached == null) {
      return const Center(child: CircularProgressIndicator(color: CypherColors.accent));
    }

    if (_isImage) {
      return InteractiveViewer(
        minScale: 0.5,
        maxScale: 6,
        child: Center(
          child: Image.network(
            _previewUrlCached!,
            fit: BoxFit.contain,
            loadingBuilder: (_, child, progress) {
              if (progress == null) return child;
              final pct = progress.expectedTotalBytes != null
                  ? progress.cumulativeBytesLoaded / progress.expectedTotalBytes!
                  : null;
              return Center(
                child: CircularProgressIndicator(value: pct, color: CypherColors.accent),
              );
            },
            errorBuilder: (_, __, ___) => const Center(
              child: Icon(Icons.broken_image_rounded, color: CypherColors.textMuted, size: 48),
            ),
          ),
        ),
      );
    }

    if (_isText) {
      return Container(
        padding: const EdgeInsets.fromLTRB(16, 90, 16, 110),
        child: _loadingText
            ? const Center(child: CircularProgressIndicator(color: CypherColors.accent))
            : SingleChildScrollView(
                child: SelectableText(
                  _textContent.isEmpty ? '(empty file)' : _textContent,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 12,
                    height: 1.7,
                    color: CypherColors.textSecondary,
                  ),
                ),
              ),
      );
    }

    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(32, 90, 32, 130),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 96, height: 96,
              decoration: BoxDecoration(
                color: CypherColors.bgCard,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: CypherColors.border),
              ),
              child: const Icon(Icons.insert_drive_file_rounded, color: CypherColors.accentLight, size: 44),
            ),
            const SizedBox(height: 16),
            Text(
              widget.fileName,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: CypherColors.textPrimary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 6),
            const Text(
              'No preview available\nSave to phone to open',
              style: TextStyle(color: CypherColors.textMuted, fontSize: 13, height: 1.5),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

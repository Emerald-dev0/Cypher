import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/file_provider.dart';
import '../services/api_service.dart';
import '../theme/colors.dart';
import '../theme/app_theme.dart';
import '../widgets/cypher_button.dart';
import '../widgets/cypher_card.dart';

class SendToPCScreen extends StatefulWidget {
  final List<String>? sharedFiles;
  const SendToPCScreen({super.key, this.sharedFiles});

  @override
  State<SendToPCScreen> createState() => _SendToPCScreenState();
}

class _SendToPCScreenState extends State<SendToPCScreen> {
  List<String> _selectedPaths = [];
  String _destination = 'Desktop';
  String _destinationPath = ''; // Full path
  Map<String, String> _destinations = {}; // name -> path
  List<Map<String, dynamic>> _subfolders = [];
  String _currentBrowsePath = '';
  String _currentDisplayName = '';
  bool _loadingFolders = false;
  bool _browsingFolders = false;
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    if (widget.sharedFiles != null && widget.sharedFiles!.isNotEmpty) {
      _selectedPaths = List<String>.from(widget.sharedFiles!);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFolders());
  }

  String get _ip => context.read<ConnectionProvider>().ip ?? '';

  Future<void> _loadFolders() async {
    setState(() => _loadingFolders = true);
    try {
      final dests = await ApiService.getUploadDestinations(_ip);
      Map<String, String> map = {};
      for (var dest in dests) {
        map[dest['name'] as String] = dest['path'] as String;
      }
      if (map.isNotEmpty) {
        setState(() {
          _destinations = map;
          _destination = map.keys.first;
          _destinationPath = map[_destination] ?? '';
        });
      }
    } catch (_) {
      setState(() {
        _destinations = {'Desktop': 'Desktop', 'Documents': 'Documents', 'Downloads': 'Downloads'};
        _destination = 'Desktop';
      });
    }
    if (mounted) setState(() => _loadingFolders = false);
  }

  Future<void> _browseFolders(String? path) async {
    setState(() => _browsingFolders = true);
    try {
      final result = await ApiService.browseFolders(_ip, path: path);
      if (result['success'] == true) {
        setState(() {
          _subfolders = List<Map<String, dynamic>>.from(result['folders'] ?? []);
          _currentBrowsePath = result['current_path'] ?? '';
          _currentDisplayName = result['display_name'] ?? 'Select Folder';
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _browsingFolders = false);
  }

  void _selectFolder(String folderPath, String folderName) {
    setState(() {
      _destination = folderName;
      _destinationPath = folderPath;
      _subfolders = [];
      _currentBrowsePath = '';
    });
  }

  Future<void> _pickFiles() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true);
    if (result != null && mounted) {
      setState(() {
        _selectedPaths.addAll(
          result.paths.whereType<String>().where((p) => !_selectedPaths.contains(p)),
        );
      });
    }
  }

  void _removeFile(String path) => setState(() => _selectedPaths.remove(path));

  Future<void> _upload() async {
    if (_selectedPaths.isEmpty) return;
    setState(() => _uploading = true);

    final fp = context.read<FileProvider>();
    // Use full path if available, otherwise use folder name
    final dest = _destinationPath.isNotEmpty ? _destinationPath : _destination;

    for (final path in _selectedPaths) {
      final name = path.split(RegExp(r'[/\\]')).last;
      await fp.upload(_ip, path, dest, name);
    }

    if (mounted) {
      setState(() => _uploading = false);
      Navigator.pushReplacementNamed(context, '/active_tasks');
    }
  }

  String _fmtSize(int bytes) {
    if (bytes < 1024)       return '$bytes B';
    if (bytes < 1048576)    return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1073741824) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
  }

  int _totalBytes() {
    int total = 0;
    for (final path in _selectedPaths) {
      try { total += File(path).lengthSync(); } catch (_) {}
    }
    return total;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Send to PC')),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // File list card
                  CypherCard(
                    padding: EdgeInsets.zero,
                    child: Column(
                      children: [
                        if (_selectedPaths.isEmpty)
                          const Padding(
                            padding: EdgeInsets.all(24),
                            child: Column(
                              children: [
                                Icon(Icons.upload_file_rounded, color: CypherColors.textMuted, size: 36),
                                SizedBox(height: 8),
                                Text('No files selected', style: TextStyle(color: CypherColors.textMuted)),
                              ],
                            ),
                          )
                        else
                          ...List.generate(_selectedPaths.length, (i) {
                            final path = _selectedPaths[i];
                            final name = path.split(RegExp(r'[/\\]')).last;
                            int size = 0;
                            try { size = File(path).lengthSync(); } catch (_) {}
                            return Column(
                              children: [
                                if (i > 0) const Divider(height: 1),
                                ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                                  leading: const Icon(Icons.insert_drive_file_rounded, color: CypherColors.accentLight, size: 22),
                                  title: Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: CypherColors.textPrimary), overflow: TextOverflow.ellipsis),
                                  subtitle: Text(_fmtSize(size), style: AppTheme.caption(context)),
                                  trailing: IconButton(
                                    icon: const Icon(Icons.close_rounded, color: CypherColors.textMuted, size: 18),
                                    onPressed: () => _removeFile(path),
                                    padding: EdgeInsets.zero,
                                    constraints: const BoxConstraints(),
                                  ),
                                ),
                              ],
                            );
                          }),
                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.add_rounded, color: CypherColors.accent, size: 22),
                          title: const Text('Add Files', style: TextStyle(color: CypherColors.accent, fontWeight: FontWeight.w500)),
                          onTap: _pickFiles,
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Destination
                  const Text('Destination folder', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: CypherColors.textSecondary)),
                  const SizedBox(height: 8),

                  // `_loadingFolders` and `_browsingFolders` were assigned in four
                  // places and read in none — the fetches gave no feedback at all.
                  if (_loadingFolders || _browsingFolders)
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: LinearProgressIndicator(minHeight: 2),
                    ),

                  // Show folder browser if browsing, otherwise show quick selections
                  if (_subfolders.isNotEmpty)
                    CypherCard(
                      padding: EdgeInsets.zero,
                      child: Column(
                        children: [
                          // Header with back button
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: CypherColors.bgOverlay,
                              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                            ),
                            child: Row(
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.arrow_back_rounded, color: CypherColors.accent),
                                  onPressed: () { HapticFeedback.selectionClick(); _browseFolders(null); },
                                  padding: EdgeInsets.zero,
                                  constraints: const BoxConstraints(),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _currentDisplayName,
                                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: CypherColors.textPrimary),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                ElevatedButton.icon(
                                  onPressed: () => _selectFolder(_currentBrowsePath, _currentDisplayName),
                                  icon: const Icon(Icons.check_rounded, size: 16),
                                  label: const Text('Select', style: TextStyle(fontSize: 12)),
                                  style: ElevatedButton.styleFrom(
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                    backgroundColor: CypherColors.success,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          // Folders list
                          ..._subfolders.map((folder) => ListTile(
                            leading: const Icon(Icons.folder_rounded, color: CypherColors.accent, size: 20),
                            title: Text(folder['name'] ?? '', style: const TextStyle(fontSize: 13, color: CypherColors.textPrimary)),
                            trailing: const Icon(Icons.arrow_forward_ios_rounded, size: 12, color: CypherColors.textMuted),
                            onTap: () { HapticFeedback.selectionClick(); _browseFolders(folder['path']); },
                          )),
                        ],
                      ),
                    )
                  else
                    Column(
                      children: _destinations.entries.map((entry) {
                        final sel = _destination == entry.key;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Container(
                            decoration: BoxDecoration(
                              color: sel ? CypherColors.accent.withOpacity(0.1) : CypherColors.bgCard,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: sel ? CypherColors.accent : CypherColors.border),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: GestureDetector(
                                    onTap: () {
                                      HapticFeedback.selectionClick();
                                      setState(() {
                                        _destination = entry.key;
                                        _destinationPath = entry.value;
                                      });
                                    },
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                                      child: Row(
                                        children: [
                                          Container(
                                            width: 24, height: 24,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: sel ? CypherColors.accent : CypherColors.bgOverlay,
                                            ),
                                            child: Center(
                                              child: Container(
                                                width: 12, height: 12,
                                                decoration: BoxDecoration(
                                                  shape: BoxShape.circle,
                                                  color: sel ? Colors.white : Colors.transparent,
                                                ),
                                              ),
                                            ),
                                          ),
                                          const SizedBox(width: 12),
                                          Expanded(
                                            child: Text(
                                              entry.key,
                                              style: TextStyle(
                                                fontSize: 13,
                                                fontWeight: FontWeight.w500,
                                                color: CypherColors.textPrimary,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                                Padding(
                                  padding: const EdgeInsets.only(right: 8),
                                  child: TextButton.icon(
                                    icon: const Icon(Icons.folder_open_rounded, size: 16),
                                    label: const Text('Browse', style: TextStyle(fontSize: 11)),
                                    onPressed: () {
                                      HapticFeedback.selectionClick();
                                      _browseFolders(entry.value);
                                    },
                                    style: TextButton.styleFrom(
                                      foregroundColor: CypherColors.accent,
                                      padding: const EdgeInsets.symmetric(horizontal: 8),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }).toList(),
                    ),

                  const SizedBox(height: 16),
                ],
              ),
            ),
          ),

          // Bottom bar
          Container(
            padding: EdgeInsets.fromLTRB(16, 12, 16, MediaQuery.of(context).padding.bottom + 12),
            decoration: BoxDecoration(
              color: CypherColors.bgCard,
              border: Border(top: BorderSide(color: CypherColors.border, width: 0.5)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${_selectedPaths.length} file${_selectedPaths.length == 1 ? '' : 's'}',
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: CypherColors.textPrimary),
                      ),
                      if (_selectedPaths.isNotEmpty)
                        Text(_fmtSize(_totalBytes()), style: AppTheme.caption(context)),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 140,
                  child: CypherButton(
                    label: 'Upload',
                    icon: const Icon(Icons.cloud_upload_rounded),
                    onTap: (_selectedPaths.isEmpty || _uploading) ? null : _upload,
                    loading: _uploading,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

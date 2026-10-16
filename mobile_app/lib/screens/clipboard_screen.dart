import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/connection_provider.dart';
import '../providers/system_provider.dart';
import '../services/api_service.dart';
import '../services/clipboard_service.dart';
import '../theme/colors.dart';
import '../widgets/cypher_button.dart';
import '../widgets/cypher_card.dart';

class ClipboardScreen extends StatefulWidget {
  const ClipboardScreen({super.key});

  @override
  State<ClipboardScreen> createState() => _ClipboardScreenState();
}

class _ClipboardScreenState extends State<ClipboardScreen> {
  String _phoneContent = '';
  bool _sending = false;
  Timer? _refreshTimer;
  final _quickSendCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ip = context.read<ConnectionProvider>().ip ?? '';
      if (ip.isNotEmpty) {
        context.read<SystemProvider>().fetchClipboard(ip);
        _loadPhoneClipboard();
        _refreshTimer = Timer.periodic(const Duration(seconds: 6), (_) {
          if (mounted) context.read<SystemProvider>().fetchClipboard(ip);
        });
      }
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _quickSendCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadPhoneClipboard() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (mounted) setState(() => _phoneContent = data?.text ?? '');
  }

  Future<void> _copyToPhone(String text) async {
    if (text.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: text));
    await ClipboardService.addToHistory(text, source: 'pc');
    HapticFeedback.mediumImpact();
    _toast('Copied to phone');
    setState(() => _phoneContent = text);
  }

  Future<void> _sendToPC(String text) async {
    if (text.trim().isEmpty) return;
    final ip = context.read<ConnectionProvider>().ip ?? '';
    setState(() => _sending = true);
    try {
      await ApiService.setPcClipboard(ip, text.trim());
      await ClipboardService.addToHistory(text.trim(), source: 'phone');
      HapticFeedback.mediumImpact();
      _toast('Sent to PC');
      _quickSendCtrl.clear();
      FocusScope.of(context).unfocus();
      context.read<SystemProvider>().fetchClipboard(ip);
    } catch (_) {
      _toast("Couldn't send — check connection", err: true);
    }
    if (mounted) setState(() => _sending = false);
  }

  Future<void> _pasteOnPC() async {
    final ip = context.read<ConnectionProvider>().ip ?? '';
    try {
      await ApiService.pasteFromPhone(ip);
      _toast('Pasted on PC');
    } catch (_) {
      _toast('Paste failed', err: true);
    }
  }

  void _toast(String msg, {bool err = false}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: err ? CypherColors.error : CypherColors.accent,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final sp = context.watch<SystemProvider>();
    final pcText = sp.pcClipboard ?? '';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Clipboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.history_rounded),
            tooltip: 'History',
            onPressed: () => Navigator.pushNamed(context, '/clipboard-history'),
          ),
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh',
            onPressed: () {
              final ip = context.read<ConnectionProvider>().ip ?? '';
              context.read<SystemProvider>().fetchClipboard(ip);
              _loadPhoneClipboard();
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
        children: [
          // PC Clipboard
          const CypherSectionHeader(title: 'PC Clipboard'),
          const SizedBox(height: 8),
          CypherCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (pcText.isEmpty)
                  const Text('Nothing in PC clipboard', style: TextStyle(color: CypherColors.textMuted, fontSize: 14))
                else
                  Text(pcText, maxLines: 6, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, color: CypherColors.textPrimary, height: 1.5)),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: CypherButton(
                        label: 'Copy to Phone',
                        onTap: () => _copyToPhone(pcText),
                      ),
                    ),
                    if (pcText.startsWith('http')) ...[
                      const SizedBox(width: 8),
                      CypherButton(
                        label: 'Open Link',
                        variant: CypherButtonVariant.secondary,
                        onTap: () => ApiService.openLink(context.read<ConnectionProvider>().ip ?? '', pcText),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),

          // Phone Clipboard
          const SizedBox(height: 20),
          const CypherSectionHeader(title: 'Phone Clipboard'),
          const SizedBox(height: 8),
          CypherCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (_phoneContent.isEmpty)
                  const Text('Nothing in phone clipboard', style: TextStyle(color: CypherColors.textMuted, fontSize: 14))
                else
                  Text(_phoneContent, maxLines: 6, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, color: CypherColors.textPrimary, height: 1.5)),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: CypherButton(
                        label: 'Send to PC',
                        onTap: () => _sendToPC(_phoneContent),
                        loading: _sending,
                      ),
                    ),
                    const SizedBox(width: 8),
                    CypherButton(
                      label: 'Paste on PC',
                      variant: CypherButtonVariant.secondary,
                      onTap: _pasteOnPC,
                    ),
                  ],
                ),
              ],
            ),
          ),

          // Quick Send
          const SizedBox(height: 20),
          const CypherSectionHeader(title: 'Quick Send'),
          const SizedBox(height: 8),
          CypherCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _quickSendCtrl,
                  maxLines: 4,
                  minLines: 2,
                  decoration: const InputDecoration(
                    hintText: 'Type text or paste a link to send to PC...',
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    fillColor: Colors.transparent,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
                const SizedBox(height: 12),
                CypherButton(
                  label: 'Send to PC',
                  onTap: () => _sendToPC(_quickSendCtrl.text),
                  loading: _sending,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

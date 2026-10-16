import 'package:flutter/material.dart';
import '../theme/colors.dart';

class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('User Guide')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 60),
        children: const [
          _GuideSection(
            icon: Icons.wifi_rounded,
            title: 'Getting Connected',
            steps: [
              'Enable your phone\'s hotspot.',
              'Connect your PC to that hotspot.',
              'Launch CYPHER on your PC.',
              'Open the app and tap "Scan for PC" — it finds your PC automatically.',
              'Enter the 6-digit code shown on the PC app to pair.',
            ],
          ),
          _GuideSection(
            icon: Icons.content_paste_rounded,
            title: 'Clipboard Sync',
            steps: [
              'Copy text on your PC — it appears in the Clipboard tab instantly.',
              'Tap "Send to PC" to push text from your phone to the PC clipboard.',
              'Use "Paste on PC" to trigger Ctrl+V remotely.',
            ],
          ),
          _GuideSection(
            icon: Icons.folder_rounded,
            title: 'File Browser',
            steps: [
              'Browse your entire PC drive from your phone.',
              'Tap a file to preview images and text files inline.',
              'Long-press or tap ⋮ on a file to download it to your phone.',
              'Use "Send to PC" to upload files from your phone.',
            ],
          ),
          _GuideSection(
            icon: Icons.people_rounded,
            title: 'Guest Access',
            steps: [
              'Go to Guest Access from the home screen.',
              'Select which folders to share and set a time limit.',
              'Tap "Create" — show the URL to your guest.',
              'The session expires automatically when the timer runs out.',
            ],
          ),
          _GuideSection(
            icon: Icons.videocam_rounded,
            title: 'Screen Recording',
            steps: [
              'Tap Screen Recorder from the home screen.',
              'Choose "Full Screen" or "Window" source.',
              'Tap Start — recording begins on your PC.',
              'Tap Stop — the file is saved to your PC\'s Documents/CYPHER folder.',
            ],
          ),
          _GuideSection(
            icon: Icons.wifi_off_rounded,
            title: 'Troubleshooting',
            steps: [
              'Ensure your PC\'s network type is set to "Private" in Windows.',
              'Check that Windows Firewall isn\'t blocking port 5000.',
              'If auto-scan fails, enter the IP shown on the PC app manually.',
              'Hotspot IP priority is 192.168.43.x — reconnect the PC if it changes.',
            ],
          ),
        ],
      ),
    );
  }
}

class _GuideSection extends StatelessWidget {
  final IconData icon;
  final String title;
  final List<String> steps;
  const _GuideSection({required this.icon, required this.title, required this.steps});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 34, height: 34,
                decoration: BoxDecoration(color: CypherColors.accentDim, borderRadius: BorderRadius.circular(8)),
                child: Icon(icon, color: CypherColors.accentLight, size: 18),
              ),
              const SizedBox(width: 12),
              Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: CypherColors.textPrimary)),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: CypherColors.bgCard,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: CypherColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: List.generate(steps.length, (i) => Padding(
                padding: EdgeInsets.only(bottom: i < steps.length - 1 ? 8 : 0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 20, height: 20,
                      margin: const EdgeInsets.only(top: 1, right: 10),
                      decoration: BoxDecoration(color: CypherColors.accent.withOpacity(0.12), shape: BoxShape.circle),
                      child: Center(child: Text('${i + 1}', style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: CypherColors.accent))),
                    ),
                    Expanded(child: Text(steps[i], style: const TextStyle(fontSize: 13, color: CypherColors.textSecondary, height: 1.4))),
                  ],
                ),
              )),
            ),
          ),
        ],
      ),
    );
  }
}

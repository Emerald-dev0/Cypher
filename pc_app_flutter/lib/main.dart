import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:window_manager/window_manager.dart';
import 'package:google_fonts/google_fonts.dart';
import 'screens/dashboard_screen.dart';
import 'services/theme_service.dart';
import 'services/backend_manager.dart';

/**
 * STARTUP SEQUENCE (FIX 3):
 * 1. App launches → show loading/splash screen (StartupScreen)
 * 2. Start Python subprocess via BackendManager (Captures stdout/stderr)
 * 3. Give Python 1 second to breathe (FIX 6)
 * 4. Wait for /ping to return 200 (Health check loop - FIX 1)
 * 5. If health check passes within 15 seconds:
 *    → Hide loading screen
 *    → Show main dashboard (DashboardScreen)
 *    → Begin normal API calls (FIX 7)
 * 6. If health check fails after 15 seconds:
 *    → Show error screen: "Could not start CYPHER"
 *    → Show "Try Again" button (Restarts sequence)
 *    → Show backend logs (FIX 5)
 */

void main() async {
  // 1. Core initialization
  WidgetsFlutterBinding.ensureInitialized();

  try {
    // 2. Initialize Window Manager
    await windowManager.ensureInitialized();

    // 3. Configure Window
    WindowOptions windowOptions = const WindowOptions(
      size: Size(1100, 700),
      minimumSize: Size(900, 600),
      center: true,
      backgroundColor: Colors.transparent,
      skipTaskbar: false,
      titleBarStyle: TitleBarStyle.hidden,
      title: "CYPHER",
    );

    // 4. Show window when ready (Non-blocking)
    windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
    });

    // 5. Launch Flutter UI immediately
    runApp(
      ChangeNotifierProvider(
        create: (_) => ThemeService(),
        child: const CypherPC(),
      ),
    );
  } catch (e) {
    debugPrint("Startup Error: $e");
    // Fallback launch
    runApp(ChangeNotifierProvider(create: (_) => ThemeService(), child: const CypherPC()));
  }
}

class CypherPC extends StatelessWidget {
  const CypherPC({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeService>(
      builder: (context, themeService, child) {
        return MaterialApp(
          title: 'CYPHER',
          debugShowCheckedModeBanner: false,
          themeMode: themeService.themeMode,
          theme: ThemeService.lightTheme,
          darkTheme: ThemeService.darkTheme,
          home: const StartupScreen(),
        );
      },
    );
  }
}

class StartupScreen extends StatefulWidget {
  const StartupScreen({super.key});

  @override
  State<StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<StartupScreen> {
  final BackendManager _backend = BackendManager();
  bool _hasError = false;
  String _phase = 'Locating the CYPHER node…';

  @override
  void initState() {
    super.initState();
    _initSystem();
  }

  Future<void> _initSystem() async {
    if (!mounted) return;
    setState(() { _hasError = false; _phase = 'Locating the CYPHER node…'; });

    setState(() => _phase = 'Starting the node…');
    final started = await _backend.start();
    if (!started) {
      if (mounted) setState(() { _hasError = true; });
      return;
    }

    if (mounted) setState(() => _phase = 'Waiting for /ping…');
    final ready = await _backend.waitForBackendReady();

    if (ready) {
      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const DashboardScreen()),
        );
      }
    } else {
      if (mounted) setState(() { _hasError = true; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final accent = const Color(0xFF7C3AED);

    if (_hasError) {
      final interpreter = _backend.usedInterpreter;
      final raw = _backend.errorLog.isNotEmpty
          ? (_backend.errorLog.length > 400 ? "...${_backend.errorLog.substring(_backend.errorLog.length - 400)}" : _backend.errorLog)
          : "The backend service failed to respond in time.";
      final errMsg = interpreter == null
          ? raw
          : "Tried: $interpreter\n$raw";
      return Scaffold(
        backgroundColor: const Color(0xFF0F0F11),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 80, height: 80,
                decoration: BoxDecoration(
                  color: Colors.redAccent.withOpacity(0.08),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.redAccent.withOpacity(0.2), width: 1.5),
                  boxShadow: [BoxShadow(color: Colors.redAccent.withOpacity(0.2), blurRadius: 40, spreadRadius: -4)],
                ),
                child: const Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 36),
              ),
              const SizedBox(height: 32),
              Text('Launch Failed', style: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.w800, color: Colors.white)),
              const SizedBox(height: 8),
              Text('Could not start the CYPHER backend.', style: GoogleFonts.inter(fontSize: 13, color: Colors.white30)),
              const SizedBox(height: 32),
              Container(
                width: 480,
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.02),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.white.withOpacity(0.06)),
                ),
                child: Text(errMsg, style: GoogleFonts.inter(fontSize: 10, color: Colors.white24, height: 1.6)),
              ),
              const SizedBox(height: 36),
              GestureDetector(
                onTap: _initSystem,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [BoxShadow(color: accent.withOpacity(0.4), blurRadius: 24, offset: const Offset(0, 4))],
                  ),
                  child: Text('Try Again', style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.white)),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: const Color(0xFF0F0F11),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 96, height: 96,
              decoration: BoxDecoration(
                color: accent.withOpacity(0.1),
                shape: BoxShape.circle,
                border: Border.all(color: accent.withOpacity(0.25), width: 1.5),
                boxShadow: [BoxShadow(color: accent.withOpacity(0.25), blurRadius: 40, spreadRadius: -4)],
              ),
              child: Icon(Icons.shield_rounded, color: accent, size: 44),
            ),
            const SizedBox(height: 40),
            Text(
              'CYPHER',
              style: GoogleFonts.inter(fontSize: 28, fontWeight: FontWeight.w800, color: Colors.white, letterSpacing: 6),
            ),
            const SizedBox(height: 8),
            Text(
              _phase,
              style: GoogleFonts.inter(fontSize: 12, color: Colors.white30, letterSpacing: 1),
            ),
            const SizedBox(height: 48),
            SizedBox(
              width: 240,
              child: Stack(
                children: [
                  Container(height: 2, decoration: BoxDecoration(color: Colors.white.withOpacity(0.06), borderRadius: BorderRadius.circular(10))),
                  Container(
                    height: 2,
                    decoration: BoxDecoration(
                      color: accent,
                      borderRadius: BorderRadius.circular(10),
                      boxShadow: [BoxShadow(color: accent.withOpacity(0.6), blurRadius: 10)],
                    ),
                    child: LinearProgressIndicator(backgroundColor: Colors.transparent, valueColor: AlwaysStoppedAnimation(accent), minHeight: 2),
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

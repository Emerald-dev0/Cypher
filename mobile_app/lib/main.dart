import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'theme/app_theme.dart';
import 'providers/connection_provider.dart';
import 'providers/file_provider.dart';
import 'providers/system_provider.dart';

import 'screens/splash_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/connection_screen.dart';
import 'screens/pairing_screen.dart';
import 'screens/home_screen.dart';
import 'screens/file_browser_screen.dart';
import 'screens/file_preview_screen.dart';
import 'screens/controls_screen.dart';
import 'screens/clipboard_screen.dart';
import 'screens/guest_screen.dart';
import 'screens/activity_screen.dart';
import 'screens/notification_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/disconnected_screen.dart';
import 'screens/send_to_pc_screen.dart';
import 'screens/transfer_progress_screen.dart';
import 'screens/guide_screen.dart';
import 'screens/master_control_screen.dart';
import 'screens/process_manager_screen.dart';
import 'screens/app_launcher_screen.dart';
import 'screens/active_tasks_screen.dart';
import 'screens/screen_recorder_screen.dart';
import 'screens/phone_browser_screen.dart';
import 'screens/setup_screen.dart';
import 'screens/drop_zone_screen.dart';
import 'screens/wake_on_lan_screen.dart';
import 'screens/clipboard_history_screen.dart';

final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarBrightness: Brightness.dark,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Color(0xFF0F0F11),
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  runApp(const CypherApp());
}

/// Request a single permission at the moment the user asks for the feature
/// that needs it.
///
/// WHY THIS CHANGED
/// ────────────────
/// `main()` used to fire six permission dialogs (storage, all-files access,
/// camera, precise location, photos, media library) at cold start, before any UI
/// was on screen. That is the single fastest way to lose a user, and it is
/// against Google Play policy: permission groups must be requested in context,
/// with the requesting feature visible. Precise location in particular has no
/// honest justification shown to the user here.
///
/// Call this from the screen that needs the permission — e.g. PairingScreen
/// requests [Permission.camera] when the user taps "Scan QR", not on launch.
///
/// Returns true when granted. When permanently denied, the caller should offer
/// [openAppSettings] rather than re-prompting (Android suppresses the dialog).
Future<bool> requestPermissionWhenNeeded(Permission permission) async {
  try {
    var status = await permission.status;
    if (status.isGranted) return true;

    status = await permission.request();
    if (status.isGranted || status.isLimited) return true;

    if (status.isPermanentlyDenied) {
      debugPrint('CYPHER: $permission permanently denied — user must enable it in Settings.');
    } else {
      debugPrint('CYPHER: $permission denied.');
    }
    return false;
  } catch (e) {
    debugPrint('CYPHER: permission request failed: $e');
    return false;
  }
}

class CypherApp extends StatelessWidget {
  const CypherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ConnectionProvider()..init()),
        ChangeNotifierProvider(create: (_) => FileProvider()),
        ChangeNotifierProvider(create: (_) => SystemProvider()),
      ],
      child: MaterialApp(
        title: 'CYPHER',
        navigatorKey: navigatorKey,
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.system,
        initialRoute: '/',
        onGenerateRoute: _generateRoute,
      ),
    );
  }

  static Route<dynamic>? _generateRoute(RouteSettings s) {
    Widget page;

    switch (s.name) {
      case '/':
        page = const SplashScreen();
      case '/onboarding':
        page = const OnboardingScreen();
      case '/setup':
        page = const SetupScreen();
      case '/connection':
        page = const ConnectionScreen();
      case '/pairing':
        page = const PairingScreen();
      case '/home':
        page = const HomeScreen();
      case '/browser':
        final a = s.arguments as Map<String, dynamic>?;
        page = FileBrowserScreen(initialPath: a?['path']);
      case '/preview':
        final a = s.arguments as Map<String, dynamic>? ?? {};
        page = FilePreviewScreen(
          filePath:  a['filePath']  ?? '',
          fileName:  a['fileName']  ?? '',
          fileSize:  a['fileSize']  ?? 0,
          fileExtension: a['fileExtension'] ?? '',
        );
      case '/controls':
        page = const ControlsScreen();
      case '/clipboard':
        page = const ClipboardScreen();
      case '/guest':
        page = const GuestScreen();
      case '/activity':
        page = const ActivityScreen();
      case '/notifications':
        page = const NotificationScreen();
      case '/settings':
        page = const SettingsScreen();
      case '/disconnected':
        page = const DisconnectedScreen();
      case '/send':
        final a = s.arguments as Map<String, dynamic>?;
        page = SendToPCScreen(sharedFiles: a?['sharedFiles']);
      case '/transfers':
        page = const TransferProgressScreen();
      case '/guide':
        page = const GuideScreen();
      case '/master_control':
        page = const MasterControlScreen();
      case '/processes':
        page = const ProcessManagerScreen();
      case '/apps_launcher':
        page = const AppLauncherScreen();
      case '/active_tasks':
        page = const ActiveTasksScreen();
      case '/recorder':
        page = const ScreenRecorderScreen();
      case '/phone_browser':
        page = const PhoneBrowserScreen();
      case '/drop':
        page = const DropZoneScreen();
      case '/wol':
        page = const WakeOnLanScreen();
      case '/clipboard-history':
        page = const ClipboardHistoryScreen();
      default:
        page = const SplashScreen();
    }

    return PageRouteBuilder(
      settings: s,
      pageBuilder: (_, __, ___) => page,
      transitionDuration: const Duration(milliseconds: 260),
      transitionsBuilder: (_, anim, __, child) {
        final curved = CurvedAnimation(parent: anim, curve: Curves.easeOutCubic);
        return FadeTransition(
          opacity: curved,
          child: SlideTransition(
            position: Tween(
              begin: const Offset(0.04, 0),
              end: Offset.zero,
            ).animate(curved),
            child: child,
          ),
        );
      },
    );
  }
}
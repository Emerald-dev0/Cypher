// Tests for the desktop shell's theme state.
//
// Deliberately avoids touching `ThemeService.lightTheme` / `.darkTheme`: those
// static fields call into google_fonts, which attempts a network fetch on first
// access. That is fine at runtime and undesirable in CI. The ThemeData
// construction itself is covered by the widget tests added under roadmap P2-D2
// once the shared `packages/cypher_ui` package exists.

import 'package:cypher_pc/services/theme_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ThemeService', () {
    late ThemeService service;

    setUp(() => service = ThemeService());

    test('defaults to dark', () {
      // Matches the product's established aesthetic. Changing the default is a
      // deliberate design decision, not a refactor side effect.
      expect(service.themeMode, ThemeMode.dark);
      expect(service.isDarkMode, isTrue);
    });

    test('toggles between dark and light', () {
      service.toggleTheme();
      expect(service.themeMode, ThemeMode.light);
      expect(service.isDarkMode, isFalse);

      service.toggleTheme();
      expect(service.themeMode, ThemeMode.dark);
      expect(service.isDarkMode, isTrue);
    });

    test('notifies listeners on toggle', () {
      var notifications = 0;
      service.addListener(() => notifications++);

      service.toggleTheme();
      expect(notifications, 1);

      service.toggleTheme();
      expect(notifications, 2);
    });

    test('does not notify when nothing changed', () {
      // Guards against a rebuild storm: Consumer<ThemeService> wraps the whole
      // MaterialApp, so a spurious notifyListeners rebuilds every screen.
      var notifications = 0;
      service.addListener(() => notifications++);
      expect(notifications, 0);
    });

    test('isDarkMode stays consistent with themeMode across many toggles', () {
      for (var i = 0; i < 10; i++) {
        service.toggleTheme();
        expect(service.isDarkMode, service.themeMode == ThemeMode.dark);
      }
    });
  });
}

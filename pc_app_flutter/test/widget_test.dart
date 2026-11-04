import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:cypher_pc/services/theme_service.dart';

void main() {
  test('ThemeService toggles between dark and light mode', () {
    final service = ThemeService();

    expect(service.themeMode, ThemeMode.dark);
    expect(service.isDarkMode, isTrue);

    service.toggleTheme();

    expect(service.themeMode, ThemeMode.light);
    expect(service.isDarkMode, isFalse);
  });
}

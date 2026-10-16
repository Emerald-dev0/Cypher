import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get light {
    final base = ThemeData.light();
    return base.copyWith(
      scaffoldBackgroundColor: CypherColors.lightBgPrimary,
      primaryColor: CypherColors.accent,
      colorScheme: const ColorScheme.light(
        primary: CypherColors.accent,
        secondary: CypherColors.accentLight,
        surface: CypherColors.lightBgCard,
        error: CypherColors.error,
        onPrimary: Colors.white,
        onSurface: CypherColors.lightTextPrimary,
        outline: CypherColors.lightBorder,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
        bodyColor: CypherColors.lightTextPrimary,
        displayColor: CypherColors.lightTextPrimary,
      ),
    );
  }

  static ThemeData get dark {
    final base = ThemeData.dark();
    return base.copyWith(
      scaffoldBackgroundColor: CypherColors.bgPrimary,
      primaryColor: CypherColors.accent,
      colorScheme: ColorScheme.dark(
        primary:   CypherColors.accent,
        secondary: CypherColors.accentLight,
        surface:   CypherColors.bgCard,
        error:     CypherColors.error,
        onPrimary: CypherColors.textPrimary,
        onSurface: CypherColors.textPrimary,
        outline:   CypherColors.border,
      ),
      textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
        bodyColor:    CypherColors.textPrimary,
        displayColor: CypherColors.textPrimary,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: CypherColors.bgPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: GoogleFonts.inter(
          fontSize: 17,
          fontWeight: FontWeight.w600,
          color: CypherColors.textPrimary,
          letterSpacing: -0.3,
        ),
        iconTheme: const IconThemeData(color: CypherColors.textSecondary, size: 20),
        systemOverlayStyle: const SystemUiOverlayStyle(
          statusBarBrightness: Brightness.dark,
          statusBarIconBrightness: Brightness.light,
          systemNavigationBarColor: CypherColors.bgPrimary,
          systemNavigationBarIconBrightness: Brightness.light,
        ),
      ),
      cardTheme: CardThemeData(
        color: CypherColors.bgCard,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: CypherColors.border),
        ),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: CypherColors.bgCard,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: CypherColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: CypherColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: CypherColors.accentLight, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: CypherColors.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: CypherColors.error, width: 1.5),
        ),
        hintStyle: GoogleFonts.inter(color: CypherColors.textMuted, fontSize: 14),
        labelStyle: GoogleFonts.inter(color: CypherColors.textSecondary, fontSize: 14),
        errorStyle: GoogleFonts.inter(color: CypherColors.error, fontSize: 12),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: CypherColors.accent,
          foregroundColor: Colors.white,
          elevation: 0,
          minimumSize: const Size(double.infinity, 44),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: CypherColors.textSecondary,
          side: BorderSide(color: CypherColors.border),
          minimumSize: const Size(double.infinity, 44),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: CypherColors.accentLight,
          textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: CypherColors.border,
        thickness: 1,
        space: 0,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: CypherColors.bgCard,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        dragHandleColor: CypherColors.textMuted,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: CypherColors.bgCard,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: CypherColors.border),
        ),
        titleTextStyle: GoogleFonts.inter(
          fontSize: 17,
          fontWeight: FontWeight.w600,
          color: CypherColors.textPrimary,
        ),
        contentTextStyle: GoogleFonts.inter(
          fontSize: 14,
          color: CypherColors.textSecondary,
          height: 1.5,
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: CypherColors.bgOverlay,
        contentTextStyle: GoogleFonts.inter(color: CypherColors.textPrimary, fontSize: 13),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(color: CypherColors.border),
        ),
        behavior: SnackBarBehavior.floating,
        elevation: 0,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? Colors.white : CypherColors.textMuted),
        trackColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? CypherColors.accent : CypherColors.bgOverlay),
        trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
      ),
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? CypherColors.accent : Colors.transparent),
        side: BorderSide(color: CypherColors.border, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: CypherColors.accent,
        linearTrackColor: CypherColors.bgOverlay,
        circularTrackColor: CypherColors.bgOverlay,
      ),
      listTileTheme: ListTileThemeData(
        tileColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        titleTextStyle: GoogleFonts.inter(
          fontSize: 14, fontWeight: FontWeight.w500, color: CypherColors.textPrimary,
        ),
        subtitleTextStyle: GoogleFonts.inter(
          fontSize: 12, color: CypherColors.textSecondary,
        ),
        iconColor: CypherColors.textSecondary,
      ),
      sliderTheme: SliderThemeData(
        activeTrackColor: CypherColors.accent,
        inactiveTrackColor: CypherColors.bgOverlay,
        thumbColor: Colors.white,
        overlayColor: CypherColors.accentDim,
        trackHeight: 3,
      ),
    );
  }

  static TextStyle headline(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 28, fontWeight: FontWeight.w700,
    color: CypherColors.textPrimary, letterSpacing: -0.5,
  );
  static TextStyle title(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 20, fontWeight: FontWeight.w600,
    color: CypherColors.textPrimary, letterSpacing: -0.3,
  );
  static TextStyle subtitle(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 15, fontWeight: FontWeight.w500, color: CypherColors.textPrimary,
  );
  static TextStyle body(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 14, fontWeight: FontWeight.w400,
    color: CypherColors.textSecondary, height: 1.5,
  );
  static TextStyle caption(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 12, fontWeight: FontWeight.w400, color: CypherColors.textMuted,
  );
  static TextStyle mono(BuildContext ctx) => GoogleFonts.jetBrainsMono(
    fontSize: 13, fontWeight: FontWeight.w400, color: CypherColors.textSecondary,
  );
  static TextStyle label(BuildContext ctx) => GoogleFonts.inter(
    fontSize: 11, fontWeight: FontWeight.w600,
    color: CypherColors.textMuted, letterSpacing: 0.8,
  );
}
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'app_colors.dart';

class AppTheme {
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: AppColors.scaffoldDark,
      primaryColor: AppColors.primary,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.primary,
        secondary: AppColors.accent,
        surface: AppColors.surfaceDark,
        error: AppColors.loss,
        onPrimary: Colors.white,
        onSecondary: Colors.black,
        onSurface: AppColors.textPrimary,
        onError: Colors.white,
      ),
      textTheme: GoogleFonts.interTextTheme(
        const TextTheme(
          displayLarge:
              TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
          displayMedium:
              TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
          titleLarge:
              TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          titleMedium:
              TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          titleSmall:
              TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
          bodyLarge:
              TextStyle(fontSize: 16, fontWeight: FontWeight.w400, color: AppColors.textPrimary),
          bodyMedium:
              TextStyle(fontSize: 14, fontWeight: FontWeight.w400, color: AppColors.textSecondary),
          bodySmall:
              TextStyle(fontSize: 12, fontWeight: FontWeight.w400, color: AppColors.textMuted),
          labelLarge:
              TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textPrimary),
          labelMedium:
              TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
          labelSmall:
              TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textMuted),
        ),
      ),
      cardTheme: CardThemeData(
        color: AppColors.cardDark,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.border, width: 0.5),
        ),
        margin: const EdgeInsets.symmetric(horizontal: 0, vertical: 6),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.scaffoldDark,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: GoogleFonts.inter(
          fontSize: 22,
          fontWeight: FontWeight.w700,
          color: AppColors.textPrimary,
        ),
        iconTheme: const IconThemeData(color: AppColors.textPrimary),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: AppColors.surfaceDark,
        selectedItemColor: AppColors.primary,
        unselectedItemColor: AppColors.textMuted,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.divider,
        thickness: 0.5,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.cardDarkElevated,
        labelStyle: GoogleFonts.inter(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: AppColors.textSecondary,
        ),
        side: const BorderSide(color: AppColors.border, width: 0.5),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
      ),
      iconTheme: const IconThemeData(color: AppColors.textSecondary, size: 20),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.surfaceDark,
        indicatorColor: AppColors.primary.withAlpha(40),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: AppColors.primary, size: 24);
          }
          return const IconThemeData(color: AppColors.textMuted, size: 24);
        }),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return GoogleFonts.inter(
                fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.primary);
          }
          return GoogleFonts.inter(
              fontSize: 12, fontWeight: FontWeight.w400, color: AppColors.textMuted);
        }),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'config.dart';
import 'screens/login_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Initialise les locales pour DateFormat('fr')
  await initializeDateFormatting('fr', null);
  runApp(const SportIAApp());
}

class SportIAApp extends StatelessWidget {
  const SportIAApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SportIA Predict',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(PRIMARY_COLOR),
          primary: const Color(PRIMARY_COLOR),
          secondary: const Color(ACCENT_COLOR),
          surface: const Color(BG_COLOR),
        ),
        scaffoldBackgroundColor: const Color(BG_COLOR),
        fontFamily: 'Roboto',
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(PRIMARY_COLOR),
          foregroundColor: Colors.white,
          elevation: 0,
          centerTitle: false,
          titleTextStyle: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.3,
          ),
        ),
        cardTheme: CardThemeData(
          elevation: 4,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          color: Colors.white,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(PRIMARY_COLOR),
            foregroundColor: Colors.white,
            elevation: 3,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            textStyle: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.4,
            ),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: const Color(PRIMARY_COLOR),
            textStyle: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        chipTheme: ChipThemeData(
          backgroundColor: Colors.white,
          selectedColor: const Color(ACCENT_COLOR),
          labelStyle: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
          secondaryLabelStyle: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(color: Colors.grey.shade300),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade300),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade300),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(ACCENT_COLOR), width: 2),
          ),
          labelStyle: TextStyle(color: Colors.grey.shade700),
        ),
      ),
      home: const LoginScreen(),
    );
  }
}

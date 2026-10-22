import 'package:shared_preferences/shared_preferences.dart';

class UserService {
  static const String _keyIsPremium = 'is_premium';
  static const String _keyIsAdmin = 'is_admin';

  static Future<bool> isPremium() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyIsPremium) ?? false;
  }

  static Future<void> setPremium(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyIsPremium, value);
  }

  static Future<bool> isAdmin() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyIsAdmin) ?? false;
  }

  static Future<void> setAdmin(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyIsAdmin, value);
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyIsPremium);
    await prefs.remove(_keyIsAdmin);
  }
}

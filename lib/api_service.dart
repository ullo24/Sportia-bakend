import 'dart:convert';
import 'package:http/http.dart' as http;
import 'config.dart';

class ApiService {
  // Récupère tous les matchs sur 7 jours
  static Future<List<dynamic>> getMatchesWeek() async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/matches-week'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as List;
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // Récupère les matchs d'un jour précis
  static Future<List<dynamic>> getMatchesByDay(String day) async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/matches/$day'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as List;
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // Récupère les meilleures prédictions du jour
  static Future<List<dynamic>> getTopPredictions(String day,
      {int limit = 20}) async {
    try {
      // Utilise le nouvel endpoint /predictions/{day}/premium
      // qui renvoie tous les matchs tries par confiance
      final res = await http
          .get(Uri.parse('$API_BASE/predictions/$day/premium'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as List;
        // Prend les N premiers (deja tries par confidence DESC)
        return data.take(limit).toList();
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  // Force un refresh du pipeline
  static Future<bool> refresh() async {
    try {
      final res = await http
          .post(Uri.parse('$API_BASE/refresh'))
          .timeout(const Duration(seconds: 60));
      return res.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  // Vérifie l'état du quota
  static Future<Map<String, dynamic>> getQuota() async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/quota'))
          .timeout(const Duration(seconds: 15));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  // Récupère les scores en direct pour un jour donné
  static Future<List<dynamic>> getLiveScores(String day) async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/live-scores/$day'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as List;
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  static Future<Map<String, dynamic>> getTickets(String day) async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/tickets/$day'))
          .timeout(const Duration(seconds: 30));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  static Future<Map<String, dynamic>> getWonPredictions(String day) async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/predictions/won/$day'))
          .timeout(const Duration(seconds: 20));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  static Future<Map<String, dynamic>> getWonPredictionsWeek() async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/predictions/won-week'))
          .timeout(const Duration(seconds: 20));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  static Future<Map<String, dynamic>?> getMatchDetail(int matchId) async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/matches/$matchId/detail'))
          .timeout(const Duration(seconds: 20));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  static Future<Map<String, dynamic>> getTicketsWeek() async {
    try {
      final res = await http
          .get(Uri.parse('$API_BASE/tickets-week'))
          .timeout(const Duration(seconds: 45));
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
      return {};
    } catch (e) {
      return {};
    }
  }
}

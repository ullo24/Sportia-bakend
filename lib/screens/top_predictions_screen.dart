import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../api_service.dart';
import '../user_service.dart';
import '../widgets/match_card.dart';
import 'match_detail_screen.dart';

class TopPredictionsScreen extends StatefulWidget {
  const TopPredictionsScreen({super.key});

  @override
  State<TopPredictionsScreen> createState() => _TopPredictionsScreenState();
}

class _TopPredictionsScreenState extends State<TopPredictionsScreen> {
  List<dynamic> _top = [];
  bool _loading = true;
  bool _isPremium = false;

  @override
  void initState() {
    super.initState();
    _loadPremiumStatus();
    _load();
  }

  Future<void> _loadPremiumStatus() async {
    final premium = await UserService.isPremium();
    if (mounted) setState(() => _isPremium = premium);
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final day = DateFormat('yyyy-MM-dd').format(DateTime.now());
    final data = await ApiService.getTopPredictions(day, limit: 20);
    if (!mounted) return;
    setState(() {
      _top = data;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(color: Color(PRIMARY_COLOR)),
      );
    }

    if (_top.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.insights, size: 64, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            const Text(
              'Aucune prédiction aujourd\'hui',
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: Color(TEXT_DARK),
              ),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Rafraîchir'),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      color: const Color(PRIMARY_COLOR),
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.only(top: 8, bottom: 16),
        children: [
          Container(
            margin: const EdgeInsets.all(12),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(PRIMARY_COLOR), Color(ACCENT_COLOR)],
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              children: [
                const Icon(Icons.star, color: Colors.amber, size: 32),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Top prédictions du jour',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Les ${_top.length} meilleures opportunités',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          ..._top.map((m) => MatchCard(
                match: m,
                isPremium: _isPremium,
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => MatchDetailScreen(match: m),
                    ),
                  ).then((_) => _loadPremiumStatus());
                },
              )),
        ],
      ),
    );
  }
}

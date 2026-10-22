import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../api_service.dart';
import '../widgets/team_logo.dart';

class WonPredictionsScreen extends StatefulWidget {
  const WonPredictionsScreen({super.key});

  @override
  State<WonPredictionsScreen> createState() => _WonPredictionsScreenState();
}

class _WonPredictionsScreenState extends State<WonPredictionsScreen> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _weekMode = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    Map<String, dynamic> result;
    if (_weekMode) {
      result = await ApiService.getWonPredictionsWeek();
    } else {
      final today = DateFormat('yyyy-MM-dd').format(DateTime.now());
      result = await ApiService.getWonPredictions(today);
    }
    if (!mounted) return;
    setState(() {
      _data = result;
      _loading = false;
    });
  }

  void _toggleMode(bool week) {
    setState(() => _weekMode = week);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Prédictions justes'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment<bool>(
                  value: false,
                  label: Text('Jour', style: TextStyle(fontSize: 11)),
                ),
                ButtonSegment<bool>(
                  value: true,
                  label: Text('Semaine', style: TextStyle(fontSize: 11)),
                ),
              ],
              selected: {_weekMode},
              onSelectionChanged: (s) => _toggleMode(s.first),
              style: ButtonStyle(
                backgroundColor: WidgetStateProperty.resolveWith((states) {
                  if (states.contains(WidgetState.selected)) {
                    return Colors.white;
                  }
                  return Colors.white24;
                }),
                foregroundColor: WidgetStateProperty.resolveWith((states) {
                  if (states.contains(WidgetState.selected)) {
                    return const Color(PRIMARY_COLOR);
                  }
                  return Colors.white;
                }),
              ),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Color(PRIMARY_COLOR)),
            )
          : _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_data == null || _data!.isEmpty) {
      return _emptyState('Aucune donnée disponible');
    }

    if (_weekMode) {
      return _buildWeekView();
    }
    return _buildDayView();
  }

  Widget _buildDayView() {
    final total = _data!['total_won_predictions'] ?? 0;
    final finished = _data!['total_finished'] ?? 0;
    final matches = (_data!['matches'] as List?) ?? [];

    return RefreshIndicator(
      color: const Color(PRIMARY_COLOR),
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildStatsBanner(total, finished),
          const SizedBox(height: 16),
          if (matches.isEmpty)
            _emptyState('Aucun match terminé aujourd\'hui')
          else
            ...matches.map<Widget>((m) => _buildMatchCard(m as Map)),
        ],
      ),
    );
  }

  Widget _buildWeekView() {
    final total = _data!['total_won_predictions'] ?? 0;
    final finished = _data!['total_finished'] ?? 0;
    final days = (_data!['days'] as Map?) ?? {};

    if (days.isEmpty) {
      return _emptyState('Aucune prédiction gagnante cette semaine');
    }

    final dayKeys = days.keys.toList()..sort((a, b) => b.compareTo(a));

    return RefreshIndicator(
      color: const Color(PRIMARY_COLOR),
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildStatsBanner(total, finished),
          const SizedBox(height: 16),
          ...dayKeys.map<Widget>((dayKey) {
            final matches = (days[dayKey] as List?) ?? [];
            final dateFormatted =
                DateFormat('EEEE d MMMM', 'fr').format(DateTime.parse(dayKey));
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(
                    children: [
                      const Icon(Icons.calendar_today,
                          size: 14, color: Color(PRIMARY_COLOR)),
                      const SizedBox(width: 6),
                      Text(
                        dateFormatted,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                          color: Color(PRIMARY_COLOR),
                        ),
                      ),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color:
                              const Color(PRIMARY_COLOR).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          '${matches.length} matchs',
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: Color(PRIMARY_COLOR),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                ...matches.map<Widget>((m) => _buildMatchCard(m as Map)),
                const SizedBox(height: 8),
              ],
            );
          }),
        ],
      ),
    );
  }

  Widget _buildStatsBanner(int totalWon, int finished) {
    final rate = finished > 0 ? (totalWon / finished) : 0.0;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF2E7D32), Color(0xFF66BB6A)],
        ),
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2E7D32).withValues(alpha: 0.3),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child:
                const Icon(Icons.check_circle, color: Colors.white, size: 32),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Prédictions réussies',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$totalWon marchés gagnants sur $finished matchs analysés',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              children: [
                const Text(
                  'RÉUSSITE',
                  style: TextStyle(
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    color: Colors.grey,
                  ),
                ),
                Text(
                  '${(rate * 100).toStringAsFixed(0)}%',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFF2E7D32),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMatchCard(Map m) {
    final hg = m['home_goals'] ?? 0;
    final ag = m['away_goals'] ?? 0;
    final wonMarkets = (m['won_markets'] as List?) ?? [];

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: const Color(0xFF2E7D32).withValues(alpha: 0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Expanded(
                  child: Text(
                    m['league'] ?? '',
                    style: const TextStyle(
                      fontSize: 11,
                      color: Color(PRIMARY_COLOR),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2E7D32),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.check_circle,
                          size: 11, color: Colors.white),
                      const SizedBox(width: 4),
                      Text(
                        '${wonMarkets.length} JUSTE${wonMarkets.length > 1 ? 'S' : ''}',
                        style: const TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            // Score + équipes
            Row(
              children: [
                TeamLogo(url: m['home_logo'] as String?, size: 26),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    m['home'] ?? '?',
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '$hg - $ag',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 14,
                    ),
                  ),
                ),
                Expanded(
                  child: Text(
                    m['away'] ?? '?',
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 6),
                TeamLogo(url: m['away_logo'] as String?, size: 26),
              ],
            ),
            const SizedBox(height: 10),
            // Marchés gagnants
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: wonMarkets.map<Widget>((w) {
                final market = w as Map;
                final proba = ((market['proba'] ?? 0.0) as num) * 100;
                return Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2E7D32).withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: const Color(0xFF2E7D32).withValues(alpha: 0.4),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.check,
                          size: 11, color: Color(0xFF2E7D32)),
                      const SizedBox(width: 4),
                      Text(
                        market['description'] ?? market['market'] ?? '',
                        style: const TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF2E7D32),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${proba.toStringAsFixed(0)}%',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: const Color(0xFF2E7D32).withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _emptyState(String message) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.emoji_events_outlined,
              size: 64, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          Text(
            message,
            style: TextStyle(fontSize: 14, color: Colors.grey.shade700),
          ),
          const SizedBox(height: 8),
          Text(
            'Reviens après les matchs du jour',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
          ),
        ],
      ),
    );
  }
}

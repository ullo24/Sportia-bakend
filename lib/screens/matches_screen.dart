import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../api_service.dart';
import '../user_service.dart';
import '../widgets/match_card.dart';
import 'match_detail_screen.dart';

class MatchesScreen extends StatefulWidget {
  const MatchesScreen({super.key});

  @override
  State<MatchesScreen> createState() => _MatchesScreenState();
}

class _MatchesScreenState extends State<MatchesScreen> {
  List<dynamic> _allMatches = [];
  List<dynamic> _filtered = [];
  List<String> _leagues = ['Toutes'];
  String _selectedLeague = 'Toutes';
  DateTime _selectedDay = DateTime.now();
  bool _loading = true;
  String? _error;
  bool _isPremium = false;
  Map<int, dynamic> _liveById = {};
  Timer? _liveTimer;

  @override
  void initState() {
    super.initState();
    _loadPremiumStatus();
    _load();
    _startLiveTimer();
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    super.dispose();
  }

  void _startLiveTimer() {
    _liveTimer?.cancel();
    _liveTimer = Timer.periodic(const Duration(seconds: 60), (_) {
      _loadLiveScores();
    });
  }

  Future<void> _loadPremiumStatus() async {
    final premium = await UserService.isPremium();
    if (mounted) setState(() => _isPremium = premium);
  }

  Future<void> _loadLiveScores() async {
    final day = DateFormat('yyyy-MM-dd').format(_selectedDay);
    final data = await ApiService.getLiveScores(day);
    if (!mounted) return;
    final map = <int, dynamic>{};
    for (final m in data) {
      final id = m['id'];
      if (id is int) map[id] = m;
    }
    setState(() => _liveById = map);
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    final data = await ApiService.getMatchesWeek();
    if (!mounted) return;

    if (data.isEmpty) {
      setState(() {
        _error = 'Impossible de charger les matchs';
        _loading = false;
      });
      return;
    }

    final leagues = data
        .map((m) => (m['league'] as String?) ?? 'Inconnu')
        .toSet()
        .toList()
      ..sort();

    setState(() {
      _allMatches = data;
      _leagues = ['Toutes', ...leagues];
      _loading = false;
    });
    _applyFilters();
  }

  void _applyFilters() {
    final dayStr = DateFormat('yyyy-MM-dd').format(_selectedDay);
    final filtered = _allMatches.where((m) {
      final kickoff = m['kickoff'] as String?;
      if (kickoff == null) return false;
      final matchesDay = kickoff.substring(0, 10) == dayStr;
      final matchesLeague =
          _selectedLeague == 'Toutes' || m['league'] == _selectedLeague;
      return matchesDay && matchesLeague;
    }).toList();

    setState(() => _filtered = filtered);
    _loadLiveScores();
  }

  Future<void> _refresh() async {
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(color: Color(PRIMARY_COLOR)),
            SizedBox(height: 16),
            Text(
              'Chargement des matchs...',
              style: TextStyle(color: Color(TEXT_DARK)),
            ),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.grey),
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(fontSize: 15)),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Réessayer'),
            ),
          ],
        ),
      );
    }

    return Column(
      children: [
        _buildDayPicker(),
        _buildLeaguePicker(),
        _buildCountBar(),
        Expanded(
          child: _filtered.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.event_busy,
                          size: 64, color: Colors.grey.shade400),
                      const SizedBox(height: 12),
                      const Text(
                        'Aucun match ce jour',
                        style: TextStyle(
                          fontSize: 15,
                          color: Color(TEXT_DARK),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Essaie un autre jour ou une autre ligue',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade600,
                        ),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  color: const Color(PRIMARY_COLOR),
                  onRefresh: _refresh,
                  child: ListView.builder(
                    padding: const EdgeInsets.only(bottom: 16),
                    itemCount: _filtered.length,
                    itemBuilder: (_, i) {
                      final m = _filtered[i];
                      final id = m['id'];
                      final live = id is int ? _liveById[id] : null;
                      return MatchCard(
                        match: m,
                        isPremium: _isPremium,
                        liveStatus: live?['status'] as String?,
                        liveHomeScore: live?['home_score'] as int?,
                        liveAwayScore: live?['away_score'] as int?,
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => MatchDetailScreen(match: m),
                            ),
                          ).then((_) => _loadPremiumStatus());
                        },
                      );
                    },
                  ),
                ),
        ),
      ],
    );
  }

  Widget _buildDayPicker() {
    final days = List.generate(7, (i) => DateTime.now().add(Duration(days: i)));

    return Container(
      height: 92,
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        itemCount: days.length,
        itemBuilder: (_, i) {
          final d = days[i];
          final isSelected = DateFormat('yyyy-MM-dd').format(d) ==
              DateFormat('yyyy-MM-dd').format(_selectedDay);
          final isToday = DateFormat('yyyy-MM-dd').format(d) ==
              DateFormat('yyyy-MM-dd').format(DateTime.now());

          return GestureDetector(
            onTap: () {
              setState(() => _selectedDay = d);
              _applyFilters();
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.symmetric(horizontal: 4),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                gradient: isSelected
                    ? const LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [Color(PRIMARY_COLOR), Color(ACCENT_COLOR)],
                      )
                    : null,
                color: isSelected ? null : Colors.grey.shade100,
                borderRadius: BorderRadius.circular(12),
                boxShadow: isSelected
                    ? [
                        BoxShadow(
                          color:
                              const Color(ACCENT_COLOR).withValues(alpha: 0.4),
                          blurRadius: 8,
                          offset: const Offset(0, 3),
                        ),
                      ]
                    : null,
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    DateFormat('EEE', 'fr')
                        .format(d)
                        .toUpperCase()
                        .replaceAll('.', ''),
                    style: TextStyle(
                      color: isSelected ? Colors.white70 : Colors.grey[700],
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                      height: 1.0,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${d.day}',
                    style: TextStyle(
                      color: isSelected ? Colors.white : const Color(TEXT_DARK),
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      height: 1.0,
                    ),
                  ),
                  if (isToday)
                    Container(
                      margin: const EdgeInsets.only(top: 3),
                      width: 4,
                      height: 4,
                      decoration: BoxDecoration(
                        color: isSelected
                            ? Colors.white
                            : const Color(ACCENT_COLOR),
                        shape: BoxShape.circle,
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildLeaguePicker() {
    return Container(
      height: 50,
      color: Colors.white,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        itemCount: _leagues.length,
        itemBuilder: (_, i) {
          final lg = _leagues[i];
          final isSelected = _selectedLeague == lg;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(lg),
              selected: isSelected,
              selectedColor: const Color(ACCENT_COLOR),
              backgroundColor: Colors.grey.shade100,
              labelStyle: TextStyle(
                color: isSelected ? Colors.white : const Color(TEXT_DARK),
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
              side: BorderSide(
                color: isSelected
                    ? const Color(ACCENT_COLOR)
                    : Colors.grey.shade300,
              ),
              onSelected: (_) {
                setState(() => _selectedLeague = lg);
                _applyFilters();
              },
            ),
          );
        },
      ),
    );
  }

  Widget _buildCountBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.white,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(PRIMARY_COLOR).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                const Icon(Icons.sports_soccer,
                    size: 14, color: Color(PRIMARY_COLOR)),
                const SizedBox(width: 4),
                Text(
                  '${_filtered.length} matchs',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                    color: Color(PRIMARY_COLOR),
                  ),
                ),
              ],
            ),
          ),
          const Spacer(),
          Text(
            DateFormat('EEEE d MMMM', 'fr').format(_selectedDay),
            style: TextStyle(
              color: Colors.grey[700],
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

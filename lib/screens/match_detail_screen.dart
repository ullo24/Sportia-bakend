import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../user_service.dart';
import '../widgets/team_logo.dart';
import 'premium_screen.dart';

class MatchDetailScreen extends StatefulWidget {
  final dynamic match;

  const MatchDetailScreen({super.key, required this.match});

  @override
  State<MatchDetailScreen> createState() => _MatchDetailScreenState();
}

class _MatchDetailScreenState extends State<MatchDetailScreen> {
  bool _isPremium = false;

  @override
  void initState() {
    super.initState();
    _loadPremium();
  }

  Future<void> _loadPremium() async {
    final p = await UserService.isPremium();
    if (mounted) setState(() => _isPremium = p);
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.match;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Détail du match'),
        actions: [
          if (_isPremium)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Chip(
                label: const Text(
                  'PREMIUM',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
                backgroundColor: const Color(ACCENT_COLOR),
                padding: EdgeInsets.zero,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(m),
            const SizedBox(height: 16),
            _buildXgCard(m),
            const SizedBox(height: 16),
            _build1X2Section(m),
            const SizedBox(height: 16),
            _buildGoalsSection(m),
            const SizedBox(height: 16),
            _buildSpecialSection(m),
            const SizedBox(height: 16),
            _buildAllMarketsSection(m),
            const SizedBox(height: 16),
            _buildAnalysisSection(m),
            const SizedBox(height: 16),
            if (!_isPremium) _buildPremiumTeaser(),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(dynamic m) {
    DateTime? kickoff;
    if (m['kickoff'] != null) {
      try {
        kickoff = DateTime.parse(m['kickoff']).toLocal();
      } catch (_) {}
    }

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(PRIMARY_COLOR), Color(ACCENT_COLOR)],
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: const Color(ACCENT_COLOR).withValues(alpha: 0.3),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            children: [
              const Icon(Icons.emoji_events, color: Colors.white70, size: 16),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  m['league'] ?? 'Championnat',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (kickoff != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.access_time,
                          color: Colors.white, size: 12),
                      const SizedBox(width: 4),
                      Text(
                        DateFormat('dd/MM HH:mm').format(kickoff),
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.15),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: TeamLogo(
                        url: m['home_logo'] as String?,
                        size: 44,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      m['home'] ?? '?',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Text(
                  'VS',
                  style: TextStyle(
                    color: Color(PRIMARY_COLOR),
                    fontWeight: FontWeight.w900,
                    fontSize: 14,
                  ),
                ),
              ),
              Expanded(
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.15),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: TeamLogo(
                        url: m['away_logo'] as String?,
                        size: 44,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      m['away'] ?? '?',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildXgCard(dynamic m) {
    final homeXg = (m['home_xg'] ?? 0.0) as num;
    final awayXg = (m['away_xg'] ?? 0.0) as num;
    final totalXg = (m['total_xg'] ?? 0.0) as num;

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics,
                    color: Color(PRIMARY_COLOR), size: 20),
                const SizedBox(width: 8),
                const Text(
                  'Buts attendus (xG)',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: Color(TEXT_DARK),
                  ),
                ),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(ACCENT_COLOR).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '${totalXg.toStringAsFixed(1)} total',
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: Color(PRIMARY_COLOR),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _xgBox('Domicile', homeXg, const Color(PRIMARY_COLOR)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _xgBox('Extérieur', awayXg, const Color(ACCENT_COLOR)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _xgBox(String label, num value, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: Colors.grey.shade700,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value.toStringAsFixed(2),
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w900,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _build1X2Section(dynamic m) {
    final hw = (m['home_win'] ?? 0.0) as num;
    final d = (m['draw'] ?? 0.0) as num;
    final aw = (m['away_win'] ?? 0.0) as num;
    final maxProb = [hw, d, aw].reduce((a, b) => a > b ? a : b);

    return _section(
      title: 'RÉSULTAT DU MATCH',
      icon: Icons.sports_soccer,
      children: [
        Row(
          children: [
            Expanded(
              child: _probCard(
                'Victoire ${m['home']}',
                hw,
                hw == maxProb,
                const Color(PRIMARY_COLOR),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _probCard(
                'Match nul',
                d,
                d == maxProb,
                Colors.grey.shade600,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _probCard(
                'Victoire ${m['away']}',
                aw,
                aw == maxProb,
                const Color(ACCENT_COLOR),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildGoalsSection(dynamic m) {
    return _section(
      title: 'MARCHÉS BUTS',
      icon: Icons.trending_up,
      children: [
        _marketRow('+1.5 buts', m['over_15'], m['under_15'], 'Plus', 'Moins'),
        const SizedBox(height: 8),
        _premiumMarketRow(
          '+2.5 buts',
          m['over_25'],
          m['under_25'],
          'Plus',
          'Moins',
        ),
        const SizedBox(height: 8),
        _premiumMarketRow(
          '-3.5 buts',
          m['under_35'],
          m['over_35'],
          'Moins',
          'Plus',
        ),
        const SizedBox(height: 8),
        _premiumMarketRow(
          '-4.5 buts',
          m['under_45'],
          m['over_45'],
          'Moins',
          'Plus',
        ),
      ],
    );
  }

  Widget _buildSpecialSection(dynamic m) {
    return _section(
      title: 'MARCHÉS SPÉCIAUX',
      icon: Icons.star_outline,
      children: [
        _premiumMarketRow(
          'Les 2 équipes marquent (BTTS)',
          m['btts_yes'],
          m['btts_no'],
          'Oui',
          'Non',
        ),
        const SizedBox(height: 8),
        _premiumSingleRow(
          'But en 1ère mi-temps',
          m['first_half_goal'],
          'Oui',
        ),
        const SizedBox(height: 8),
        _premiumHandicapRow(m),
      ],
    );
  }

  Widget _buildAllMarketsSection(dynamic m) {
    if (!_isPremium) {
      return _lockedMarket('Tous les marchés (15+)');
    }

    final markets = [
      _marketRow('Double Chance 1X', m['dc_1x'], null, 'Oui', null),
      _marketRow('Double Chance 12', m['dc_12'], null, 'Oui', null),
      _marketRow('Double Chance X2', m['dc_x2'], null, 'Oui', null),
      _marketRow('Draw No Bet - Domicile', m['dnb_home'], null, 'Oui', null),
      _marketRow('Draw No Bet - Extérieur', m['dnb_away'], null, 'Oui', null),
      _marketRow('Over 0.5 but', m['over_05'], null, 'Oui', null),
      _marketRow('Under 0.5 but', m['under_05'], null, 'Oui', null),
      _marketRow('BTTS & Over 2.5', m['btts_over_25'], null, 'Oui', null),
      _marketRow('BTTS & Under 3.5', m['btts_under_35'], null, 'Oui', null),
      _marketRow(
          'Handicap -1 Domicile', m['handicap_home_minus1'], null, 'Oui', null),
      _marketRow('Handicap -1 Extérieur', m['handicap_away_minus1'], null,
          'Oui', null),
      _marketRow(
          'Handicap +1 Domicile', m['handicap_home_plus1'], null, 'Oui', null),
      _marketRow(
          'Handicap +1 Extérieur', m['handicap_away_plus1'], null, 'Oui', null),
      _marketRow('But en 1ère MT', m['first_half_goal'], null, 'Oui', null),
      _marketRow('Domicile marque', m['home_scores'], null, 'Oui', null),
      _marketRow('Extérieur marque', m['away_scores'], null, 'Oui', null),
    ];

    // Gere exact_scores qui peut etre :
    // - une List (venant de /matches/{id}/detail)
    // - une String JSON (venant de /matches-week)
    // - null
    List<dynamic> exactScores = [];
    final raw = m['exact_scores'];
    if (raw is List) {
      exactScores = raw;
    } else if (raw is String && raw.isNotEmpty) {
      final decoded = _tryDecodeJsonList(raw);
      if (decoded != null) exactScores = decoded;
    }

    if (exactScores.isNotEmpty) {
      markets.add(
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Scores exacts les plus probables',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: Color(TEXT_DARK),
                ),
              ),
              const SizedBox(height: 4),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: exactScores.map<Widget>((s) {
                  final score = s['score'] ?? '?';
                  final prob = ((s['prob'] ?? 0.0) as num) * 100;
                  return Chip(
                    label: Text(
                      '$score (${prob.toStringAsFixed(0)}%)',
                      style: const TextStyle(fontSize: 10),
                    ),
                    backgroundColor: Colors.blue.shade50,
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      );
    }

    return _section(
      title: 'TOUS LES MARCHÉS (PREMIUM)',
      icon: Icons.list_alt,
      children: markets,
    );
  }

  Widget _buildAnalysisSection(dynamic m) {
    final analysis = (m['analysis'] ?? '') as String;

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.psychology,
                    color: Color(PRIMARY_COLOR), size: 20),
                const SizedBox(width: 8),
                const Text(
                  'Analyse IA',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: Color(TEXT_DARK),
                  ),
                ),
                const Spacer(),
                if (!_isPremium)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.amber.shade600,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text(
                      'PREMIUM',
                      style: TextStyle(
                        fontSize: 8,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(BG_COLOR),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.grey.shade200),
              ),
              child: _isPremium
                  ? Text(
                      analysis,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(TEXT_DARK),
                        height: 1.6,
                      ),
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _shortAnalysis(m),
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(TEXT_DARK),
                            height: 1.6,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: Colors.amber.shade50,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.amber.shade300),
                          ),
                          child: const Row(
                            children: [
                              Icon(Icons.lock, size: 14, color: Colors.orange),
                              SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  'Analyse complète réservée aux membres Premium',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: Colors.orange,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  String _shortAnalysis(dynamic m) {
    final hw = (((m['home_win'] ?? 0.0) as num) * 100).toStringAsFixed(0);
    final d = (((m['draw'] ?? 0.0) as num) * 100).toStringAsFixed(0);
    final aw = (((m['away_win'] ?? 0.0) as num) * 100).toStringAsFixed(0);
    final totalXg = ((m['total_xg'] ?? 0.0) as num).toStringAsFixed(1);
    return '${m['home']} vs ${m['away']}\n\n'
        'Buts attendus : $totalXg au total\n'
        '1X2 : $hw% / $d% / $aw%';
  }

  Widget _buildPremiumTeaser() {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(
            colors: [Colors.amber.shade400, Colors.orange.shade600],
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.workspace_premium, color: Colors.white, size: 28),
                SizedBox(width: 8),
                Text(
                  'Débloquer tous les marchés',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              '+2.5, -3.5, -4.5, BTTS, Handicap,\n1ère mi-temps, analyse complète',
              style: TextStyle(color: Colors.white, fontSize: 13),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () async {
                  await Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const PremiumScreen(),
                    ),
                  );
                  await _loadPremium();
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.orange.shade700,
                ),
                child: const Text('Voir les offres Premium'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: const Color(PRIMARY_COLOR), size: 18),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    color: Color(PRIMARY_COLOR),
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _probCard(String label, num prob, bool highlight, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
      decoration: BoxDecoration(
        color: highlight ? color : color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: highlight ? color : color.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        children: [
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 9,
              color: highlight ? Colors.white70 : Colors.grey.shade700,
              fontWeight: FontWeight.w500,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          Text(
            '${(prob * 100).toStringAsFixed(0)}%',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w900,
              color: highlight ? Colors.white : color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _marketRow(
    String label,
    dynamic prob1,
    dynamic prob2,
    String sub1,
    String? sub2,
  ) {
    final p1 = (prob1 ?? 0.0) as num;
    final p2 = (prob2 ?? 0.0) as num;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(BG_COLOR),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Color(TEXT_DARK),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: _miniProb(
                  sub1,
                  p1,
                  p1 >= 0.55,
                  const Color(PRIMARY_COLOR),
                ),
              ),
              if (sub2 != null) ...[
                const SizedBox(width: 6),
                Expanded(
                  child: _miniProb(
                    sub2,
                    p2,
                    p2 >= 0.55,
                    Colors.grey.shade600,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _premiumMarketRow(
    String label,
    dynamic prob1,
    dynamic prob2,
    String sub1,
    String? sub2,
  ) {
    if (!_isPremium) {
      return _lockedMarket(label);
    }
    return _marketRow(label, prob1, prob2, sub1, sub2);
  }

  Widget _premiumSingleRow(String label, dynamic prob, String sub) {
    if (!_isPremium) {
      return _lockedMarket(label);
    }
    final p = (prob ?? 0.0) as num;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(BG_COLOR),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Color(TEXT_DARK),
            ),
          ),
          const SizedBox(height: 6),
          _miniProb(sub, p, p >= 0.55, const Color(PRIMARY_COLOR)),
        ],
      ),
    );
  }

  Widget _lockedMarket(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade300),
      ),
      child: Row(
        children: [
          Icon(Icons.lock, size: 14, color: Colors.grey.shade600),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: Colors.grey.shade700,
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.amber.shade600,
              borderRadius: BorderRadius.circular(4),
            ),
            child: const Text(
              'PREMIUM',
              style: TextStyle(
                fontSize: 8,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _premiumHandicapRow(dynamic m) {
    if (!_isPremium) {
      return _lockedMarket('Handicap -1');
    }
    final homeH = (m['handicap_home_1'] ?? 0.0) as num;
    final awayH = (m['handicap_away_1'] ?? 0.0) as num;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(BG_COLOR),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Handicap -1 (gagne par 2+ buts)',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Color(TEXT_DARK),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: _miniProb(
                  m['home'] ?? 'Dom.',
                  homeH,
                  homeH >= 0.30,
                  const Color(PRIMARY_COLOR),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _miniProb(
                  m['away'] ?? 'Ext.',
                  awayH,
                  awayH >= 0.30,
                  const Color(ACCENT_COLOR),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _miniProb(String label, num prob, bool highlight, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: highlight ? color : color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: highlight ? color : color.withValues(alpha: 0.25),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w500,
                color: highlight ? Colors.white : const Color(TEXT_DARK),
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 4),
          Text(
            '${(prob * 100).toStringAsFixed(0)}%',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: highlight ? Colors.white : color,
            ),
          ),
        ],
      ),
    );
  }

  List<dynamic>? _tryDecodeJsonList(String s) {
    try {
      final decoded = jsonDecode(s);
      if (decoded is List) return decoded;
      return null;
    } catch (_) {
      return null;
    }
  }
}

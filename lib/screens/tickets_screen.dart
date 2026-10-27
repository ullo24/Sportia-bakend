import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../config.dart';
import '../api_service.dart';
import '../user_service.dart';
import '../widgets/team_logo.dart';
import 'match_detail_screen.dart';

class TicketsScreen extends StatefulWidget {
  const TicketsScreen({super.key});

  @override
  State<TicketsScreen> createState() => _TicketsScreenState();
}

class _TicketsScreenState extends State<TicketsScreen> {
  Map<String, dynamic>? _tickets;
  Map<String, dynamic>? _weekTicket;
  bool _loading = true;
  String? _error;
  bool _isPremium = false;
  bool _weekMode = false;

  @override
  void initState() {
    super.initState();
    _loadPremium();
    _load();
  }

  Future<void> _loadPremium() async {
    final p = await UserService.isPremium();
    if (mounted) setState(() => _isPremium = p);
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_weekMode) {
        final data = await ApiService.getTicketsWeek();
        if (!mounted) return;
        if (data.isEmpty || data['error'] != null) {
          setState(() {
            _error = data['error'] ?? 'Aucun ticket semaine disponible';
            _loading = false;
          });
        } else {
          setState(() {
            _weekTicket = data;
            _loading = false;
          });
        }
      } else {
        final day = DateFormat('yyyy-MM-dd').format(DateTime.now());
        final data = await ApiService.getTickets(day);
        if (!mounted) return;
        if (data.isEmpty || data['error'] != null) {
          setState(() {
            _error = data['error'] ?? 'Aucun ticket disponible';
            _loading = false;
          });
        } else {
          setState(() {
            _tickets = data;
            _loading = false;
          });
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Erreur de chargement';
        _loading = false;
      });
    }
  }

  void _toggleMode(bool week) {
    setState(() => _weekMode = week);
    _load();
  }

  Future<void> _openMatchDetail(Map pick) async {
    final matchId = pick['match_id'];
    if (matchId == null) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(
        child: CircularProgressIndicator(color: Color(PRIMARY_COLOR)),
      ),
    );
    try {
      final match = await ApiService.getMatchDetail(matchId as int);
      if (!mounted) return;
      Navigator.pop(context);
      if (match == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Match introuvable')),
        );
        return;
      }
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => MatchDetailScreen(match: match)),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Erreur de chargement')),
      );
    }
  }

 
  // 👇👇👇 INSÈRE ICI LE BLOC _safeTicket 👇👇👇
  Map<String, dynamic> _safeTicket(String key) {
    final t = _tickets?[key];
    if (t is Map<String, dynamic>) return t;
    return {
      "name": "",
      "total_cote": 1.0,
      "count": 0,
      "joint_prob": 0.0,
      "joint_prob_pct": 0.0,
      "picks": [],
    };
  }
  // 👆👆👆 FIN DU BLOC À INSÉRER 👆👆👆
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tickets'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment<bool>(
                  value: false,
                  icon: Icon(Icons.today, size: 16),
                  label: Text('Jour', style: TextStyle(fontSize: 11)),
                ),
                ButtonSegment<bool>(
                  value: true,
                  icon: Icon(Icons.calendar_month, size: 16),
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
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.confirmation_number_outlined,
                size: 64, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(_error!,
                  style: const TextStyle(fontSize: 14),
                  textAlign: TextAlign.center),
            ),
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

    return RefreshIndicator(
      color: const Color(PRIMARY_COLOR),
      onRefresh: _load,
      child: _weekMode ? _buildWeekView() : _buildDayView(),
    );
  }

    // ============ VUE JOUR ============
  Widget _buildDayView() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildHeaderBanner('Tickets du jour',
            DateFormat('EEEE d MMMM', 'fr').format(DateTime.now())),
        const SizedBox(height: 16),
        _buildTicketCard(
          data: _safeTicket('safe'),
          title: 'SAFE',
          subtitle: 'Cote ~2.5 · 2-3 picks fiables',
          gradient: [const Color(0xFF2E7D32), const Color(0xFF4CAF50)],
          icon: Icons.verified,
          isPremiumLocked: false,
        ),
        const SizedBox(height: 12),
        _buildTicketCard(
          data: _safeTicket('medium_short'),
          title: 'MEDIUM SHORT',
          subtitle: 'Cote ~55 · 5-8 picks',
          gradient: [const Color(0xFF1565C0), const Color(0xFF42A5F5)],
          icon: Icons.trending_up,
          isPremiumLocked: !_isPremium,
        ),
        const SizedBox(height: 12),
        _buildTicketCard(
          data: _safeTicket('medium_long'),
          title: 'MEDIUM LONG',
          subtitle: 'Cote ~125 · 7-10 picks',
          gradient: [const Color(0xFF00838F), const Color(0xFF26C6DA)],
          icon: Icons.rocket_launch,
          isPremiumLocked: !_isPremium,
        ),
        const SizedBox(height: 12),
        _buildTicketCard(
          data: _safeTicket('risky'),
          title: 'RISKY',
          subtitle: 'Cote ~1000 · Marchés variés',
          gradient: [const Color(0xFFB71C1C), const Color(0xFFFF5722)],
          icon: Icons.local_fire_department,
          isPremiumLocked: !_isPremium,
        ),
        const SizedBox(height: 16),
        _buildDisclaimer(),
      ],
    );
  }

  // ============ VUE SEMAINE ============
  // ============ VUE SEMAINE ============
  Widget _buildWeekView() {
    final picks = (_weekTicket!['picks'] as List?) ?? [];
    final cote = _weekTicket!['total_cote'] ?? 1.0;
    final count = _weekTicket!['total_picks'] ?? 0;
    final eligible = _weekTicket!['total_eligible_matches'] ?? 0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildHeaderBanner(
          'Ticket semaine',
          'Top équipes · ${_weekTicket!['week_start']} → ${_weekTicket!['week_end']}',
        ),
        const SizedBox(height: 12),
        // Statistiques
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF6A1B9A), Color(0xFFAB47BC)],
            ),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(
            children: [
              Expanded(
                child: _statBox('Matchs éligibles', '$eligible'),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _statBox('Picks', '$count'),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _statBox('Cote', cote.toStringAsFixed(2)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // Le ticket semaine
        Card(
          elevation: 4,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(18),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: [Color(0xFF6A1B9A), Color(0xFFAB47BC)],
                  ),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(20),
                    topRight: Radius.circular(20),
                  ),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.calendar_month,
                        color: Colors.white, size: 32),
                    const SizedBox(width: 10),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'SEMAINE RISKY',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.8,
                            ),
                          ),
                          Text(
                            'Top équipes · Picks safe',
                            style: TextStyle(
                              color: Colors.white70,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        children: [
                          const Text(
                            'COTE',
                            style: TextStyle(
                              fontSize: 8,
                              fontWeight: FontWeight.bold,
                              color: Colors.grey,
                            ),
                          ),
                          Text(
                            cote.toStringAsFixed(2),
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w900,
                              color: Color(0xFF6A1B9A),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                color: const Color(0xFF6A1B9A).withValues(alpha: 0.08),
                child: Row(
                  children: [
                    const Icon(Icons.list_alt,
                        size: 14, color: Color(0xFF6A1B9A)),
                    const SizedBox(width: 6),
                    Text(
                      '$count sélections',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF6A1B9A),
                      ),
                    ),
                    const Spacer(),
                    if (!_isPremium)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
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
              ),
              if (!_isPremium)
                _buildLockedPicks(count)
              else
                ...picks.map<Widget>((p) => _buildPickRow(p as Map)),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _buildDisclaimer(),
      ],
    );
  }

  Widget _statBox(String label, String value) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        children: [
          Text(label,
              style: const TextStyle(color: Colors.white70, fontSize: 9)),
          const SizedBox(height: 2),
          Text(value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              )),
        ],
      ),
    );
  }

  Widget _buildHeaderBanner(String title, String subtitle) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(PRIMARY_COLOR), Color(ACCENT_COLOR)],
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.confirmation_number,
                color: Colors.white, size: 32),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    )),
                const SizedBox(height: 4),
                Text(subtitle,
                    style:
                        const TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTicketCard({
    required Map<String, dynamic> data,
    required String title,
    required String subtitle,
    required List<Color> gradient,
    required IconData icon,
    required bool isPremiumLocked,
  }) {
    final count = data['count'] ?? 0;
    final cote = data['total_cote'] ?? 1.0;
    final picks = (data['picks'] as List?) ?? [];

    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: gradient),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(20),
                topRight: Radius.circular(20),
              ),
            ),
            child: Row(
              children: [
                Icon(icon, color: Colors.white, size: 28),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0.8,
                          )),
                      Text(subtitle,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 11)),
                    ],
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Column(
                    children: [
                      const Text('COTE',
                          style: TextStyle(
                            fontSize: 8,
                            fontWeight: FontWeight.bold,
                            color: Colors.grey,
                          )),
                      Text(cote.toStringAsFixed(2),
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w900,
                            color: gradient.first,
                          )),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: gradient.first.withValues(alpha: 0.08),
            child: Row(
              children: [
                Icon(Icons.list_alt, size: 14, color: gradient.first),
                const SizedBox(width: 6),
                Text('$count sélections',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: gradient.first,
                    )),
                // 👇👇👇 INSÈRE ICI LE BLOC joint_prob_pct 👇👇👇
                if ((data['joint_prob_pct'] ?? 0) > 0) ...[
                  const SizedBox(width: 8),
                  Text(
                    '· ${(data['joint_prob_pct'] as num).toStringAsFixed(1)}% chance',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: gradient.first.withValues(alpha: 0.8),
                    ),
                  ),
                ],
                const Spacer(),
                if (isPremiumLocked)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.amber.shade600,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text('PREMIUM',
                        style: TextStyle(
                          fontSize: 8,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        )),
                  ),
              ],
            ),
          ),
          if (isPremiumLocked)
            _buildLockedPicks(count)
          else
            ...picks.map<Widget>((p) => _buildPickRow(p as Map)),
        ],
      ),
    );
  }

  Widget _buildLockedPicks(int count) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          Icon(Icons.lock, size: 40, color: Colors.grey.shade400),
          const SizedBox(height: 8),
          Text('$count sélections disponibles',
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 13,
              )),
          const SizedBox(height: 4),
          Text('Passe Premium pour voir les picks',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        ],
      ),
    );
  }

  Widget _buildPickRow(Map p) {
    final result = (p['result'] ?? 'pending').toString();
    final reason = (p['reason'] ?? '').toString();
    final currentScore = p['current_score'];

    Color bgColor, borderColor, iconColor;
    IconData icon;
    String statusLabel;

    switch (result) {
      case 'won':
        bgColor = const Color(0xFF2E7D32).withValues(alpha: 0.08);
        borderColor = const Color(0xFF2E7D32).withValues(alpha: 0.4);
        iconColor = const Color(0xFF2E7D32);
        icon = Icons.check_circle;
        statusLabel = 'GAGNÉ';
        break;
      case 'lost':
        bgColor = const Color(0xFFD32F2F).withValues(alpha: 0.08);
        borderColor = const Color(0xFFD32F2F).withValues(alpha: 0.4);
        iconColor = const Color(0xFFD32F2F);
        icon = Icons.cancel;
        statusLabel = 'PERDU';
        break;
      default:
        bgColor = const Color(0xFFF57C00).withValues(alpha: 0.08);
        borderColor = const Color(0xFFF57C00).withValues(alpha: 0.4);
        iconColor = const Color(0xFFF57C00);
        icon = Icons.schedule;
        statusLabel = 'EN ATTENTE';
    }

    return InkWell(
      onTap: () => _openMatchDetail(p),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: bgColor,
          border: Border(top: BorderSide(color: borderColor, width: 1)),
        ),
        child: Row(
          children: [
            TeamLogo(url: p['home_logo'] as String?, size: 22),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${p['home']} - ${p['away']}',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Color(TEXT_DARK),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Flexible(
                        child: Text(p['description'] ?? p['market'] ?? '',
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.grey.shade700,
                              fontWeight: FontWeight.w600,
                            ),
                            overflow: TextOverflow.ellipsis),
                      ),
                      if (currentScore != null &&
                          currentScore.toString().isNotEmpty) ...[
                        const SizedBox(width: 6),
                        Text('[$currentScore]',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: iconColor,
                            )),
                      ],
                    ],
                  ),
                  if (reason.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(reason,
                          style: TextStyle(
                            fontSize: 10,
                            color: iconColor,
                            fontWeight: FontWeight.w500,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(PRIMARY_COLOR).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(p['cote'].toStringAsFixed(2),
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w900,
                        color: Color(PRIMARY_COLOR),
                      )),
                ),
                const SizedBox(height: 4),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icon, size: 12, color: iconColor),
                    const SizedBox(width: 2),
                    Text(statusLabel,
                        style: TextStyle(
                          fontSize: 8,
                          fontWeight: FontWeight.bold,
                          color: iconColor,
                        )),
                  ],
                ),
                const SizedBox(height: 2),
                const Icon(Icons.chevron_right, size: 14, color: Colors.grey),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDisclaimer() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.amber.shade50,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.amber.shade200),
      ),
      child: Row(
        children: [
          Icon(Icons.info_outline, size: 18, color: Colors.orange.shade700),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Les cotes sont des estimations. Aucune garantie de gain. Jouer comporte des risques.',
              style: TextStyle(
                fontSize: 11,
                color: Colors.orange.shade900,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

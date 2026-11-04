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
  Map<String, dynamic>? _weekValueTicket; // 👈 AJOUTE CECI
  bool _loading = true;
  String? _error;
  bool _isPremium = false;
  bool _weekMode = false;
  bool _showValueWeek = false; // 👈 Nouveau (false = Complet, true = Value)

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
        // On charge les deux tickets en parallèle
        final results = await Future.wait([
          ApiService.getTicketsWeek(),
          ApiService.getTicketsWeekValue(),
        ]);
        final completeData = results[0];
        final valueData = results[1];

        if (!mounted) return;
        
        setState(() {
          _weekTicket = completeData;
          _weekValueTicket = valueData;
          _loading = false;
        });
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
  
    Future<void> _showAiChat(Map pick) async {
    TextEditingController textController = TextEditingController();
    bool isLoading = true;
    Map<String, dynamic>? aiResponse;
    String currentQuestion = "Pourquoi ce pick a-t-il été choisi ?";

    showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            
            // Fonction interne pour poser une question à l'IA
            void askAi(String question) {
              setDialogState(() {
                isLoading = true;
                currentQuestion = question;
              });
              
              ApiService.explainPick(pick['match_id'], pick['market'], question).then((res) {
                if (context.mounted) {
                  setDialogState(() {
                    aiResponse = res;
                    isLoading = false;
                  });
                }
              });
            }

            // Appel initial (seulement la première fois)
            if (isLoading && aiResponse == null) {
              askAi(currentQuestion);
            }

            return AlertDialog(
              title: Row(
                children: [
                  const Icon(Icons.smart_toy, color: Colors.blue),
                  const SizedBox(width: 8),
                  const Text('Analyse & Chat IA', style: TextStyle(fontSize: 16)),
                ],
              ),
              content: SizedBox(
                width: double.maxFinite,
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // 1. Affichage de la question posée
                      Text('Question : "$currentQuestion"', 
                        style: const TextStyle(fontStyle: FontStyle.italic, color: Colors.grey, fontSize: 12)),
                      const SizedBox(height: 12),
                      
                      // 2. Affichage de la réponse de l'IA
                      if (isLoading)
                        const SizedBox(height: 80, child: Center(child: CircularProgressIndicator()))
                      else ...[
                        Text(
                          aiResponse?['explanation'] ?? 'Désolé, je n\'ai pas pu analyser ce pick.',
                          style: const TextStyle(fontSize: 13, height: 1.4),
                        ),
                        
                        // 3. Si l'IA propose une alternative, on affiche le bouton
                        if (aiResponse?['alternative_market'] != null) ...[
                          const SizedBox(height: 16),
                          const Divider(),
                          const Text("💡 Suggestion d'alternative :", 
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.green)),
                          const SizedBox(height: 8),
                          ElevatedButton.icon(
                            icon: const Icon(Icons.swap_horiz),
                            label: Text("Remplacer par ${aiResponse?['alternative_description']}"),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.green,
                              foregroundColor: Colors.white,
                              minimumSize: const Size(double.infinity, 40),
                            ),
                            onPressed: () {
                              // 👇 APPEL À LA FONCTION DE MISE À JOUR DYNAMIQUE 👇
                              _updatePickInCurrentView(
                                pick['match_id'] as int,
                                aiResponse!['alternative_market'].toString(),
                                aiResponse!['alternative_description'].toString(),
                                (aiResponse!['alternative_proba'] as num).toDouble(),
                              );
                              
                              Navigator.pop(context); // Fermer la popup
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('✅ Pick modifié et ticket recalculé !'),
                                  backgroundColor: Colors.green,
                                ),
                              );
                            },
                          ),
                        ]
                      ],
                      
                      const SizedBox(height: 16),
                      const Divider(),
                      
                      // 4. Champ de texte pour continuer la discussion
                      TextField(
                        controller: textController,
                        decoration: InputDecoration(
                          hintText: "Ex: Et si on jouait le BTTS ?",
                          hintStyle: const TextStyle(fontSize: 12),
                          suffixIcon: IconButton(
                            icon: const Icon(Icons.send, color: Colors.blue, size: 20),
                            onPressed: () {
                              if (textController.text.trim().isNotEmpty) {
                                askAi(textController.text.trim());
                                textController.clear();
                              }
                            },
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        ),
                        style: const TextStyle(fontSize: 13),
                        onSubmitted: (val) {
                          if (val.trim().isNotEmpty) {
                            askAi(val.trim());
                            textController.clear();
                          }
                        },
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Fermer'),
                ),
              ],
            );
          },
        );
      },
    );
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
    // 1. On sélectionne les données en fonction du bouton actif
    final currentData = _showValueWeek ? _weekValueTicket : _weekTicket;

    if (currentData == null) {
      return const Center(child: Text("Chargement des tickets..."));
    }

    final picks = (currentData['picks'] as List?) ?? [];
    final cote = currentData['total_cote'] ?? 1.0;
    final count = currentData['total_picks'] ?? 0;
    final eligible = currentData['total_eligible_matches'] ?? count;
    final isValue = _showValueWeek;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // 👇 NOUVEAU : Le sélecteur Complet / Value 👇
        Center(
          child: SegmentedButton<bool>(
            segments: const [
              ButtonSegment<bool>(
                value: false,
                label: Text('Complet', style: TextStyle(fontSize: 12)),
                icon: Icon(Icons.list, size: 16),
              ),
              ButtonSegment<bool>(
                value: true,
                label: Text('Value (Top)', style: TextStyle(fontSize: 12)),
                icon: Icon(Icons.star, size: 16),
              ),
            ],
            selected: {_showValueWeek},
            onSelectionChanged: (s) => setState(() => _showValueWeek = s.first),
          ),
        ),
        const SizedBox(height: 16),

        // 2. Bannière d'en-tête
        _buildHeaderBanner(
          isValue ? 'Ticket Value Optimisé' : 'Ticket Semaine Complet',
          'Top équipes · ${currentData['week_start']} → ${currentData['week_end']}',
        ),
        const SizedBox(height: 12),

        // 3. Statistiques (Changement de couleur : Vert pour Value, Violet pour Complet)
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: isValue
                  ? [const Color(0xFF00897B), const Color(0xFF26A69A)] // Teal
                  : [const Color(0xFF6A1B9A), const Color(0xFFAB47BC)], // Violet
            ),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(
            children: [
              Expanded(
                child: _statBox('Matchs', '$eligible'),
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

        // 4. La carte du ticket
        Card(
          elevation: 4,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          child: Column(
            children: [
              // En-tête de la carte
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: isValue
                        ? [const Color(0xFF00897B), const Color(0xFF26A69A)]
                        : [const Color(0xFF6A1B9A), const Color(0xFFAB47BC)],
                  ),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(20),
                    topRight: Radius.circular(20),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(isValue ? Icons.stars : Icons.calendar_month,
                        color: Colors.white, size: 32),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            isValue ? 'VALUE PICKS' : 'SEMAINE COMPLET',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.8,
                            ),
                          ),
                          Text(
                            isValue ? 'Optimisé pour gagner' : 'Tous les matchs éligibles',
                            style: const TextStyle(
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
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w900,
                              color: isValue ? const Color(0xFF00897B) : const Color(0xFF6A1B9A),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              
              // Barre de sélections
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                color: (isValue ? const Color(0xFF00897B) : const Color(0xFF6A1B9A)).withValues(alpha: 0.08),
                child: Row(
                  children: [
                    Icon(Icons.list_alt,
                        size: 14, color: isValue ? const Color(0xFF00897B) : const Color(0xFF6A1B9A)),
                    const SizedBox(width: 6),
                    Text(
                      '$count sélections',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: isValue ? const Color(0xFF00897B) : const Color(0xFF6A1B9A),
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
              
              // Liste des picks
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

    void _updatePickInCurrentView(int matchId, String newMarket, String newDesc, double newProba) {
    double newCote = 1.0 / newProba;

    // Fonction utilitaire pour mettre à jour un ticket spécifique
    void processTicket(Map<String, dynamic>? ticketData) {
      if (ticketData == null) return;
      final picks = ticketData['picks'] as List?;
      if (picks == null) return;

      bool updated = false;
      double newTotalCote = 1.0;
      double newJointProb = 1.0;

      for (var p in picks) {
        if (p['match_id'] == matchId) {
          p['market'] = newMarket;
          p['description'] = newDesc;
          p['proba'] = newProba;
          p['cote'] = newCote;
          updated = true;
        }
        // On recalcule la cote totale et la proba jointe au passage
        newTotalCote *= ((p['cote'] ?? 1.0) as num).toDouble();
        newJointProb *= ((p['proba'] ?? 1.0) as num).toDouble();
      }

      if (updated) {
        ticketData['total_cote'] = newTotalCote;
        ticketData['joint_prob_pct'] = newJointProb * 100;
        ticketData['total_picks'] = picks.length; // au cas où
      }
    }

    // On met à jour l'état et on rafraîchit l'écran
    setState(() {
      if (_weekMode) {
        // Si on est dans la vue Semaine, on met à jour les deux tickets (Complet et Value)
        processTicket(_weekTicket);
        processTicket(_weekValueTicket);
      } else {
        // Si on est dans la vue Jour, on cherche dans les 4 tickets
        if (_tickets != null) {
          processTicket(_tickets!['safe']);
          processTicket(_tickets!['medium_short']);
          processTicket(_tickets!['medium_long']);
          processTicket(_tickets!['risky']);
          processTicket(_tickets!['medium']); // fallback
        }
      }
    });
  }
                          
  Widget _buildPickRow(Map p) {
    final result = (p['result'] ?? 'pending').toString();
    final reason = (p['reason'] ?? '').toString();
    final currentScore = p['current_score'];

    // Formatage de la date et de l'heure
    String dateStr = '';
    if (p['kickoff'] != null) {
      try {
        final dt = DateTime.parse(p['kickoff']).toLocal();
        dateStr = DateFormat("d MMM 'à' HH:mm", 'fr').format(dt);
      } catch (_) {}
    }

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
                  // Affichage de l'heure
                  if (dateStr.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2, bottom: 2),
                      child: Row(
                        children: [
                          Icon(Icons.access_time, size: 10, color: Colors.grey.shade600),
                          const SizedBox(width: 4),
                          Text(
                            dateStr,
                            style: TextStyle(
                              fontSize: 10,
                              color: Colors.grey.shade600,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
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
            
            // 👇 COLONNE DE DROITE (Cote, Statut et Bouton IA) 👇
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
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
                const SizedBox(height: 6),
                
                // 👇 LE BOUTON IA EST ICI 👇
                InkWell(
                  onTap: () => _showAiChat(p),
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.blue.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.blue.withValues(alpha: 0.3), width: 1),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.smart_toy, size: 12, color: Colors.blue),
                        SizedBox(width: 4),
                        Text('IA', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.blue)),
                      ],
                    ),
                  ),
                ),
                // 👆 FIN DU BOUTON IA 👆
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

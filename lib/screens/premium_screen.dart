import 'package:flutter/material.dart';
import '../config.dart';
import '../user_service.dart';

class PremiumScreen extends StatefulWidget {
  const PremiumScreen({super.key});

  @override
  State<PremiumScreen> createState() => _PremiumScreenState();
}

class _PremiumScreenState extends State<PremiumScreen> {
  bool _isPremium = false;
  bool _yearly = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await UserService.isPremium();
    if (mounted) setState(() => _isPremium = p);
  }

  Future<void> _activate() async {
    await UserService.setPremium(true);
    await _load();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Premium activé (démo)'),
        backgroundColor: Colors.green,
      ),
    );
  }

  Future<void> _cancel() async {
    await UserService.setPremium(false);
    await _load();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Premium désactivé'),
        backgroundColor: Colors.orange,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SportIA Premium')),
      body: _isPremium ? _buildActiveState() : _buildPaywall(),
    );
  }

  // ===== ETAT ACTIF (deja premium) =====
  Widget _buildActiveState() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFFF57C00), Color(0xFFFFA726)],
              ),
              borderRadius: BorderRadius.circular(24),
              boxShadow: [
                BoxShadow(
                  color: Colors.orange.withValues(alpha: 0.3),
                  blurRadius: 24,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.workspace_premium,
                    size: 56,
                    color: Colors.orange.shade700,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Premium actif',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Tous les marchés débloqués',
                  style: TextStyle(color: Colors.white70, fontSize: 14),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          _buildBenefitsList(),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: _cancel,
            icon: const Icon(Icons.cancel_outlined),
            label: const Text('Désactiver Premium (démo)'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
              side: const BorderSide(color: Colors.red),
              padding: const EdgeInsets.symmetric(
                horizontal: 24,
                vertical: 14,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Ceci est une démo, aucun paiement réel',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _buildBenefitsList() {
    final benefits = [
      'Tous les marchés (+2.5, -3.5, -4.5, BTTS)',
      'Handicap et but en 1ère mi-temps',
      'Analyse détaillée de chaque match',
      'Prédictions IA optimisées',
      'Sans publicité',
      'Support prioritaire',
    ];
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        children: benefits
            .map(
              (b) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    const Icon(
                      Icons.check_circle,
                      color: Color(0xFF2E7D32),
                      size: 20,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        b,
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(TEXT_DARK),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }

  // ===== PAYWALL (pas premium) =====
  Widget _buildPaywall() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      child: Column(
        children: [
          _buildHero(),
          const SizedBox(height: 20),
          _buildFeatureComparison(),
          const SizedBox(height: 20),
          _buildPricing(),
          const SizedBox(height: 20),
          _buildCTA(),
          const SizedBox(height: 12),
          Text(
            'Démo - aucun paiement réel',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _buildHero() {
    return Container(
      padding: const EdgeInsets.all(24),
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
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          const Icon(
            Icons.workspace_premium,
            color: Colors.amber,
            size: 56,
          ),
          const SizedBox(height: 12),
          const Text(
            'Passe Premium',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Débloque tous les marchés et analyses IA',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.9),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFeatureComparison() {
    final features = [
      ('1X2 + Over 1.5', true, true),
      ('Over 2.5 / Under 3.5 / Under 4.5', false, true),
      ('BTTS (les 2 marquent)', false, true),
      ('Handicap -1', false, true),
      ('But en 1ère mi-temps', false, true),
      ('Analyse courte', true, true),
      ('Analyse IA détaillée', false, true),
      ('Sans publicité', false, true),
      ('2 matchs gratuits / jour', true, false),
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        children: [
          Row(
            children: [
              const SizedBox(width: 4),
              const Expanded(
                child: Text(
                  'Fonctionnalité',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: Color(TEXT_DARK),
                  ),
                ),
              ),
              SizedBox(
                width: 60,
                child: Text(
                  'Gratuit',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: Colors.grey.shade600,
                  ),
                ),
              ),
              SizedBox(
                width: 60,
                child: Text(
                  'Premium',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: Colors.orange.shade700,
                  ),
                ),
              ),
            ],
          ),
          const Divider(height: 20),
          ...features.map(
            (f) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      f.$1,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(TEXT_DARK),
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 60,
                    child: Icon(
                      f.$2 ? Icons.check : Icons.close,
                      color:
                          f.$2 ? const Color(0xFF2E7D32) : Colors.grey.shade400,
                      size: 18,
                    ),
                  ),
                  SizedBox(
                    width: 60,
                    child: Icon(
                      f.$3 ? Icons.check : Icons.close,
                      color:
                          f.$3 ? const Color(0xFF2E7D32) : Colors.grey.shade400,
                      size: 18,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPricing() {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _pricingCard(
                title: 'Mensuel',
                price: '9,99 €',
                period: '/mois',
                badge: null,
                selected: !_yearly,
                onTap: () => setState(() => _yearly = false),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _pricingCard(
                title: 'Annuel',
                price: '59,99 €',
                period: '/an',
                badge: '-50%',
                selected: _yearly,
                onTap: () => setState(() => _yearly = true),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _pricingCard({
    required String title,
    required String price,
    required String period,
    required String? badge,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: selected ? const Color(PRIMARY_COLOR) : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? const Color(PRIMARY_COLOR) : Colors.grey.shade300,
            width: selected ? 2 : 1,
          ),
          boxShadow: selected
              ? [
                  BoxShadow(
                    color: const Color(PRIMARY_COLOR).withValues(alpha: 0.25),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Column(
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: selected ? Colors.white : const Color(TEXT_DARK),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  price,
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    color: selected ? Colors.white : const Color(PRIMARY_COLOR),
                  ),
                ),
                Text(
                  period,
                  style: TextStyle(
                    fontSize: 11,
                    color: selected ? Colors.white70 : Colors.grey.shade600,
                  ),
                ),
              ],
            ),
            if (badge != null)
              Positioned(
                top: -24,
                right: -8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.amber.shade600,
                    borderRadius: BorderRadius.circular(8),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.amber.withValues(alpha: 0.4),
                        blurRadius: 8,
                      ),
                    ],
                  ),
                  child: Text(
                    badge,
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildCTA() {
    return SizedBox(
      width: double.infinity,
      height: 54,
      child: ElevatedButton(
        onPressed: _activate,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(PRIMARY_COLOR),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
        child: Text(
          _yearly
              ? 'Démarrer l\'essai - 59,99 €/an'
              : 'Démarrer l\'essai - 9,99 €/mois',
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}

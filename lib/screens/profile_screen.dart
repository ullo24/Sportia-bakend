import 'package:flutter/material.dart';
import '../config.dart';
import '../user_service.dart';
import 'login_screen.dart';
import 'premium_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _isPremium = false;
  bool _isAdmin = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await UserService.isPremium();
    final a = await UserService.isAdmin();
    if (mounted) {
      setState(() {
        _isPremium = p;
        _isAdmin = a;
      });
    }
  }

  Future<void> _openPremium() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const PremiumScreen()),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: _isPremium
                  ? [const Color(0xFFF57C00), const Color(0xFFFFA726)]
                  : [const Color(PRIMARY_COLOR), const Color(ACCENT_COLOR)],
            ),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: (_isPremium ? Colors.orange : const Color(ACCENT_COLOR))
                    .withValues(alpha: 0.3),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 3),
                ),
                child: CircleAvatar(
                  radius: 44,
                  backgroundColor: Colors.white,
                  child: Icon(
                    _isPremium ? Icons.workspace_premium : Icons.person,
                    size: 52,
                    color: _isPremium
                        ? Colors.orange.shade700
                        : const Color(PRIMARY_COLOR),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                _isAdmin ? 'Super Admin' : 'Utilisateur',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                _isPremium ? 'Premium activé' : 'Version gratuite',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.85),
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        if (!_isPremium)
          Card(
            elevation: 4,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: _openPremium,
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
                        Icon(Icons.workspace_premium,
                            color: Colors.white, size: 28),
                        SizedBox(width: 8),
                        Text(
                          'Passer Premium',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Tous les marchés : +2.5, BTTS,\nHandicap, 1ère MT, analyse détaillée',
                      style: TextStyle(color: Colors.white, fontSize: 13),
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _openPremium,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: Colors.orange.shade700,
                        ),
                        child: const Text('Découvrir les offres'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        if (_isPremium)
          Card(
            elevation: 4,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: _openPremium,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  gradient: LinearGradient(
                    colors: [Colors.amber.shade400, Colors.orange.shade600],
                  ),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.workspace_premium,
                        color: Colors.white, size: 32),
                    SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Premium actif',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 17,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Gérer mon abonnement',
                            style:
                                TextStyle(color: Colors.white70, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right, color: Colors.white),
                  ],
                ),
              ),
            ),
          ),
        const SizedBox(height: 16),
        Card(
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            children: [
              ListTile(
                leading: const Icon(Icons.notifications_outlined,
                    color: Color(PRIMARY_COLOR)),
                title: const Text('Notifications'),
                trailing: Switch(
                  value: true,
                  activeColor: const Color(ACCENT_COLOR),
                  onChanged: (_) {},
                ),
              ),
              const Divider(height: 1),
              ListTile(
                leading:
                    const Icon(Icons.info_outline, color: Color(PRIMARY_COLOR)),
                title: const Text('À propos'),
                subtitle: const Text('Version 2.0.0'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {},
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.logout, color: Colors.red),
                title: const Text('Déconnexion',
                    style: TextStyle(color: Colors.red)),
                onTap: () async {
                  await UserService.logout();
                  if (!mounted) return;
                  Navigator.pushAndRemoveUntil(
                    context,
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (route) => false,
                  );
                },
              ),
            ],
          ),
        ),
      ],
    );
  }
}
